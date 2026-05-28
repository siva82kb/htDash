#!/usr/bin/env python3
"""
Migrate device data from flat type-grouped folders to per-type folders.

Usage: python scripts/migrate_device_data.py

Old structure:
  devices/inventory/{type}.json
  devices/assignments/{type}.json
  devices/fault_reports/{type}.json
  devices/events/{type}/{device_id}.json
  devices/logs/{type}/{device_id}.log
  devices/attachments/{type}/{event_id}.ext

New structure:
  devices/{folder}/inventory.json
  devices/{folder}/assignments.json
  devices/{folder}/faultReport.json
  devices/{folder}/events/{device_id}.json
  devices/{folder}/logs/{device_id}.log
  devices/{folder}/attachments/{event_id}.ext

Type → folder mapping:
  pluto → pluto, mars → mars, agwatch → agwatch
  modem/modems → modems, laptop/laptops → laptops
  sims → sims
"""

import json
import shutil
from pathlib import Path
from typing import Dict

TYPE_FOLDER = {
    'pluto': 'pluto', 'mars': 'mars', 'agwatch': 'agwatch',
    'modem': 'modems', 'modems': 'modems',
    'laptop': 'laptops', 'laptops': 'laptops',
    'sims': 'sims',
}

def type_folder(device_type: str) -> str:
    return TYPE_FOLDER.get(device_type, device_type)

def move_file(src: Path, dst: Path, description: str) -> bool:
    """Move file from src to dst, creating parent dirs. Return True if moved."""
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    print(f"[OK] {description}: {src.relative_to(src.parent.parent.parent)} -> {dst.relative_to(dst.parent.parent.parent)}")
    return True

def update_attachment_refs_in_events(events_dir: Path, old_type_folder: str, new_type_folder: str) -> None:
    """Update attachment field in all event JSONs from 'attachments/{type}/' → '{folder}/attachments/'."""
    if not events_dir.exists():
        return
    for event_file in events_dir.glob('*.json'):
        try:
            with open(event_file, encoding='utf-8') as f:
                data = json.load(f)
            events = data.get('events', [])
            updated = False
            for event in events:
                if 'attachment' in event and event['attachment']:
                    old_ref = f'attachments/{old_type_folder}/'
                    new_ref = f'{new_type_folder}/attachments/'
                    if event['attachment'].startswith(old_ref):
                        event['attachment'] = event['attachment'].replace(old_ref, new_ref, 1)
                        updated = True
            if updated:
                tmp = event_file.with_suffix('.tmp')
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                tmp.replace(event_file)
        except Exception as e:
            print(f"⚠ Warning: could not update attachment refs in {event_file}: {e}")

