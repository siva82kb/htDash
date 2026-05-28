"""
Setup rich test data for the four ranipet test patients.

This script advances three patients (HOCMCV002, 003, 004) to different stages of therapy,
while leaving HOCMCV005 as-is (inactive) for testing the full activation flow.

Run this after reset_test_patient.py.
"""

import sys
from datetime import datetime
from pathlib import Path
import uuid
import json

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.data_access import (
    get_patients_path,
    write_patient_meta,
    read_device_assignments,
    write_device_assignments,
)
from utils.protocol_events import (
    populate_activation_dates,
    write_protocol_events,
    read_protocol_events,
)

HOSPITAL = 'ranipet'


def _move_to_complete(entry: dict, completion_date: str, filed_at: str = None, **extra) -> dict:
    """Convert an incomplete entry to complete by adding completion_date and filed_at."""
    if filed_at is None:
        filed_at = completion_date.replace('T', 'T').replace(':00', ':00:00')[-8:].count(':') < 2 and completion_date + ':00' or completion_date + ':00'
        # Parse just the date and time part and add seconds
        dt = datetime.fromisoformat(completion_date)
        filed_at = dt.strftime('%Y-%m-%dT%H:%M:%S')

    completed = {**entry, 'completion_date': completion_date, 'filed_at': filed_at}
    completed.update(extra)
    return completed


