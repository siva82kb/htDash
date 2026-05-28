"""
Protocol events utilities — create, read, and update protocol_events.json.

protocol_events.json sits at the patient root alongside <homer_id>.json.
It is created at group assignment and updated throughout the patient's journey.
"""

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from config import Config

if Config.USE_S3:
    from utils.s3_store import s3_read_json, s3_write_json

_PROTOCOL_PATH = Path(__file__).parent.parent / 'config' / 'study_protocol.json'


def load_study_protocol() -> dict:
    with open(_PROTOCOL_PATH, encoding='utf-8') as f:
        return json.load(f)


def _patients_path(hospital_folder: str) -> Path:
    return Path(Config.DATA_ROOT) / hospital_folder / 'patients'


def _events_path(hospital_folder: str, homer_id: str) -> Path:
    return _patients_path(hospital_folder) / homer_id / 'protocol_events.json'


def read_protocol_events(hospital_folder: str, homer_id: str) -> Optional[dict]:
    if Config.USE_S3:
        return s3_read_json(f"{hospital_folder}/patients/{homer_id}/protocol_events.json")
    path = _events_path(hospital_folder, homer_id)
    if not path.exists():
        return None
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def write_protocol_events(hospital_folder: str, homer_id: str, data: dict) -> None:
    if Config.USE_S3:
        s3_write_json(f"{hospital_folder}/patients/{homer_id}/protocol_events.json", data)
        return
    path = _events_path(hospital_folder, homer_id)
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def _date_add(base_iso: str, days: int) -> str:
    """Return ISO datetime string for base_iso + days."""
    base = datetime.fromisoformat(base_iso)
    return (base + timedelta(days=days)).strftime('%Y-%m-%dT%H:%M')


def _make_incomplete_entry(event: dict, scheduled_date) -> dict:
    return {
        'id':                str(uuid.uuid4()),
        'protocol_event_id': event['id'],
        'scheduled_date':    scheduled_date,  # [start_iso, end_iso] list or None
        'flagged':           False,
        'notes':             '',
    }


def create_protocol_events(hospital_folder: str, homer_id: str,
                           group: str, a0_date: str) -> None:
    """Create protocol_events.json at group assignment.

    Pre-populates incomplete with all timed events (strict, point_in_time, windowed):
    - reference=assignment → scheduled_date = [start_iso, end_iso] computed from a0_date
    - reference=activation → scheduled_date=null (filled at activation)

    free section initialised to zero state.
    complete starts empty.
    """
    protocol = load_study_protocol()
    timed_types = {'strict', 'point_in_time', 'windowed'}

    group_events  = protocol.get(group, [])
    shared_events = protocol.get('shared', [])
    all_events    = group_events + shared_events

    incomplete = []
    for event in all_events:
        if event.get('type') not in timed_types:
            continue
        reference = event.get('reference')
        window    = event.get('window') or {}
        start_day = window.get('start_day', 0)
        end_day   = window.get('end_day', start_day)

        if reference == 'assignment':
            scheduled_date = [_date_add(a0_date, start_day - 1), _date_add(a0_date, end_day - 1)]
        else:
            scheduled_date = None  # filled at activation

        entry = _make_incomplete_entry(event, scheduled_date)
        if event['id'] in ('a1_assessment', 'a2_assessment'):
            entry['appointment_date'] = None
        incomplete.append(entry)

    free: dict = {
        'adverse_event':                [],
        'adverse_event_followup':       [],
        'adverse_event_followup_visit': [],
        'adverse_event_clinical_visit': [],
        'patient_call':                 [],
        'watch_record':                 [],
        'watch_data_upload':            [],
        'activation_attempt':           [],
        'd15_attempt':                  [],
        'schedule_a1_call':             [],
        'schedule_a2_call':             [],
        'pre_discontinuation':          None,
        'discontinuation':              None,
    }
    if group == 'experimental':
        free['robot_issue_call']           = []
        free['robot_issue_visit']          = []
        free['resolve_robot_issue_visit']  = []
        free['other_device_issue_call']    = []
        free['other_device_issue_visit']   = []

    data = {
        'incomplete': incomplete,
        'complete':   [],
        'cancelled':  [],
        'free':       free,
    }
    write_protocol_events(hospital_folder, homer_id, data)


def populate_activation_dates(hospital_folder: str, homer_id: str,
                               activation_date: str) -> None:
    """On activation:
    - Fill scheduled_date for all reference=activation placeholders in incomplete.
    - Seed the first watch_record chained entry.
    """
    protocol = load_study_protocol()
    events_by_id = {}
    for section in ('experimental', 'control', 'shared'):
        for e in protocol.get(section, []):
            events_by_id[e['id']] = e

    data = read_protocol_events(hospital_folder, homer_id)
    if not data:
        return

    # Fill activation-reference scheduled dates
    for entry in data.get('incomplete', []):
        if entry.get('scheduled_date') is not None:
            continue
        event_def = events_by_id.get(entry['protocol_event_id'], {})
        if event_def.get('reference') != 'activation':
            continue
        window    = event_def.get('window') or {}
        start_day = window.get('start_day', 0)
        end_day   = window.get('end_day', start_day)
        entry['scheduled_date'] = [
            _date_add(activation_date, start_day - 1),
            _date_add(activation_date, end_day - 1),
        ]

    # Seed first watch_record
    watch_entry = {
        'id':                str(uuid.uuid4()),
        'protocol_event_id': 'watch_record',
        'scheduled_date':    [activation_date, activation_date],
        'flagged':           False,
        'notes':             '',
    }
    data['incomplete'].append(watch_entry)

    write_protocol_events(hospital_folder, homer_id, data)


def append_free_event(hospital_folder: str, homer_id: str,
                      key: str, record: dict) -> None:
    """Append a record to a list key in the free section."""
    data = read_protocol_events(hospital_folder, homer_id)
    if not data:
        return
    free = data.setdefault('free', {})
    free.setdefault(key, [])
    free[key].append(record)
    write_protocol_events(hospital_folder, homer_id, data)


def set_free_event(hospital_folder: str, homer_id: str,
                   key: str, record: dict) -> None:
    """Set a singleton key in the free section (pre_discontinuation, discontinuation)."""
    data = read_protocol_events(hospital_folder, homer_id)
    if not data:
        return
    data.setdefault('free', {})[key] = record
    write_protocol_events(hospital_folder, homer_id, data)
