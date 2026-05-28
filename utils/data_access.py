"""
Data access utilities for the hospital-scoped data folder structure.

Layout:
    data/
    ├── manipal/
    │   ├── patients/<homer_id>/<homer_id>.json  — patient metadata
    │   │                      <homer_id>.log   — patient activity log
    │   ├── dashboard/<user_id>.csv              — per-user session log
    │   └── devices/pluto|mars|actigraphs|modems|sims/
    ├── ranipet/
    └── ludhiana/

Access control:
    login_place == 'admin'   → can read all hospitals
    login_place == 'Manipal' → mapped to 'manipal' folder only
"""

import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional
from config import Config

if Config.USE_S3:
    from utils.s3_store import (
        s3_read_json, s3_write_json,
        s3_read_text, s3_write_text, s3_append_text,
        s3_list_immediate_folders, s3_key_exists,
    )

_PROTOCOL_PATH = Path(__file__).parent.parent / 'config' / 'study_protocol.json'
_protocol_cache: dict = {}


def _load_protocol() -> dict:
    global _protocol_cache
    if not _protocol_cache:
        try:
            with open(_PROTOCOL_PATH, encoding='utf-8') as f:
                _protocol_cache = json.load(f)
        except Exception:
            _protocol_cache = {'config': {}, 'shared': [], 'experimental': [], 'control': []}
    return _protocol_cache


def _protocol_config() -> dict:
    return _load_protocol().get('config', {})


def derive_status(patient: dict) -> str:
    """Derive patient state from factual fields. State is never stored."""
    group       = patient.get('group')
    activation  = patient.get('activationDate')
    discontinue = patient.get('discontinuationDate')
    training    = patient.get('trainingCompletionDate')
    a1          = patient.get('a1CompletionDate')
    a2          = patient.get('a2CompletionDate')
    a0          = patient.get('a0CompletionDate')

    if not group:
        return 'pre_discontinued' if discontinue else 'unassigned'
    # all_completed supersedes discontinued and broken_protocol.
    if a2 or patient.get('a2MissedDate'):
        return 'all_completed'
    if discontinue:
        return 'discontinued'
    if patient.get('brokenProtocolDate'):
        return 'broken_protocol'

    if not activation:
        # Check if activation window has been missed → broken_protocol
        if a0:
            protocol = _load_protocol()
            activation_event = next(
                (e for e in protocol.get('shared', []) if e.get('id') == 'activation'), None
            )
            end_day = activation_event['window']['end_day'] if activation_event else 5
            try:
                a0_date = datetime.fromisoformat(a0).date()
                if date.today() > a0_date + timedelta(days=end_day):
                    return 'broken_protocol'
            except Exception:
                pass
        return 'inactive'

    cfg = _protocol_config()
    cum_pause = patient.get('cumulativePauseDays') or 0
    max_pause = cfg.get('max_cumulative_pause_days', 10)
    if cum_pause > max_pause:
        return 'broken_protocol'

    if not training:
        try:
            activation_date = datetime.fromisoformat(activation).date()
            if date.today() >= activation_date + timedelta(days=28):
                return 'post_training'
        except Exception:
            pass

    if patient.get('trainingPausedDate'):
        return 'paused'

    if a1 or patient.get('a1MissedDate'):
        return 'a1_completed'
    if training:
        return 'training_completed'
    return 'active'


def get_hospital_folder(login_place: str) -> Optional[str]:
    """Map a session login_place ('Manipal') to a data folder name ('manipal').
    Returns None for the global admin — admin reads all hospitals."""
    return Config.HOSPITAL_FOLDER_MAP.get(login_place)


def get_patients_path(hospital_folder: str) -> Path:
    return Path(Config.DATA_ROOT) / hospital_folder / 'patients'


def list_patient_ids(hospital_folder: str) -> list:
    """Return a list of patient_id strings (one per subfolder)."""
    if Config.USE_S3:
        return sorted(s3_list_immediate_folders(f"{hospital_folder}/patients"))
    path = get_patients_path(hospital_folder)
    if not path.exists():
        return []
    return [d.name for d in sorted(path.iterdir()) if d.is_dir()]