def setup_hocmcv002() -> None:
    """HOCMCV002: experimental, day 7 of therapy."""
    print("Setting up HOCMCV002 (experimental, day 7)…")

    homer_id = 'HOCMCV002'
    activation_date = '2026-04-02T10:00'

    # Step 1: populate activation dates
    populate_activation_dates(HOSPITAL, homer_id, activation_date)

    # Step 2: Read protocol events
    data = read_protocol_events(HOSPITAL, homer_id)
    incomplete = data['incomplete']
    complete = data['complete']
    free = data['free']

    # Move events to complete
    events_to_complete = {
        'exp_device_install': {'pluto_id': 'PLT-001', 'mars_id': 'MRS-001', 'demo_done': True, 'notes': ''},
        'activation': {'session_start': '2026-04-02T10:00', 'session_end': '2026-04-02T11:00', 'triggered': [], 'notes': ''},
        'adl_prescription_d01': {'notes': ''},
        'prescription_printout_d01': {'notes': ''},
        'home_visit_d02': {'session_start': '2026-04-03T10:00', 'session_end': '2026-04-03T11:00', 'notes': ''},
        'home_visit_d03': {'session_start': '2026-04-04T10:00', 'session_end': '2026-04-04T11:00', 'notes': ''},
        'adl_agwatch_timing_d03': {'notes': ''},
    }

    completion_dates = {
        'exp_device_install': '2026-04-02T10:00',
        'activation': '2026-04-02T10:00',
        'adl_prescription_d01': '2026-04-02T10:30',
        'prescription_printout_d01': '2026-04-02T10:45',
        'home_visit_d02': '2026-04-03T10:00',
        'home_visit_d03': '2026-04-04T10:00',
        'adl_agwatch_timing_d03': '2026-04-04T11:00',
    }

    new_incomplete = []
    watch_record_entry = None

    for entry in incomplete:
        event_id = entry['protocol_event_id']

        if event_id in events_to_complete:
            complete.append(_move_to_complete(
                entry,
                completion_dates[event_id],
                **events_to_complete[event_id]
            ))
        elif event_id == 'watch_record':
            # Keep this one to move to free
            watch_record_entry = entry
        else:
            new_incomplete.append(entry)

    # Move watch_record to free (day 3 entry) and seed next in incomplete
    if watch_record_entry:
        # Create completed watch record entry for day 3
        watch_free_entry = {
            'id': str(uuid.uuid4()),
            'ag_watch_right': {'old_id': None, 'old_lost': False, 'new_id': 'AGW-001'},
            'ag_watch_left': {'old_id': None, 'old_lost': False, 'new_id': 'AGW-002'},
            'sync_datetime': '2026-04-04T10:00',
            'worn_datetime': '2026-04-04T10:00',
            'next_followup_days': 7,
            'notes': '',
            'triggered_by': {'type': 'activation', 'id': watch_record_entry['id']},
            'completion_date': '2026-04-04T10:00',
            'filed_at': '2026-04-04T10:00:00',
        }
        free['watch_record'].append(watch_free_entry)

        # Seed next watch_record in incomplete for day 11 (next followup = day 3 + 7)
        next_watch = {
            'id': str(uuid.uuid4()),
            'protocol_event_id': 'watch_record',
            'scheduled_date': ['2026-04-09T10:00', '2026-04-09T10:00'],
            'flagged': False,
            'notes': '',
        }
        new_incomplete.append(next_watch)

    data['incomplete'] = new_incomplete
    data['complete'] = complete
    data['free'] = free
    write_protocol_events(HOSPITAL, homer_id, data)

    # Step 3: Update patient meta
    meta = {
        'homerID': homer_id,
        'hospitalID': 'RP-T001',
        'group': 'experimental',
        'trainingSide': 'Right',
        'enrollDate': '2026-04-08T12:00',
        'a0CompletionDate': '2026-04-08T12:00',
        'activationDate': activation_date,
        'discontinuationDate': None,
        'trainingCompletionDate': None,
        'trainingPausedDate': None,
        'brokenProtocolDate': None,
        'a1CompletionDate': None,
        'a2CompletionDate': None,
        'cumulativePauseDays': 0,
        'pauseHistory': [],
        'vcgGroup': None,
        'agWatchRightID': 'AGW-001',
        'agWatchLeftID': 'AGW-002',
    }
    write_patient_meta(HOSPITAL, homer_id, meta)

    # Step 4: Write device assignments
    assignments = read_device_assignments(HOSPITAL, 'pluto')
    assignments.append({
        'device_id': 'PLT-001',
        'patient_id': homer_id,
        'assigned_date': activation_date,
        'returned_date': None,
    })
    write_device_assignments(HOSPITAL, 'pluto', assignments)

    assignments = read_device_assignments(HOSPITAL, 'mars')
    assignments.append({
        'device_id': 'MRS-001',
        'patient_id': homer_id,
        'assigned_date': activation_date,
        'returned_date': None,
    })
    write_device_assignments(HOSPITAL, 'mars', assignments)

    assignments = read_device_assignments(HOSPITAL, 'agwatch')
    assignments.extend([
        {
            'device_id': 'AGW-001',
            'patient_id': homer_id,
            'limb': 'Right',
            'assigned_date': '2026-04-04T10:00',
            'returned_date': None,
        },
        {
            'device_id': 'AGW-002',
            'patient_id': homer_id,
            'limb': 'Left',
            'assigned_date': '2026-04-04T10:00',
            'returned_date': None,
        },
    ])
    write_device_assignments(HOSPITAL, 'agwatch', assignments)

    print(f"  OK HOCMCV002 setup complete")


