# htDash — Device Data Schemas

---

## Folder Structure

All device data lives under `data/<hospital>/devices/`. Each device type has its own subfolder containing all related files.

```
data/<hospital>/devices/
├── pluto/
│   ├── inventory.json
│   ├── assignments.json
│   ├── faultReport.json
│   ├── events/
│   │   └── <device_id>.json
│   ├── logs/
│   │   └── <device_id>.log
│   └── attachments/
│       └── <event_id>.<ext>
├── mars/          (same layout as pluto)
├── agwatch/       (same layout as pluto)
├── modems/
│   ├── inventory.json
│   ├── assignments.json
│   ├── events/
│   │   └── <device_id>.json
│   ├── logs/
│   │   └── <device_id>.log
│   └── attachments/
│       └── <event_id>.<ext>
├── laptops/       (same layout as modems)
└── sims/
    ├── inventory.json
    └── events/
        └── <device_id>.json
```

**Type → folder name mapping** (used in all path construction via `_type_folder()` in `utils/data_access.py`):

| Input type string | Folder name |
|-------------------|-------------|
| `pluto` | `pluto` |
| `mars` | `mars` |
| `agwatch` | `agwatch` |
| `modem` / `modems` | `modems` |
| `laptop` / `laptops` | `laptops` |
| `sims` | `sims` |

**Migration:** `scripts/migrate_device_data.py` moves all existing files from the old flat layout to this structure. Safe to re-run (skips files that no longer exist at old paths).

---

## Device States

State is always **derived** — never stored directly. Derivation order (highest priority first):

| State | Badge | Condition |
|-------|-------|-----------|
| **Issue** | red | `faulty=true` (pluto/mars) or `has_issue=true` (agwatch) |
| **Assigned** | blue | Active assignment record exists (`returned_date=null`) |
| **Clinic** | gray | `clinic_only=true`, no active assignment |
| **Available** | green | None of the above |

---

## Inventory Files

### `pluto/inventory.json` and `mars/inventory.json`