def read_patient_meta(hospital_folder: str, patient_id: str) -> Optional[dict]:
    """Read <patient_id>.json for a single patient. Returns None if not found."""
    if Config.USE_S3:
        return s3_read_json(f"{hospital_folder}/patients/{patient_id}/{patient_id}.json")
    meta_path = get_patients_path(hospital_folder) / patient_id / f'{patient_id}.json'
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def get_all_patients(hospital_folder: str) -> list:
    """Return a list of patient metadata dicts for one hospital."""
    patients = []
    for patient_id in list_patient_ids(hospital_folder):
        meta = read_patient_meta(hospital_folder, patient_id)
        if meta:
            patients.append(meta)
    return patients


def find_patient_folder(login_place: str, homer_id: str) -> Optional[str]:
    """Return the hospital folder that contains homer_id, or None if not found."""
    folder = get_hospital_folder(login_place)
    if folder:
        return folder if read_patient_meta(folder, homer_id) else None
    # Admin: search all hospitals
    for f in Config.HOSPITALS:
        if read_patient_meta(f, homer_id):
            return f
    return None


def iter_patients_with_folder(login_place: str):
    """Yield (hospital_folder, homer_id, patient_meta) for all visible patients."""
    if login_place == Config.ADMIN_LOGIN:
        for folder in Config.HOSPITALS:
            for pid in list_patient_ids(folder):
                meta = read_patient_meta(folder, pid)
                if meta:
                    yield folder, pid, meta
    else:
        folder = get_hospital_folder(login_place)
        if folder:
            for pid in list_patient_ids(folder):
                meta = read_patient_meta(folder, pid)
                if meta:
                    yield folder, pid, meta


def get_patients_for_user(login_place: str) -> list:
    """Return patients visible to a user based on their login_place.
    Global admin sees all hospitals; site users see only their own."""
    if login_place == Config.ADMIN_LOGIN:
        patients = []
        for folder in Config.HOSPITALS:
            patients.extend(get_all_patients(folder))
        return patients
    folder = get_hospital_folder(login_place)
    if not folder:
        return []
    return get_all_patients(folder)


_HOMER_ID_PREFIXES = {
    'manipal':  'HOMCHP',
    'ranipet':  'HOCMCV',
    'ludhiana': 'HOCMCL',
}