def setup_hocmcv003() -> None:
    """HOCMCV003: experimental, day 1 of therapy."""
    print("Setting up HOCMCV003 (experimental, day 1)…")

    homer_id = 'HOCMCV003'
    activation_date = '2026-04-08T10:00'

    # Step 1: populate activation dates
    populate_activation_dates(HOSPITAL, homer_id, activation_date)

    # Step 2: Read protocol events
    data = read_protocol_events(HOSPITAL, homer_id)
    incomplete = data['incomplete']
    complete = data['complete']

    # Move only exp_device_install and activation to complete
    new_incomplete = []
    for entry in incomplete:
        event_id = entry['protocol_event_id']

        if event_id == 'exp_device_install':
            complete.append(_move_to_complete(
                entry,
                activation_date,
                pluto_id='PLT-002',
                mars_id='MRS-002',
                demo_done=True,
                notes=''
            ))
        elif event_id == 'activation':
            complete.append(_move_to_complete(
                entry,
                activation_date,
                session_start=activation_date,
                session_end='2026-04-08T11:00',
                triggered=[],
                notes=''
            ))
        else:
            new_incomplete.append(entry)

    data['incomplete'] = new_incomplete
    data['complete'] = complete
    write_protocol_events(HOSPITAL, homer_id, data)

    # Step 3: Update patient meta
    meta = {
        'homerID': homer_id,
        'hospitalID': 'RP-T002',
        'group': 'experimental',
        'trainingSide': 'Left',
        'enrollDate': '2026-04-08T12:00',
        'a0CompletionDate': '2026-04-08T12:00',
        'activationDate': activation_date,
        'discontinuationDate': None,
        'trainingCompletionDate': None,
        'trainingPausedDate': None,
        'brokenProtocolDate': None,
        'a1CompletionDate': None,
        'a2CompletionDate': None,
        'cumulativePauseDays': 0,
        'pauseHistory': [],
        'vcgGroup': None,
        'agWatchRightID': None,
        'agWatchLeftID': None,
    }
    write_patient_meta(HOSPITAL, homer_id, meta)

    # Step 4: Write device assignments
    assignments = read_device_assignments(HOSPITAL, 'pluto')
    assignments.append({
        'device_id': 'PLT-002',
        'patient_id': homer_id,
        'assigned_date': activation_date,
        'returned_date': None,
    })
    write_device_assignments(HOSPITAL, 'pluto', assignments)

    assignments = read_device_assignments(HOSPITAL, 'mars')
    assignments.append({
        'device_id': 'MRS-002',
        'patient_id': homer_id,
        'assigned_date': activation_date,
        'returned_date': None,
    })
    write_device_assignments(HOSPITAL, 'mars', assignments)

    print(f"  OK HOCMCV003 setup complete")


