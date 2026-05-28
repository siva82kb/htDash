"""
Shift a patient's entire timeline by N days.

For every entry in protocol_events.json:
  - scheduled_date is RECOMPUTED from the new reference date (a0 or activation)
    using study_protocol.json window definitions, preserving the original time-of-day.
  - All datetime fields (completion_date, session_start, session_end, sync_datetime,
    worn_datetime) are shifted by the per-entry delta (new_scheduled[0] - old_scheduled[0]).
    This handles any pre-existing inconsistencies in the file.
  - watch_record and other free entries (reference=null, no window) shift by N directly.

Patient JSON: enrollDate, a0CompletionDate, and activationDate all shift by N.

Usage:
    python scripts/shift_activation.py <homer_id> <days> [hospital]
    python scripts/shift_activation.py HOCMCV002 -2
    python scripts/shift_activation.py HOCMCV002 1 ranipet
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.data_access import read_patient_meta, write_patient_meta
from utils.protocol_events import read_protocol_events, write_protocol_events

FMT_DATE = '%Y-%m-%d'
FMT      = '%Y-%m-%dT%H:%M'
FMT_SECS = '%Y-%m-%dT%H:%M:%S'

DATETIME_FIELDS = ('completion_date', 'session_start', 'session_end',
                   'sync_datetime', 'worn_datetime', 'cancelled_at',
                   'removed_date', 'data_start', 'data_end')


def parse_dt(value: str) -> datetime:
    if len(value) == 10:
        return datetime.strptime(value, FMT_DATE)
    fmt = FMT_SECS if len(value) > 16 else FMT
    return datetime.strptime(value, fmt)


def fmt_dt(dt: datetime, has_secs: bool) -> str:
    return dt.strftime(FMT_SECS if has_secs else FMT)


def shift_dt(value: str, delta: timedelta) -> str:
    if len(value) == 10:
        return (datetime.strptime(value, FMT_DATE) + delta).strftime(FMT_DATE)
    has_secs = len(value) > 16
    return fmt_dt(parse_dt(value) + delta, has_secs)


def build_event_index(protocol_path: Path) -> dict:
    """Return {event_id: {reference, window}} from study_protocol.json."""
    data = json.loads(protocol_path.read_text(encoding='utf-8'))
    index = {}
    for section in ('experimental', 'control', 'shared'):
        for ev in data.get(section, []):
            # Don't overwrite — first occurrence wins (experimental > control > shared)
            if ev['id'] not in index:
                index[ev['id']] = {
                    'reference': ev.get('reference'),
                    'window':    ev.get('window'),
                }
    return index


def recompute_scheduled(ref_date: datetime, window: dict,
                         old_sd: list) -> list:
    """
    Recompute [start, end] using the new reference date and window offsets.
    Time-of-day is preserved from old_sd[0].
    """
    time_str = old_sd[0].split('T')[1] if old_sd[0] else '08:00'
    h, m     = map(int, time_str.split(':')[:2])
    start = ref_date + timedelta(days=window['start_day'] - 1)
    end   = ref_date + timedelta(days=window['end_day']   - 1)
    start = start.replace(hour=h, minute=m, second=0, microsecond=0)
    end   = end.replace(  hour=h, minute=m, second=0, microsecond=0)
    return [start.strftime(FMT), end.strftime(FMT)]


def shift_entry(entry: dict, event_index: dict,
                new_a0: datetime, new_activation: datetime,
                n_delta: timedelta) -> None:
    pid = entry.get('protocol_event_id', '')
    ev  = event_index.get(pid)
    sd  = entry.get('scheduled_date')

    if not isinstance(sd, list) or len(sd) != 2 or not sd[0]:
        # No scheduled_date (free events) — shift all datetime fields by N
        for field in DATETIME_FIELDS:
            if entry.get(field):
                entry[field] = shift_dt(entry[field], n_delta)
        return

    # Recompute scheduled_date from protocol definition
    ref    = ev.get('reference') if ev else None
    window = ev.get('window')    if ev else None

    if ref == 'activation' and window:
        new_sd = recompute_scheduled(new_activation, window, sd)
    elif ref == 'assignment' and window:
        new_sd = recompute_scheduled(new_a0, window, sd)
    else:
        # No window definition (watch_record chained, etc.) — shift by N
        new_sd = [shift_dt(sd[0], n_delta), shift_dt(sd[1], n_delta)]

    # Per-entry delta: how much did this event's scheduled_date actually move?
    entry_delta = parse_dt(new_sd[0]) - parse_dt(sd[0])
    entry['scheduled_date'] = new_sd

    # Shift all datetime fields by the per-entry delta
    for field in DATETIME_FIELDS:
        if entry.get(field):
            entry[field] = shift_dt(entry[field], entry_delta)


def shift_free_section(free: dict, n_delta: timedelta) -> None:
    """Shift datetime fields on any free-event entries."""
    for key, val in free.items():
        if val is None:
            continue
        entries = val if isinstance(val, list) else [val]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for field in DATETIME_FIELDS:
                if entry.get(field):
                    entry[field] = shift_dt(entry[field], n_delta)


def shift_activation(homer_id: str, days: int, hospital: str) -> None:
    n_delta = timedelta(days=days)

    # ── Patient meta ──────────────────────────────────────────────────────────
    patient = read_patient_meta(hospital, homer_id)
    if not patient:
        print(f"ERROR: patient {homer_id} not found in {hospital}")
        sys.exit(1)
    if not patient.get('activationDate'):
        print(f"ERROR: {homer_id} has no activationDate — activate first")
        sys.exit(1)

    old_a0         = patient['a0CompletionDate']
    old_enroll     = patient.get('enrollDate', old_a0)
    old_activation = patient['activationDate']

    new_a0         = parse_dt(old_a0)         + n_delta
    new_enroll     = parse_dt(old_enroll)     + n_delta
    new_activation = parse_dt(old_activation) + n_delta

    patient['enrollDate']        = new_enroll.strftime(FMT)
    patient['a0CompletionDate']  = new_a0.strftime(FMT)
    patient['activationDate']    = new_activation.strftime(FMT)

    # Shift all other date fields in patient meta that are set.
    # shift_dt preserves the original format (date-only or datetime).
    for field in ('trainingCompletionDate', 'trainingPausedDate', 'brokenProtocolDate',
                  'a1CompletionDate', 'a2CompletionDate',
                  'discontinuationDate', 'preDiscontinuationDate'):
        if patient.get(field):
            patient[field] = shift_dt(patient[field], n_delta)

    # Shift pauseHistory epoch start/end datetimes
    for epoch in patient.get('pauseHistory', []):
        if epoch.get('start'):
            epoch['start'] = shift_dt(epoch['start'], n_delta)
        if epoch.get('end'):
            epoch['end'] = shift_dt(epoch['end'], n_delta)

    write_patient_meta(hospital, homer_id, patient)
    print(f"enrollDate:       {old_enroll}  →  {patient['enrollDate']}")
    print(f"a0CompletionDate: {old_a0}  →  {patient['a0CompletionDate']}")
    print(f"activationDate:   {old_activation}  →  {patient['activationDate']}")

    # ── Protocol events ───────────────────────────────────────────────────────
    events_data = read_protocol_events(hospital, homer_id)
    if not events_data:
        print("ERROR: protocol_events.json not found")
        sys.exit(1)

    protocol_path = PROJECT_ROOT / 'config' / 'study_protocol.json'
    event_index   = build_event_index(protocol_path)

    count = 0
    for section in ('incomplete', 'complete'):
        for entry in events_data.get(section, []):
            shift_entry(entry, event_index, new_a0, new_activation, n_delta)
            count += 1

    # Cancelled stubs: shift scheduled_date like incomplete entries + shift cancelled_at
    for entry in events_data.get('cancelled', []):
        shift_entry(entry, event_index, new_a0, new_activation, n_delta)
        count += 1

    shift_free_section(events_data.get('free', {}), n_delta)

    write_protocol_events(hospital, homer_id, events_data)
    print(f"Shifted {count} protocol event entries.")
    print(f"Done.")


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) < 2:
        print("Usage: python scripts/shift_activation.py <homer_id> <days> [hospital]")
        print("Example: python scripts/shift_activation.py HOCMCV002 -2")
        sys.exit(1)
    homer_id = args[0]
    days     = int(args[1])
    hospital = args[2] if len(args) > 2 else 'ranipet'
    shift_activation(homer_id, days, hospital)