def generate_homer_id(hospital_folder: str) -> str:
    """Auto-generate the next homerID for a hospital (e.g. HOMCHP004)."""
    prefix = _HOMER_ID_PREFIXES.get(hospital_folder, 'HOMUNK')
    existing = list_patient_ids(hospital_folder)
    nums = []
    for pid in existing:
        if pid.startswith(prefix):
            try:
                nums.append(int(pid[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{max(nums, default=0) + 1:03d}"


def write_patient_meta(hospital_folder: str, patient_id: str, data: dict) -> None:
    """Write (create or update) <patient_id>.json for a patient atomically."""
    if Config.USE_S3:
        s3_write_json(f"{hospital_folder}/patients/{patient_id}/{patient_id}.json", data)
        return
    patient_dir = get_patients_path(hospital_folder) / patient_id
    patient_dir.mkdir(parents=True, exist_ok=True)
    meta_path = patient_dir / f'{patient_id}.json'
    tmp_path = meta_path.with_suffix('.tmp')
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, meta_path)


def _dashboard_path(hospital_folder: str) -> Path:
    return Path(Config.DATA_ROOT) / hospital_folder / 'dashboard'


def _safe_id(user_id: str) -> str:
    return ''.join(c for c in user_id if c.isalnum() or c in '-_')


def open_session(hospital_folder: str, user_id: str) -> int:
    """Write a new session row to dashboard/<user_id>.csv on login.
    Returns the new session_id.
    """
    login_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    safe_id = _safe_id(user_id)

    if Config.USE_S3:
        key = f"{hospital_folder}/dashboard/{safe_id}.csv"
        try:
            existing = s3_read_text(key) or ''
            if not existing:
                header = (
                    f':Location: {hospital_folder.capitalize()}\n'
                    f':ID: {user_id}\n'
                    'session_id,login_time,logout_time,logout_reason\n'
                )
                content = header + f'1,{login_time},null,null\n'
                s3_write_text(key, content)
                return 1
            lines = existing.splitlines(keepends=True)
            data_rows = [l for l in lines if l.strip() and not l.startswith(':') and not l.startswith('session_id')]
            session_id = len(data_rows) + 1
            s3_append_text(key, f'{session_id},{login_time},null,null\n')
            return session_id
        except Exception as e:
            print(f'Warning: could not open session (S3): {e}')
            return -1

    dashboard_dir = _dashboard_path(hospital_folder)
    dashboard_dir.mkdir(parents=True, exist_ok=True)
    csv_path = dashboard_dir / f'{safe_id}.csv'

    preheader = [
        f':Location: {hospital_folder.capitalize()}\n',
        f':ID: {user_id}\n',
        'session_id,login_time,logout_time,logout_reason\n',
    ]

    try:
        if not csv_path.exists():
            with open(csv_path, 'w', encoding='utf-8') as f:
                f.writelines(preheader)
                f.write(f'1,{login_time},null,null\n')
            return 1

        with open(csv_path, encoding='utf-8') as f:
            lines = f.readlines()

        data_rows = [l for l in lines if l.strip() and not l.startswith(':') and not l.startswith('session_id')]
        session_id = len(data_rows) + 1

        with open(csv_path, 'a', encoding='utf-8') as f:
            f.write(f'{session_id},{login_time},null,null\n')
        return session_id

    except Exception as e:
        print(f'Warning: could not open session: {e}')
        return -1


def close_session(hospital_folder: str, user_id: str, session_id: int, reason: str) -> None:
    """Update the open session row with logout_time and reason."""
    logout_time = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    safe_id = _safe_id(user_id)

    if Config.USE_S3:
        key = f"{hospital_folder}/dashboard/{safe_id}.csv"
        try:
            existing = s3_read_text(key)
            if not existing:
                return
            lines = existing.splitlines(keepends=True)
            updated = []
            for line in lines:
                if not line.startswith(':') and not line.startswith('session_id') and line.strip():
                    parts = line.strip().split(',')
                    if len(parts) >= 4 and parts[0] == str(session_id) and parts[2] == 'null':
                        line = f'{parts[0]},{parts[1]},{logout_time},{reason}\n'
                updated.append(line)
            s3_write_text(key, ''.join(updated))
        except Exception as e:
            print(f'Warning: could not close session (S3): {e}')
        return

    csv_path = _dashboard_path(hospital_folder) / f'{safe_id}.csv'
    if not csv_path.exists():
        return
    try:
        with open(csv_path, encoding='utf-8') as f:
            lines = f.readlines()
        updated = []
        for line in lines:
            if not line.startswith(':') and not line.startswith('session_id') and line.strip():
                parts = line.strip().split(',')
                if len(parts) >= 4 and parts[0] == str(session_id) and parts[2] == 'null':
                    line = f'{parts[0]},{parts[1]},{logout_time},{reason}\n'
            updated.append(line)
        tmp_path = csv_path.with_suffix('.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.writelines(updated)
        os.replace(tmp_path, csv_path)
    except Exception as e:
        print(f'Warning: could not close session: {e}')


def create_patient_log(hospital_folder: str, homer_id: str) -> None:
    """Create <homer_id>.log with the two-line preheader. Called at enrollment."""
    if Config.USE_S3:
        key = f"{hospital_folder}/patients/{homer_id}/{homer_id}.log"
        try:
            s3_write_text(key, f':Location: {hospital_folder.capitalize()}\n:HomerId: {homer_id}\n')
        except Exception as e:
            print(f'Warning: could not create patient log (S3): {e}')
        return
    log_path = get_patients_path(hospital_folder) / homer_id / f'{homer_id}.log'
    try:
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f':Location: {hospital_folder.capitalize()}\n')
            f.write(f':HomerId: {homer_id}\n')
    except Exception as e:
        print(f'Warning: could not create patient log: {e}')


def write_patient_log(hospital_folder: str, homer_id: str, user_id: str,
                      session_id: int, action: str, detail_file: str = None) -> None:
    """Append a clinical action line to patients/<homer_id>/<homer_id>.log.

    Format:
        [YYYY-MM-DD HH:MM:SS]   <user_id>    #<session_id>    <action> | <detail_file>
    """
    timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    detail = f' | {detail_file}' if detail_file else ''
    line = f'[{timestamp}]   {user_id:<16}#{session_id:<4} {action}{detail}\n'
    if Config.USE_S3:
        key = f"{hospital_folder}/patients/{homer_id}/{homer_id}.log"
        try:
            s3_append_text(key, line)
        except Exception as e:
            print(f'Warning: could not write patient log (S3): {e}')
        return
    log_path = get_patients_path(hospital_folder) / homer_id / f'{homer_id}.log'
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(line)
    except Exception as e:
        print(f'Warning: could not write patient log: {e}')


# ── Device file utilities ──────────────────────────────────────────────────────

def _devices_path(hospital_folder: str) -> Path:
    return Path(Config.DATA_ROOT) / hospital_folder / 'devices'


def read_device_inventory(hospital_folder: str, device_type: str) -> list:
    """Return all device entries from {folder}/inventory.json."""
    folder = _type_folder(device_type)
    if Config.USE_S3:
        data = s3_read_json(f"{hospital_folder}/devices/{folder}/inventory.json")
        return (data or {}).get('devices', [])
    path = _devices_path(hospital_folder) / folder / 'inventory.json'
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f).get('devices', [])
    except Exception:
        return []


def read_device_assignments(hospital_folder: str, device_type: str) -> list:
    """Return all assignment records from {folder}/assignments.json."""
    folder = _type_folder(device_type)
    if Config.USE_S3:
        data = s3_read_json(f"{hospital_folder}/devices/{folder}/assignments.json")
        return (data or {}).get('assignments', [])
    path = _devices_path(hospital_folder) / folder / 'assignments.json'
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f).get('assignments', [])
    except Exception:
        return []


