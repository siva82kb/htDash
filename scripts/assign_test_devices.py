"""Assign devices to the test patients after setup_test_data has run."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from utils.data_access import read_device_assignments, write_device_assignments

HOSPITAL = 'ranipet'

def assign_devices() -> None:
    """Write device assignments for the three activated test patients."""

    # Pluto assignments
    pluto_assignments = [
        {'device_id': 'PLT-001', 'patient_id': 'HOCMCV002', 'assigned_date': '2026-04-02T10:00', 'returned_date': None},
        {'device_id': 'PLT-002', 'patient_id': 'HOCMCV003', 'assigned_date': '2026-04-08T10:00', 'returned_date': None},
    ]
    write_device_assignments(HOSPITAL, 'pluto', pluto_assignments)
    print(f"Assigned {len(pluto_assignments)} Pluto devices")

    # Mars assignments
    mars_assignments = [
        {'device_id': 'MRS-001', 'patient_id': 'HOCMCV002', 'assigned_date': '2026-04-02T10:00', 'returned_date': None},
        {'device_id': 'MRS-002', 'patient_id': 'HOCMCV003', 'assigned_date': '2026-04-08T10:00', 'returned_date': None},
    ]
    write_device_assignments(HOSPITAL, 'mars', mars_assignments)
    print(f"Assigned {len(mars_assignments)} Mars devices")

    # AG Watch assignments
    agwatch_assignments = [
        {'device_id': 'AGW-001', 'patient_id': 'HOCMCV002', 'limb': 'Right', 'assigned_date': '2026-04-04T10:00', 'returned_date': None},
        {'device_id': 'AGW-002', 'patient_id': 'HOCMCV002', 'limb': 'Left', 'assigned_date': '2026-04-04T10:00', 'returned_date': None},
        {'device_id': 'AGW-003', 'patient_id': 'HOCMCV004', 'limb': 'Right', 'assigned_date': '2026-03-27T10:00', 'returned_date': None},
        {'device_id': 'AGW-004', 'patient_id': 'HOCMCV004', 'limb': 'Left', 'assigned_date': '2026-03-27T10:00', 'returned_date': None},
    ]
    write_device_assignments(HOSPITAL, 'agwatch', agwatch_assignments)
    print(f"Assigned {len(agwatch_assignments)} AG Watch devices")

    print("\nDone! Device assignments ready.")

if __name__ == '__main__':
    assign_devices()
