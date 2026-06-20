from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify
from models.user import current_session
from utils.data_access import get_patients_for_user, derive_status, iter_patients_with_folder
from utils.protocol_events import read_protocol_events, load_study_protocol

bp = Blueprint('dashboard', __name__)

_AE_FOLLOWUP_LABELS = {
    'adverse_event_followup':        'Follow-up Call',
    'adverse_event_followup_visit':  'Follow-up Visit',
    'adverse_event_clinical_visit':  'Clinical Visit',
}


def _wdu_event_name(entry, fallback='AG Watch Data Upload'):
    """Per-entry display name for a watch_data_upload event: limb + watch id, so the
    right/left tasks are distinguishable. Kept in sync with the same helper in
    routes/user_management.py."""
    limb = (entry.get('limb') or '').title()
    wid  = entry.get('watch_id') or ''
    return f"AG Watch Data Upload — {limb} ({wid})" if (limb or wid) else fallback


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


@bp.route('/api/dashboard/stats', methods=['GET'])
def stats():
    """Return patient counts for the dashboard stat bubbles."""
    if not current_session.login_place:
        return jsonify({'error': 'Not authenticated'}), 401

    patients = get_patients_for_user(current_session.login_place)

    statuses = [derive_status(p) for p in patients]

    return jsonify({
        'total':              len(patients),
        'experimental':       sum(1 for p in patients if p.get('group') == 'experimental'),
        'control':            sum(1 for p in patients if p.get('group') == 'control'),
        'unassigned':         sum(1 for s in statuses if s == 'unassigned'),
        'inactive':           sum(1 for s in statuses if s == 'inactive'),
        'active':             sum(1 for s in statuses if s == 'active'),
        'paused':             sum(1 for s in statuses if s == 'paused'),
        'post_training':      sum(1 for s in statuses if s == 'post_training'),
        'training_completed': sum(1 for s in statuses if s == 'training_completed'),
        'a1_completed':       sum(1 for s in statuses if s == 'a1_completed'),
        'all_completed':      sum(1 for s in statuses if s == 'all_completed'),
        'pre_discontinued':   sum(1 for s in statuses if s == 'pre_discontinued'),
        'broken_protocol':    sum(1 for s in statuses if s == 'broken_protocol'),
        'discontinued':       sum(1 for s in statuses if s == 'discontinued'),
    })


