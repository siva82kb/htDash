"""
Device event utilities — per-device chronological event log.

Events stored at: data/<hospital>/devices/<type>/events/<device_id>.json
Write pattern: atomic .tmp → os.replace(), S3-aware. Mirrors utils/protocol_events.py.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from config import Config
from utils.data_access import _type_folder

if Config.USE_S3:
    from utils.s3_store import s3_read_json, s3_write_json

_CLOSE_EVENTS = frozenset({'repair', 'available', 'retire', 'discarded', 'lost'})


def _events_path(hospital_folder: str, device_type: str, device_id: str) -> Path:
    return (
        Path(Config.DATA_ROOT)
        / hospital_folder
        / 'devices'
        / _type_folder(device_type)
        / 'events'
        / f'{device_id}.json'
    )


def read_device_events(hospital_folder: str, device_type: str, device_id: str) -> dict:
    if Config.USE_S3:
        data = s3_read_json(f"{hospital_folder}/devices/{_type_folder(device_type)}/events/{device_id}.json")
        return data if data else {'events': []}
    path = _events_path(hospital_folder, device_type, device_id)
    if not path.exists():
        return {'events': []}
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'events': []}


def write_device_events(hospital_folder: str, device_type: str, device_id: str, data: dict) -> None:
    if Config.USE_S3:
        s3_write_json(f"{hospital_folder}/devices/{_type_folder(device_type)}/events/{device_id}.json", data)
        return
    path = _events_path(hospital_folder, device_type, device_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def append_device_event(
    hospital_folder: str,
    device_type: str,
    device_id: str,
    event_type: str,
    by: str,
    notes: str = '',
    homer_id: Optional[str] = None,
    related_device_id: Optional[str] = None,
    patient_event_id: Optional[str] = None,
    event_date: Optional[str] = None,
    issue_occur_date: Optional[str] = None,
) -> str:
    """Append one event to a device's event file. Returns the new event id."""
    data = read_device_events(hospital_folder, device_type, device_id)
    # 'date' is always the wall-clock time the event was logged — used for chronological ordering.
    # User-supplied event_date (e.g. resolve_date, issue_date) is stored as 'event_date' for display only.
    ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    event = {
        'id':                str(uuid.uuid4()),
        'device_id':         device_id,
        'event_type':        event_type,
        'date':              ts,
        'by':                by,
        'notes':             notes or '',
        'homer_id':          homer_id,
        'related_device_id': related_device_id,
        'patient_event_id':  patient_event_id,
    }
    if event_date:
        event['event_date'] = event_date
    if issue_occur_date:
        event['issue_occur_date'] = issue_occur_date
    data.setdefault('events', []).append(event)
    write_device_events(hospital_folder, device_type, device_id, data)
    return event['id']


def read_all_device_events(hospital_folder: str, device_type: str) -> list:
    """Read and merge all event files for a device type. Returns a flat list sorted by date desc."""
    if Config.USE_S3:
        from utils.s3_store import s3_list_prefix
        prefix = f"{hospital_folder}/devices/{_type_folder(device_type)}/events/"
        keys = s3_list_prefix(prefix)
        all_events = []
        for key in keys:
            data = s3_read_json(key) or {}
            all_events.extend(data.get('events', []))
    else:
        events_dir = Path(Config.DATA_ROOT) / hospital_folder / 'devices' / _type_folder(device_type) / 'events'
        all_events = []
        if events_dir.exists():
            for json_file in events_dir.glob('*.json'):
                try:
                    with open(json_file, encoding='utf-8') as f:
                        data = json.load(f)
                    all_events.extend(data.get('events', []))
                except Exception:
                    pass
    all_events.sort(key=lambda e: e.get('date', ''), reverse=True)
    return all_events


def update_device_event(hospital_folder: str, device_type: str, device_id: str, event_id: str, updates: dict) -> bool:
    """Patch fields on an existing event by id. Returns True if found and updated."""
    data = read_device_events(hospital_folder, device_type, device_id)
    for ev in data.get('events', []):
        if ev['id'] == event_id:
            ev.update(updates)
            write_device_events(hospital_folder, device_type, device_id, data)
            return True
    return False


def get_open_issues(hospital_folder: str, device_type: str) -> list:
    """Return list of {device_id, faulty_event} for devices with unresolved faulty events."""
    if Config.USE_S3:
        from utils.s3_store import s3_list_prefix
        prefix = f"{hospital_folder}/devices/{_type_folder(device_type)}/events/"
        keys = s3_list_prefix(prefix)
        issues = []
        for key in keys:
            try:
                data = s3_read_json(key) or {}
                events = sorted(data.get('events', []), key=lambda e: e.get('date', ''))
                faulty_event = None
                for ev in events:
                    if ev['event_type'] == 'faulty':
                        faulty_event = ev
                    elif ev['event_type'] in _CLOSE_EVENTS:
                        faulty_event = None
                if faulty_event:
                    issues.append(faulty_event)
            except Exception:
                pass
        return issues
    events_dir = Path(Config.DATA_ROOT) / hospital_folder / 'devices' / _type_folder(device_type) / 'events'
    issues = []
    if not events_dir.exists():
        return issues
    for json_file in events_dir.glob('*.json'):
        try:
            with open(json_file, encoding='utf-8') as f:
                data = json.load(f)
            events = sorted(data.get('events', []), key=lambda e: e.get('date', ''))
            faulty_event = None
            for ev in events:
                if ev['event_type'] == 'faulty':
                    faulty_event = ev
                elif ev['event_type'] in _CLOSE_EVENTS:
                    faulty_event = None
            if faulty_event:
                issues.append(faulty_event)
        except Exception:
            pass
    return issues


def get_resolved_issues(hospital_folder: str, device_type: str) -> list:
    """Return list of {faulty_event, resolved_event} pairs where issue was closed."""
    if Config.USE_S3:
        from utils.s3_store import s3_list_prefix
        prefix = f"{hospital_folder}/devices/{_type_folder(device_type)}/events/"
        keys = s3_list_prefix(prefix)
        resolved = []
        for key in keys:
            try:
                data = s3_read_json(key) or {}
                events = sorted(data.get('events', []), key=lambda e: e.get('date', ''))
                pending_faulty = None
                for ev in events:
                    if ev['event_type'] == 'faulty':
                        pending_faulty = ev
                    elif ev['event_type'] in _CLOSE_EVENTS and pending_faulty:
                        resolved.append({'faulty': pending_faulty, 'resolved': ev})
                        pending_faulty = None
            except Exception:
                pass
        resolved.sort(key=lambda p: p['resolved'].get('date', ''), reverse=True)
        return resolved
    events_dir = Path(Config.DATA_ROOT) / hospital_folder / 'devices' / _type_folder(device_type) / 'events'
    resolved = []
    if not events_dir.exists():
        return resolved
    for json_file in events_dir.glob('*.json'):
        try:
            with open(json_file, encoding='utf-8') as f:
                data = json.load(f)
            events = sorted(data.get('events', []), key=lambda e: e.get('date', ''))
            pending_faulty = None
            for ev in events:
                if ev['event_type'] == 'faulty':
                    pending_faulty = ev
                elif ev['event_type'] in _CLOSE_EVENTS and pending_faulty:
                    resolved.append({'faulty': pending_faulty, 'resolved': ev})
                    pending_faulty = None
        except Exception:
            pass
    resolved.sort(key=lambda p: p['resolved'].get('date', ''), reverse=True)
    return resolved
