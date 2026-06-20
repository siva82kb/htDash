# routes/devices.py
from flask import Blueprint, request, jsonify, render_template
from flask import session as flask_session
from config import Config
from models.user import current_session
from utils.data_access import (
    get_hospital_folder,
    read_device_inventory,
    read_device_assignments,
    write_device_assignments,
    write_device_inventory,
    read_sims,
    write_sims,
    mark_device_faulty,
    mark_device_not_faulty,
    write_device_log,
    _type_folder,
    read_patient_meta,
    find_patient_folder,
)
from utils.device_events import (
    append_device_event,
    read_all_device_events,
    read_device_events,
    get_open_issues,
    get_resolved_issues,
    update_device_event,
)
import os
import json
from datetime import datetime, date
import uuid
from pathlib import Path

bp = Blueprint('devices', __name__)

def get_devices_file_path(place=None):
    if not place:
        place = current_session.login_place
    folder = os.path.join(Config.META_DATA_PATH, place)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'devices.json')

def load_devices(place=None):
    file_path = get_devices_file_path(place)
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    return {'deviceSets': [], 'watches': []}

def save_devices(data, place=None):
    """Atomic save to prevent JSON corruption"""
    import tempfile
    file_path = get_devices_file_path(place)
    dir_path = os.path.dirname(file_path)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, file_path)
    except Exception:
        try: os.unlink(tmp_path)
        except OSError: pass
        raise

@bp.route('/', methods=['GET'])
def get_devices():
    """Get all devices for the current centre"""
    try:
        devices = load_devices()
        return jsonify({'status': 'success', 'devices': devices})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/device_sets', methods=['GET'])
def get_device_sets():
    """Get all device sets"""
    try:
        devices = load_devices()
        return jsonify({'status': 'success', 'deviceSets': devices.get('deviceSets', [])})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/device_sets', methods=['POST'])
def create_device_set():
    """Create a new device set"""
    try:
        data = request.get_json()
        devices = load_devices()
        
        device_set = {
            'id': str(uuid.uuid4()),
            'setNumber': data.get('setNumber'),
            'marsDeviceId': data.get('marsDeviceId'),
            'plutoDeviceId': data.get('plutoDeviceId'),
            'laptopNumber': data.get('laptopNumber'),
            'modemSerial': data.get('modemSerial'),
            'status': 'available',
            'assignedPatientId': None,
            'assignmentDate': None,
            'expectedReturnDate': None,
            'returnDate': None,
            'createdAt': datetime.now().isoformat()
        }
        
        devices.setdefault('deviceSets', []).append(device_set)
        save_devices(devices)
        
        return jsonify({'status': 'success', 'deviceSet': device_set})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/device_sets/<device_id>', methods=['PUT'])
def update_device_set(device_id):
    """Update a device set"""
    try:
        data = request.get_json()
        devices = load_devices()
        
        for ds in devices.get('deviceSets', []):
            if ds['id'] == device_id:
                ds.update(data)
                ds['updatedAt'] = datetime.now().isoformat()
                break
        
        save_devices(devices)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/device_sets/<device_id>', methods=['DELETE'])
def delete_device_set(device_id):
    """Delete a device set"""
    try:
        devices = load_devices()
        
        devices['deviceSets'] = [ds for ds in devices.get('deviceSets', []) if ds['id'] != device_id]
        
        save_devices(devices)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/device_sets/<device_id>/assign', methods=['POST'])
def assign_device_set(device_id):
    """Assign a device set to a patient"""
    try:
        data = request.get_json()
        devices = load_devices()
        
        for ds in devices.get('deviceSets', []):
            if ds['id'] == device_id:
                ds['status'] = 'assigned'
                ds['assignedPatientId'] = data.get('patientId')
                ds['assignmentDate'] = datetime.now().isoformat()
                if data.get('expectedReturnDate'):
                    ds['expectedReturnDate'] = data.get('expectedReturnDate')
                ds['updatedAt'] = datetime.now().isoformat()
                break
        
        save_devices(devices)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/device_sets/<device_id>/return', methods=['POST'])
def return_device_set(device_id):
    """Return a device set"""
    try:
        devices = load_devices()
        
        for ds in devices.get('deviceSets', []):
            if ds['id'] == device_id:
                ds['status'] = 'available'
                ds['assignedPatientId'] = None
                ds['returnDate'] = datetime.now().isoformat()
                ds['updatedAt'] = datetime.now().isoformat()
                break
        
        save_devices(devices)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ActiGraph Watches
@bp.route('/watches', methods=['GET'])
def get_watches():
    """Get all watches"""
    try:
        devices = load_devices()
        return jsonify({'status': 'success', 'watches': devices.get('watches', [])})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/watches', methods=['POST'])
def create_watch():
    """Create a new watch"""
    try:
        data = request.get_json()
        devices = load_devices()
        
        watch = {
            'id': str(uuid.uuid4()),
            'name': data.get('name'),
            'leftSerial': data.get('leftSerial'),
            'rightSerial': data.get('rightSerial'),
            'status': 'available',
            'assignedPatientId': None,
            'assignmentDate': None,
            'isBackup': data.get('isBackup', False),
            'createdAt': datetime.now().isoformat()
        }
        
        devices.setdefault('watches', []).append(watch)
        save_devices(devices)
        
        return jsonify({'status': 'success', 'watch': watch})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/watches/<watch_id>', methods=['PUT'])
def update_watch(watch_id):
    """Update a watch"""
    try:
        data = request.get_json()
        devices = load_devices()
        
        for watch in devices.get('watches', []):
            if watch['id'] == watch_id:
                watch.update(data)
                watch['updatedAt'] = datetime.now().isoformat()
                break
        
        save_devices(devices)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/watches/<watch_id>', methods=['DELETE'])
def delete_watch(watch_id):
    """Delete a watch"""
    try:
        devices = load_devices()
        
        devices['watches'] = [w for w in devices.get('watches', []) if w['id'] != watch_id]
        
        save_devices(devices)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/watches/<watch_id>/assign', methods=['POST'])
def assign_watch(watch_id):
    """Assign a watch to a patient"""
    try:
        data = request.get_json()
        devices = load_devices()
        
        for watch in devices.get('watches', []):
            if watch['id'] == watch_id:
                watch['status'] = 'assigned'
                watch['assignedPatientId'] = data.get('patientId')
                watch['assignmentDate'] = datetime.now().isoformat()
                watch['updatedAt'] = datetime.now().isoformat()
                break
        
        save_devices(devices)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@bp.route('/watches/<watch_id>/return', methods=['POST'])