@bp.route('/api/dashboard/events', methods=['GET'])
def events():
    """Return overdue and upcoming (next 7 days) protocol events across all visible patients."""
    if not current_session.login_place:
        return jsonify({'error': 'Not authenticated'}), 401

    protocol = load_study_protocol()

    # Build flat event_names for display (merge all sections; names don't conflict)
    event_names = {}
    for section in ('experimental', 'control', 'shared'):
        for e in protocol.get(section, []):
            event_names[e['id']] = e['name']
    event_names['training_pause_followup'] = 'Training Pause Follow-up'
    event_names['schedule_a1_call']        = 'Schedule A1 Assessment'
    event_names['schedule_a2_call']        = 'Schedule A2 Assessment'
    event_names['device_return']           = 'Device Return'
    event_names['watch_data_upload']       = 'AG Watch Data Upload'

    # Build per-group event_defs so depends_on is looked up against the correct
    # group definition (e.g. activation has different depends_on per group).
    group_defs = {}
    for grp in ('experimental', 'control'):
        defs = {}
        for e in protocol.get('shared', []):
            defs[e['id']] = e
        for e in protocol.get(grp, []):
            defs[e['id']] = e
        defs['training_pause_followup'] = {'name': 'Training Pause Follow-up', 'depends_on': []}
        defs['device_return']           = {'name': 'Device Return',            'depends_on': []}
        defs['watch_data_upload']       = {'name': 'AG Watch Data Upload',     'depends_on': []}
        group_defs[grp] = defs

    # Merged defs for topo sort (experimental preferred — stricter depends_on).
    # Ordering within a date is cosmetic; correctness comes from blocked_by above.
    topo_defs = {**group_defs.get('control', {}), **group_defs.get('experimental', {})}

    # A1/A2 window definitions (used to precompute per-patient window dates)
    _assessment_defs = {}
    for _s in protocol.get('shared', []):
        if _s['id'] in ('a1_assessment', 'a2_assessment'):
            _assessment_defs[_s['id']] = _s

    terminal = {'discontinued', 'pre_discontinued', 'all_completed'}
    today = date.today()
    overdue  = []
    upcoming = []

    for hospital_folder, homer_id, patient in iter_patients_with_folder(current_session.login_place):
        if derive_status(patient) in terminal:
            continue
        events_data = read_protocol_events(hospital_folder, homer_id)
        if not events_data:
            continue

        # For broken_protocol patients: show discontinuation reminder + open AE follow-up stubs only
        if derive_status(patient) == 'broken_protocol':
            _BP_INTERACTIVE = frozenset({
                'adverse_event', 'adverse_event_followup',
                'adverse_event_followup_visit', 'adverse_event_clinical_visit',
                'device_return',
                'watch_data_upload',
            })
            ae_alias_map_bp = {
                e['id']: e['alias']
                for e in events_data.get('free', {}).get('adverse_event', [])
                if e.get('alias')
            }
            for entry in events_data.get('incomplete', []):
                pid = entry.get('protocol_event_id')
                if pid not in _BP_INTERACTIVE:
                    continue
                sched = entry.get('scheduled_date')
                if not sched or not isinstance(sched, list) or len(sched) < 2:
                    continue
                try:
                    end_dt = datetime.fromisoformat(sched[1]).date()
                except Exception:
                    continue
                if pid in _AE_FOLLOWUP_LABELS:
                    ae_ids  = entry.get('adverse_event_ids') or []
                    aliases = [ae_alias_map_bp[aid] for aid in ae_ids if aid in ae_alias_map_bp]
                    ev_name = f"{_AE_FOLLOWUP_LABELS[pid]}: {', '.join(aliases)}" if aliases else _AE_FOLLOWUP_LABELS[pid]
                elif pid == 'watch_data_upload':
                    ev_name = _wdu_event_name(entry)
                else:
                    ev_name = event_names.get(pid, pid)
                overdue.append({
                    'id':                entry['id'],
                    'protocol_event_id': pid,
                    'homer_id':          homer_id,
                    'event_name':        ev_name,
                    'scheduled_date':    sched,
                    'days':              (end_dt - today).days,
                    'active_window':     end_dt >= today,
                    'blocked_by':        [],
                })
            if not events_data.get('free', {}).get('discontinuation'):
                broken_date = patient.get('brokenProtocolDate') or today.isoformat()
                try:
                    broken_sched = datetime.fromisoformat(broken_date).date()
                except Exception:
                    broken_sched = today
                overdue.append({
                    'id':                'discontinuation_reminder',
                    'protocol_event_id': 'discontinuation_reminder',
                    'homer_id':          homer_id,
                    'event_name':        'Discontinue Patient',
                    'scheduled_date':    [broken_date, broken_date],
                    'days':              (broken_sched - today).days,
                    'active_window':     False,
                    'blocked_by':        [],
                })
            continue

        # For paused patients: live check if D02/D03 window has already passed → treat as broken protocol
        if derive_status(patient) == 'paused':
            completed_ids_paused = {e['protocol_event_id'] for e in events_data.get('complete', [])}
            d0203_missed = False
            for visit_id in ('home_visit_d02', 'home_visit_d03'):
                if visit_id in completed_ids_paused:
                    continue
                inc_entry = next((e for e in events_data.get('incomplete', [])
                                  if e.get('protocol_event_id') == visit_id), None)
                if not inc_entry:
                    continue
                sd = inc_entry.get('scheduled_date')
                if not sd or sd[1] is None:
                    continue
                try:
                    end_date = datetime.fromisoformat(sd[1]).date()
                except (ValueError, TypeError):
                    continue
                if end_date < today:
                    d0203_missed = True
                    break
            if d0203_missed and not events_data.get('free', {}).get('discontinuation'):
                broken_date = today.isoformat()
                overdue.append({
                    'id':                'discontinuation_reminder',
                    'protocol_event_id': 'discontinuation_reminder',
                    'homer_id':          homer_id,
                    'event_name':        'Discontinue Patient',
                    'scheduled_date':    [broken_date, broken_date],
                    'days':              0,
                    'blocked_by':        [],
                })
                continue

        completed_ids = {e['protocol_event_id'] for e in events_data.get('complete', [])}
        # Free-event types (e.g. watch_record) count as completed once at least
        # one entry has been filed, so depends_on can reference them. Kept in
        # sync with the same rule in routes/user_management.py.
        for free_type, free_list in (events_data.get('free') or {}).items():
            if free_list:
                completed_ids.add(free_type)
        known_ids     = completed_ids | {e['protocol_event_id'] for e in events_data.get('incomplete', [])}
        patient_defs  = group_defs.get(patient.get('group', ''), {})
        ae_alias_map  = {
            e['id']: e['alias']
            for e in events_data.get('free', {}).get('adverse_event', [])
            if e.get('alias')
        }

        _PAUSE_VISIBLE = frozenset({
            'adverse_event', 'adverse_event_followup', 'adverse_event_followup_visit',
            'adverse_event_clinical_visit',
            'robot_issue_call', 'robot_issue_visit', 'resolve_robot_issue_visit',
            'other_device_issue_call', 'other_device_issue_visit',
            'training_completion_d29',
            'device_return',
            'watch_data_upload',
        })
        _DISCONTINUED_VISIBLE = frozenset({
            'adverse_event', 'adverse_event_followup',
            'adverse_event_followup_visit', 'adverse_event_clinical_visit',
            'a1_assessment', 'a2_assessment',
            'schedule_a1_call', 'schedule_a2_call',
            'device_return',
            'watch_data_upload',
        })
        _POST_TRAINING_VISIBLE = frozenset({
            'training_completion_d29',
            'adverse_event', 'adverse_event_followup',
            'adverse_event_followup_visit', 'adverse_event_clinical_visit',
            'a1_assessment', 'a2_assessment',
            'schedule_a1_call', 'schedule_a2_call',
            'device_return',
            'watch_data_upload',
        })
        _TRAINING_COMPLETED_VISIBLE = frozenset({
            'adverse_event', 'adverse_event_followup',
            'adverse_event_followup_visit', 'adverse_event_clinical_visit',
            'a1_assessment', 'a2_assessment',
            'schedule_a1_call', 'schedule_a2_call',
            'device_return',
            'watch_data_upload',
        })
        # After device_return is completed: only AE chains and assessments remain visible.
        # Training is fully over, only post-training follow-ups shown.
        _POST_DEVICE_RETURN_VISIBLE = frozenset({
            'adverse_event', 'adverse_event_followup',
            'adverse_event_followup_visit', 'adverse_event_clinical_visit',
            'a1_assessment', 'a2_assessment',
            'schedule_a1_call', 'schedule_a2_call',
        })
        is_paused             = bool(patient.get('trainingPausedDate'))
        is_discontinued       = bool(patient.get('discontinuationDate'))
        is_post_training      = (derive_status(patient) == 'post_training')
        is_training_completed = (derive_status(patient) == 'training_completed')
        is_a1_completed       = (derive_status(patient) == 'a1_completed')
        is_all_completed      = (derive_status(patient) == 'all_completed')
        # Check if device_return has been completed
        is_device_return_completed = bool(
            is_training_completed and
            any(e.get('protocol_event_id') == 'device_return' for e in events_data.get('complete', []))
        )

        # Precompute A1/A2 window dates for this patient
        _pt_assessment_windows = {}
        if patient.get('activationDate'):
            try:
                _act_dt = datetime.fromisoformat(patient['activationDate']).date()
                for _pid, _def in _assessment_defs.items():
                    _win = _def.get('window')
                    if _win:
                        _ws = _act_dt + timedelta(days=_win['start_day'] - 1)
                        _we = _act_dt + timedelta(days=_win['end_day'] - 1)
                        _pt_assessment_windows[_pid] = (_ws.isoformat(), _we.isoformat())
            except Exception:
                pass

        _ASSESSMENT_PIDS = frozenset({'a1_assessment', 'a2_assessment'})

        for entry in events_data.get('incomplete', []):
            pid   = entry.get('protocol_event_id')
            sched = entry.get('scheduled_date')

            if not sched or not isinstance(sched, list) or len(sched) < 2:
                # Assessment events shown even without a scheduled appointment.
                if pid not in _ASSESSMENT_PIDS or pid not in _pt_assessment_windows:
                    continue
                _ws_str, _we_str = _pt_assessment_windows[pid]
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
                # Assessment events: override categorisation bounds with window dates
                if pid in _ASSESSMENT_PIDS and pid in _pt_assessment_windows:
                    try:
                        _ws_str, _we_str = _pt_assessment_windows[pid]
                        start_date = datetime.fromisoformat(_ws_str).date()
                        end_date   = datetime.fromisoformat(_we_str).date()
                    except Exception:
                        pass

            # A2 assessment completed (all_completed): no overdue events shown.
            if is_all_completed:
                continue

            # After device_return completed or A1 assessment completed: only AE chains and assessments remain visible.
            if (is_device_return_completed or is_a1_completed) and pid not in _POST_DEVICE_RETURN_VISIBLE:
                continue

            if is_training_completed and not is_device_return_completed and pid not in _TRAINING_COMPLETED_VISIBLE:
                continue

            if is_discontinued and pid not in _DISCONTINUED_VISIBLE:
                continue

            if is_post_training and pid not in _POST_TRAINING_VISIBLE:
                continue

            on_hold = is_paused and pid not in _PAUSE_VISIBLE and start_date <= today

            dep_ids    = patient_defs.get(pid, {}).get('depends_on') or []
            blocked_by = []
            for d in dep_ids:
                if d not in known_ids:
                    continue
                # For assessments, check if appointment is scheduled or call is completed
                if pid in ('a1_assessment', 'a2_assessment') and d in ('schedule_a1_call', 'schedule_a2_call'):
                    if entry.get('appointment_date') or d in completed_ids:
                        continue  # Dependency satisfied
                elif d in completed_ids:
                    continue  # Dependency satisfied for all other events
                blocked_by.append(event_names.get(d, d))

            if pid in _AE_FOLLOWUP_LABELS:
                ae_ids   = entry.get('adverse_event_ids') or []
                aliases  = [ae_alias_map[aid] for aid in ae_ids if aid in ae_alias_map]
                ev_name  = f"{_AE_FOLLOWUP_LABELS[pid]}: {', '.join(aliases)}" if aliases else _AE_FOLLOWUP_LABELS[pid]
            elif pid == 'watch_data_upload':
                ev_name  = _wdu_event_name(entry)
            else:
                ev_name  = event_names.get(pid, pid)

            record = {
                'id':                entry['id'],
                'protocol_event_id': pid,
                'homer_id':          homer_id,
                'event_name':        ev_name,
                'scheduled_date':    sched,
                'blocked_by':        blocked_by,
            }
            if pid in _ASSESSMENT_PIDS and pid in _pt_assessment_windows:
                _ws_str, _we_str = _pt_assessment_windows[pid]
                record['window_start'] = _ws_str
                record['window_end']   = _we_str
            if entry.get('training_stopped'):
                record['training_stopped'] = True

            if on_hold:
                # On-hold events never appear in the dashboard upcoming list
                # (dashboard only shows events due within 7 days; on-hold ones are not actionable)
                continue
            elif start_date > today:
                diff = (start_date - today).days
                if diff <= 7:
                    record['days'] = diff
                    record['active_window'] = False
                    upcoming.append(record)
            elif end_date >= today:
                record['days'] = (end_date - today).days
                record['active_window'] = True
                overdue.append(record)
            else:
                record['days'] = (end_date - today).days  # negative
                record['active_window'] = False
                overdue.append(record)

    # Active-window first, then past-due; within each sub-group sort by end date
    # and topo-sort within same-end-date groups so parents appear before dependents.
    end_date_fn = lambda ev: (ev['scheduled_date'] or ['', ''])[1][:10]
    active_overdue = sorted([e for e in overdue if e.get('active_window')],     key=end_date_fn)
    past_overdue   = sorted([e for e in overdue if not e.get('active_window')], key=end_date_fn)
    overdue  = _apply_ordering_rules(
        _topo_sort(active_overdue, topo_defs, end_date_fn) +
        _topo_sort(past_overdue,   topo_defs, end_date_fn)
    )
    upcoming = _apply_ordering_rules(
        _topo_sort(upcoming, topo_defs, lambda ev: (ev['scheduled_date'] or ['', ''])[0][:10])
    )

    return jsonify({'overdue': overdue, 'upcoming': upcoming})