```json
{
  "devices": [
    {
      "id": "PLT-001",
      "serial": "PLT2024001",
      "clinic_only": false,
      "faulty": false,
      "inclusion_date": "2024-01-15",
      "removal_date": null
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique device identifier (e.g. `PLT-001`, `MRS-001`) |
| `serial` | string | Physical serial number |
| `clinic_only` | boolean | `true` = device reserved for in-clinic sessions; not assignable to patients |
| `faulty` | boolean | `true` = device has a reported fault; overrides all other states |
| `inclusion_date` | `YYYY-MM-DD` | Date added to inventory |
| `removal_date` | `YYYY-MM-DD` or `null` | Date permanently removed; `null` = still in service |

**Notes:**
- Only one pluto and one mars device can be `clinic_only=true` at a time (enforced server-side).
- A device with `removal_date` set is permanently retired and excluded from all lists.

---

### `agwatch/inventory.json`

```json
{
  "devices": [
    {
      "id": "AGW-001",
      "serial": "AGW2024001",
      "limb_default": "Right",
      "has_issue": false,
      "inclusion_date": "2024-01-15",
      "removal_date": null,
      "lost_date": null
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique device identifier (e.g. `AGW-001`) |
| `serial` | string | Physical serial number |
| `limb_default` | `"Right"` or `"Left"` | Which arm this watch is designated for; determines display column |
| `has_issue` | boolean | `true` = watch has a reported fault; overrides all other states |
| `inclusion_date` | `YYYY-MM-DD` | Date added to inventory |
| `removal_date` | `YYYY-MM-DD` or `null` | Date permanently removed; `null` = still in service |
| `lost_date` | `YYYY-MM-DD` or `null` | Set when watch is confirmed lost; permanently retired |

**Notes:**
- A watch with `lost_date` set is excluded from all lists and cannot be re-assigned.
- `limb_default` determines which column (Left / Right) the watch appears in on the devices page.

---

### `modems/inventory.json`

```json
{
  "devices": [
    {
      "id": "MDM-001",
      "serial": "MDM2024001",
      "sim_id": "8920949d-84a4-485f-aee0-9db217db1b00",
      "inclusion_date": "2024-01-15",
      "removal_date": null
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique device identifier (e.g. `MDM-001`) |
| `serial` | string | Physical serial number |
| `sim_id` | string or `null` | Phone number of the linked SIM card in `sims/inventory.json`; `null` = no SIM linked |
| `has_issue` | boolean | `true` = device has a reported fault; overrides all other states |
| `inclusion_date` | `YYYY-MM-DD` | Date added to inventory |
| `removal_date` | `YYYY-MM-DD` or `null` | Date permanently removed |

**Notes:**
- A SIM can only be linked to one modem at a time. Availability is derived by checking which SIMs are referenced by any modem's `sim_id` — SIMs with a modem reference are excluded from the device setup dropdown.
- SIM expiry is shown for all SIMs regardless of modem assignment status.

---

### `laptops/inventory.json`

```json
{
  "devices": [
    {
      "id": "LPT-001",
      "serial": "LPT2024001",
      "inclusion_date": "2024-01-15",
      "removal_date": null
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique device identifier (e.g. `LPT-001`) |
| `serial` | string | Physical serial number |
| `has_issue` | boolean | `true` = device has a reported fault; overrides all other states |
| `inclusion_date` | `YYYY-MM-DD` | Date added to inventory |
| `removal_date` | `YYYY-MM-DD` or `null` | Date permanently removed |

---

## Assignment Files

One file per device type, stored at `<type>/assignments.json`. All share the same top-level key `"assignments"`.

### `pluto/assignments.json` and `mars/assignments.json`

```json
{
  "assignments": [
    {
      "id": "uuid",
      "device_id": "PLT-001",
      "homer_id": "HOCMCV002",
      "assigned_date": "2026-04-08T09:00",
      "returned_date": null,
      "assigned_by": "RP-HS-ADMIN",
      "notes": ""
    }
  ]
}
```

### `agwatch/assignments.json`

```json
{
  "assignments": [
    {
      "id": "uuid",
      "device_id": "AGW-001",
      "homer_id": "HOCMCV002",
      "limb": "Right",
      "assigned_date": "2026-04-08T09:00",
      "returned_date": null,
      "assigned_by": "RP-HS-ADMIN",
      "notes": ""
    }
  ]
}
```

### `modems/assignments.json` and `laptops/assignments.json`

```json
{
  "assignments": [
    {
      "id": "uuid",
      "device_id": "MDM-001",
      "homer_id": "HOCMCV002",
      "assigned_date": "2026-04-08T09:00",
      "returned_date": null,
      "assigned_by": "RP-HS-ADMIN"
    }
  ]
}
```

### Assignment record fields

| Field | Type | Present on | Description |
|-------|------|------------|-------------|
| `id` | UUID string | All | Unique record ID (absent on older records written before UUID was added) |
| `device_id` | string | All | References `id` in the corresponding inventory file |
| `homer_id` | string | All | Patient's Homer ID (`patient_id` in older records — both are accepted on read) |
| `limb` | `"Right"` or `"Left"` | agwatch only | Which arm the watch was assigned to |
| `assigned_date` | `YYYY-MM-DDTHH:MM` | All | When the assignment was created |
| `returned_date` | `YYYY-MM-DDTHH:MM` or `null` | All | When the device was returned; `null` = assignment is active |
| `assigned_by` | string | All | Login ID of the admin who created the assignment |
| `notes` | string | pluto/mars | Optional notes entered at assignment time |

**Active assignment:** `returned_date = null`. A device with any active assignment record is in the Assigned state.

**28-day auto-reset (all device types):** On every `GET /devices/api/inventory` call, active assignments across all device types where the patient's `activationDate` is ≥ 28 days ago have `returned_date` set automatically. Assignment date is not used — the reset counts from the patient's activation. Devices with `faulty=true` (pluto/mars) or `has_issue=true` (agwatch) are skipped.

---

## `sims/inventory.json`

```json
{
  "sims": [
    {
      "id": "9090909090",
      "phoneNumber": "9090909090",
      "network": "jio",
      "rechargeDate": "2026-04-07",
      "expiryDate": "2026-05-07",
      "rechargeAmount": null,
      "dataPlan": "28",
      "reminderDays": 5,
      "status": "active",
      "notes": "",
      "createdAt": "2026-04-08T12:02:29"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (phone number) | SIM identifier — **set to the phone number** at creation. Referenced by modem inventory via `sim_id`. Duplicate phone numbers rejected on add. |
| `phoneNumber` | string | Same as `id`; kept for display compatibility |
| `network` | string | Carrier name (e.g. `"jio"`, `"airtel"`) |
| `rechargeDate` | `YYYY-MM-DD` or `null` | Date of most recent recharge |
| `expiryDate` | `YYYY-MM-DD` or `null` | Date the current recharge expires |
| `rechargeAmount` | number or `null` | Amount paid at last recharge |
| `dataPlan` | string or `null` | Plan duration in days (e.g. `"28"`) |
| `reminderDays` | integer | Days before expiry to start showing the amber warning banner |
| `status` | `"active"` or `"inactive"` | Whether this SIM is in service |
| `notes` | string | Free-text notes |
| `createdAt` | ISO 8601 datetime | When this SIM record was created |

**SIM expiry badge logic** (shown for all SIMs regardless of modem assignment status):

| Condition | Badge |
|-----------|-------|
| `expiryDate` not set | — |
| Expired | red "Expired" + Recharge button |
| ≤ 3 days remaining | red "Expires in Xd" |
| ≤ 5 days remaining | amber "Expires in Xd" |
| Active | green with expiry date |

An amber banner appears at the top of the Devices page if any SIM expires within `reminderDays` days.

When `isExpired=true`, a **Recharge** button appears in the SIM row alongside the badge. Clicking it opens the Recharge SIM modal (fields: Recharge Date, Data Plan, Expiry Date auto-computed from plan). Calls `POST /devices/api/recharge-sim` (body: `{sim_id, rechargeDate, dataPlan, expiryDate}`).

---

## Device Log Files

One log file per device, stored at `<device_type>/logs/<device_id>.log`.

`<device_type>` folder is one of: `pluto`, `mars`, `agwatch`, `modems`, `laptops`.

```
:Location: Ranipet
:DeviceId: AGR-88
[2026-04-09T08:49:36]   RP-HS-ADMIN     #3    Added to inventory
[2026-04-09T09:15:00]   RP-HS-ADMIN     #3    Assigned to HOCMCV002
[2026-04-09T10:30:00]   RP-HS-ADMIN     #3    Issue reported; swapped to AGR-99 — Screen cracked
[2026-04-09T11:00:00]   RP-HS-ADMIN     #3    Issue resolved
```

Example path: `agwatch/logs/AGR-88.log`

**Header lines** (written once at creation):

| Line | Content |
|------|---------|
| `:Location:` | Hospital display name |
| `:DeviceId:` | Device ID matching the filename |

**Log entry columns** (tab-separated):

| Column | Content |
|--------|---------|
| Timestamp | `[YYYY-MM-DDTHH:MM:SS]` |
| Login ID | The user who performed the action |
| Session | `#<session_id>` |
| Action | Free-text description |

**Standard action strings:**

| Action | Trigger |
|--------|---------|
| `Added to inventory` | Device added via Add modal |
| `Assigned to <homer_id>` | Device assigned to patient (modem/laptop assign, or device swap — new device) |
| `Returned from <homer_id>` | Device unassigned from patient |
| `Issue reported` | `toggle-issue` called with `has_issue=true`; optional `— <notes>` appended |
| `Issue resolved` | `toggle-issue` called with `has_issue=false`; optional `— <notes>` appended |
| `Issue reported; swapped to <new_id>` | Old device log on swap; optional `— <notes>` appended |
| `Assigned to <homer_id> (swap from <old_id>)` | New device log on swap; optional `— <notes>` appended |
| `Set to clinic-only` | Admin toggled device to Clinic state |
| `Cleared from clinic-only` | Admin cleared device from Clinic state |

---

## Field Naming: `homer_id` vs `patient_id`

Assignment records written by the current codebase use `homer_id`. Older records (written before this convention was standardised) use `patient_id`. Both field names are accepted on read throughout `routes/devices.py`:

```python
homer_id = a.get('patient_id') or a.get('homer_id')
```

New records written by the API always use `homer_id`.

---

---

## Device Event Files

One JSON file per device, stored at `<device_type>/events/<device_id>.json`. Mirrors `<device_type>/logs/<device_id>.log` structure. Written with atomic `.tmp → os.replace()` pattern via `utils/device_events.py`.

```json
{
  "events": [
    {
      "id": "<uuid>",
      "device_id": "P-1",
      "event_type": "faulty",
      "date": "YYYY-MM-DDTHH:MM:SS",
      "by": "<login_id>",
      "notes": "Motor not responding",
      "homer_id": "HOCMCV002",
      "related_device_id": "P-2",
      "patient_event_id": "<uuid>"
    }
  ]
}
```

| Field | Type | Present on | Description |
|-------|------|------------|-------------|
| `id` | UUID string | All | Unique event ID |
| `device_id` | string | All | Device this event belongs to |
| `event_type` | string | All | See valid types per device below |
| `date` | ISO 8601 datetime | All | When the event occurred |
| `by` | string | All | Login ID of user who logged the event |
| `notes` | string or `null` | All | Optional free-text notes |
| `homer_id` | string or `null` | `assign`, `available` | Patient involved |
| `related_device_id` | string or `null` | `swap` | Device swapped to/from |
| `patient_event_id` | UUID or `null` | `faulty` (Pluto/Mars) | Links to `robot_issue_visit` UUID in patient's `protocol_events.json` |

**Valid event types per device type** (defined in `config/device_protocol.json`):

| Device | Event types |
|--------|-------------|
| Pluto / Mars | `assign`, `available`, `faulty`, `swap`, `repair`, `retire`, `discarded` |
| Agwatch | `assign`, `available`, `faulty`, `repair`, `lost`, `retire`, `discarded` |
| Modem | `assign`, `available`, `faulty`, `repair`, `retire`, `discarded` |
| Laptop | `assign`, `available`, `faulty`, `repair`, `retire`, `discarded` |
| SIM | `recharge`, `expired`, `retire`, `discarded` |

**When events are auto-created:**
- `assign` — `exp_device_install` (all device types); `swap-device` new device; robot issue visit / resolve robot issue visit new device; other device issue visit replaced device
- `available` — 28-day auto-reset fires, or manual unassign
- `faulty` — `toggle-issue` marks faulty; `swap-device` old device; robot issue visit fault-driven swap old device
- `repair` — `toggle-issue` resolves a faulty device; robot issue visit / resolve visit repaired_on_site
- `recharge` — `recharge-sim`

**Issues container logic:** a device is "open issue" when its last state-event is `faulty` and no subsequent `repair`, `available`, `retire`, or `discarded` event exists. "Resolved" = a `faulty` event that was closed by one of those events.

---

## API Endpoints

| Route | Method | Auth | Purpose |
|-------|--------|------|---------|
| `/devices/page` | GET | Required | Render the devices HTML page |
| `/devices/api/inventory` | GET | Required | Full inventory + assignments + SIMs; triggers 28-day auto-reset |
| `/devices/api/add` | POST | Admin | Add a device or SIM to inventory |
| `/devices/api/toggle-clinic` | POST | Admin | Toggle `clinic_only` on a pluto or mars device (one-per-type rule) |
| `/devices/api/toggle-issue` | POST | Admin/Engineer | Mark or resolve a device issue; optional `notes`; auto-creates device event |
| `/devices/api/swap-device` | POST | Admin/Engineer | Replace a faulty assigned device; patient follows; auto-creates device events |
| `/devices/api/link-sim` | POST | Admin | Link or unlink a SIM to a modem |
| `/devices/api/recharge-sim` | POST | Admin | Record a SIM recharge; auto-creates `recharge` device event |
| `/devices/api/device-events` | GET | Required | Fetch device events (`?type=<type>` or `?type=<type>&device_id=<id>`) |
| `/devices/api/log-event` | POST | Admin/Engineer | Manually log a device event (retire, discarded, repair, etc.) |
| `/devices/api/issues` | GET | Required | Open issues per device type (`?type=<type>`) |
| `/devices/api/solutions` | GET | Required | Resolved issue pairs per device type (`?type=<type>`) |