def migrate_hospital(hospital_path: Path) -> None:
    """Migrate one hospital's device data."""
    devices_dir = hospital_path / 'devices'
    if not devices_dir.exists():
        print(f"[SKIP] {hospital_path.name}: no devices/ folder")
        return

    print(f"\n[MIGRATE] {hospital_path.name}...")

    # 1. Migrate inventory files
    print("  Migrating inventory...")
    for device_type in ['pluto', 'mars', 'agwatch', 'modem', 'modems', 'laptop', 'laptops']:
        src = devices_dir / 'inventory' / f'{device_type}.json'
        dst = devices_dir / type_folder(device_type) / 'inventory.json'
        move_file(src, dst, f"Inventory {device_type}")

    # 2. Migrate SIMs (special case: from inventory/sims.json → sims/inventory.json)
    src = devices_dir / 'inventory' / 'sims.json'
    dst = devices_dir / 'sims' / 'inventory.json'
    move_file(src, dst, "SIM inventory")

    # 3. Migrate assignments
    print("  Migrating assignments...")
    for device_type in ['pluto', 'mars', 'agwatch', 'modem', 'modems', 'laptop', 'laptops', 'sims']:
        src = devices_dir / 'assignments' / f'{device_type}.json'
        dst = devices_dir / type_folder(device_type) / 'assignments.json'
        move_file(src, dst, f"Assignments {device_type}")

    # 4. Migrate fault reports
    print("  Migrating fault reports...")
    for device_type in ['pluto', 'mars', 'agwatch']:
        src = devices_dir / 'fault_reports' / f'{device_type}.json'
        dst = devices_dir / type_folder(device_type) / 'faultReport.json'
        move_file(src, dst, f"Fault reports {device_type}")

    # 5. Migrate logs (devices/logs/{folder}/*.log → devices/{folder}/logs/*.log)
    print("  Migrating logs...")
    logs_dir = devices_dir / 'logs'
    if logs_dir.exists():
        for subfolder in logs_dir.iterdir():
            if subfolder.is_dir():
                new_logs_dir = devices_dir / type_folder(subfolder.name) / 'logs'
                if subfolder.name in TYPE_FOLDER or subfolder.name in ['pluto', 'mars', 'agwatch', 'modems', 'laptops']:
                    new_logs_dir.parent.mkdir(parents=True, exist_ok=True)
                    for log_file in subfolder.glob('*.log'):
                        dst = new_logs_dir / log_file.name
                        move_file(log_file, dst, f"Log {subfolder.name}/{log_file.name}")

    # 6. Migrate events (devices/events/{type}/*.json → devices/{folder}/events/*.json)
    print("  Migrating events...")
    events_dir = devices_dir / 'events'
    if events_dir.exists():
        for type_dir in events_dir.iterdir():
            if type_dir.is_dir():
                new_events_dir = devices_dir / type_folder(type_dir.name) / 'events'
                new_events_dir.mkdir(parents=True, exist_ok=True)
                for event_file in type_dir.glob('*.json'):
                    dst = new_events_dir / event_file.name
                    move_file(event_file, dst, f"Events {type_dir.name}/{event_file.name}")

    # 7. Migrate attachments (devices/attachments/{type}/* → devices/{folder}/attachments/*)
    print("  Migrating attachments...")
    attachments_dir = devices_dir / 'attachments'
    if attachments_dir.exists():
        for type_dir in attachments_dir.iterdir():
            if type_dir.is_dir():
                new_attach_dir = devices_dir / type_folder(type_dir.name) / 'attachments'
                new_attach_dir.mkdir(parents=True, exist_ok=True)
                for attach_file in type_dir.glob('*'):
                    if attach_file.is_file():
                        dst = new_attach_dir / attach_file.name
                        move_file(attach_file, dst, f"Attachment {type_dir.name}/{attach_file.name}")

    # 8. Update attachment references in event JSONs
    print("  Updating attachment references...")
    for type_folder_name in ['pluto', 'mars', 'agwatch', 'modems', 'laptops', 'sims']:
        old_type = type_folder_name.rstrip('s') if type_folder_name.endswith('s') and type_folder_name != 'sims' else type_folder_name
        events_path = devices_dir / type_folder_name / 'events'
        update_attachment_refs_in_events(events_path, old_type, type_folder_name)

    # 9. Clean up empty old folders
    print("  Cleaning up empty folders...")
    for folder_name in ['inventory', 'assignments', 'fault_reports', 'events', 'attachments', 'logs']:
        old_folder = devices_dir / folder_name
        if old_folder.exists():
            try:
                # Remove only if empty
                if not any(old_folder.iterdir()):
                    old_folder.rmdir()
                    print(f"[OK] Removed empty {folder_name}/ folder")
            except OSError:
                print(f"[WARN] Could not remove {folder_name}/: still has files")

    print(f"  [DONE] {hospital_path.name} migration complete")

def main():
    from config import Config

    data_root = Path(Config.DATA_ROOT)
    if not data_root.exists():
        print(f"ERROR: DATA_ROOT not found: {data_root}")
        return

    print(f"Starting device data migration from {data_root}")

    hospital_count = 0
    for hospital_dir in sorted(data_root.iterdir()):
        if hospital_dir.is_dir() and (hospital_dir / 'devices').exists():
            migrate_hospital(hospital_dir)
            hospital_count += 1

    print(f"\nMigration complete! ({hospital_count} hospitals processed)")
    print("Next: test the app to ensure everything works")

if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    main()