def write_device_assignments(hospital_folder: str, device_type: str, assignments: list) -> None:
    """Atomically overwrite {folder}/assignments.json."""
    folder = _type_folder(device_type)
    if Config.USE_S3:
        s3_write_json(f"{hospital_folder}/devices/{folder}/assignments.json",
                      {'assignments': assignments})
        return
    path = _devices_path(hospital_folder) / folder / 'assignments.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'assignments': assignments}, f, indent=2)
    os.replace(tmp, path)


def write_device_inventory(hospital_folder: str, device_type: str, data: dict) -> None:
    """Atomically overwrite {folder}/inventory.json."""
    folder = _type_folder(device_type)
    if Config.USE_S3:
        s3_write_json(f"{hospital_folder}/devices/{folder}/inventory.json", data)
        return
    path = _devices_path(hospital_folder) / folder / 'inventory.json'
    tmp = path.with_suffix('.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def read_sims(hospital_folder: str) -> list:
    """Return all SIM cards from sims/inventory.json."""
    if Config.USE_S3:
        data = s3_read_json(f"{hospital_folder}/devices/sims/inventory.json")
        return (data or {}).get('sims', [])
    path = _devices_path(hospital_folder) / 'sims' / 'inventory.json'
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f).get('sims', [])
    except Exception:
        return []


def write_sims(hospital_folder: str, sims: list) -> None:
    """Atomically overwrite sims/inventory.json."""
    if Config.USE_S3:
        s3_write_json(f"{hospital_folder}/devices/sims/inventory.json", {'sims': sims})
        return
    path = _devices_path(hospital_folder) / 'sims' / 'inventory.json'
    tmp = path.with_suffix('.tmp')
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump({'sims': sims}, f, indent=2)
    os.replace(tmp, path)



