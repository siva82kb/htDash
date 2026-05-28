from flask import Blueprint, request, jsonify, render_template, redirect, url_for, session as flask_session
from pathlib import Path
from utils.data_access import (
    get_patients_for_user, derive_status, get_hospital_folder, find_patient_folder,
    read_patient_meta, write_patient_meta, create_patient_folders, generate_homer_id,
    create_patient_log, write_patient_log, get_patients_path,
    get_available_devices, read_device_inventory, write_device_inventory, read_device_assignments,
    write_device_assignments, write_device_log, mark_device_lost,
    mark_device_faulty, mark_device_not_faulty,
    read_fault_reports, write_fault_reports, read_sims, write_sims,
)
from utils.protocol_events import (
    create_protocol_events, populate_activation_dates,
    set_free_event, read_protocol_events, write_protocol_events, load_study_protocol,
)
from utils.device_events import append_device_event
from utils.date_validation import validate_completion_date, validate_event_date, get_date_rules
import os
import csv
import json
import shutil
from datetime import datetime, timedelta, date
from config import Config
from models.user import current_session
from utils.file_handlers import FileHandler
from utils.file_handlers import FileHandler as FH
from utils.s3_operations import S3Operations
from utils.data_processors import DataProcessor
import uuid
import qrcode
import io
import base64



def _parse_date_flex(date_str):
    """Parse multiple possible date formats."""
    if not date_str:
        return None

    formats = (
        '%Y-%m-%d',
        '%d-%m-%Y',
        '%Y-%m-%dT%H:%M',   # <-- ADD THIS
        '%Y-%m-%dT%H:%M:%S' # <-- optional (safer)
    )

    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue

    return None

bp = Blueprint("user_management", __name__)


def _filer():
    """loginid of the current request's user — stamped as `filed_by` on every filed event."""
    return flask_session.get('loginid', 'unknown')


def _apply_event_notes_count(items, priv):
    """Stamp role-filtered `event_notes_count` on each item and strip the raw
    `event_notes` field so its content never leaves this endpoint.

    Notes are role-private — admins see all buckets; therapist/engineer see
    only their own. Content is served by `routes/notes.py` event-note endpoints
    (role-filtered there too). Used by `api_patient_events` and `api_call_logs`
    so every event-card surface gets the same badge count on first render."""
    for item in items:
        _en = item.get('event_notes') or {}
        if priv == 'admin':
            item['event_notes_count'] = sum(len(v) for v in _en.values() if isinstance(v, list))
        elif priv in ('therapist', 'engineer'):
            item['event_notes_count'] = len(_en.get(priv) or [])
        else:
            item['event_notes_count'] = 0
        item.pop('event_notes', None)


def _next_wr_alias(events_data):
    """Compute the next `WR##` alias for this patient.

    Watch records are the one chain-style event whose completions land in
    `events_data['complete']` (not in a `free.*` bucket), so the count comes
    from filtering complete[] by `protocol_event_id == 'watch_record'`.
    See CLAUDE.md → "Watch Records tab"."""
    max_n = 0
    for e in events_data.get('complete', []) or []:
        if e.get('protocol_event_id') != 'watch_record':
            continue
        a = (e.get('alias') or '')
        if a.startswith('WR'):
            try:
                max_n = max(max_n, int(a[2:]))
            except ValueError:
                pass
    return f"WR{max_n + 1:02d}"


def _next_call_alias(events_data):
    """Compute the next `Call-###` alias for this patient.

    Shared per-patient sequence across all four therapist-conducted call types:
    `patient_call`, `followup_call_d07`, `followup_call_d21`, and
    `adverse_event_followup`. Counter is independent of AE/RI/ODI aliases.
    See CLAUDE.md → "Call Logs tab"."""
    max_n = 0
    free = events_data.get('free', {}) or {}
    for bucket in ('patient_call', 'adverse_event_followup'):
        for e in free.get(bucket, []) or []:
            a = (e.get('alias') or '')
            if a.startswith('Call-'):
                try:
                    max_n = max(max_n, int(a[5:]))
                except ValueError:
                    pass
    for e in events_data.get('complete', []) or []:
        if e.get('protocol_event_id') in ('followup_call_d07', 'followup_call_d21'):
            a = (e.get('alias') or '')
            if a.startswith('Call-'):
                try:
                    max_n = max(max_n, int(a[5:]))
                except ValueError:
                    pass
    return f"Call-{max_n + 1:03d}"


def _outside_assessment_window(patient, pid, date_str):
    """Returns True if `date_str` (YYYY-MM-DDTHH:MM or YYYY-MM-DD) falls outside
    the protocol-defined ideal window for the assessment `pid`. Uses
    `study_protocol.json` windows (same source as `_assessment_windows` in
    `api_patient_events`), interpreted 1-based per the protocol convention:
    Day 1 = activationDate itself, so `start_day - 1` is the offset in days.

    Returns False when the window cannot be computed (missing activation date,
    missing protocol definition, malformed input), so the caller defaults to
    "in window" and skips the reason gate."""
    if not patient or not patient.get('activationDate') or not date_str:
        return False
    try:
        act_dt = datetime.fromisoformat(patient['activationDate']).date()
        date_d = datetime.strptime(date_str[:10], '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return False
    protocol = load_study_protocol()
    group = patient.get('group') or ''
    for entry in (protocol.get(group, []) or []) + (protocol.get('shared', []) or []):
        if entry.get('id') == pid:
            win = entry.get('window') or {}
            if 'start_day' in win and 'end_day' in win:
                start = act_dt + timedelta(days=win['start_day'] - 1)
                end   = act_dt + timedelta(days=win['end_day']   - 1)
                return date_d < start or date_d > end
            return False
    return False


_CALL_MODES = ('audio', 'video')


def _bad_outcome(no_issue, triggered_items):
    """Outcome-group gate. Returns (jsonify(error), 400) when the outcome
    selection is invalid (both sides set or neither set), else None. Same
    semantics as the patient_call route used to enforce inline — pulled into
    a helper so activation / home_visit / followup_call / patient_call all
    apply the identical rule. See CLAUDE.md → "Outcome group convention"."""
    if no_issue and triggered_items:
        return (jsonify({'error': '"No issue" cannot be combined with any triggered events.'}), 400)
    if not no_issue and not triggered_items:
        return (jsonify({'error': 'Please indicate what came out of this (select "No issue" or one of the issue types).'}), 400)
    return None


def _bad_call_mode(value):
    """Call-mode gate. Returns (jsonify(error), 400) when value is missing or
    outside {"audio","video"}, else None. Applied to every call route
    (patient_call, followup_call_d07, followup_call_d21)."""
    if value not in _CALL_MODES:
        return (jsonify({'error': 'Call mode is required and must be "audio" or "video".'}), 400)
    return None


def _bad_date(patient, value, event_id=None, events_data=None):
    """Date Rule Framework gate. Returns a (jsonify(error), 400) response tuple
    when `value` violates the applicable rule (per-event when `event_id` is in
    `config/date_rules.json` events, else the default rule), else None. Routes
    use the walrus pattern:  `if r := _bad_date(patient, event_date): return r`.
    For events with per-event overrides (e.g. exp_device_install, activation),
    pass `event_id` and `events_data` so the resolver can dereference
    `event:<id>` tokens against currently-completed entries."""
    err = validate_event_date(patient, value, event_id=event_id, events_data=events_data)
    return (jsonify({'error': err}), 400) if err else None


def _wdu_event_name(entry, fallback='AG Watch Data Upload'):
    """Per-entry display name for a watch_data_upload event: limb + watch id, so the
    right/left tasks are distinguishable in the event lists. Kept in sync with the
    same helper in routes/dashboard.py."""
    limb = (entry.get('limb') or '').title()
    wid  = entry.get('watch_id') or ''
    return f"AG Watch Data Upload — {limb} ({wid})" if (limb or wid) else fallback


# ── URL-routed patients page ───────────────────────────────────────────────────

@bp.route('/patients', methods=['GET'])
def patients_page():
    if not flask_session.get('login_place'):
        return redirect(url_for('login'))
    return render_template('patients.html', active_page='patients')


@bp.route('/patients/<homer_id>', methods=['GET'])
def patient_detail_page(homer_id):
    if not flask_session.get('login_place'):
        return redirect(url_for('login'))
    return render_template('patient_detail.html', homer_id=homer_id, place=flask_session.get('login_place'),
                           active_page='patients', date_rules=get_date_rules())


@bp.route('/api/patients/<homer_id>', methods=['GET'])
def api_patient_detail(homer_id):
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400
    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    return jsonify({**patient, 'status': derive_status(patient)})


def _topo_sort(events, event_defs, date_fn):
    """Group events by date_fn, topo-sort within each group (parents before dependents),
    return in ascending date order.

    Ordering edges come from both `depends_on` (hard blocking) and `comes_after`
    (soft display hint) in event_defs. Only `depends_on` drives the blocked_by badge;
    both fields drive this sort.
    """
    events_by_date = {}
    for ev in events:
        events_by_date.setdefault(date_fn(ev), []).append(ev)

    result = []
    for date_key in sorted(events_by_date):
        group = events_by_date[date_key]
        if len(group) <= 1:
            result.extend(group)
            continue
        ids_in_group = {ev['protocol_event_id'] for ev in group}
        ev_map       = {ev['protocol_event_id']: ev for ev in group}
        in_degree    = {ev['protocol_event_id']: 0 for ev in group}
        dependents   = {ev['protocol_event_id']: [] for ev in group}
        for ev in group:
            pid  = ev['protocol_event_id']
            def_entry = event_defs.get(pid, {})
            deps = list(def_entry.get('depends_on') or []) + list(def_entry.get('comes_after') or [])
            for d in deps:
                if d in ids_in_group:
                    in_degree[pid] += 1
                    dependents[d].append(pid)
        queue        = [ev for ev in group if in_degree[ev['protocol_event_id']] == 0]
        sorted_group = []
        while queue:
            ev = queue.pop(0)
            sorted_group.append(ev)
            for dep_pid in dependents[ev['protocol_event_id']]:
                in_degree[dep_pid] -= 1
                if in_degree[dep_pid] == 0:
                    queue.append(ev_map[dep_pid])
        placed = {ev['protocol_event_id'] for ev in sorted_group}
        sorted_group.extend(ev for ev in group if ev['protocol_event_id'] not in placed)
        result.extend(sorted_group)
    return result


def _topo_descendants_first(events, event_defs):
    """Re-order a list of events so that dependents appear BEFORE their parents
    (reverse of the parents-before-dependents topo used for overdue/upcoming).
    Edges come from `depends_on` + `comes_after` on each event_def. Events with
    no topo relationship to anything else in the list keep their input order
    (stable sort by negative depth)."""
    if len(events) <= 1:
        return list(events)
    ids_in_group = {ev.get('protocol_event_id') for ev in events}
    depth_cache  = {}

    def depth(pid):
        if pid in depth_cache:
            return depth_cache[pid]
        defn = event_defs.get(pid) or {}
        deps = list(defn.get('depends_on') or []) + list(defn.get('comes_after') or [])
        rel  = [depth(d) for d in deps if d in ids_in_group and d != pid]
        depth_cache[pid] = (max(rel) + 1) if rel else 0
        return depth_cache[pid]

    return sorted(events, key=lambda ev: -depth(ev.get('protocol_event_id')))


def _topo_groups_apply_descendants_first(events, event_defs):
    """In-place: within runs of consecutive entries sharing (completion_date,
    filed_by), apply `_topo_descendants_first`. Assumes the input is already
    sorted by (completion_date desc, filed_at desc) — within each topo'd run,
    same-depth events preserve their filed_at-desc order via stable sort."""
    i = 0
    n = len(events)
    while i < n:
        ck = events[i].get('completion_date')
        fb = events[i].get('filed_by')
        j = i + 1
        while j < n and events[j].get('completion_date') == ck and events[j].get('filed_by') == fb:
            j += 1
        if j - i > 1:
            events[i:j] = _topo_descendants_first(events[i:j], event_defs)
        i = j


def _apply_ordering_rules(events):
    """Post-sort pass: schedule_a1_call and schedule_a2_call always appear
    immediately before their assessment counterpart when both are in the same list."""
    result = list(events)
    for call_pid, assess_pid in (('schedule_a1_call', 'a1_assessment'),
                                  ('schedule_a2_call', 'a2_assessment')):
        call_idx   = next((i for i, e in enumerate(result) if e['protocol_event_id'] == call_pid), None)
        assess_idx = next((i for i, e in enumerate(result) if e['protocol_event_id'] == assess_pid), None)
        if call_idx is not None and assess_idx is not None and call_idx > assess_idx:
            ev = result.pop(call_idx)
            result.insert(assess_idx, ev)
    return result


def _cancel_training_ended_stubs(events_data, protocol_event_ids, cancelled_at):
    """Move incomplete stubs to cancelled[] with reason 'training_ended'."""
    ids = frozenset(protocol_event_ids)
    remaining = []
    for e in events_data.get('incomplete', []):
        if e.get('protocol_event_id') in ids:
            events_data.setdefault('cancelled', []).append({
                **e,
                'cancelled_at':        cancelled_at,
                'cancellation_reason': 'training_ended',
            })
        else:
            remaining.append(e)
    events_data['incomplete'] = remaining


def _auto_terminate_pause_if_expired(patient, folder, homer_id, events_data):
    """Close the open pause epoch at Day 28 end-of-day if the training window has passed."""
    if not patient.get('trainingPausedDate'):
        return
    activation = patient.get('activationDate')
    if not activation:
        return
    try:
        activation_date = datetime.fromisoformat(activation).date()
    except Exception:
        return
    day28_end = activation_date + timedelta(days=28)
    if date.today() < day28_end:
        return

    paused_since_str = patient['trainingPausedDate']
    try:
        paused_since = datetime.fromisoformat(paused_since_str).date()
    except Exception:
        return

    pause_days = max(0, (day28_end - paused_since).days)
    day28_end_str = datetime.combine(day28_end, datetime.min.time().replace(hour=23, minute=59)).isoformat()

    open_epoch = next((e for e in patient.get('pauseHistory', []) if e.get('end') is None), None)
    if open_epoch:
        open_epoch['end']  = day28_end_str
        open_epoch['days'] = pause_days
        open_epoch['end_event_id'] = None

    patient['cumulativePauseDays'] = (patient.get('cumulativePauseDays') or 0) + pause_days
    patient['trainingPausedDate']  = None

    if patient['cumulativePauseDays'] > 10 and not patient.get('brokenProtocolDate'):
        patient['brokenProtocolDate'] = day28_end_str

    _cancel_training_ended_stubs(events_data, ['watch_record'], day28_end_str)

    write_patient_meta(folder, homer_id, patient)
    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)


@bp.route('/api/patients/<homer_id>/events', methods=['GET'])
def api_patient_events(homer_id):
    """Return overdue and upcoming incomplete protocol events for a single patient."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    protocol = load_study_protocol()

    patient    = read_patient_meta(folder, homer_id)
    events_data = read_protocol_events(folder, homer_id)

    # Auto-terminate pause if Day 28 has passed
    if patient:
        _auto_terminate_pause_if_expired(patient, folder, homer_id, events_data)

    # Lazy cleanup: cancel stray watch_record stubs for patients whose training has ended.
    # Covers data written before the no-seed guard was in place.
    if patient and events_data:
        _st = derive_status(patient)
        if _st in ('post_training', 'training_completed', 'a1_completed', 'all_completed'):
            _stray = any(
                e.get('protocol_event_id') == 'watch_record'
                for e in events_data.get('incomplete', [])
            )
            if _stray:
                _cancel_training_ended_stubs(
                    events_data, ['watch_record'],
                    datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
                )
                write_protocol_events(folder, homer_id, events_data)

    # Auto-seeding for assessment scheduling stubs.
    if patient and events_data and patient.get('activationDate'):
        _now_str  = datetime.now().strftime('%Y-%m-%dT%H:%M')
        _filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        _dirty    = False

        # A1: seed schedule_a1_call when a1_assessment.appointment_date is null and no stub exists.
        # Also clean up any orphaned schedule_a1_call stubs if a1 is complete or window has closed.
        _a1_complete = any(
            e.get('protocol_event_id') == 'a1_assessment'
            for e in events_data.get('complete', [])
        )
        _a1_stub_exists = any(
            e.get('protocol_event_id') == 'schedule_a1_call'
            for e in events_data.get('incomplete', [])
        )
        # Compute A1 window bounds unconditionally (needed for both cleanup and seeding).
        _a1_window_open = True
        _a1_window_leadtime = False
        _a1_seed_date = None
        try:
            _a1_def = next((e for e in protocol.get('shared', []) if e['id'] == 'a1_assessment'), None)
            if _a1_def and _a1_def.get('window') and patient and patient.get('activationDate'):
                _act = datetime.fromisoformat(patient['activationDate']).date()
                _a1_start = _act + timedelta(days=_a1_def['window']['start_day'] - 1)
                _a1_end   = _act + timedelta(days=_a1_def['window']['end_day']   - 1)
                _a1_window_open     = date.today() <= _a1_end
                _a1_window_leadtime = date.today() >= _a1_start - timedelta(days=7)
                _a1_seed_date       = (_a1_start - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M')
        except Exception:
            pass
        _a1_stub = next((e for e in events_data.get('incomplete', [])
                         if e.get('protocol_event_id') == 'schedule_a1_call'), None)
        # Remove stub if: complete, window closed, not yet in lead time, or scheduled_date is wrong.
        _a1_stub_stale = (_a1_stub and _a1_seed_date and
                          (_a1_stub.get('scheduled_date') or [None])[0] != _a1_seed_date)
        if _a1_stub_exists and (_a1_complete or not _a1_window_open or not _a1_window_leadtime or _a1_stub_stale):
            events_data['incomplete'] = [
                e for e in events_data['incomplete']
                if e.get('protocol_event_id') != 'schedule_a1_call'
            ]
            _a1_stub_exists = False
            _dirty = True
        if not _a1_complete and not _a1_stub_exists:
            _a1_inc = next((
                e for e in events_data.get('incomplete', [])
                if e.get('protocol_event_id') == 'a1_assessment'
            ), None)
            _a1_training_ended = bool(patient and (
                patient.get('trainingCompletionDate') or
                patient.get('brokenProtocolDate') or
                patient.get('discontinuationDate')
            ))
            if (_a1_inc and _a1_inc.get('appointment_date') is None
                    and _a1_training_ended and _a1_window_open and _a1_window_leadtime
                    and _a1_seed_date):
                events_data.setdefault('incomplete', []).insert(0, {
                    'id':                str(uuid.uuid4()),
                    'protocol_event_id': 'schedule_a1_call',
                    'scheduled_date':    [_a1_seed_date, _a1_seed_date],
                    'filed_at':          _filed_at,
                    'filed_by':   _filer(),
                })
                _dirty = True

        # A2: seed schedule_a2_call when a2_assessment.appointment_date is null OR 7 days before window.
        _a2_def = None
        for _e in protocol.get('shared', []):
            if _e['id'] == 'a2_assessment':
                _a2_def = _e
                break
        if _a2_def and _a2_def.get('window'):
            try:
                _act_date = datetime.fromisoformat(patient['activationDate']).date()
                _a2_start = _act_date + timedelta(days=_a2_def['window']['start_day'] - 1)
                _today    = date.today()
                _a2_complete = any(
                    e.get('protocol_event_id') == 'a2_assessment'
                    for e in events_data.get('complete', [])
                )
                _a2_stub_exists = any(
                    e.get('protocol_event_id') == 'schedule_a2_call'
                    for e in events_data.get('incomplete', [])
                )
                _a2_inc = next((
                    e for e in events_data.get('incomplete', [])
                    if e.get('protocol_event_id') == 'a2_assessment'
                ), None)
                _a2_end         = _act_date + timedelta(days=_a2_def['window']['end_day'] - 1)
                _a2_null_date   = _a2_inc and _a2_inc.get('appointment_date') is None
                _a2_near_window = _today >= (_a2_start - timedelta(days=7))
                _a2_window_open = _today <= _a2_end

                _a2_seed_date = (_a2_start - timedelta(days=7)).strftime('%Y-%m-%dT%H:%M')
                _a2_stub_obj  = next((e for e in events_data.get('incomplete', [])
                                      if e.get('protocol_event_id') == 'schedule_a2_call'), None)
                _a2_stub_stale = (_a2_stub_obj and
                                  (_a2_stub_obj.get('scheduled_date') or [None])[0] != _a2_seed_date)
                # Clean up orphaned stub when A2 is complete, already scheduled, window closed, or stale.
                if _a2_stub_exists and (_a2_complete or not _a2_null_date or not _a2_window_open or _a2_stub_stale):
                    events_data['incomplete'] = [
                        e for e in events_data['incomplete']
                        if e.get('protocol_event_id') != 'schedule_a2_call'
                    ]
                    _a2_stub_exists = False
                    _dirty = True
                if (not _a2_complete and not _a2_stub_exists
                        and _a2_null_date and _a2_near_window and _a2_window_open):
                        events_data.setdefault('incomplete', []).insert(0, {
                            'id':                str(uuid.uuid4()),
                            'protocol_event_id': 'schedule_a2_call',
                            'scheduled_date':    [_a2_seed_date, _a2_seed_date],
                            'filed_at':          _filed_at,
                            'filed_by':   _filer(),
                        })
                        _dirty = True
            except Exception:
                pass

        if _dirty:
            write_protocol_events(folder, homer_id, events_data)

    # Lazy seeding for device_return when training ends (any path).
    if patient and events_data:
        _training_ended = bool(
            patient.get('trainingCompletionDate') or
            patient.get('brokenProtocolDate') or
            patient.get('discontinuationDate')
        )
        if _training_ended:
            _dr_in_incomplete = any(
                e.get('protocol_event_id') == 'device_return'
                for e in events_data.get('incomplete', [])
            )
            _dr_complete = bool(events_data.get('free', {}).get('device_return'))
            if not _dr_in_incomplete and not _dr_complete:
                _dr_now      = datetime.now().strftime('%Y-%m-%dT%H:%M')
                _dr_filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
                events_data.setdefault('incomplete', []).append({
                    'id':                str(uuid.uuid4()),
                    'protocol_event_id': 'device_return',
                    'scheduled_date':    [_dr_now, _dr_now],
                    'filed_at':          _dr_filed_at,
                    'filed_by':   _filer(),
                })
                write_protocol_events(folder, homer_id, events_data)

    # Build event_defs from shared + patient's group only so group-specific
    # depends_on (e.g. activation→exp_device_install for experimental) are not
    # overwritten by the other group's definition.
    event_defs = {}
    for e in protocol.get('shared', []):
        event_defs[e['id']] = e
    for e in protocol.get((patient or {}).get('group', ''), []):
        event_defs[e['id']] = e
    event_defs['training_pause_followup'] = {'name': 'Training Pause Follow-up', 'depends_on': []}
    event_defs['schedule_a1_call']        = {'name': 'Schedule A1 Assessment',   'depends_on': []}
    event_defs['schedule_a2_call']        = {'name': 'Schedule A2 Assessment',   'depends_on': []}
    event_defs['device_return']           = {'name': 'Device Return',            'depends_on': []}
    event_defs['watch_data_upload']       = {'name': 'AG Watch Data Upload',     'depends_on': []}

    # Precompute A1/A2 window dates from activationDate for row display
    _assessment_windows = {}
    if patient and patient.get('activationDate'):
        try:
            _act_dt = datetime.fromisoformat(patient['activationDate']).date()
            for _pid in ('a1_assessment', 'a2_assessment'):
                _def = event_defs.get(_pid, {})
                _win = _def.get('window')
                if _win:
                    _ws = _act_dt + timedelta(days=_win['start_day'] - 1)
                    _we = _act_dt + timedelta(days=_win['end_day'] - 1)
                    _assessment_windows[_pid] = (_ws.isoformat(), _we.isoformat())
        except Exception:
            pass

    if not events_data:
        return jsonify({'overdue': [], 'upcoming': []})

    today = datetime.now().date()
    overdue  = []
    upcoming = []

    is_broken_protocol = bool(patient and derive_status(patient) == 'broken_protocol')

    # Build set of completed event IDs for dependency checking. Includes both
    # `complete[]` (regular protocol events) AND any non-empty `free.<id>[]`
    # bucket (chained / unscheduled free events such as `watch_record`), so that
    # depends_on can reference free-event types. Satisfied-by-any-completion:
    # one filed entry of the right type is enough to clear the dependency.
    completed_ids = {e['protocol_event_id'] for e in events_data.get('complete', [])}
    for free_type, free_list in (events_data.get('free') or {}).items():
        if free_list:
            completed_ids.add(free_type)
    # Build set of all known event IDs (incomplete + complete) — only these can block
    known_ids = completed_ids | {e['protocol_event_id'] for e in events_data.get('incomplete', [])}

    # Backfill missing aliases (one-time repair for pre-alias data). Each
    # bucket has its own per-patient counter — AE, RI, and ODI are independent
    # sequences. Re-sort by completion_date/filed_at so backfilled numbers
    # match chronological order even if the bucket was written out of order.
    _alias_dirty = False
    for _bucket, _prefix in (('adverse_event', 'AE'),
                             ('robot_issue_call', 'RI'),
                             ('other_device_issue_call', 'ODI')):
        _entries = events_data.get('free', {}).get(_bucket, [])
        if _entries and any(not e.get('alias') for e in _entries):
            _sorted = sorted(_entries, key=lambda e: e.get('completion_date') or e.get('filed_at') or '')
            for i, e in enumerate(_sorted):
                if not e.get('alias'):
                    e['alias'] = f"{_prefix}{i + 1:02d}"
                    _alias_dirty = True

    # WR## alias: per-patient sequence on completed `watch_record` entries.
    # Unlike the AE/RI/ODI buckets, watch_record completions land in `complete[]`
    # (not `free.*`), so filter complete[] by protocol_event_id.
    _wr_entries = [e for e in (events_data.get('complete', []) or [])
                   if e.get('protocol_event_id') == 'watch_record']
    if _wr_entries and any(not (e.get('alias') or '').startswith('WR') for e in _wr_entries):
        _max_wr = 0
        for _e in _wr_entries:
            _a = (_e.get('alias') or '')
            if _a.startswith('WR'):
                try:
                    _max_wr = max(_max_wr, int(_a[2:]))
                except ValueError:
                    pass
        _unaliased = sorted(
            [_e for _e in _wr_entries if not (_e.get('alias') or '').startswith('WR')],
            key=lambda e: e.get('completion_date') or e.get('filed_at') or '',
        )
        for _i, _e in enumerate(_unaliased):
            _e['alias'] = f"WR{_max_wr + _i + 1:02d}"
        _alias_dirty = True

    # Call-### alias: shared sequence across patient_call, followup_call_d07/d21,
    # and adverse_event_followup. Collect every completed call entry across the
    # four buckets, sort chronologically, then assign aliases to unaliased ones
    # starting from one above the highest existing Call-###. Stable for already-
    # aliased entries; new numbers are appended in chronological order.
    _call_entries = []
    for _e in events_data.get('free', {}).get('patient_call', []) or []:
        _call_entries.append(_e)
    for _e in events_data.get('free', {}).get('adverse_event_followup', []) or []:
        _call_entries.append(_e)
    for _e in events_data.get('complete', []) or []:
        if _e.get('protocol_event_id') in ('followup_call_d07', 'followup_call_d21'):
            _call_entries.append(_e)
    if _call_entries and any(not (e.get('alias') or '').startswith('Call-') for e in _call_entries):
        _max_call = 0
        for _e in _call_entries:
            _a = (_e.get('alias') or '')
            if _a.startswith('Call-'):
                try:
                    _max_call = max(_max_call, int(_a[5:]))
                except ValueError:
                    pass
        _unaliased = sorted(
            [_e for _e in _call_entries if not (_e.get('alias') or '').startswith('Call-')],
            key=lambda e: e.get('completion_date') or e.get('filed_at') or '',
        )
        for _i, _e in enumerate(_unaliased):
            _e['alias'] = f"Call-{_max_call + _i + 1:03d}"
        _alias_dirty = True

    if _alias_dirty:
        write_protocol_events(folder, homer_id, events_data)

    # Alias lookup for follow-up event name construction
    ae_alias_map = {
        e['id']: e['alias']
        for e in events_data.get('free', {}).get('adverse_event', [])
        if e.get('alias')
    }

    # When training is paused only follow-up events (AE/RI resolution chain) are shown.
    # training_completion_d29 is also visible — it can be filed independently of the AE chain.
    _PAUSE_VISIBLE = frozenset({
        'adverse_event', 'adverse_event_followup', 'adverse_event_followup_visit',
        'adverse_event_clinical_visit',
        'robot_issue_call', 'robot_issue_visit', 'resolve_robot_issue_visit',
        'other_device_issue_call', 'other_device_issue_visit',
        'training_completion_d29',
        'device_return',
        'watch_data_upload',
    })
    # For broken_protocol patients only AE/RI/ODI chains + assessments are interactive.
    _BROKEN_PROTOCOL_INTERACTIVE = frozenset({
        'adverse_event', 'adverse_event_followup',
        'adverse_event_followup_visit', 'adverse_event_clinical_visit',
        'robot_issue_call', 'robot_issue_visit', 'resolve_robot_issue_visit',
        'other_device_issue_call', 'other_device_issue_visit',
        'discontinuation_reminder',
        'a1_assessment', 'a2_assessment',
        'schedule_a1_call', 'schedule_a2_call',
        'device_return',
        'watch_data_upload',
    })
    # For discontinued patients only open AE chains + assessments remain relevant.
    _DISCONTINUED_VISIBLE = frozenset({
        'adverse_event', 'adverse_event_followup',
        'adverse_event_followup_visit', 'adverse_event_clinical_visit',
        'a1_assessment', 'a2_assessment',
        'schedule_a1_call', 'schedule_a2_call',
        'device_return',
        'watch_data_upload',
    })
    # For post_training patients (Day 28 passed, D29 not yet filed): only D29,
    # AE chains, assessments, and device_return are shown.
    _POST_TRAINING_VISIBLE = frozenset({
        'training_completion_d29',
        'adverse_event', 'adverse_event_followup',
        'adverse_event_followup_visit', 'adverse_event_clinical_visit',
        'a1_assessment', 'a2_assessment',
        'schedule_a1_call', 'schedule_a2_call',
        'device_return',
        'watch_data_upload',
    })
    is_paused        = bool(patient and patient.get('trainingPausedDate'))
    is_discontinued  = bool(patient and patient.get('discontinuationDate'))
    is_post_training = bool(patient and derive_status(patient) == 'post_training')

    _ASSESSMENT_PIDS = frozenset({'a1_assessment', 'a2_assessment'})

    for entry in events_data.get('incomplete', []):
        pid   = entry.get('protocol_event_id')
        sched = entry.get('scheduled_date')

        if not sched or not isinstance(sched, list) or len(sched) < 2:
            # Assessment events are shown even without a scheduled appointment date.
            # Use window dates for categorisation; sched stays null for the client.
            if pid not in _ASSESSMENT_PIDS or pid not in _assessment_windows:
                continue
            _ws_str, _we_str = _assessment_windows[pid]
            try:
                start_date = datetime.fromisoformat(_ws_str).date()
                end_date   = datetime.fromisoformat(_we_str).date()
            except Exception:
                continue
            sched = None
        else:
            try:
                start_date = datetime.fromisoformat(sched[0]).date()
                end_date   = datetime.fromisoformat(sched[1]).date()
            except Exception:
                continue
            # Assessment events: override categorisation bounds with window dates so
            # days = window_end − today (not appointment_date − today).
            if pid in _ASSESSMENT_PIDS and pid in _assessment_windows:
                try:
                    _ws_str, _we_str = _assessment_windows[pid]
                    start_date = datetime.fromisoformat(_ws_str).date()
                    end_date   = datetime.fromisoformat(_we_str).date()
                except Exception:
                    pass

        # Discontinued patients: only AE follow-up chain + assessments shown.
        if is_discontinued and pid not in _DISCONTINUED_VISIBLE:
            continue

        # For broken_protocol patients: only AE/RI/ODI chains + assessments are shown.
        if is_broken_protocol and pid not in _BROKEN_PROTOCOL_INTERACTIVE:
            continue

        # For post_training patients: only D29, AE chains, assessments, device_return shown.
        if is_post_training and pid not in _POST_TRAINING_VISIBLE:
            continue

        on_hold = is_paused and pid not in _PAUSE_VISIBLE and start_date <= today

        # Compute blocked_by: depends_on entries that are applicable and not yet complete
        dep_ids = event_defs.get(pid, {}).get('depends_on') or []
        blocked_by = [
            event_defs[d]['name'] for d in dep_ids
            if d in known_ids and d not in completed_ids
        ]

        if pid in _AE_FOLLOWUP_LABELS:
            ae_ids  = entry.get('adverse_event_ids') or []
            aliases = [ae_alias_map[aid] for aid in ae_ids if aid in ae_alias_map]
            event_name = f"{_AE_FOLLOWUP_LABELS[pid]}: {', '.join(aliases)}" if aliases else _AE_FOLLOWUP_LABELS[pid]
        elif pid == 'watch_data_upload':
            event_name = _wdu_event_name(entry)
        else:
            event_name = event_defs.get(pid, {}).get('name', pid)

        record = {
            'id':                entry['id'],
            'protocol_event_id': pid,
            'event_name':        event_name,
            'scheduled_date':    sched,
            'blocked_by':        blocked_by,
        }
        if pid in _ASSESSMENT_PIDS and pid in _assessment_windows:
            _ws_str, _we_str = _assessment_windows[pid]
            record['window_start']    = _ws_str
            record['window_end']      = _we_str
            record['appointment_date'] = entry.get('appointment_date')
        if entry.get('triggered_by'):
            record['triggered_by'] = entry['triggered_by']
        if pid == 'watch_data_upload':
            for _f in ('watch_id', 'limb', 'removed_date', 'data_start', 'data_end'):
                record[_f] = entry.get(_f)
        if entry.get('adverse_event_ids') is not None:
            record['adverse_event_ids'] = entry['adverse_event_ids']
        if entry.get('training_stopped'):
            record['training_stopped'] = True

        if on_hold or start_date > today:
            record['days'] = (start_date - today).days
            record['active_window'] = False
            if on_hold:
                record['on_hold'] = True
            upcoming.append(record)
        elif end_date >= today:
            record['days'] = (end_date - today).days
            record['active_window'] = True
            overdue.append(record)
        else:
            record['days'] = (end_date - today).days  # negative
            record['active_window'] = False
            overdue.append(record)

    # Inject discontinuation_reminder synthetic event for broken_protocol patients
    if is_broken_protocol and not events_data.get('free', {}).get('discontinuation'):
        broken_date = (patient or {}).get('brokenProtocolDate') or today.isoformat()
        try:
            broken_sched = datetime.fromisoformat(broken_date).date()
        except Exception:
            broken_sched = today
        overdue.append({
            'id':                'discontinuation_reminder',
            'protocol_event_id': 'discontinuation_reminder',
            'event_name':        'Discontinue Patient',
            'scheduled_date':    [broken_date, broken_date],
            'days':              (broken_sched - today).days,
            'active_window':     False,
            'blocked_by':        [],
        })

    # Active-window first, then past-due; within each sub-group sort by end date
    # and topo-sort within same-end-date groups so parents appear before dependents.
    end_date_fn = lambda ev: (ev['scheduled_date'] or ['', ''])[1][:10]
    active_overdue = sorted([e for e in overdue if e.get('active_window')],  key=end_date_fn)
    past_overdue   = sorted([e for e in overdue if not e.get('active_window')], key=end_date_fn)
    overdue  = _apply_ordering_rules(
        _topo_sort(active_overdue, event_defs, end_date_fn) +
        _topo_sort(past_overdue,   event_defs, end_date_fn)
    )
    upcoming = _apply_ordering_rules(
        _topo_sort(upcoming, event_defs, lambda ev: (ev['scheduled_date'] or ['', ''])[0][:10])
    )

    complete_list = []
    for entry in events_data.get('complete', []):
        pid = entry.get('protocol_event_id', '')
        item = dict(entry)
        item['event_name'] = event_defs.get(pid, {}).get('name', pid)
        complete_list.append(item)

    # Free events are already "complete" — include them so they appear in the
    # timeline and completed-events count.
    _FREE_EVENT_NAMES = {
        'activation_attempt':            'Activation Attempt',
        'd15_attempt':                   'Day 15 Visit Attempt',
        'patient_call':                  'Patient Call',
        'adverse_event':                 'File Adverse Event',
        'adverse_event_followup':        'Adverse Event Follow-up Call',
        'adverse_event_followup_visit':  'Adverse Event Follow-up Visit',
        'adverse_event_clinical_visit':  'Adverse Event Clinical Visit',
        'robot_issue_call':              'Robot Issue — Engineer Call',
        'robot_issue_visit':             'Robot Issue — Engineer Visit',
        'resolve_robot_issue_visit':     'Robot Issue — Replacement Visit',
        'other_device_issue_call':       'Other Device Issue — Engineer Call',
        'other_device_issue_visit':      'Other Device Issue — Engineer Visit',
        'watch_data_upload':             'AG Watch Data Upload',
    }
    for free_type, free_name in _FREE_EVENT_NAMES.items():
        for entry in events_data.get('free', {}).get(free_type, []):
            item = dict(entry)
            item['event_name']        = (_wdu_event_name(entry, free_name)
                                         if free_type == 'watch_data_upload' else free_name)
            item['protocol_event_id'] = free_type
            complete_list.append(item)

    # free.discontinuation is a singleton dict, not a list — handle separately
    disc = events_data.get('free', {}).get('discontinuation')
    if disc and isinstance(disc, dict):
        item = dict(disc)
        item['event_name']        = 'Patient Discontinued'
        item['protocol_event_id'] = 'discontinuation'
        complete_list.append(item)

    # free.device_return is also a singleton dict (only ever one return per patient).
    dr = events_data.get('free', {}).get('device_return')
    if dr and isinstance(dr, dict):
        item = dict(dr)
        item['event_name']        = 'Device Return'
        item['protocol_event_id'] = 'device_return'
        complete_list.append(item)

    # Primary sort: completion_date descending (newest clinical date first),
    # with filed_at as the fallback when completion_date is absent. Tiebreaker:
    # filed_at descending (last filed at the top within same clinical date).
    complete_list.sort(
        key=lambda x: (x.get('completion_date') or x.get('filed_at') or '',
                       x.get('filed_at') or ''),
        reverse=True,
    )

    # Within any run of consecutive entries that share BOTH completion_date AND
    # filed_by, re-order so dependents appear above their parents (reverse of
    # the parents-before-dependents topo used for overdue/upcoming). When
    # filed_by differs across a same-date group the topo pass is skipped and
    # filed_at desc from the primary sort stands. See CLAUDE.md → "Completed-
    # event ordering".
    _topo_groups_apply_descendants_first(complete_list, event_defs)

    _apply_event_notes_count(complete_list, flask_session.get('privilege', ''))

    return jsonify({'overdue': overdue, 'upcoming': upcoming, 'complete': complete_list})


@bp.route('/api/patients/<homer_id>/available-devices', methods=['GET'])
def api_available_devices(homer_id):
    """Return available Pluto/Mars/Modem/Laptop/Agwatch devices plus the patient's current assignments."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    def current_device_id(device_type):
        assignments = read_device_assignments(folder, device_type)
        current = next((a for a in assignments if a.get('returned_date') is None), None)
        return current['device_id'] if current else None

    # Get modem list with SIM info
    modems = get_available_devices(folder, 'modems')
    try:
        all_sims = read_sims(folder)
        sim_map = {s['id']: s for s in all_sims}
    except Exception:
        sim_map = {}

    modems_with_sim = []
    for modem in modems:
        modem_dict = modem.copy() if isinstance(modem, dict) else {'id': modem}
        sim_id = modem_dict.get('sim_id')
        if sim_id and sim_id in sim_map:
            modem_dict['sim_phone'] = sim_map[sim_id].get('phoneNumber', '')
        modems_with_sim.append(modem_dict)

    # Get available SIMs (not currently linked to any modem's sim_id)
    try:
        all_sims = read_sims(folder)
        modem_inv = read_device_inventory(folder, 'modems')
        used_sim_ids = {d.get('sim_id') for d in modem_inv if d.get('sim_id')}
        available_sims = [s for s in all_sims if s['id'] not in used_sim_ids]
    except Exception:
        available_sims = []

    return jsonify({
        'pluto':         get_available_devices(folder, 'pluto'),
        'mars':          get_available_devices(folder, 'mars'),
        'modem':         modems_with_sim,
        'laptop':        get_available_devices(folder, 'laptops'),
        'agwatch':       get_available_devices(folder, 'agwatch'),
        'sims':          available_sims,
        'current_pluto': current_device_id('pluto'),
        'current_mars':  current_device_id('mars'),
        'current_modem': current_device_id('modems'),
        'current_laptop': current_device_id('laptops'),
    })


@bp.route('/api/patients/<homer_id>/available-agwatches', methods=['GET'])
def api_available_agwatches(homer_id):
    """Return available AG watches plus the patient's currently-assigned watches."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    available = get_available_devices(folder, 'agwatch')

    # Also return the currently-assigned watches so the modal can offer
    # "keep same watch" (new_id = old_id) when no swap is needed.
    patient = read_patient_meta(folder, homer_id)
    inventory = {d['id']: d for d in read_device_inventory(folder, 'agwatch')}

    def current_watch(watch_id):
        if not watch_id:
            return None
        d = inventory.get(watch_id)
        return {'id': d['id'], 'serial': d.get('serial', '')} if d else None

    return jsonify({
        'agwatch':       available,
        'current_right': current_watch(patient.get('agWatchRightID')),
        'current_left':  current_watch(patient.get('agWatchLeftID')),
    })


@bp.route('/api/patients/<homer_id>/complete-event/exp_device_install', methods=['POST'])
def api_complete_device_install(homer_id):
    """Complete the exp_device_install protocol event."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    data = request.get_json() or {}
    event_id   = data.get('event_id')
    event_date = data.get('eventDate', '').strip()
    if r := _bad_date(patient, event_date, event_id='exp_device_install'): return r
    pluto_id   = data.get('plutoId', '').strip()
    mars_id    = data.get('marsId', '').strip()
    modem_id   = data.get('modemId', '').strip()
    laptop_id  = data.get('laptopId', '').strip()
    sim_id     = data.get('simId', '').strip()
    demo_done  = bool(data.get('demoDone', False))
    notes      = data.get('notes', '').strip()

    if not event_date:
        return jsonify({'error': 'Event date is required.'}), 400
    if not pluto_id:
        return jsonify({'error': 'Pluto device is required.'}), 400
    if not mars_id:
        return jsonify({'error': 'Mars device is required.'}), 400
    if not modem_id:
        return jsonify({'error': 'Modem device is required.'}), 400
    if not laptop_id:
        return jsonify({'error': 'Laptop device is required.'}), 400
    if not sim_id:
        return jsonify({'error': 'SIM card is required.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    # Find the matching incomplete entry
    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == 'exp_device_install'
         and (event_id is None or e.get('id') == event_id)),
        None
    )
    if not entry:
        return jsonify({'error': 'Event not found in incomplete list.'}), 404

    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    complete_entry = {
        **entry,
        'completion_date': event_date,
        'filed_at':        filed_at,
        'filed_by':   _filer(),
        'pluto_id':        pluto_id,
        'mars_id':         mars_id,
        'modem_id':        modem_id,
        'laptop_id':       laptop_id,
        'sim_id':          sim_id,
        'demo_done':       demo_done,
        'notes':           notes,
    }

    events_data['incomplete'] = [e for e in incomplete if e.get('id') != entry['id']]
    events_data.setdefault('complete', []).append(complete_entry)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    # Record device assignments
    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    for device_type, device_id in (('pluto', pluto_id), ('mars', mars_id), ('modems', modem_id), ('laptops', laptop_id)):
        assignments = read_device_assignments(folder, device_type)
        assignments.append({
            'id':            str(uuid.uuid4()),
            'device_id':     device_id,
            'homer_id':      homer_id,
            'assigned_date': event_date,
            'returned_date': None,
            'assigned_by':   loginid,
            'notes':         notes,
        })
        write_device_assignments(folder, device_type, assignments)
        write_device_log(folder, device_id, loginid, session_id,
                         f'Assigned to {homer_id}')

    # Assign SIM to modem in device inventory
    try:
        modem_inventory = read_device_inventory(folder, 'modems')
        for modem in modem_inventory:
            if modem.get('id') == modem_id:
                modem['sim_id'] = sim_id
                modem['sim_assigned_date'] = event_date
                break
        write_device_inventory(folder, 'modems', {'devices': modem_inventory})
        write_device_log(folder, sim_id, loginid, session_id, f'Assigned to modem {modem_id}')
    except Exception as e:
        # Log but don't fail if SIM assignment has issues
        write_patient_log(folder, homer_id, loginid, session_id, f'Warning: SIM assignment failed - {str(e)}')

    write_patient_log(folder, homer_id, loginid, session_id,
                      f'Device setup completed — Pluto: {pluto_id}, Mars: {mars_id}, Modem: {modem_id}, Laptop: {laptop_id}, SIM: {sim_id}')

    # Record assign device events
    for device_type, device_id in (('pluto', pluto_id), ('mars', mars_id), ('modems', modem_id), ('laptops', laptop_id)):
        append_device_event(folder, device_type, device_id, event_type='assign',
                            by=loginid, homer_id=homer_id)
    append_device_event(folder, 'sims', sim_id, event_type='assign',
                        by=loginid, notes=f'Linked to modem {modem_id}', homer_id=homer_id)

    return jsonify({'ok': True})


@bp.route('/api/patients', methods=['GET'])
def api_patients_list():
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    patients = get_patients_for_user(flask_session['login_place'])
    return jsonify([{**p, 'status': derive_status(p)} for p in patients])


@bp.route('/api/patients', methods=['POST'])
def api_create_patient():
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json() or {}
    hospital_id   = (data.get('hospitalID') or '').strip()
    training_side = (data.get('trainingSide') or '').strip()
    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400
    homer_id = generate_homer_id(folder)
    patient_data = {
        'homerID':                    homer_id,
        'hospitalID':                 hospital_id or None,
        'group':                      None,
        'trainingSide':               training_side or None,
        'enrollDate':                 datetime.now().strftime('%Y-%m-%dT%H:%M'),
        'activationDate':             None,
        'discontinuationDate':        None,
        'trainingCompletionDate':     None,
        'a0CompletionDate':           None,
        'a1CompletionDate':           None,
        'a2CompletionDate':           None,
        'trainingPausedDate':         None,
        'cumulativePauseDays':        0,
        'pauseHistory':               [],
        'brokenProtocolDate':         None,
        'vcgGroup':                   None,
        'agWatchRightID':             None,
        'agWatchLeftID':              None,
    }
    write_patient_meta(folder, homer_id, patient_data)
    create_patient_folders(folder, homer_id, 'unassigned')
    create_patient_log(folder, homer_id)
    write_patient_log(
        folder, homer_id,
        flask_session.get('loginid', 'unknown'),
        flask_session.get('session_id', 0),
        f'Created new patient : {homer_id}.json'
    )
    return jsonify({'status': 'success', 'homerID': homer_id}), 201


@bp.route('/api/patients/<homer_id>/group', methods=['POST'])
def api_assign_group(homer_id):
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403

    data   = request.get_json() or {}
    group  = (data.get('group') or '').strip().lower()
    a0_date = (data.get('a0CompletionDate') or '').strip()
    if group not in ('experimental', 'control'):
        return jsonify({'error': 'group must be "experimental" or "control"'}), 400
    if not a0_date:
        return jsonify({'error': 'a0CompletionDate is required'}), 400
    try:
        from datetime import datetime as dt
        if dt.strptime(a0_date, '%Y-%m-%dT%H:%M') > dt.now():
            return jsonify({'error': 'a0CompletionDate cannot be in the future'}), 400
    except ValueError:
        return jsonify({'error': 'a0CompletionDate format must be YYYY-MM-DDTHH:MM'}), 400

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    if patient.get('group'):
        return jsonify({'error': 'Patient is already assigned to a group'}), 409

    patient['group']            = group
    patient['a0CompletionDate'] = a0_date
    write_patient_meta(folder, homer_id, patient)
    create_patient_folders(folder, homer_id, group)

    try:
        create_protocol_events(folder, homer_id, group, a0_date)
    except Exception as e:
        print(f'Warning: could not create protocol_events.json: {e}')

    try:
        write_patient_log(
            folder, homer_id,
            flask_session.get('loginid', 'unknown'),
            flask_session.get('session_id', 0),
            f'Assigned group: {group}'
        )
    except Exception as e:
        print(f'Warning: could not write patient log: {e}')

    return jsonify({'status': 'success', 'homerID': homer_id, 'group': group})


def _close_patient_device_assignments(hospital_folder, homer_id, now_hhmm):
    """Close all open device assignments for a patient and clear has_issue flags."""
    for dtype in ('pluto', 'mars', 'agwatch', 'modems', 'laptops'):
        assignments = read_device_assignments(hospital_folder, dtype)
        patient_device_ids = set()
        changed_asgn = False
        for a in assignments:
            if a.get('homer_id') == homer_id and a.get('returned_date') is None:
                a['returned_date'] = now_hhmm
                patient_device_ids.add(a['device_id'])
                changed_asgn = True
        if not changed_asgn:
            continue
        write_device_assignments(hospital_folder, dtype, assignments)
        inv = read_device_inventory(hospital_folder, dtype)
        changed_inv = False
        for d in inv:
            if d['id'] in patient_device_ids:
                if d.get('has_issue'):
                    d['has_issue'] = False
                    changed_inv = True
                if dtype == 'modems' and d.get('sim_id'):
                    d['sim_id'] = None
                    changed_inv = True
        if changed_inv:
            write_device_inventory(hospital_folder, dtype, {'devices': inv})


@bp.route('/api/patients/<homer_id>/create-discontinuation-stub', methods=['POST'])
def api_create_discontinuation_stub(homer_id):
    """Create a discontinuation stub in incomplete — first step of the two-step discontinuation flow."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    if patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is already discontinued'}), 409

    status = derive_status(patient)
    if status == 'broken_protocol':
        return jsonify({'error': 'Broken-protocol patients use the discontinuation_reminder event'}), 400
    if status in ('discontinued', 'pre_discontinued', 'all_completed'):
        return jsonify({'error': 'Cannot create discontinuation stub in current status'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found'}), 404

    existing = next(
        (e for e in events_data.get('incomplete', [])
         if e.get('protocol_event_id') == 'discontinuation'),
        None
    )
    if existing:
        return jsonify({'error': 'Discontinuation stub already exists'}), 409

    now      = datetime.now().strftime('%Y-%m-%dT%H:%M')
    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    stub = {
        'id':                str(uuid.uuid4()),
        'protocol_event_id': 'discontinuation',
        'scheduled_date':    [now, now],
        'filed_at':          filed_at,
        'filed_by':   _filer(),
    }
    events_data.setdefault('incomplete', []).append(stub)
    write_protocol_events(folder, homer_id, events_data)

    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/discontinue', methods=['POST'])
def api_discontinue_patient(homer_id):
    """Complete the discontinuation modal — step 2 of the two-step flow."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    if patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is already discontinued'}), 409

    data            = request.get_json() or {}
    completion_date = (data.get('completion_date') or '').strip()
    reason          = (data.get('reason') or '').strip()
    notes           = (data.get('notes') or '').strip() or None
    stub_id         = data.get('event_id')

    if not completion_date:
        return jsonify({'error': 'Discontinuation date is required.'}), 400
    if r := _bad_date(patient, completion_date): return r
    try:
        disc_dt = datetime.strptime(completion_date, '%Y-%m-%dT%H:%M')
        if disc_dt > datetime.now():
            return jsonify({'error': 'Discontinuation date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400
    if not reason:
        return jsonify({'error': 'A reason is required.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm   = datetime.now().strftime('%Y-%m-%dT%H:%M')
    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    # Remove stub from incomplete (stub_id present for real stub path; absent for broken_protocol path)
    if stub_id:
        events_data['incomplete'] = [
            e for e in events_data.get('incomplete', [])
            if e.get('id') != stub_id
        ]
    else:
        events_data['incomplete'] = [
            e for e in events_data.get('incomplete', [])
            if e.get('protocol_event_id') != 'discontinuation'
        ]

    # Cancel training-ended stubs
    _cancel_training_ended_stubs(events_data, ['watch_record', 'resolve_robot_issue_visit'], filed_at)

    # Set discontinuationDate
    patient['discontinuationDate'] = completion_date
    write_patient_meta(folder, homer_id, patient)

    # Append completed entry to free.discontinuation
    record_id = str(uuid.uuid4())
    record = {
        'id':              record_id,
        'completion_date': completion_date,
        'filed_at':        filed_at,
        'filed_by':   _filer(),
        'reason':          reason,
        'notes':           notes,
    }
    events_data.setdefault('free', {})['discontinuation'] = record
    write_protocol_events(folder, homer_id, events_data)

    try:
        write_patient_log(folder, homer_id, loginid, session_id, 'Patient discontinued.')
    except Exception as e:
        print(f'Warning: could not write patient log: {e}')

    return jsonify({'ok': True, 'event_id': record_id})


@bp.route('/api/patients/<homer_id>/current-devices', methods=['GET'])
def api_current_devices(homer_id):
    """Return open device assignments for the overview panel (all authenticated roles)."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    devices = []
    agwatch_asgns = read_device_assignments(folder, 'agwatch')
    agwatch_inv   = {d['id']: d for d in read_device_inventory(folder, 'agwatch')}
    for a in agwatch_asgns:
        if a.get('homer_id') == homer_id and a.get('returned_date') is None:
            inv = agwatch_inv.get(a['device_id'], {})
            devices.append({
                'type':      'agwatch',
                'device_id': a['device_id'],
                'limb':      a.get('limb', ''),
                'has_issue': bool(inv.get('has_issue')),
                'lost':      bool(inv.get('lost_date')),
            })

    if patient.get('group') == 'experimental':
        all_sims = {s['id']: s for s in read_sims(folder)}
        for dtype in ('pluto', 'mars', 'modems', 'laptops'):
            inv_map = {d['id']: d for d in read_device_inventory(folder, dtype)}
            for a in read_device_assignments(folder, dtype):
                if a.get('homer_id') == homer_id and a.get('returned_date') is None:
                    inv = inv_map.get(a['device_id'], {})
                    entry = {
                        'type':      dtype,
                        'device_id': a['device_id'],
                        'has_issue': bool(inv.get('has_issue')),
                    }
                    if dtype == 'modems' and inv.get('sim_id'):
                        sim_rec = all_sims.get(inv['sim_id'], {})
                        entry['sim'] = sim_rec.get('phoneNumber', inv['sim_id'])
                    devices.append(entry)

    return jsonify({'devices': devices})


@bp.route('/api/patients/<homer_id>/device-return-devices', methods=['GET'])
def api_device_return_devices(homer_id):
    """Return currently open-assigned devices for the device return modal."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    devices = []
    # AGWatch — both groups
    agwatch_asgns = read_device_assignments(folder, 'agwatch')
    agwatch_inv   = {d['id']: d for d in read_device_inventory(folder, 'agwatch')}
    for a in agwatch_asgns:
        if a.get('homer_id') == homer_id and a.get('returned_date') is None:
            devices.append({
                'type':      'agwatch',
                'device_id': a['device_id'],
                'limb':      a.get('limb', ''),
                'info':      agwatch_inv.get(a['device_id'], {}),
            })

    # Pluto, Mars, Modem, Laptop — experimental only
    if patient.get('group') == 'experimental':
        for dtype in ('pluto', 'mars', 'modems', 'laptops'):
            inv   = {d['id']: d for d in read_device_inventory(folder, dtype)}
            asgns = read_device_assignments(folder, dtype)
            for a in asgns:
                if a.get('homer_id') == homer_id and a.get('returned_date') is None:
                    entry = {
                        'type':      dtype,
                        'device_id': a['device_id'],
                        'info':      inv.get(a['device_id'], {}),
                    }
                    devices.append(entry)
                    # If modem has an associated SIM, add it
                    if dtype == 'modems':
                        sim_id = inv.get(a['device_id'], {}).get('sim_id')
                        if sim_id:
                            all_sims = read_sims(folder)
                            sim_rec = next((s for s in all_sims if s['id'] == sim_id), None)
                            if sim_rec:
                                phone = sim_rec.get('phoneNumber', sim_id)
                                devices.append({
                                    'type':      'sims',
                                    'device_id': phone,
                                    'sim_id':    sim_id,
                                    'info':      sim_rec,
                                })

    return jsonify({'devices': devices})


@bp.route('/api/patients/<homer_id>/complete-event/device-return', methods=['POST'])
def api_complete_device_return(homer_id):
    """Complete the device return modal — closes all device assignments and logs device condition."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    data            = request.get_json() or {}
    event_id        = data.get('event_id')
    completion_date = (data.get('completion_date') or '').strip()
    notes           = (data.get('notes') or '').strip() or None
    device_entries  = data.get('devices') or []

    if not completion_date:
        return jsonify({'error': 'Event date is required.'}), 400
    if r := _bad_date(patient, completion_date): return r
    try:
        comp_dt = datetime.strptime(completion_date, '%Y-%m-%dT%H:%M')
        if comp_dt > datetime.now():
            return jsonify({'error': 'Event date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400

    if events_data.get('free', {}).get('device_return'):
        return jsonify({'error': 'Device return already completed.'}), 409

    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm   = datetime.now().strftime('%Y-%m-%dT%H:%M')
    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    # Close all open device assignments and process per-device outcomes
    for dtype in ('pluto', 'mars', 'agwatch', 'modems', 'laptops'):
        assignments = read_device_assignments(folder, dtype)
        inv_list    = read_device_inventory(folder, dtype)
        inv_map     = {d['id']: d for d in inv_list}
        changed_asgn = False
        changed_inv  = False
        for a in assignments:
            if a.get('homer_id') != homer_id or a.get('returned_date') is not None:
                continue
            dev_id  = a['device_id']
            # Find matching device entry from submitted form data
            if dtype == 'agwatch':
                d_entry = next((e for e in device_entries
                                if e.get('type') == 'agwatch' and e.get('device_id') == dev_id), None)
            else:
                d_entry = next((e for e in device_entries
                                if e.get('type') == dtype and e.get('device_id') == dev_id), None)
            if d_entry:
                status     = d_entry.get('status', 'working')
                issue_date = d_entry.get('issue_date', '') or completion_date[:10]
                dev_notes  = d_entry.get('notes') or ''
                if status in ('lost', 'low_battery'):
                    if dev_id in inv_map:
                        inv_map[dev_id]['lost_date'] = issue_date
                        changed_inv = True
                    a['lost'] = True
                    label = 'Low battery' if status == 'low_battery' else 'Lost'
                    append_device_event(folder, dtype, dev_id, 'lost', loginid,
                                        homer_id=homer_id,
                                        notes=f'{label} at device return ({issue_date}){(": " + dev_notes) if dev_notes else ""}')
                elif status == 'faulty':
                    if dev_id in inv_map:
                        inv_map[dev_id]['has_issue'] = True
                        changed_inv = True
                    append_device_event(folder, dtype, dev_id, 'faulty', loginid,
                                        homer_id=homer_id,
                                        notes=f'Faulty at device return{(": " + dev_notes) if dev_notes else ""}')
                else:
                    if dev_id in inv_map:
                        inv_map[dev_id].pop('has_issue', None)
                # Clear SIM from modem when closing modem assignment
                if dtype == 'modems' and dev_id in inv_map:
                    inv_map[dev_id]['sim_id'] = None
                    changed_inv = True
            a['returned_date'] = now_hhmm
            changed_asgn = True
        if changed_asgn:
            write_device_assignments(folder, dtype, assignments)
        if changed_inv:
            write_device_inventory(folder, dtype, {'devices': inv_list})

    # Handle SIM status
    sim_entry = next((e for e in device_entries if e.get('type') == 'sims'), None)
    if sim_entry:
        sim_id     = sim_entry.get('sim_id')
        sim_status = sim_entry.get('status', 'working')
        issue_date = sim_entry.get('issue_date', completion_date[:10])
        if sim_id and sim_status in ('lost', 'faulty'):
            all_sims = read_sims(folder)
            for s in all_sims:
                if s['id'] == sim_id:
                    if sim_status == 'lost':
                        s['lost_date'] = issue_date
                    else:
                        s['has_issue'] = True
                    break
            write_sims(folder, all_sims)

    # Remove stub from incomplete
    if event_id:
        events_data['incomplete'] = [
            e for e in events_data.get('incomplete', [])
            if e.get('id') != event_id
        ]
    else:
        events_data['incomplete'] = [
            e for e in events_data.get('incomplete', [])
            if e.get('protocol_event_id') != 'device_return'
        ]

    # Build completed record
    record_id = event_id or str(uuid.uuid4())
    record = {
        'id':              record_id,
        'protocol_event_id': 'device_return',
        'completion_date': completion_date,
        'filed_at':        filed_at,
        'filed_by':   _filer(),
        'notes':           notes,
        'devices':         device_entries,
    }
    events_data.setdefault('free', {})['device_return'] = record
    write_protocol_events(folder, homer_id, events_data)

    try:
        write_patient_log(folder, homer_id, loginid, session_id, 'Device return recorded.')
    except Exception as e:
        print(f'Warning: could not write patient log: {e}')

    return jsonify({'ok': True, 'event_id': record_id})


@bp.route('/api/patients/<homer_id>/activate', methods=['POST'])
def api_activate_patient(homer_id):
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json() or {}
    activation_date = (data.get('activationDate') or '').strip()
    vcg_group       = (data.get('vcgGroup') or '').strip() or None
    notes           = (data.get('notes') or '').strip()
    session_start   = (data.get('sessionStart') or '').strip()
    session_end     = (data.get('sessionEnd') or '').strip()
    triggered_items = data.get('triggered', [])
    no_issue        = bool(data.get('no_issue', False))
    if not isinstance(triggered_items, list):
        triggered_items = []
    if r := _bad_outcome(no_issue, triggered_items): return r
    if not activation_date:
        return jsonify({'error': 'activationDate is required'}), 400
    try:
        if datetime.strptime(activation_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'activationDate cannot be in the future'}), 400
    except ValueError:
        return jsonify({'error': 'activationDate format must be YYYY-MM-DDTHH:MM'}), 400
    if not session_start or not session_end:
        return jsonify({'error': 'Session start and end times are required'}), 400
    try:
        _ss = datetime.strptime(session_start, '%Y-%m-%dT%H:%M')
        _se = datetime.strptime(session_end,   '%Y-%m-%dT%H:%M')
        if _ss.date() != _se.date():
            return jsonify({'error': 'Session start and end must be on the same date'}), 400
        if _ss >= _se:
            return jsonify({'error': 'Session start must be before session end'}), 400
    except ValueError:
        return jsonify({'error': 'Session times must be in YYYY-MM-DDTHH:MM format'}), 400
    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400
    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    if derive_status(patient) != 'inactive':
        return jsonify({'error': 'Patient must be inactive to activate'}), 409
    # Per-event rule needs events_data to dereference event:exp_device_install.
    _ed = read_protocol_events(folder, homer_id)
    if r := _bad_date(patient, activation_date, event_id='activation', events_data=_ed): return r
    if r := _bad_date(patient, session_start,   event_id='activation', events_data=_ed): return r

    # Control patients must have a VCG group selected at activation
    if patient.get('group') == 'control':
        if not vcg_group:
            return jsonify({'error': 'VCG group is required for control patients'}), 400
        if vcg_group not in ('vcg2', 'vcg3', 'vcg4_5'):
            return jsonify({'error': 'vcgGroup must be vcg2, vcg3, or vcg4_5'}), 400

    # Validate triggered items (stubs only — no detail fields required at trigger time)
    is_experimental = patient.get('group') == 'experimental'
    for item in triggered_items:
        t = item.get('type')
        if t == 'adverse_event':
            pass
        elif t == 'robot_issue_call':
            if not is_experimental:
                return jsonify({'error': 'Robot issue call is only valid for experimental patients.'}), 400
        elif t == 'watch_record':
            pass
        elif t == 'other_device_issue_call':
            if not is_experimental:
                return jsonify({'error': 'Other device issue call is only valid for experimental patients.'}), 400
        else:
            return jsonify({'error': f'Unknown triggered type: {t}'}), 400

    # Check depends_on prerequisites for activation
    protocol = load_study_protocol()
    patient_group = patient.get('group', '')
    activation_def = next(
        (e for e in protocol.get(patient_group, []) if e['id'] == 'activation'),
        None
    )
    dep_ids = (activation_def or {}).get('depends_on') or []
    events_data = read_protocol_events(folder, homer_id)
    if dep_ids:
        completed_ids = {e['protocol_event_id'] for e in (events_data or {}).get('complete', [])}
        # Free-event types count as completed once at least one entry is filed
        # (matches the rule used in api_patient_events / dashboard events).
        for ftype, flist in ((events_data or {}).get('free') or {}).items():
            if flist:
                completed_ids.add(ftype)
        known_ids = completed_ids | {e['protocol_event_id'] for e in (events_data or {}).get('incomplete', [])}
        blocking = [d for d in dep_ids if d in known_ids and d not in completed_ids]
        if blocking:
            event_names = {e['id']: e['name'] for section in ('shared', 'experimental', 'control') for e in protocol.get(section, [])}
            names = ', '.join(event_names.get(d, d) for d in blocking)
            return jsonify({'error': f'Cannot activate: complete these first — {names}'}), 409

    # Update patient record
    patient['activationDate'] = activation_date
    if vcg_group:
        patient['vcgGroup'] = vcg_group
    write_patient_meta(folder, homer_id, patient)

    # Move activation event from incomplete to complete
    activation_entry_id = None
    if events_data:
        incomplete = events_data.get('incomplete', [])
        entry = next((e for e in incomplete if e.get('protocol_event_id') == 'activation'), None)
        if entry:
            activation_entry_id = entry['id']
            filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            complete_entry = {**entry, 'completion_date': activation_date, 'filed_at': filed_at, 'filed_by': _filer(),
                              'session_start': session_start, 'session_end': session_end, 'notes': notes,
                              'no_issue': no_issue, 'triggered': []}
            events_data['incomplete'] = [e for e in incomplete if e.get('id') != entry['id']]
            events_data.setdefault('complete', []).append(complete_entry)
            write_protocol_events(folder, homer_id, events_data)

    # Fill activation-reference scheduled dates and seed first watch_record
    try:
        populate_activation_dates(folder, homer_id, activation_date)
    except Exception as e:
        print(f'Warning: could not populate activation dates: {e}')

    # Stamp triggered_by on the seeded watch_record and process additional triggered items
    try:
        ev_data = read_protocol_events(folder, homer_id)
        if ev_data and activation_entry_id:
            filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            triggered_refs = []

            # Always stamp the seeded watch_record with triggered_by = activation
            wr = next(
                (e for e in ev_data.get('incomplete', [])
                 if e.get('protocol_event_id') == 'watch_record'),
                None
            )
            if wr:
                wr['triggered_by'] = {'type': 'activation', 'id': activation_entry_id}

            # Process additional triggered items from the form
            now_hhmm = datetime.now().strftime('%Y-%m-%dT%H:%M')
            for item in triggered_items:
                t = item.get('type')
                if t == 'adverse_event':
                    new_id = str(uuid.uuid4())
                    ev_data.setdefault('incomplete', []).append({
                        'id':               new_id,
                        'protocol_event_id': 'adverse_event',
                        'triggered_by':     {'type': 'activation', 'id': activation_entry_id},
                        'scheduled_date':   [now_hhmm, now_hhmm],
                        'filed_at':         filed_at,
                        'filed_by':   _filer(),
                    })
                    triggered_refs.append({'type': 'adverse_event', 'id': new_id})
                elif t == 'robot_issue_call':
                    new_id = str(uuid.uuid4())
                    ev_data.setdefault('incomplete', []).append({
                        'id':               new_id,
                        'protocol_event_id': 'robot_issue_call',
                        'triggered_by':     {'type': 'activation', 'id': activation_entry_id},
                        'scheduled_date':   [now_hhmm, now_hhmm],
                        'filed_at':         filed_at,
                        'filed_by':   _filer(),
                    })
                    triggered_refs.append({'type': 'robot_issue_call', 'id': new_id})
                elif t == 'other_device_issue_call':
                    new_id = str(uuid.uuid4())
                    ev_data.setdefault('incomplete', []).append({
                        'id':               new_id,
                        'protocol_event_id': 'other_device_issue_call',
                        'triggered_by':     {'type': 'activation', 'id': activation_entry_id},
                        'scheduled_date':   [now_hhmm, now_hhmm],
                        'filed_at':         filed_at,
                        'filed_by':   _filer(),
                    })
                    triggered_refs.append({'type': 'other_device_issue_call', 'id': new_id})
                elif t == 'watch_record':
                    # Stamp triggered_by and scheduled_date onto the existing open chain entry
                    if wr:
                        wr['triggered_by']   = {'type': 'activation', 'id': activation_entry_id}
                        wr['scheduled_date'] = [now_hhmm, now_hhmm]
                        triggered_refs.append({'type': 'watch_record', 'id': wr['id']})

            # Update triggered refs on the activation complete entry
            if triggered_refs:
                act_entry = next(
                    (e for e in ev_data.get('complete', [])
                     if e.get('id') == activation_entry_id),
                    None
                )
                if act_entry:
                    act_entry['triggered'] = triggered_refs

            write_protocol_events(folder, homer_id, ev_data)
    except Exception as e:
        print(f'Warning: could not stamp watch_record triggered_by: {e}')

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    try:
        write_patient_log(folder, homer_id, loginid, session_id, 'Patient activated')
    except Exception as e:
        print(f'Warning: could not write patient log: {e}')
    return jsonify({'status': 'success', 'homerID': homer_id})


@bp.route('/api/patients/<homer_id>/log-activation-attempt', methods=['POST'])
def api_log_activation_attempt(homer_id):
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    data            = request.get_json() or {}
    visit_date      = (data.get('visitDate') or '').strip()
    notes           = (data.get('notes') or '').strip()
    primary_reason  = (data.get('primaryReason') or '').strip()
    triggered_items = data.get('triggered', [])
    if not isinstance(triggered_items, list):
        triggered_items = []

    _VALID_REASONS = {'adverse_event', 'robot_issue_call', 'other_device_issue_call', 'other'}
    if primary_reason not in _VALID_REASONS:
        return jsonify({'error': 'Primary reason is required'}), 400
    if not visit_date:
        return jsonify({'error': 'Visit date is required'}), 400
    try:
        if datetime.strptime(visit_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'Visit date cannot be in the future'}), 400
    except ValueError:
        return jsonify({'error': 'Visit date format must be YYYY-MM-DDTHH:MM'}), 400
    if primary_reason == 'other' and not notes:
        return jsonify({'error': 'Notes are required when reason is "Other"'}), 400

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    if derive_status(patient) != 'inactive':
        return jsonify({'error': 'Patient must be inactive to log an activation attempt'}), 409
    # The attempt is part of activation — bounded by the same per-event rule
    # (within 5 days of enrollment, after device setup for experimental).
    _ed_attempt = read_protocol_events(folder, homer_id)
    if r := _bad_date(patient, visit_date, event_id='activation', events_data=_ed_attempt): return r

    is_experimental = patient.get('group') == 'experimental'
    if primary_reason in ('robot_issue_call', 'other_device_issue_call') and not is_experimental:
        return jsonify({'error': f'{primary_reason} is only valid for experimental patients'}), 400
    for item in triggered_items:
        t = item.get('type')
        if t == 'adverse_event':
            pass
        elif t in ('robot_issue_call', 'other_device_issue_call'):
            if not is_experimental:
                return jsonify({'error': f'{t} is only valid for experimental patients'}), 400
        else:
            return jsonify({'error': f'Unknown triggered type: {t}'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found'}), 404

    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm   = datetime.now().strftime('%Y-%m-%dT%H:%M')
    attempt_id = str(uuid.uuid4())

    triggered_refs = []
    # All triggered items (primary reason non-"other" is already in the list from the client)
    for item in triggered_items:
        t              = item.get('type')
        training_stopped = item.get('training_stopped', False)
        new_id         = str(uuid.uuid4())
        stub = {
            'id':                new_id,
            'protocol_event_id': t,
            'triggered_by':      {'type': 'activation_attempt', 'id': attempt_id},
            'scheduled_date':    [now_hhmm, now_hhmm],
            'filed_at':          filed_at,
            'filed_by':   _filer(),
        }
        if training_stopped:
            stub['training_stopped'] = True
        events_data.setdefault('incomplete', []).append(stub)
        triggered_refs.append({'type': t, 'id': new_id})

    act_entry = next((e for e in events_data.get('incomplete', [])
                      if e.get('protocol_event_id') == 'activation'), None)
    attempt_entry = {
        'id':                attempt_id,
        'protocol_event_id': 'activation_attempt',
        'completion_date':   visit_date,
        'visit_date':        visit_date,
        'scheduled_date':    act_entry.get('scheduled_date') if act_entry else None,
        'primary_reason':    primary_reason,
        'notes':             notes,
        'filed_at':          filed_at,
        'filed_by':   _filer(),
        'triggered':         triggered_refs,
        'triggered_by':      None,
    }
    events_data.setdefault('free', {}).setdefault('activation_attempt', []).append(attempt_entry)
    write_protocol_events(folder, homer_id, events_data)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)
    write_patient_log(folder, homer_id, loginid, session_id,
                      'Activation attempt recorded — training not completed')
    return jsonify({'status': 'success'})


_PRINTOUT_PDF_FILES = {
    'prescription_printout_d01': 'attachments/prescription_d01.pdf',
    'prescription_printout_d15': 'attachments/prescription_d15.pdf',
}


def _generate_placeholder_pdf(homer_id: str, title: str) -> bytes:
    """Generate a minimal placeholder PDF using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont('Helvetica-Bold', 16)
    c.drawString(72, 750, title)
    c.setFont('Helvetica', 12)
    c.drawString(72, 720, f'Patient: {homer_id}')
    c.drawString(72, 700, 'TODO: prescription content to be generated here.')
    c.save()
    return buf.getvalue()


@bp.route('/api/patients/<homer_id>/complete-event/prescription-printout', methods=['POST'])
def api_complete_prescription_printout(homer_id):
    """Mark prescription printout event complete. PDF attachment is uploaded separately."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    data              = request.get_json() or {}
    event_id          = data.get('event_id')
    protocol_event_id = data.get('protocol_event_id', '')
    language          = data.get('language', 'english')  # For logging purposes

    if protocol_event_id not in _PRINTOUT_PDF_FILES:
        return jsonify({'error': 'Invalid protocol event ID.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == protocol_event_id
         and (event_id is None or e.get('id') == event_id)),
        None
    )
    if not entry:
        return jsonify({'error': 'Event not found in incomplete list.'}), 404

    # Mark event complete (attachment will be added separately via upload-attachment endpoint)
    # Generate and save the PDF
    rel_path = _PRINTOUT_PDF_FILES[protocol_event_id]
    title = ('Revised Therapy Prescription Printout'
             if protocol_event_id == 'prescription_printout_d15'
             else 'Therapy Prescription Printout')
    pdf_bytes = _generate_placeholder_pdf(homer_id, title)
    if Config.USE_S3:
        from utils.s3_store import s3_upload_bytes
        s3_upload_bytes(f"{folder}/patients/{homer_id}/{rel_path}", pdf_bytes, content_type='application/pdf')
    else:
        pdf_path = get_patients_path(folder) / homer_id / rel_path
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)

    now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    complete_entry = {
        **entry,
        'completion_date': now,
        'filed_at':        now,
        'filed_by':   _filer(),
    }

    events_data['incomplete'] = [e for e in incomplete if e.get('id') != entry['id']]
    events_data.setdefault('complete', []).append(complete_entry)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)
    log_msg = ('Revised prescription printout completed' if protocol_event_id == 'prescription_printout_d15'
               else 'Prescription printout completed')
    write_patient_log(folder, homer_id, loginid, session_id, log_msg)

    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/generate-prescription-pdf', methods=['POST'])
def api_generate_prescription_pdf(homer_id):
    """Generate prescription pamphlet PDF server-side using Puppeteer."""
    import subprocess
    import tempfile
    import platform

    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    data = request.get_json() or {}
    event_id = data.get('event_id')
    protocol_event_id = data.get('protocol_event_id', '')
    language = data.get('language', 'english')
    html_content = data.get('html_content', '')
    caption = data.get('caption', '')

    if not html_content:
        return jsonify({'error': 'No HTML content provided'}), 400
    if protocol_event_id not in _PRINTOUT_PDF_FILES:
        return jsonify({'error': 'Invalid protocol event ID'}), 400
    if not caption:
        return jsonify({'error': 'Caption is required'}), 400

    try:
        # Create temporary files for HTML input and PDF output
        with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as html_file:
            html_file.write(html_content)
            html_input_path = html_file.name

        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as pdf_file:
            pdf_output_path = pdf_file.name

        try:
            # Get the path to the render_pdf.js script
            script_path = Path(__file__).parent.parent / 'scripts' / 'render_pdf.js'

            # Determine Node command based on OS
            node_cmd = 'node.exe' if platform.system() == 'Windows' else 'node'

            # Call Puppeteer script to render HTML to PDF
            result = subprocess.run(
                [node_cmd, str(script_path), html_input_path, pdf_output_path],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return jsonify({
                    'error': f'PDF rendering failed: {result.stderr}'
                }), 500

            # Read the generated PDF
            with open(pdf_output_path, 'rb') as f:
                pdf_bytes = f.read()

            # Save PDF to patient folder (same location as upload-attachment)
            pdf_rel_path = _PRINTOUT_PDF_FILES.get(protocol_event_id, 'prescription_attachment.pdf')

            if Config.USE_S3:
                from utils.s3_store import s3_upload_bytes
                s3_upload_bytes(
                    f"{folder}/patients/{homer_id}/{pdf_rel_path}",
                    pdf_bytes,
                    content_type='application/pdf'
                )
            else:
                pdf_full_path = get_patients_path(folder) / homer_id / pdf_rel_path
                pdf_full_path.parent.mkdir(parents=True, exist_ok=True)
                pdf_full_path.write_bytes(pdf_bytes)

            # Mark event complete
            events_data = read_protocol_events(folder, homer_id)
            if not events_data:
                return jsonify({'error': 'Protocol events not found'}), 404

            incomplete = events_data.get('incomplete', [])
            entry = next(
                (e for e in incomplete
                 if e.get('protocol_event_id') == protocol_event_id
                 and (event_id is None or e.get('id') == event_id)),
                None
            )
            if not entry:
                return jsonify({'error': 'Event not found in incomplete list'}), 404

            now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            complete_entry = {
                **entry,
                'completion_date': now,
                'filed_at': now,
                'filed_by':   _filer(),
                'attachment': pdf_rel_path,
                'attachment_caption': caption,
            }

            events_data['incomplete'] = [e for e in incomplete if e.get('id') != entry['id']]
            events_data.setdefault('complete', []).append(complete_entry)

            write_protocol_events(folder, homer_id, events_data)

            # Log the event
            loginid = flask_session.get('loginid', 'unknown')
            session_id = flask_session.get('session_id', -1)
            log_msg = (f'Prescription printout ({language}) generated and saved as PDF')
            write_patient_log(folder, homer_id, loginid, session_id, log_msg)

            return jsonify({'ok': True})

        finally:
            # Clean up temporary files
            try:
                os.unlink(html_input_path)
            except:
                pass
            try:
                os.unlink(pdf_output_path)
            except:
                pass

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'PDF rendering timed out'}), 500
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@bp.route('/api/patients/<homer_id>/attachment/<path:rel_path>', methods=['GET'])
def api_get_attachment(homer_id, rel_path):
    """Serve a file from the patient's attachments folder."""
    from flask import send_file
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404
    if Config.USE_S3:
        from utils.s3_store import s3_get_bytes
        import io, posixpath
        key = f"{folder}/patients/{homer_id}/{rel_path}"
        data = s3_get_bytes(key)
        if data is None:
            return jsonify({'error': 'File not found'}), 404
        filename = posixpath.basename(rel_path)
        return send_file(io.BytesIO(data), as_attachment=True, download_name=filename)
    file_path = get_patients_path(folder) / homer_id / rel_path
    if not file_path.exists() or not file_path.is_file():
        return jsonify({'error': 'File not found'}), 404
    return send_file(file_path, as_attachment=True, download_name=file_path.name)


_SIMPLE_EVENT_IDS = {
    'home_visit_d02',
    'home_visit_d03',
    'home_visit_d15',
}

_HOME_VISIT_IDS        = {'home_visit_d02', 'home_visit_d03', 'home_visit_d15'}
_HV_ACTIVATION_OFFSETS = {'home_visit_d02': 1, 'home_visit_d03': 2}

_SIMPLE_EVENT_LOG_MESSAGES = {
    'home_visit_d02': 'Home visit recorded — Day 02',
    'home_visit_d03': 'Home visit recorded — Day 03',
    'home_visit_d15': 'Home visit recorded — Day 15',
}

_FOLLOWUP_CALL_IDS = {
    'followup_call_d07': 'attachments/followup_call_d07.pdf',
    'followup_call_d21': 'attachments/followup_call_d21.pdf',
}


@bp.route('/api/patients/<homer_id>/complete-event/simple', methods=['POST'])
def api_complete_simple_event(homer_id):
    """Complete a simple protocol event that only requires a date and optional notes."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    data              = request.get_json() or {}
    event_id          = data.get('event_id')
    protocol_event_id = (data.get('protocol_event_id') or '').strip()
    completion_date   = (data.get('completion_date') or '').strip()
    notes             = (data.get('notes') or '').strip()
    session_start     = (data.get('session_start') or '').strip()
    session_end       = (data.get('session_end') or '').strip()

    if protocol_event_id not in _SIMPLE_EVENT_IDS:
        return jsonify({'error': 'Invalid protocol event ID.'}), 400
    if r := _bad_date(patient, completion_date): return r
    if r := _bad_date(patient, session_start):   return r
    if protocol_event_id in _HOME_VISIT_IDS:
        if not session_start or not session_end:
            return jsonify({'error': 'Session start and end are required.'}), 400
        try:
            _ss = datetime.strptime(session_start, '%Y-%m-%dT%H:%M')
            _se = datetime.strptime(session_end,   '%Y-%m-%dT%H:%M')
            if _ss.date() != _se.date():
                return jsonify({'error': 'Session start and end must be on the same date.'}), 400
            if _ss >= _se:
                return jsonify({'error': 'Session start must be before session end.'}), 400
            if _ss > datetime.now():
                return jsonify({'error': 'Session start cannot be in the future.'}), 400
        except ValueError:
            return jsonify({'error': 'Session times must be in YYYY-MM-DDTHH:MM format.'}), 400
        completion_date = session_start
    else:
        if not completion_date:
            return jsonify({'error': 'Event date is required.'}), 400
        try:
            if datetime.strptime(completion_date, '%Y-%m-%dT%H:%M') > datetime.now():
                return jsonify({'error': 'Event date cannot be in the future.'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid date format.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == protocol_event_id
         and (event_id is None or e.get('id') == event_id)),
        None
    )
    if not entry:
        return jsonify({'error': 'Event not found in incomplete list.'}), 404

    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    complete_entry = {
        **entry,
        'completion_date': completion_date,
        'filed_at':        filed_at,
        'filed_by':   _filer(),
        'notes':           notes,
    }
    if protocol_event_id in _HOME_VISIT_IDS:
        complete_entry['session_start'] = session_start
        complete_entry['session_end']   = session_end

    events_data['incomplete'] = [e for e in incomplete if e.get('id') != entry['id']]
    events_data.setdefault('complete', []).append(complete_entry)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    write_patient_log(folder, homer_id, loginid, session_id,
                      _SIMPLE_EVENT_LOG_MESSAGES[protocol_event_id])

    return jsonify({'ok': True})


_AUDIO_CONTENT_TYPES = {'mp3': 'audio/mpeg', 'm4a': 'audio/mp4', 'wav': 'audio/wav'}


@bp.route('/api/patients/<homer_id>/complete-event/training-completion', methods=['POST'])
def api_complete_training_completion(homer_id):
    """Complete training_completion_d29 with feedback form, qualitative analysis uploads."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    event_id          = (request.form.get('event_id') or '').strip()
    completion_date   = (request.form.get('completion_date') or '').strip()
    notes             = (request.form.get('notes') or '').strip()
    a1_appointment    = (request.form.get('a1_appointment_date') or '').strip()
    feedback_notes    = (request.form.get('feedback_form_notes') or '').strip()
    qual_str          = (request.form.get('qualitative_recruited') or 'false').strip().lower()
    qualitative_recruited = qual_str in ('true', '1', 'yes')
    attachment_caption = (request.form.get('attachment_caption') or '').strip()

    if not completion_date:
        return jsonify({'error': 'Event date is required.'}), 400
    if r := _bad_date(patient, completion_date, event_id='training_completion_d29'): return r
    try:
        if datetime.strptime(completion_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'Event date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400

    feedback_file    = request.files.get('feedback_form_file')
    audio_file       = request.files.get('qualitative_audio_file')
    scan_file        = request.files.get('qualitative_scan_file')
    attachment_file  = request.files.get('attachment_file')

    has_feedback_file  = bool(feedback_file and feedback_file.filename)
    has_audio_file     = bool(audio_file and audio_file.filename)
    has_scan_file      = bool(scan_file and scan_file.filename)
    has_generic_file   = bool(attachment_file and attachment_file.filename)

    if not has_feedback_file and not feedback_notes:
        return jsonify({'error': 'Feedback form: upload the PDF or provide notes.'}), 400
    if has_feedback_file and not feedback_file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Feedback form must be a PDF file.'}), 400

    if qualitative_recruited:
        if not has_audio_file:
            return jsonify({'error': 'Audio recording is required for qualitative analysis.'}), 400
        audio_ext = audio_file.filename.rsplit('.', 1)[-1].lower() if '.' in audio_file.filename else ''
        if audio_ext not in _AUDIO_CONTENT_TYPES:
            return jsonify({'error': 'Audio must be MP3, M4A, or WAV.'}), 400
        if has_scan_file and not scan_file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Qualitative scan must be a PDF file.'}), 400

    if has_generic_file:
        if not attachment_file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'Attachment must be a PDF file.'}), 400
        if not attachment_caption:
            return jsonify({'error': 'Attachment description is required when a file is selected.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == 'training_completion_d29'
         and (not event_id or e.get('id') == event_id)),
        None
    )
    if not entry:
        return jsonify({'error': 'Event not found in incomplete list.'}), 404

    eid = entry['id']

    def _save_file(file_obj, rel_path, content_type):
        if Config.USE_S3:
            from utils.s3_store import s3_upload_file
            import tempfile, os as _os
            suffix = '.' + rel_path.rsplit('.', 1)[-1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                file_obj.save(tmp.name)
                tmp_path = tmp.name
            try:
                s3_upload_file(tmp_path, f"{folder}/patients/{homer_id}/{rel_path}",
                               content_type=content_type)
            finally:
                _os.unlink(tmp_path)
        else:
            dest = get_patients_path(folder) / homer_id / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            file_obj.save(str(dest))

    feedback_rel = None
    if has_feedback_file:
        feedback_rel = f'attachments/{eid}_feedback.pdf'
        _save_file(feedback_file, feedback_rel, 'application/pdf')

    audio_rel = None
    scan_rel  = None
    if qualitative_recruited:
        audio_ext = audio_file.filename.rsplit('.', 1)[-1].lower()
        audio_rel = f'attachments/{eid}_audio.{audio_ext}'
        _save_file(audio_file, audio_rel, _AUDIO_CONTENT_TYPES[audio_ext])
        if has_scan_file:
            scan_rel = f'attachments/{eid}_scan.pdf'
            _save_file(scan_file, scan_rel, 'application/pdf')

    generic_rel = None
    if has_generic_file:
        generic_rel = f'attachments/{eid}.pdf'
        _save_file(attachment_file, generic_rel, 'application/pdf')

    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    complete_entry = {
        **entry,
        'completion_date':          completion_date,
        'filed_at':                 filed_at,
        'filed_by':   _filer(),
        'notes':                    notes,
        'feedback_form_attachment': feedback_rel,
        'feedback_form_notes':      feedback_notes,
        'qualitative_recruited':    qualitative_recruited,
    }
    if qualitative_recruited:
        complete_entry['qualitative_audio_attachment'] = audio_rel
        complete_entry['qualitative_scan_attachment']  = scan_rel
    if generic_rel:
        complete_entry['attachment']         = generic_rel
        complete_entry['attachment_caption'] = attachment_caption

    # Remove the D29 entry itself then cancel all training-ended stubs
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != eid]
    _cancel_training_ended_stubs(events_data, ['watch_record', 'resolve_robot_issue_visit'], filed_at)
    events_data.setdefault('complete', []).append(complete_entry)

    # If therapist set an A1 appointment date, update the a1_assessment stub's appointment_date.
    if a1_appointment:
        try:
            _appt_str = datetime.strptime(a1_appointment, '%Y-%m-%d').strftime('%Y-%m-%dT09:00')
            for _e in events_data.get('incomplete', []):
                if _e.get('protocol_event_id') == 'a1_assessment':
                    _e['appointment_date'] = _appt_str
                    break
        except ValueError:
            pass  # ignore malformed date; assessment stub keeps original window

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    patient = read_patient_meta(folder, homer_id)
    if patient:
        patient['trainingCompletionDate'] = completion_date
        if patient.get('trainingPausedDate'):
            patient['trainingPausedDate'] = None
            write_patient_log(folder, homer_id, loginid, session_id,
                              'Training pause cleared — training completed')
        write_patient_meta(folder, homer_id, patient)

    write_patient_log(folder, homer_id, loginid, session_id,
                      'Training completion visit recorded')
    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/complete-event/home-visit', methods=['POST'])
def api_complete_home_visit(homer_id):
    """Complete a home-visit event (YES path) or log a training-not-done attempt (NO path)."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    body              = request.get_json() or {}
    event_id          = body.get('event_id')
    protocol_event_id = (body.get('protocol_event_id') or '').strip()
    training_not_done = bool(body.get('training_not_done'))
    no_issue          = bool(body.get('no_issue', False))

    if protocol_event_id not in _HOME_VISIT_IDS:
        return jsonify({'error': 'Invalid protocol event ID.'}), 400

    is_experimental = patient and patient.get('group') == 'experimental'

    triggered_items = body.get('triggered', [])
    if not isinstance(triggered_items, list):
        triggered_items = []
    for item in triggered_items:
        t = item.get('type')
        if t == 'adverse_event':
            pass
        elif t == 'robot_issue_call':
            if not is_experimental:
                return jsonify({'error': 'Robot issue call is only valid for experimental patients.'}), 400
        elif t == 'watch_record':
            if training_not_done:
                return jsonify({'error': 'Watch record cannot be triggered when training was not done.'}), 400
        elif t == 'other_device_issue_call':
            if not is_experimental:
                return jsonify({'error': 'Other device issue call is only valid for experimental patients.'}), 400
        else:
            return jsonify({'error': f'Unknown triggered type: {t}'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == protocol_event_id
         and (event_id is None or e.get('id') == event_id)),
        None
    )
    if not entry:
        return jsonify({'error': 'Event not found in incomplete list.'}), 404

    entry_id   = entry['id']
    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm   = datetime.now().strftime('%Y-%m-%dT%H:%M')
    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    primary_reason = (body.get('primary_reason') or '').strip() or None

    def _build_triggered_refs(source_protocol_id, source_entry_id):
        refs = []
        for item in triggered_items:
            t = item.get('type')
            if t in ('adverse_event', 'robot_issue_call', 'other_device_issue_call'):
                new_id = str(uuid.uuid4())
                stub = {
                    'id':                new_id,
                    'protocol_event_id': t,
                    'triggered_by':      {'type': source_protocol_id, 'id': source_entry_id},
                    'scheduled_date':    [now_hhmm, now_hhmm],
                    'filed_at':          filed_at,
                    'filed_by':   _filer(),
                }
                if item.get('training_stopped'):
                    stub['training_stopped'] = True
                events_data.setdefault('incomplete', []).append(stub)
                refs.append({'type': t, 'id': new_id})
            elif t == 'watch_record':
                wr = next(
                    (e for e in events_data.get('incomplete', [])
                     if e.get('protocol_event_id') == 'watch_record'),
                    None
                )
                if wr:
                    wr['triggered_by']   = {'type': source_protocol_id, 'id': source_entry_id}
                    wr['scheduled_date'] = [now_hhmm, now_hhmm]
                    refs.append({'type': 'watch_record', 'id': wr['id']})
        return refs

    from utils.protocol_events import write_protocol_events

    if training_not_done:
        # ── NO path ─────────────────────────────────────────────────────────
        visit_date = (body.get('visit_date') or '').strip()
        notes      = (body.get('notes') or '').strip()

        if not visit_date:
            return jsonify({'error': 'Visit date is required.'}), 400
        if r := _bad_date(patient, visit_date): return r
        try:
            _vd = datetime.strptime(visit_date, '%Y-%m-%dT%H:%M')
            if _vd > datetime.now():
                return jsonify({'error': 'Visit date cannot be in the future.'}), 400
        except ValueError:
            return jsonify({'error': 'Visit date must be in YYYY-MM-DDTHH:MM format.'}), 400
        if not primary_reason:
            return jsonify({'error': 'A primary reason is required when training was not completed.'}), 400
        if primary_reason == 'other' and not notes:
            return jsonify({'error': 'Notes are required when reason is "Other".'}), 400

        triggered_refs = _build_triggered_refs(protocol_event_id, entry_id)

        if protocol_event_id == 'home_visit_d15':
            # D15 NO: log d15_attempt free event, keep home_visit_d15 incomplete
            attempt_id = str(uuid.uuid4())
            events_data.setdefault('free', {}).setdefault('d15_attempt', []).append({
                'id':                attempt_id,
                'protocol_event_id': 'd15_attempt',
                'scheduled_date':    entry.get('scheduled_date'),
                'visit_date':        visit_date,
                'completion_date':   visit_date,
                'primary_reason':    primary_reason,
                'notes':             notes,
                'filed_at':          filed_at,
                'filed_by':   _filer(),
                'triggered':         triggered_refs,
            })
            write_protocol_events(folder, homer_id, events_data)
            write_patient_log(folder, homer_id, loginid, session_id,
                              'Home visit Day 15 attempt recorded — training not completed')
            return jsonify({'ok': True, 'attempt_id': attempt_id})

        else:
            # D02/D03 NO: broken protocol — require double confirmation
            if not bool(body.get('confirmed_broken_protocol')):
                return jsonify({'error': 'confirmed_broken_protocol is required for D02/D03 training not done.'}), 400

            complete_entry = {
                **entry,
                'completion_date':   visit_date,
                'training_not_done': True,
                'primary_reason':    primary_reason,
                'filed_at':          filed_at,
                'filed_by':   _filer(),
                'notes':             notes,
                'triggered':         triggered_refs,
            }
            events_data['incomplete'] = [e for e in incomplete if e.get('id') != entry['id']]
            events_data.setdefault('complete', []).append(complete_entry)

            if not patient.get('brokenProtocolDate'):
                patient['brokenProtocolDate'] = visit_date[:10]
            _cancel_training_ended_stubs(events_data, ['watch_record'], filed_at)
            write_patient_meta(folder, homer_id, patient)
            write_protocol_events(folder, homer_id, events_data)

            day = '02' if protocol_event_id == 'home_visit_d02' else '03'
            write_patient_log(folder, homer_id, loginid, session_id,
                              f'Home visit Day {day} — training not completed (broken protocol)')
            return jsonify({'ok': True})

    else:
        # ── YES path ─────────────────────────────────────────────────────────
        session_start = (body.get('session_start') or '').strip()
        session_end   = (body.get('session_end') or '').strip()
        notes         = (body.get('notes') or '').strip()

        if r := _bad_outcome(no_issue, triggered_items): return r
        if not session_start or not session_end:
            return jsonify({'error': 'Session start and end are required.'}), 400
        if r := _bad_date(patient, session_start): return r
        try:
            _ss = datetime.strptime(session_start, '%Y-%m-%dT%H:%M')
            _se = datetime.strptime(session_end,   '%Y-%m-%dT%H:%M')
            if _ss.date() != _se.date():
                return jsonify({'error': 'Session start and end must be on the same date.'}), 400
            if _ss >= _se:
                return jsonify({'error': 'Session start must be before session end.'}), 400
            if _ss > datetime.now():
                return jsonify({'error': 'Session start cannot be in the future.'}), 400
        except ValueError:
            return jsonify({'error': 'Session times must be in YYYY-MM-DDTHH:MM format.'}), 400

        # D02/D03: validate session date is locked to activationDate + offset
        if protocol_event_id in _HV_ACTIVATION_OFFSETS:
            act_str = patient.get('activationDate', '') if patient else ''
            if act_str:
                try:
                    act_date = datetime.strptime(act_str, '%Y-%m-%dT%H:%M').date()
                    expected = act_date + timedelta(days=_HV_ACTIVATION_OFFSETS[protocol_event_id])
                    if _ss.date() != expected:
                        day_num = _HV_ACTIVATION_OFFSETS[protocol_event_id] + 1
                        return jsonify({'error': f'Session date must be {expected.isoformat()} (Day {day_num}).'}), 400
                except ValueError:
                    pass

        triggered_refs = _build_triggered_refs(protocol_event_id, entry_id)

        complete_entry = {
            **entry,
            'completion_date': session_start,
            'session_start':   session_start,
            'session_end':     session_end,
            'filed_at':        filed_at,
            'filed_by':   _filer(),
            'notes':           notes,
            'no_issue':        no_issue,
            'triggered':       triggered_refs,
        }
        events_data['incomplete'] = [e for e in incomplete if e.get('id') != entry['id']]
        events_data.setdefault('complete', []).append(complete_entry)

        write_protocol_events(folder, homer_id, events_data)
        write_patient_log(folder, homer_id, loginid, session_id,
                          _SIMPLE_EVENT_LOG_MESSAGES[protocol_event_id])
        return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/complete-event/adverse-event', methods=['POST'])
def api_complete_adverse_event(homer_id):
    """Complete an adverse event stub: moves it from incomplete to free.adverse_event."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    body                      = request.get_json() or {}
    event_id                  = body.get('event_id')
    completion_date           = (body.get('completion_date') or '').strip()
    description               = (body.get('description') or '').strip()
    action_taken              = (body.get('action_taken') or '').strip()
    training_blocked          = bool(body.get('training_blocked', False))
    scheduled_followup_visit  = (body.get('scheduled_followup_visit') or '').strip() or None
    scheduled_clinical_visit  = (body.get('scheduled_clinical_visit') or '').strip() or None

    if not event_id:
        return jsonify({'error': 'event_id is required.'}), 400
    if not completion_date:
        return jsonify({'error': 'Event date is required.'}), 400
    if r := _bad_date(patient, completion_date): return r
    try:
        if datetime.strptime(completion_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'Event date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400
    if not description:
        return jsonify({'error': 'Description is required.'}), 400
    if not action_taken:
        return jsonify({'error': 'Action taken is required.'}), 400
    if scheduled_followup_visit:
        try:
            datetime.strptime(scheduled_followup_visit, '%Y-%m-%dT%H:%M')
        except ValueError:
            return jsonify({'error': 'Invalid follow-up visit date format.'}), 400
    if scheduled_clinical_visit:
        try:
            datetime.strptime(scheduled_clinical_visit, '%Y-%m-%dT%H:%M')
        except ValueError:
            return jsonify({'error': 'Invalid clinical visit date format.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == 'adverse_event' and e.get('id') == event_id),
        None
    )
    if not entry:
        return jsonify({'error': 'Adverse event stub not found.'}), 404

    filed_at  = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    today     = date.today()
    tomorrow  = (today + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    today_str = today.strftime('%Y-%m-%dT%H:%M')

    # Build completed entry
    followup_visit_stub_id  = str(uuid.uuid4()) if scheduled_followup_visit else None
    clinical_visit_stub_id  = str(uuid.uuid4()) if scheduled_clinical_visit else None

    complete_entry = {
        **entry,
        'completion_date':          completion_date,
        'filed_at':                 filed_at,
        'filed_by':   _filer(),
        'description':              description,
        'action_taken':             action_taken,
        'training_blocked':         training_blocked,
        'scheduled_followup_visit': followup_visit_stub_id,
        'scheduled_clinical_visit': clinical_visit_stub_id,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    existing_aes = events_data.setdefault('free', {}).setdefault('adverse_event', [])
    complete_entry['alias'] = f"AE{len(existing_aes) + 1:02d}"
    existing_aes.append(complete_entry)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    if training_blocked:
        patient_meta = read_patient_meta(folder, homer_id)
        if patient_meta:
            pause_history = patient_meta.setdefault('pauseHistory', [])
            new_reason = {'type': 'adverse_event', 'event_id': event_id}
            open_epoch = next((e for e in pause_history if e.get('end') is None), None)
            if not patient_meta.get('trainingPausedDate'):
                patient_meta['trainingPausedDate'] = completion_date
                pause_history.append({'start': completion_date, 'end': None, 'days': None, 'reasons': [new_reason]})
            elif open_epoch:
                open_epoch['reasons'].append(new_reason)
            write_patient_meta(folder, homer_id, patient_meta)
        write_patient_log(folder, homer_id, loginid, session_id, 'Training paused — adverse event')

    # Schedule follow-up visit stub if requested
    if scheduled_followup_visit:
        events_data.setdefault('incomplete', []).append({
            'id':                 followup_visit_stub_id,
            'protocol_event_id':  'adverse_event_followup_visit',
            'adverse_event_ids':  [event_id],
            'scheduled_date':     [scheduled_followup_visit, scheduled_followup_visit],
            'triggered_by':       {'type': 'adverse_event', 'id': event_id},
            'filed_at':           filed_at,
            'filed_by':   _filer(),
            'cancellable':        True,
        })
        write_patient_log(folder, homer_id, loginid, session_id, 'AE follow-up visit scheduled')

    # Schedule clinical visit stub if requested
    if scheduled_clinical_visit:
        events_data.setdefault('incomplete', []).append({
            'id':                 clinical_visit_stub_id,
            'protocol_event_id':  'adverse_event_clinical_visit',
            'adverse_event_ids':  [event_id],
            'scheduled_date':     [scheduled_clinical_visit, scheduled_clinical_visit],
            'triggered_by':       {'type': 'adverse_event', 'id': event_id},
            'filed_at':           filed_at,
            'filed_by':   _filer(),
            'cancellable':        True,
        })
        write_patient_log(folder, homer_id, loginid, session_id, 'AE clinical visit scheduled')

    # Always seed/update the adverse_event_followup stub
    followup_stub = next(
        (e for e in events_data.get('incomplete', [])
         if e.get('protocol_event_id') == 'adverse_event_followup'),
        None
    )
    if followup_stub:
        if event_id not in followup_stub.get('adverse_event_ids', []):
            followup_stub.setdefault('adverse_event_ids', []).append(event_id)
    else:
        events_data.setdefault('incomplete', []).append({
            'id':                  str(uuid.uuid4()),
            'protocol_event_id':   'adverse_event_followup',
            'adverse_event_ids':   [event_id],
            'scheduled_date':      [today_str, tomorrow],
            'filed_at':            filed_at,
            'filed_by':   _filer(),
        })

    # Also update any existing follow-up visit / clinical visit stubs so they
    # reflect all ongoing AEs (not just the ones known when the stub was created).
    for stub in events_data.get('incomplete', []):
        if stub.get('protocol_event_id') in (
            'adverse_event_followup_visit', 'adverse_event_clinical_visit'
        ):
            if event_id not in stub.get('adverse_event_ids', []):
                stub.setdefault('adverse_event_ids', []).append(event_id)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    write_patient_log(folder, homer_id, loginid, session_id, 'Adverse event recorded.')

    return jsonify({'ok': True, 'id': event_id})


@bp.route('/api/patients/<homer_id>/complete-event/adverse-event-followup', methods=['POST'])
def api_complete_adverse_event_followup(homer_id):
    """Complete an adverse_event_followup stub."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # AE follow-up routes deliberately do NOT block discontinued patients —
    # AE chains must remain completable after discontinuation until all AEs are resolved.
    patient = read_patient_meta(folder, homer_id)

    body                    = request.get_json() or {}
    event_id                = body.get('event_id')
    completion_date         = (body.get('completion_date') or '').strip()
    duration_str            = str(body.get('duration_minutes', '')).strip()
    call_mode               = (body.get('call_mode') or '').strip()
    # patient_initiated must be a real bool — missing/non-bool is rejected so the
    # therapist can't sidestep the required two-pill radio.
    patient_initiated_raw   = body.get('patient_initiated', None)
    notes                   = (body.get('notes') or '').strip()
    ae_discussions          = body.get('ae_discussions', [])
    scheduled_followup_visit = (body.get('scheduled_followup_visit') or '').strip() or None
    scheduled_clinical_visit = (body.get('scheduled_clinical_visit') or '').strip() or None

    if not event_id:
        return jsonify({'error': 'event_id is required.'}), 400
    if not completion_date:
        return jsonify({'error': 'Call date is required.'}), 400
    # Load events_data up-front so the per-event Date Rule Framework lookup can
    # resolve `event:adverse_event` (the AE follow-up's `not_before` token).
    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404
    if r := _bad_date(patient, completion_date,
                      event_id='adverse_event_followup', events_data=events_data): return r
    if r := _bad_call_mode(call_mode):            return r
    if not isinstance(patient_initiated_raw, bool):
        return jsonify({'error': 'Please indicate who initiated this call (Therapist / Patient).'}), 400
    patient_initiated = patient_initiated_raw
    try:
        if datetime.strptime(completion_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'Call date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400
    if not duration_str:
        return jsonify({'error': 'Duration is required.'}), 400
    try:
        duration_minutes = int(duration_str)
        if duration_minutes <= 0:
            raise ValueError
    except ValueError:
        return jsonify({'error': 'Duration must be a positive integer.'}), 400
    if not notes:
        return jsonify({'error': 'Notes are required.'}), 400
    if not isinstance(ae_discussions, list):
        return jsonify({'error': 'ae_discussions must be a list.'}), 400
    for sched_field, label in ((scheduled_followup_visit, 'Follow-up visit date'),
                                (scheduled_clinical_visit, 'Clinical visit date')):
        if sched_field:
            try:
                datetime.strptime(sched_field, '%Y-%m-%dT%H:%M')
            except ValueError:
                return jsonify({'error': f'Invalid date format for {label}.'}), 400

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == 'adverse_event_followup' and e.get('id') == event_id),
        None
    )
    if not entry:
        return jsonify({'error': 'Follow-up stub not found.'}), 404

    # Validate ae_discussions against the stub's AE list
    stub_ae_ids = entry.get('adverse_event_ids', [])
    resolved_ids = {r['adverse_event_id'] for r in ae_discussions if r.get('resolved')}

    # Look up each AE to check training_blocked
    training_ended = bool(patient and (
        patient.get('trainingCompletionDate') or
        patient.get('brokenProtocolDate') or
        patient.get('discontinuationDate')
    ))
    if not training_ended and patient and patient.get('activationDate'):
        try:
            _act = datetime.fromisoformat(patient['activationDate']).date()
            training_ended = date.today() > _act + timedelta(days=28)
        except Exception:
            pass
    free_aes = {ae['id']: ae for ae in events_data.get('free', {}).get('adverse_event', [])}
    for r in ae_discussions:
        ae_id = r.get('adverse_event_id')
        if ae_id not in stub_ae_ids:
            return jsonify({'error': f'Unknown adverse_event_id: {ae_id}'}), 400
        if r.get('resolved'):
            ae = free_aes.get(ae_id, {})
            if ae.get('training_blocked') and not training_ended and not (r.get('can_resume_from') or '').strip():
                return jsonify({'error': 'can_resume_from is required for resolved training-blocked events.'}), 400

    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    today    = date.today()
    tomorrow = (today + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    today_str = today.strftime('%Y-%m-%dT%H:%M')

    complete_entry = {
        **entry,
        'alias':                   _next_call_alias(events_data),
        'completion_date':         completion_date,
        'filed_at':                filed_at,
        'filed_by':   _filer(),
        'duration_minutes':        duration_minutes,
        'call_mode':               call_mode,
        'patient_initiated':       patient_initiated,
        'notes':                   notes,
        'ae_discussions':          ae_discussions,
        'scheduled_followup_visit': scheduled_followup_visit,
        'scheduled_clinical_visit': scheduled_clinical_visit,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    events_data.setdefault('free', {}).setdefault('adverse_event_followup', []).append(complete_entry)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    # Create explicitly-scheduled visit/clinical stubs (uses all AE IDs from this call stub)
    _create_ae_visit_stubs(events_data, 'adverse_event_followup', event_id, stub_ae_ids,
                            scheduled_followup_visit, scheduled_clinical_visit, filed_at)

    # Determine unresolved AEs to carry into next follow-up call stub
    unresolved_ids = [ae_id for ae_id in stub_ae_ids if ae_id not in resolved_ids]

    if unresolved_ids:
        events_data.setdefault('incomplete', []).append({
            'id':                str(uuid.uuid4()),
            'protocol_event_id': 'adverse_event_followup',
            'adverse_event_ids': unresolved_ids,
            'scheduled_date':    [today_str, tomorrow],
            'filed_at':          filed_at,
            'filed_by':   _filer(),
        })
    else:
        # All AEs resolved — check if pause can be cleared
        patient_meta = read_patient_meta(folder, homer_id)
        resolve_ri_stubs = [
            e for e in events_data.get('incomplete', [])
            if e.get('protocol_event_id') == 'resolve_robot_issue_visit'
        ]
        if patient_meta and patient_meta.get('trainingPausedDate') and not resolve_ri_stubs and not training_ended:
            # Compute cumulativePauseDays from max can_resume_from across all pausing AEs
            training_paused = datetime.fromisoformat(patient_meta['trainingPausedDate']).date()
            resume_dates = []
            for r in ae_discussions:
                ae = free_aes.get(r.get('adverse_event_id'), {})
                if r.get('resolved') and ae.get('training_blocked') and r.get('can_resume_from'):
                    try:
                        resume_dates.append(date.fromisoformat(r['can_resume_from']))
                    except ValueError:
                        pass
            max_resume = max(resume_dates) if resume_dates else None
            if max_resume:
                pause_days = max(0, (max_resume - training_paused).days)
                patient_meta['cumulativePauseDays'] = (patient_meta.get('cumulativePauseDays') or 0) + pause_days
            else:
                pause_days = 0
            # Close the open pauseHistory epoch
            end_dt = filed_at[:16]
            open_epoch = next((e for e in patient_meta.get('pauseHistory', []) if e.get('end') is None), None)
            if open_epoch:
                open_epoch['end']          = end_dt
                open_epoch['days']         = pause_days
                open_epoch['end_event_id'] = event_id
            patient_meta['trainingPausedDate'] = None
            if (patient_meta.get('cumulativePauseDays') or 0) > 10:
                if not patient_meta.get('brokenProtocolDate'):
                    patient_meta['brokenProtocolDate'] = filed_at[:10]
            if max_resume and _check_d0203_broken_protocol(events_data, max_resume):
                if not patient_meta.get('brokenProtocolDate'):
                    patient_meta['brokenProtocolDate'] = filed_at[:10]
            if patient_meta.get('brokenProtocolDate'):
                _cancel_training_ended_stubs(events_data, ['watch_record'], filed_at)
            _shift_future_incomplete_events(events_data, pause_days)
            write_patient_meta(folder, homer_id, patient_meta)
            write_patient_log(folder, homer_id, loginid, session_id, 'Adverse event(s) resolved — training resumed')

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    write_patient_log(folder, homer_id, loginid, session_id, 'Adverse event follow-up call recorded.')

    return jsonify({'ok': True, 'id': event_id})


def _check_d0203_broken_protocol(events_data, can_resume_from):
    """Return True if D02 or D03 training was missed due to pause (window ended before resume date)."""
    complete_ids = {e['protocol_event_id'] for e in events_data.get('complete', [])}
    for visit_id in ('home_visit_d02', 'home_visit_d03'):
        if visit_id in complete_ids:
            continue
        entry = next((e for e in events_data.get('incomplete', [])
                      if e.get('protocol_event_id') == visit_id), None)
        if entry is None:
            continue
        sd = entry.get('scheduled_date')
        if not sd or sd[1] is None:
            continue
        try:
            end_date = datetime.fromisoformat(sd[1]).date()
        except (ValueError, TypeError):
            continue
        if end_date < can_resume_from:
            return True
    return False


def _shift_future_incomplete_events(events_data, pause_days):
    """Shift all future incomplete scheduled_date windows forward by pause_days calendar days."""
    if not pause_days or pause_days <= 0:
        return
    delta = timedelta(days=pause_days)
    for entry in events_data.get('incomplete', []):
        sd = entry.get('scheduled_date')
        if not sd or not isinstance(sd, list) or len(sd) != 2:
            continue
        if sd[0] is None or sd[1] is None:
            continue
        try:
            start = datetime.fromisoformat(sd[0])
            end   = datetime.fromisoformat(sd[1])
            entry['scheduled_date'] = [
                (start + delta).strftime('%Y-%m-%dT%H:%M'),
                (end   + delta).strftime('%Y-%m-%dT%H:%M'),
            ]
        except (ValueError, TypeError):
            pass


def _clear_ae_pause_if_resolved(patient_meta, events_data, ae_discussions, free_aes, filed_at, event_id, folder, homer_id, loginid, session_id, training_ended=False):
    """Clear trainingPausedDate if all AEs resolved and no resolve_robot_issue_visit stubs remain."""
    resolve_ri_stubs = [
        e for e in events_data.get('incomplete', [])
        if e.get('protocol_event_id') == 'resolve_robot_issue_visit'
    ]
    if not patient_meta or not patient_meta.get('trainingPausedDate') or resolve_ri_stubs or training_ended:
        return
    training_paused = datetime.fromisoformat(patient_meta['trainingPausedDate']).date()
    resume_dates = []
    for r in ae_discussions:
        ae = free_aes.get(r.get('adverse_event_id'), {})
        if r.get('resolved') and ae.get('training_blocked') and r.get('can_resume_from'):
            try:
                resume_dates.append(date.fromisoformat(r['can_resume_from']))
            except ValueError:
                pass
    max_resume = max(resume_dates) if resume_dates else None
    if max_resume:
        pause_days = max(0, (max_resume - training_paused).days)
    else:
        # No can_resume_from (training already ended) — use actual elapsed days
        pause_days = max(0, (date.fromisoformat(filed_at[:10]) - training_paused).days)
    patient_meta['cumulativePauseDays'] = (patient_meta.get('cumulativePauseDays') or 0) + pause_days
    end_dt = filed_at[:16]
    open_epoch = next((e for e in patient_meta.get('pauseHistory', []) if e.get('end') is None), None)
    if open_epoch:
        open_epoch['end']          = end_dt
        open_epoch['days']         = pause_days
        open_epoch['end_event_id'] = event_id
    patient_meta['trainingPausedDate'] = None
    if (patient_meta.get('cumulativePauseDays') or 0) > 10:
        if not patient_meta.get('brokenProtocolDate'):
            patient_meta['brokenProtocolDate'] = filed_at[:10]
    if max_resume and _check_d0203_broken_protocol(events_data, max_resume):
        if not patient_meta.get('brokenProtocolDate'):
            patient_meta['brokenProtocolDate'] = filed_at[:10]
    if patient_meta.get('brokenProtocolDate'):
        _cancel_training_ended_stubs(events_data, ['watch_record'], filed_at)
    _shift_future_incomplete_events(events_data, pause_days)
    write_patient_meta(folder, homer_id, patient_meta)
    write_patient_log(folder, homer_id, loginid, session_id, 'Adverse event(s) resolved — training resumed')


def _compute_globally_unresolved_ae_ids(events_data, free_aes):
    """Return AE IDs that have NOT been resolved in any completed follow-up event."""
    resolved = set()
    for ftype in ('adverse_event_followup', 'adverse_event_followup_visit',
                  'adverse_event_clinical_visit'):
        for entry in events_data.get('free', {}).get(ftype, []):
            for disc in entry.get('ae_discussions', []):
                if disc.get('resolved'):
                    resolved.add(disc['adverse_event_id'])
    return [ae_id for ae_id in free_aes if ae_id not in resolved]


def _seed_next_ae_followup_or_clear(events_data, stub_ae_ids, ae_discussions, free_aes,
                                     patient_meta, filed_at, event_id,
                                     folder, homer_id, loginid, session_id, training_ended=False):
    """Seed next follow-up stub for unresolved AEs, or clear pause if all resolved.
    Only one adverse_event_followup stub may exist in incomplete at a time."""
    # Derive unresolved AEs globally across all completed follow-up events so
    # that resolving an AE in any event type correctly removes it from all stubs.
    unresolved_ids = _compute_globally_unresolved_ae_ids(events_data, free_aes)
    today_str = date.today().strftime('%Y-%m-%dT%H:%M')
    tomorrow  = (date.today() + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
    if unresolved_ids:
        existing = next(
            (e for e in events_data.get('incomplete', [])
             if e.get('protocol_event_id') == 'adverse_event_followup'),
            None
        )
        if existing is None:
            events_data.setdefault('incomplete', []).append({
                'id':                str(uuid.uuid4()),
                'protocol_event_id': 'adverse_event_followup',
                'adverse_event_ids': unresolved_ids,
                'scheduled_date':    [today_str, tomorrow],
                'filed_at':          filed_at,
                'filed_by':   _filer(),
            })
        else:
            existing['adverse_event_ids'] = unresolved_ids
        # Prune resolved AEs from any existing visit / clinical visit stubs
        unresolved_set = set(unresolved_ids)
        for stub in events_data.get('incomplete', []):
            if stub.get('protocol_event_id') in (
                'adverse_event_followup_visit', 'adverse_event_clinical_visit'
            ):
                stub['adverse_event_ids'] = [
                    aid for aid in stub.get('adverse_event_ids', [])
                    if aid in unresolved_set
                ]
    else:
        # All AEs resolved — remove any lingering follow-up call stub
        events_data['incomplete'] = [
            e for e in events_data.get('incomplete', [])
            if e.get('protocol_event_id') != 'adverse_event_followup'
        ]
        _clear_ae_pause_if_resolved(patient_meta, events_data, ae_discussions, free_aes,
                                     filed_at, event_id, folder, homer_id, loginid, session_id,
                                     training_ended=training_ended)


def _create_ae_visit_stubs(events_data, source_type, source_id, ae_ids,
                            scheduled_followup_visit, scheduled_clinical_visit, filed_at):
    """Create follow-up visit and/or clinical visit stubs when the therapist schedules them."""
    if scheduled_followup_visit and ae_ids:
        events_data.setdefault('incomplete', []).append({
            'id':                str(uuid.uuid4()),
            'protocol_event_id': 'adverse_event_followup_visit',
            'adverse_event_ids': list(ae_ids),
            'scheduled_date':    [scheduled_followup_visit, scheduled_followup_visit],
            'filed_at':          filed_at,
            'filed_by':   _filer(),
            'triggered_by':      {'type': source_type, 'id': source_id},
        })
    if scheduled_clinical_visit and ae_ids:
        events_data.setdefault('incomplete', []).append({
            'id':                str(uuid.uuid4()),
            'protocol_event_id': 'adverse_event_clinical_visit',
            'adverse_event_ids': list(ae_ids),
            'scheduled_date':    [scheduled_clinical_visit, scheduled_clinical_visit],
            'filed_at':          filed_at,
            'filed_by':   _filer(),
            'triggered_by':      {'type': source_type, 'id': source_id},
        })


@bp.route('/api/patients/<homer_id>/complete-event/ae-followup-visit', methods=['POST'])
def api_complete_ae_followup_visit(homer_id):
    """Complete an adverse_event_followup_visit stub."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # AE follow-up routes deliberately do NOT block discontinued patients.
    patient = read_patient_meta(folder, homer_id)

    body                     = request.get_json() or {}
    event_id                 = body.get('event_id')
    triggered_by             = body.get('triggered_by')
    visit_start              = (body.get('visit_start') or '').strip()
    visit_end                = (body.get('visit_end') or '').strip()
    notes                    = (body.get('notes') or '').strip() or None
    ae_discussions           = body.get('ae_discussions', [])
    scheduled_followup_visit = (body.get('scheduled_followup_visit') or '').strip() or None
    scheduled_clinical_visit = (body.get('scheduled_clinical_visit') or '').strip() or None

    # Two modes:
    #   1) Stub-driven (default): `event_id` references an existing
    #      `adverse_event_followup_visit` stub seeded via the "Schedule a
    #      follow-up visit" toggle. Visit start < end (real time range).
    #   2) Ad-hoc (`event_id` absent, `triggered_by` present): the AE
    #      discussion happened during a parent visit (e.g., D29 home visit).
    #      No stub exists; the entry is created fresh, AE ids are sourced from
    #      the active `adverse_event_followup` daily call stub, and visit
    #      start == end is allowed (the parent visit is a point in time).
    ad_hoc = (not event_id) and isinstance(triggered_by, dict) and triggered_by.get('type')

    if not event_id and not ad_hoc:
        return jsonify({'error': 'event_id is required.'}), 400
    if not visit_start:
        return jsonify({'error': 'Visit start is required.'}), 400
    if not visit_end:
        return jsonify({'error': 'Visit end is required.'}), 400
    if r := _bad_date(patient, visit_start): return r
    try:
        start_dt = datetime.strptime(visit_start, '%Y-%m-%dT%H:%M')
        end_dt   = datetime.strptime(visit_end,   '%Y-%m-%dT%H:%M')
        if start_dt > datetime.now():
            return jsonify({'error': 'Visit start cannot be in the future.'}), 400
        if start_dt.date() != end_dt.date():
            return jsonify({'error': 'Visit start and end must be on the same date.'}), 400
        # Ad-hoc mode files at a single instant (parent visit's completion
        # date), so end == start is valid. The stub-driven path keeps the
        # strict "end > start" check.
        if (not ad_hoc) and end_dt <= start_dt:
            return jsonify({'error': 'Visit end must be after visit start.'}), 400
        if ad_hoc and end_dt < start_dt:
            return jsonify({'error': 'Visit end cannot be before visit start.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400
    if not isinstance(ae_discussions, list):
        return jsonify({'error': 'ae_discussions must be a list.'}), 400
    for sched_field, label in ((scheduled_followup_visit, 'Follow-up visit date'),
                                (scheduled_clinical_visit, 'Clinical visit date')):
        if sched_field:
            try:
                datetime.strptime(sched_field, '%Y-%m-%dT%H:%M')
            except ValueError:
                return jsonify({'error': f'Invalid date format for {label}.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    if ad_hoc:
        # No stub to consume. Source AE ids from the daily call stub (the
        # active AE-chain register) and synthesize a minimal entry shape so
        # the rest of the route works unchanged.
        aef_call_stub = next(
            (e for e in incomplete if e.get('protocol_event_id') == 'adverse_event_followup'),
            None
        )
        if not aef_call_stub:
            return jsonify({'error': 'No active AE follow-up to attach this visit to.'}), 400
        import uuid as _uuid
        entry = {
            'id':                str(_uuid.uuid4()),
            'protocol_event_id': 'adverse_event_followup_visit',
            'adverse_event_ids': list(aef_call_stub.get('adverse_event_ids', [])),
            'triggered_by':      triggered_by,
            'scheduled_date':    [visit_start, visit_start],
        }
        # Use this id as the entry's identifier for downstream code paths that
        # expect `event_id` to point at the entry being written.
        event_id = entry['id']
    else:
        entry = next(
            (e for e in incomplete
             if e.get('protocol_event_id') == 'adverse_event_followup_visit' and e.get('id') == event_id),
            None
        )
        if not entry:
            return jsonify({'error': 'Follow-up visit stub not found.'}), 404

    training_ended = bool(patient and (
        patient.get('trainingCompletionDate') or
        patient.get('brokenProtocolDate') or
        patient.get('discontinuationDate')
    ))
    if not training_ended and patient and patient.get('activationDate'):
        try:
            _act = datetime.fromisoformat(patient['activationDate']).date()
            training_ended = date.today() > _act + timedelta(days=28)
        except Exception:
            pass
    stub_ae_ids = entry.get('adverse_event_ids', [])
    free_aes    = {ae['id']: ae for ae in events_data.get('free', {}).get('adverse_event', [])}

    for r in ae_discussions:
        ae_id = r.get('adverse_event_id')
        if ae_id not in stub_ae_ids:
            return jsonify({'error': f'Unknown adverse_event_id: {ae_id}'}), 400
        if r.get('resolved'):
            ae = free_aes.get(ae_id, {})
            if ae.get('training_blocked') and not training_ended and not (r.get('can_resume_from') or '').strip():
                return jsonify({'error': 'can_resume_from is required for resolved training-blocked events.'}), 400

    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    complete_entry = {
        **entry,
        'completion_date':          visit_start,
        'filed_at':                 filed_at,
        'filed_by':   _filer(),
        'visit_start':              visit_start,
        'visit_end':                visit_end,
        'ae_discussions':           ae_discussions,
        'notes':                    notes,
        'scheduled_followup_visit': scheduled_followup_visit,
        'scheduled_clinical_visit': scheduled_clinical_visit,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    events_data.setdefault('free', {}).setdefault('adverse_event_followup_visit', []).append(complete_entry)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    # Create explicitly-scheduled visit/clinical stubs (unresolved AE IDs only)
    resolved_ids_fv     = {r['adverse_event_id'] for r in ae_discussions if r.get('resolved')}
    unresolved_ids_fv   = [ae_id for ae_id in stub_ae_ids if ae_id not in resolved_ids_fv]
    _create_ae_visit_stubs(events_data, 'adverse_event_followup_visit', event_id, unresolved_ids_fv,
                            scheduled_followup_visit, scheduled_clinical_visit, filed_at)

    patient_meta = read_patient_meta(folder, homer_id)
    _seed_next_ae_followup_or_clear(events_data, stub_ae_ids, ae_discussions, free_aes,
                                     patient_meta, filed_at, event_id,
                                     folder, homer_id, loginid, session_id,
                                     training_ended=training_ended)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)
    write_patient_log(folder, homer_id, loginid, session_id, 'AE follow-up visit recorded.')

    return jsonify({'ok': True, 'id': event_id})


@bp.route('/api/patients/<homer_id>/complete-event/ae-clinical-visit', methods=['POST'])
def api_complete_ae_clinical_visit(homer_id):
    """Complete an adverse_event_clinical_visit stub."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # AE follow-up routes deliberately do NOT block discontinued patients.
    patient = read_patient_meta(folder, homer_id)

    body                     = request.get_json() or {}
    event_id                 = body.get('event_id')
    visit_start              = (body.get('visit_start') or '').strip()
    visit_end                = (body.get('visit_end') or '').strip()
    notes                    = (body.get('notes') or '').strip() or None
    ae_discussions           = body.get('ae_discussions', [])
    scheduled_followup_visit = (body.get('scheduled_followup_visit') or '').strip() or None
    scheduled_clinical_visit = (body.get('scheduled_clinical_visit') or '').strip() or None

    if not event_id:
        return jsonify({'error': 'event_id is required.'}), 400
    if not visit_start:
        return jsonify({'error': 'Visit start is required.'}), 400
    if not visit_end:
        return jsonify({'error': 'Visit end is required.'}), 400
    if r := _bad_date(patient, visit_start): return r
    try:
        start_dt = datetime.strptime(visit_start, '%Y-%m-%dT%H:%M')
        end_dt   = datetime.strptime(visit_end,   '%Y-%m-%dT%H:%M')
        if start_dt > datetime.now():
            return jsonify({'error': 'Visit start cannot be in the future.'}), 400
        if start_dt.date() != end_dt.date():
            return jsonify({'error': 'Visit start and end must be on the same date.'}), 400
        if end_dt <= start_dt:
            return jsonify({'error': 'Visit end must be after visit start.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400
    if not isinstance(ae_discussions, list):
        return jsonify({'error': 'ae_discussions must be a list.'}), 400
    for sched_field, label in ((scheduled_followup_visit, 'Follow-up visit date'),
                                (scheduled_clinical_visit, 'Clinical visit date')):
        if sched_field:
            try:
                datetime.strptime(sched_field, '%Y-%m-%dT%H:%M')
            except ValueError:
                return jsonify({'error': f'Invalid date format for {label}.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == 'adverse_event_clinical_visit' and e.get('id') == event_id),
        None
    )
    if not entry:
        return jsonify({'error': 'Clinical visit stub not found.'}), 404

    stub_ae_ids = entry.get('adverse_event_ids', [])
    free_aes    = {ae['id']: ae for ae in events_data.get('free', {}).get('adverse_event', [])}

    training_ended = bool(patient and (
        patient.get('trainingCompletionDate') or
        patient.get('brokenProtocolDate') or
        patient.get('discontinuationDate')
    ))
    if not training_ended and patient and patient.get('activationDate'):
        try:
            _act = datetime.fromisoformat(patient['activationDate']).date()
            training_ended = date.today() > _act + timedelta(days=28)
        except Exception:
            pass

    for r in ae_discussions:
        ae_id = r.get('adverse_event_id')
        if ae_id not in stub_ae_ids:
            return jsonify({'error': f'Unknown adverse_event_id: {ae_id}'}), 400
        if r.get('resolved'):
            ae = free_aes.get(ae_id, {})
            if ae.get('training_blocked') and not training_ended and not (r.get('can_resume_from') or '').strip():
                return jsonify({'error': 'can_resume_from is required for resolved training-blocked events.'}), 400

    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')

    complete_entry = {
        **entry,
        'completion_date':          visit_start,
        'filed_at':                 filed_at,
        'filed_by':   _filer(),
        'visit_start':              visit_start,
        'visit_end':                visit_end,
        'ae_discussions':           ae_discussions,
        'notes':                    notes,
        'scheduled_followup_visit': scheduled_followup_visit,
        'scheduled_clinical_visit': scheduled_clinical_visit,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    events_data.setdefault('free', {}).setdefault('adverse_event_clinical_visit', []).append(complete_entry)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    # Create explicitly-scheduled visit/clinical stubs (unresolved AE IDs only)
    resolved_ids_cv   = {r['adverse_event_id'] for r in ae_discussions if r.get('resolved')}
    unresolved_ids_cv = [ae_id for ae_id in stub_ae_ids if ae_id not in resolved_ids_cv]
    _create_ae_visit_stubs(events_data, 'adverse_event_clinical_visit', event_id, unresolved_ids_cv,
                            scheduled_followup_visit, scheduled_clinical_visit, filed_at)

    patient_meta = read_patient_meta(folder, homer_id)
    _seed_next_ae_followup_or_clear(events_data, stub_ae_ids, ae_discussions, free_aes,
                                     patient_meta, filed_at, event_id,
                                     folder, homer_id, loginid, session_id,
                                     training_ended=training_ended)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)
    write_patient_log(folder, homer_id, loginid, session_id, 'AE clinical visit recorded.')

    return jsonify({'ok': True, 'id': event_id})


@bp.route('/api/patients/<homer_id>/cancel-event/<event_type>', methods=['POST'])
def api_cancel_event(homer_id, event_type):
    """Cancel a cancellable stub — moves it from incomplete to cancelled array."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    cancellable_types = {'ae-followup-visit': 'adverse_event_followup_visit',
                         'ae-clinical-visit':  'adverse_event_clinical_visit'}
    protocol_event_id = cancellable_types.get(event_type)
    if not protocol_event_id:
        return jsonify({'error': 'Unknown or non-cancellable event type.'}), 400

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    body                = request.get_json() or {}
    event_id            = body.get('event_id')
    cancellation_reason = (body.get('cancellation_reason') or '').strip()

    if not event_id:
        return jsonify({'error': 'event_id is required.'}), 400
    if not cancellation_reason:
        return jsonify({'error': 'Cancellation reason is required.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == protocol_event_id and e.get('id') == event_id),
        None
    )
    if not entry:
        return jsonify({'error': 'Stub not found.'}), 404

    cancelled_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    cancelled_entry = {**entry, 'cancelled_at': cancelled_at, 'cancellation_reason': cancellation_reason}

    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    events_data.setdefault('cancelled', []).append(cancelled_entry)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)
    write_patient_log(folder, homer_id, loginid, session_id,
                      f'{protocol_event_id} cancelled — {cancellation_reason}')

    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/issue-validation-dates', methods=['POST'])
def api_issue_validation_dates(homer_id):
    """Fetch patient enrollment date and triggered event's issue occurrence date for validation."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    data = request.get_json() or {}
    triggered_by_id = (data.get('triggered_by_id') or '').strip()

    # Get patient enrollment date
    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient data not found'}), 404

    enroll_date = patient.get('activationDate')

    # Get issue occurrence date from triggered event (if applicable)
    issue_occur_date = None
    if triggered_by_id:
        events_data = read_protocol_events(folder, homer_id)
        if events_data:
            # Search in free events for the triggered event
            for event_type_key in ['robot_issue_call', 'robot_issue_visit', 'resolve_robot_issue_visit',
                                    'other_device_issue_call', 'other_device_issue_visit']:
                for ev in events_data.get('free', {}).get(event_type_key, []):
                    if ev.get('id') == triggered_by_id:
                        issue_occur_date = ev.get('issue_occur_date') or ev.get('completion_date', '').split('T')[0]
                        break

    return jsonify({
        'enroll_date': enroll_date,
        'issue_occur_date': issue_occur_date,
    })


@bp.route('/api/patients/<homer_id>/complete-event/robot-issue-call', methods=['POST'])
def api_complete_robot_issue_call(homer_id):
    """Complete a robot_issue_call stub; if any device needs a visit, create robot_issue_visit stub."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    body             = request.get_json() or {}
    event_id         = body.get('event_id')
    completion_date  = (body.get('completion_date') or '').strip()
    issue_occur_date = (body.get('issue_occur_date') or '').strip() or None
    call_mode        = (body.get('call_mode') or '').strip()
    notes            = (body.get('notes') or '').strip() or None
    devices          = body.get('devices', [])  # [{device, outcome, notes}]

    if not event_id:
        return jsonify({'error': 'event_id is required.'}), 400
    if not completion_date:
        return jsonify({'error': 'Call date is required.'}), 400
    if r := _bad_date(patient, completion_date): return r
    if r := _bad_call_mode(call_mode):            return r
    try:
        call_dt = datetime.strptime(completion_date, '%Y-%m-%dT%H:%M')
        if call_dt > datetime.now():
            return jsonify({'error': 'Call date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid call date format.'}), 400

    # Validate issue_occur_date (required for robot issues)
    if not issue_occur_date:
        return jsonify({'error': 'Issue occurred date is required.'}), 400
    if r := _bad_date(patient, issue_occur_date): return r
    try:
        issue_dt = _parse_date_flex(issue_occur_date)
        if not issue_dt:
            return jsonify({'error': f'Invalid issue occurred date format: {issue_occur_date}'}), 400
        today = datetime.now()
        if issue_dt > today:
            return jsonify({'error': 'Issue occurred date cannot be in the future.'}), 400
        if patient and patient.get('activationDate'):
            activation_dt = _parse_date_flex(patient['activationDate'])
            if not activation_dt:
                return jsonify({'error': f"Invalid activation date format: {patient['activationDate']}"}), 400
            if issue_dt.date() < activation_dt.date():
                return jsonify({'error': f"Issue occurred date must be on or after activation date ({patient['activationDate']})."}), 400
        # Validate call date is after issue occurred date
        if call_dt.date() < issue_dt.date():
            return jsonify({'error': 'Call date must be on or after issue occurred date.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid issue occurred date format.'}), 400
    is_bp = bool(patient.get('brokenProtocolDate'))

    if not isinstance(devices, list):
        return jsonify({'error': 'devices must be a list.'}), 400
    if not is_bp:
        valid_outcomes = ('resolved', 'visit_required')
        for d in devices:
            if d.get('device') not in ('pluto', 'mars'):
                return jsonify({'error': 'device must be pluto or mars.'}), 400
            if d.get('outcome') not in valid_outcomes:
                return jsonify({'error': 'device outcome must be resolved or visit_required.'}), 400
    else:
        for d in devices:
            if d.get('device') not in ('pluto', 'mars'):
                return jsonify({'error': 'device must be pluto or mars.'}), 400
    if not devices and not notes:
        return jsonify({'error': 'Notes are required when no device is selected.'}), 400

    patient_meta = read_patient_meta(folder, homer_id)
    if not patient_meta or patient_meta.get('group') != 'experimental':
        return jsonify({'error': 'Robot issue call is only valid for experimental patients.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == 'robot_issue_call' and e.get('id') == event_id),
        None
    )
    if not entry:
        return jsonify({'error': 'Robot issue call stub not found.'}), 404

    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm   = datetime.now().strftime('%Y-%m-%dT%H:%M')
    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)
    device_folder = get_hospital_folder(flask_session['login_place'])

    if is_bp:
        # Broken-protocol mode: mark each selected device faulty, no visit stub
        for d in devices:
            dtype     = d.get('device')
            dev_notes = (d.get('notes') or '').strip() or None
            if dtype not in ('pluto', 'mars'):
                continue
            # Find device_id via open assignment for this patient
            assignments = read_device_assignments(device_folder, dtype)
            device_id = next(
                (a['device_id'] for a in assignments
                 if a.get('homer_id') == homer_id and a.get('returned_date') is None),
                None
            )
            if not device_id:
                continue
            inv = read_device_inventory(device_folder, dtype)
            for dev in inv:
                if dev['id'] == device_id:
                    dev['has_issue'] = True
                    break
            write_device_inventory(device_folder, dtype, {'devices': inv})
            append_device_event(device_folder, dtype, device_id,
                                event_type='faulty', by=loginid,
                                notes=dev_notes, homer_id=homer_id,
                                patient_event_id=event_id,
                                issue_occur_date=issue_occur_date)
        complete_entry = {
            **entry,
            'completion_date':      completion_date,
            'issue_occur_date':     issue_occur_date,
            'filed_at':             filed_at,
            'filed_by':   _filer(),
            'call_mode':            call_mode,
            'notes':                notes,
            'devices':              devices,
            'visit_required':       False,
            'broken_protocol_mode': True,
        }
        events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
        existing_ris = events_data.setdefault('free', {}).setdefault('robot_issue_call', [])
        complete_entry['alias'] = f"RI{len(existing_ris) + 1:02d}"
        existing_ris.append(complete_entry)
        write_protocol_events(folder, homer_id, events_data)
        write_patient_log(folder, homer_id, loginid, session_id, 'Robot issue call recorded (broken protocol).')
        return jsonify({'ok': True})

    visit_required = any(d.get('outcome') == 'visit_required' for d in devices)

    complete_entry = {
        **entry,
        'completion_date':  completion_date,
        'issue_occur_date': issue_occur_date,
        'filed_at':         filed_at,
        'filed_by':   _filer(),
        'call_mode':        call_mode,
        'notes':            notes,
        'devices':          devices,
        'visit_required':   visit_required,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    existing_ris = events_data.setdefault('free', {}).setdefault('robot_issue_call', [])
    complete_entry['alias'] = f"RI{len(existing_ris) + 1:02d}"
    existing_ris.append(complete_entry)

    if visit_required:
        events_data.setdefault('incomplete', []).append({
            'id':                str(uuid.uuid4()),
            'protocol_event_id': 'robot_issue_visit',
            'triggered_by':      {'type': 'robot_issue_call', 'id': event_id},
            'scheduled_date':    [now_hhmm, now_hhmm],
            'filed_at':          filed_at,
            'filed_by':   _filer(),
        })
        write_patient_log(folder, homer_id, loginid, session_id, 'Robot issue visit required.')

    write_protocol_events(folder, homer_id, events_data)
    write_patient_log(folder, homer_id, loginid, session_id, 'Robot issue call recorded.')

    return jsonify({'ok': True})


# ── Other Device Issue ─────────────────────────────────────────────────────────

@bp.route('/api/patients/<homer_id>/complete-event/other-device-issue-call', methods=['POST'])
def api_complete_other_device_issue_call(homer_id):
    """Complete an other_device_issue_call stub: record issue_occur_date + per-device outcome."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    body             = request.get_json() or {}
    event_id         = body.get('event_id')
    completion_date  = (body.get('completion_date') or '').strip()
    issue_occur_date = (body.get('issue_occur_date') or '').strip() or None
    call_mode        = (body.get('call_mode') or '').strip()
    notes            = (body.get('notes') or '').strip() or None
    devices_list     = body.get('devices', [])

    if not event_id:
        return jsonify({'error': 'event_id is required.'}), 400
    if not completion_date:
        return jsonify({'error': 'Call date is required.'}), 400
    if r := _bad_date(patient, completion_date):  return r
    if r := _bad_call_mode(call_mode):            return r
    if r := _bad_date(patient, issue_occur_date): return r
    try:
        call_dt = datetime.strptime(completion_date, '%Y-%m-%dT%H:%M')
        if call_dt > datetime.now():
            return jsonify({'error': 'Call date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid call date format.'}), 400

    # Validate issue_occur_date (if provided)
    if issue_occur_date:
        try:
            issue_dt = _parse_date_flex(issue_occur_date)
            if not issue_dt:
                return jsonify({'error': f'Invalid issue occurred date format: {issue_occur_date}'}), 400
            today = datetime.now()
            if issue_dt > today:
                return jsonify({'error': 'Issue occurred date cannot be in the future.'}), 400
            if patient and patient.get('activationDate'):
                activation_dt = _parse_date_flex(patient['activationDate'])
                if not activation_dt:
                    return jsonify({'error': f"Invalid activation date format: {patient['activationDate']}"}), 400
                if issue_dt.date() < activation_dt.date():
                    return jsonify({'error': f"Issue occurred date must be on or after activation date ({patient['activationDate']})."}), 400
            # Validate call date is after issue occurred date
            if call_dt.date() < issue_dt.date():
                return jsonify({'error': 'Call date must be on or after issue occurred date.'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid issue occurred date format.'}), 400
    is_bp = bool(patient.get('brokenProtocolDate'))

    if not isinstance(devices_list, list) or not devices_list:
        return jsonify({'error': 'At least one device entry is required.'}), 400

    valid_dtypes   = ('modems', 'laptops', 'sims')
    valid_outcomes = ('visit_required', 'resolved_over_call')
    for d in devices_list:
        if d.get('device_type') not in valid_dtypes:
            return jsonify({'error': f'device_type must be one of {valid_dtypes}'}), 400
        if not is_bp and d.get('outcome') not in valid_outcomes:
            return jsonify({'error': f'outcome must be visit_required or resolved_over_call'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == 'other_device_issue_call' and e.get('id') == event_id),
        None
    )
    if not entry:
        return jsonify({'error': 'Other device issue call stub not found.'}), 404

    device_folder = get_hospital_folder(flask_session['login_place'])
    loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    session_id = flask_session.get('session_id', -1)
    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm   = datetime.now().strftime('%Y-%m-%dT%H:%M')

    if is_bp:
        # Broken-protocol mode: mark each selected device faulty, no visit stub
        device_results = []
        for d in devices_list:
            dtype     = d.get('device_type')
            device_id = (d.get('device_id') or '').strip()
            d_notes   = (d.get('notes') or '').strip() or None
            if not device_id:
                continue
            if dtype == 'sims':
                all_sims = read_sims(device_folder)
                for s in all_sims:
                    if s['id'] == device_id:
                        s['has_issue'] = True
                        break
                write_sims(device_folder, all_sims)
            else:
                inv_data = {'devices': read_device_inventory(device_folder, dtype)}
                for dev in inv_data['devices']:
                    if dev['id'] == device_id:
                        dev['has_issue'] = True
                        break
                write_device_inventory(device_folder, dtype, inv_data)
            ev_id = append_device_event(device_folder, dtype, device_id,
                                        event_type='faulty', by=loginid,
                                        notes=d_notes, homer_id=homer_id,
                                        patient_event_id=event_id,
                                        issue_occur_date=issue_occur_date)
            device_results.append({'device_type': dtype, 'device_id': device_id, 'event_id': ev_id})

        complete_entry = {
            **entry,
            'completion_date':      completion_date,
            'issue_occur_date':     issue_occur_date,
            'filed_at':             filed_at,
            'filed_by':   _filer(),
            'call_mode':            call_mode,
            'notes':                notes,
            'devices':              device_results,
            'visit_required':       False,
            'broken_protocol_mode': True,
            'attachment':           None,
            'attachment_caption':   None,
        }
        events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
        existing_odis = events_data.setdefault('free', {}).setdefault('other_device_issue_call', [])
        complete_entry['alias'] = f"ODI{len(existing_odis) + 1:02d}"
        existing_odis.append(complete_entry)
        write_protocol_events(folder, homer_id, events_data)
        write_patient_log(folder, homer_id, loginid, session_id,
                          'Other device issue call recorded (broken protocol).')
        return jsonify({'ok': True})

    visit_required = any(d.get('outcome') == 'visit_required' for d in devices_list)

    # Process each device
    device_results = []
    for d in devices_list:
        dtype     = d.get('device_type')
        device_id = (d.get('device_id') or '').strip()
        outcome   = d.get('outcome')
        d_notes   = (d.get('notes') or '').strip() or None

        if not device_id:
            continue

        if dtype == 'sims':
            all_sims = read_sims(device_folder)
            if outcome == 'visit_required':
                for s in all_sims:
                    if s['id'] == device_id:
                        s['has_issue'] = True
                        break
                write_sims(device_folder, all_sims)
                ev_id = append_device_event(device_folder, dtype, device_id,
                                            event_type='faulty', by=loginid,
                                            notes=d_notes, homer_id=homer_id,
                                            patient_event_id=event_id,
                                            issue_occur_date=issue_occur_date)
            else:  # resolved_over_call
                for s in all_sims:
                    if s['id'] == device_id and s.get('has_issue'):
                        s['has_issue'] = False
                        break
                write_sims(device_folder, all_sims)
                ev_id = append_device_event(device_folder, dtype, device_id,
                                            event_type='repair', by=loginid,
                                            notes=d_notes, homer_id=homer_id,
                                            patient_event_id=event_id,
                                            issue_occur_date=issue_occur_date)
        else:
            inv_data = {'devices': read_device_inventory(device_folder, dtype)}
            if outcome == 'visit_required':
                for dev in inv_data['devices']:
                    if dev['id'] == device_id:
                        dev['has_issue'] = True
                        break
                write_device_inventory(device_folder, dtype, inv_data)
                ev_id = append_device_event(device_folder, dtype, device_id,
                                            event_type='faulty', by=loginid,
                                            notes=d_notes, homer_id=homer_id,
                                            patient_event_id=event_id,
                                            issue_occur_date=issue_occur_date)
            else:  # resolved_over_call
                for dev in inv_data['devices']:
                    if dev['id'] == device_id and dev.get('has_issue'):
                        dev['has_issue'] = False
                        break
                write_device_inventory(device_folder, dtype, inv_data)
                ev_id = append_device_event(device_folder, dtype, device_id,
                                            event_type='repair', by=loginid,
                                            notes=d_notes, homer_id=homer_id,
                                            patient_event_id=event_id,
                                            issue_occur_date=issue_occur_date)
        device_results.append({'device_type': dtype, 'device_id': device_id,
                                'outcome': outcome, 'event_id': ev_id})

    complete_entry = {
        **entry,
        'completion_date':  completion_date,
        'issue_occur_date': issue_occur_date,
        'filed_at':         filed_at,
        'filed_by':   _filer(),
        'call_mode':        call_mode,
        'notes':            notes,
        'devices':          device_results,
        'visit_required':   visit_required,
        'attachment':       None,
        'attachment_caption': None,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    existing_odis = events_data.setdefault('free', {}).setdefault('other_device_issue_call', [])
    complete_entry['alias'] = f"ODI{len(existing_odis) + 1:02d}"
    existing_odis.append(complete_entry)

    if visit_required:
        events_data.setdefault('incomplete', []).append({
            'id':                str(uuid.uuid4()),
            'protocol_event_id': 'other_device_issue_visit',
            'triggered_by':      {'type': 'other_device_issue_call', 'id': event_id},
            'scheduled_date':    [now_hhmm, now_hhmm],
            'filed_at':          filed_at,
            'filed_by':   _filer(),
        })
        write_patient_log(folder, homer_id, loginid, session_id,
                          'Other device issue — engineer visit required.')

    write_protocol_events(folder, homer_id, events_data)
    write_patient_log(folder, homer_id, loginid, session_id, 'Other device issue call recorded.')

    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/complete-event/other-device-issue-visit', methods=['POST'])
def api_complete_other_device_issue_visit(homer_id):
    """Complete an other_device_issue_visit stub: resolve per-device outcomes."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    is_bp = bool(patient.get('brokenProtocolDate')) if patient else False

    body            = request.get_json() or {}
    event_id        = body.get('event_id')
    completion_date = (body.get('completion_date') or '').strip()
    notes           = (body.get('notes') or '').strip() or None
    device_outcomes = body.get('device_outcomes', [])

    if not event_id:
        return jsonify({'error': 'event_id is required.'}), 400
    if not completion_date:
        return jsonify({'error': 'Visit date is required.'}), 400
    if r := _bad_date(patient, completion_date): return r
    try:
        visit_dt = datetime.strptime(completion_date, '%Y-%m-%dT%H:%M')
        if visit_dt > datetime.now():
            return jsonify({'error': 'Visit date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid visit date format.'}), 400
    if not is_bp and (not isinstance(device_outcomes, list) or not device_outcomes):
        return jsonify({'error': 'At least one device outcome is required.'}), 400

    if not is_bp:
        valid_dtypes   = ('modems', 'laptops', 'sims')
        valid_outcomes = ('repaired', 'replaced', 'neither')
        for do in device_outcomes:
            if do.get('device_type') not in valid_dtypes:
                return jsonify({'error': f'device_type must be one of {valid_dtypes}'}), 400
            if do.get('outcome') not in valid_outcomes:
                return jsonify({'error': f'outcome must be repaired, replaced, or neither'}), 400
            if do.get('outcome') == 'replaced' and not do.get('new_device_id'):
                return jsonify({'error': 'new_device_id is required for replaced outcome.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == 'other_device_issue_visit' and e.get('id') == event_id),
        None
    )
    if not entry:
        return jsonify({'error': 'Other device issue visit stub not found.'}), 404

    # Look up issue_occur_date from the triggering other_device_issue_call entry
    call_issue_occur_date = None
    triggered_by = entry.get('triggered_by', {})
    if triggered_by.get('type') == 'other_device_issue_call':
        call_entry = next(
            (e for e in events_data.get('free', {}).get('other_device_issue_call', [])
             if e.get('id') == triggered_by.get('id')),
            None
        )
        if call_entry:
            call_issue_occur_date = call_entry.get('issue_occur_date')

    # Validate visit date is after issue occurred date
    if call_issue_occur_date:
        try:
            issue_dt = _parse_date_flex(call_issue_occur_date)
            if issue_dt and visit_dt.date() < issue_dt.date():
                return jsonify({'error': f'Visit date must be on or after issue occurred date ({call_issue_occur_date}).'}), 400
        except ValueError:
            pass

    device_folder = get_hospital_folder(flask_session['login_place'])

    # ── Broken-protocol mode: fault documentation only ────────────────────────
    if is_bp:
        device_faults = body.get('device_faults', [])
        filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
        session_id = flask_session.get('session_id', -1)
        valid_dtypes = ('modems', 'laptops', 'sims')
        for df in device_faults:
            dtype     = df.get('device_type')
            device_id = df.get('device_id')
            fault_notes = (df.get('notes') or '').strip()
            if dtype not in valid_dtypes or not device_id:
                continue
            inv_data = {'devices': read_device_inventory(device_folder, dtype)}
            for d in inv_data['devices']:
                if d['id'] == device_id:
                    d['has_issue'] = True
                    break
            write_device_inventory(device_folder, dtype, inv_data)
            append_device_event(device_folder, dtype, device_id, 'faulty', loginid,
                                notes=fault_notes or 'Reported faulty (broken protocol fault documentation)',
                                homer_id=homer_id)
        complete_entry = {
            **entry,
            'completion_date':      completion_date,
            'filed_at':             filed_at,
            'filed_by':   _filer(),
            'broken_protocol_mode': True,
            'device_faults':        device_faults,
            'notes':                notes,
        }
        events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
        events_data.setdefault('free', {}).setdefault('other_device_issue_visit', []).append(complete_entry)
        write_protocol_events(folder, homer_id, events_data)
        write_patient_log(folder, homer_id, loginid, session_id,
                          'Other device issue visit recorded (broken protocol — fault documentation only).')
        return jsonify({'ok': True})
    # ─────────────────────────────────────────────────────────────────────────

    loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    session_id = flask_session.get('session_id', -1)
    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm   = datetime.now().strftime('%Y-%m-%dT%H:%M')

    saved_outcomes = []
    for do in device_outcomes:
        dtype      = do.get('device_type')
        device_id  = (do.get('device_id') or '').strip()
        outcome    = do.get('outcome')
        new_dev_id = (do.get('new_device_id') or '').strip() or None
        d_notes    = (do.get('notes') or '').strip() or None

        if not device_id:
            continue

        inv_data = {'devices': read_device_inventory(device_folder, dtype)}

        if outcome == 'repaired':
            # Clear has_issue — device is fixed
            if dtype == 'sims':
                all_sims = read_sims(device_folder)
                for s in all_sims:
                    if s['id'] == device_id:
                        s['has_issue'] = False
                        break
                write_sims(device_folder, all_sims)
            else:
                for dev in inv_data['devices']:
                    if dev['id'] == device_id:
                        dev['has_issue'] = False
                        break
                write_device_inventory(device_folder, dtype, inv_data)
            append_device_event(device_folder, dtype, device_id,
                                event_type='repair', by=loginid,
                                notes=d_notes, homer_id=homer_id,
                                patient_event_id=event_id)

        if outcome == 'replaced' and new_dev_id:
            if dtype == 'sims':
                # SIM replacement: update modem.sim_id to new SIM
                modem_inv = read_device_inventory(device_folder, 'modems')
                for m in modem_inv:
                    if m.get('sim_id') == device_id:
                        m['sim_id'] = new_dev_id
                        m['sim_assigned_date'] = now_hhmm
                        break
                write_device_inventory(device_folder, 'modems', {'devices': modem_inv})
                append_device_event(device_folder, dtype, new_dev_id,
                                    event_type='assign', by=loginid,
                                    notes=f'Replacement for {device_id} (patient {homer_id})',
                                    homer_id=homer_id)
            else:
                # Modem/laptop replacement: close old assignment and create new one
                asgns = read_device_assignments(device_folder, dtype)
                for a in asgns:
                    if a.get('device_id') == device_id and a.get('returned_date') is None:
                        a['returned_date'] = now_hhmm
                        break
                asgns.append({
                    'id':            str(uuid.uuid4()),
                    'device_id':     new_dev_id,
                    'homer_id':      homer_id,
                    'assigned_date': now_hhmm,
                    'returned_date': None,
                })
                write_device_assignments(device_folder, dtype, asgns)
                append_device_event(device_folder, dtype, new_dev_id,
                                    event_type='assign', by=loginid,
                                    notes=f'Replacement for {device_id} (patient {homer_id})',
                                    homer_id=homer_id)

                # For modems: transfer sim_id from old modem to new modem
                if dtype == 'modems':
                    inv_data = {'devices': read_device_inventory(device_folder, 'modems')}
                    old_sim_id = None
                    for m in inv_data['devices']:
                        if m['id'] == device_id and m.get('sim_id'):
                            old_sim_id = m['sim_id']
                            m['sim_id'] = None
                            break
                    if old_sim_id:
                        for m in inv_data['devices']:
                            if m['id'] == new_dev_id:
                                m['sim_id'] = old_sim_id
                                m['sim_assigned_date'] = now_hhmm
                                break
                        write_device_inventory(device_folder, 'modems', inv_data)

        saved_outcomes.append({'device_type': dtype, 'device_id': device_id,
                                'outcome': outcome, 'new_device_id': new_dev_id,
                                'notes': d_notes})

    complete_entry = {
        **entry,
        'completion_date':   completion_date,
        'filed_at':          filed_at,
        'filed_by':   _filer(),
        'notes':             notes,
        'device_outcomes':   saved_outcomes,
        'attachment':        None,
        'attachment_caption': None,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    events_data.setdefault('free', {}).setdefault('other_device_issue_visit', []).append(complete_entry)

    write_protocol_events(folder, homer_id, events_data)
    write_patient_log(folder, homer_id, loginid, session_id, 'Other device issue visit recorded.')

    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/complete-event/robot-issue-visit', methods=['POST'])
def api_complete_robot_issue_visit(homer_id):
    """Complete a robot_issue_visit stub: per-device outcomes, fault reports, optional pause."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient_meta = read_patient_meta(folder, homer_id)
    if patient_meta and patient_meta.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    if not patient_meta or patient_meta.get('group') != 'experimental':
        return jsonify({'error': 'Robot issue visit is only valid for experimental patients.'}), 400

    is_bp = bool(patient_meta.get('brokenProtocolDate'))

    body            = request.get_json() or {}
    event_id        = body.get('event_id')
    completion_date = (body.get('completion_date') or '').strip()
    notes           = (body.get('notes') or '').strip()
    device_outcomes = body.get('device_outcomes', [])

    if not event_id:
        return jsonify({'error': 'event_id is required.'}), 400
    if not completion_date:
        return jsonify({'error': 'Visit date is required.'}), 400
    if r := _bad_date(patient_meta, completion_date): return r
    try:
        visit_dt = datetime.strptime(completion_date, '%Y-%m-%dT%H:%M')
        if visit_dt > datetime.now():
            return jsonify({'error': 'Visit date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid visit date format.'}), 400
    if not is_bp and (not isinstance(device_outcomes, list) or not device_outcomes):
        return jsonify({'error': 'At least one device outcome is required.'}), 400

    if not is_bp:
        valid_devices  = {'pluto', 'mars'}
        valid_outcomes = {'repaired_on_site', 'swapped', 'neither'}
        for do in device_outcomes:
            dev = do.get('device')
            out = do.get('outcome')
            if dev not in valid_devices:
                return jsonify({'error': f'Invalid device: {dev}.'}), 400
            if out not in valid_outcomes:
                return jsonify({'error': f'Invalid outcome for {dev}: {out}.'}), 400
            if out == 'repaired_on_site':
                if not (do.get('notes') or '').strip():
                    return jsonify({'error': f'{dev.capitalize()} repair notes are required.'}), 400
            elif out == 'swapped':
                if do.get('swap_type') not in ('fault_driven', 'preventive'):
                    return jsonify({'error': f'{dev.capitalize()} swap type must be fault_driven or preventive.'}), 400
            elif out == 'neither':
                if not (do.get('notes') or '').strip():
                    return jsonify({'error': f'{dev.capitalize()} notes are required.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == 'robot_issue_visit' and e.get('id') == event_id),
        None
    )
    if not entry:
        return jsonify({'error': 'Robot issue visit stub not found.'}), 404

    # Look up issue_occur_date from the triggering robot_issue_call entry
    call_issue_occur_date = None
    triggered_by = entry.get('triggered_by', {})
    if triggered_by.get('type') == 'robot_issue_call':
        call_entry = next(
            (e for e in events_data.get('free', {}).get('robot_issue_call', [])
             if e.get('id') == triggered_by.get('id')),
            None
        )
        if call_entry:
            call_issue_occur_date = call_entry.get('issue_occur_date')

    # Validate visit date is after issue occurred date
    if call_issue_occur_date:
        try:
            issue_dt = _parse_date_flex(call_issue_occur_date)
            if issue_dt and visit_dt.date() < issue_dt.date():
                return jsonify({'error': f'Visit date must be on or after issue occurred date ({call_issue_occur_date}).'}), 400
        except ValueError:
            pass

    # ── Broken-protocol mode: fault documentation only ────────────────────────
    if is_bp:
        device_faults = body.get('device_faults', [])
        filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        loginid    = flask_session.get('loginid', 'unknown')
        session_id = flask_session.get('session_id', -1)
        for df in device_faults:
            device_type = df.get('device')
            fault_notes = (df.get('notes') or '').strip()
            if device_type not in ('pluto', 'mars'):
                continue
            inv = read_device_inventory(folder, device_type)
            assignments = read_device_assignments(folder, device_type)
            current = next((a for a in assignments if a.get('returned_date') is None), None)
            device_id = current['device_id'] if current else None
            for d in inv:
                if d['id'] == device_id:
                    d['has_issue'] = True
                    break
            write_device_inventory(folder, device_type, {'devices': inv})
            if device_id:
                append_device_event(folder, device_type, device_id, 'faulty', loginid,
                                    notes=fault_notes or 'Reported faulty (broken protocol fault documentation)',
                                    homer_id=homer_id)
        complete_entry = {
            **entry,
            'completion_date':   completion_date,
            'filed_at':          filed_at,
            'filed_by':   _filer(),
            'broken_protocol_mode': True,
            'device_faults':     device_faults,
            'notes':             notes,
        }
        events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
        events_data.setdefault('free', {}).setdefault('robot_issue_visit', []).append(complete_entry)
        write_protocol_events(folder, homer_id, events_data)
        write_patient_log(folder, homer_id, loginid, session_id,
                          'Robot issue visit recorded (broken protocol — fault documentation only).')
        return jsonify({'ok': True})
    # ─────────────────────────────────────────────────────────────────────────

    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm   = datetime.now().strftime('%Y-%m-%dT%H:%M')
    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    saved_outcomes  = []
    any_taken_back  = False

    for do in device_outcomes:
        device_type = do['device']
        outcome     = do['outcome']

        assignments = read_device_assignments(folder, device_type)
        current = next((a for a in assignments if a.get('returned_date') is None), None)
        old_device_id = current['device_id'] if current else None

        new_device_id = None
        swap_type     = None
        out_notes     = None

        if outcome == 'repaired_on_site':
            out_notes = do.get('notes', '').strip()
            if old_device_id:
                append_device_event(folder, device_type, old_device_id, 'faulty', loginid,
                                    notes='Reported faulty during robot issue visit', homer_id=homer_id,
                                    issue_occur_date=call_issue_occur_date)
                append_device_event(folder, device_type, old_device_id, 'repair', loginid,
                                    notes=out_notes or 'Repaired on site during robot issue visit', homer_id=homer_id)

        elif outcome == 'swapped':
            swap_type     = do.get('swap_type')
            out_notes     = (do.get('notes') or '').strip() or None
            new_device_id = do.get('new_device_id') or None

            # Close current assignment
            if old_device_id and current:
                current['returned_date'] = now_hhmm
                write_device_assignments(folder, device_type, assignments)
                if swap_type == 'fault_driven':
                    write_device_log(folder, old_device_id, loginid, session_id,
                                     f'Returned (faulty — robot issue visit) from {homer_id}')
                    mark_device_faulty(folder, device_type, old_device_id)
                    append_device_event(folder, device_type, old_device_id, 'faulty', loginid,
                                        notes=out_notes or 'Marked faulty during robot issue visit', homer_id=homer_id,
                                        issue_occur_date=call_issue_occur_date)
                    # Create pending fault report stub
                    reports = read_fault_reports(folder, device_type)
                    reports.append({
                        'id':         str(uuid.uuid4()),
                        'device_id':  old_device_id,
                        'homer_id':   homer_id,
                        'event_id':   event_id,
                        'swap_type':  'fault_driven',
                        'notes':      out_notes,
                        'filed_by':   _filer(),
                        'filed_at':   filed_at,
                        'resolution': None,
                    })
                    write_fault_reports(folder, device_type, reports)
                else:  # preventive
                    write_device_log(folder, old_device_id, loginid, session_id,
                                     f'Returned (preventive swap — robot issue visit) from {homer_id}')

            if new_device_id:
                # Assign replacement device
                assignments = read_device_assignments(folder, device_type)
                assignments.append({
                    'id':            str(uuid.uuid4()),
                    'device_id':     new_device_id,
                    'homer_id':      homer_id,
                    'assigned_date': now_hhmm,
                    'returned_date': None,
                    'assigned_by':   loginid,
                    'notes':         'Assigned after robot issue visit (swap)',
                })
                write_device_assignments(folder, device_type, assignments)
                write_device_log(folder, new_device_id, loginid, session_id,
                                 f'Assigned to {homer_id} after robot issue visit (swap)')
                append_device_event(folder, device_type, new_device_id, 'assign', loginid,
                                    notes=f'Replacement for {old_device_id} (patient {homer_id})',
                                    homer_id=homer_id)
            else:
                # No replacement — training pause required
                any_taken_back = True

        else:  # neither
            out_notes = do.get('notes', '').strip()

        saved_outcomes.append({
            'device':        device_type,
            'outcome':       outcome,
            'old_device_id': old_device_id,
            'new_device_id': new_device_id,
            'swap_type':     swap_type,
            'notes':         out_notes,
        })

    complete_entry = {
        **entry,
        'completion_date': completion_date,
        'filed_at':        filed_at,
        'filed_by':   _filer(),
        'device_outcomes': saved_outcomes,
        'notes':           notes,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    events_data.setdefault('free', {}).setdefault('robot_issue_visit', []).append(complete_entry)

    if any_taken_back:
        pause_history = patient_meta.setdefault('pauseHistory', [])
        new_reason = {'type': 'robot_issue', 'event_id': event_id}
        open_epoch = next((e for e in pause_history if e.get('end') is None), None)
        if not patient_meta.get('trainingPausedDate'):
            patient_meta['trainingPausedDate'] = completion_date
            pause_history.append({'start': completion_date, 'end': None, 'days': None, 'reasons': [new_reason]})
        elif open_epoch:
            open_epoch['reasons'].append(new_reason)
        write_patient_meta(folder, homer_id, patient_meta)
        events_data.setdefault('incomplete', []).append({
            'id':                str(uuid.uuid4()),
            'protocol_event_id': 'resolve_robot_issue_visit',
            'triggered_by':      {'type': 'robot_issue_visit', 'id': event_id},
            'scheduled_date':    [now_hhmm, now_hhmm],
            'filed_at':          filed_at,
            'filed_by':   _filer(),
        })
        write_patient_log(folder, homer_id, loginid, session_id,
                          'Training paused — robot issue (device taken back without replacement).')

    write_protocol_events(folder, homer_id, events_data)
    write_patient_log(folder, homer_id, loginid, session_id, 'Robot issue visit recorded.')

    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/complete-event/resolve-robot-issue-visit', methods=['POST'])
def api_complete_resolve_robot_issue_visit(homer_id):
    """Complete a resolve_robot_issue_visit stub: assign replacement devices, clear pause when all resolved."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    is_bp = bool(patient.get('brokenProtocolDate')) if patient else False

    body                  = request.get_json() or {}
    event_id              = body.get('event_id')
    completion_date       = (body.get('completion_date') or '').strip()
    can_resume_from       = (body.get('can_resume_from') or '').strip()
    notes                 = (body.get('notes') or '').strip()
    device_replacements   = body.get('device_replacements', [])
    other_device_outcomes = body.get('other_device_outcomes', [])

    if not event_id:
        return jsonify({'error': 'event_id is required.'}), 400
    if not completion_date:
        return jsonify({'error': 'Visit date is required.'}), 400
    if r := _bad_date(patient, completion_date): return r
    try:
        visit_dt = datetime.strptime(completion_date, '%Y-%m-%dT%H:%M')
        if visit_dt > datetime.now():
            return jsonify({'error': 'Visit date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid visit date format.'}), 400
    if not is_bp:
        if not can_resume_from:
            return jsonify({'error': 'Can resume from date is required.'}), 400
        try:
            resume_date = date.fromisoformat(can_resume_from)
            if resume_date > date.today():
                return jsonify({'error': 'Can resume from date cannot be in the future.'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid can_resume_from date format.'}), 400

        valid_devices  = {'pluto', 'mars'}
        valid_outcomes = {'repaired_on_site', 'swapped', 'neither'}
        for da in device_replacements:
            if da.get('device') not in valid_devices:
                return jsonify({'error': f'Invalid device: {da.get("device")}.'}), 400
            if not da.get('new_device_id') and not (da.get('notes') or '').strip():
                dev = da.get('device', 'device').capitalize()
                return jsonify({'error': f'Notes are required when no replacement {dev} is available.'}), 400
        for do in other_device_outcomes:
            dev = do.get('device')
            out = do.get('outcome')
            if dev not in valid_devices:
                return jsonify({'error': f'Invalid device: {dev}.'}), 400
            if out not in valid_outcomes:
                return jsonify({'error': f'Invalid outcome for {dev}: {out}.'}), 400
            if out == 'repaired_on_site':
                if not (do.get('notes') or '').strip():
                    return jsonify({'error': f'{dev.capitalize()} repair notes are required.'}), 400
            elif out == 'swapped':
                if do.get('swap_type') not in ('fault_driven', 'preventive'):
                    return jsonify({'error': f'{dev.capitalize()} swap type must be fault_driven or preventive.'}), 400
            elif out == 'neither':
                if not (do.get('notes') or '').strip():
                    return jsonify({'error': f'{dev.capitalize()} notes are required.'}), 400

    patient_meta = read_patient_meta(folder, homer_id)
    if not patient_meta or patient_meta.get('group') != 'experimental':
        return jsonify({'error': 'Resolve robot issue visit is only valid for experimental patients.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == 'resolve_robot_issue_visit' and e.get('id') == event_id),
        None
    )
    if not entry:
        return jsonify({'error': 'Resolve robot issue visit stub not found.'}), 404

    # Trace back through robot_issue_visit → robot_issue_call to get issue_occur_date
    call_issue_occur_date = None
    _tb = entry.get('triggered_by', {})
    if _tb.get('type') == 'robot_issue_visit':
        _visit_entry = next(
            (e for e in events_data.get('free', {}).get('robot_issue_visit', [])
             if e.get('id') == _tb.get('id')),
            None
        )
        if _visit_entry:
            _tb2 = _visit_entry.get('triggered_by', {})
            if _tb2.get('type') == 'robot_issue_call':
                _call_entry = next(
                    (e for e in events_data.get('free', {}).get('robot_issue_call', [])
                     if e.get('id') == _tb2.get('id')),
                    None
                )
                if _call_entry:
                    call_issue_occur_date = _call_entry.get('issue_occur_date')

    # Validate visit date is after issue occurred date
    if call_issue_occur_date:
        try:
            issue_dt = datetime.strptime(call_issue_occur_date, '%Y-%m-%d')
            if visit_dt.date() < issue_dt.date():
                return jsonify({'error': f'Visit date must be on or after issue occurred date ({call_issue_occur_date}).'}), 400
        except ValueError:
            pass

    # ── Broken-protocol mode: fault documentation only ────────────────────────
    if is_bp:
        device_faults = body.get('device_faults', [])
        filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        loginid    = flask_session.get('loginid', 'unknown')
        session_id = flask_session.get('session_id', -1)
        for df in device_faults:
            device_type = df.get('device')
            fault_notes = (df.get('notes') or '').strip()
            if device_type not in ('pluto', 'mars'):
                continue
            # The device was taken back — no current assignment; we have device_id from df
            device_id = df.get('device_id')
            if device_id:
                inv = read_device_inventory(folder, device_type)
                for d in inv:
                    if d['id'] == device_id:
                        d['has_issue'] = True
                        break
                write_device_inventory(folder, device_type, {'devices': inv})
                append_device_event(folder, device_type, device_id, 'faulty', loginid,
                                    notes=fault_notes or 'Reported faulty (broken protocol fault documentation)',
                                    homer_id=homer_id)
        complete_entry = {
            **entry,
            'completion_date':      completion_date,
            'filed_at':             filed_at,
            'filed_by':   _filer(),
            'broken_protocol_mode': True,
            'device_faults':        device_faults,
            'notes':                notes,
        }
        events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
        events_data.setdefault('free', {}).setdefault('resolve_robot_issue_visit', []).append(complete_entry)
        write_protocol_events(folder, homer_id, events_data)
        write_patient_log(folder, homer_id, loginid, session_id,
                          'Robot issue visit recorded (broken protocol — fault documentation only).')
        return jsonify({'ok': True})
    # ─────────────────────────────────────────────────────────────────────────

    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm   = datetime.now().strftime('%Y-%m-%dT%H:%M')
    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)

    saved_replacements = []
    any_still_missing  = False

    for da in device_replacements:
        device_type   = da['device']
        old_device_id = da.get('old_device_id')
        new_device_id = da.get('new_device_id') or None
        da_notes      = (da.get('notes') or '').strip() or None

        if new_device_id:
            assignments = read_device_assignments(folder, device_type)
            assignments.append({
                'id':            str(uuid.uuid4()),
                'device_id':     new_device_id,
                'homer_id':      homer_id,
                'assigned_date': now_hhmm,
                'returned_date': None,
                'assigned_by':   loginid,
                'notes':         'Assigned after resolve robot issue visit',
            })
            write_device_assignments(folder, device_type, assignments)
            write_device_log(folder, new_device_id, loginid, session_id,
                             f'Assigned to {homer_id} after resolve robot issue visit')
            append_device_event(folder, device_type, new_device_id, 'assign', loginid,
                                notes=f'Replacement for {old_device_id} (patient {homer_id})',
                                homer_id=homer_id)
        else:
            any_still_missing = True

        saved_replacements.append({
            'device':        device_type,
            'old_device_id': old_device_id,
            'new_device_id': new_device_id,
            'notes':         da_notes,
        })

    # Process other device outcomes (same logic as robot_issue_visit)
    saved_other_outcomes = []
    for do in other_device_outcomes:
        device_type   = do['device']
        outcome       = do['outcome']
        swap_type     = do.get('swap_type')
        out_notes     = (do.get('notes') or '').strip() or None
        new_device_id = do.get('new_device_id') or None

        assignments = read_device_assignments(folder, device_type)
        current = next((a for a in assignments if a.get('returned_date') is None), None)
        old_device_id = current['device_id'] if current else None

        if outcome == 'repaired_on_site':
            if old_device_id:
                append_device_event(folder, device_type, old_device_id, 'faulty', loginid,
                                    notes='Reported faulty during resolve robot issue visit', homer_id=homer_id,
                                    issue_occur_date=call_issue_occur_date)
                append_device_event(folder, device_type, old_device_id, 'repair', loginid,
                                    notes=out_notes or 'Repaired on site during resolve robot issue visit', homer_id=homer_id)

        elif outcome == 'swapped':
            if old_device_id and current:
                current['returned_date'] = now_hhmm
                write_device_assignments(folder, device_type, assignments)
                if swap_type == 'fault_driven':
                    write_device_log(folder, old_device_id, loginid, session_id,
                                     f'Returned (faulty — resolve robot issue visit) from {homer_id}')
                    mark_device_faulty(folder, device_type, old_device_id)
                    append_device_event(folder, device_type, old_device_id, 'faulty', loginid,
                                        notes=out_notes or 'Marked faulty during resolve robot issue visit', homer_id=homer_id,
                                        issue_occur_date=call_issue_occur_date)
                    reports = read_fault_reports(folder, device_type)
                    reports.append({
                        'id':         str(uuid.uuid4()),
                        'device_id':  old_device_id,
                        'homer_id':   homer_id,
                        'event_id':   event_id,
                        'swap_type':  'fault_driven',
                        'notes':      out_notes,
                        'filed_by':   _filer(),
                        'filed_at':   filed_at,
                        'resolution': None,
                    })
                    write_fault_reports(folder, device_type, reports)
                else:
                    write_device_log(folder, old_device_id, loginid, session_id,
                                     f'Returned (preventive swap — resolve robot issue visit) from {homer_id}')
            if new_device_id:
                assignments = read_device_assignments(folder, device_type)
                assignments.append({
                    'id':            str(uuid.uuid4()),
                    'device_id':     new_device_id,
                    'homer_id':      homer_id,
                    'assigned_date': now_hhmm,
                    'returned_date': None,
                    'assigned_by':   loginid,
                    'notes':         'Assigned after resolve robot issue visit (other device swap)',
                })
                write_device_assignments(folder, device_type, assignments)
                write_device_log(folder, new_device_id, loginid, session_id,
                                 f'Assigned to {homer_id} after resolve robot issue visit (other device swap)')
                append_device_event(folder, device_type, new_device_id, 'assign', loginid,
                                    notes=f'Replacement for {old_device_id} (patient {homer_id})',
                                    homer_id=homer_id)

        saved_other_outcomes.append({
            'device':        device_type,
            'outcome':       outcome,
            'old_device_id': old_device_id,
            'new_device_id': new_device_id,
            'swap_type':     swap_type,
            'notes':         out_notes,
        })

    complete_entry = {
        **entry,
        'completion_date':      completion_date,
        'filed_at':             filed_at,
        'filed_by':   _filer(),
        'can_resume_from':      can_resume_from,
        'device_replacements':  saved_replacements,
        'other_device_outcomes': saved_other_outcomes,
        'notes':                notes,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    events_data.setdefault('free', {}).setdefault('resolve_robot_issue_visit', []).append(complete_entry)

    if any_still_missing:
        # Some devices still have no replacement — create another stub
        events_data.setdefault('incomplete', []).append({
            'id':                str(uuid.uuid4()),
            'protocol_event_id': 'resolve_robot_issue_visit',
            'triggered_by':      {'type': 'resolve_robot_issue_visit', 'id': event_id},
            'scheduled_date':    [now_hhmm, now_hhmm],
            'filed_at':          filed_at,
            'filed_by':   _filer(),
        })

    # Check if all pause causes are now resolved
    remaining_rriv = [e for e in events_data.get('incomplete', [])
                      if e.get('protocol_event_id') == 'resolve_robot_issue_visit']
    remaining_aef  = [e for e in events_data.get('incomplete', [])
                      if e.get('protocol_event_id') == 'adverse_event_followup']

    if patient_meta.get('trainingPausedDate') and not remaining_rriv and not remaining_aef:
        training_paused = datetime.fromisoformat(patient_meta['trainingPausedDate']).date()

        resume_dates = [resume_date]
        for rriv in events_data.get('free', {}).get('resolve_robot_issue_visit', []):
            try:
                resume_dates.append(date.fromisoformat(rriv['can_resume_from']))
            except (ValueError, KeyError):
                pass
        free_aes = {ae['id']: ae for ae in events_data.get('free', {}).get('adverse_event', [])}
        for aef in events_data.get('free', {}).get('adverse_event_followup', []):
            for r in aef.get('ae_discussions', []):
                ae = free_aes.get(r.get('adverse_event_id'), {})
                if r.get('resolved') and ae.get('training_blocked') and r.get('can_resume_from'):
                    try:
                        resume_dates.append(date.fromisoformat(r['can_resume_from']))
                    except ValueError:
                        pass

        max_resume = max(resume_dates)
        pause_days = max(0, (max_resume - training_paused).days)
        patient_meta['cumulativePauseDays'] = (patient_meta.get('cumulativePauseDays') or 0) + pause_days
        # Close the open pauseHistory epoch
        end_dt = filed_at[:16]
        open_epoch = next((e for e in patient_meta.get('pauseHistory', []) if e.get('end') is None), None)
        if open_epoch:
            open_epoch['end']          = end_dt
            open_epoch['days']         = pause_days
            open_epoch['end_event_id'] = event_id
        patient_meta['trainingPausedDate']  = None
        if (patient_meta.get('cumulativePauseDays') or 0) > 10:
            if not patient_meta.get('brokenProtocolDate'):
                patient_meta['brokenProtocolDate'] = filed_at[:10]
        if _check_d0203_broken_protocol(events_data, max_resume):
            if not patient_meta.get('brokenProtocolDate'):
                patient_meta['brokenProtocolDate'] = filed_at[:10]
        if patient_meta.get('brokenProtocolDate'):
            _cancel_training_ended_stubs(events_data, ['watch_record'], filed_at)
        _shift_future_incomplete_events(events_data, pause_days)
        write_patient_meta(folder, homer_id, patient_meta)
        write_patient_log(folder, homer_id, loginid, session_id,
                          'Robot issue resolved — replacement device assigned.')

    write_protocol_events(folder, homer_id, events_data)
    write_patient_log(folder, homer_id, loginid, session_id, 'Robot issue resolved — replacement visit recorded.')

    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/complete-event/followup-call', methods=['POST'])
def api_complete_followup_call(homer_id):
    """Complete a follow-up call event with duration, training log PDF, and notes."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    body               = request.get_json() or {}
    event_id           = body.get('event_id')
    protocol_event_id  = (body.get('protocol_event_id') or '').strip()
    completion_date    = (body.get('completion_date') or '').strip()
    duration_str       = str(body.get('duration_minutes', '')).strip()
    call_mode          = (body.get('call_mode') or '').strip()
    notes              = (body.get('notes') or '').strip()
    date_change_reason = (body.get('date_change_reason') or '').strip()
    triggered_items    = body.get('triggered', [])
    no_issue           = bool(body.get('no_issue', False))
    if not isinstance(triggered_items, list):
        triggered_items = []

    if protocol_event_id not in _FOLLOWUP_CALL_IDS:
        return jsonify({'error': 'Invalid protocol event ID.'}), 400
    if not completion_date:
        return jsonify({'error': 'Call date is required.'}), 400
    # Load events_data up-front so the per-event Date Rule Framework lookup can
    # resolve `event:home_visit_d03` (for D07) and `event:followup_call_d07`
    # (for D21). The same handle is reused later for the actual mutation.
    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404
    if r := _bad_date(patient, completion_date,
                      event_id=protocol_event_id, events_data=events_data): return r
    if r := _bad_call_mode(call_mode):              return r
    if r := _bad_outcome(no_issue, triggered_items): return r
    try:
        if datetime.strptime(completion_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'Call date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400
    if not duration_str:
        return jsonify({'error': 'Duration is required.'}), 400
    try:
        duration_minutes = int(duration_str)
        if duration_minutes <= 0:
            raise ValueError
    except ValueError:
        return jsonify({'error': 'Duration must be a positive integer.'}), 400
    if not notes:
        return jsonify({'error': 'Notes are required.'}), 400

    # Validate triggered items (stubs only — no detail fields required at trigger time)
    patient_meta    = read_patient_meta(folder, homer_id)
    is_experimental = patient_meta and patient_meta.get('group') == 'experimental'
    for item in triggered_items:
        t = item.get('type')
        if t == 'adverse_event':
            pass
        elif t == 'robot_issue_call':
            if not is_experimental:
                return jsonify({'error': 'Robot issue call is only valid for experimental patients.'}), 400
        elif t == 'watch_record':
            pass
        elif t == 'other_device_issue_call':
            if not is_experimental:
                return jsonify({'error': 'Other device issue call is only valid for experimental patients.'}), 400
        else:
            return jsonify({'error': f"Unknown triggered type: {t}"}), 400

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == protocol_event_id
         and (event_id is None or e.get('id') == event_id)),
        None
    )
    if not entry:
        return jsonify({'error': 'Event not found in incomplete list.'}), 404

    call_id  = entry['id']
    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm = datetime.now().strftime('%Y-%m-%dT%H:%M')

    # Process triggered items — create stubs in incomplete
    triggered_refs = []
    for item in triggered_items:
        t = item.get('type')
        if t == 'adverse_event':
            new_id = str(uuid.uuid4())
            events_data.setdefault('incomplete', []).append({
                'id':               new_id,
                'protocol_event_id': 'adverse_event',
                'triggered_by':     {'type': protocol_event_id, 'id': call_id},
                'scheduled_date':   [now_hhmm, now_hhmm],
                'filed_at':         filed_at,
                'filed_by':   _filer(),
            })
            triggered_refs.append({'type': 'adverse_event', 'id': new_id})

        elif t == 'robot_issue_call':
            new_id = str(uuid.uuid4())
            events_data.setdefault('incomplete', []).append({
                'id':               new_id,
                'protocol_event_id': 'robot_issue_call',
                'triggered_by':     {'type': protocol_event_id, 'id': call_id},
                'scheduled_date':   [now_hhmm, now_hhmm],
                'filed_at':         filed_at,
                'filed_by':   _filer(),
            })
            triggered_refs.append({'type': 'robot_issue_call', 'id': new_id})

        elif t == 'other_device_issue_call':
            new_id = str(uuid.uuid4())
            events_data.setdefault('incomplete', []).append({
                'id':               new_id,
                'protocol_event_id': 'other_device_issue_call',
                'triggered_by':     {'type': protocol_event_id, 'id': call_id},
                'scheduled_date':   [now_hhmm, now_hhmm],
                'filed_at':         filed_at,
                'filed_by':   _filer(),
            })
            triggered_refs.append({'type': 'other_device_issue_call', 'id': new_id})

        elif t == 'watch_record':
            # Stamp triggered_by and scheduled_date onto the existing open chain entry
            wr = next(
                (e for e in events_data.get('incomplete', [])
                 if e.get('protocol_event_id') == 'watch_record'),
                None
            )
            if wr:
                wr['triggered_by']   = {'type': protocol_event_id, 'id': call_id}
                wr['scheduled_date'] = [now_hhmm, now_hhmm]
                triggered_refs.append({'type': 'watch_record', 'id': wr['id']})

    complete_entry = {
        **entry,
        'alias':            _next_call_alias(events_data),
        'completion_date':  completion_date,
        'filed_at':         filed_at,
        'filed_by':   _filer(),
        'duration_minutes': duration_minutes,
        'call_mode':        call_mode,
        'no_issue':         no_issue,
        'notes':            notes,
        'triggered':        triggered_refs,
        **({'date_change_reason': date_change_reason} if date_change_reason else {}),
    }

    events_data['incomplete'] = [e for e in incomplete if e.get('id') != entry['id']]
    events_data.setdefault('complete', []).append(complete_entry)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)
    day        = '07' if protocol_event_id == 'followup_call_d07' else '21'
    write_patient_log(folder, homer_id, loginid, session_id,
                      f'Follow-up call recorded — Day {day}')
    for ref in triggered_refs:
        msg = {'adverse_event': 'Adverse event recorded',
               'robot_issue_call': 'Robot issue call logged',
               'watch_record':  'Watch record triggered'}.get(ref['type'])
        if msg:
            write_patient_log(folder, homer_id, loginid, session_id, msg)

    return jsonify({'ok': True})


# ── Watch Record endpoint ──────────────────────────────────────────────────────

@bp.route('/api/patients/<homer_id>/complete-event/watch-record', methods=['POST'])
def api_complete_watch_record(homer_id):
    """Complete a watch_record event: assign watches, seed next chain entry."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    data               = request.get_json() or {}
    event_id           = data.get('event_id')
    ag_right_new       = data.get('ag_watch_right_new')   # str or None
    ag_left_new        = data.get('ag_watch_left_new')    # str or None
    right_old_lost     = bool(data.get('ag_watch_right_old_lost', False))
    left_old_lost      = bool(data.get('ag_watch_left_old_lost', False))
    sync_datetime      = (data.get('sync_datetime') or '').strip()
    worn_datetime      = (data.get('worn_datetime') or '').strip()
    next_followup_days = data.get('next_followup_days')
    notes              = (data.get('notes') or '').strip()

    if not event_id:
        return jsonify({'error': 'event_id is required'}), 400

    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    old_right    = patient.get('agWatchRightID')
    old_left     = patient.get('agWatchLeftID')
    two_watches  = bool(old_right and old_left)
    both_current = two_watches and ag_right_new == old_right and ag_left_new == old_left
    sync_required = two_watches and not both_current
    worn_required = not both_current

    if ag_right_new and ag_left_new and ag_right_new == ag_left_new:
        return jsonify({'error': 'Right and left watches must be different'}), 400
    if sync_required and not sync_datetime:
        return jsonify({'error': 'Sync date & time is required when watches are changed'}), 400
    if worn_required and not worn_datetime:
        return jsonify({'error': 'Worn date & time is required'}), 400
    right_no_watch = old_right is not None and ag_right_new is None
    left_no_watch  = old_left  is not None and ag_left_new  is None
    if (right_no_watch or left_no_watch) and not notes:
        return jsonify({'error': 'Notes are required when a watch is not assigned'}), 400
    if not isinstance(next_followup_days, int) or next_followup_days < 1:
        return jsonify({'error': 'next_followup_days must be a positive integer'}), 400
    for dt_val, label in ((sync_datetime, 'Sync'), (worn_datetime, 'Worn')):
        if not dt_val:
            continue
        try:
            if datetime.strptime(dt_val, '%Y-%m-%dT%H:%M') > datetime.now():
                return jsonify({'error': f'{label} date cannot be in the future'}), 400
        except ValueError:
            return jsonify({'error': f'{label} date format must be YYYY-MM-DDTHH:MM'}), 400
    if r := _bad_date(patient, sync_datetime): return r
    if r := _bad_date(patient, worn_datetime): return r

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found'}), 404

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('id') == event_id and e.get('protocol_event_id') == 'watch_record'),
        None
    )
    if not entry:
        return jsonify({'error': 'Watch record not found in incomplete'}), 404
    filed_at        = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    completion_date = worn_datetime or sync_datetime or filed_at[:16]

    complete_entry = {
        **entry,
        'alias':              _next_wr_alias(events_data),
        'completion_date':    completion_date,
        'filed_at':           filed_at,
        'filed_by':   _filer(),
        'ag_watch_right':     {'old_id': old_right, 'old_lost': right_old_lost, 'new_id': ag_right_new},
        'ag_watch_left':      {'old_id': old_left,  'old_lost': left_old_lost,  'new_id': ag_left_new},
        'sync_datetime':      sync_datetime,
        'worn_datetime':      worn_datetime,
        'next_followup_days': next_followup_days,
        'notes':              notes,
    }

    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    events_data.setdefault('complete', []).append(complete_entry)

    # Read agwatch assignments once — used both to seed data-upload tasks (for the
    # removed watch's assignment window) and for the assignment mutation loop below.
    assignments = read_device_assignments(folder, 'agwatch')

    # Seed a watch_data_upload task for each removed, recoverable (non-lost) watch.
    # A watch is "removed" when it had an old id that differs from the new id (a swap,
    # or a removal to a gap with new_id null). Lost watches are skipped — there is no
    # physical device to pull data from. The engineer uploads the raw .gt3x later.
    wdu_refs = []
    for old_id, old_lost, new_id, limb in (
        (old_right, right_old_lost, ag_right_new, 'right'),
        (old_left,  left_old_lost,  ag_left_new,  'left'),
    ):
        if old_id and old_id != new_id and not old_lost:
            assigned_date = next(
                (a.get('assigned_date') for a in assignments
                 if a.get('device_id') == old_id and a.get('homer_id') == homer_id
                 and a.get('returned_date') is None),
                None
            )
            wdu_id = str(uuid.uuid4())
            events_data.setdefault('incomplete', []).append({
                'id':                wdu_id,
                'protocol_event_id': 'watch_data_upload',
                'triggered_by':      {'type': 'watch_record', 'id': event_id},
                'watch_id':          old_id,
                'limb':              limb,
                'removed_date':      completion_date,
                'data_start':        assigned_date,
                'data_end':          completion_date,
                'scheduled_date':    [completion_date, completion_date],
                'filed_at':          filed_at,
                'filed_by':          _filer(),
            })
            wdu_refs.append({'type': 'watch_data_upload', 'id': wdu_id})
    if wdu_refs:
        complete_entry['triggered'] = wdu_refs

    # Seed next chain entry only if training has not permanently ended
    _training_ended = bool(
        patient.get('trainingCompletionDate') or
        patient.get('brokenProtocolDate') or
        patient.get('discontinuationDate')
    )
    if not _training_ended and patient.get('activationDate'):
        try:
            _act = datetime.fromisoformat(patient['activationDate']).date()
            _training_ended = date.today() > _act + timedelta(days=28)
        except Exception:
            pass
    if not _training_ended:
        next_dt = (datetime.fromisoformat(completion_date) + timedelta(days=next_followup_days)).strftime('%Y-%m-%dT%H:%M')
        events_data['incomplete'].append({
            'id':                str(uuid.uuid4()),
            'protocol_event_id': 'watch_record',
            'scheduled_date':    [next_dt, next_dt],
            'flagged':           False,
            'notes':             '',
        })
    write_protocol_events(folder, homer_id, events_data)

    # Update patient meta
    patient['agWatchRightID'] = ag_right_new
    patient['agWatchLeftID']  = ag_left_new
    write_patient_meta(folder, homer_id, patient)

    # Update device assignments: close old open assignment, open new
    # (assignments already read above for data-upload seeding)
    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)
    lost_date_str = completion_date[:10]
    for old_id, old_lost, new_id, limb in (
        (old_right, right_old_lost, ag_right_new, 'right'),
        (old_left,  left_old_lost,  ag_left_new,  'left'),
    ):
        if old_id and old_id != new_id:
            for a in assignments:
                if a.get('device_id') == old_id and a.get('homer_id') == homer_id and a.get('returned_date') is None:
                    a['returned_date'] = completion_date
                    if old_lost:
                        a['lost'] = True
            if old_lost:
                mark_device_lost(folder, 'agwatch', old_id, lost_date_str)
                write_device_log(folder, old_id, loginid, session_id, f'Lost — reported by {homer_id}')
                append_device_event(folder, 'agwatch', old_id, 'lost', loginid,
                                    homer_id=homer_id, notes=f'Lost — reported by {homer_id}')
            else:
                append_device_event(folder, 'agwatch', old_id, 'available', loginid,
                                    homer_id=homer_id, notes=f'Returned by {homer_id}')
        if new_id and new_id != old_id:
            assignments.append({
                'id':            str(uuid.uuid4()),
                'device_id':     new_id,
                'homer_id':      homer_id,
                'limb':          limb,
                'assigned_date': completion_date,
                'returned_date': None,
                'lost':          False,
                'assigned_by':   loginid,
                'notes':         notes,
            })
            write_device_log(folder, new_id, loginid, session_id, f'Assigned to {homer_id} ({limb})')
            append_device_event(folder, 'agwatch', new_id, 'assign', loginid,
                                homer_id=homer_id, notes=f'Assigned ({limb})')
    write_device_assignments(folder, 'agwatch', assignments)

    write_patient_log(folder, homer_id, loginid, session_id, 'Watch record filed')
    return jsonify({'status': 'success'})


# ── AG Watch Data Upload ───────────────────────────────────────────────────────

def _save_watch_data_file(folder: str, homer_id: str, rel_path: str, file_obj) -> None:
    """Persist an uploaded .gt3x (S3 or local) at <patient>/<rel_path>."""
    if Config.USE_S3:
        from utils.s3_store import s3_upload_file
        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(delete=False, suffix='.gt3x') as tmp:
            file_obj.save(tmp.name)
            tmp_path = tmp.name
        try:
            s3_upload_file(tmp_path, f"{folder}/patients/{homer_id}/{rel_path}",
                           content_type='application/octet-stream')
        finally:
            _os.unlink(tmp_path)
    else:
        dest = get_patients_path(folder) / homer_id / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        file_obj.save(str(dest))


def _watch_data_staged(folder: str, homer_id: str, event_id: str) -> bool:
    """True if a staged .gt3x exists for this event (uploaded but not yet completed)."""
    rel = f'actigraphs/{event_id}.gt3x'
    if Config.USE_S3:
        from utils.s3_store import s3_key_exists
        return s3_key_exists(f"{folder}/patients/{homer_id}/{rel}")
    return (get_patients_path(folder) / homer_id / rel).exists()


@bp.route('/api/patients/<homer_id>/upload-watch-data', methods=['POST'])
def api_upload_watch_data(homer_id):
    """Stage a raw .gt3x for a watch_data_upload task (step 1 of 2).

    Fires the moment a file is chosen so the client can show an upload progress bar
    and gate the Save button. Stores to actigraphs/<event_id>.gt3x (idempotent — a
    re-selected file overwrites). The event is completed separately (JSON call).
    """
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    event_id  = (request.form.get('event_id') or '').strip()
    data_file = request.files.get('file')
    if not event_id:
        return jsonify({'error': 'event_id is required'}), 400
    if not data_file or not data_file.filename:
        return jsonify({'error': 'No file provided'}), 400
    if not data_file.filename.lower().endswith('.gt3x'):
        return jsonify({'error': 'Data file must be a .gt3x file.'}), 400

    # Guard: only allow writes for an actual open watch_data_upload stub.
    events_data = read_protocol_events(folder, homer_id)
    stub = next(
        (e for e in (events_data or {}).get('incomplete', [])
         if e.get('id') == event_id and e.get('protocol_event_id') == 'watch_data_upload'),
        None
    )
    if not stub:
        return jsonify({'error': 'Watch data upload task not found in incomplete'}), 404

    _save_watch_data_file(folder, homer_id, f'actigraphs/{event_id}.gt3x', data_file)
    return jsonify({'ok': True, 'original_filename': data_file.filename})


@bp.route('/api/patients/<homer_id>/complete-event/watch-data-upload', methods=['POST'])
def api_complete_watch_data_upload(homer_id):
    """Complete a watch_data_upload task (step 2 of 2): record metadata, or skip.

    JSON request (the .gt3x was already staged via /upload-watch-data). Engineer/admin
    only. Deliberately NOT blocked when the patient is discontinued — watch data must
    remain uploadable.
    """
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    data              = request.get_json() or {}
    event_id          = (data.get('event_id') or '').strip()
    skipped           = bool(data.get('skipped'))
    notes             = (data.get('notes') or '').strip()
    original_filename = (data.get('original_filename') or '').strip() or None

    if not event_id:
        return jsonify({'error': 'event_id is required'}), 400

    if skipped:
        if not notes:
            return jsonify({'error': 'A detailed reason is required when the upload is skipped.'}), 400
    else:
        if not _watch_data_staged(folder, homer_id, event_id):
            return jsonify({'error': 'Please upload the data file before saving.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found'}), 404
    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('id') == event_id and e.get('protocol_event_id') == 'watch_data_upload'),
        None
    )
    if not entry:
        return jsonify({'error': 'Watch data upload task not found in incomplete'}), 404

    filed_at        = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    completion_date = filed_at[:16]   # htDash upload/completion time — no engineer-entered date
    data_file_rel   = f'actigraphs/{event_id}.gt3x'
    if skipped:
        original_filename = None
        data_file_rel     = None
        # Best-effort cleanup of any staged file the engineer uploaded then abandoned (local only).
        if not Config.USE_S3:
            try:
                (get_patients_path(folder) / homer_id / f'actigraphs/{event_id}.gt3x').unlink(missing_ok=True)
            except Exception:
                pass

    complete_entry = {
        **entry,
        'completion_date':   completion_date,
        'filed_at':          filed_at,
        'filed_by':          _filer(),
        'data_file':         data_file_rel,
        'original_filename': original_filename,
        'skipped':           bool(skipped),
        'notes':             notes,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != event_id]
    events_data.setdefault('free', {}).setdefault('watch_data_upload', []).append(complete_entry)
    write_protocol_events(folder, homer_id, events_data)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)
    log_msg    = 'AG watch data upload skipped' if skipped else 'AG watch data uploaded'
    watch_id   = entry.get('watch_id')
    if watch_id:
        write_device_log(folder, watch_id, loginid, session_id, f'{log_msg} ({homer_id})')
    write_patient_log(folder, homer_id, loginid, session_id, log_msg)
    return jsonify({'status': 'success'})


@bp.route('/api/patients/<homer_id>/watch-data/<event_id>', methods=['GET'])
def api_download_watch_data(homer_id, event_id):
    """Download the uploaded .gt3x for a watch_data_upload event.

    Exception to the admin/therapist-only attachment rule: engineers may download
    raw watch data, so admin, therapist, and engineer are all permitted.
    """
    from flask import send_file
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege', '') not in ('admin', 'therapist', 'engineer'):
        return jsonify({'error': 'Forbidden'}), 403
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    events_data = read_protocol_events(folder, homer_id)
    entry = None
    if events_data:
        for e in events_data.get('free', {}).get('watch_data_upload', []):
            if e.get('id') == event_id:
                entry = e
                break
    if not entry or not entry.get('data_file'):
        return jsonify({'error': 'Data file not found'}), 404

    rel           = entry['data_file']
    download_name = entry.get('original_filename') or f'{event_id}.gt3x'
    if Config.USE_S3:
        from utils.s3_store import s3_get_bytes
        import io
        data = s3_get_bytes(f"{folder}/patients/{homer_id}/{rel}")
        if data is None:
            return jsonify({'error': 'Data file not found'}), 404
        return send_file(io.BytesIO(data), mimetype='application/octet-stream',
                         as_attachment=True, download_name=download_name)
    path = get_patients_path(folder) / homer_id / rel
    if not path.exists():
        return jsonify({'error': 'Data file not found'}), 404
    return send_file(str(path), mimetype='application/octet-stream',
                     as_attachment=True, download_name=download_name)


# ── AG Watch Timing endpoints ──────────────────────────────────────────────────

_AE_FOLLOWUP_LABELS = {
    'adverse_event_followup':        'Follow-up Call',
    'adverse_event_followup_visit':  'Follow-up Visit',
    'adverse_event_clinical_visit':  'Clinical Visit',
}

_AGWATCH_TIMING_CONFIG = {
    'agwatch_timing_d01': {
        'timing_file':        'agwatch_timing_d01.json',
        'session_source':     'activation',
        'adl_prescription':   'adl_prescription_d01',
        'vcg_prescription':   'vcg_prescription_d01',
    },
    'agwatch_timing_d02': {
        'timing_file':        'agwatch_timing_d02.json',
        'session_source':     'home_visit_d02',
        'adl_prescription':   'adl_prescription_d01',
        'vcg_prescription':   'vcg_prescription_d01',
    },
    'agwatch_timing_d03': {
        'timing_file':        'agwatch_timing_d03.json',
        'session_source':     'home_visit_d03',
        'adl_prescription':   'adl_prescription_d01',
        'vcg_prescription':   'vcg_prescription_d01',
    },
    'agwatch_timing_d15': {
        'timing_file':        'agwatch_timing_d15.json',
        'session_source':     'home_visit_d15',
        'adl_prescription':   'adl_prescription_d15',
        'vcg_prescription':   'vcg_prescription_d15',
    },
}


@bp.route('/api/patients/<homer_id>/agwatch-timing-exercises/<protocol_event_id>', methods=['GET'])
def api_agwatch_timing_exercises(homer_id, protocol_event_id):
    """Return VCG (control only) + ADL exercise lists for a combined agwatch timing event."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    cfg = _AGWATCH_TIMING_CONFIG.get(protocol_event_id)
    if not cfg:
        return jsonify({'error': 'Unknown agwatch timing event'}), 400

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    patient   = read_patient_meta(folder, homer_id) or {}
    group     = patient.get('group', '')
    vcg_group = patient.get('vcgGroup', '')
    ex_data   = _load_exercises()

    # Session window from the associated home visit / activation
    events_data = read_protocol_events(folder, homer_id)
    session_source = cfg['session_source']
    hv_entry = next(
        (e for e in (events_data or {}).get('complete', []) if e.get('protocol_event_id') == session_source),
        None
    )
    session_start = hv_entry.get('session_start') if hv_entry else None
    session_end   = hv_entry.get('session_end')   if hv_entry else None

    exercises = []

    # VCG exercises — control group only
    if group == 'control':
        vcg_presc_path = _PRESCRIPTION_FILES.get(cfg['vcg_prescription'])
        vcg_presc      = _read_prescription(folder, homer_id, vcg_presc_path) if vcg_presc_path else None
        if vcg_presc:
            vcg_lookup = {e['id']: e['name']
                          for e in ex_data.get('vcg', {}).get(vcg_group, {}).get('exercises', [])}
            for ex in vcg_presc.get('prescribed_exercises', []):
                exercises.append({
                    'exercise_id': ex['exercise_id'],
                    'type':        'vcg',
                    'name':        vcg_lookup.get(ex['exercise_id'], ex['exercise_id']),
                    'blocks':      ex.get('blocks'),
                    'repetitions': ex.get('repetitions'),
                })

    # ADL exercises — both groups
    adl_presc_path = _PRESCRIPTION_FILES.get(cfg['adl_prescription'])
    adl_presc      = _read_prescription(folder, homer_id, adl_presc_path) if adl_presc_path else None
    if adl_presc:
        adl_lookup = {e['id']: e['name'] for e in ex_data.get('adl', {}).get('exercises', [])}
        for ex in adl_presc.get('prescribed_exercises', []):
            exercises.append({
                'exercise_id': ex['exercise_id'],
                'type':        'adl',
                'name':        adl_lookup.get(ex['exercise_id'], ex['exercise_id']),
                'blocks':      ex.get('blocks'),
                'repetitions': ex.get('repetitions'),
            })

    if not exercises:
        return jsonify({'error': 'No prescriptions found — complete the ADL prescription first'}), 404

    return jsonify({
        'exercises':     exercises,
        'session_start': session_start,
        'session_end':   session_end,
    })


@bp.route('/api/patients/<homer_id>/complete-event/agwatch-timing', methods=['POST'])
def api_complete_agwatch_timing(homer_id):
    """Record agwatch timing data and mark the event complete."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    patient = read_patient_meta(folder, homer_id)
    if patient and patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    data              = request.get_json() or {}
    event_id          = data.get('event_id')
    protocol_event_id = data.get('protocol_event_id', '').strip()
    timings           = data.get('timings', [])
    notes             = data.get('notes', '').strip()

    cfg = _AGWATCH_TIMING_CONFIG.get(protocol_event_id)
    if not cfg:
        return jsonify({'error': 'Unknown agwatch timing event'}), 400

    # Validate: if start or end is absent/null, per-entry notes are required
    for i, t in enumerate(timings):
        start = (t.get('start') or '').strip()
        end   = (t.get('end')   or '').strip()
        if not start or not end:
            if not (t.get('notes') or '').strip():
                return jsonify({'error': f'Notes are required for exercise {i + 1} when timing is incomplete.'}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    # Hard validation: timings must fall within the home visit session window
    session_source = cfg.get('session_source')
    if session_source:
        hv_entry = next(
            (e for e in events_data.get('complete', []) if e.get('protocol_event_id') == session_source),
            None
        )
        if hv_entry:
            ses_start_str = hv_entry.get('session_start', '')
            ses_end_str   = hv_entry.get('session_end', '')
            if ses_start_str and ses_end_str:
                try:
                    ses_start = datetime.strptime(ses_start_str, '%Y-%m-%dT%H:%M')
                    ses_end   = datetime.strptime(ses_end_str,   '%Y-%m-%dT%H:%M')
                    for i, t in enumerate(timings):
                        t_start = (t.get('start') or '').strip()
                        t_end   = (t.get('end')   or '').strip()
                        if t_start:
                            try:
                                ts = datetime.strptime(t_start[:16], '%Y-%m-%dT%H:%M')
                                if ts < ses_start:
                                    return jsonify({'error': f'Exercise {i + 1}: start time is before the session start ({ses_start_str.split("T")[1]}).'}), 400
                            except ValueError:
                                pass
                        if t_end:
                            try:
                                te = datetime.strptime(t_end[:16], '%Y-%m-%dT%H:%M')
                                if te > ses_end:
                                    return jsonify({'error': f'Exercise {i + 1}: end time is after the session end ({ses_end_str.split("T")[1]}).'}), 400
                            except ValueError:
                                pass
                except ValueError:
                    pass

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e.get('protocol_event_id') == protocol_event_id
         and (event_id is None or e.get('id') == event_id)),
        None
    )
    if not entry:
        return jsonify({'error': 'Event not found in incomplete list.'}), 404

    # Write the timing file
    timing_rel = cfg['timing_file']
    filed_at  = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    loginid   = flask_session.get('loginid', 'unknown')
    timing_content = {
        'filed_at':  filed_at,
        'filed_by':  loginid,
        'timings':   [
            {
                'exercise_id': t.get('exercise_id'),
                'start':       (t.get('start') or '').strip() or None,
                'end':         (t.get('end')   or '').strip() or None,
                'notes':       (t.get('notes') or '').strip(),
            }
            for t in timings
        ],
        'notes': notes,
    }
    if Config.USE_S3:
        from utils.s3_store import s3_write_json
        s3_write_json(f"{folder}/patients/{homer_id}/{timing_rel}", timing_content)
    else:
        timing_path = get_patients_path(folder) / homer_id / timing_rel
        timing_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = timing_path.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(timing_content, f, indent=2)
        os.replace(tmp, timing_path)

    # Mark event complete
    complete_entry = {
        **entry,
        'completion_date': filed_at,
        'filed_at':        filed_at,
        'filed_by':   _filer(),
        'timing_file':     timing_rel,
    }
    events_data['incomplete'] = [e for e in incomplete if e.get('id') != entry['id']]
    events_data.setdefault('complete', []).append(complete_entry)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    session_id = flask_session.get('session_id', -1)
    day_label  = protocol_event_id.split('_')[-1]  # d01, d02, d03, d15
    write_patient_log(folder, homer_id, loginid, session_id,
                      f'AG watch timings recorded ({day_label})')

    return jsonify({'ok': True})


# ── Attachment upload / download ───────────────────────────────────────────────

@bp.route('/api/patients/<homer_id>/upload-attachment', methods=['POST'])
def api_upload_attachment(homer_id):
    """Upload a PDF attachment for a completed protocol event."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    privilege = flask_session.get('privilege', '')
    if privilege not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    event_id = (request.form.get('event_id') or '').strip()
    caption  = (request.form.get('caption')  or '').strip()
    pdf_file = request.files.get('file')

    if not event_id:
        return jsonify({'error': 'event_id is required'}), 400
    if not pdf_file or not pdf_file.filename:
        return jsonify({'error': 'No file provided'}), 400
    if not pdf_file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'Attachment must be a PDF file'}), 400
    if not caption:
        return jsonify({'error': 'Caption is required'}), 400

    # Find event — search complete list first, then all free arrays
    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found'}), 404

    entry = next(
        (e for e in events_data.get('complete', []) if e.get('id') == event_id),
        None
    )
    if not entry:
        for val in events_data.get('free', {}).values():
            if isinstance(val, list):
                entry = next((e for e in val if e.get('id') == event_id), None)
                if entry:
                    break
    if not entry:
        return jsonify({'error': 'Event not found'}), 404
    
    # Use predefined filename based on protocol_event_id
    protocol_event_id = entry.get('protocol_event_id', '')
    pdf_path_mapping = _PRINTOUT_PDF_FILES.get(protocol_event_id, 'prescription_attachment.pdf')

#     # Save PDF as attachments/<event_id>.pdf
#     #save file name using predeifned
#     attachment_path = get_patients_path(folder) / homer_id / pdf_path_mapping
#     attachment_path.parent.mkdir(parents=True, exist_ok=True)
#     pdf_file.save(str(attachment_path))
    
   ##js
    attachment_rel = pdf_path_mapping  # e.g., "attachments/prescription_d01.pdf"
    if Config.USE_S3:
        from utils.s3_store import s3_upload_file
        import tempfile, os as _os
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            pdf_file.save(tmp.name)
            tmp_path = tmp.name
        try:
            s3_upload_file(tmp_path, f"{folder}/patients/{homer_id}/{attachment_rel}",
                           content_type='application/pdf')
        finally:
            _os.unlink(tmp_path)
    else:
        attachment_path = get_patients_path(folder) / homer_id / attachment_rel
        attachment_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_file.save(str(attachment_path))

  
    friendly_filename = pdf_path_mapping.split('/')[-1] if '/' in pdf_path_mapping else pdf_path_mapping

    # Stamp fields on the entry
    entry['attachment']         = pdf_path_mapping
    entry['attachment_caption'] = caption

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/download-attachment/<event_id>', methods=['GET'])
def api_download_attachment(homer_id, event_id):
    """Download the PDF attachment for a completed protocol event."""
    from flask import send_file
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    privilege = flask_session.get('privilege', '')
    if privilege not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Look up the actual attachment path stored on the event
    events_data = read_protocol_events(folder, homer_id)
    attachment_rel = None
    if events_data:
        entry = next((e for e in events_data.get('complete', []) if e.get('id') == event_id), None)
        if not entry:
            for val in events_data.get('free', {}).values():
                if isinstance(val, list):
                    entry = next((e for e in val if e.get('id') == event_id), None)
                    if entry:
                        break
        if entry:
            attachment_rel = entry.get('attachment')
    # Fall back to legacy path
    if not attachment_rel:
        attachment_rel = f'attachments/{event_id}.pdf'

    if Config.USE_S3:
        from utils.s3_store import s3_get_bytes
        import io
        key = f"{folder}/patients/{homer_id}/{attachment_rel}"
        data = s3_get_bytes(key)
        if data is None:
            return jsonify({'error': 'Attachment not found'}), 404
        import posixpath
        filename = posixpath.basename(attachment_rel)
        return send_file(
            io.BytesIO(data),
            mimetype='application/pdf',
            as_attachment=False,
            download_name=filename,
        )

    attachment_path = get_patients_path(folder) / homer_id / attachment_rel
    if not attachment_path.exists():
        return jsonify({'error': 'Attachment not found'}), 404

    # Get the friendly filename from protocol_event_id
    events_data = read_protocol_events(folder, homer_id)
    friendly_name = 'prescription_attachment.pdf'  # Default fallback

    if events_data:
        # Search in complete events
        for entry in events_data.get('complete', []):
            if entry.get('id') == event_id:
                protocol_event_id = entry.get('protocol_event_id', '')
                friendly_name = _PRINTOUT_PDF_FILES.get(protocol_event_id, 'prescription_attachment.pdf')
                break
        # Search in free events if not found
        if friendly_name == 'prescription_attachment.pdf':
            for val in events_data.get('free', {}).values():
                if isinstance(val, list):
                    for entry in val:
                        if entry.get('id') == event_id:
                            protocol_event_id = entry.get('protocol_event_id', '')
                            friendly_name = _PRINTOUT_PDF_FILES.get(protocol_event_id, 'prescription_attachment.pdf')
                            break

    # Read the PDF file
    with open(str(attachment_path), 'rb') as f:
        pdf_data = f.read()

    # Create response with the PDF data
    from flask import make_response
    response = make_response(pdf_data)

    # Set headers explicitly for maximum compatibility
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Length'] = len(pdf_data)
    # RFC 6266 format: attachment; filename="filename.pdf"
    response.headers['Content-Disposition'] = f'attachment; filename="{friendly_name}"'

    # Also set cache control to prevent caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'

    return response


@bp.route('/api/patients/<homer_id>/log-patient-call', methods=['POST'])
def api_log_patient_call(homer_id):
    """Append a patient call to free.patient_call and process triggered events."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    body             = request.get_json() or {}
    completion_date  = (body.get('completion_date') or '').strip()
    duration_str     = str(body.get('duration_minutes', '')).strip()
    notes            = (body.get('notes') or '').strip()
    call_type        = (body.get('call_type') or 'patient_initiated').strip()
    call_mode        = (body.get('call_mode') or '').strip()
    reason           = (body.get('reason') or '').strip()
    triggered_items  = body.get('triggered', [])
    no_issue         = bool(body.get('no_issue', False))
    if not isinstance(triggered_items, list):
        triggered_items = []

    if r := _bad_call_mode(call_mode): return r
    if r := _bad_outcome(no_issue, triggered_items): return r

    if not completion_date:
        return jsonify({'error': 'Call date is required.'}), 400
    try:
        if datetime.strptime(completion_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'Call date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400
    if not duration_str:
        return jsonify({'error': 'Duration is required.'}), 400
    try:
        duration_minutes = int(duration_str)
        if duration_minutes <= 0:
            raise ValueError
    except ValueError:
        return jsonify({'error': 'Duration must be a positive integer.'}), 400
    if not notes:
        return jsonify({'error': 'Notes are required.'}), 400
    if call_type not in ('patient_initiated', 'therapist_initiated'):
        return jsonify({'error': 'Invalid call_type.'}), 400
    if call_type == 'therapist_initiated' and not reason:
        return jsonify({'error': 'Reason is required for therapist-initiated calls.'}), 400

    patient_meta    = read_patient_meta(folder, homer_id)
    is_experimental = patient_meta and patient_meta.get('group') == 'experimental'

    # Validate triggered items (stubs only — no detail fields required at trigger time)
    for item in triggered_items:
        t = item.get('type')
        if t == 'adverse_event':
            pass
        elif t == 'robot_issue_call':
            if not is_experimental:
                return jsonify({'error': 'Robot issue call is only valid for experimental patients.'}), 400
        elif t == 'watch_record':
            pass
        elif t == 'other_device_issue_call':
            if not is_experimental:
                return jsonify({'error': 'Other device issue call is only valid for experimental patients.'}), 400
        else:
            return jsonify({'error': f"Unknown triggered type: {t}"}), 400

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    call_id  = str(uuid.uuid4())
    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    now_hhmm = datetime.now().strftime('%Y-%m-%dT%H:%M')

    # Process triggered items — create stubs in incomplete
    triggered_refs = []
    for item in triggered_items:
        t = item.get('type')
        if t == 'adverse_event':
            new_id = str(uuid.uuid4())
            events_data.setdefault('incomplete', []).append({
                'id':               new_id,
                'protocol_event_id': 'adverse_event',
                'triggered_by':     {'type': 'patient_call', 'id': call_id},
                'scheduled_date':   [now_hhmm, now_hhmm],
                'filed_at':         filed_at,
                'filed_by':   _filer(),
            })
            triggered_refs.append({'type': 'adverse_event', 'id': new_id})

        elif t == 'robot_issue_call':
            new_id = str(uuid.uuid4())
            events_data.setdefault('incomplete', []).append({
                'id':               new_id,
                'protocol_event_id': 'robot_issue_call',
                'triggered_by':     {'type': 'patient_call', 'id': call_id},
                'scheduled_date':   [now_hhmm, now_hhmm],
                'filed_at':         filed_at,
                'filed_by':   _filer(),
            })
            triggered_refs.append({'type': 'robot_issue_call', 'id': new_id})

        elif t == 'other_device_issue_call':
            new_id = str(uuid.uuid4())
            events_data.setdefault('incomplete', []).append({
                'id':               new_id,
                'protocol_event_id': 'other_device_issue_call',
                'triggered_by':     {'type': 'patient_call', 'id': call_id},
                'scheduled_date':   [now_hhmm, now_hhmm],
                'filed_at':         filed_at,
                'filed_by':   _filer(),
            })
            triggered_refs.append({'type': 'other_device_issue_call', 'id': new_id})

        elif t == 'watch_record':
            wr = next(
                (e for e in events_data.get('incomplete', [])
                 if e.get('protocol_event_id') == 'watch_record'),
                None
            )
            if wr:
                wr['triggered_by']   = {'type': 'patient_call', 'id': call_id}
                wr['scheduled_date'] = [now_hhmm, now_hhmm]
                triggered_refs.append({'type': 'watch_record', 'id': wr['id']})

    events_data['free'].setdefault('patient_call', []).append({
        'id':               call_id,
        'alias':            _next_call_alias(events_data),
        'completion_date':  completion_date,
        'filed_at':         filed_at,
        'filed_by':   _filer(),
        'duration_minutes': duration_minutes,
        'call_type':        call_type,
        'call_mode':        call_mode,
        'reason':           reason if call_type == 'therapist_initiated' else None,
        'no_issue':         no_issue,
        'notes':            notes,
        'triggered':        triggered_refs,
    })

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)
    write_patient_log(folder, homer_id, loginid, session_id, 'Patient call recorded')
    for ref in triggered_refs:
        msg = {'adverse_event': 'Adverse event recorded',
               'robot_issue_call': 'Robot issue call logged',
               'watch_record':  'Watch record triggered'}.get(ref['type'])
        if msg:
            write_patient_log(folder, homer_id, loginid, session_id, msg)

    return jsonify({'ok': True, 'id': call_id})


@bp.route('/api/patients/<homer_id>/call-logs', methods=['GET'])
def api_call_logs(homer_id):
    """Return all call records: scheduled follow-up calls + free patient calls."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    protocol    = load_study_protocol()
    patient     = read_patient_meta(folder, homer_id)
    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'followup_calls': [], 'patient_calls': [], 'ae_followup_calls': []})

    event_defs = {}
    for e in protocol.get('shared', []):
        event_defs[e['id']] = e
    for e in protocol.get((patient or {}).get('group', ''), []):
        event_defs[e['id']] = e

    FOLLOWUP_IDS = {'followup_call_d07', 'followup_call_d21'}
    followup_calls = []
    for entry in events_data.get('complete', []):
        pid = entry.get('protocol_event_id', '')
        if pid in FOLLOWUP_IDS:
            item = dict(entry)
            item['event_name'] = event_defs.get(pid, {}).get('name', pid)
            followup_calls.append(item)
    followup_calls.sort(key=lambda x: x.get('completion_date') or '', reverse=True)

    patient_calls = list(events_data.get('free', {}).get('patient_call', []))
    patient_calls.sort(key=lambda x: x.get('completion_date') or '', reverse=True)

    # Look up AE aliases so the client can render a "Re: AE02, AE05" line on
    # each AE follow-up call card without having to walk the AE list itself.
    ae_alias_by_id = {ae.get('id'): ae.get('alias')
                      for ae in events_data.get('free', {}).get('adverse_event', [])
                      if ae.get('id')}
    ae_followup_calls = []
    for entry in events_data.get('free', {}).get('adverse_event_followup', []):
        item = dict(entry)
        item['ae_aliases'] = [ae_alias_by_id.get(_id) for _id in (entry.get('adverse_event_ids') or [])
                              if ae_alias_by_id.get(_id)]
        ae_followup_calls.append(item)
    ae_followup_calls.sort(key=lambda x: x.get('completion_date') or '', reverse=True)

    # Same role-filtered count + strip pattern used by api_patient_events so the
    # Call Logs card surface lights up its note-count badge on first render
    # without exposing per-bucket note content.
    _priv = flask_session.get('privilege', '')
    _apply_event_notes_count(followup_calls,    _priv)
    _apply_event_notes_count(patient_calls,     _priv)
    _apply_event_notes_count(ae_followup_calls, _priv)

    return jsonify({
        'followup_calls':     followup_calls,
        'patient_calls':      patient_calls,
        'ae_followup_calls':  ae_followup_calls,
    })


@bp.route('/api/patients/<homer_id>/complete-training', methods=['POST'])
def api_complete_training(homer_id):
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') != 'admin':
        return jsonify({'error': 'Forbidden'}), 403
    data = request.get_json() or {}
    training_date = (data.get('trainingCompletionDate') or '').strip()
    if not training_date:
        return jsonify({'error': 'trainingCompletionDate is required'}), 400
    try:
        if datetime.strptime(training_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'trainingCompletionDate cannot be in the future'}), 400
    except ValueError:
        return jsonify({'error': 'trainingCompletionDate format must be YYYY-MM-DDTHH:MM'}), 400
    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400
    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404

    # Check if patient is discontinued
    if patient.get('discontinuationDate'):
        return jsonify({'error': 'Patient is discontinued. No further changes are allowed.'}), 403

    if derive_status(patient) != 'active':
        return jsonify({'error': 'Patient must be active to complete training'}), 409
    patient['trainingCompletionDate'] = training_date
    write_patient_meta(folder, homer_id, patient)
    try:
        write_patient_log(folder, homer_id, flask_session.get('loginid', 'unknown'),
                          flask_session.get('session_id', 0), 'Training completed')
    except Exception as e:
        print(f'Warning: could not write patient log: {e}')
    return jsonify({'status': 'success', 'homerID': homer_id})


@bp.route('/api/patients/<homer_id>/complete-event/a1-assessment', methods=['POST'])
def api_complete_a1_assessment(homer_id):
    """Complete the a1_assessment protocol event."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    body          = request.get_json() or {}
    event_id      = (body.get('event_id') or '').strip()
    a1_date       = (body.get('completion_date') or '').strip()
    notes         = (body.get('notes') or '').strip()
    oow_reason    = (body.get('out_of_window_reason') or '').strip()

    if not a1_date:
        return jsonify({'error': 'Assessment date is required.'}), 400
    try:
        if datetime.strptime(a1_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'Assessment date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400

    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404
    # Per-event hard bound: not_before activationDate + 29d. The framework
    # needs events_data to resolve event:<id> references (not needed here for
    # A1, but kept for consistency with A2's event:a1_assessment rule).
    if r := _bad_date(patient, a1_date, event_id='a1_assessment', events_data=events_data): return r
    # Out-of-ideal-window reason gate: when the assessment date falls outside
    # the protocol-defined ideal window, the reason field is required. Same
    # contract as on the client (see saveA1Assessment).
    if _outside_assessment_window(patient, 'a1_assessment', a1_date) and not oow_reason:
        return jsonify({'error': 'Reason is required when the A1 date is outside the ideal window.'}), 400
    status = derive_status(patient)
    if status not in ('training_completed', 'broken_protocol', 'discontinued', 'post_training'):
        return jsonify({'error': 'Patient must have completed training to record A1 assessment.'}), 409

    entry = next(
        (e for e in events_data.get('incomplete', [])
         if e.get('protocol_event_id') == 'a1_assessment'
         and (not event_id or e.get('id') == event_id)),
        None
    )
    if not entry:
        return jsonify({'error': 'A1 assessment event not found in incomplete list.'}), 404

    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    complete_entry = {**entry, 'completion_date': a1_date, 'filed_at': filed_at, 'filed_by': _filer(), 'notes': notes}
    if oow_reason:
        complete_entry['out_of_window_reason'] = oow_reason
    # Remove the assessment entry and any orphaned schedule-call stubs.
    events_data['incomplete'] = [
        e for e in events_data['incomplete']
        if e.get('id') != entry['id']
        and e.get('protocol_event_id') != 'schedule_a1_call'
    ]
    events_data.setdefault('complete', []).append(complete_entry)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    patient['a1CompletionDate'] = a1_date
    write_patient_meta(folder, homer_id, patient)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', 0)
    write_patient_log(folder, homer_id, loginid, session_id, 'A1 assessment recorded')
    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/complete-event/a2-assessment', methods=['POST'])
def api_complete_a2_assessment(homer_id):
    """Complete the a2_assessment protocol event."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    body         = request.get_json() or {}
    event_id     = (body.get('event_id') or '').strip()
    a2_date      = (body.get('completion_date') or '').strip()
    notes        = (body.get('notes') or '').strip()
    oow_reason   = (body.get('out_of_window_reason') or '').strip()
    a1_miss_gap  = body.get('a1_miss_gap_seconds')

    if not a2_date:
        return jsonify({'error': 'Assessment date is required.'}), 400
    try:
        if datetime.strptime(a2_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'Assessment date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid date format.'}), 400

    patient = read_patient_meta(folder, homer_id)
    if not patient:
        return jsonify({'error': 'Patient not found'}), 404
    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404
    # Per-event hard bound: not_before event:a1_assessment. The token resolves
    # to None until A1 is filed, so this rule effectively only blocks A2 from
    # being earlier than A1 once A1 is completed (the auto-miss-A1 flow writes
    # A1 missed without a completion_date, so this rule does not block it).
    if r := _bad_date(patient, a2_date, event_id='a2_assessment', events_data=events_data): return r
    if _outside_assessment_window(patient, 'a2_assessment', a2_date) and not oow_reason:
        return jsonify({'error': 'Reason is required when the A2 date is outside the ideal window.'}), 400
    status = derive_status(patient)
    if status not in ('training_completed', 'broken_protocol', 'discontinued', 'post_training', 'a1_completed'):
        return jsonify({'error': 'Patient must have completed training to record A2 assessment.'}), 409

    entry = next(
        (e for e in events_data.get('incomplete', [])
         if e.get('protocol_event_id') == 'a2_assessment'
         and (not event_id or e.get('id') == event_id)),
        None
    )
    if not entry:
        return jsonify({'error': 'A2 assessment event not found in incomplete list.'}), 404

    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    complete_entry = {**entry, 'completion_date': a2_date, 'filed_at': filed_at, 'filed_by': _filer(), 'notes': notes}
    if oow_reason:
        complete_entry['out_of_window_reason'] = oow_reason

    # Auto-miss A1 if still incomplete.
    a1_entry = next(
        (e for e in events_data.get('incomplete', [])
         if e.get('protocol_event_id') == 'a1_assessment'),
        None
    )
    if a1_entry:
        # Back-date A1 by the OK-press gap so it sorts before A2 (no fixed offset). A2 stays
        # server-authoritative; only the gap is client-measured, so this is skew-immune.
        try:
            _gap = max(0.0, float(a1_miss_gap)) if a1_miss_gap is not None else 0.0
        except (TypeError, ValueError):
            _gap = 0.0
        a1_filed_at = (datetime.strptime(filed_at, '%Y-%m-%dT%H:%M:%S') - timedelta(seconds=_gap)).strftime('%Y-%m-%dT%H:%M:%S')
        a1_missed = {**a1_entry, 'missed': True, 'missed_at': a1_filed_at[:16], 'filed_at': a1_filed_at, 'filed_by': _filer()}
        patient['a1MissedDate'] = a1_filed_at

    # Remove A2, A1 (if being auto-missed), and any orphaned schedule-call stubs.
    events_data['incomplete'] = [
        e for e in events_data['incomplete']
        if e.get('id') != entry['id']
        and e.get('protocol_event_id') not in ('schedule_a2_call', 'schedule_a1_call')
        and (not a1_entry or e.get('id') != a1_entry['id'])
    ]
    events_data.setdefault('complete', []).append(complete_entry)
    if a1_entry:
        events_data['complete'].append(a1_missed)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    patient['a2CompletionDate'] = a2_date
    write_patient_meta(folder, homer_id, patient)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', 0)
    write_patient_log(folder, homer_id, loginid, session_id, 'A2 assessment recorded')
    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/complete-event/miss-assessment', methods=['POST'])
def api_miss_assessment(homer_id):
    """Mark an a1_assessment or a2_assessment as missed (patient confirmed non-attendance)."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    body            = request.get_json() or {}
    assessment_type = (body.get('assessment_type') or '').strip()
    event_id        = (body.get('event_id') or '').strip()
    a1_miss_gap     = body.get('a1_miss_gap_seconds')

    if assessment_type not in ('a1', 'a2'):
        return jsonify({'error': 'assessment_type must be a1 or a2'}), 400

    pid = f'{assessment_type}_assessment'
    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    stub = next(
        (e for e in events_data.get('incomplete', [])
         if e.get('protocol_event_id') == pid
         and (not event_id or e.get('id') == event_id)),
        None
    )
    if not stub:
        return jsonify({'error': f'{pid} not found in incomplete.'}), 404

    filed_at  = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    missed_at = filed_at[:16]

    complete_entry = {**stub, 'missed': True, 'missed_at': missed_at, 'filed_at': filed_at, 'filed_by': _filer()}

    # When marking A2 as missed, auto-miss A1 if still incomplete.
    a1_auto_missed = None
    if assessment_type == 'a2':
        a1_stub = next(
            (e for e in events_data.get('incomplete', [])
             if e.get('protocol_event_id') == 'a1_assessment'),
            None
        )
        if a1_stub:
            # Back-date A1 by the OK-press gap so it sorts before A2 (no fixed offset).
            try:
                _gap = max(0.0, float(a1_miss_gap)) if a1_miss_gap is not None else 0.0
            except (TypeError, ValueError):
                _gap = 0.0
            a1_filed_at = (datetime.strptime(filed_at, '%Y-%m-%dT%H:%M:%S') - timedelta(seconds=_gap)).strftime('%Y-%m-%dT%H:%M:%S')
            a1_auto_missed = {**a1_stub, 'missed': True, 'missed_at': a1_filed_at[:16], 'filed_at': a1_filed_at, 'filed_by': _filer()}

    events_data['incomplete'] = [
        e for e in events_data['incomplete']
        if e.get('id') != stub['id']
        and e.get('protocol_event_id') != f'schedule_{assessment_type}_call'
        and (not a1_auto_missed or e.get('id') != a1_auto_missed['id'])
    ]
    if a1_auto_missed:
        events_data['incomplete'] = [
            e for e in events_data['incomplete']
            if e.get('protocol_event_id') != 'schedule_a1_call'
        ]
    events_data.setdefault('complete', []).append(complete_entry)
    if a1_auto_missed:
        events_data['complete'].append(a1_auto_missed)

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    patient = read_patient_meta(folder, homer_id)
    if patient:
        patient[f'{assessment_type}MissedDate'] = missed_at
        if a1_auto_missed:
            patient['a1MissedDate'] = a1_auto_missed['filed_at']
        write_patient_meta(folder, homer_id, patient)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', 0)
    write_patient_log(folder, homer_id, loginid, session_id,
                      f'{assessment_type.upper()} assessment marked as missed')
    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/cancel-assessment-appointment', methods=['POST'])
def api_cancel_assessment_appointment(homer_id):
    """Cancel a scheduled a1_assessment or a2_assessment appointment.

    Appends to appointment_cancellations on the stub and resets appointment_date to null.
    The auto-seeding in api_patient_events will then create the scheduling call stub.
    """
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    body            = request.get_json() or {}
    assessment_type = (body.get('assessment_type') or '').strip()
    event_id        = (body.get('event_id') or '').strip()
    reason          = (body.get('reason') or '').strip()

    if assessment_type not in ('a1', 'a2'):
        return jsonify({'error': 'assessment_type must be a1 or a2'}), 400
    if not reason:
        return jsonify({'error': 'Cancellation reason is required.'}), 400

    pid = f'{assessment_type}_assessment'
    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    stub = next(
        (e for e in events_data.get('incomplete', [])
         if e.get('protocol_event_id') == pid
         and (not event_id or e.get('id') == event_id)),
        None
    )
    if not stub:
        return jsonify({'error': f'{pid} not found in incomplete.'}), 404

    appt_date = stub.get('appointment_date')
    if not appt_date:
        return jsonify({'error': 'No scheduled appointment to cancel.'}), 400

    stub.setdefault('appointment_cancellations', []).append({
        'cancelled_at':    datetime.now().strftime('%Y-%m-%dT%H:%M'),
        'appointment_date': appt_date,
        'reason':          reason,
    })
    stub['appointment_date'] = None

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', 0)
    write_patient_log(folder, homer_id, loginid, session_id,
                      f'{assessment_type.upper()} assessment appointment cancelled')
    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/complete-event/schedule-assessment-call', methods=['POST'])
def api_complete_schedule_assessment_call(homer_id):
    """Complete a schedule_a1_call or schedule_a2_call stub, update assessment appointment_date."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    body             = request.get_json() or {}
    event_id         = (body.get('event_id') or '').strip()
    call_type        = (body.get('call_type') or '').strip()
    completion_date  = (body.get('completion_date') or '').strip()
    duration_minutes = body.get('duration_minutes')
    notes            = (body.get('notes') or '').strip()
    new_appt_date    = (body.get('new_appointment_date') or '').strip()

    if call_type not in ('schedule_a1_call', 'schedule_a2_call'):
        return jsonify({'error': 'Invalid call_type.'}), 400
    assessment_id = 'a1_assessment' if call_type == 'schedule_a1_call' else 'a2_assessment'

    if not completion_date:
        return jsonify({'error': 'Call date is required.'}), 400
    if r := _bad_date(read_patient_meta(folder, homer_id), completion_date): return r
    try:
        if datetime.strptime(completion_date, '%Y-%m-%dT%H:%M') > datetime.now():
            return jsonify({'error': 'Call date cannot be in the future.'}), 400
    except ValueError:
        return jsonify({'error': 'Invalid call date format.'}), 400

    try:
        duration_minutes = int(duration_minutes)
        if duration_minutes <= 0:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'Duration must be a positive integer.'}), 400

    if not notes:
        return jsonify({'error': 'Notes are required.'}), 400
    if not new_appt_date:
        return jsonify({'error': 'New appointment date is required.'}), 400
    try:
        datetime.strptime(new_appt_date, '%Y-%m-%d')
    except ValueError:
        return jsonify({'error': 'Invalid appointment date format (YYYY-MM-DD required).'}), 400

    # Validate appointment date falls within the assessment window.
    _pt = read_patient_meta(folder, homer_id)
    if _pt and _pt.get('activationDate'):
        _proto = load_study_protocol()
        for _s in _proto.get('shared', []):
            if _s['id'] == assessment_id and _s.get('window'):
                try:
                    _act_d     = datetime.strptime(_pt['activationDate'][:10], '%Y-%m-%d').date()
                    _win_start = _act_d + timedelta(days=_s['window']['start_day'] - 1)
                    _win_end   = _act_d + timedelta(days=_s['window']['end_day']   - 1)
                    _appt_d    = datetime.strptime(new_appt_date, '%Y-%m-%d').date()
                    if not (_win_start <= _appt_d <= _win_end):
                        return jsonify({'error': (
                            f'Appointment date must be within the assessment window '
                            f'({_win_start.isoformat()} to {_win_end.isoformat()}).'
                        )}), 400
                except Exception:
                    pass
                break

    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found.'}), 404

    entry = next(
        (e for e in events_data.get('incomplete', [])
         if e.get('protocol_event_id') == call_type
         and (not event_id or e.get('id') == event_id)),
        None
    )
    if not entry:
        return jsonify({'error': 'Scheduling call stub not found.'}), 404

    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    complete_entry = {
        **entry,
        'completion_date':    completion_date,
        'filed_at':           filed_at,
        'filed_by':   _filer(),
        'duration_minutes':   duration_minutes,
        'notes':              notes,
        'new_appointment_date': new_appt_date,
    }
    events_data['incomplete'] = [e for e in events_data['incomplete'] if e.get('id') != entry['id']]
    events_data.setdefault('free', {}).setdefault(call_type, []).append(complete_entry)

    # Update the assessment stub's appointment_date (scheduled_date holds the window and is immutable).
    appt_str = datetime.strptime(new_appt_date, '%Y-%m-%d').strftime('%Y-%m-%dT09:00')
    for e in events_data.get('incomplete', []):
        if e.get('protocol_event_id') == assessment_id:
            e['appointment_date'] = appt_str
            break

    from utils.protocol_events import write_protocol_events
    write_protocol_events(folder, homer_id, events_data)

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', 0)
    label      = 'A1' if call_type == 'schedule_a1_call' else 'A2'
    write_patient_log(folder, homer_id, loginid, session_id,
                      f'{label} scheduling call recorded — new appointment: {new_appt_date}')
    return jsonify({'ok': True})


# ──────────────────────────────────────────────────────────────────────────────

def _auto_activate_experimental_patient(homer_id, place, device_name=None):
    """Auto-activate experimental patient if not already activated.
    Called when new configdata.csv is uploaded or first data is received.
    Returns True if patient was activated, False otherwise."""
    try:
        # Load patient data
        patient_data = FileHandler.load_homer_id_details(place)
        
        # Find the patient
        patient = None
        for user in patient_data.get("details", []):
            if user.get("homerID") == homer_id:
                patient = user
                break
        
        if not patient:
            print(f"DEBUG: Auto-activation: Patient {homer_id} not found")
            return False
        
        # Check if already activated (experimental patients need both pluto and mars active)
        if patient.get("group") != "experimental":
            print(f"DEBUG: Auto-activation: Patient {homer_id} is not experimental group")
            return False
        
        current_status = patient.get("status", {})
        if isinstance(current_status, dict):
            pluto_active = current_status.get("pluto") == "active"
            mars_active = current_status.get("mars") == "active"
            if pluto_active and mars_active:
                print(f"DEBUG: Auto-activation: Patient {homer_id} already fully activated")
                return False
        
        # Check if configdata.csv exists and has StartDate
        config_path = None
        for device in ["Pluto", "Mars", "pluto", "mars"]:
            test_path = os.path.join(Config.META_DATA_PATH, place, homer_id, device, "configdata.csv")
            if os.path.exists(test_path):
                config_path = test_path
                break
        
        if not config_path:
            print(f"DEBUG: Auto-activation: No configdata.csv found for {homer_id}")
            return False
        
        # Read StartDate from config
        activation_date = None
        with open(config_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if rows and rows[0].get("StartDate"):
                start_date_str = rows[0].get("StartDate")
                try:
                    activation_date = datetime.strptime(start_date_str, "%d-%m-%Y")
                    print(f"DEBUG: Auto-activation: Found StartDate in config: {activation_date}")
                except ValueError as e:
                    print(f"DEBUG: Auto-activation: Could not parse date {start_date_str}: {e}")
                    activation_date = datetime.now()
        
        if not activation_date:
            activation_date = datetime.now()
        
        # Activate the patient - set both pluto and mars as active
        if not isinstance(patient.get("status"), dict):
            patient["status"] = {"pluto": "not_activated", "mars": "not_activated"}
        
        # Activate based on device or both
        if device_name:
            device_lower = device_name.lower() if isinstance(device_name, str) else ""
            if "pluto" in device_lower:
                patient["status"]["pluto"] = "active"
            elif "mars" in device_lower:
                patient["status"]["mars"] = "active"
            else:
                patient["status"]["pluto"] = "active"
                patient["status"]["mars"] = "active"
        else:
            # No device specified - activate both
            patient["status"]["pluto"] = "active"
            patient["status"]["mars"] = "active"
        
        # Set activation date if not already set
        if not patient.get("activation_date"):
            patient["activation_date"] = activation_date.strftime("%Y-%m-%d")
        
        # Generate timeline if not already generated
        if not patient.get("timeline_generated"):
            try:
                from routes.patient_events import generate_study_events, load_events, save_events
                events = generate_study_events(homer_id, activation_date, "experimental")
                all_events = load_events(place)
                all_events[homer_id] = events
                save_events(all_events, place)
                patient["timeline_generated"] = True
                print(f"DEBUG: Auto-activation: Generated timeline for {homer_id}")
            except Exception as te:
                print(f"Warning: Could not generate timeline for {homer_id}: {te}")
        
        # Save updated patient data
        FileHandler.save_homer_id_details(place, patient_data)
        print(f"DEBUG: Auto-activation: Successfully activated {homer_id}")
        return True
        
    except Exception as e:
        print(f"Error in auto-activate experimental patient {homer_id}: {e}")
        return False


def _resolve_place(homer_id):
    """Return the site folder that owns homer_id.
    For admin users, checks session.place_info (populated by get_userId).
    Falls back to scanning all META-DATA sub-folders.
    For site users, returns login_place directly."""
    import os
    if current_session.is_admin():
        # place_info is filled in by get_userId on every page load
        cached = current_session.place_info.get(homer_id)
        if cached:
            return cached
        # Fallback: scan folders
        for place in os.listdir(Config.META_DATA_PATH):
            place_path = os.path.join(Config.META_DATA_PATH, place)
            if not os.path.isdir(place_path):
                continue
            details = FileHandler.load_homer_id_details(place)
            for d in details.get("details", []):
                if d.get("homerID") == homer_id:
                    return place
        return current_session.login_place  # last resort
    return current_session.login_place


@bp.route("/create_homer_id", methods=["POST"])
def create_homer_id():
    data = request.get_json()
    hospital_id = data.get("hospitalId")
    training_side = data.get("trainingSide")
    group = data.get("group")

    if not current_session.login_place:
        return jsonify({"status": "error", "message": "Not logged in"}), 401

    homer_id = FileHandler.add_new_homer_id(
        current_session.login_place, hospital_id, training_side, group
    )

    # Log patient creation
    try:
        from routes.auth import log_patient_created
        log_patient_created(homer_id, training_side, current_session.login_place)
    except Exception as e:
        print(f"Warning: Could not log patient creation: {e}")

    # Upload the updated homerIdDetails.json to AWS
    try:
        details_path = os.path.join(
            Config.META_DATA_PATH, current_session.login_place, "homerIdDetails.json"
        )
        s3_key = f"{current_session.login_place}/homerIdDetails.json"
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(details_path), exist_ok=True)
        
        # Upload to AWS
        upload_success = S3Operations.upload_to_s3(details_path, s3_key)
        if not upload_success:
            print(f"WARNING: Failed to upload homerIdDetails.json to S3")
    except Exception as upload_err:
        print(f"ERROR: Could not upload to AWS: {upload_err}")

    return jsonify(
        {
            "status": "success",
            "message": "User registered successfully",
            "homer_id": homer_id,
        }
    ), 200


# In routes/user_management.py - Update the get_hospital_ids function


@bp.route("/get_userId", methods=["POST"])
def get_hospital_ids():
    device_name = request.form.get("search_term", "Pluto")
    current_session.device_name = device_name

    # Always derive login_place from LOGIN_CREDENTIALS using the loginId sent by frontend
    login_id = request.form.get("LoginId", "")
    user_data = Config.LOGIN_CREDENTIALS.get(login_id) if login_id else None

    if user_data:
        current_session.login_place = user_data.get("place")
        current_session.privilege = user_data.get("privilege", "user")

    # login_place must be a real place at this point
    if not current_session.login_place:
        return jsonify({"hospital_info": []}), 200

    hospital_info = []
    local_hospital_ids = set()
    _local_place_info = {}  # collected here, written to session once at end

    # First, load homerIdDetails.json to get status for all users
    # Only the global lab admin sees all centres; site admins see their own place only
    homer_details = {}
    if not current_session.is_admin():
        if current_session.login_place:
            homer_data = FileHandler.load_homer_id_details(current_session.login_place)
            for user in homer_data.get("details", []):
                homer_details[user.get("homerID")] = {
                    "group": user.get("group"),
                    "status": user.get("status", {}),
                    "trainingSide": user.get("trainingSide"),
                }
    else:
        # For admin, load from all places
        if os.path.exists(Config.META_DATA_PATH):
            for place in os.listdir(Config.META_DATA_PATH):
                place_path = os.path.join(Config.META_DATA_PATH, place)
                if os.path.isdir(place_path):
                    homer_data = FileHandler.load_homer_id_details(place)
                    for user in homer_data.get("details", []):
                        user_id = user.get("homerID")
                        homer_details[user_id] = {
                            "group": user.get("group"),
                            "status": user.get("status", {}),
                            "trainingSide": user.get("trainingSide"),
                            "place": place,
                        }

    def read_csv_file(
        path,
        default_status,
        deviceName,
        role_value=None,
        place=None,
    ):
        try:
            with open(path, mode="r", encoding="utf-8") as file:
                csv_reader = csv.DictReader(file)
                for row in csv_reader:
                    hospital_id = row.get("HospitalID") or row.get(
                        "HomerID"
                    )  # Support both headers
                    if not hospital_id:
                        continue

                    role = role_value
                    place_to_check = place if place else current_session.login_place

                    if role == "experimental":
                        # Do NOT auto-activate here — activation should only happen
                        # when cloud data is confirmed uploaded (via activate_experimental_patient route)
                        # or via the manual activate button in the UI.
                        pass

                    if place:
                        _local_place_info[hospital_id] = place
                    local_hospital_ids.add(hospital_id)
        except Exception as e:
            print(f"Error reading CSV: {e}")

    # Helper function to update status in homerDetails.json
    def update_user_status(place, homer_id, new_status, device_name):
        try:
            data = FileHandler.load_homer_id_details(place)
            user_updated = False

            for user in data.get("details", []):
                if user.get("homerID") == homer_id:
                    current_status = user.get("status")

                    print(
                        f"🔵 Updating {homer_id} - Current status type: {type(current_status)}, Current status: {current_status}"
                    )
                    print(f"🔵 Device: {device_name}, New status: {new_status}")

                    # If status is dictionary (multiple device values for experimental)
                    if isinstance(current_status, dict):
                        user["status"][device_name.lower()] = new_status
                        print(
                            f"✅ Updated dict status for {device_name}: {user['status']}"
                        )
                    # If status is single value (string for control)
                    elif isinstance(current_status, str):
                        user["status"] = new_status
                        print(f"✅ Updated string status: {user['status']}")
                    # If status doesn't exist, create it (for experimental users)
                    elif current_status is None:
                        # For experimental users, create dict; for control, create string
                        if device_name and device_name.lower() in ["pluto", "mars"]:
                            user["status"] = {device_name.lower(): new_status}
                            print(f"✅ Created new dict status: {user['status']}")
                        else:
                            user["status"] = new_status
                            print(f"✅ Created new string status: {user['status']}")

                    user_updated = True
                    break

            # Save updated data to file
            if user_updated:
                FileHandler.save_homer_id_details(place, data)
                print(f"✅ Saved homerDetails.json for {place}")
            else:
                print(f"❌ User {homer_id} not found in {place}")

            # Update in-memory dictionary to reflect the change (with error handling)
            if homer_id in homer_details:
                try:
                    current_in_memory = homer_details[homer_id]["status"]
                    if isinstance(current_in_memory, dict):
                        homer_details[homer_id]["status"][device_name.lower()] = (
                            new_status
                        )
                    else:
                        homer_details[homer_id]["status"] = new_status
                    print(f"✅ In-memory status updated for {homer_id}")
                except Exception as e:
                    print(f"⚠️ Could not update in-memory status: {e}")

        except Exception as e:
            print(f"❌ Error updating status: {e}")
            import traceback

            traceback.print_exc()

    if current_session.is_admin():
        # Admin view - check all places
        if os.path.exists(Config.META_DATA_PATH):
            for place in os.listdir(Config.META_DATA_PATH):
                place_path = os.path.join(Config.META_DATA_PATH, place)
                if os.path.isdir(place_path):
                    exp_csv = os.path.join(
                        place_path, f"{device_name.lower()}UserDetails.csv"
                    )
                    ctrl_csv = os.path.join(place_path, Config.CONTROL_USER_DETAILS)
                    if os.path.exists(exp_csv):
                        read_csv_file(
                            exp_csv,
                            default_status="",
                            deviceName=device_name.lower(),
                            role_value="experimental",
                            place=place,
                        )
                    if os.path.exists(ctrl_csv):
                        read_csv_file(
                            ctrl_csv,
                            default_status="",
                            deviceName="",
                            role_value="control",
                            place=place,
                        )

        # Deactivate users not in any CSV files (admin view)
        # Guard: only run deactivation if we actually read some CSV data.
        # If all CSV files are temporarily missing, local_hospital_ids will be empty
        # and we must NOT wipe every patient's activation status.
        if local_hospital_ids and os.path.exists(Config.META_DATA_PATH):
            for place in os.listdir(Config.META_DATA_PATH):
                place_path = os.path.join(Config.META_DATA_PATH, place)
                if os.path.isdir(place_path):
                    data = FileHandler.load_homer_id_details(place)
                    for user in data.get("details", []):
                        user_id = user.get("homerID")
                        if user_id and user_id not in local_hospital_ids:
                            if (
                                user.get("status") == "active"
                                and user.get("group") == "experimental"
                            ):
                                print(
                                    f"Deactivating user {user_id} - not found in CSV files"
                                )
                                update_user_status(place, user_id, "not_activated", device_name)
                                user["status"] = "not_activated"
    else:
        # Regular user view
        place_path = os.path.join(Config.META_DATA_PATH, current_session.login_place)
        pexp_csv = os.path.join(place_path, f"plutoUserDetails.csv")
        mexp_csv = os.path.join(place_path, f"marsUserDetails.csv")
        ctrl_csv = os.path.join(place_path, Config.CONTROL_USER_DETAILS)

        if os.path.exists(pexp_csv):
            read_csv_file(
                pexp_csv,
                default_status="",
                deviceName="pluto",
                role_value="experimental",
            )
        if os.path.exists(mexp_csv):
            read_csv_file(
                mexp_csv,
                default_status="",
                deviceName="mars",
                role_value="experimental",
            )
        if os.path.exists(ctrl_csv):
            read_csv_file(
                ctrl_csv, default_status="", deviceName="", role_value="control"
            )

    # Deactivate users who are active but NOT in any CSV files (for non-admin only)
    # Guard: skip if no CSV data was loaded — prevents wiping all patients on CSV read failure.
    if not current_session.is_admin() and local_hospital_ids:
        place = current_session.login_place
        data = FileHandler.load_homer_id_details(place)
        for user in data.get("details", []):
            user_id = user.get("homerID")
            if user_id and user_id not in local_hospital_ids:
                if (
                    user.get("status") == "active"
                    and user.get("group") == "experimental"
                ):
                    print(f"Deactivating user {user_id} - not found in CSV files")
                    update_user_status(place, user_id, "not_activated", device_name)
                    user["status"] = "not_activated"

    # Build hospital_info from homerIdDetails for current place
    # For admin, iterate all places since they can see everyone
    if current_session.is_admin():
        if os.path.exists(Config.META_DATA_PATH):
            for place in os.listdir(Config.META_DATA_PATH):
                place_path = os.path.join(Config.META_DATA_PATH, place)
                if os.path.isdir(place_path):
                    place_data = FileHandler.load_homer_id_details(place)
                    for item in place_data.get("details", []):
                        homer_id = item.get("homerID")
                        if homer_id:
                            _local_place_info[homer_id] = place  # ← needed for save routes
                        hospital_info.append({
                            "HospitalID": homer_id,
                            "Status": item.get("status", {}),
                            "role": item.get("group"),
                            "trainingSide": item.get("trainingSide"),
                            "activated": item.get("activated", False),
                            "vcgType": item.get("vcg_type") or item.get("vcgType"),
                            "place": place,
                            "discontinued": item.get("discontinued", False),
                            "studyPaused": item.get("studyPaused", False),
                            "pausedAt": item.get("pausedAt", None),
                            "resumedAt": item.get("resumedAt", None),
                            "activationDate": item.get("activation_date", None),
                            "discontinueReason": item.get("discontinueReason", ""),
                            "discontinueDate": item.get("discontinueDate", ""),
                        })
    else:
        data = FileHandler.load_homer_id_details(current_session.login_place)
        for item in data.get("details", []):
            hospital_info.append({
                "HospitalID": item.get("homerID"),
                "Status": item.get("status", {}),
                "role": item.get("group"),
                "trainingSide": item.get("trainingSide"),
                "activated": item.get("activated", False),
                "vcgType": item.get("vcg_type") or item.get("vcgType"),
                "discontinued": item.get("discontinued", False),
                "studyPaused": item.get("studyPaused", False),
                "pausedAt": item.get("pausedAt", None),
                "resumedAt": item.get("resumedAt", None),
                "activationDate": item.get("activation_date", None),
                "discontinueReason": item.get("discontinueReason", ""),
                "discontinueDate": item.get("discontinueDate", ""),
            })

    # Flush place_info to session once (avoids Flask not detecting nested dict mutations)
    if _local_place_info:
        current_session.set_place_info(_local_place_info)

    return jsonify({"hospital_info": hospital_info})



@bp.route("/trackrecord/<homer_id>", methods=["GET"])
def get_track_record(homer_id):
    """Get track record for a specific homer ID"""
    if not current_session.login_place:
        return jsonify({"error": "Not logged in"}), 401

    place = _resolve_place(homer_id)
    data = FileHandler.load_homer_id_details(place)

    for user in data.get("details", []):
        if user.get("homerID") == homer_id:
            return jsonify(
                {"homerID": homer_id, "trackRecord": user.get("trackRecord", [])}
            )

    return jsonify({"error": "HomerID not found"}), 404


@bp.route("/update-trackrecord", methods=["POST"])
def update_track_record():
    """Update track record for a homer ID"""
    if not current_session.login_place:
        return jsonify({"error": "Not logged in"}), 401

    payload = request.json
    homer_id = payload.get("homerID")
    updated_record = payload.get("trackRecord")

    if not homer_id or updated_record is None:
        return jsonify({"error": "Missing homerID or trackRecord"}), 400

    place = _resolve_place(homer_id)
    data = FileHandler.load_homer_id_details(place)

    user_found = False
    for user in data.get("details", []):
        if user.get("homerID") == homer_id:
            user["trackRecord"] = updated_record  # Store as list
            user_found = True
            break

    if not user_found:
        return jsonify({"error": "HomerID not found"}), 404

    FileHandler.save_homer_id_details(place, data)
    return jsonify({"success": True})


@bp.route("/add-swap-watch", methods=["POST"])
def add_swap_watch_record():
    """Add swap watch record for a homer ID"""
    if not current_session.login_place:
        return jsonify({"error": "Not logged in"}), 401

    payload = request.json
    homer_id = payload.get("homerID")
    swap_watch_record = payload.get("swapWatchRecord")

    if not homer_id or swap_watch_record is None:
        return jsonify({"error": "Missing homerID or swapWatchRecord"}), 400

    place = _resolve_place(homer_id)
    data = FileHandler.load_homer_id_details(place)

    user_found = False
    for user in data.get("details", []):
        if user.get("homerID") == homer_id:
            if "swapWatchRecords" not in user:
                user["swapWatchRecords"] = []
            user["swapWatchRecords"].append(swap_watch_record)
            user_found = True
            break

    if not user_found:
        return jsonify({"error": "HomerID not found"}), 404

    FileHandler.save_homer_id_details(place, data)
    return jsonify({"success": True, "message": "Swap watch record added successfully"})


@bp.route("/swap-watch-records/<homer_id>", methods=["GET"])
def get_swap_watch_records(homer_id):
    """Get swap watch records for a homer ID"""
    if not current_session.login_place:
        return jsonify({"error": "Not logged in"}), 401

    place = _resolve_place(homer_id)
    data = FileHandler.load_homer_id_details(place)

    for user in data.get("details", []):
        if user.get("homerID") == homer_id:
            return jsonify({"swapWatchRecords": user.get("swapWatchRecords", [])})

    return jsonify({"error": "HomerID not found"}), 404


@bp.route("/get-config-dates/<homer_id>", methods=["GET"])
def get_config_dates(homer_id):
    """Get startDate, endDate and group from homerIdDetails.json or device-specific configdata.csv"""
    if not current_session.login_place:
        return jsonify({"error": "Not logged in"}), 401

    try:
        from flask import request

        # Get the current device from query parameter
        current_device = request.args.get(
            "device", "Pluto"
        )  # Default to Pluto if not specified
        start_date = None
        end_date = None
        group = None
        found_source = None

        # FIRST: Always check homerIdDetails.json to determine group
        homer_details_path = os.path.join(
            Config.META_DATA_PATH, current_session.login_place, "homerIdDetails.json"
        )
        user_group = None

        if os.path.exists(homer_details_path):
            try:
                with open(homer_details_path, "r") as f:
                    data = json.load(f)
                    for user in data.get("details", []):
                        if user.get("homerID") == homer_id:
                            user_group = user.get("group")
                            group = user_group

                            # For CONTROL group: Always get from homerIdDetails.json
                            if user_group == "control":
                                # Try both possible field names for dates
                                start_date = user.get("startDate") or user.get(
                                    "activation_date"
                                )
                                end_date = user.get("endDate") or user.get("end_date")
                                if start_date and end_date:
                                    found_source = "homerIdDetails.json (control group)"
                            break
            except Exception as e:
                pass

        # For EXPERIMENTAL group: Get from device-specific configdata.csv
        if not found_source and user_group == "experimental":
            base_path = os.path.join(
                Config.META_DATA_PATH, current_session.login_place, homer_id
            )

            # Build path for the specific device
            device_config = os.path.join(base_path, current_device, "configdata.csv")

            if os.path.exists(device_config):
                try:
                    with open(device_config, "r") as f:
                        reader = csv.DictReader(f)
                        rows = list(reader)
                        if rows:
                            first_row = rows[0]
                            last_row = rows[-1]
                            start_date = first_row.get("StartDate")
                            end_date = last_row.get("EndDate")
                            found_source = (
                                f"{current_device}/configdata.csv (experimental group)"
                            )
                except Exception as e:
                    pass
            else:
                # Fallback: If device config not found for experimental group, try others
                base_path = os.path.join(
                    Config.META_DATA_PATH, current_session.login_place, homer_id
                )

                for device in ["Pluto", "Mars", "actilife"]:
                    if device == current_device:
                        continue  # Already checked this

                    device_config = os.path.join(base_path, device, "configdata.csv")

                    if os.path.exists(device_config):
                        try:
                            with open(device_config, "r") as f:
                                reader = csv.DictReader(f)
                                rows = list(reader)
                                if rows:
                                    first_row = rows[0]
                                    last_row = rows[-1]
                                    start_date = first_row.get("StartDate")
                                    end_date = last_row.get("EndDate")
                                    found_source = f"{device}/configdata.csv (fallback)"
                                    break
                        except Exception as e:
                            pass

        if not start_date or not end_date:
            error_msg = f"Config dates not found for {homer_id} (group: {user_group}, device: {current_device})"
            return jsonify({"error": error_msg}), 404

        return jsonify(
            {
                "startDate": start_date,
                "endDate": end_date,
                "group": group or "unknown",
                "source": found_source,
            }
        )

    except Exception as e:
        return jsonify({"error": f"Exception in get_config_dates: {str(e)}"}), 500


@bp.route("/assign_group_user", methods=["POST"])
def assign_group_for_user():
    """Assign group to a user (experimental/control)"""
    if not current_session.login_place:
        return jsonify({"error": "Not logged in"}), 401

    try:
        request_data = request.get_json()
        homer_id = request_data.get("userID")
        group = request_data.get("selectedGroup")

        if not homer_id or not group:
            return jsonify(
                {"status": "error", "message": "Missing userID or group"}
            ), 400

        # Load user data
        data = FileHandler.load_homer_id_details(current_session.login_place)

        # Find user and get training side
        trainingside = None
        for user in data.get("details", []):
            if user.get("homerID") == homer_id:
                trainingside = user.get("trainingSide")
                break

        if not trainingside:
            return jsonify({"status": "error", "message": "User not found"}), 404

        startdate = ""
        enddate = ""
        location = current_session.login_place

        if group == "experimental":
            # Create rows for Pluto and Mars
            header_pluto = Config.PLUTO_CONFIG_HEADER
            mech_values_pluto = [0, 0, 0, 0, 0, 0]  # 6 values for Pluto
            row_pluto = (
                [homer_id, startdate, enddate, 0]
                + mech_values_pluto
                + [trainingside, location, group, 0, 0]
            )

            header_mars = Config.MARS_CONFIG_HEADER
            mech_values_mars = [0, 0, 0]  # 3 values for Mars
            row_mars = (
                [homer_id, startdate, enddate, 0]
                + mech_values_mars
                + ["150", "250", trainingside, location, group]
            )

            # Create directories and write files
            local_folder_path = os.path.join(
                Config.META_DATA_PATH, current_session.login_place, homer_id
            )

            for device, header, row in [
                ("Pluto", header_pluto, row_pluto),
                ("Mars", header_mars, row_mars),
            ]:
                file_path = os.path.join(local_folder_path, device, Config.CONFIG_DATA)
                try:
                    FileHandler.write_csv_data(file_path, row, header)
                    # Upload to S3 (non-blocking - local data saved regardless)
                    s3_key = f"{current_session.login_place}/{homer_id}/{device}/{Config.CONFIG_DATA}"
                    S3Operations.upload_to_s3(file_path, s3_key)
                    # Update user record in homerIdDetails after writing CSV
                    if device == "Mars":  # Only update JSON once, after both devices processed
                        for user in data["details"]:
                            if user["homerID"] == homer_id:
                                user["group"] = group
                                user["status"] = {
                                    "pluto": "not_activated",
                                    "mars": "not_activated",
                                }
                                if "trackRecord" not in user:
                                    user["trackRecord"] = []
                                user["trackRecord"] = Config.exprTrackRecord
                                FH.save_homer_id_details(
                                    current_session.login_place, data
                                )
                                break

                except Exception as e:
                    # Cleanup on error
                    if os.path.exists(local_folder_path):
                        FileHandler.cleanup_user_folder(
                            local_folder_path, device, Config.CONFIG_DATA
                        )
                    return jsonify(
                        {"status": "error", "message": f"Failed for {device}: {str(e)}"}
                    ), 500

        else:  # Control group
            device = Config.ACTILIFE_LABEL
            row = [homer_id, startdate, enddate, location, group]
            header = Config.ACTILIFE_CONFIG_HEADER

            local_folder_path = os.path.join(
                Config.META_DATA_PATH, current_session.login_place, homer_id
            )
            file_path = os.path.join(local_folder_path, device, Config.CONFIG_DATA)

            try:
                FileHandler.write_csv_data(file_path, row, header)
                # Upload to S3
                s3_key = f"{current_session.login_place}/{homer_id}/{device}/{Config.CONFIG_DATA}"
                if not S3Operations.upload_to_s3(file_path, s3_key):
                    raise Exception("S3 upload failed")
                else:
                    for user in data["details"]:
                        if user["homerID"] == homer_id:
                            # ✅ update group
                            user["group"] = group
                            # ✅ update status
                            user["status"] = "not_activated"

                            # ✅ add new trackRecord
                            user["trackRecord"] = Config.ctrlTrackRecord

                            FH.save_homer_id_details(current_session.login_place, data)
                            break  # stop after updating the correct user

                # Write to control user details
                control_data = [
                    datetime.now().strftime("%d-%m-%Y"),
                    homer_id,
                    location,
                    group,
                ]
                control_file_path = os.path.join(
                    Config.META_DATA_PATH,
                    current_session.login_place,
                    Config.CONTROL_USER_DETAILS,
                )
                FileHandler.write_csv_data(
                    control_file_path,
                    control_data,
                    ["Date", "HomerID", "Location", "Group"],
                )

            except Exception as e:
                if os.path.exists(local_folder_path):
                    FileHandler.cleanup_user_folder(
                        local_folder_path, device, Config.CONFIG_DATA
                    )
                    return jsonify({"status": "error", "message": f"Failed: {str(e)}"}), 500

        # Log group assignment
        try:
            from routes.auth import log_group_assigned
            log_group_assigned(homer_id, group, current_session.login_place)
        except Exception as e:
            print(f"Warning: Could not log group assignment: {e}")

        return jsonify(
            {
                "status": "success",
                "message": f"User {homer_id} assigned to {group} group successfully",
            }
        ), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500


@bp.route("/activate_control_patient", methods=["POST"])
def activate_control_patient():
    """Activate a control patient with VCG type selection"""
    if not current_session.login_place:
        return jsonify({"error": "Not logged in"}), 401

    try:
        request_data = request.get_json()
        homer_id = request_data.get("userID")
        vcg_type_raw = request_data.get("vcgType")
        activation_date_str = request_data.get("activationDate", "")  # NEW: user-selected date

        if not homer_id or not vcg_type_raw:
            return jsonify(
                {"status": "error", "message": "Missing userID or vcgType"}
            ), 400

        # Normalise to canonical key (handles vcg4_5 → VCG4,5 etc.)
        vcg_type_map = {
            "vcg2": "VCG2", "VCG2": "VCG2",
            "vcg3": "VCG3", "VCG3": "VCG3",
            "vcg4_5": "VCG4,5", "VCG4_5": "VCG4,5",
            "vcg4,5": "VCG4,5", "VCG4,5": "VCG4,5",
            "vcg4&5": "VCG4,5", "VCG4&5": "VCG4,5",
        }
        vcg_type = vcg_type_map.get(vcg_type_raw, vcg_type_raw.upper())

        # Parse user-provided activation date, fall back to today
        if activation_date_str:
            try:
                activation_date = datetime.strptime(activation_date_str, "%Y-%m-%d")
            except ValueError:
                activation_date = datetime.now()
        else:
            activation_date = datetime.now()

        # Resolve correct site for this patient (admin may manage multiple sites)
        activate_place = _resolve_place(homer_id)
        # Load user data from the correct site
        data = FileHandler.load_homer_id_details(activate_place)

        # Find user and update
        user_found = False
        for user in data.get("details", []):
            if user.get("homerID") == homer_id:
                user["activated"] = True
                user["vcg_type"] = vcg_type  # always stored as canonical key
                user["activation_date"] = activation_date.strftime("%Y-%m-%d")  # always use provided date
                user_found = True
                break

        if not user_found:
            return jsonify({"status": "error", "message": "User not found"}), 404

        FileHandler.save_homer_id_details(activate_place, data)

        # Generate timeline events for the patient
        try:
            from routes.patient_events import (
                generate_study_events,
                load_events,
                save_events,
            )

            events = generate_study_events(homer_id, activation_date, "control")
            all_events = load_events(activate_place)
            all_events[homer_id] = events
            save_events(all_events, activate_place)
        except Exception as te:
            pass  # Don't fail activation if timeline generation fails

        # Log patient activation
        try:
            from routes.auth import log_patient_activated
            log_patient_activated(homer_id, activation_date_str, "control", current_session.login_place)
        except Exception as e:
            print(f"Warning: Could not log patient activation: {e}")

        return jsonify(
            {
                "status": "success",
                "message": f"Patient {homer_id} activated with {vcg_type.upper()} exercises",
            }
        ), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500


@bp.route("/register_new_user", methods=["POST"])
def register_new_user():
    """Register a new user with all details"""
    if not current_session.login_place:
        return jsonify({"error": "Not logged in"}), 401

    try:
        data = request.get_json()
        username = data.get("username")
        hospital_id = data.get("hospitalId")
        start_date = data.get("startDate")
        end_date = data.get("endDate")
        age = data.get("age")
        location = data.get("location")
        training_side = data.get("trainingSide")
        group = data.get("group")
        fme1k = data.get("fme1k")
        fme2k = data.get("fme2k")

        prescribed_times_pluto = data.get("prescribedTimesPluto", [])
        prescribed_times_mars = data.get("prescribedTimesMars", [])

        # Validate required fields
        if not all([username, hospital_id, start_date, end_date, group]):
            return jsonify(
                {"status": "error", "message": "Missing required fields"}
            ), 400

        # Format dates
        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d").strftime("%d-%m-%Y")
            end_date = datetime.strptime(end_date, "%Y-%m-%d").strftime("%d-%m-%Y")
        except ValueError:
            return jsonify(
                {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD"}
            ), 400

        # Calculate total times
        total_time_pluto = sum(float(p.get("time", 0)) for p in prescribed_times_pluto)
        total_time_mars = sum(float(p.get("time", 0)) for p in prescribed_times_mars)

        local_folder_path = os.path.join(
            Config.META_DATA_PATH, current_session.login_place, hospital_id
        )

        if group == "experimental":
            # Pluto configuration
            header_pluto = Config.PLUTO_CONFIG_HEADER
            mech_values_pluto = [p.get("time", 0) for p in prescribed_times_pluto]
            if len(mech_values_pluto) < 6:
                mech_values_pluto.extend([0] * (6 - len(mech_values_pluto)))

            # PLUTO_CONFIG_HEADER: HomerID, StartDate, EndDate, TotalTime, WFE, WURD, FPS, HOC, FME1, FME2, TrainingSide, Location, Group, FME1K, FME2K (15 cols)
            row_pluto = (
                [hospital_id, start_date, end_date, total_time_pluto]
                + mech_values_pluto
                + [training_side, location, group, fme1k or 0, fme2k or 0]
            )

            # Mars configuration
            header_mars = Config.MARS_CONFIG_HEADER
            mech_values_mars = [p.get("time", 0) for p in prescribed_times_mars]
            if len(mech_values_mars) < 3:
                mech_values_mars.extend([0] * (3 - len(mech_values_mars)))

            forearm_length = data.get("forearmLength", "150")
            upperarm_length = data.get("upperarmLength", "250")

            # MARS_CONFIG_HEADER: HomerID, StartDate, EndDate, TotalTime, ML, AP, MLAP, ForeArmLength, UpperArmLength, TrainingSide, Location, Group (12 cols)
            row_mars = (
                [hospital_id, start_date, end_date, total_time_mars]
                + mech_values_mars
                + [forearm_length, upperarm_length, training_side, location, group]
            )

            # Create files for both devices
            for device, header, row in [
                ("Pluto", header_pluto, row_pluto),
                ("Mars", header_mars, row_mars),
            ]:
                file_path = os.path.join(local_folder_path, device, Config.CONFIG_DATA)
                try:
                    FileHandler.write_csv_data(file_path, row, header)
                    # Upload to S3
                    s3_key = f"{current_session.login_place}/{hospital_id}/{device}/{Config.CONFIG_DATA}"
                    if not S3Operations.upload_to_s3(file_path, s3_key):
                        raise Exception(f"S3 upload failed for {device}")
                except Exception as e:
                    if os.path.exists(local_folder_path):
                        FileHandler.cleanup_user_folder(
                            local_folder_path, device, Config.CONFIG_DATA
                        )
                    return jsonify(
                        {"status": "error", "message": f"Failed for {device}: {str(e)}"}
                    ), 500

        else:  # Control group
            device = Config.ACTILIFE_LABEL
            # ACTILIFE_CONFIG_HEADER: HomerID, StartDate, EndDate, Location, Group (5 cols)
            row = [hospital_id, start_date, end_date, location, group]
            header = Config.ACTILIFE_CONFIG_HEADER

            file_path = os.path.join(local_folder_path, device, Config.CONFIG_DATA)

            try:
                FileHandler.write_csv_data(file_path, row, header)
                # Upload to S3
                s3_key = f"{current_session.login_place}/{hospital_id}/{device}/{Config.CONFIG_DATA}"
                if not S3Operations.upload_to_s3(file_path, s3_key):
                    raise Exception("S3 upload failed")

                # Write to control user details
                control_data = [
                    datetime.now().strftime("%d-%m-%Y"),
                    hospital_id,
                    location,
                    group,
                ]
                control_file_path = os.path.join(
                    Config.META_DATA_PATH,
                    current_session.login_place,
                    Config.CONTROL_USER_DETAILS,
                )
                FileHandler.write_csv_data(
                    control_file_path,
                    control_data,
                    ["Date", "HomerID", "Location", "Group"],
                )

            except Exception as e:
                if os.path.exists(local_folder_path):
                    FileHandler.cleanup_user_folder(
                        local_folder_path, device, Config.CONFIG_DATA
                    )
                return jsonify({"status": "error", "message": f"Failed: {str(e)}"}), 500

        # Homer ID entry is already created by assign_group logic; 
        # here we only need to add if not already present (create_homer_id handles this)
        # Note: register_new_user creates CSV files only - the homerIdDetails entry
        # was created earlier by create_homer_id route

        # Generate timeline events for patients
        try:
            from routes.patient_events import (
                generate_study_events,
                load_events,
                save_events,
            )

            start_date_dt = datetime.strptime(start_date, "%d-%m-%Y")
            events = generate_study_events(hospital_id, start_date_dt, group)
            all_events = load_events(current_session.login_place)
            all_events[hospital_id] = events
            save_events(all_events, current_session.login_place)
        except Exception as te:
            pass  # Don't fail registration if timeline generation fails

        return jsonify(
            {
                "status": "success",
                "message": "User registered and data uploaded successfully",
            }
        ), 200

    except Exception as e:
        return jsonify(
            {"status": "error", "message": f"Registration failed: {str(e)}"}
        ), 500


@bp.route("/update_data_in_aws", methods=["POST"])
def upload_updated_data():
    """Update user data and upload to AWS"""
    if not current_session.login_place:
        return jsonify({"error": "Not logged in"}), 401

    try:
        data = request.form.getlist("updatedData[]")
        user_name = request.form.get("userName")
        device_name = request.form.get("deviceName")

        if not all([data, user_name, device_name]):
            return jsonify({"status": "error", "message": "Missing required data"}), 400

        # Determine header based on device
        if device_name == Config.PLUTO_LABEL:
            header = Config.PLUTO_CONFIG_HEADER
        elif device_name == Config.MARS_LABEL:
            header = Config.MARS_CONFIG_HEADER
        else:
            return jsonify({"status": "error", "message": "Invalid device name"}), 400

        # Build paths
        if current_session.is_admin():
            place = current_session.place_info.get(user_name, current_session.login_place)
            file_path = os.path.join(
                Config.META_DATA_PATH, place, user_name, device_name, Config.CONFIG_DATA
            )
            s3_key = f"{place}/{user_name}/{device_name}/{Config.CONFIG_DATA}"
        else:
            place = current_session.login_place
            file_path = os.path.join(
                Config.META_DATA_PATH,
                current_session.login_place,
                user_name,
                device_name,
                Config.CONFIG_DATA,
            )
            s3_key = f"{current_session.login_place}/{user_name}/{device_name}/{Config.CONFIG_DATA}"

        # First, upload to S3
        # Create a temp file for upload
        import tempfile
        import os as _os
        
        # Create temp file with the data
        temp_dir = tempfile.gettempdir()
        temp_file = _os.path.join(temp_dir, f"upload_{user_name}_{device_name}_{int(datetime.now().timestamp())}.csv")
        
        try:
            # Write to temp file
            FileHandler.write_csv_data(temp_file, data, header)
            
            # Upload to S3 first
            s3_uploaded = S3Operations.upload_to_s3(temp_file, s3_key)
            
            if not s3_uploaded:
                # Clean up temp file
                if _os.path.exists(temp_file):
                    _os.remove(temp_file)
                return jsonify(
                    {"status": "error", "message": "Failed to upload to S3"}
                ), 500
            
            # S3 upload successful - now save locally as backup/metadata
            _os.makedirs(_os.path.dirname(file_path), exist_ok=True)
            _os.rename(temp_file, file_path)  # Move temp file to local storage

        except Exception as e:
            # Clean up temp file on error
            if _os.path.exists(temp_file):
                _os.remove(temp_file)
            return jsonify(
                {"status": "error", "message": f"Upload failed: {str(e)}"}
            ), 500

        # Auto-activate experimental patient if not already activated
        try:
            _auto_activate_experimental_patient(user_name, place, device_name)
        except Exception as auto_err:
            print(f"Warning: Auto-activation check failed: {auto_err}")

        # Change 2: Check if config StartDate matches stored activation_date
        mismatch_warning = None
        try:
            homer_data = FileHandler.load_homer_id_details(place)
            patient_record = next(
                (u for u in homer_data.get("details", []) if u.get("homerID") == user_name), None
            )
            if patient_record and patient_record.get("activation_date"):
                stored_activation = datetime.strptime(patient_record["activation_date"], "%Y-%m-%d")
                # Read StartDate from the newly uploaded config file
                try:
                    import pandas as _pd
                    cfg_df = _pd.read_csv(file_path)
                    if not cfg_df.empty and "StartDate" in cfg_df.columns:
                        config_start_str = cfg_df["StartDate"].iloc[0]
                        config_start = datetime.strptime(config_start_str, "%d-%m-%Y")
                        diff_days = abs((config_start - stored_activation).days)
                        if diff_days > 0:
                            mismatch_warning = {
                                "activation_date": patient_record["activation_date"],
                                "config_start_date": config_start.strftime("%Y-%m-%d"),
                                "diff_days": diff_days,
                            }
                            # Save mismatch as an event so it appears in the timeline error section
                            try:
                                from routes.patient_events import load_events, save_events
                                all_events = load_events(place)
                                mismatches = all_events.setdefault(f"{user_name}_config_mismatches", [])
                                import uuid as _uuid
                                mismatches.append({
                                    "id": str(_uuid.uuid4()),
                                    "type": "config_date_mismatch",
                                    "device": device_name,
                                    "activation_date": patient_record["activation_date"],
                                    "config_start_date": config_start.strftime("%Y-%m-%d"),
                                    "diff_days": diff_days,
                                    "detected_at": datetime.now().isoformat(),
                                })
                                save_events(all_events, place)
                            except Exception as _ev_err:
                                print(f"Warning: Could not save mismatch event: {_ev_err}")
                except Exception as _cfg_err:
                    print(f"Warning: Could not read config StartDate for mismatch check: {_cfg_err}")
        except Exception as _mm_err:
            print(f"Warning: Mismatch check failed: {_mm_err}")

        response_payload = {"status": "success", "message": "Data uploaded to AWS successfully"}
        if mismatch_warning:
            response_payload["mismatch_warning"] = mismatch_warning
        return jsonify(response_payload), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500


@bp.route("/get_config_mismatches/<user_id>", methods=["GET"])
def get_config_mismatches(user_id):
    """Return any config StartDate vs activation_date mismatches for a patient."""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401
        place = _resolve_place(user_id)
        from routes.patient_events import load_events
        all_events = load_events(place)
        mismatches = all_events.get(f"{user_id}_config_mismatches", [])
        return jsonify({"status": "success", "mismatches": mismatches})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# Add this function to routes/user_management.py
@bp.route("/check_control_activation/<user_id>", methods=["GET"])
def check_control_activation(user_id):
    """Check if control user is activated"""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        # Determine file path
        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
            config_path = os.path.join(
                Config.META_DATA_PATH,
                place,
                user_id,
                Config.ACTILIFE_LABEL,
                Config.CONFIG_DATA,
            )
        else:
            config_path = os.path.join(
                Config.META_DATA_PATH,
                current_session.login_place,
                user_id,
                Config.ACTILIFE_LABEL,
                Config.CONFIG_DATA,
            )

        activated = os.path.exists(config_path)

        return jsonify({"status": "success", "activated": activated})

    except Exception as e:
        print(f"Error checking activation: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/activate_control_user", methods=["POST"])
def activate_control_user():
    """Activate control group user with start and end dates."""
    try:
        if not current_session.login_place:
            return jsonify({"status": "error", "message": "Not logged in"}), 401

        data = request.get_json()
        user_id = data.get("user_id")
        vcg_type = data.get("vcg_type")
        activation_date_str = data.get("activation_date", "")  # NEW: user-selected date

        if not user_id:
            return jsonify({"status": "error", "message": "Missing user ID"}), 400

        if not vcg_type:
            return jsonify(
                {"status": "error", "message": "Please select VCG type"}
            ), 400

        # Use user-provided activation date, fall back to today
        if activation_date_str:
            try:
                start_date = datetime.strptime(activation_date_str, "%Y-%m-%d")
            except ValueError:
                start_date = datetime.now()
        else:
            start_date = datetime.now()

        end_date = start_date + timedelta(days=28)

        start_date_str = start_date.strftime("%d-%m-%Y")
        end_date_str = end_date.strftime("%d-%m-%Y")

        # Determine paths
        if current_session.is_admin():
            place = current_session.place_info.get(user_id, current_session.login_place)
            base_path = os.path.join(Config.META_DATA_PATH, place, user_id)
        else:
            place = current_session.login_place
            base_path = os.path.join(
                Config.META_DATA_PATH, current_session.login_place, user_id
            )

        # Create actilife folder for config
        device_path = os.path.join(base_path, Config.ACTILIFE_LABEL)
        os.makedirs(device_path, exist_ok=True)

        # Create config data
        config_file = os.path.join(device_path, Config.CONFIG_DATA)

        # Prepare row data
        row_data = [
            user_id,
            start_date_str,
            end_date_str,
            current_session.login_place,
            "control",
        ]

        # Write to CSV
        with open(config_file, "w", newline="", encoding="utf-8") as f:
            csvwriter = csv.writer(f)
            csvwriter.writerow(Config.ACTILIFE_CONFIG_HEADER)
            csvwriter.writerow(row_data)

        # Upload to S3
        if current_session.is_admin():
            s3_key = f"{place}/{user_id}/{Config.ACTILIFE_LABEL}/{Config.CONFIG_DATA}"
        else:
            s3_key = f"{current_session.login_place}/{user_id}/{Config.ACTILIFE_LABEL}/{Config.CONFIG_DATA}"

        upload_success = S3Operations.upload_to_s3(config_file, s3_key)

        if not upload_success:
            # Cleanup on failure
            if os.path.exists(config_file):
                os.remove(config_file)
            return jsonify(
                {"status": "error", "message": "Failed to upload to S3"}
            ), 500

        # Create VCG and ADL folders
        vcg_folder = os.path.join(device_path, "vcg_prescriptions")
        adl_folder = os.path.join(device_path, "adl_prescriptions")
        os.makedirs(vcg_folder, exist_ok=True)
        os.makedirs(adl_folder, exist_ok=True)

        # Update homerIdDetails with activation info and VCG type
        # Use the resolved `place` (not login_place which is "admin" for global admin)
        data = FileHandler.load_homer_id_details(place)
        user_found = False
        for user in data.get("details", []):
            if user.get("homerID") == user_id:
                user["status"] = "active"
                user["activated"] = True
                user["activation_date"] = start_date_str
                user["end_date"] = end_date_str
                user["vcg_type"] = vcg_type  # Store VCG type here
                user["trackRecord"] = Config.ctrlTrackRecord
                user_found = True
                break

        if not user_found:
            # Add new entry if not found
            data["details"].append(
                {
                    "homerID": user_id,
                    "status": "active",
                    "activated": True,
                    "activation_date": start_date_str,
                    "end_date": end_date_str,
                    "group": "control",
                    "vcg_type": vcg_type,
                    "trackRecord": Config.ctrlTrackRecord,
                }
            )

        # Use resolved place so admin writes to the correct site file
        FileHandler.save_homer_id_details(place, data)

        return jsonify(
            {
                "status": "success",
                "message": "User activated successfully",
                "start_date": start_date_str,
                "end_date": end_date_str,
                "vcg_type": vcg_type,
            }
        ), 200

    except Exception as e:
        print(f"Error activating user: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/delete_patient", methods=["POST"])
def delete_patient():
    """Delete a patient permanently - admin only"""
    try:
        req_data = request.get_json()
        patient_id = req_data.get("patientId")
        password = req_data.get("password")
        reason = req_data.get("reason", "")

        if not patient_id or not password:
            return jsonify(
                {"status": "error", "message": "Patient ID and password required"}
            ), 400

        if not reason:
            return jsonify(
                {"status": "error", "message": "Reason for deletion is required"}
            ), 400

        # Check if user is admin (site admin or global admin can delete)
        if not current_session.is_site_admin():
            return jsonify(
                {"status": "error", "message": "Only admins can delete patients"}
            ), 403

        # Verify password
        admin_password = getattr(Config, "ADMIN_DELETE_PASSWORD", "homeradmin123")
        if password != admin_password:
            print("pass :", password," admin:", admin_password)
            return jsonify({"status": "error", "message": "Invalid password"}), 401

        # Resolve the actual site folder first — for global admin, login_place is "admin"
        # (not a real folder), so we must find the patient's real site before loading.
        actual_place = _resolve_place(patient_id)

        # Load patient data from the correct site file
        homer_data = FileHandler.load_homer_id_details(actual_place)

        # Find and remove patient
        found = False
        if "details" in homer_data:
            original_count = len(homer_data["details"])
            homer_data["details"] = [
                p
                for p in homer_data["details"]
                if p.get("hospitalId") != patient_id and p.get("homerID") != patient_id
            ]
            found = len(homer_data["details"]) < original_count

        if found:
            FileHandler.save_homer_id_details(actual_place, homer_data)

            # Log the deletion with reason before deleting data
            try:
                from routes.auth import log_patient_delete
                log_patient_delete(
                    patient_id=patient_id,
                    reason=reason,
                    deleted_by=current_session.login_place
                )
            except Exception as log_err:
                print(f"Warning: Could not log patient deletion: {log_err}")

            # Delete patient data folder
            patient_folder = os.path.join(
                Config.META_DATA_PATH, actual_place, patient_id
            )
            if os.path.exists(patient_folder):
                try:
                    shutil.rmtree(patient_folder)
                except Exception as e:
                    print(f"Error deleting patient folder: {e}")

            # Clean up patient_events.json - remove timeline, adverse, issues entries
            # so a re-registered patient with same ID starts completely fresh
            try:
                from routes.patient_events import load_events, save_events
                all_events = load_events(actual_place)
                keys_to_remove = [
                    k for k in list(all_events.keys())
                    if k == patient_id
                    or k == f"{patient_id}_adverse"
                    or k == f"{patient_id}_issues"
                ]
                for k in keys_to_remove:
                    del all_events[k]
                save_events(all_events, actual_place)
            except Exception as e:
                print(f"Warning: Could not clean patient events: {e}")

            return jsonify(
                {"status": "success", "message": "Patient deleted successfully"}
            )
        else:
            return jsonify({"status": "error", "message": "Patient not found"}), 404

    except Exception as e:
        print(f"Error deleting patient: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@bp.route("/change_vcg_type", methods=["POST"])
def change_vcg_type():
    """Change VCG type for an activated patient"""
    try:
        data = request.get_json()
        patient_id = data.get("patientId")
        new_vcg_type = data.get("vcgType")

        if not patient_id or not new_vcg_type:
            return jsonify(
                {"status": "error", "message": "Patient ID and VCG type required"}
            ), 400

        # Load patient data
        patient_data = FileHandler.load_homer_id_details(current_session.login_place)

        # Find and update patient
        found = False
        if "details" in patient_data:
            for patient in patient_data["details"]:
                if (
                    patient.get("hospitalId") == patient_id
                    or patient.get("homerID") == patient_id
                ):
                    # Store old VCG type in history
                    old_vcg_type = patient.get("vcg_type") or patient.get("vcgType", "")
                    if "vcgHistory" not in patient:
                        patient["vcgHistory"] = []
                    if old_vcg_type:
                        patient["vcgHistory"].append(
                            {
                                "vcg_type": old_vcg_type,
                                "changedAt": datetime.now().isoformat(),
                            }
                        )
                    # Update to new VCG type (standardized field name)
                    patient["vcg_type"] = new_vcg_type
                    # Remove old field if present
                    patient.pop("vcgType", None)
                    patient["vcgChangedAt"] = datetime.now().isoformat()
                    found = True
                    break

        if found:
            FileHandler.save_homer_id_details(current_session.login_place, patient_data)
            return jsonify(
                {
                    "status": "success",
                    "message": f"VCG type changed to {new_vcg_type.upper()}",
                }
            )
        else:
            return jsonify({"status": "error", "message": "Patient not found"}), 404

    except Exception as e:
        print(f"Error changing VCG type: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route("/activate_experimental_patient", methods=["POST"])
def activate_experimental_patient():
    """Activate an experimental group patient for a specific device.
    
    This is triggered either:
    1. Automatically when cloud data upload is confirmed (called from S3 sync logic)
    2. Manually via the debug 'Manual Activate' button in the UI
    """
    if not current_session.login_place:
        return jsonify({"error": "Not logged in"}), 401

    try:
        req_data = request.get_json()
        homer_id = req_data.get("userID")
        device = req_data.get("device", "").lower()  # "pluto" or "mars" or "both"
        activation_date_str = req_data.get("activationDate", "")  # NEW: user-selected date

        if not homer_id:
            return jsonify({"status": "error", "message": "Missing userID"}), 400

        # Parse user-provided activation date, fall back to config file / today
        user_activation_date = None
        if activation_date_str:
            try:
                user_activation_date = datetime.strptime(activation_date_str, "%Y-%m-%d")
            except ValueError:
                pass

        data = FileHandler.load_homer_id_details(current_session.login_place)

        user_found = False
        for user in data.get("details", []):
            if user.get("homerID") == homer_id:
                if user.get("group") != "experimental":
                    return jsonify({"status": "error", "message": "Patient is not in experimental group"}), 400

                current_status = user.get("status", {})
                if not isinstance(current_status, dict):
                    current_status = {"pluto": "not_activated", "mars": "not_activated"}

                if device == "both" or not device:
                    current_status["pluto"] = "active"
                    current_status["mars"] = "active"
                elif device in ["pluto", "mars"]:
                    current_status[device] = "active"
                else:
                    return jsonify({"status": "error", "message": "Invalid device. Use 'pluto', 'mars', or 'both'"}), 400

                user["status"] = current_status
                # Set activated flag so frontend patient.activated check works
                user["activated"] = True
                if not user.get("timeline_generated"):
                    try:
                        from routes.patient_events import generate_study_events, load_events, save_events

                        # Prefer user-provided activation date, then config file, then today
                        activation_date = user_activation_date

                        if not activation_date:
                            base_path = os.path.join(Config.META_DATA_PATH, current_session.login_place, homer_id)
                            for device_name in ["Pluto", "Mars", "pluto", "mars", "actilife"]:
                                config_path = os.path.join(base_path, device_name, "configdata.csv")
                                if os.path.exists(config_path):
                                    try:
                                        with open(config_path, "r") as f:
                                            reader = csv.DictReader(f)
                                            rows = list(reader)
                                            if rows and rows[0].get("StartDate"):
                                                start_date_str = rows[0].get("StartDate")
                                                activation_date = datetime.strptime(start_date_str, "%d-%m-%Y")
                                                break
                                    except Exception as e:
                                        pass

                        if not activation_date:
                            activation_date = datetime.now()

                        user["activation_date"] = activation_date.strftime("%Y-%m-%d")
                        events = generate_study_events(homer_id, activation_date, "experimental")
                        all_events = load_events(current_session.login_place)
                        all_events[homer_id] = events
                        save_events(all_events, current_session.login_place)
                        user["timeline_generated"] = True
                    except Exception as te:
                        print(f"Warning: Could not generate timeline for {homer_id}: {te}")
                else:
                    # Already generated — update activation_date if user provided one
                    if user_activation_date:
                        user["activation_date"] = user_activation_date.strftime("%Y-%m-%d")

                user_found = True
                break

        if not user_found:
            return jsonify({"status": "error", "message": "Patient not found"}), 404

        FileHandler.save_homer_id_details(current_session.login_place, data)

        # Log patient activation
        try:
            from routes.auth import log_patient_activated
            log_patient_activated(homer_id, activation_date_str or "N/A", "experimental", current_session.login_place)
        except Exception as e:
            print(f"Warning: Could not log patient activation: {e}")

        activated_device_label = device if device and device != "both" else "both devices"
        return jsonify({
            "status": "success",
            "message": f"Patient {homer_id} activated successfully for {activated_device_label}",
        }), 200

    except Exception as e:
        print(f"Error activating experimental patient: {e}")
        return jsonify({"status": "error", "message": f"Server error: {str(e)}"}), 500


@bp.route("/auto_activate_experimental/<patient_id>", methods=["POST"])
def auto_activate_experimental_api(patient_id):
    """Manually trigger auto-activation for an experimental patient.
    This checks if configdata.csv exists and activates the patient if not already active."""
    if not current_session.login_place:
        return jsonify({"status": "error", "message": "Not logged in"}), 401
    
    try:
        place = _resolve_place(patient_id)
        activated = _auto_activate_experimental_patient(patient_id, place)
        
        if activated:
            return jsonify({
                "status": "success",
                "message": f"Patient {patient_id} activated successfully"
            })
        else:
            return jsonify({
                "status": "info",
                "message": f"Patient {patient_id} could not be activated (may already be active or no config data found)"
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ── Exercise catalogue ─────────────────────────────────────────────────────────

_EXERCISES_PATH = Path(__file__).parent.parent / 'config' / 'homer_exercises.json'
_EXERCISE_SS_PATH = Path(__file__).parent.parent / 'EXERCISE_SS'
_exercises_cache: dict = {}

# Screenshot mapping: exercise_id → relative path from EXERCISE_SS/
_SCREENSHOT_MAP = {
    # ADL exercises
    'adl_1': 'ADL_SS/ADL_1.png', 'adl_2': 'ADL_SS/ADL_2.png', 'adl_3': 'ADL_SS/ADL_3.png',
    'adl_4': 'ADL_SS/ADL_4.png', 'adl_5': 'ADL_SS/ADL_5.png', 'adl_6': 'ADL_SS/ADL_6.png',
    'adl_7': 'ADL_SS/ADL_7.png', 'adl_8': 'ADL_SS/ADL_8.png',
    # VCG2 - Unilateral
    'vcg2_uni_1': 'VCG2_SS/VCG2_Unilateral_task_1.png', 'vcg2_uni_2': 'VCG2_SS/VCG2_Unilateral_task_2.png',
    'vcg2_uni_3': 'VCG2_SS/VCG2_Unilateral_task_3.png', 'vcg2_uni_4': 'VCG2_SS/VCG2_Unilateral_task_4.png',
    'vcg2_uni_5': 'VCG2_SS/VCG2_Unilateral_task_5.png', 'vcg2_uni_6': 'VCG2_SS/VCG2_Unilateral_task_6.png',
    'vcg2_uni_7': 'VCG2_SS/VCG2_Unilateral_task_7.png', 'vcg2_uni_8': 'VCG2_SS/VCG2_Unilateral_task_8.png',
    # VCG2 - Bilateral (IDs 9-18, but screenshots are task_1-10)
    'vcg2_bil_9': 'VCG2_SS/VCG2_Bilateral_task_1.png', 'vcg2_bil_10': 'VCG2_SS/VCG2_Bilateral_task_2.png',
    'vcg2_bil_11': 'VCG2_SS/VCG2_Bilateral_task_3.png', 'vcg2_bil_12': 'VCG2_SS/VCG2_Bilateral_task_4.png',
    'vcg2_bil_13': 'VCG2_SS/VCG2_Bilateral_task_5.png', 'vcg2_bil_14': 'VCG2_SS/VCG2_Bilateral_task_6.png',
    'vcg2_bil_15': 'VCG2_SS/VCG2_Bilateral_task_7.png', 'vcg2_bil_16': 'VCG2_SS/VCG2_Bilateral_task_8.png',
    'vcg2_bil_17': 'VCG2_SS/VCG2_Bilateral_task_9.png', 'vcg2_bil_18': 'VCG2_SS/VCG2_Bilateral_task_10.png',
    # VCG3 - Unilateral
    'vcg3_uni_1': 'VCG3_SS/VCG3-Uni-task_1.png', 'vcg3_uni_2': 'VCG3_SS/VCG3-Uni-task_2.png',
    'vcg3_uni_3': 'VCG3_SS/VCG3-Uni-task_3.png', 'vcg3_uni_4': 'VCG3_SS/VCG3-Uni-task_4.png',
    'vcg3_uni_5': 'VCG3_SS/VCG3-Uni-task_5.png', 'vcg3_uni_6': 'VCG3_SS/VCG3-Uni-task_6.png',
    'vcg3_uni_7': 'VCG3_SS/VCG3-Uni-task_7.png', 'vcg3_uni_8': 'VCG3_SS/VCG3-Uni-task_8.png',
    'vcg3_uni_9': 'VCG3_SS/VCG3-Uni-task_9.png', 'vcg3_uni_10': 'VCG3_SS/VCG3-Uni-task_10.png',
    # VCG3 - Bilateral
    'vcg3_bil_1': 'VCG3_SS/VCG3-Bi-task_1.png', 'vcg3_bil_2': 'VCG3_SS/VCG3-Bi-task_2.png',
    'vcg3_bil_3': 'VCG3_SS/VCG3-Bi-task_3.png', 'vcg3_bil_4': 'VCG3_SS/VCG3-Bi-task_4.png',
    'vcg3_bil_5': 'VCG3_SS/VCG3-Bi-task_5.png', 'vcg3_bil_6': 'VCG3_SS/VCG3-Bi-task_6.png',
    'vcg3_bil_7': 'VCG3_SS/VCG3-Bi-task_7.png', 'vcg3_bil_8': 'VCG3_SS/VCG3-Bi-task_8.png',
    'vcg3_bil_9': 'VCG3_SS/VCG3-Bi-task_9.png', 'vcg3_bil_10': 'VCG3_SS/VCG3-Bi-task_10.png',
    'vcg3_bil_11': 'VCG3_SS/VCG3-Bi-task_11.png', 'vcg3_bil_12': 'VCG3_SS/VCG3-Bi-task_12.png',
    # VCG4-5 - Unilateral
    'vcg45_uni_1': 'VCG4-5_SS/VCG4-5-Uni-task_1.png', 'vcg45_uni_2': 'VCG4-5_SS/VCG4-5-Uni-task_2.png',
    'vcg45_uni_3': 'VCG4-5_SS/VCG4-5-Uni-task_3.png', 'vcg45_uni_4': 'VCG4-5_SS/VCG4-5-uni-task_4.png',
    'vcg45_uni_5': 'VCG4-5_SS/VCG4-5-Uni-task_5.png', 'vcg45_uni_6': 'VCG4-5_SS/VCG4-5-Uni-task_6.png',
    'vcg45_uni_7': 'VCG4-5_SS/VCG4-5-Uni-task_7.png', 'vcg45_uni_8': 'VCG4-5_SS/VCG4-5-Uni-task_8.png',
    # VCG4-5 - Bilateral
    'vcg45_bil_1': 'VCG4-5_SS/VCG4-5-Bi-task_1.png', 'vcg45_bil_2': 'VCG4-5_SS/VCG4-5-Bi-task_2.png',
    'vcg45_bil_3': 'VCG4-5_SS/VCG4-5-Bi-task_3.png', 'vcg45_bil_4': 'VCG4-5_SS/VCG4-5-Bi-task_4.png',
    'vcg45_bil_5': 'VCG4-5_SS/VCG4-5-Bi-task_5.png', 'vcg45_bil_6': 'VCG4-5_SS/VCG4-5-Bi-task_6.png',
    'vcg45_bil_7': 'VCG4-5_SS/VCG4-5-Bi-task_7.png', 'vcg45_bil_8': 'VCG4-5_SS/VCG4-5-Bi-task_8.png',
    'vcg45_bil_9': 'VCG4-5_SS/VCG4-5-Bi-task_9.png', 'vcg45_bil_10': 'VCG4-5_SS/VCG4-5-Bi-task_10.png',
    'vcg45_bil_11': 'VCG4-5_SS/VCG4-5-Bi-task_11.png', 'vcg45_bil_12': 'VCG4-5_SS/VCG4-5-Bi-task_12.png',
    'vcg45_bil_13': 'VCG4-5_SS/VCG4-5-Bi-task_13.png', 'vcg45_bil_14': 'VCG4-5_SS/VCG4-5-Bi-task_14.png',
    'vcg45_bil_15': 'VCG4-5_SS/VCG4-5-Bi-task_15.png', 'vcg45_bil_16': 'VCG4-5_SS/VCG4-5-Bi-task_16.png',
    'vcg45_bil_17': 'VCG4-5_SS/VCG4-5-Bi-task_17.png', 'vcg45_bil_18': 'VCG4-5_SS/VCG4-5-Bi-task_18.png',
    'vcg45_bil_19': 'VCG4-5_SS/VCG4-5-Bi-task_19.png',
}


def _load_exercises() -> dict:
    global _exercises_cache
    if not _exercises_cache:
        try:
            with open(_EXERCISES_PATH, encoding='utf-8') as f:
                _exercises_cache = json.load(f)
        except Exception:
            _exercises_cache = {}
    return _exercises_cache


@bp.route('/api/exercises', methods=['GET'])
def api_exercises():
    """Return exercise list from homer_exercises.json.
    ?type=adl           → ADL exercises
    ?type=vcg&group=vcg3 → VCG exercises for a specific group
    """
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    ex_type = request.args.get('type', 'adl')
    group   = request.args.get('group', '')
    data    = _load_exercises()
    if ex_type == 'adl':
        return jsonify(data.get('adl', {}).get('exercises', []))
    if ex_type == 'vcg':
        vcg = data.get('vcg', {})
        if group not in vcg:
            return jsonify({'error': f'Unknown VCG group: {group}'}), 400
        return jsonify(vcg[group].get('exercises', []))
    return jsonify({'error': 'type must be adl or vcg'}), 400


# ── Prescription file helpers ──────────────────────────────────────────────────

_PRESCRIPTION_FILES = {
    'adl_prescription_d01': 'adl/adl_prescription_d01.json',
    'adl_prescription_d15': 'adl/adl_prescription_d15.json',
    'vcg_prescription_d01': 'vcg_exercise/vcg_prescription_d01.json',
    'vcg_prescription_d15': 'vcg_exercise/vcg_prescription_d15.json',
}


def _write_prescription(folder: str, homer_id: str, rel_path: str, content: dict) -> None:
    if Config.USE_S3:
        from utils.s3_store import s3_write_json
        s3_write_json(f"{folder}/patients/{homer_id}/{rel_path}", content)
        return
    path = get_patients_path(folder) / homer_id / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(content, f, indent=2)
    os.replace(tmp, path)


def _read_prescription(folder: str, homer_id: str, rel_path: str):
    if Config.USE_S3:
        from utils.s3_store import s3_read_json
        return s3_read_json(f"{folder}/patients/{homer_id}/{rel_path}")
    path = get_patients_path(folder) / homer_id / rel_path
    if not path.exists():
        return None
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


@bp.route('/api/patients/<homer_id>/prescription/<event_id>', methods=['GET'])
def api_get_prescription(homer_id, event_id):
    """Return an existing prescription file (used to pre-populate d15 revision modals)."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404
    rel_path = _PRESCRIPTION_FILES.get(event_id)
    if not rel_path:
        return jsonify({'error': 'Unknown prescription event'}), 400
    data = _read_prescription(folder, homer_id, rel_path)
    if data is None:
        return jsonify({'error': 'Prescription not found'}), 404
    return jsonify(data)


# ── Prescription pamphlet helpers ──────────────────────────────────────────────

def _make_qr_b64(url: str) -> str:
    """Generate QR code image as base64 data URI."""
    if not url or url.strip() == '':
        return ''
    try:
        qr = qrcode.QRCode(version=1, box_size=4, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ''


def _make_screenshot_b64(exercise_id: str) -> str:
    """Read exercise screenshot and return as base64 string. Tries .png then .jpg."""
    rel = _SCREENSHOT_MAP.get(exercise_id)
    if not rel:
        return ''
    candidates = [rel, rel[:-4] + '.jpg'] if rel.lower().endswith('.png') else [rel]
    if Config.USE_S3:
        from utils.s3_store import s3_get_bytes
        for candidate in candidates:
            data = s3_get_bytes(f'EXERCISE_SS/{candidate}')
            if data:
                try:
                    return base64.b64encode(data).decode()
                except Exception:
                    return ''
        return ''
    for candidate in candidates:
        path = _EXERCISE_SS_PATH / candidate
        if path.exists():
            try:
                return base64.b64encode(path.read_bytes()).decode()
            except Exception:
                return ''
    return ''


def _get_field_labels(language: str) -> dict:
    """Get translated labels for exercise fields."""
    labels = {
        'english': {
            'description': 'Description',
            'dosage': 'Dosage',
            'items': 'Items Needed',
            'adl_section': 'Activities of Daily Living (ADL)',
            'vcg_section': 'Virtual Center of Gravity (VCG)',
            'scan_video': 'Scan for Video',
            'video_instruction': 'Watch the exercise video using your smartphone camera',
        },
        'tamil': {
            'description': 'விளக்கம்',
            'dosage': 'தீவிரம்',
            'items': 'தேவையான பொருட்கள்',
            'adl_section': 'நாளாந்த வாழ்க்கை நடவடிக்கைகள் (ADL)',
            'vcg_section': 'மெய்ம் ஈர்ப்பு மையம் (VCG)',
            'scan_video': 'வீடியோவுக்கு ஸ்கேன் செய்யவும்',
            'video_instruction': 'உங்கள் ஸ்மார்ட்ஃபோன் கேமிரா ஐப் பயன்படுத்தி பயிற்சி வீடியோவைப் பாருங்கள்',
        },
        'telugu': {
            'description': 'వివరణ',
            'dosage': 'మోతాదు',
            'items': 'అవసరమైన వస్తువులు',
            'adl_section': 'రోజువారీ జీవన కార్యకలాపాలు (ADL)',
            'vcg_section': 'వర్చువల్ గురుత్వాకర్షణ కేంద్రం (VCG)',
            'scan_video': 'వీడియో కోసం స్కాన్ చేయండి',
            'video_instruction': 'మీ స్మార్ట్‌ఫోన్ కెమెరా ఉపయోగించి వ్యాయామ వీడియోను చూడండి',
        },
        'kannada': {
            'description': 'ವಿವರಣೆ',
            'dosage': 'ಮಾತ್ರೆ',
            'items': 'ಬೇಕಾದ ವಸ್ತುಗಳು',
            'adl_section': 'ದೈನಂದಿನ ಜೀವನ ಚಟುವಟಿಕೆಗಳು (ADL)',
            'vcg_section': 'ವರ್ಚುವಲ್ ಗುರುತ್ವಾಕರ್ಷಣ ಕೇಂದ್ರ (VCG)',
            'scan_video': 'ವೀಡಿಯೋಗಾಗಿ ಸ್ಕ್ಯಾನ್ ಮಾಡಿ',
            'video_instruction': 'ನಿಮ್ಮ ಸ್ಮಾರ್ಟ್‌ಫೋನ್ ಕ್ಯಾಮೆರಾವನ್ನು ಬಳಸಿ ವ್ಯಾಯಾಮ ವೀಡಿಯೋವನ್ನು ವೀಕ್ಷಿಸಿ',
        },
        'hindi': {
            'description': 'विवरण',
            'dosage': 'खुराक',
            'items': 'आवश्यक वस्तुएं',
            'adl_section': 'दैनिक जीवन कार्यकलाप (ADL)',
            'vcg_section': 'वर्चुअल गुरुत्व केंद्र (VCG)',
            'scan_video': 'वीडियो के लिए स्कैन करें',
            'video_instruction': 'अपने स्मार्टफोन कैमरे का उपयोग करके व्यायाम वीडियो देखें',
        },
        'punjabi': {
            'description': 'ਵਰਣਨ',
            'dosage': 'ਖੁਰਾਕ',
            'items': 'ਲੋੜੀਂਦੀਆਂ ਵਸਤੂਆਂ',
            'adl_section': 'ਰੋਜ਼ਾਨਾ ਜੀਵਨ ਦੀਆਂ ਗਤੀਵਿਧੀਆਂ (ADL)',
            'vcg_section': 'ਵਰਚੁਅਲ ਗੁਰੁਤਾ ਕੇਂਦਰ (VCG)',
            'scan_video': 'ਵੀਡੀਓ ਲਈ ਸਕੈਨ ਕਰੋ',
            'video_instruction': 'ਆਪਣੇ ਸਮਾਰਟ ਫੋਨ ਕੈਮਰੇ ਦੀ ਵਰਤੋਂ ਕਰਕੇ ਅਭਿਆਸ ਵੀਡੀਓ ਦੇਖੋ',
        },
    }
    return labels.get(language, labels['english'])


def _get_exercise_text(exercise: dict, language: str) -> dict:
    """Extract exercise text in the requested language, with English fallback."""
    if language == 'english' or language not in exercise:
        return {
            'name':        exercise.get('name', ''),
            'description': exercise.get('description', ''),
            'dosage':      exercise.get('dosage', ''),
            'items':       exercise.get('items', ''),
        }
    lang_block = exercise.get(language, {})
    return {
        'name':        lang_block.get('name')        or exercise.get('name', ''),
        'description': lang_block.get('description') or exercise.get('description', ''),
        'dosage':      lang_block.get('dosage')      or exercise.get('dosage', ''),
        'items':       lang_block.get('items')       or exercise.get('items', ''),
    }


@bp.route('/api/patients/<homer_id>/prescription-pamphlet', methods=['GET'])
def api_prescription_pamphlet(homer_id):
    """Generate and return HTML pamphlet for prescribed exercises in requested language."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401

    event_id = request.args.get('event_id')
    language = request.args.get('language', 'english')

    if not event_id:
        return jsonify({'error': 'Missing event_id'}), 400

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    # Load all exercises
    all_exercises = _load_exercises()

    # Determine which day (d01 or d15) from protocol_events
    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return jsonify({'error': 'Protocol events not found'}), 404

    day_match = None
    prescribed_date = None
    for section in ['incomplete', 'complete']:
        for entry in events_data.get(section, []):
            if entry.get('id') == event_id:
                proto_id = entry.get('protocol_event_id', '')
                if 'd15' in proto_id:
                    day_match = 'd15'
                else:
                    day_match = 'd01'
                # Get the date: use completion_date if available, else use scheduled_date
                prescribed_date = entry.get('completion_date') or (entry.get('scheduled_date', ['', ''])[0] if entry.get('scheduled_date') else '')
                break
        if day_match:
            break

    if not day_match:
        day_match = 'd01'  # Default to d01 if not found

    # Read ADL prescription
    adl_exercises_list = []
    adl_rel_path = f'adl/adl_prescription_{day_match}.json'
    adl_data = _read_prescription(folder, homer_id, adl_rel_path)
    if adl_data and adl_data.get('prescribed_exercises'):
        adl_lib = all_exercises.get('adl', {}).get('exercises', [])
        for presc in adl_data['prescribed_exercises']:
            ex_id = presc.get('exercise_id')
            ex = next((e for e in adl_lib if e.get('id') == ex_id), None)
            if ex:
                text = _get_exercise_text(ex, language)
                qr = _make_qr_b64(ex.get('youtube_url', ''))
                screenshot = _make_screenshot_b64(ex_id)
                adl_exercises_list.append({
                    'name': text['name'],
                    'description': text['description'],
                    'dosage': text['dosage'],
                    'items': text['items'],
                    'screenshot': screenshot,
                    'qr_code': qr,
                })

    # Read VCG prescription
    vcg_exercises_list = []
    vcg_rel_path = f'vcg_exercise/vcg_prescription_{day_match}.json'
    vcg_data = _read_prescription(folder, homer_id, vcg_rel_path)
    if vcg_data and vcg_data.get('prescribed_exercises'):
        # Determine VCG group from the data if available, default to vcg2
        vcg_group = vcg_data.get('vcg_group', 'vcg2')
        vcg_lib = all_exercises.get('vcg', {}).get(vcg_group, {}).get('exercises', [])
        for presc in vcg_data['prescribed_exercises']:
            ex_id = presc.get('exercise_id')
            ex = next((e for e in vcg_lib if e.get('id') == ex_id), None)
            if ex:
                text = _get_exercise_text(ex, language)
                qr = _make_qr_b64(ex.get('youtube_url', ''))
                screenshot = _make_screenshot_b64(ex_id)
                vcg_exercises_list.append({
                    'name': text['name'],
                    'description': text['description'],
                    'dosage': text['dosage'],
                    'items': text['items'],
                    'screenshot': screenshot,
                    'qr_code': qr,
                })

    labels = _get_field_labels(language)

    return render_template(
        'prescription_pamphlet.html',
        patient_id=homer_id,
        prescribed_date=prescribed_date,
        adl_exercises=adl_exercises_list,
        vcg_exercises=vcg_exercises_list,
        language=language,
        labels=labels
    )


@bp.route('/api/patients/<homer_id>/agwatch-timing/<protocol_event_id>', methods=['GET'])
def api_get_agwatch_timing(homer_id, protocol_event_id):
    """Return a saved agwatch timing file."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    cfg = _AGWATCH_TIMING_CONFIG.get(protocol_event_id)
    if not cfg:
        return jsonify({'error': 'Unknown agwatch timing event'}), 400
    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404
    if Config.USE_S3:
        from utils.s3_store import s3_read_json
        data = s3_read_json(f"{folder}/patients/{homer_id}/{cfg['timing_file']}")
        if data is None:
            return jsonify({'error': 'Timing file not found'}), 404
        return jsonify(data)
    path = get_patients_path(folder) / homer_id / cfg['timing_file']
    if not path.exists():
        return jsonify({'error': 'Timing file not found'}), 404
    with open(path, encoding='utf-8') as f:
        return jsonify(json.load(f))


# Maps prescription event_id → the completed event whose completion_date it inherits
_PRESCRIPTION_DATE_SOURCE = {
    'adl_prescription_d01': 'activation',
    'vcg_prescription_d01': 'activation',
    'adl_prescription_d15': 'home_visit_d15',
    'vcg_prescription_d15': 'home_visit_d15',
}


def _complete_prescription_event(folder, homer_id, event_id, presc_file,
                                  loginid, session_id, extra_fields, log_msg):
    """Move a prescription event from incomplete→complete and write the prescription file."""
    events_data = read_protocol_events(folder, homer_id)
    if not events_data:
        return False, 'Protocol events not found.'

    incomplete = events_data.get('incomplete', [])
    entry = next(
        (e for e in incomplete
         if e['protocol_event_id'] == event_id
         and (extra_fields.get('_event_uuid') is None
              or e['id'] == extra_fields.get('_event_uuid'))),
        None
    )
    if not entry:
        return False, f'{event_id} not found in incomplete list.'

    # completion_date is copied from the reference event (activation or home_visit_d15)
    ref_event_id = _PRESCRIPTION_DATE_SOURCE.get(event_id)
    ref_event = next(
        (e for e in events_data.get('complete', [])
         if e.get('protocol_event_id') == ref_event_id),
        None
    )
    if not ref_event:
        return False, f'Reference event {ref_event_id} not found in complete list.'
    completion_date = ref_event['completion_date']

    filed_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    complete_entry = {
        **entry,
        'completion_date':   completion_date,
        'filed_at':          filed_at,
        'filed_by':   _filer(),
        'prescription_file': presc_file,
    }
    events_data['incomplete'] = [e for e in incomplete if e['id'] != entry['id']]
    events_data.setdefault('complete', []).append(complete_entry)
    write_protocol_events(folder, homer_id, events_data)
    write_patient_log(folder, homer_id, loginid, session_id, log_msg, presc_file)
    return True, None


@bp.route('/api/patients/<homer_id>/adl-prescription', methods=['POST'])
def api_adl_prescription(homer_id):
    """Complete adl_prescription_d01 or adl_prescription_d15."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    body       = request.get_json() or {}
    event_uuid = body.get('event_id')
    event_id   = body.get('protocol_event_id', '').strip()
    exercises  = body.get('exercises', [])
    notes      = body.get('notes', '').strip()

    if event_id not in ('adl_prescription_d01', 'adl_prescription_d15'):
        return jsonify({'error': 'protocol_event_id must be adl_prescription_d01 or adl_prescription_d15'}), 400
    if not exercises:
        return jsonify({'error': 'At least one exercise is required.'}), 400
    for ex in exercises:
        if not ex.get('exercise_id'):
            return jsonify({'error': 'Each exercise must have an exercise_id.'}), 400
        if not ex.get('blocks') or not ex.get('repetitions'):
            return jsonify({'error': 'Each exercise must have blocks and repetitions.'}), 400

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)
    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    presc_file = _PRESCRIPTION_FILES[event_id]
    log_msg    = 'ADL prescription recorded' if event_id == 'adl_prescription_d01' else 'ADL prescription revised'

    presc_data = {
        'filed_at':             filed_at,
        'filed_by':             loginid,
        'prescribed_exercises': exercises,
        'notes':                notes,
    }
    _write_prescription(folder, homer_id, presc_file, presc_data)

    ok, err = _complete_prescription_event(
        folder, homer_id, event_id, presc_file, loginid, session_id,
        {'_event_uuid': event_uuid}, log_msg
    )
    if not ok:
        return jsonify({'error': err}), 404

    return jsonify({'ok': True})


@bp.route('/api/patients/<homer_id>/vcg-prescription', methods=['POST'])
def api_vcg_prescription(homer_id):
    """Complete vcg_prescription_d01 or vcg_prescription_d15."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'therapist'):
        return jsonify({'error': 'Forbidden'}), 403

    folder = find_patient_folder(flask_session['login_place'], homer_id)
    if not folder:
        return jsonify({'error': 'Patient not found'}), 404

    body       = request.get_json() or {}
    event_uuid = body.get('event_id')
    event_id   = body.get('protocol_event_id', '').strip()
    exercises  = body.get('exercises', [])
    notes      = body.get('notes', '').strip()

    if event_id not in ('vcg_prescription_d01', 'vcg_prescription_d15'):
        return jsonify({'error': 'protocol_event_id must be vcg_prescription_d01 or vcg_prescription_d15'}), 400
    if not exercises:
        return jsonify({'error': 'At least one exercise is required.'}), 400
    for ex in exercises:
        if not ex.get('exercise_id'):
            return jsonify({'error': 'Each exercise must have an exercise_id.'}), 400
        if not ex.get('blocks') or not ex.get('repetitions'):
            return jsonify({'error': 'Each exercise must have blocks and repetitions.'}), 400

    patient = read_patient_meta(folder, homer_id)
    vcg_group = (patient or {}).get('vcgGroup', '')
    if not vcg_group:
        return jsonify({'error': 'Patient has no VCG group assigned.'}), 409

    loginid    = flask_session.get('loginid', 'unknown')
    session_id = flask_session.get('session_id', -1)
    filed_at   = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    presc_file = _PRESCRIPTION_FILES[event_id]
    log_msg    = 'VCG prescription recorded' if event_id == 'vcg_prescription_d01' else 'VCG prescription revised'

    presc_data = {
        'filed_at':             filed_at,
        'filed_by':             loginid,
        'vcg_group':            vcg_group,
        'prescribed_exercises': exercises,
        'notes':                notes,
    }
    _write_prescription(folder, homer_id, presc_file, presc_data)

    ok, err = _complete_prescription_event(
        folder, homer_id, event_id, presc_file, loginid, session_id,
        {'_event_uuid': event_uuid}, log_msg
    )
    if not ok:
        return jsonify({'error': err}), 404

    return jsonify({'ok': True})