def setup_hocmcv004() -> None:
    """HOCMCV004: control, day 15 of therapy."""
    print("Setting up HOCMCV004 (control, day 15)…")

    homer_id = 'HOCMCV004'
    activation_date = '2026-03-25T10:00'

    # Step 1: populate activation dates
    populate_activation_dates(HOSPITAL, homer_id, activation_date)

    # Step 2: Read protocol events
    data = read_protocol_events(HOSPITAL, homer_id)
    incomplete = data['incomplete']
    complete = data['complete']
    free = data['free']

    # Events to complete for day 15 control patient
    events_to_complete = {
        'activation': {
            'session_start': '2026-03-25T10:00',
            'session_end': '2026-03-25T11:00',
            'triggered': [],
            'notes': ''
        },
        'vcg_prescription_d01': {'notes': ''},
        'adl_prescription_d01': {'notes': ''},
        'prescription_printout_d01': {'notes': ''},
        'home_visit_d02': {'session_start': '2026-03-26T10:00', 'session_end': '2026-03-26T11:00', 'notes': ''},
        'home_visit_d03': {'session_start': '2026-03-27T10:00', 'session_end': '2026-03-27T11:00', 'notes': ''},
        'adl_agwatch_timing_d03': {'notes': ''},
        'vcg_agwatch_timing_d03': {'notes': ''},
    }

    completion_dates = {
        'activation': '2026-03-25T10:00',
        'vcg_prescription_d01': '2026-03-25T10:30',
        'adl_prescription_d01': '2026-03-25T10:30',
        'prescription_printout_d01': '2026-03-25T10:45',
        'home_visit_d02': '2026-03-26T10:00',
        'home_visit_d03': '2026-03-27T10:00',
        'adl_agwatch_timing_d03': '2026-03-27T11:00',
        'vcg_agwatch_timing_d03': '2026-03-27T11:30',
    }

    new_incomplete = []
    watch_record_entry = None
    activation_id = None

    for entry in incomplete:
        event_id = entry['protocol_event_id']

        if event_id in events_to_complete:
            entry_copy = _move_to_complete(
                entry,
                completion_dates[event_id],
                **events_to_complete[event_id]
            )
            if event_id == 'activation':
                activation_id = entry['id']
            complete.append(entry_copy)
        elif event_id == 'watch_record':
            watch_record_entry = entry
        else:
            new_incomplete.append(entry)

    # Move watch_record to free (day 3 entry) and seed next
    if watch_record_entry:
        watch_free_entry = {
            'id': str(uuid.uuid4()),
            'ag_watch_right': {'old_id': None, 'old_lost': False, 'new_id': 'AGW-003'},
            'ag_watch_left': {'old_id': None, 'old_lost': False, 'new_id': 'AGW-004'},
            'sync_datetime': '2026-03-27T10:00',
            'worn_datetime': '2026-03-27T10:00',
            'next_followup_days': 7,
            'notes': '',
            'triggered_by': {'type': 'activation', 'id': activation_id},
            'completion_date': '2026-03-27T10:00',
            'filed_at': '2026-03-27T10:00:00',
        }
        free['watch_record'].append(watch_free_entry)

        # Seed next watch_record in incomplete for day 15 (day 3 + 7 + 5)
        next_watch = {
            'id': str(uuid.uuid4()),
            'protocol_event_id': 'watch_record',
            'scheduled_date': ['2026-04-08T10:00', '2026-04-08T10:00'],
            'flagged': False,
            'notes': '',
        }
        new_incomplete.append(next_watch)

    data['incomplete'] = new_incomplete
    data['complete'] = complete
    data['free'] = free
    write_protocol_events(HOSPITAL, homer_id, data)

    # Step 3: Update patient meta
    meta = {
        'homerID': homer_id,
        'hospitalID': 'RP-T003',
        'group': 'control',
        'trainingSide': 'Right',
        'enrollDate': '2026-04-08T12:00',
        'a0CompletionDate': '2026-04-08T12:00',
        'activationDate': activation_date,
        'discontinuationDate': None,
        'trainingCompletionDate': None,
        'trainingPausedDate': None,
        'brokenProtocolDate': None,
        'a1CompletionDate': None,
        'a2CompletionDate': None,
        'cumulativePauseDays': 0,
        'pauseHistory': [],
        'vcgGroup': 'vcg2',
        'agWatchRightID': 'AGW-003',
        'agWatchLeftID': 'AGW-004',
    }
    write_patient_meta(HOSPITAL, homer_id, meta)

    # Step 4: Write device assignments (agwatch only for control)
    assignments = read_device_assignments(HOSPITAL, 'agwatch')
    assignments.extend([
        {
            'device_id': 'AGW-003',
            'patient_id': homer_id,
            'limb': 'Right',
            'assigned_date': '2026-03-27T10:00',
            'returned_date': None,
        },
        {
            'device_id': 'AGW-004',
            'patient_id': homer_id,
            'limb': 'Left',
            'assigned_date': '2026-03-27T10:00',
            'returned_date': None,
        },
    ])
    write_device_assignments(HOSPITAL, 'agwatch', assignments)

    print(f"  OK HOCMCV004 setup complete")


if __name__ == '__main__':
    print("Setting up rich test data for four ranipet patients…\n")

    setup_hocmcv002()
    setup_hocmcv003()
    setup_hocmcv004()
    # HOCMCV005 is left as-is from reset_test_patient.py (inactive)

    print("\nDone! Test data is ready.")
    print("\nPatient states:")
    print("  HOCMCV002 (experimental, day 7) — followup_call_d07 due today")
    print("  HOCMCV003 (experimental, day 1) — device setup & activation done, day-1 events ready")
    print("  HOCMCV004 (control, day 15)     — day-15 cluster of events ready")
    print("  HOCMCV005 (control, inactive)   — ready for activation flow")