def return_watch(watch_id):
    """Return a watch"""
    try:
        devices = load_devices()
        
        for watch in devices.get('watches', []):
            if watch['id'] == watch_id:
                watch['status'] = 'available'
                watch['assignedPatientId'] = None
                watch['returnDate'] = datetime.now().isoformat()
                watch['updatedAt'] = datetime.now().isoformat()
                break
        
        save_devices(devices)
        
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Device statistics for dashboard
@bp.route('/stats', methods=['GET'])
def get_device_stats():
    """Get device statistics"""
    try:
        devices = load_devices()
        
        device_sets = devices.get('deviceSets', [])
        watches = devices.get('watches', [])
        
        available_sets = sum(1 for ds in device_sets if ds.get('status') == 'available')
        assigned_sets = sum(1 for ds in device_sets if ds.get('status') == 'assigned')
        dropped_sets = sum(1 for ds in device_sets if ds.get('status') == 'dropped')
        
        available_watches = sum(1 for w in watches if w.get('status') == 'available')
        assigned_watches = sum(1 for w in watches if w.get('status') == 'assigned')
        
        return jsonify({
            'status': 'success',
            'stats': {
                'deviceSets': {
                    'total': len(device_sets),
                    'available': available_sets,
                    'assigned': assigned_sets,
                    'dropped': dropped_sets
                },
                'watches': {
                    'total': len(watches),
                    'available': available_watches,
                    'assigned': assigned_watches
                }
            }
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


def load_device_config():
    """Load the predefined device configuration"""
    config_path = os.path.join(Config.BASE_DIR, Config.DEVICE_CONFIG_PATH)
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return {'locations': {}}


@bp.route('/config/<place>', methods=['GET'])
def get_device_config(place):
    """Get device configuration for a specific location"""
    try:
        config = load_device_config()
        location_config = config.get('locations', {}).get(place, {})
        return jsonify({
            'status': 'success',
            'location': place,
            'deviceSets': location_config.get('deviceSets', [])
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bp.route('/config/available/<place>', methods=['GET'])
def get_available_device_sets(place):
    """Get available (unassigned) device sets for a location"""
    try:
        config = load_device_config()
        location_config = config.get('locations', {}).get(place, {})
        
        devices = load_devices()
        assigned_set_ids = {ds.get('assignedDeviceSetId') for ds in devices.get('deviceSets', []) if ds.get('assignedDeviceSetId')}
        
        available_sets = []
        for ds in location_config.get('deviceSets', []):
            if ds.get('setId') not in assigned_set_ids:
                available_sets.append(ds)
        
        return jsonify({
            'status': 'success',
            'availableSets': available_sets
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bp.route('/assign_from_config', methods=['POST'])
def assign_device_from_config():
    """Assign a device set from predefined config to a patient"""
    try:
        data = request.get_json()
        place = data.get('place')
        patient_id = data.get('patientId')
        set_id = data.get('setId')
        
        if not place or not patient_id or not set_id:
            return jsonify({'status': 'error', 'message': 'place, patientId, and setId are required'}), 400
        
        config = load_device_config()
        location_config = config.get('locations', {}).get(place, {})
        
        selected_set = None
        for ds in location_config.get('deviceSets', []):
            if ds.get('setId') == set_id:
                selected_set = ds
                break
        
        if not selected_set:
            return jsonify({'status': 'error', 'message': 'Device set not found'}), 404
        
        devices = load_devices(place)
        
        device_set = {
            'id': str(uuid.uuid4()),
            'setNumber': selected_set.get('setId'),
            'marsDeviceId': selected_set.get('mars'),
            'plutoDeviceId': selected_set.get('pluto'),
            'modemSerial': selected_set.get('modem'),
            'simCard': selected_set.get('simCard'),
            'simNumber': data.get('simNumber') or selected_set.get('simCard'),
            'laptopNumber': selected_set.get('laptop'),
            'assignedDeviceSetId': set_id,
            'status': 'assigned',
            'assignedPatientId': patient_id,
            'assignmentDate': datetime.now().isoformat(),
            'createdAt': datetime.now().isoformat()
        }
        
        devices.setdefault('deviceSets', []).append(device_set)
        save_devices(devices, place)
        
        return jsonify({'status': 'success', 'deviceSet': device_set})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


def get_device_swap_history_file_path(place=None):
    if not place:
        place = current_session.login_place
    folder = os.path.join(Config.META_DATA_PATH, place)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, 'device_swap_history.json')


def load_device_swap_history(place=None):
    file_path = get_device_swap_history_file_path(place)
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return json.load(f)
    return {'swaps': []}


def save_device_swap_history(data, place=None):
    import tempfile
    file_path = get_device_swap_history_file_path(place)
    dir_path = os.path.dirname(file_path)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w') as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, file_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


@bp.route('/swap_history/<patient_id>', methods=['GET'])
def get_device_swap_history(patient_id):
    """Get device swap history for a patient"""
    try:
        place = (
            current_session.place_info.get(patient_id, current_session.login_place)
            if current_session.is_admin()
            else current_session.login_place
        )
        
        history = load_device_swap_history(place)
        patient_swaps = [s for s in history.get('swaps', []) if s.get('patientId') == patient_id]
        
        return jsonify({
            'status': 'success',
            'swaps': patient_swaps
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bp.route('/swap', methods=['POST'])
def record_device_swap():
    """Record a device swap for a patient"""
    try:
        data = request.get_json()
        patient_id = data.get('patientId')
        device_type = data.get('deviceType')
        old_device_id = data.get('oldDeviceId')
        new_device_id = data.get('newDeviceId')
        reason = data.get('reason', '')
        swap_date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        if not patient_id or not device_type or not new_device_id:
            return jsonify({'status': 'error', 'message': 'patientId, deviceType, and newDeviceId are required'}), 400
        
        place = (
            current_session.place_info.get(patient_id, current_session.login_place)
            if current_session.is_admin()
            else current_session.login_place
        )
        
        history = load_device_swap_history(place)
        
        swap_record = {
            'id': str(uuid.uuid4()),
            'patientId': patient_id,
            'deviceType': device_type,
            'oldDeviceId': old_device_id,
            'newDeviceId': new_device_id,
            'reason': reason,
            'date': swap_date,
            'swappedAt': datetime.now().isoformat(),
            'swappedBy': current_session.login_place
        }
        
        history.setdefault('swaps', []).append(swap_record)
        save_device_swap_history(history, place)
        
        return jsonify({'status': 'success', 'swap': swap_record})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@bp.route('/swap_history_all', methods=['GET'])
def get_all_swap_history():
    """Get all device swap history for the current location"""
    try:
        history = load_device_swap_history()
        return jsonify({'status': 'success', 'swaps': history.get('swaps', [])})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Devices page (HTML) ───────────────────────────────────────────────────────

@bp.route('/page', methods=['GET'])
def devices_page():
    """Render the Device Management HTML page."""
    if not flask_session.get('login_place'):
        from flask import redirect, url_for
        return redirect(url_for('login'))
    # Devices page visible only to engineers and admins
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden — device management requires engineer or admin privilege'}), 403
    return render_template('devices.html', active_page='devices')


# ── Device inventory API ──────────────────────────────────────────────────────

@bp.route('/api/inventory', methods=['GET'])
def api_device_inventory():
    """Return the full device inventory with current assignment info for the user's site."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    # Device inventory visible only to engineers and admins
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden — device management requires engineer or admin privilege'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    from utils.data_access import get_patients_for_user
    patients = get_patients_for_user(flask_session['login_place'])
    patient_map = {p['homerID']: p for p in patients}

    def _assignment_info(device_id, assignments, limb=False):
        for a in assignments:
            if a.get('device_id') == device_id and a.get('returned_date') is None:
                homer_id = a.get('patient_id') or a.get('homer_id')
                p = patient_map.get(homer_id, {})
                info = {'homerID': homer_id, 'hospitalID': p.get('hospitalID')}
                if limb:
                    info['limb'] = a.get('limb')
                return info
        return None

    # ── 28-day auto-reset for all assigned device types ──────────────────────
    # Count from the patient's activationDate, not the assignment date.
    # Pluto/mars: skip if faulty. Agwatch: skip if has_issue (lost watches have
    # no active assignment anyway). Modems/laptops: unchanged behaviour.
    # Cache the assignments per dtype after auto-reset, to avoid double-read race
    # between the auto-reset pass and the inventory response construction.
    now_str = datetime.now().strftime('%Y-%m-%dT%H:%M')
    cached_assignments = {}
    for dtype in ('modems', 'laptops', 'pluto', 'mars', 'agwatch'):
        asgns = read_device_assignments(folder, dtype)
        cached_assignments[dtype] = asgns  # cache the read
        inv   = {d['id']: d for d in read_device_inventory(folder, dtype)}
        changed = False
        for a in asgns:
            if a.get('returned_date') is None:
                try:
                    dev = inv.get(a.get('device_id', ''), {})
                    # Don't auto-return devices with active issues
                    if dev.get('faulty') or dev.get('has_issue'):
                        continue
                    homer_id = a.get('homer_id') or a.get('patient_id', '')
                    activation = (patient_map.get(homer_id) or {}).get('activationDate')
                    if not activation:
                        continue   # patient not yet activated — don't reset
                    dt = datetime.fromisoformat(activation)
                    if (datetime.now() - dt).days >= 28:
                        a['returned_date'] = now_str
                        changed = True
                except Exception:
                    pass
        if changed:
            write_device_assignments(folder, dtype, asgns)

    result = {}

    # pluto / mars
    for dtype in ('pluto', 'mars'):
        inventory   = read_device_inventory(folder, dtype)
        assignments = cached_assignments[dtype]
        result[dtype] = []
        for d in inventory:
            result[dtype].append({
                'id':           d['id'],
                'serial':       d.get('serial', ''),
                'clinic_only':  d.get('clinic_only', False),
                'faulty':       d.get('faulty', False),
                'has_issue':    d.get('has_issue', False),
                'removal_date': d.get('removal_date'),
                'assigned_to':  _assignment_info(d['id'], assignments),
            })

    # agwatch — include limb from assignment record
    inventory   = read_device_inventory(folder, 'agwatch')
    assignments = cached_assignments['agwatch']
    result['agwatch'] = []
    for d in inventory:
        result['agwatch'].append({
            'id':           d['id'],
            'serial':       d.get('serial', ''),
            'limb_default': d.get('limb_default', ''),
            'has_issue':    d.get('has_issue', False),
            'lost':         d.get('lost_date') is not None,
            'removal_date': d.get('removal_date'),
            'assigned_to':  _assignment_info(d['id'], assignments, limb=True),
        })

    # modems — resolve sim_info from sims.json
    all_sims = read_sims(folder)
    sim_map  = {s['id']: s for s in all_sims}

    modem_inv  = read_device_inventory(folder, 'modems')
    modem_asgn = cached_assignments['modems']

    # build set of modems that have an active patient assignment
    modem_active = {d['id'] for d in modem_inv if _assignment_info(d['id'], modem_asgn)}

    result['modems'] = []
    for d in modem_inv:
        sim_id   = d.get('sim_id')
        sim_info = None
        if sim_id and sim_id in sim_map:
            s = sim_map[sim_id]
            sim_info = {'id': sim_id, 'phoneNumber': s.get('phoneNumber'), 'network': s.get('network')}
        result['modems'].append({
            'id':           d['id'],
            'serial':       d.get('serial', ''),
            'sim_id':       sim_id,
            'sim_info':     sim_info,
            'has_issue':    d.get('has_issue', False),
            'removal_date': d.get('removal_date'),
            'assigned_to':  _assignment_info(d['id'], modem_asgn),
        })

    # laptops
    laptop_inv  = read_device_inventory(folder, 'laptops')
    laptop_asgn = cached_assignments['laptops']
    result['laptops'] = []
    for d in laptop_inv:
        result['laptops'].append({
            'id':           d['id'],
            'serial':       d.get('serial', ''),
            'has_issue':    d.get('has_issue', False),
            'removal_date': d.get('removal_date'),
            'assigned_to':  _assignment_info(d['id'], laptop_asgn),
        })

    # sims — compute expiry for all SIMs regardless of modem assignment status
    today = date.today()
    result['sims'] = []
    for s in all_sims:
        entry = {k: v for k, v in s.items()}
        linked_modem = next((d['id'] for d in modem_inv if d.get('sim_id') == s['id']), None)
        entry['modem_id'] = linked_modem
        if s.get('expiryDate'):
            try:
                expiry = datetime.strptime(s['expiryDate'], '%Y-%m-%d').date()
                diff   = (expiry - today).days
                entry['daysUntilExpiry'] = diff
                entry['isExpired']       = diff < 0
            except Exception:
                pass
        result['sims'].append(entry)

    # active experimental patients only (for assign-device dropdown)
    from utils.data_access import derive_status
    assignable_statuses = {'inactive', 'active', 'paused', 'training_complete', 'broken_protocol'}
    result['patients'] = sorted(
        [
            {'homerID': p['homerID'], 'hospitalID': p.get('hospitalID', '')}
            for p in patients
            if p.get('group') == 'experimental'
            and derive_status(p) in assignable_statuses
        ],
        key=lambda p: p['homerID']
    )

    return jsonify(result)


# ── Add device (admin only) ───────────────────────────────────────────────────

@bp.route('/api/add', methods=['POST'])
def api_add_device():
    """Add a new device or SIM to inventory. Admin only."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') != 'admin':
        return jsonify({'error': 'Forbidden — admin only'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data  = request.get_json() or {}
    dtype = (data.get('device_type') or '').strip().lower()

    # ── SIM card ──────────────────────────────────────────────────────────────
    if dtype == 'sim':
        phone  = (data.get('phoneNumber') or '').strip()
        if not phone:
            return jsonify({'error': 'phoneNumber is required'}), 400
        sims_list = read_sims(folder)
        if any(s['id'] == phone for s in sims_list):
            return jsonify({'error': f'SIM with phone number {phone} already exists'}), 409
        new_sim = {
            'id':            phone,
            'phoneNumber':   phone,
            'network':       (data.get('network') or '').strip(),
            'rechargeDate':  data.get('rechargeDate') or None,
            'expiryDate':    data.get('expiryDate') or None,
            'rechargeAmount': data.get('rechargeAmount') or None,
            'dataPlan':      data.get('dataPlan') or None,
            'reminderDays':  int(data.get('reminderDays') or 3),
            'status':        'active',
            'notes':         data.get('notes') or '',
            'createdAt':     datetime.now().isoformat(),
        }
        sims_list.append(new_sim)
        write_sims(folder, sims_list)
        return jsonify({'status': 'success', 'device': new_sim})

    # ── Hardware devices ──────────────────────────────────────────────────────
    valid_types = ('pluto', 'mars', 'agwatch', 'modem', 'laptop')
    if dtype not in valid_types:
        return jsonify({'error': f'device_type must be one of: {", ".join(valid_types)} or sim'}), 400

    # Normalise to plural filename form used in inventory/assignments files
    if dtype == 'modem':
        dtype = 'modems'
    elif dtype == 'laptop':
        dtype = 'laptops'

    device_id = (data.get('id') or '').strip()
    serial    = (data.get('serial') or '').strip()
    if not device_id or not serial:
        return jsonify({'error': 'id and serial are required'}), 400

    inv_data = {'devices': read_device_inventory(folder, dtype)}
    if any(d['id'] == device_id for d in inv_data['devices']):
        return jsonify({'error': f'Device ID {device_id!r} already exists'}), 409

    new_device = {
        'id':             device_id,
        'serial':         serial,
        'clinic_only':    False,
        'inclusion_date': datetime.now().strftime('%Y-%m-%d'),
        'removal_date':   None,
    }
    if dtype in ('pluto', 'mars'):
        new_device['faulty'] = False
    elif dtype == 'agwatch':
        new_device['lost_date'] = None
        new_device['has_issue'] = False
        limb_default = (data.get('limb_default') or '').strip()
        if limb_default in ('Left', 'Right'):
            new_device['limb_default'] = limb_default
    elif dtype == 'modem':
        sim_id = (data.get('sim_id') or '').strip() or None
        if sim_id:
            # validate SIM exists and isn't already linked
            all_sim_ids = {s['id'] for s in read_sims(folder)}
            if sim_id not in all_sim_ids:
                return jsonify({'error': 'SIM not found'}), 404
            existing_modems = read_device_inventory(folder, 'modems')
            if any(m.get('sim_id') == sim_id for m in existing_modems):
                return jsonify({'error': 'SIM is already linked to another modem'}), 409
        new_device['sim_id'] = sim_id

    inv_data['devices'].append(new_device)
    write_device_inventory(folder, dtype, inv_data)

    loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    session_id = flask_session.get('session_id', 0) or 0
    write_device_log(folder, device_id, loginid, session_id, 'Added to inventory', device_type=dtype)
    return jsonify({'status': 'success', 'device': new_device})


# ── Toggle clinic_only ────────────────────────────────────────────────────────

@bp.route('/api/toggle-clinic', methods=['POST'])
def api_toggle_clinic():
    """Toggle clinic_only flag on a pluto/mars device. Admin only.
    Server computes new value (flips current). Enforces one-per-type rule:
    setting a device to clinic_only=True clears any other device of the same type.
    Device must be Available (not assigned, not faulty) to be set as clinic.
    """
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden — device management requires engineer or admin privilege'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data      = request.get_json() or {}
    dtype     = (data.get('device_type') or '').strip().lower()
    device_id = (data.get('device_id') or '').strip()

    if dtype not in ('pluto', 'mars') or not device_id:
        return jsonify({'error': 'device_type must be pluto or mars, device_id is required'}), 400

    devices = read_device_inventory(folder, dtype)
    target  = next((d for d in devices if d['id'] == device_id), None)
    if not target:
        return jsonify({'error': 'Device not found'}), 404

    new_clinic = not target.get('clinic_only', False)
    loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    session_id = flask_session.get('session_id', 0) or 0

    if new_clinic:
        # Validate device is in Available state: not faulty, not assigned
        if target.get('faulty'):
            return jsonify({'error': 'Cannot set clinic: device has an issue'}), 409
        assignments = read_device_assignments(folder, dtype)
        if any(a.get('device_id') == device_id and a.get('returned_date') is None for a in assignments):
            return jsonify({'error': 'Cannot set clinic: device is currently assigned to a patient'}), 409
        # One-per-type: clear any other device that is currently clinic_only
        for d in devices:
            if d['id'] != device_id and d.get('clinic_only'):
                d['clinic_only'] = False
                write_device_log(folder, d['id'], loginid, session_id, 'Clinic status cleared (replaced by another device)', device_type=dtype)

    target['clinic_only'] = new_clinic
    write_device_inventory(folder, dtype, {'devices': devices})
    action = 'Marked clinic-only' if new_clinic else 'Marked assignable (removed from clinic)'
    write_device_log(folder, device_id, loginid, session_id, action, device_type=dtype)
    return jsonify({'status': 'success', 'clinic_only': new_clinic})


# ── Get patient enrollment date for date validation ─────────────────────────────

@bp.route('/api/device-validation-dates', methods=['POST'])
def api_device_validation_dates():
    """Fetch patient enrollment date and device issue occurrence date for validation."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data = request.get_json() or {}
    dtype = (data.get('device_type') or '').strip().lower()
    device_id = (data.get('device_id') or '').strip()

    if dtype not in ('pluto', 'mars', 'agwatch', 'modems', 'laptops') or not device_id:
        return jsonify({'error': 'device_type and device_id are required'}), 400

    # Get device inventory to find assigned patient
    devices = read_device_inventory(folder, dtype)
    device = next((d for d in devices if d['id'] == device_id), None)
    if not device:
        return jsonify({'error': 'Device not found'}), 404

    enroll_date = None
    issue_occur_date = None

    # If device is assigned to a patient, get their activation date
    if device.get('assigned_to'):
        homer_id = device['assigned_to'].get('homerID')
        patient_folder = find_patient_folder(flask_session['login_place'], homer_id)
        if patient_folder:
            patient = read_patient_meta(patient_folder, homer_id)
            if patient:
                enroll_date = patient.get('activationDate')

    # Get device's issue occurrence date from faulty event
    try:
        events_data = read_device_events(folder, dtype, device_id)
        events = events_data.get('events', [])
        # Find the most recent faulty event
        for ev in sorted(events, key=lambda e: e.get('date', ''), reverse=True):
            if ev.get('event_type') == 'faulty':
                issue_occur_date = ev.get('issue_occur_date') or ev.get('date', '').split('T')[0]
                break
    except Exception as e:
        # Silently continue if no events found
        pass

    return jsonify({
        'enroll_date': enroll_date,
        'issue_occur_date': issue_occur_date,
    })


# ── Toggle issue state ────────────────────────────────────────────────────────

@bp.route('/api/toggle-issue', methods=['POST'])
def api_toggle_issue():
    """Mark/unmark device issue. Admin or engineer."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden — device management requires engineer or admin privilege'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data         = request.get_json() or {}
    dtype        = (data.get('device_type') or '').strip().lower()
    device_id    = (data.get('device_id') or '').strip()
    has_issue    = bool(data.get('has_issue'))
    notes        = (data.get('notes') or '').strip()
    resolve_date = (data.get('resolve_date') or '').strip() or None
    issue_date   = (data.get('issue_date') or '').strip() or None

    if dtype not in ('pluto', 'mars', 'agwatch', 'modems', 'laptops') or not device_id:
        return jsonify({'error': 'device_type (pluto/mars/agwatch/modems/laptops) and device_id are required'}), 400

    # Validate issue_date (when reporting issue)
    if has_issue and issue_date:
        try:
            issue_dt = datetime.strptime(issue_date, '%Y-%m-%d')
            today = datetime.now()
            if issue_dt > today:
                return jsonify({'error': 'Issue occurred date cannot be in the future'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid issue date format'}), 400

    # Validate resolve_date (when resolving issue)
    if not has_issue and resolve_date:
        try:
            resolve_dt = datetime.strptime(resolve_date, '%Y-%m-%d')
            today = datetime.now()
            if resolve_dt > today:
                return jsonify({'error': 'Resolution date cannot be in the future'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid resolution date format'}), 400

    if dtype in ('pluto', 'mars'):
        if has_issue:
            mark_device_faulty(folder, dtype, device_id)
        else:
            mark_device_not_faulty(folder, dtype, device_id)
    else:
        # agwatch / modems / laptops — use has_issue field
        inv_data = {'devices': read_device_inventory(folder, dtype)}
        found = False
        for d in inv_data['devices']:
            if d['id'] == device_id:
                d['has_issue'] = has_issue
                found = True
                break
        if not found:
            return jsonify({'error': 'Device not found'}), 404
        write_device_inventory(folder, dtype, inv_data)

    loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    session_id = flask_session.get('session_id', 0) or 0
    action = f'Issue {"reported" if has_issue else "resolved"}'
    if notes:
        action += f' — {notes}'
    write_device_log(folder, device_id, loginid, session_id, action, device_type=dtype)

    # When resolving: check if a faulty event already exists in the file.
    # If not (inventory flag was set without an event), synthesise one so
    # get_resolved_issues can form a faulty→repair pair.
    if not has_issue:
        existing = read_device_events(folder, dtype, device_id)
        events = existing.get('events', [])
        # Determine if there is an unresolved faulty event
        pending_faulty = None
        for ev in sorted(events, key=lambda e: e.get('date', '')):
            if ev.get('event_type') == 'faulty':
                pending_faulty = ev
            elif ev.get('event_type') in ('repair', 'available', 'retire', 'discarded', 'lost'):
                pending_faulty = None
        if pending_faulty is None:
            append_device_event(folder, dtype, device_id,
                                event_type='faulty',
                                by='system',
                                notes='(Auto-recorded: issue existed before event logging)')

    event_id = append_device_event(folder, dtype, device_id,
                                   event_type='faulty' if has_issue else 'repair',
                                   by=loginid, notes=notes,
                                   event_date=issue_date if has_issue else resolve_date)
    return jsonify({'status': 'success', 'event_id': event_id})


# ── Mark device lost (permanent retire) ──────────────────────────────────────

@bp.route('/api/lose-device', methods=['POST'])
def api_lose_device():
    """Permanently retire a device as lost. Sets removal_date and appends lost event."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') == 'user':
        return jsonify({'error': 'Forbidden'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data      = request.get_json() or {}
    dtype     = (data.get('device_type') or '').strip().lower()
    device_id = (data.get('device_id') or '').strip()
    notes     = (data.get('notes') or '').strip()

    if dtype not in ('modems', 'laptops', 'agwatch') or not device_id:
        return jsonify({'error': 'device_type (modems/laptops/agwatch) and device_id are required'}), 400

    inv_data = {'devices': read_device_inventory(folder, dtype)}
    found = False
    for d in inv_data['devices']:
        if d['id'] == device_id:
            d['removal_date'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            d['has_issue'] = False
            found = True
            break
    if not found:
        return jsonify({'error': 'Device not found'}), 404
    write_device_inventory(folder, dtype, inv_data)

    loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    session_id = flask_session.get('session_id', 0) or 0
    action = 'Marked as lost (permanently retired)'
    if notes:
        action += f' — {notes}'
    write_device_log(folder, device_id, loginid, session_id, action, device_type=dtype)
    event_id = append_device_event(folder, dtype, device_id,
                                   event_type='lost',
                                   by=loginid, notes=notes)
    return jsonify({'status': 'success', 'event_id': event_id})


# ── Recharge SIM ─────────────────────────────────────────────────────────────

@bp.route('/api/recharge-sim', methods=['POST'])
def api_recharge_sim():
    """Record a SIM recharge — updates rechargeDate, expiryDate, dataPlan. Admin or engineer."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden — device management requires engineer or admin privilege'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data   = request.get_json() or {}
    sim_id = (data.get('sim_id') or '').strip()
    if not sim_id:
        return jsonify({'error': 'sim_id is required'}), 400

    sims = read_sims(folder)
    target = next((s for s in sims if s['id'] == sim_id), None)
    if not target:
        return jsonify({'error': 'SIM not found'}), 404

    target['rechargeDate'] = data.get('rechargeDate') or None
    target['expiryDate']   = data.get('expiryDate') or None
    target['dataPlan']     = data.get('dataPlan') or None
    target['updatedAt']    = datetime.now().isoformat()
    write_sims(folder, sims)
    loginid = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    append_device_event(folder, 'sims', sim_id, event_type='recharge', by=loginid,
                        notes=f"Plan: {target['dataPlan'] or '—'}, Expiry: {target['expiryDate'] or '—'}")
    return jsonify({'status': 'success'})


# ── Link SIM to modem ─────────────────────────────────────────────────────────

@bp.route('/api/link-sim', methods=['POST'])
def api_link_sim():
    """Link a SIM card to a modem. Admin or engineer."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden — device management requires engineer or admin privilege'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data      = request.get_json() or {}
    modem_id  = (data.get('modem_id') or '').strip()
    sim_id    = (data.get('sim_id') or '').strip() or None  # None = unlink

    inv_data = {'devices': read_device_inventory(folder, 'modems')}

    # Validate SIM not already linked to a different modem
    if sim_id:
        all_sims = {s['id'] for s in read_sims(folder)}
        if sim_id not in all_sims:
            return jsonify({'error': 'SIM not found'}), 404
        for m in inv_data['devices']:
            if m.get('sim_id') == sim_id and m['id'] != modem_id:
                return jsonify({'error': 'SIM is already linked to another modem'}), 409

    found = False
    for m in inv_data['devices']:
        if m['id'] == modem_id:
            m['sim_id'] = sim_id
            found = True
            break
    if not found:
        return jsonify({'error': 'Modem not found'}), 404

    write_device_inventory(folder, 'modems', inv_data)
    loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    session_id = flask_session.get('session_id', 0) or 0
    action = f'Linked SIM {sim_id}' if sim_id else 'Unlinked SIM'
    write_device_log(folder, modem_id, loginid, session_id, action, device_type='modems')
    return jsonify({'status': 'success'})


# ── Swap device (reassign patient from faulty to available) ──────────────────

@bp.route('/api/swap-device', methods=['POST'])
def api_swap_device():
    """Swap an assigned (now-faulty) device for an available one. Admin or engineer.

    Body: { device_type, old_device_id, new_device_id }
    - Marks old device faulty/has_issue
    - Closes old assignment, opens new assignment for same patient
    """
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden — device management requires engineer or admin privilege'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data          = request.get_json() or {}
    dtype         = (data.get('device_type') or '').strip().lower()
    old_device_id = (data.get('old_device_id') or '').strip()
    new_device_id = (data.get('new_device_id') or '').strip()
    notes         = (data.get('notes') or '').strip()
    issue_date    = (data.get('issue_date') or '').strip() or None

    if dtype not in ('pluto', 'mars', 'agwatch') or not old_device_id or not new_device_id:
        return jsonify({'error': 'device_type, old_device_id, new_device_id required'}), 400

    # Validate issue_date (when reporting issue during swap)
    if issue_date:
        try:
            issue_dt = datetime.strptime(issue_date, '%Y-%m-%d')
            today = datetime.now()
            if issue_dt > today:
                return jsonify({'error': 'Issue occurred date cannot be in the future'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid issue date format'}), 400

    assignments = read_device_assignments(folder, dtype)
    now_str = datetime.now().strftime('%Y-%m-%dT%H:%M')

    # Find the active assignment for the old device
    active_asgn = None
    for a in assignments:
        if a.get('device_id') == old_device_id and a.get('returned_date') is None:
            active_asgn = a
            break
    if not active_asgn:
        return jsonify({'error': 'No active assignment found for this device'}), 404

    homer_id = active_asgn.get('patient_id') or active_asgn.get('homer_id')
    limb     = active_asgn.get('limb')

    # Verify new device is available (not assigned, not faulty/has_issue, not clinic_only)
    inv = read_device_inventory(folder, dtype)
    new_dev = next((d for d in inv if d['id'] == new_device_id), None)
    if not new_dev:
        return jsonify({'error': 'New device not found'}), 404
    if new_dev.get('faulty') or new_dev.get('has_issue') or new_dev.get('clinic_only'):
        return jsonify({'error': 'Selected device is not available'}), 409
    already_assigned = any(
        a.get('device_id') == new_device_id and a.get('returned_date') is None
        for a in assignments
    )
    if already_assigned:
        return jsonify({'error': 'New device is already assigned'}), 409

    # Mark old device faulty/has_issue
    if dtype in ('pluto', 'mars'):
        mark_device_faulty(folder, dtype, old_device_id)
    else:
        for d in inv:
            if d['id'] == old_device_id:
                d['has_issue'] = True
                break
        write_device_inventory(folder, dtype, {'devices': inv})

    # Close old assignment
    active_asgn['returned_date'] = now_str

    # Open new assignment
    new_asgn = {
        'id':            str(uuid.uuid4()),
        'device_id':     new_device_id,
        'homer_id':      homer_id,
        'assigned_date': now_str,
        'returned_date': None,
    }
    if limb:
        new_asgn['limb'] = limb
    assignments.append(new_asgn)
    write_device_assignments(folder, dtype, assignments)

    loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    session_id = flask_session.get('session_id', 0) or 0
    old_action = f'Issue reported; swapped to {new_device_id}'
    new_action = f'Assigned to {homer_id} (swap from {old_device_id})'
    if notes:
        old_action += f' — {notes}'
        new_action += f' — {notes}'
    write_device_log(folder, old_device_id, loginid, session_id, old_action, device_type=dtype)
    write_device_log(folder, new_device_id, loginid, session_id, new_action, device_type=dtype)
    append_device_event(folder, dtype, old_device_id, event_type='faulty', by=loginid,
                        notes=notes or 'Marked faulty (device swap)', homer_id=homer_id,
                        related_device_id=new_device_id)
    append_device_event(folder, dtype, new_device_id, event_type='assign', by=loginid,
                        notes=f'Assigned (swap from {old_device_id})', homer_id=homer_id,
                        related_device_id=old_device_id)
    return jsonify({'status': 'success', 'homer_id': homer_id})


# ── Assign / unassign modem or laptop ────────────────────────────────────────

@bp.route('/api/assign-device', methods=['POST'])
def api_assign_device():
    """Manually assign a modem or laptop to a patient. Admin only.

    Body: { device_type: 'modem'|'laptop', device_id: '...', homer_id: '...' }
    """
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') != 'admin':
        return jsonify({'error': 'Forbidden — admin only'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data      = request.get_json() or {}
    dtype     = (data.get('device_type') or '').strip().lower()
    device_id = (data.get('device_id') or '').strip()
    homer_id  = (data.get('homer_id') or '').strip()

    if dtype not in ('modems', 'laptops', 'modem', 'laptop') or not device_id or not homer_id:
        return jsonify({'error': 'device_type (modem/laptop), device_id, and homer_id are required'}), 400

    # Normalise to plural form used in filenames
    dtype = 'modems' if dtype in ('modem', 'modems') else 'laptops'

    inv = read_device_inventory(folder, dtype)
    dev = next((d for d in inv if d['id'] == device_id), None)
    if not dev:
        return jsonify({'error': 'Device not found'}), 404
    if dev.get('clinic_only'):
        return jsonify({'error': 'Device is clinic-only and cannot be assigned to a patient'}), 409

    assignments = read_device_assignments(folder, dtype)
    if any(a.get('device_id') == device_id and a.get('returned_date') is None for a in assignments):
        return jsonify({'error': 'Device is already assigned'}), 409

    now_str = datetime.now().strftime('%Y-%m-%dT%H:%M')
    new_asgn = {
        'id':            str(uuid.uuid4()),
        'device_id':     device_id,
        'homer_id':      homer_id,
        'assigned_date': now_str,
        'returned_date': None,
    }
    assignments.append(new_asgn)
    write_device_assignments(folder, dtype, assignments)

    # For modems: transfer sim_id from previously-assigned modem if any
    if dtype == 'modems':
        prev_ids = {a['device_id'] for a in assignments
                    if a.get('homer_id') == homer_id
                    and a.get('returned_date') is not None
                    and a['device_id'] != device_id}
        if prev_ids:
            orphaned_sim = None
            for m in inv:
                if m['id'] in prev_ids and m.get('sim_id'):
                    orphaned_sim = m['sim_id']
                    m['sim_id'] = None
                    break
            if orphaned_sim:
                for m in inv:
                    if m['id'] == device_id:
                        m['sim_id'] = orphaned_sim
                        m['sim_assigned_date'] = now_str
                        break
                write_device_inventory(folder, dtype, {'devices': inv})

    loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    session_id = flask_session.get('session_id', 0) or 0
    write_device_log(folder, device_id, loginid, session_id, f'Assigned to {homer_id}', device_type=dtype)
    return jsonify({'status': 'success'})


@bp.route('/api/unassign-device', methods=['POST'])
def api_unassign_device():
    """Return a modem or laptop from a patient. Admin or engineer.

    Body: { device_type: 'modem'|'laptop', device_id: '...' }
    """
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    # Unassign visible only to engineers and admins
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden — device management requires engineer or admin privilege'}), 403
    if flask_session.get('privilege') != 'admin':
        return jsonify({'error': 'Forbidden — admin only'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data      = request.get_json() or {}
    dtype     = (data.get('device_type') or '').strip().lower()
    device_id = (data.get('device_id') or '').strip()

    if dtype not in ('modems', 'laptops', 'modem', 'laptop') or not device_id:
        return jsonify({'error': 'device_type (modem/laptop) and device_id are required'}), 400

    dtype = 'modems' if dtype in ('modem', 'modems') else 'laptops'

    assignments = read_device_assignments(folder, dtype)
    active = next((a for a in assignments if a.get('device_id') == device_id and a.get('returned_date') is None), None)
    if not active:
        return jsonify({'error': 'No active assignment found for this device'}), 404

    homer_id = active.get('homer_id') or active.get('patient_id', '')
    active['returned_date'] = datetime.now().strftime('%Y-%m-%dT%H:%M')
    write_device_assignments(folder, dtype, assignments)

    loginid    = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    session_id = flask_session.get('session_id', 0) or 0
    write_device_log(folder, device_id, loginid, session_id, f'Returned from {homer_id}', device_type=dtype)
    append_device_event(folder, dtype, device_id, event_type='available', by=loginid,
                        homer_id=homer_id)
    return jsonify({'status': 'success'})


# ── Device events API ─────────────────────────────────────────────────────────

@bp.route('/api/device-events', methods=['GET'])
def api_device_events():
    """Fetch device events. ?type=<type> for all devices of a type, or add &device_id=<id> for one."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    # Device events visible only to engineers and admins
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden — device management requires engineer or admin privilege'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    dtype     = (request.args.get('type') or '').strip().lower()
    device_id = (request.args.get('device_id') or '').strip()

    valid = ('pluto', 'mars', 'agwatch', 'modems', 'laptops', 'sims')
    if dtype not in valid:
        return jsonify({'error': f'type must be one of: {", ".join(valid)}'}), 400

    if device_id:
        data = read_device_events(folder, dtype, device_id)
        return jsonify({'events': data.get('events', [])})

    events = read_all_device_events(folder, dtype)
    return jsonify({'events': events})


@bp.route('/api/log-event', methods=['POST'])
def api_log_device_event():
    """Manually log a device event (retire, discarded, repair, etc.). Admin or engineer."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') not in ('admin', 'engineer'):
        return jsonify({'error': 'Forbidden — device management requires engineer or admin privilege'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    data      = request.get_json() or {}
    dtype     = (data.get('device_type') or '').strip().lower()
    device_id = (data.get('device_id') or '').strip()
    event_type = (data.get('event_type') or '').strip().lower()
    notes     = (data.get('notes') or '').strip()

    valid_types = ('pluto', 'mars', 'agwatch', 'modems', 'laptops', 'sims')
    if dtype not in valid_types or not device_id or not event_type:
        return jsonify({'error': 'device_type, device_id, and event_type are required'}), 400

    import json as _json
    protocol_path = Path(__file__).parent.parent / 'config' / 'device_protocol.json'
    with open(protocol_path, encoding='utf-8') as f:
        protocol = _json.load(f)
    valid_events = set(protocol.get(dtype, {}).get('events', {}).keys())
    if event_type not in valid_events:
        return jsonify({'error': f'event_type {event_type!r} is not valid for {dtype}'}), 400

    privilege = flask_session.get('privilege', 'user')
    allowed_roles = protocol[dtype]['events'][event_type].get('roles', [])
    if privilege not in allowed_roles:
        return jsonify({'error': 'Forbidden — insufficient role for this event type'}), 403

    loginid = flask_session.get('loginid', flask_session.get('login_place', 'unknown'))
    event_id = append_device_event(folder, dtype, device_id, event_type=event_type,
                                   by=loginid, notes=notes)

    # If retiring/discarding, update inventory removal_date
    if event_type in ('retire', 'discarded'):
        if dtype == 'sims':
            sims = read_sims(folder)
            for s in sims:
                if s['id'] == device_id:
                    s['removal_date'] = datetime.now().strftime('%Y-%m-%d')
                    break
            write_sims(folder, sims)
        else:
            inv = read_device_inventory(folder, dtype)
            for d in inv:
                if d['id'] == device_id:
                    d['removal_date'] = datetime.now().strftime('%Y-%m-%d')
                    break
            write_device_inventory(folder, dtype, {'devices': inv})

    session_id = flask_session.get('session_id', 0) or 0
    write_device_log(folder, device_id, loginid, session_id, event_type.capitalize() + (f' — {notes}' if notes else ''), device_type=dtype)
    return jsonify({'status': 'success', 'event_id': event_id})


@bp.route('/api/issues', methods=['GET'])
def api_device_issues():
    """Return open issues for a device type. ?type=<type>"""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    dtype = (request.args.get('type') or '').strip().lower()
    valid = ('pluto', 'mars', 'agwatch', 'modems', 'laptops', 'sims')
    if dtype not in valid:
        return jsonify({'error': f'type must be one of: {", ".join(valid)}'}), 400

    issues = get_open_issues(folder, dtype)
    return jsonify({'issues': issues})


@bp.route('/api/solutions', methods=['GET'])
def api_device_solutions():
    """Return resolved issue pairs for a device type. ?type=<type>"""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    dtype = (request.args.get('type') or '').strip().lower()
    valid = ('pluto', 'mars', 'agwatch', 'modems', 'laptops', 'sims')
    if dtype not in valid:
        return jsonify({'error': f'type must be one of: {", ".join(valid)}'}), 400

    solutions = get_resolved_issues(folder, dtype)
    return jsonify({'solutions': solutions})


# ── Device event attachments ──────────────────────────────────────────────────

@bp.route('/api/upload-event-attachment', methods=['POST'])
def api_upload_event_attachment():
    """Upload a PDF or image attachment for a device event. Admin or engineer."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401
    if flask_session.get('privilege') == 'user':
        return jsonify({'error': 'Forbidden'}), 403

    folder = get_hospital_folder(flask_session['login_place'])
    if not folder:
        return jsonify({'error': 'Cannot determine hospital folder'}), 400

    dtype     = (request.form.get('device_type') or '').strip().lower()
    device_id = (request.form.get('device_id') or '').strip()
    event_id  = (request.form.get('event_id') or '').strip()
    file      = request.files.get('file')

    if not dtype or not device_id or not event_id or not file:
        return jsonify({'error': 'device_type, device_id, event_id, and file are required'}), 400

    allowed_exts = {'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp'}
    orig_ext = Path(file.filename).suffix.lower() if file.filename else ''
    if orig_ext not in allowed_exts:
        return jsonify({'error': f'File type not allowed. Use: {", ".join(allowed_exts)}'}), 400

    attach_dir = Path(Config.DATA_ROOT) / folder / 'devices' / _type_folder(dtype) / 'attachments'
    attach_dir.mkdir(parents=True, exist_ok=True)
    filename = f'{event_id}{orig_ext}'
    file_path = attach_dir / filename

    tmp_path = file_path.with_suffix('.tmp')
    file.save(str(tmp_path))
    os.replace(tmp_path, file_path)

    rel_path = f'{_type_folder(dtype)}/attachments/{filename}'
    updated = update_device_event(folder, dtype, device_id, event_id, {'attachment': rel_path})
    if not updated:
        return jsonify({'error': 'Event not found — file saved but event not linked'}), 404

    return jsonify({'status': 'success', 'attachment': rel_path})


@bp.route('/api/download-event-attachment', methods=['GET'])
def api_download_event_attachment():
    """Download an attachment for a device event."""
    if not flask_session.get('login_place'):
        return jsonify({'error': 'Not authenticated'}), 401

    folder    = get_hospital_folder(flask_session['login_place'])
    dtype     = (request.args.get('type') or '').strip().lower()
    device_id = (request.args.get('device_id') or '').strip()
    event_id  = (request.args.get('event_id') or '').strip()

    if not folder or not dtype or not device_id or not event_id:
        return jsonify({'error': 'type, device_id, and event_id are required'}), 400

    events_data = read_device_events(folder, dtype, device_id)
    event = next((e for e in events_data.get('events', []) if e['id'] == event_id), None)
    if not event or not event.get('attachment'):
        return jsonify({'error': 'Attachment not found'}), 404

    file_path = Path(Config.DATA_ROOT) / folder / 'devices' / event['attachment']
    if not file_path.exists():
        return jsonify({'error': 'File not found on disk'}), 404

    from flask import send_file
    return send_file(str(file_path), as_attachment=True, download_name=file_path.name)