def get_available_devices(hospital_folder: str, device_type: str) -> list:
    """Return active, non-clinic, non-lost, non-faulty, unassigned devices for a given type."""
    inventory = read_device_inventory(hospital_folder, device_type)
    assignments = read_device_assignments(hospital_folder, device_type)
    assigned_ids = {a['device_id'] for a in assignments if a.get('returned_date') is None}
    return [
        d for d in inventory
        if d.get('removal_date') is None
        and d.get('lost_date') is None
        and not d.get('clinic_only', False)
        and not d.get('faulty', False)
        and not d.get('has_issue', False)
        and d['id'] not in assigned_ids
    ]


def mark_device_faulty(hospital_folder: str, device_type: str, device_id: str) -> None:
    """Set faulty: true on a device inventory entry."""
    folder = _type_folder(device_type)
    if Config.USE_S3:
        key = f"{hospital_folder}/devices/{folder}/inventory.json"
        try:
            data = s3_read_json(key) or {'devices': []}
            for d in data.get('devices', []):
                if d['id'] == device_id:
                    d['faulty'] = True
                    break
            s3_write_json(key, data)
        except Exception as e:
            print(f'Warning: could not mark device faulty (S3): {e}')
        return
    path = _devices_path(hospital_folder) / folder / 'inventory.json'
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for d in data.get('devices', []):
            if d['id'] == device_id:
                d['faulty'] = True
                break
        tmp = path.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print(f'Warning: could not mark device faulty: {e}')


def mark_device_not_faulty(hospital_folder: str, device_type: str, device_id: str) -> None:
    """Clear faulty flag on a device inventory entry (device declared repaired)."""
    folder = _type_folder(device_type)
    if Config.USE_S3:
        key = f"{hospital_folder}/devices/{folder}/inventory.json"
        try:
            data = s3_read_json(key) or {'devices': []}
            for d in data.get('devices', []):
                if d['id'] == device_id:
                    d.pop('faulty', None)
                    break
            s3_write_json(key, data)
        except Exception as e:
            print(f'Warning: could not clear device faulty flag (S3): {e}')
        return
    path = _devices_path(hospital_folder) / folder / 'inventory.json'
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for d in data.get('devices', []):
            if d['id'] == device_id:
                d.pop('faulty', None)
                break
        tmp = path.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print(f'Warning: could not clear device faulty flag: {e}')


def mark_device_lost(hospital_folder: str, device_type: str,
                     device_id: str, lost_date: str) -> None:
    """Set lost_date on a device inventory entry (agwatch only)."""
    folder = _type_folder(device_type)
    if Config.USE_S3:
        key = f"{hospital_folder}/devices/{folder}/inventory.json"
        try:
            data = s3_read_json(key) or {'devices': []}
            for d in data.get('devices', []):
                if d['id'] == device_id:
                    d['lost_date'] = lost_date
                    break
            s3_write_json(key, data)
        except Exception as e:
            print(f'Warning: could not mark device lost (S3): {e}')
        return
    path = _devices_path(hospital_folder) / folder / 'inventory.json'
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        for d in data.get('devices', []):
            if d['id'] == device_id:
                d['lost_date'] = lost_date
                break
        tmp = path.with_suffix('.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print(f'Warning: could not mark device lost: {e}')


_TYPE_FOLDER = {
    'pluto': 'pluto', 'mars': 'mars', 'agwatch': 'agwatch',
    'modem': 'modems', 'modems': 'modems',
    'laptop': 'laptops', 'laptops': 'laptops',
    'sims': 'sims',
}

def _type_folder(device_type: str) -> str:
    """Return the folder name for a device type."""
    return _TYPE_FOLDER.get(device_type, device_type)


def write_device_log(hospital_folder: str, device_id: str, user_id: str,
                     session_id: int, action: str, device_type: str = '') -> None:
    """Append an entry to {folder}/logs/{device_id}.log, creating it if needed."""
    subfolder = _type_folder(device_type) if device_type else 'misc'
    timestamp = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    line = f'[{timestamp}]   {user_id:<16}#{session_id:<4} {action}\n'
    if Config.USE_S3:
        key = f"{hospital_folder}/devices/{subfolder}/logs/{device_id}.log"
        try:
            existing = s3_read_text(key)
            if existing is None:
                line = (f':Location: {hospital_folder.capitalize()}\n'
                        f':DeviceId: {device_id}\n') + line
            s3_append_text(key, line)
        except Exception as e:
            print(f'Warning: could not write device log (S3): {e}')
        return
    logs_dir = _devices_path(hospital_folder) / subfolder / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f'{device_id}.log'
    is_new = not log_path.exists()
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            if is_new:
                f.write(f':Location: {hospital_folder.capitalize()}\n')
                f.write(f':DeviceId: {device_id}\n')
            f.write(line)
    except Exception as e:
        print(f'Warning: could not write device log: {e}')


def read_fault_reports(hospital_folder: str, device_type: str) -> list:
    """Read fault reports for a device type from {folder}/faultReport.json."""
    folder = _type_folder(device_type)
    if Config.USE_S3:
        data = s3_read_json(f"{hospital_folder}/devices/{folder}/faultReport.json")
        return (data or {}).get('fault_reports', [])
    path = _devices_path(hospital_folder) / folder / 'faultReport.json'
    if not path.exists():
        return []
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data.get('fault_reports', [])
    except Exception:
        return []


def write_fault_reports(hospital_folder: str, device_type: str, reports: list) -> None:
    """Write fault reports for a device type to {folder}/faultReport.json."""
    folder = _type_folder(device_type)
    if Config.USE_S3:
        s3_write_json(f"{hospital_folder}/devices/{folder}/faultReport.json",
                      {'fault_reports': reports})
        return
    path = _devices_path(hospital_folder) / folder / 'faultReport.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump({'fault_reports': reports}, f, indent=2)
        os.replace(tmp, path)
    except Exception as e:
        print(f'Warning: could not write fault reports: {e}')


def create_patient_folders(hospital_folder: str, patient_id: str, group: str) -> None:
    """Create the standard subfolder structure for a new patient.
    No-op when USE_S3=True — S3 has no concept of empty folders.
    """
    if Config.USE_S3:
        return
    base = get_patients_path(hospital_folder) / patient_id
    common = ['actigraphs', 'adl', 'attachments', 'note_attachments']
    experimental_only = ['pluto', 'mars']
    control_only = ['vcg_exercise']

    folders = common[:]
    if group == 'experimental':
        folders += experimental_only
    elif group == 'control':
        folders += control_only

    for folder in folders:
        (base / folder).mkdir(parents=True, exist_ok=True)


# ── Patient notes (free-text Notes tab) ────────────────────────────────────────

_NOTES_BUCKETS = ('admin', 'therapist', 'engineer')


def _empty_notes() -> dict:
    return {b: [] for b in _NOTES_BUCKETS}


def read_patient_notes(hospital_folder: str, patient_id: str) -> dict:
    """Read notes.json for a patient. Returns role-keyed buckets; empty buckets if absent."""
    if Config.USE_S3:
        data = s3_read_json(f"{hospital_folder}/patients/{patient_id}/notes.json")
    else:
        path = get_patients_path(hospital_folder) / patient_id / 'notes.json'
        if not path.exists():
            return _empty_notes()
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            return _empty_notes()
    if not isinstance(data, dict):
        return _empty_notes()
    # Ensure all buckets are present and are lists.
    return {b: (data.get(b) if isinstance(data.get(b), list) else []) for b in _NOTES_BUCKETS}


def write_patient_notes(hospital_folder: str, patient_id: str, data: dict) -> None:
    """Write (create or update) notes.json for a patient atomically."""
    if Config.USE_S3:
        s3_write_json(f"{hospital_folder}/patients/{patient_id}/notes.json", data)
        return
    patient_dir = get_patients_path(hospital_folder) / patient_id
    patient_dir.mkdir(parents=True, exist_ok=True)
    path = patient_dir / 'notes.json'
    tmp = path.with_suffix('.tmp')
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
