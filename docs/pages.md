# htDash — Pages & Actions

---

## URL Structure

| Page           | URL                    | Blueprint                                                                                                      |
| -------------- | ---------------------- | -------------------------------------------------------------------------------------------------------------- |
| Login          | `/login`               | `routes/auth.py`                                                                                               |
| Dashboard      | `/`                    | `main.py`                                                                                                      |
| Patient list   | `/patients`            | `routes/user_management.py`                                                                                    |
| Patient detail | `/patients/<homer_id>` | `routes/user_management.py`                                                                                    |
| Devices        | `/devices/`            | `routes/devices.py`                                                                                            |
| SIM cards      | `/sim_cards/`          | `routes/sim_cards.py` (legacy — SIM management is integrated into the Devices page; `/sim_cards/` is not used) |

---

## Template Architecture

`base.html` contains: sidebar (real `<a href>` links), header bar, flash messages, and block definitions (`title`, `content`, `scripts`). All page templates extend it.

---

## User Permissions

| User type   | Description                                          |
| ----------- | ---------------------------------------------------- |
| `admin`     | Global admin — sees all sites, all actions           |
| `therapist` | Site user — sees own site patients, clinical actions |
| `engineer`  | Site user — device and technical actions             |

Actions list which user types are permitted. UI controls for disallowed actions are visible but disabled.

---

## Pages

### `GET /login`

Login form.

**Actions:** [Successful login](#successful-login), [Failed login](#failed-login)

---

### `GET /`

Main dashboard. Stat bubbles in two rows (6 per row on large screens), in order:

1. Total enrolled
2. Experimental group
3. Control group
4. Unassigned
5. Inactive
6. Active
7. Paused
8. Training Complete
9. A1 Complete
10. Broken Protocol
11. Discontinued
12. All Complete

Numbers are derived from `homer_id.json` files across all visible patients. Site users see their site only; admin sees all. `pre_discontinued` status is returned by the stats API but intentionally not shown as a bubble.

Below the stats: **Overdue** and **Upcoming** event panels showing protocol events across all non-terminal patients. Fetched from `GET /api/dashboard/events`.

- **Overdue** — two sub-groups shown together: (1) active-window events (`start` ≤ today ≤ `end`) sorted ascending by end date, then (2) past-due events (`end` < today) sorted ascending by end date. Active-window and past-due events are clickable if `depends_on` is satisfied.
- **Upcoming** — incomplete events whose `scheduled_date[0]` (start) > today, within 7 days, sorted ascending by start date. Within the same date, events that appear in another event's `depends_on` are sorted before their dependents. **Upcoming events are never clickable** — rendered as a plain `<div>` with label "Available from \<date\>" in place of the urgency label. This applies regardless of `depends_on` state.
- The two lists are mutually exclusive.
- Each event row displays the **Homer ID** prominently alongside the event name (e.g. `HOCMCV003 · ADL Prescription Day 01`), since rows span multiple patients.

**Actions:** None

---

### `GET /patients`

Patient list for the user's visible site(s).

#### Page elements

- Search bar (filter by Homer ID)
- **Add Patient** button (admin only)
- Filter tabs (in order): All, Unassigned, Inactive, Active, Paused, Training Complete, A1 Complete, Pre-Discontinued, Broken Protocol, Discontinued, All Complete — each with count. "All" selected by default.
- Patient rows sorted by `enrollDate`. Row colour indicates group. Status badge colour-coded.
- Each row: Homer ID, Hospital ID, Group, Training Side, Status
- Clicking a row navigates to `/patients/<homer_id>`

#### Patient state transitions

| Current state      | Action                                                                                                | Field set                                                       | Next state         |
| ------------------ | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------ |
| unassigned         | Assign group + Record A0                                                                              | `group`, `a0CompletionDate`                                     | inactive           |
| unassigned         | Pre-Discontinue                                                                                       | `discontinuationDate`                                           | pre_discontinued   |
| inactive           | Activate                                                                                              | `activationDate`                                                | active             |
| inactive           | Discontinue                                                                                           | `discontinuationDate`                                           | discontinued       |
| inactive           | _(today > a0 + 5 days)_                                                                               | _(none — derived)_                                              | broken_protocol    |
| broken_protocol    | Discontinue                                                                                           | `discontinuationDate`                                           | discontinued       |
| active             | Complete `training_completion_d29` event                                                              | `trainingCompletionDate`                                        | training_completed |
| active             | Discontinue                                                                                           | `discontinuationDate`                                           | discontinued       |
| active             | _(today > activationDate + 28 days)_                                                                  | _(none — derived; `post_training` if no `trainingCompletionDate`)_ | post_training   |
| post_training      | Complete `training_completion_d29` event                                                              | `trainingCompletionDate`                                        | training_completed |
| post_training      | Discontinue                                                                                           | `discontinuationDate`                                           | discontinued       |
| active             | Robot issue visit — device swapped with no replacement available                                      | `trainingPausedDate` set                                        | paused             |
| active             | Adverse event — `training_blocked` checked                                                            | `trainingPausedDate` set                                        | paused             |
| paused             | All pause causes resolved (`can_resume_from` set on all; no `resolve_robot_issue_visit` stubs remain) | `trainingPausedDate` cleared; `cumulativePauseDays` incremented | active             |
| paused             | All pause causes resolved (`cumulativePauseDays` > 10)                                                | `cumulativePauseDays` incremented                               | broken_protocol    |
| paused             | Complete `training_completion_d29` event                                                              | `trainingCompletionDate`                                        | training_completed |
| paused             | Discontinue                                                                                           | `discontinuationDate`                                           | discontinued       |
| training_completed | Record A1                                                                                             | `a1CompletionDate`                                              | a1_completed       |
| a1_completed       | Record A2                                                                                             | `a2CompletionDate`                                              | all_completed      |

**Actions:** [Add Patient](#add-patient), [Assign Group](#assign-group), [Pre-Discontinue](#pre-discontinue)

---

### `GET /patients/<homer_id>`

Patient detail. Shown for patients `inactive` and beyond (including `broken_protocol`, `paused`). Not shown for `pre_discontinued` or `discontinued`.

#### Page elements

- Back button → `/patients`
- Page title: Homer ID + status badge

- **Tab bar** (JS-driven switching):

  | Tab            | Shown for         |
  | -------------- | ----------------- |
  | Overview       | All               |
  | Devices        | Experimental only |
  | VCG            | Control only      |
  | ADL            | All               |
  | Call Logs      | All               |
  | Adverse Events | All               |
  | Watch Records  | All               |
  | Robot Issues   | Experimental only |
  | Timeline       | All               |
  | Notes          | All               |

  (The Notes tab is the last tab and is shown to all roles, but each role sees only its own notes — see the Notes tab description below.)

- **Overview tab** (default):
  0a. **Training period expiry banner** — shown when `today > activationDate + 28 days` AND `trainingCompletionDate` is null. Amber informational strip above the events panels: "Training period has ended (Day 28 passed). Training completion (D29) can be filed when ready." Disappears once D29 is filed. See `docs/ae_ri_logic.md` Section 15.
  0b. **Pause alert banner** — shown only when `status === 'paused'`. Full-width amber strip (red when ≥ 8 days total) injected above the Patient Info / Key Dates grid. Contains:
  - "Training Paused" heading with pause icon
  - "Paused since: \<date\>" and "Days paused so far: X / 10"
  - A **segmented progress bar** over 10 days: one colour slice per closed past epoch (from `pauseHistory` closed entries) plus a distinct colour for the current open epoch. Each slice width = its `days` / 10. Turns red at ≥ 8 days total.
  - Reason pills: "Robot issue pending" (if any `resolve_robot_issue_visit` stubs exist in `incomplete`) and/or "Adverse event pending" (if any `adverse_event_followup` stubs exist in `incomplete`)
  - The "days paused so far" is `cumulativePauseDays` (closed epochs) + `(today − trainingPausedDate).days` (current open epoch). Banner is hidden for all other statuses.
    0b. **Pause history card** — rendered as a `col-span-5` card inside the Patient Info / Key Dates grid, appearing as a second row spanning the full width. Hidden when `pauseHistory` is empty; shown as soon as any pause epoch exists. Shows a compact table of all pause epochs from `pauseHistory`:
  - Columns: Epoch # | Start date | End date | Days | Reasons
  - The current open epoch shows "Ongoing" for End and "—" for Days.
  1. **Patient Info card** — Homer ID, Hospital ID, Group, Training Side, Status, Enrolment Date, Pluto ID _(experimental group)_, Mars ID _(experimental group)_, AG Watch Right ID _(both groups)_, AG Watch Left ID _(both groups)_,
  2. **Key Dates card** — A0, Activation, Training Completion, A1, A2, Discontinuation dates. A separate **Days card** sits alongside showing days elapsed since activation (Day 1 = activation date). Displays `—` until activated. Hidden for terminal states (discontinued, all_completed, pre_discontinued). Calculated client-side in `patient_detail.js`.
  3. **Events panels** — Three columns: Completed | Overdue | Upcoming. Fetched from `GET /api/patients/<homer_id>/events`.
     - **Completed** — compact vertical timeline, most recent first. Green circle markers on a vertical line. Shows event name + completion date. Read-only.
     - **Overdue column** — two sub-groups shown together: (1) active-window events (`start` ≤ today ≤ `end`), label `Due now · N days left`, sorted ascending by end date; then (2) past-due events (`end` < today), label `Nd overdue`, sorted ascending by end date. Active-window events appear above past-due events.
     - **Upcoming** — incomplete events whose `scheduled_date[0]` (start) > today, sorted ascending by start date. No cap (all future events shown). Within the same date, events that appear in another event's `depends_on` are sorted before their dependents. **Upcoming events are never clickable** — rendered as a plain `<div>` with label "Available from \<date\>" in place of the urgency label. This applies regardless of `depends_on` state.
     - The three states are mutually exclusive. Categorisation always uses `start` for upcoming and `end` for overdue/broken-protocol.
     - **Blocked events** (unmet `depends_on`): rendered as a non-clickable `<div>` with an amber badge on the right reading "Needs: \<event name\>". A muted lock icon appears next to the event name. Applies only to overdue events — upcoming events use the "Available from" label regardless.
     - **On-hold events** (training paused + event is not an AE/RI follow-up + `scheduled_date[0]` ≤ today): rendered in the upcoming section even though their window has opened or passed. Gray/muted styling, non-clickable `<div>`, slate "On hold" badge on the right. Events whose window has not yet opened (`scheduled_date[0]` > today) continue to show normally with "Available from" label. The server sets `on_hold: true` on the event record; both event APIs apply this rule consistently.

- **Timeline tab** — full-width **master–detail** layout, most recent first. Combines completed protocol events with two synthetic patient milestones injected client-side:
  - **Patient Enrolled** — from `enrollDate` in `<homer_id>.json`
  - **A0 Assessment** — from `a0CompletionDate` in `<homer_id>.json`
  - Synthetic events use **blue circles**; protocol events use **green circles**.
  - All events sorted descending by `filed_at` / `completion_date`.

  **Two-pane layout** — the original rich timeline on the left, a notes panel on the right, as a **centered group** (margins on wide screens — not full width); each pane scrolls independently:
  - _Left (timeline)_: the original 3-column rows are kept intact (`1fr 20px 1fr`) — event name / scheduled date / **Day N** / transition badges on the left, circle + connecting line in the centre, and completion datetime / filed-at / extra event-specific fields / **attachment download link** on the right. A **note-count badge** (sticky-note icon + N) appears with the badges when the event has retrospective notes; the count is **role-filtered** (therapist/engineer see their own bucket's count, admin sees all) and is supplied by the events API as `event_notes_count` (the API still strips note content). Real (non-synthetic) rows are clickable: **hover highlights**, **click selects** (persistent ring) and loads that event's notes on the right. Synthetic rows (Enrolled, A0) are not selectable.
  - _Right (notes panel)_: a compact header (event name + completion date + badges) followed by the **Retrospective Event Notes** view (role-filtered list + Add Note — see below). Event details are not duplicated here; they remain inline in the row. When nothing is selected, the panel shows a placeholder.

  **Transition badges** — a small pill shown on the timeline row and in the notes-panel header whenever that event caused a patient state transition. Derived client-side by `_deriveTransitions(patient, events)` — never stored. At most one badge per event.

  | Badge            | Colour | Condition                                                         |
  | ---------------- | ------ | ----------------------------------------------------------------- |
  | Training paused  | amber  | Event `id` appears in any `pauseHistory[*].reasons[*].event_id`   |
  | Training resumed | green  | Event `id` matches a closed `pauseHistory[*].end_event_id`        |
  | Protocol broken  | red    | Event `completion_date` (date only) matches `brokenProtocolDate`  |
  | Discontinued     | slate  | Event `completion_date` (date only) matches `discontinuationDate` |

  `_deriveTransitions(patient, events)` returns a `Map<event_id, badge>` built once when the timeline renders. Synthetic events (Enrolled, A0) never carry badges.

  Data from the `complete` array in `GET /api/patients/<homer_id>/events` (all fields are returned, including `id`; only `event_notes` is stripped — see retrospective event notes below). This includes both protocol events from `protocol_events.json`'s `complete[]` array and completed free events. The `free.discontinuation` singleton is also included (as `protocol_event_id: "discontinuation"`, `event_name: "Patient Discontinued"`) so the discontinuation entry appears in the timeline.

  **Retrospective event notes** — when a real (non-synthetic) event is selected, its detail panel lazy-loads that event's role-filtered notes from `GET /api/patients/<homer_id>/events/<event_id>/notes` and shows an **Add Note** button. This is the **only** place event notes can be added or viewed. See [Retrospective Event Notes](#retrospective-event-notes-event_notes) for the full spec. Synthetic rows (Patient Enrolled, A0) have no notes section.

- **ADL tab** — shows the ADL prescription history for the patient. Each prescription is a card with a coloured header (day 01 = blue-400, day 15 = blue-600). Each exercise row shows: numbered circle badge · exercise name · blocks × reps (right-aligned). If the corresponding AG watch timing event is complete, the recorded `HH:MM:SS → HH:MM:SS` window appears below blocks × reps in the same row. Data is fetched in parallel via:
  - `GET /api/patients/<homer_id>/prescription/adl_prescription_d01` (or `d15`)
  - `GET /api/patients/<homer_id>/agwatch-timing/adl_agwatch_timing_d03` (or `d15`)
  - If `prescription_printout_d01` (or `d15`) is complete, a **Download PDF** link appears in the card header.

- **VCG tab** _(control patients only)_ — same layout as ADL tab, using teal headers (day 01 = teal-400, day 15 = teal-600). Data fetched via:
  - `GET /api/patients/<homer_id>/prescription/vcg_prescription_d01` (or `d15`)
  - `GET /api/patients/<homer_id>/agwatch-timing/vcg_agwatch_timing_d03` (or `d15`)

- **Adverse Events tab** — `admin` and `therapist` only (engineers cannot see this tab). Shows one collapsible card per adverse event, assembled client-side from the events API.
  - **Alias:** each AE is assigned a stable alias `AE01`, `AE02`, … in chronological order (oldest = AE01). The alias never changes even as new AEs are filed.
  - **Display order:** newest first (most recently reported at the top).
  - **Card header** (always visible, click to expand/collapse):
    - Left: alias (`AE01`) + status badge
    - Right: chevron (rotates on open)
    - Status badge variants: red pill "Ongoing — Training blocked" (`training_blocked: true`, unresolved); amber pill "Ongoing" (unresolved, no block); green pill "Resolved"
  - **Meta row** (always visible, below header): `Reported: <date> | Resolved: <date> | Duration: N days | Day X`
    - Resolved date and Duration shown only when resolved. When ongoing, Duration shows "N days ongoing" (elapsed since report date). Day X from activation.
  - **Expanded body:**
    - Description and action taken
    - Triggered-by event (type + date)
    - Attachment download link (if present)
    - **Follow-up history** section: chronological list of all `adverse_event_followup`, `adverse_event_followup_visit`, and `adverse_event_clinical_visit` entries whose `ae_discussions` contains this AE's ID. Each row shows: event type, date, event notes, per-AE discussion notes, resolved/unresolved status, `can_resume_from` (if resolved and set), attachment link (if present).
  - **Color theme per card:** red border/header (training blocked + unresolved), amber border/header (unresolved, no block), green border/header (resolved).
  - Assembly: data fetched from `GET /api/patients/<homer_id>/events` (which returns all `free` arrays); assembled per-AE by filtering on `adverse_event_id` across follow-up event types — no separate endpoint required.

- **Notes tab** — free-text clinical notes per patient, separate from protocol events. Visible to all roles; each role sees only its own notes (admin sees everyone's). Data from `GET /api/patients/<homer_id>/notes`. See [Create Note](#create-note-note) for the full behavioural spec.
  - **Create Note** button (top of tab) opens a `max-w-3xl` modal: title input (required), a **Quill** rich-text editor, and the standard attachment widget (one optional PDF + required caption when attached).
  - **Display:** collapsible cards in the same style as the Adverse Events tab, **newest first by `created_at`**.
    - **Card header** (always visible, click to expand/collapse): alias (`Notes-T-0001`) + title on the left; created date + chevron on the right.
    - **Expanded body:** the rich-text content (HTML, DOMPurify-sanitised on render); `Created: <created_at>` and `Committed: <committed_at>`; author (shown in the admin view, which spans all roles); attachment download link if present.
  - **Immutable:** no edit or delete. A correction is a new note that references the earlier one by alias (e.g. "supersedes Notes-T-0003").
  - **Stored** in `notes.json` (role-keyed buckets); see `docs/data_schemas.md`.

- **Stub tabs** — Devices, Call Logs, Watch Records, Robot Issues show "Coming soon"

**Actions:** [Device Setup](#device-setup-exp_device_install), [Activate](#activate), [ADL Prescription](#adl-prescription-adl_prescription_d01), [VCG Prescription](#vcg-prescription-vcg_prescription_d01), [Prescription Printout](#prescription-printout-prescription_printout_d01), [ADL Prescription Revision](#adl-prescription-revision-adl_prescription_d15), [VCG Prescription Revision](#vcg-prescription-revision-vcg_prescription_d15), [Home Visit](#home-visit), [Follow-up Call](#follow-up-call-followup_call_d07-followup_call_d21), [Patient Call](#patient-call), [Watch Record](#watch-record-watch_record), [Training Completion](#training-completion-visit-training_completion_d29), [File Adverse Event](#file-adverse-event-adverse_event), [Adverse Event Follow-up Call](#adverse-event-follow-up-call-adverse_event_followup), [Adverse Event Follow-up Visit](#adverse-event-follow-up-visit-adverse_event_followup_visit), [Adverse Event Clinical Visit](#adverse-event-clinical-visit-adverse_event_clinical_visit), [Record A1](#record-a1-assessment-a1_assessment), [Record A2](#record-a2-assessment-a2_assessment), [Assessment Scheduling Call](#assessment-scheduling-call-schedule_a1_call-schedule_a2_call), [Create Note](#create-note-note), [Discontinue](#discontinue)

---

### `GET /devices`

Device Management page. Shows all devices for the current site grouped by type. All users can view; admins can add devices, toggle clinic status, and link SIMs; engineers/admins can report and resolve issues.

#### Page elements

- **Location badge** — current site name in the page header.
- **SIM expiry banner** — amber alert strip shown when any SIM has `daysUntilExpiry ≤ 5`.
- Six device sections rendered as cards:

| Section           | Device type | Notes                                          |
| ----------------- | ----------- | ---------------------------------------------- |
| Pluto Devices     | `pluto`     | Robot devices; experimental patients only      |
| Mars Devices      | `mars`      | Robot devices; experimental patients only      |
| Actigraph Watches | `agwatch`   | Split into Right Watch / Left Watch sub-tables |
| Modems            | `modems`    | Shows linked SIM info                          |
| SIM Cards         | `sims`      | Shows expiry badge with countdown              |
| Laptops           | `laptops`   | Assignable to patients                         |

Each device row (Pluto/Mars/Agwatch/Laptops) shows:

- Device ID, Serial, Status badge, Assigned Patient (link to patient detail)
- **Actions column** (admin or engineer): Report Issue / Resolve Issue toggle; clinic toggle (admin only)

Status badges: **Available** (green) · **Assigned** (blue) · **Clinic Only** (slate) · **Issue** (red) · **Lost** (slate, agwatch only)

SIM row columns: Phone number, Network, Linked Modem, Recharge Date, Expiry Status badge.
SIM expiry badge: **Active** (green) · **Expires in Xd** amber (≤5d) · **Expires in Xd** red (≤3d) · **Expired** (red).
When a SIM is expired, a **Recharge** button appears inline in the Expiry Status cell. Clicking it opens the Recharge SIM modal (Recharge Date, Data Plan, Expiry Date auto-computed from plan).

Agwatch section header has **Right Watch** and **Left Watch** add buttons (admin only).

#### Data sources

- `GET /devices/api/inventory` — returns full inventory with assignment info for all device types:
  ```json
  {
    "pluto":   [{ "id", "serial", "clinic_only", "faulty", "assigned_to": {"homerID","hospitalID"}|null }],
    "mars":    [...],
    "agwatch": [{ ..., "has_issue", "lost", "assigned_to": {..., "limb"}|null }],
    "modems":  [{ "id", "serial", "clinic_only", "sim_id", "sim_info": {"id","phoneNumber","network"}|null }],
    "laptops": [{ "id", "serial", "clinic_only", "assigned_to": {...}|null }],
    "sims":    [{ "id", "phoneNumber", "network", "rechargeDate", "expiryDate", "daysUntilExpiry", "isExpired", "modem_id" }]
  }
  ```

#### Actions

- **Add Device** (Pluto/Mars) — admin only. Modal: device type selector, ID, serial. `POST /devices/api/add`
- **Add Watch** — admin only. Separate "Right Watch" / "Left Watch" buttons. Modal: ID, serial, limb pre-filled (read-only). `POST /devices/api/add` with `device_type: agwatch`.
- **Add Modem** — admin only. Modal: ID, serial. SIM is linked post-creation via Link SIM. `POST /devices/api/add` with `device_type: modem`.
- **Add SIM** — admin only. Modal: phone number, network, recharge date, expiry date, reminder days. `POST /devices/api/add` with `device_type: sim`.
- **Add Laptop** — admin only. Modal: ID, serial. `POST /devices/api/add` with `device_type: laptop`.
- **Link SIM** — admin only. Per-modem button. Dropdown of available SIMs (unlinked or currently linked). `POST /devices/api/link-sim`.
- **Toggle Clinic** — admin only. Switches `clinic_only` between true/false. Clinic-only devices do not appear in patient assignment dropdowns. `POST /devices/api/toggle-clinic`.
- **Report Issue / Resolve Issue** — admin or engineer. Sets/clears `faulty` (Pluto/Mars) or `has_issue` (Agwatch). Devices with active issues excluded from `get_available_devices()`. `POST /devices/api/toggle-issue`.

---

## Actions

Each action is defined once here. Pages above reference which actions apply to them.

---

### Successful login

- Trigger: User submits correct credentials
- Allowed users: all
- Modal fields: none (standard login form)
- Server actions:
  - Open session row in `dashboard/<user_id>.csv`
  - Run broken protocol check: stamp `brokenProtocolDate` + log entry for any newly-detected patients
- Log message: none

---

### Failed login

- Trigger: User submits incorrect credentials
- Server actions: none
- Log message: none

---

### Add Patient

- Trigger: "Add Patient" button on `/patients`
- Allowed users: `admin`
- Modal fields:
  - Hospital Patient ID (text, required)
  - Training Side (Left / Right toggle, required)
- Server actions:
  - Generate `homerID`
  - Create `<homer_id>.json`
  - Create `<homer_id>.log`
  - Create patient subfolders
- Log message: `Created new patient : <homer_id>.json`

---

### Assign Group

- Trigger: "Assign Group" button on patient card (unassigned patients)
- Allowed users: `admin`
- Modal fields:
  - Group (Experimental / Control toggle, required)
  - A0 Assessment Date (datetime, required; cannot be in the future)
- Server actions:
  - Update `<homer_id>.json` with `group` and `a0CompletionDate`
  - Create `protocol_events.json` — pre-populate `incomplete` with all timed events; compute `scheduled_date` for `reference: "assignment"` events; leave `reference: "activation"` events as `null` placeholders
- Log message: `Group assigned: <group>`

---

### Pre-Discontinue

- Trigger: "Pre-DC" button on patient card (unassigned patients)
- Allowed users: `admin`, `therapist`
- Modal fields:
  - Reason / Comments (textarea, required)
- Server actions:
  - Update `<homer_id>.json` with `discontinuationDate`
  - Append `pre_discontinuation` record to `protocol_events.json` free section
- Log message: `Patient pre-discontinued`

---

### Activate

- Trigger:
  - Clicking the `activation` event row on patient detail (inactive patients).
  - Takes the user to patients details page where the modal is implemented.
- Allowed users: `admin`, `therapist`
- Prerequisites: all events listed in `depends_on` for `activation` in `study_protocol.json` must be in `complete` (e.g. `exp_device_install` for experimental patients)
- Modal fields:
  - **Was training completed?** (toggle, required — must be explicitly set before other fields appear)
  - **If YES (training completed):**
    - Event Date (datetime, required; cannot be in the future)
    - **VCG Group** (dropdown: VCG 2 / VCG 3 / VCG 4–5; required; **control patients only**) — therapist selects the patient's VCG level at the activation visit; fixed for the entire study duration
    - Notes (textarea, optional)
    - **Triggered events section** — user can optionally flag an adverse event, robot issue (exp only) as a consequence of this visit. Each toggle shows an info note only — no sub-form fields. Watch Record toggle always shown (first watch record is seeded on activation).
  - **If NO (training not completed):**
    - **Primary reason** (pill buttons, required): `Adverse Event` / `Robot Issue` (exp only) / `Other Device Issue` (exp only) / `Other`. Same behavior as home visit D02/D03 "No" path — selecting a non-"Other" reason auto-triggers that event type with `training_stopped: true`; its secondary toggle is hidden to prevent duplicate stubs.
    - Visit Date (datetime, required; cannot be in the future)
    - Notes (textarea; **mandatory only when primary reason = Other**, optional otherwise)
    - **Triggered events section** — secondary adverse event and robot issue (exp only) toggles. The toggle matching the primary reason is hidden. No watch record toggle (patient not yet activated, no watches assigned).
- Server actions — **training completed path:**
  - Verify `depends_on` prerequisites are met
  - Update `<homer_id>.json` with `activationDate` and `vcgGroup` (control patients only)
  - Compute and fill `scheduled_date` for all `reference: "activation"` entries in `protocol_events.json`
  - Seed first `watch_record` entry in `incomplete` with `scheduled_date = [activationDate, activationDate]` and `triggered_by = {type: "activation", id: <activation_entry_id>}`
  - For triggered `adverse_event`: append stub to `incomplete` with `triggered_by: {type: "activation", id: <activation_entry_id>}`
  - For triggered robot issue: append `robot_issue_call` stub to `incomplete` with `triggered_by: {type: "activation", id: <activation_entry_id>}`
  - For triggered `watch_record`: stamp `triggered_by` and update `scheduled_date = [now, now]` on the open chain entry
  - Log message: `Patient activated`
- Server actions — **training not completed path:**
  - Append `activation_attempt` entry to `free.activation_attempt[]` in `protocol_events.json` with `visit_date`, `completion_date` (= visit_date), `primary_reason`, `notes`, `filed_at`, `triggered: [...]`
  - `activation` protocol event remains in `incomplete` — nothing changes on patient JSON
  - If `primary_reason` is not `"other"`: auto-append that event type stub to `incomplete` with `triggered_by: {type: "activation_attempt", id: <attempt_entry_id>}` and `training_stopped: true`. This stub is the primary reason event and is not duplicated by the secondary trigger section.
  - For any secondary triggered events (those whose toggle was not hidden by the primary reason): append stubs to `incomplete` with `triggered_by: {type: "activation_attempt", id: <attempt_entry_id>}`.
  - `activation_attempt` entries are included in `_FREE_EVENT_NAMES` and appear in the timeline and completed-events count.
  - Log message: `Activation attempt recorded — training not completed`
- UI behaviour: if prerequisites are unmet, the event row is rendered as a non-clickable `<div>` with a muted lock icon and amber "Needs: \<blocking event name\>" badge
- **Event row deadline label:** the activation event row uses "Expires today" / "Expires in X days" instead of the standard "Due today" / "Xd left" label. Activation is the only event with this label — it is a true hard cutoff (after Day 5, activation is permanently impossible). All other windowed events use the standard overdue/upcoming labels.

---

### Record A1 Assessment (`a1_assessment`)

- Trigger: `a1_assessment` event row on patient detail — appears in overdue/upcoming panels once the patient reaches `training_completed` status. This is a windowed protocol event (window defined in `study_protocol.json`, approximately days 30–37 after activation, i.e. 2–4 weeks after D29).
- Allowed users: `admin`, `therapist`
- **Event row UI**: click the row to open the A1 recording modal. No inline buttons on the row.
- **"Delayed" badge**: if the assessment is completed after `window_end`, the completed event row (in the timeline and overdue panel) shows an amber "Delayed" badge. Filed on time → no badge.
- Modal: `a1-assessment-modal`
  - Title: "Record A1 Assessment"
  - **Cancellation section (top)** — shown only when `appointment_date` is not null:
    - Displays the currently scheduled appointment date
    - Reason (text input, required to confirm cancel)
    - "Cancel Scheduled Assessment" button — on click: show a confirmation dialog ("Cancel the scheduled A1 assessment on \<date\>? This cannot be undone."). On confirm:
      - Append `{ cancelled_at, appointment_date, reason }` to `appointment_cancellations` on the `a1_assessment` stub
      - Reset `appointment_date` to `null` on the stub
      - Modal stays open; cancellation section disappears
    - After cancellation, auto-seeding in `api_patient_events` will create a `schedule_a1_call` stub on next load if all seeding conditions are met (see [Auto-seeding](#auto-seeding-both)). In practice: by the time an appointment is cancelled, `today >= window_start − 7 days` is already satisfied, so the stub seeds immediately as long as the window has not yet closed.
  - Assessment Date (datetime, required; cannot be in the future)
    - **Out-of-window confirmation**: if the chosen date falls outside `[window_start, window_end]`, a double-confirmation dialog fires before saving: "This date is outside the A1 assessment window. Are you sure?" The therapist can proceed or go back.
  - Notes (textarea, optional)
  - **Mark as Missed** button — the therapist can mark A1 as missed if the patient confirms they will not attend. On click: double-confirmation dialog ("Mark A1 assessment as missed? This cannot be undone."). On confirm:
    - Move `a1_assessment` stub from `incomplete` to `complete` with `missed: true`, `missed_at: <now>`, `filed_at`
    - Update `<homer_id>.json` with `a1MissedDate = missed_at`
    - Any open `schedule_a1_call` stub is removed from `incomplete`
  - Completion and cancellation are **independent** — the therapist can cancel only, complete only, or cancel then complete (patient arrived at a different time)
- Server actions (completion):
  - Move `a1_assessment` entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date`, `filed_at`
  - Update `<homer_id>.json` with `a1CompletionDate = completion_date`
- Server actions (cancellation — separate endpoint):
  - Append cancellation record to `appointment_cancellations` on the `a1_assessment` incomplete stub
  - Set `appointment_date = null` on the stub
- Log message: `A1 assessment recorded` / `A1 assessment appointment cancelled` / `A1 assessment marked as missed`

---

### Record A2 Assessment (`a2_assessment`)

- Trigger: `a2_assessment` event row on patient detail — appears in overdue/upcoming panels once the patient reaches `a1_completed` status. Windowed protocol event (window defined in `study_protocol.json`, approximately days 60–90 after activation, i.e. ~4 weeks after A1 window).
- Allowed users: `admin`, `therapist`
- **`schedule_a2_call` auto-seeding:** In `api_patient_events`, if `today >= a2_window_start − 7 days` AND `today ≤ a2_window_end` AND A2 is not complete AND no `schedule_a2_call` stub exists in `incomplete`, a new `schedule_a2_call` stub is created. Seeding stops once the window closes — after that the assessment is reached directly from the overdue panel.
- **"Delayed" badge**: same rule as A1 — amber badge when `completion_date > window_end`.
- **A2 before A1 confirmation**: when the therapist opens the A2 modal and `a1_assessment` is still in `incomplete` (not missed, not complete), a double-confirmation fires: "A1 has not been completed. Filing A2 will automatically mark A1 as missed. Continue?" On confirm: A1 is auto-missed (same server action as "Mark as Missed" above) before A2 proceeds.
- **Event row UI**: click the row to open the A2 recording modal. No inline buttons on the row.
- Modal: `a2-assessment-modal`
  - Title: "Record A2 Assessment"
  - Same structure as A1 modal — cancellation section (top, conditional), assessment date with out-of-window confirmation, notes, Mark as Missed button
- Server actions: same as A1 but targets `a2_assessment` stub and writes `a2CompletionDate` / `a2MissedDate`
- Log message: `A2 assessment recorded` / `A2 assessment appointment cancelled` / `A2 assessment marked as missed`

---

### Assessment Scheduling Call (`schedule_a1_call`, `schedule_a2_call`)

Two free events — one per assessment. Record a phone call made by the therapist to schedule or reschedule an assessment appointment.

**Display names:** `schedule_a1_call` → "Schedule A1 Assessment"; `schedule_a2_call` → "Schedule A2 Assessment"

#### Auto-seeding (both)

A scheduling call stub is auto-seeded by `api_patient_events` (lazily, once per patient) when ALL of the following hold:
- The corresponding assessment (`a1_assessment` / `a2_assessment`) is in `incomplete` with `appointment_date = null`
- AND no stub for the corresponding scheduling call already exists in `incomplete`
- AND **`today >= window_start − 7 days`** — gives therapist a 1-week lead time; prevents premature seeding when training ends early (broken protocol / discontinuation set on Day 3 should not immediately show the scheduling stub)
- AND **`today ≤ window_end`** — once the protocol window has closed, no scheduling stub is seeded; the assessment is reached directly from the overdue panel
- AND **training has permanently ended** — `trainingCompletionDate` OR `brokenProtocolDate` OR `discontinuationDate` is set. `post_training` (Day 28 passed but D29 not filed) does **not** trigger seeding.

For normal patients, D29 sets `appointment_date` directly in the modal, so the `appointment_date = null` condition is never met via this path — no stub seeds at D29. The stub only appears if that appointment is later cancelled.

Only one stub may exist in `incomplete` at a time.

#### `schedule_a1_call`

- Trigger: auto-seeded (see above). Appears in overdue as **"Schedule A1 Assessment"**.
- Allowed users: `admin`, `therapist`
- Modal: `schedule-a1-call-modal`
  - Title: "Schedule A1 Assessment"
  - Call Date/Time (datetime, required; cannot be in the future)
  - Duration (integer minutes, required; must be > 0)
  - Notes (textarea, required)
  - New Appointment Date (date only, required) — the date the patient agreed to come for A1
- Server actions:
  - Remove stub from `incomplete`
  - Append completed entry to `free.schedule_a1_call` with `completion_date`, `filed_at`, `duration_minutes`, `notes`, `new_appointment_date`
  - Update the `a1_assessment` stub's `scheduled_date` in `incomplete` to `[new_appointment_date + "T09:00", new_appointment_date + "T09:00"]`
- Log message: `A1 scheduling call recorded — new appointment: <date>`

#### `schedule_a2_call`

- Trigger: auto-seeded (see above). Appears in overdue as **"Schedule A2 Assessment"**.
- Allowed users: `admin`, `therapist`
- Modal: `schedule-a2-call-modal`
  - Title: "Schedule A2 Assessment"
  - Same fields as `schedule_a1_call`
- Server actions: same as `schedule_a1_call` but targets `a2_assessment` stub and appends to `free.schedule_a2_call`
- Log message: `A2 scheduling call recorded — new appointment: <date>`

**Common notes:**
- Missing an A1 or A2 assessment is not a broken protocol event and does not trigger discontinuation. The study continues with whatever assessments were completed.
- A delayed assessment (completed after `window_end`) is valid and recorded normally — the `completion_date` captures when it actually happened. An amber "Delayed" badge is shown on the event row.
- History: all past scheduling calls are visible in the Timeline tab (as completed free events in `free.schedule_a1_call` / `free.schedule_a2_call`).
- Appointment cancellation history is stored on the assessment stub's `appointment_cancellations` list (see data_schemas.md).
- Missed assessments are stored in `complete` with `missed: true` and `missed_at`. `a1MissedDate` / `a2MissedDate` are written to `<homer_id>.json`.

---

### Create Note (`note`)

- Trigger: "Create Note" button at the top of the **Notes** tab on patient detail
- Allowed users: `admin`, `therapist`, `engineer` (all roles may create)
- Notes are **immutable** — there is no edit or delete action. Corrections are filed as a new note that references the earlier one by alias.
- Modal: `note-modal` (`max-w-3xl`)
  - Title: "Create Note"
  - **Note title** (text, required)
  - **Body** — Quill rich-text editor (required); stored as HTML in `content_html`
  - Attachment (optional PDF; caption required when a file is attached)
  - On open, the client records the modal-open time; on save it sends the elapsed gap so the server can set `created_at = committed_at − gap` (same mechanism as the A1/A2 auto-miss ordering fix)
- Server actions (`POST /api/patients/<homer_id>/notes`, in `routes/notes.py`):
  - Determine the author's role bucket (`admin` / `therapist` / `engineer`); create `notes.json` lazily if absent
  - Assign `alias = Notes-<R>-NNNN` (`<R>` = role letter, `NNNN` = next sequence in that bucket)
  - Set `committed_at = now()`, `created_at = committed_at − gap`, `author = loginid`
  - Save uploaded PDF to `note_attachments/<note_id>.pdf` if present; store `attachment` + `attachment_caption`
  - Append the note object to the role bucket in `notes.json`
- Read (`GET /api/patients/<homer_id>/notes`): returns the caller's own bucket (therapist/engineer) or all three buckets (admin), each sorted newest-first by `created_at`
- Attachment download (`GET /api/patients/<homer_id>/notes/<note_id>/attachment`): allowed for the note's **author (any role) and admin** — a note-scoped exception to the rule that engineers cannot download attachments
- Log message: `Note created — <alias>`

---

### Retrospective Event Notes (`event_notes`)

Notes attached to an already-completed event, after the fact. **Only** accessible from the **Timeline** tab (expand an event row). Stored on the event entry in `protocol_events.json` as `event_notes` (role-keyed buckets); see `docs/data_schemas.md`.

- Trigger: **Add Note** button in the Timeline detail panel of the selected event
- Allowed users: `admin`, `therapist`, `engineer` (all roles may create). Synthetic rows (Patient Enrolled, A0) cannot take notes.
- **Immutable** — no edit/delete; corrections are a new note referencing the earlier one by alias.
- Modal: reuses the `note-modal` (`max-w-3xl`) — title (required), Quill body (required), optional PDF (caption required when attached). On open the client records the modal-open time; on save it sends the elapsed gap.
- Create (`POST /api/patients/<homer_id>/events/<event_id>/notes`, in `routes/notes.py`):
  - Locate the event (search `complete[]` then `free.*[]` by `id`); create its `event_notes` bucket object lazily
  - Assign `alias = EvtNote-<R>-NNNN` (`<R>` = role letter; `NNNN` = next sequence for that role **patient-wide** across all events)
  - Set `committed_at = now()`, `created_at = committed_at − gap`, `author = loginid`
  - Save uploaded PDF to `note_attachments/<note_id>.pdf`; store `attachment` + `attachment_caption`
  - Append to `event_notes[<role>]` on the event entry; write `protocol_events.json`
- Read (`GET /api/patients/<homer_id>/events/<event_id>/notes`): returns the caller's own bucket (therapist/engineer) or all three (admin), newest-first by `created_at`, plus `is_admin`
- Attachment download (`GET /api/patients/<homer_id>/event-notes/<note_id>/attachment`): allowed for the note's **author (any role) and admin** — same note-scoped exception as free notes
- **Leak prevention:** `GET /api/patients/<homer_id>/events` strips `event_notes` from every entry, so notes reach the client only through the role-filtered read endpoint above
- Log message: `Event note created — <alias>`

---

### Discontinue

Discontinuing a patient is a two-step process: (1) a `discontinuation` stub is created via a double-confirmed button click, then (2) the stub is completed via the discontinuation modal. Broken-protocol patients skip step 1 — they use a synthetic `discontinuation_reminder` event instead.

#### "Discontinue Patient" button

- Trigger: "Discontinue Patient" button in the patient detail header
- Allowed users: `admin`
- **Visible when:** patient status is `inactive`, `active`, or `paused` AND no real `discontinuation` stub exists in `incomplete`
- **Hidden when:** a real `discontinuation` stub already exists in `incomplete` (avoid duplicate stubs), OR patient is `broken_protocol` (use `discontinuation_reminder` instead), OR patient is `training_completed`, `a1_completed`, `post_training`, `all_completed`, `discontinued`, or `pre_discontinued`. Training completion is the natural end of the protocol — discontinuation is not applicable from that point onwards.
- Applicable states where button is visible: `inactive`, `active`, `paused`
- On click — double confirmation popup:
  1. "Discontinuing a patient is a major and irreversible event. Are you sure you want to proceed?"
  2. "This will permanently close the patient record once the discontinuation event is completed. Confirm?"
- On double confirm: server creates a `discontinuation` stub in `incomplete` with `scheduled_date: [now, now]`; button disappears; stub appears in the overdue panel as a clickable event row

#### `discontinuation_reminder` (synthetic event — broken_protocol only)

- Injected by both event APIs (`/api/patients/<homer_id>/events` and `/api/dashboard/events`) when:
  1. Patient status is `broken_protocol`
  2. No real `discontinuation` stub or entry exists in `free.discontinuation`
- Opens the discontinuation modal directly — no extra confirmation step (broken protocol is already a confirmed state requiring no additional double-check)
- The `discontinuation_reminder` is a synthetic event only; it is never written to disk

#### Discontinuation modal

- Trigger: clicking the real `discontinuation` stub in the overdue panel, **or** clicking the `discontinuation_reminder` synthetic event row (broken_protocol path)
- Allowed users: `admin`
- Modal: `discontinuation-modal`
  - Context banner (read-only): "Once saved, this patient record becomes read-only."
  - Discontinuation Date (datetime, required; cannot be in the future)
  - Reason (textarea, required)
  - Notes (textarea, optional)
  - Attachment (optional PDF)
- Server actions:
  - If triggered from real stub: remove the stub from `incomplete`
  - Set `discontinuationDate` on `<homer_id>.json`
  - **Does NOT close device assignments** — the `device_return` event (filed separately by the engineer) is responsible for closing all assignments
  - Append completed entry to `free.discontinuation` with `completion_date`, `filed_at`, `reason`, `notes`, `attachment`
- Log message: `Patient discontinued`

---

### ADL Prescription (`adl_prescription_d01`)

- Trigger: `adl_prescription_d01` event row on patient detail (both groups, day 1 after activation)
- Allowed users: `admin`, `therapist`
- Modal fields:
  - Event Date (read-only — auto-populated from the `activation` event's `completion_date`)
  - **Exercise search bar** — live-filters the ADL exercise list fetched from `GET /api/exercises?type=adl`; clicking a result adds it to the selected list; already-selected exercises are excluded from search results
  - **Selected exercises list** (scrollable if long) — each exercise exists in one of two states:
    - _Editing state_ (entered when first added, or when Edit is pressed): exercise name + × (remove) button; Blocks field (number, required); Repetitions field (number, required); Notes field (textarea, optional); **Save** button — commits values and collapses to compact view
    - _Compact state_ (entered after Save is pressed): exercise name · `<blocks> blocks × <reps> reps`; **Edit** button (re-expands to editing state pre-filled with saved values); × button (removes exercise)
    - The modal's **Save Prescription** button is **disabled** while any exercise card is in editing state — the therapist must Save or remove all cards before submitting
  - General Notes (textarea, optional)
- Server actions:
  - Write prescription to `adl/adl_prescription_d01.json` in the patient folder
  - Move `adl_prescription_d01` entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date`, `filed_at`, `prescription_file: "adl/adl_prescription_d01.json"`
- Log message: `ADL prescription recorded`

---

### VCG Prescription (`vcg_prescription_d01`)

- Trigger: `vcg_prescription_d01` event row on patient detail (control patients only, day 1 after activation)
- Allowed users: `admin`, `therapist`
- Modal fields:
  - Event Date (read-only — auto-populated from the `activation` event's `completion_date`)
  - **VCG Group** (read-only display — pre-filled from `vcgGroup` in `<homer_id>.json`, set at activation)
  - **Exercise search bar** — live-filters the VCG exercise list fetched from `GET /api/exercises?type=vcg&group=<vcg_group>`; clicking a result adds it to the selected list; already-selected exercises are excluded
  - **Selected exercises list** (scrollable if long) — same two-state card behaviour as [ADL Prescription](#adl-prescription-adl_prescription_d01); **Save Prescription** button disabled while any card is in editing state
  - General Notes (textarea, optional)
- Server actions:
  - Write prescription to `vcg_exercise/vcg_prescription_d01.json` in the patient folder
  - Move `vcg_prescription_d01` entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date`, `filed_at`, `prescription_file: "vcg_exercise/vcg_prescription_d01.json"`
- Log message: `VCG prescription recorded`

---

### Prescription Printout (`prescription_printout_d01`)

- Trigger: `prescription_printout_d01` event row on patient detail (both groups, day 1 after activation)
- Allowed users: `admin`, `therapist`
- `depends_on`: `adl_prescription_d01` (both groups); `vcg_prescription_d01` (control only)
- Modal: `prescription-printout-modal`
  - Title: "Therapy Prescription Printout"
  - Patient ID display (read-only)
  - PDF preview area (TODO: generate and render prescription PDF)
  - **Save PDF** button — generates PDF, saves to `attachments/prescription_d01.pdf`, marks event complete, downloads file to browser
  - **Print** button — generates PDF, saves to `attachments/prescription_d01.pdf`, marks event complete, sends to printer
- Server actions:
  - Generate prescription PDF (TODO)
  - Save PDF to `attachments/prescription_d01.pdf` in the patient folder (overwrite if exists)
  - Move `prescription_printout_d01` entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date` (current datetime), `filed_at` (current datetime), `attachment: "attachments/prescription_d01.pdf"`
- Log message: `Prescription printout generated`

---

### Revised Prescription Printout (`prescription_printout_d15`)

- Trigger: `prescription_printout_d15` event row on patient detail (both groups, day 15 after activation)
- Allowed users: `admin`, `therapist`
- `depends_on`: `adl_prescription_d15` (both groups); `vcg_prescription_d15` (control only)
- Modal: `prescription-printout-modal` (shared with d01)
  - Title: "Revised Therapy Prescription Printout"
  - Patient ID display (read-only)
  - PDF preview area (TODO: generate and render revised prescription PDF)
  - **Save PDF** button — generates PDF, saves to `attachments/prescription_d15.pdf`, marks event complete, downloads file to browser
  - **Print** button — generates PDF, saves to `attachments/prescription_d15.pdf`, marks event complete, sends to printer
- Server actions:
  - Generate revised prescription PDF (TODO)
  - Save PDF to `attachments/prescription_d15.pdf` in the patient folder (overwrite if exists)
  - Move `prescription_printout_d15` entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date` (current datetime), `filed_at` (current datetime), `attachment: "attachments/prescription_d15.pdf"`
- Log message: `Revised prescription printout generated`

---

### ADL Prescription Revision (`adl_prescription_d15`)

- Trigger: `adl_prescription_d15` event row on patient detail (both groups, day 15 after activation)
- Allowed users: `admin`, `therapist`
- `depends_on`: `home_visit_d15` (both groups)
- Modal fields: same structure as [ADL Prescription](#adl-prescription-adl_prescription_d01), with:
  - Event Date (read-only — auto-populated from the `home_visit_d15` event's `completion_date`)
  - Exercise list and notes pre-populated from `adl/adl_prescription_d01.json` — all cards open in **compact state** (already saved); therapist edits individual cards as needed
- Server actions:
  - Write revised prescription to `adl/adl_prescription_d15.json` in the patient folder
  - Move `adl_prescription_d15` entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date`, `filed_at`, `prescription_file: "adl/adl_prescription_d15.json"`
- Log message: `ADL prescription revised`

---

### VCG Prescription Revision (`vcg_prescription_d15`)

- Trigger: `vcg_prescription_d15` event row on patient detail (control patients only, day 15 after activation)
- Allowed users: `admin`, `therapist`
- `depends_on`: `home_visit_d15`
- Modal fields: same structure as [VCG Prescription](#vcg-prescription-vcg_prescription_d01), with:
  - Event Date (read-only — auto-populated from the `home_visit_d15` event's `completion_date`)
  - VCG Group read-only (from `vcgGroup` in `<homer_id>.json` — fixed for entire study)
  - Exercise list and notes pre-populated from `vcg_exercise/vcg_prescription_d01.json` — all cards open in **compact state**; therapist edits individual cards as needed
- Server actions:
  - Write revised prescription to `vcg_exercise/vcg_prescription_d15.json` in the patient folder
  - Move `vcg_prescription_d15` entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date`, `filed_at`, `prescription_file: "vcg_exercise/vcg_prescription_d15.json"`
- Log message: `VCG prescription revised`

---

### Home Visit (`home_visit_d02`, `home_visit_d03`, `home_visit_d15`)

- Trigger: respective event row on patient detail
- Allowed users: `admin`, `therapist`
- Modal: `home-visit-modal` (dedicated; not shared)
  - Title: event name (e.g. "Home Visit Day 02")
  - **Was training completed?** (toggle, required — must be explicitly set before other fields appear)
  - **If YES (training completed):**
    - Session Start (datetime, required; cannot be in the future)
      - **D02 and D03 only:** the date portion is **pre-filled and locked** to the exact Day 2 or Day 3 calendar date derived from `activationDate`. The therapist selects time only. The date field is read-only. Rationale: if training was completed, it must have been on that day — locking the date prevents entry errors and eliminates any broken protocol ambiguity on this path.
      - **D15:** date is editable as normal (no lock).
    - Session End (datetime, required; must be same calendar date as start and strictly after start)
    - Notes (textarea, optional)
    - **Triggered events section** — adverse event, robot issue (exp only), watch record (if watch assigned). Each toggle shows an info note only — no sub-form fields.
  - **If NO (training not completed):**
    - **Why was training not completed?** (single-select pill buttons, **mandatory**):
      - `Adverse Event` — creates an AE stub with `training_stopped: true`; pre-checks `Training Blocked` in the File AE modal
      - `Robot Issue` *(experimental only)* — creates a `robot_issue_call` stub with `training_stopped: true`; pre-checks `Visit Required` for all devices in the RI Call modal
      - `Other Device Issue` *(experimental only)* — creates an `other_device_issue_call` stub with `training_stopped: true`; pre-checks `Visit Required` for all devices in the ODI Call modal
      - `Other` — no stub; notes field becomes mandatory
    - Visit Date (datetime, required; cannot be in the future)
    - Notes (textarea; **mandatory when primary reason = Other**, optional otherwise)
    - **Additional events** — secondary trigger toggles for any other events that arose from this visit (same as existing section). The toggle matching the primary reason is **hidden** (duplicate stub prevention).
- Client validation — **training not completed path (D02 and D03 only):**
  - Before submitting, show a **double confirmation popup**:
    - First popup: "Training was not completed on Day N. This will mark the patient as broken protocol. Continue?"
    - Second popup: "This cannot be undone without admin intervention. Confirm broken protocol?"
  - Only proceed to server save if both are confirmed. Include `confirmed_broken_protocol: true` in the request body.
- Server actions — **training completed path** (all three visits):
  - For D02 and D03: validate that `session_start` and `session_end` fall on the expected calendar date (`activationDate + N − 1 days`); reject with 400 if not
  - Move entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date` (= session start), `session_start`, `session_end`, `filed_at`, `notes`, `triggered: [...]`
  - For triggered `adverse_event`: append stub to `incomplete` with `triggered_by: {type: "<home_visit_event_id>", id: <entry_id>}`
  - For triggered robot issue: append `robot_issue_call` stub to `incomplete` with `triggered_by: {type: "<home_visit_event_id>", id: <entry_id>}`
  - For triggered `watch_record`: stamp `triggered_by` and update `scheduled_date = [now, now]` on the open chain entry
  - Log message: `Home visit recorded — Day <N>`
- Server actions — **training not completed path (D02 and D03):**
  - Require `confirmed_broken_protocol: true` in request body; reject with 409 if absent
  - Move entry from `incomplete` to `complete` with `training_not_done: true`, `primary_reason`, `completion_date` (= visit date), `filed_at`, `notes`, `triggered: [...]`
  - Set `brokenProtocolDate` on `<homer_id>.json` immediately
  - For triggered events: same stub creation as training completed path (excluding watch record). The stub for the primary reason gets `training_stopped: true` added.
  - Log message: `Home visit recorded — Day <N> — training not completed — broken protocol`
- Server actions — **training not completed path (D15 only):**
  - Append `d15_attempt` entry to `free.d15_attempt[]` in `protocol_events.json` with `visit_date`, `primary_reason`, `notes`, `triggered: [...]`
  - `home_visit_d15` remains in `incomplete`
  - For triggered events: same stub creation, with `triggered_by: {type: "d15_attempt", id: <attempt_entry_id>}`. Primary reason stub gets `training_stopped: true`.
  - Log message: `D15 attempt recorded — training not completed`

---

### Follow-up Call (`followup_call_d07`, `followup_call_d21`)

- Trigger: respective event row on patient detail
- Allowed users: `admin`, `therapist`
- Modal: `followup-call-modal` (dedicated; not shared with home visits)
  - Title: event name (e.g. "Follow-up Phone Call Day 07")
  - Call Date/Time (datetime, required; cannot be in the future)
  - **Date Change Reason** (textarea, amber border, conditionally visible): shown only when the selected date differs from `scheduled_date[0]`; required when visible; label shows the scheduled date for reference
  - Duration (integer minutes, required; must be > 0)
  - Training log PDF (file upload, required; `.pdf` only) — photos of the patient's weekly training log, sent by the patient before the call
  - Notes (textarea, required)
  - **Triggered events section** — user can optionally flag an adverse event, robot issue (exp only), and/or watch record as a consequence of this call. Each toggle shows an info note only — no sub-form fields. Watch Record toggle only shown if at least one watch is currently assigned.
  - **AE Discussion** (Yes/No, required when an `adverse_event_followup` stub exists in `incomplete`; hidden otherwise) — "Did any AE-related discussion happen during this call?" If Yes, the AE follow-up modal opens automatically after the call saves, with **call date and duration pre-filled** from this call. If No, the call saves normally and the stub remains accessible from the overdue panel.
- Server actions:
  - Save uploaded PDF to `attachments/followup_call_d07.pdf` (or `d21`) in the patient folder, overwriting if exists
  - Move entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date`, `filed_at`, `duration_minutes`, `attachment`, `notes`, `triggered: [...]`; if date differs from scheduled, also adds `date_change_reason`
  - For triggered `adverse_event`: append a stub to `incomplete` with `protocol_event_id = "adverse_event"`, `scheduled_date = [now, now]`, `triggered_by: {type: "<followup_call_event_id>", id: <entry_id>}` — stub is completed later via the standalone modal
  - For triggered robot issue: append a `robot_issue_call` stub to `incomplete` with `triggered_by: {type: "<followup_call_event_id>", id: <entry_id>}`, `scheduled_date: [now, now]` — no intermediate `robot_issue` event
  - For triggered `watch_record`: stamp `triggered_by` and update `scheduled_date = [now, now]` on the open `watch_record` chain entry
- **Post-save AE follow-up (client-side):** if `ae_discussion = "yes"` and an `adverse_event_followup` stub exists, the AE follow-up modal opens automatically with `call_date` pre-filled from `completion_date` and `duration_minutes` pre-filled from the call duration (both remain editable). The stub always persists in `incomplete` regardless of the answer.
- Log message: `Follow-up call recorded — Day <N>`

---

### Patient Call

- Trigger: "Log Patient Call" button in the tab bar on patient detail
- Allowed users: `admin`, `therapist`
- **Visible when:** patient status is `active`, `paused`, `post_training`, `training_completed`, `a1_completed`, `broken_protocol`, or `discontinued`. Hidden once `all_completed` (A2 done/delayed/missed — no further contact needed), and also hidden for `inactive`, `unassigned`, `pre_discontinued`.
- Modal: `patient-call-modal`
  - Title: "Log Patient Call"
  - Call Date/Time (datetime, required; cannot be in the future)
  - Duration (integer minutes, required; must be > 0)
  - Notes (textarea, required)
  - **Therapist initiated** (toggle, default off) — indicates an unplanned outbound call by the therapist (e.g. following up after an adverse event). Protocol follow-up calls (D7/D21) are not recorded here. When toggled on, a **Reason** field (textarea, required) appears to document why the call was made outside the normal protocol.
  - **Adverse event(s) discussed** (checkbox, default unchecked) — indicates that one or more ongoing adverse events were discussed during this call. Stored as `ae_discussed: true/false`. Used on the Adverse Events tab to show that a patient call touched an AE, and allows follow-up calls to reference this patient call as the initiating contact when `patient_initiated: true`.
  - **Call mode (required)** — two pills (Audio / Video), no default. Therapist must pick one before save. Stored as `call_mode: "audio" | "video"`. Same field on `followup_call_d07` and `followup_call_d21`.
  - **What came out of this call? (required)** — the user must explicitly state the outcome. Five toggles, with **mutual exclusion** between "No issue" and any of the other four:
    - **No issue** (toggle, both groups): the call had no downstream consequence. Sits at the top of the group. When checked, all four issue toggles below are disabled; when any issue toggle is checked, this toggle is disabled. Stored as `no_issue: true` on the call record.
    - **Adverse Event** (toggle, both groups): if enabled, shows an info note only — no sub-form fields
    - **Robot Issue** (toggle, experimental only — hidden for control patients): if enabled, shows an info note only — no sub-form fields
    - **Watch Record** (toggle, both groups): only shown if at least one watch is currently assigned (`agWatchRightID` or `agWatchLeftID` is not null); if enabled, shows an info note — no sub-form fields
    - **Other Device Issue** (toggle, experimental only — hidden for control patients): if enabled, shows an info note only — no sub-form fields
  - Multiple issue toggles may be enabled simultaneously when "No issue" is not selected. Save is blocked until either "No issue" or at least one issue toggle is checked (the client shows an error; the server enforces `no_issue XOR len(triggered) > 0`).
  - Attachment (optional PDF)
- Server actions:
  - Append `patient_call` entry to `free.patient_call` in `protocol_events.json`, with `call_type`, `call_mode`, `reason` (if therapist initiated), `ae_discussed`, `no_issue`, `triggered: [...]`
  - For each enabled toggle:
    - **Adverse event**: append a stub to `incomplete` with `protocol_event_id = "adverse_event"`, `scheduled_date = [now, now]`, `triggered_by: {type: "patient_call", id: <call_id>}` — stub is completed later via the standalone `adverse-event-modal`
    - **Robot issue** (exp only): append a `robot_issue_call` stub to `incomplete` with `triggered_by: {type: "patient_call", id: <call_id>}`, `scheduled_date: [now, now]` — no intermediate `robot_issue` event
    - **Watch record**: stamp `triggered_by: {type: "patient_call", id: <call_id>}` onto the existing open `watch_record` entry in `incomplete`, and update its `scheduled_date` to `[now, now]` — no new entry is created; the entry immediately becomes overdue; the therapist completes it via the Watch Record modal
- Log message: `Patient call recorded`; additional log entries for each triggered event (e.g. `Adverse event stub created`, `Robot issue stub created`, `Watch record triggered`)

---

### Activation Attempt (`activation_attempt`)

- Trigger: choosing "No" on the "Was training completed?" toggle in the Activate modal
- Allowed users: `admin`, `therapist`
- Purpose: records a therapist visit where activation was attempted but training could not be completed. A ghost/free event — not planned in advance, can happen multiple times. `activation` protocol event remains `incomplete`.
- Modal fields (rendered inline within the Activate modal when training not completed):
  - **Primary reason** (pill buttons, required): `Adverse Event` / `Robot Issue` (exp only) / `Other Device Issue` (exp only) / `Other`
  - Visit Date (datetime, required; cannot be in the future)
  - Notes (textarea; **mandatory only when primary reason = Other**, optional otherwise)
  - **Triggered events section** — secondary adverse event, robot issue (exp only) toggles. The toggle matching the primary reason is hidden. No watch record (patient not yet activated).
- Storage: appended to `free.activation_attempt[]` in `protocol_events.json`
- Entry fields: `id`, `visit_date`, `completion_date` (= visit_date), `primary_reason`, `notes`, `filed_at`, `triggered: [...]`, `triggered_by: null`
- Consequence: none immediate — `activation` stays in `incomplete` and follows its normal window expiry logic. If an AE is triggered with `training_stopped: true`, `activation` goes On Hold during the pause and becomes active or broken-protocol when the pause clears, depending on whether the window is still open.
- Appears in timeline and completed-events count.
- Log message: `Activation attempt recorded — training not completed`

---

### D15 Attempt (`d15_attempt`)

- Trigger: choosing "No" on the "Was training completed?" toggle in the Home Visit D15 modal
- Allowed users: `admin`, `therapist`
- Purpose: records a therapist visit on or around Day 15 where training could not be completed. A ghost/free event — not planned in advance, can happen multiple times. `home_visit_d15` protocol event remains `incomplete`.
- Modal fields (rendered inline within the Home Visit modal when training not completed):
  - Visit Date (datetime, required; cannot be in the future)
  - Notes (textarea, **mandatory** — must explain why training was not completed)
  - **Triggered events section** — adverse event, robot issue (exp only), and watch record (if watch assigned) toggles.
- Storage: appended to `free.d15_attempt[]` in `protocol_events.json`
- Entry fields: `id`, `visit_date`, `notes`, `filed_at`, `triggered: [...]`, `triggered_by: null`
- Consequence: `home_visit_d15` stays `incomplete` and becomes overdue at its absolute protocol position. D15 dependents (prescriptions, agwatch timing) stay blocked by `home_visit_d15` until it is eventually completed.
- Log message: `D15 attempt recorded — training not completed`

---

### AG Watch Timings (`agwatch_timing_d01`, `agwatch_timing_d02`, `agwatch_timing_d03`, `agwatch_timing_d15`)

- Trigger: respective event row on patient detail
- Both groups. Experimental: ADL exercises only. Control: VCG exercises first, then ADL exercises.
- Allowed users: `admin`, `therapist`
- `depends_on` (group-specific entries in `study_protocol.json`):
  - `agwatch_timing_d01`: `activation`
  - `agwatch_timing_d02`: `home_visit_d02`
  - `agwatch_timing_d03` (experimental): `home_visit_d03`
  - `agwatch_timing_d03` (control): `home_visit_d03`, `vcg_prescription_d01`
  - `agwatch_timing_d15` (experimental): `home_visit_d15`, `adl_prescription_d15`
  - `agwatch_timing_d15` (control): `home_visit_d15`, `adl_prescription_d15`, `vcg_prescription_d15`
- `comes_after`: `agwatch_timing_d01` lists `watch_record` (so watch record task appears first on activation day)
- Modal: wider `agwatch-timing-modal`
  - Title: "AG Watch Timings — Day 01 / 02 / 03 / 15"
  - **Session window** (read-only banner at top): `session_start → session_end` from the associated home visit. All exercise times must fall within this window.
  - Exercise table — VCG rows first (control only), then ADL rows (both groups):

    | Exercise Name (+ block/rep summary, read-only) | Start (`HH:MM`) | End (`HH:MM`) | Notes |
    |---|---|---|---|

  - Per-row rules:
    - Both Start and End filled → Notes optional
    - Both Start and End empty → Notes **required** (explanation of why timing was not recorded)
    - Only one of Start/End filled → error (incomplete entry, cannot save)
  - Attachment (optional PDF)
- **Client-side validation (real-time)**:
  1. Start < End per row (flagged immediately on input)
  2. Start and End within `session_start`/`session_end` bounds
  3. No overlap across all rows (VCG + ADL combined) — both conflicting rows highlighted
  4. Incomplete entry (one of Start/End missing) flagged per row
  5. Missing Notes when both times empty flagged on blur
- Server actions:
  - On modal open — `GET /api/patients/<homer_id>/agwatch-timing-exercises/<protocol_event_id>` — returns VCG + ADL exercise lists with group info and session window from the associated home visit
  - On save — `POST /api/patients/<homer_id>/complete-event/agwatch-timing` — writes timing JSON file, moves event to `complete`
  - For tab display — `GET /api/patients/<homer_id>/agwatch-timing/<protocol_event_id>` — returns saved timing for rendering inline in the ADL/VCG tab
- Log message: `AG watch timings recorded (d01|d02|d03|d15)`

> **Replaces** the previous 8 separate events (`adl_agwatch_timing_d01/02/03/15` and `vcg_agwatch_timing_d01/02/03/15`).

---

### Training Completion Visit (`training_completion_d29`)

- Trigger: `training_completion_d29` event row on patient detail (`active`, `paused`, or `post_training` patients, day 29+)
- Allowed users: `admin`, `therapist`
- Modal: `#d29-modal` (dedicated)
  - Title: "Training Completion Day 29"
  - Event Date (datetime, required; cannot be in the future)
  - Notes (textarea, optional)
  - **A1 Appointment Date** (date only, optional) — when the patient's first A1 assessment is scheduled. If provided, the server updates the `a1_assessment` stub's `appointment_date` directly; no `schedule_a1_call` event is created. Therapists use this to record an appointment agreed with the patient during the D29 visit. Date must fall within the A1 assessment protocol window.
  - **Feedback Form** section:
    - PDF upload (optional upload, but if absent then notes required)
    - Notes textarea (optional unless no file uploaded)
  - **Qualitative Analysis** section:
    - "Was this patient recruited for qualitative analysis?" Yes/No toggle
    - If Yes: Audio recording upload (MP3/M4A/WAV, required)
    - If Yes: Scanned document upload (PDF, optional)
  - Generic attachment section (PDF, optional)
- File naming: `<event_id>_feedback.pdf`, `<event_id>_audio.<ext>`, `<event_id>_scan.pdf`, `<event_id>.pdf`
- Server actions:
  - POST to `/api/patients/<homer_id>/complete-event/training-completion` (multipart form)
  - Move entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date`, `filed_at`, `notes`, `feedback_form_attachment`, `feedback_form_notes`, `qualitative_recruited`, `qualitative_audio_attachment`, `qualitative_scan_attachment`, `attachment`, `attachment_caption`
  - Update `<homer_id>.json` with `trainingCompletionDate = completion_date`
  - If `a1_appointment_date` provided: update the `a1_assessment` stub's `appointment_date` in `incomplete` to `a1_appointment_date + "T09:00"`
  - If patient was `paused`, also clear `trainingPausedDate` and discard `resolve_robot_issue_visit` stubs
  - **Does NOT close device assignments** — that is handled by the `device_return` event (filed separately by the engineer)
  - **AE Discussion** (Yes/No, required when an `adverse_event_followup` stub exists in `incomplete`; hidden otherwise) — "Did any AE-related discussion happen during this visit?" If Yes, the AE follow-up modal opens automatically after D29 saves. If No, D29 saves normally and the stub remains in `incomplete` for later access from the overdue panel.
- **Post-save AE follow-up (client-side):** if `ae_discussion = "yes"` and an `adverse_event_followup` stub exists, the AE follow-up modal is opened automatically after save. If `ae_discussion = "no"`, or no stub exists, the modal is not opened. The stub always persists in `incomplete` regardless.
- Log message: `Training completion visit recorded`

---

### Device Return (`device_return`)

- **Groups:** Both — but device sections differ (see below)
- **Trigger:** `device_return` event row on patient detail. Lazily seeded in `api_patient_events` the first time the page loads after training ends (any path): `trainingCompletionDate` set, OR `brokenProtocolDate` set, OR `discontinuationDate` set. Seeded with `scheduled_date: [now, now]` so it appears immediately as overdue. Only seeded once (guard: no existing stub in `incomplete` and no completed entry in `free.device_return`).
- **Allowed users:** `engineer`, `admin`
- **Modal:** `#device-return-modal`
  - Title: "Device Return"
  - Event Date (datetime, required; cannot be in the future)
  - **Per-device sections** — one card per device currently assigned to the patient, fetched from open assignments:

    **AG Watch — per limb (both groups):**
    - Device ID + limb shown (read-only header)
    - Status: **Returned** / **Lost** / **Battery dead** (required radio)
    - If Lost or Battery dead: **"When did this happen?"** (date, required)
    - Notes (optional)

    **Pluto / Mars (experimental only):**
    - Device ID shown (read-only header)
    - Condition: **Working** / **Faulty** (required radio)
    - Comments (optional)

    **Laptop (experimental only):**
    - Device ID shown (read-only header)
    - Condition: **Working** / **Faulty** (required radio)
    - Comments (optional)

    **Modem (experimental only):**
    - Device ID shown (read-only header)
    - Condition: **Working** / **Faulty** (required radio)
    - Comments (optional)

    **SIM card (experimental only, if modem has a SIM assigned):**
    - Phone number shown (read-only header)
    - Status: **Returned** / **Lost** (required radio)
    - If Lost: **"When did this happen?"** (date, required)
    - Notes (optional)

  - General Notes (textarea, optional)
  - Attachment (optional PDF)

- **Server actions:**
  - Close all open device assignments for this patient across all types: write `returned_date = now` to every open assignment
  - **AG Watch Lost or Battery dead:** set `lost_date` on the watch inventory record; close assignment with `lost: true`; append `faulty` device event with the reported issue date
  - **Pluto / Mars / Laptop / Modem Faulty:** set `has_issue: true` in inventory; append `faulty` device event
  - **SIM Lost:** mark SIM as lost in inventory
  - Append completed entry to `free.device_return`
- **Log message:** `Device return recorded`

---

### Device Setup (`exp_device_install`)

- Trigger:
  - Clicking the `exp_device_install` event row on patient detail (experimental, inactive patients).
  - Takes the user to patients details page where the modal is implemented.
- Allowed users: `admin`, `engineer`
- Modal fields:
  - Event Date (datetime, required; cannot be in the future)
  - Pluto device (dropdown — active, non-clinic, unassigned devices from inventory; required)
  - Mars device (dropdown — same criteria; required)
  - Demo done (toggle, required)
  - Notes (textarea, optional)
- Server actions:
  - Move `exp_device_install` entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date`, `filed_at`, `pluto_id`, `mars_id`, `demo_done`, `notes`
  - Append assignment record to `devices/assignments/pluto.json` and `devices/assignments/mars.json`
  - Append to `devices/logs/pluto/<pluto_id>.log` and `devices/logs/mars/<mars_id>.log`
- Log message: `Device setup completed — Pluto: <pluto_id>, Mars: <mars_id>`

---

### File Adverse Event (`adverse_event`)

- Trigger: `adverse_event` event row on patient detail — only appears when a stub exists in `incomplete` (created by a triggering event: activation, home visit, follow-up call, or patient call)
- Allowed users: `admin`, `therapist`
- Modal: `adverse-event-modal`
  - Title: "File Adverse Event"
  - **Context banner** (read-only): "Triggered by: \<triggering event name\>" — derived from the stub's `triggered_by.type`
  - Event Date (datetime, required; cannot be in the future)
  - Description (textarea, required)
  - Action taken (textarea, required)
  - Training blocked as a result (checkbox) — **only shown when `activationDate` is set** (i.e. patient has been successfully activated at least once). Hidden for pre-activation AEs (triggered from activation attempts) because there is no active training to pause. When shown and checked, `trainingPausedDate` is set and the patient transitions to `paused`. When the stub carries `training_stopped: true`, this checkbox is pre-checked (only applicable post-activation).
  - **Schedule follow-up visit** (optional toggle): when enabled, shows a target date/time input (required when toggle is on; cannot be in the past)
  - **Schedule clinical visit** (optional toggle): when enabled, shows a target date/time input (required when toggle is on; cannot be in the past)
  - Attachment (optional PDF)
- Server actions:
  - Remove the stub from `incomplete` in `protocol_events.json`
  - Append completed entry to `free.adverse_event` with `completion_date`, `filed_at`, `description`, `action_taken`, `training_blocked`, `triggered_by` (carried from stub), `scheduled_followup_visit`, `scheduled_clinical_visit` (both `null` if not scheduled), `attachment` (if uploaded)
  - If `training_blocked` is checked: set `trainingPausedDate` on `<homer_id>.json`; append pause epoch to `pauseHistory`
  - If follow-up visit scheduled: create `adverse_event_followup_visit` stub in `incomplete` with `scheduled_date: [target, target]`, `adverse_event_ids: [<this_ae_id>]`, `triggered_by: {type: "adverse_event", id: <this_ae_id>}`; store `stub_id` in `scheduled_followup_visit`
  - If clinical visit scheduled: same for `adverse_event_clinical_visit`
  - **Always** (regardless of `training_blocked`): if an `adverse_event_followup` stub already exists in `incomplete`, add this event's ID to its `adverse_event_ids` list. If no stub exists, seed a new one with `adverse_event_ids: [<this_event_id>]`, `scheduled_date: [today, today + 1 day]`
- Log message: `Adverse event filed`; if training blocked: also `Training paused — adverse event`; if visits scheduled: `Adverse event follow-up visit scheduled` / `Adverse event clinical visit scheduled`

---

### Robot Issue — Engineer Call (`robot_issue_call`)

- Trigger: `robot_issue_call` event row on patient detail — only appears when a stub exists in `incomplete`. Stubs are created directly by triggering modals (activation, home visit, patient call, follow-up call) when the "robot issue" toggle is checked. There is no intermediate `robot_issue` event.
- Allowed users: `admin`, `engineer`
- Experimental patients only
- Modal: `robot-issue-call-modal`
  - **Context banner** (read-only): "Robot issue reported during \<triggering event name\> on \<date\>"
  - Call Date/Time (datetime, required; cannot be in the future)
  - **Per device** (Pluto and Mars, each with a checkbox):
    - If checked, reveals inline sub-form:
      - **Outcome** (radio, required): Resolved by call / Visit required
      - **Notes** (textarea, required) — what was discussed for this device
  - **Overall notes** (textarea) — required if neither device checkbox is checked; optional otherwise
  - Attachment (optional PDF)
- **Visit required** is derived: if any checked device has outcome = `visit_required`, a `robot_issue_visit` stub is created. If no device is checked (general call), visit is never required.
- Server actions:
  - Remove the stub from `incomplete`
  - Append completed entry to `free.robot_issue_call` with `completion_date`, `filed_at`, `notes`, `devices` (per checked device: `device`, `outcome`, `notes`), `visit_required` (derived), `triggered_by`, `attachment`
  - If `visit_required`: create one `robot_issue_visit` stub in `incomplete` with `triggered_by: {type: "robot_issue_call", id: <event_id>}`, `scheduled_date: [now, now]`
- Log message: `Robot issue call recorded`; if visit required: also `Robot issue visit required`

---

### Robot Issue — Engineer Visit (`robot_issue_visit`)

- Trigger: `robot_issue_visit` event row on patient detail — only appears when a stub exists in `incomplete` (created when a robot issue call outcome is "visit required")
- Allowed users: `admin`, `engineer`
- Experimental patients only

#### Normal mode (patient is NOT `broken_protocol`)

- Modal: `robot-issue-visit-modal`
  - **Context banner** (read-only): "Robot issue call on \<date\>"
  - Visit Date/Time (datetime, required; cannot be in the future)
  - **Per device — both Pluto and Mars always shown.** The engineer must record an outcome for every device. If nothing was done for a device, select **Neither** and explain in notes.
    - Device name and current device ID (read-only labels)
    - **Outcome** (radio, required):
      - **Repaired on site** — device fixed during the visit; stays assigned; no inventory change:
        - Notes (textarea, required) — what was done
      - **Swapped** — device replaced on site:
        - New device (dropdown): available working devices + null ("No device available")
        - **Swap type** (radio, required): **Fault-driven** (device suspected/confirmed faulty) / **Preventive** (precautionary replacement, not necessarily faulty)
        - Notes (textarea, required)
      - **Neither (no action taken)** — nothing done for this device (not relevant to visit, or usage guidance only):
        - Notes (textarea, required) — explain why no action was taken
  - Additional notes (textarea, optional)
  - Attachment (optional PDF)
- Server actions:
  - Remove the stub from `incomplete`
  - For each device:
    - If **Repaired on site**: no assignment change, device not marked faulty; no fault report created (detail deferred to Devices page)
    - If **Swapped + fault-driven + new device selected**: close current assignment; mark old device faulty in inventory; open new assignment; create a pending fault report stub in `devices/fault_reports/<type>.json` (`resolution: null`, `swap_type: "fault_driven"`)
    - If **Swapped + fault-driven + null** (no replacement): close current assignment; mark old device faulty; no new assignment; set `trainingPausedDate`; create `resolve_robot_issue_visit` stub; create pending fault report stub
    - If **Swapped + preventive**: close current assignment; open new assignment if non-null; device NOT marked faulty; no fault report
    - If **Swapped + preventive + null**: close current assignment; no new assignment; set `trainingPausedDate`; create `resolve_robot_issue_visit` stub; device NOT marked faulty; no fault report
    - If **Neither**: no device change, no pause, no fault report
  - Append completed entry to `free.robot_issue_visit` with `completion_date`, `filed_at`, `device_outcomes` (per device: `device`, `outcome`, `swap_type`, `old_device_id`, `new_device_id`, `notes`), `notes`, `triggered_by`, `attachment`
- Log message: `Robot issue visit recorded`; if any device taken back with no replacement: also `Training paused — robot issue`

#### Broken-protocol mode (patient is `broken_protocol`)

The goal is to document which devices are faulty. No device swaps or assignment changes occur — assignments remain open until the patient is discontinued.

- Modal: same `robot-issue-visit-modal` but with a "Broken Protocol — Fault Documentation Only" banner
- Visit Date/Time (datetime, required; cannot be in the future)
- **Per device** (Pluto and Mars):
  - Device name and current device ID (read-only labels)
  - **Has fault** (checkbox)
  - If checked: Fault description (textarea, required)
- Additional notes (textarea, optional)
- Attachment (optional PDF)
- Server actions:
  - Remove the stub from `incomplete`
  - For each device where **Has fault** is checked: set `has_issue: true` in inventory; append a `faulty` device event
  - Device assignments are NOT closed (they stay open until discontinuation)
  - No pause mechanics (patient is already broken_protocol; `trainingPausedDate` is not modified)
  - Append completed entry to `free.robot_issue_visit` with `completion_date`, `filed_at`, `broken_protocol_mode: true`, `device_faults` (per faulted device: `device`, `notes`), `notes`, `triggered_by`, `attachment`
- Log message: `Robot issue visit recorded (broken protocol — fault documentation only)`

---

### Other Device Issue — Engineer Call (`other_device_issue_call`)

- Trigger: trigger toggle in primary training modals (activation, home_visit_d02/d03/d15, followup_call_d07/d21, patient_call). Toggle pre-checked and secondary outcome fields pre-set to "Visit Required" when created from the training-not-done "Other Device Issue" primary reason path.
- Allowed users: `admin`, `engineer`
- Experimental patients only
- Modal: `other-device-issue-call-modal`
  - **Context banner** (read-only): if triggered from a primary event, shows "Triggered by: \<event name\>"
  - **Issue First Occurred** (datetime, required; min = patient's `activationDate`; max = today) — when the issue was first noticed, distinct from the call date
  - Call Date/Time (datetime, required; min = issue_occur_date; max = today)
  - **Per device** (Modem, Laptop — each with a checkbox):
    - If checked, reveals inline sub-form:
      - **Outcome** (radio, required): Resolved over call / Visit required
      - **Notes** (textarea, required)
  - **Overall notes** (textarea, optional)
  - Attachment (optional PDF)
- **Visit required** is derived: if any checked device has outcome = `visit_required`, an `other_device_issue_visit` stub is created.
- Server actions:
  - Remove the stub from `incomplete`
  - For each checked device: set `has_issue: true` in inventory; append a `faulty` device event with `issue_occur_date`
  - For devices resolved over call: clear `has_issue: false` immediately
  - Append completed entry to `free.other_device_issue_call` with `completion_date`, `filed_at`, `issue_occur_date`, `notes`, `devices` (per device: `device`, `outcome`, `notes`), `visit_required` (derived), `triggered_by`, `attachment`
  - If `visit_required`: create one `other_device_issue_visit` stub in `incomplete` with `triggered_by: {type: "other_device_issue_call", id: <event_id>}`, `scheduled_date: [now, now]`
- Log message: `Other device issue call recorded`; if visit required: also `Other device issue visit required`

---

### Other Device Issue — Engineer Visit (`other_device_issue_visit`)

- Trigger: `other_device_issue_visit` event row on patient detail — only appears when a stub exists in `incomplete` (created when an other device issue call outcome is "visit required")
- Allowed users: `admin`, `engineer`
- Experimental patients only

#### Normal mode (patient is NOT `broken_protocol`)

- Modal: `other-device-issue-visit-modal`
  - **Context banner** (read-only): "Other device issue call on \<date\>"
  - Visit Date/Time (datetime, required; min = issue_occur_date from triggering call; max = today)
  - **Per device** (Modem, Laptop — both always shown; engineer records an outcome for every device):
    - Device name and current device ID (read-only labels)
    - **Outcome** (radio, required):
      - **Repaired** — device fixed; stays assigned; `has_issue` cleared; no inventory change
        - Notes (textarea, required)
      - **Replaced** — device swapped:
        - New device (dropdown): available devices of same type + null ("No device available")
        - Notes (textarea, required)
      - **Neither** — no action taken for this device:
        - Notes (textarea, required)
  - Additional notes (textarea, optional)
  - Attachment (optional PDF)
- Server actions:
  - Remove the stub from `incomplete`
  - For each device:
    - If **Repaired**: clear `has_issue: false` in inventory; append a `repaired` device event
    - If **Replaced + new device selected**: close current assignment; clear `has_issue` on old device; open new assignment for new device; append `faulty` and `assign` device events
    - If **Replaced + null**: close current assignment; clear `has_issue` on old device; no new assignment
    - If **Neither**: no device change
  - Append completed entry to `free.other_device_issue_visit` with `completion_date`, `filed_at`, `device_outcomes` (per device: `device`, `outcome`, `old_device_id`, `new_device_id`, `notes`), `notes`, `triggered_by`, `attachment`
  - Does NOT set `trainingPausedDate` (other device issues do not pause training)
- Log message: `Other device issue visit recorded`

#### Broken-protocol mode (patient is `broken_protocol`)

- Modal: same `other-device-issue-visit-modal` with "Broken Protocol — Fault Documentation Only" banner
- Visit Date/Time (datetime, required; max = today)
- **Per device** (Modem, Laptop):
  - **Has fault** (checkbox)
  - If checked: Fault description (textarea, required)
- Additional notes (textarea, optional)
- Attachment (optional PDF)
- Server actions:
  - Remove the stub from `incomplete`
  - For each faulted device: set `has_issue: true` in inventory; append a `faulty` device event
  - Device assignments are NOT closed (stay open until discontinuation)
  - Append completed entry to `free.other_device_issue_visit` with `completion_date`, `filed_at`, `broken_protocol_mode: true`, `device_faults`, `notes`, `triggered_by`, `attachment`
- Log message: `Other device issue visit recorded (broken protocol — fault documentation only)`

---

### Adverse Event Follow-up Call (`adverse_event_followup`)

- Trigger: `adverse_event_followup` event row on patient detail — only appears when a stub exists in `incomplete`
- Allowed users: `admin`, `therapist`
- Modal: `adverse-event-followup-modal`
  - **Context banner** (read-only): lists all adverse events covered by this follow-up (names + dates), derived from `adverse_event_ids`
  - **Patient initiated** (toggle, default off) — indicates that the patient contacted the clinic first (rather than the therapist initiating the call). When on, a **Related patient call** selector appears (required when toggle is on): dropdown of all `patient_call` entries for this patient where `ae_discussed: true`, shown as "DD Mon YYYY · HH:MM". Selecting one stores `related_patient_call_id`. The therapist should first log the patient call via the Patient Call modal, then open this follow-up.
  - Call Date/Time (datetime, required; cannot be in the future)
  - Duration (integer minutes, required; must be > 0)
  - Notes (textarea, optional) — general call-level notes
  - **Per adverse event** — one section per AE in `adverse_event_ids`:
    - AE name/date (read-only label)
    - **Discussion notes** (textarea, optional) — what was discussed about this AE during the call
    - **Resolved** (checkbox)
    - **Can resume from** (date, required if resolved AND that AE had `training_blocked: true`; hidden if training has permanently ended — i.e. `trainingCompletionDate`, `brokenProtocolDate`, or `discontinuationDate` is set, or status is `post_training`) — the earliest date training is possible again from this AE's perspective. Not applicable once training is over.
  - **Schedule follow-up visit** (optional toggle): when enabled, shows a target date/time input (required when toggle is on; cannot be in the past). If an `adverse_event_followup_visit` stub already exists that covers all current `adverse_event_ids`, this toggle is hidden (stub already scheduled)
  - **Schedule clinical visit** (optional toggle): when enabled, shows a target date/time input (required when toggle is on; cannot be in the past). Same hide-if-exists logic as above.
  - Attachment (optional PDF)
- Server actions:
  - Remove the stub from `incomplete` in `protocol_events.json`
  - Append completed entry to `free.adverse_event_followup` with `completion_date`, `filed_at`, `patient_initiated`, `related_patient_call_id` (if patient-initiated), `duration_minutes`, `notes`, `ae_discussions` (per-AE: `ae_id`, `notes`, `resolved`, `can_resume_from`), `scheduled_followup_visit`, `scheduled_clinical_visit` (both `null` if not scheduled), `triggered_by` (from stub), `attachment` (if uploaded)
  - If follow-up visit scheduled: create `adverse_event_followup_visit` stub in `incomplete` with `scheduled_date: [target, target]`, `adverse_event_ids: [<all AE IDs in this call>]`, `triggered_by: {type: "adverse_event_followup", id: <this_event_id>}`
  - If clinical visit scheduled: same for `adverse_event_clinical_visit`
  - If any AEs remain unresolved: seed next `adverse_event_followup` stub with `adverse_event_ids` = unresolved AE IDs, `scheduled_date: [today, today + 1 day]`
  - If all AEs resolved and no `resolve_robot_issue_visit` stubs remain in `incomplete` **and training has not permanently ended**: compute `max_resume = max(can_resume_from across all pausing AEs)`; increment `cumulativePauseDays` by `(max_resume − trainingPausedDate.date()).days` (minimum 0); clear `trainingPausedDate`; if `cumulativePauseDays` > 10, patient transitions to `broken_protocol`. **If training has permanently ended** (`trainingCompletionDate`, `brokenProtocolDate`, or `discontinuationDate` set): skip pause clearance entirely — `can_resume_from` is not collected and pause fields are not modified.
  - **D02/D03 broken protocol check (Path 3):** after pause clears, check if `max_resume > scheduled_date[1]` for `home_visit_d02` or `home_visit_d03` and those visits are still in `incomplete`. If so, the server returns a 409 with `broken_protocol_warning: true` and the affected day(s). The client shows the double confirmation popup. On re-submit with `confirmed_broken_protocol: true`, the server sets `brokenProtocolDate` and completes the follow-up.
  - If all AEs resolved but `resolve_robot_issue_visit` stubs still remain: no change to pause fields (robot issue still blocking)
- Log message: `Adverse event follow-up call recorded`; if visits scheduled: `AE follow-up visit scheduled` / `AE clinical visit scheduled`; if all resolved: also `Adverse event(s) resolved`

---

### Resolve Robot Issue — Replacement Visit (`resolve_robot_issue_visit`)

- Trigger: `resolve_robot_issue_visit` event row on patient detail — only appears when a stub exists in `incomplete` (created when a robot issue visit swaps a device with no replacement available)
- Allowed users: `admin`, `engineer`
- Experimental patients only

#### Normal mode (patient is NOT `broken_protocol`)

- Modal: `resolve-robot-issue-visit-modal`
  - **Context banner** (read-only): "Robot issue visit on \<date\> — device(s) taken back without replacement"
  - Visit Date/Time (datetime, required; cannot be in the future)
  - **Per taken-back device** (one row per device that was taken back without replacement — always required):
    - Device name + "taken back — no current assignment" (read-only label)
    - New device (dropdown): available working devices + null ("No device available")
    - Notes (textarea, required if null selected — explain why no replacement available)
    - If null selected: another `resolve_robot_issue_visit` stub is created on save
  - **Other device** (the device that was NOT taken back — optional section):
    - Checkbox: "Also attended to \<device name\> during this visit"
    - If checked, reveals full outcome sub-form identical to `robot_issue_visit`:
      - Current device ID (read-only)
      - **Outcome** (radio, required): Repaired on site / Swapped / Neither (no action taken)
        - Repaired: Notes (required)
        - Swapped: New device dropdown + **Swap type** (Fault-driven / Preventive) + Notes (required)
        - Neither: Notes (required)
  - **Can resume from** (date, required; cannot be in the future) — earliest date training is possible again
  - Additional notes (textarea, optional)
  - Attachment (optional PDF)
- Server actions:
  - Remove the stub from `incomplete`
  - For each taken-back device:
    - If new device selected: open new assignment; if `swap_type` was fault-driven on the original `robot_issue_visit`, update existing fault report stub with replacement info
    - If null again: create another `resolve_robot_issue_visit` stub
  - For the other device (if attended to): same per-device logic as `robot_issue_visit` server actions
  - Append completed entry to `free.resolve_robot_issue_visit` with `completion_date`, `filed_at`, `can_resume_from`, `device_replacements` (per taken-back device: `device`, `old_device_id`, `new_device_id`, `notes`), `other_device_outcomes` (per attended other device: same fields as `robot_issue_visit` `device_outcomes`), `notes`, `attachment`
  - If no `resolve_robot_issue_visit` stubs remain in `incomplete` AND no `adverse_event_followup` stubs remain: compute `cumulativePauseDays`; clear `trainingPausedDate`; if total > 10, patient transitions to `broken_protocol`
  - If `adverse_event_followup` stubs remain: no change to pause fields
- Log message: `Robot issue resolved — replacement device assigned`

#### Broken-protocol mode (patient is `broken_protocol`)

Same fault-documentation approach as `robot_issue_visit` broken-protocol mode. No replacement device assignment occurs.

- Modal: same `resolve-robot-issue-visit-modal` with "Broken Protocol — Fault Documentation Only" banner
- Visit Date/Time (datetime, required; cannot be in the future)
- **Per taken-back device**: Device name + fault description (textarea, required)
- **Other device** (optional): Checkbox "Also attended to \<device\>" — if checked, fault description only (no outcome options)
- Additional notes (textarea, optional)
- Attachment (optional PDF)
- Server actions:
  - Remove the stub from `incomplete`
  - For each taken-back device and any attended other device: set `has_issue: true` in inventory; append a `faulty` device event
  - Device assignments are NOT opened or closed (assignments remain as-is until discontinuation)
  - `can_resume_from` not collected; pause fields not modified (patient is already broken_protocol)
  - Append completed entry to `free.resolve_robot_issue_visit` with `completion_date`, `filed_at`, `broken_protocol_mode: true`, `device_faults`, `notes`, `attachment`
- Log message: `Robot issue visit recorded (broken protocol — fault documentation only)`

---

### Adverse Event Follow-up Visit (`adverse_event_followup_visit`)

- Trigger: `adverse_event_followup_visit` event row on patient detail — only appears when a stub exists in `incomplete`. Stubs are created by the File Adverse Event modal, the Adverse Event Follow-up Call modal, or any other Adverse Event Follow-up Visit or Clinical Visit modal when a new follow-up visit is scheduled.
- Allowed users: `admin`, `therapist`
- Cancellable: yes — a **Cancel Visit** button is shown in the modal footer. Clicking it prompts for a cancellation reason (textarea, required). Cancellation moves the stub to the top-level `cancelled` array in `protocol_events.json` with `cancelled_at` timestamp and `cancellation_reason`. No further stubs are created.
- Modal: `adverse-event-followup-visit-modal`
  - **Context banner** (read-only): lists all adverse events covered by this visit (aliases + dates), derived from `adverse_event_ids`
  - Visit start (datetime, required; cannot be in the future)
  - Visit end (datetime, required; must be same calendar date as start; must be after start)
  - **Per adverse event** — one section per AE in `adverse_event_ids`:
    - AE alias + date (read-only label, e.g. "AE02 — 2026-05-01")
    - **Discussion notes** (textarea, optional) — what was discussed / observed during this visit for this AE
    - **Resolved** (checkbox)
    - **Can resume from** (date, required if resolved AND that AE had `training_blocked: true`; hidden if training has permanently ended — same rule as `adverse_event_followup`)
  - Visit-level notes (textarea, optional)
  - **Schedule follow-up visit** (optional toggle): when enabled, shows a target date/time input (required when toggle is on; cannot be in the past). Hidden if an `adverse_event_followup_visit` stub already exists covering all current `adverse_event_ids`.
  - **Schedule clinical visit** (optional toggle): when enabled, shows a target date/time input (required when toggle is on; cannot be in the past). Hidden if an `adverse_event_clinical_visit` stub already exists covering all current `adverse_event_ids`.
  - Trigger toggles: Adverse Event, Robot Issue (experimental only), Watch Record — same as other follow-up modals
  - Attachment (optional PDF)
- Server actions:
  - Remove the stub from `incomplete`
  - Append completed entry to `free.adverse_event_followup_visit` with `completion_date` (= visit start), `filed_at`, `visit_start`, `visit_end`, `ae_discussions` (per-AE: `ae_id`, `notes`, `resolved`, `can_resume_from`), `notes`, `triggered_by` (from stub), `attachment` (if uploaded)
  - If follow-up visit scheduled: create `adverse_event_followup_visit` stub in `incomplete` with `scheduled_date: [target, target]`, `adverse_event_ids` = unresolved AE IDs, `triggered_by: {type: "adverse_event_followup_visit", id: <this_event_id>}`
  - If clinical visit scheduled: same for `adverse_event_clinical_visit`
  - If any AEs remain unresolved: seed next `adverse_event_followup` stub with `adverse_event_ids` = unresolved AE IDs, `scheduled_date: [today, today + 1 day]`
  - If all AEs resolved and no `resolve_robot_issue_visit` stubs remain in `incomplete`: clear pause (same logic as follow-up call, including training-permanently-ended skip)
- Log message: `Adverse event follow-up visit recorded`; if all resolved: also `Adverse event(s) resolved`

---

### Adverse Event Clinical Visit (`adverse_event_clinical_visit`)

- Trigger: `adverse_event_clinical_visit` event row on patient detail — only appears when a stub exists in `incomplete`. Stubs are created by the File Adverse Event modal, the Adverse Event Follow-up Call modal, or any other Adverse Event Follow-up Visit or Clinical Visit modal when a new clinical visit is scheduled.
- Allowed users: `admin`, `therapist`
- Cancellable: yes — same cancellation behaviour as `adverse_event_followup_visit` (reason required, stored as `cancellation_reason`)
- Modal: `adverse-event-clinical-visit-modal`
  - **Context banner** (read-only): lists all adverse events covered by this visit (aliases + dates), derived from `adverse_event_ids`
  - Visit start (datetime, required; cannot be in the future)
  - Visit end (datetime, required; same calendar date; after start)
  - **Per adverse event** — one section per AE in `adverse_event_ids`:
    - AE alias + date (read-only label, e.g. "AE02 — 2026-05-01")
    - **Discussion notes** (textarea, optional) — notes from the consultant / therapist discussion about this AE
    - **Resolved** (checkbox)
    - **Can resume from** (date, required if resolved AND that AE had `training_blocked: true`; hidden if training has permanently ended — same rule as `adverse_event_followup`)
  - Visit-level notes (textarea, optional)
  - **Schedule follow-up visit** (optional toggle): when enabled, shows a target date/time input (required when toggle is on; cannot be in the past). Hidden if an `adverse_event_followup_visit` stub already exists covering all current `adverse_event_ids`.
  - **Schedule clinical visit** (optional toggle): when enabled, shows a target date/time input (required when toggle is on; cannot be in the past). Hidden if an `adverse_event_clinical_visit` stub already exists covering all current `adverse_event_ids`.
  - Trigger toggles: Adverse Event, Robot Issue (experimental only), Watch Record — same as other follow-up modals
  - Attachment (optional PDF)
- Server actions:
  - Remove the stub from `incomplete`
  - Append completed entry to `free.adverse_event_clinical_visit` with `completion_date` (= visit start), `filed_at`, `visit_start`, `visit_end`, `ae_discussions` (per-AE: `ae_id`, `notes`, `resolved`, `can_resume_from`), `notes`, `triggered_by` (from stub), `attachment` (if uploaded)
  - If follow-up visit scheduled: create `adverse_event_followup_visit` stub in `incomplete` with `scheduled_date: [target, target]`, `adverse_event_ids` = unresolved AE IDs, `triggered_by: {type: "adverse_event_clinical_visit", id: <this_event_id>}`
  - If clinical visit scheduled: same for `adverse_event_clinical_visit`
  - If any AEs remain unresolved: seed next `adverse_event_followup` stub with `adverse_event_ids` = unresolved AE IDs, `scheduled_date: [today, today + 1 day]`
  - If all AEs resolved and no `resolve_robot_issue_visit` stubs remain: clear pause (same logic)
- Log message: `Adverse event clinical visit recorded`; if all resolved: also `Adverse event(s) resolved`

---

### Watch Record (`watch_record`)

- Trigger:
  - `watch_record` event row on patient detail — covers three cases:
    1. **Activation-seeded**: first entry, seeded at activation with `triggered_by = {type: "activation", ...}` and `scheduled_date = [activationDate, activationDate]`; immediately overdue
    2. **Call-claimed**: existing open chain entry claimed by a patient call or follow-up call; `triggered_by` and `scheduled_date = [now, now]` stamped at call-save time; immediately overdue
    3. **Chain follow-up**: open entry seeded at completion of previous watch record; `scheduled_date` computed from `next_followup_days`
  - "Log Watch Record" button on the Watch Records tab (standalone, user-initiated — creates a new entry)
- Allowed users: `admin`, `engineer`
- Modal: `watch-record-modal` (shared across all trigger paths)
  - **Context banner** (read-only, top of modal):
    - If `triggered_by.type = "activation"`: "Triggered by: Patient Activation"
    - If `triggered_by.type` is a call: "Triggered by: \<call event name\>"
    - If no `triggered_by`: "Scheduled chain follow-up"
  - **Current watches** (read-only display, one row per limb):
    - Right: watch ID (or "Not assigned" if null) + **Lost** checkbox — checkbox only shown when `old_id` is not null
    - Left: same
    - These become `old_id` and `old_lost` in the saved record
  - AG Watch Right — new assignment (dropdown: active, unassigned, non-lost watches from inventory + **"No Watch Available"** option; required). Selecting "No Watch Available" sets `ag_watch_right.new_id` to `null`.
  - AG Watch Left — new assignment (dropdown — same options; required).
  - Sync date & time (datetime; cannot be in the future) — when the watches were synced / data downloaded. **Required if at least one new watch is assigned; omitted when both are "No Watch Available".**
  - Worn date & time (datetime; cannot be in the future) — when the patient put the watches on. Same requirement as Sync.
  - Next follow-up in N days (integer input, required; must be ≥ 1) — determines when the next chain entry is scheduled
  - Notes (textarea) — **required if either new watch is "No Watch Available"**; optional otherwise
- Server actions:
  - Move `watch_record` entry from `incomplete` to `complete` in `protocol_events.json`, adding `completion_date`, `filed_at`, `ag_watch_right: {old_id, old_lost, new_id}`, `ag_watch_left: {old_id, old_lost, new_id}`, `sync_datetime`, `worn_datetime`, `next_followup_days`, `notes`; `triggered_by` already present if entry was claimed
  - Update `agWatchRightID` and `agWatchLeftID` in `<homer_id>.json`
  - For each limb: close the existing open assignment record (`returned_date = completion_date`); if `old_lost: true`, also set `lost: true` on that assignment record and set `lost_date` on the inventory record
  - For each new watch assigned: append a new assignment record to `devices/assignments/agwatch.json`; write device log `Assigned to <homer_id> (<limb>)` to `devices/logs/agwatch/<watch_id>.log`
  - For each lost watch: write device log `Lost — reported by <homer_id>` to `devices/logs/agwatch/<watch_id>.log`
  - Seed next `watch_record` entry in `incomplete` with `scheduled_date = [completion_date + next_followup_days, completion_date + next_followup_days]`
- Log message: `Watch record filed`

---

### AG Watch Data Upload (`watch_data_upload`)

Engineer event to pull and upload the raw ActiGraph data file (`.gt3x`) from a watch each time it is physically removed from a patient. **One task per removed watch.** Auto-seeded — there is no "add" button.

- **Trigger:** `watch_data_upload` event row on patient detail (also surfaced on the Watch Records tab). Auto-seeded when a watch is **removed and recoverable**:
  - **From `watch_record`:** for each limb where `old_id` is present, `old_id != new_id` (normal swap, or removal-to-gap with `new_id` null), and `old_lost` is **false**. One stub per such limb. Lost watches are never seeded — there is no device to pull data from.
  - **From `device_return`:** for each watch returned at end of training whose status is **not** lost. One stub per returned watch. *(device_return is step 19b — the seeding hook is wired when that event is built.)*
- **Allowed users:** `admin`, `engineer`
- **Display name:** the event row name embeds the limb and watch id so the right/left tasks are distinguishable when a single swap removes both watches — e.g. **"AG Watch Data Upload — Right (WOLD1)"**. Computed per-entry in both event APIs (helper `_wdu_event_name`, mirrored in `routes/user_management.py` and `routes/dashboard.py`), the same way AE follow-up rows embed their AE aliases.
- **Stub fields** (in `incomplete`, before fill):
  - `triggered_by`: `{ type: "watch_record" | "device_return", id: <uuid of triggering entry> }`
  - `watch_id`: the removed watch's device ID
  - `limb`: `"right" | "left"`
  - `removed_date`: triggering event's `completion_date` (`YYYY-MM-DDTHH:MM`)
  - `data_start` / `data_end`: the watch's assignment window for this patient (`assigned_date` → `removed_date`), derived from the assignment record — shows the engineer the expected data range
  - `scheduled_date`: `[removed_date, removed_date]` — surfaces immediately as actionable
  - The triggering entry stores the reverse reference: `triggered: [{ type: "watch_data_upload", id }]`
- **Modal:** `watch-data-upload-modal`
  - **Context banner** (read-only): watch ID, limb, removed date, expected data range (`data_start` → `data_end`)
  - **Data file** (file input, `.gt3x` only) — the raw ActiGraph file. **Uploads immediately on select** (see upload flow below): a progress bar shows 0–100%, and **Save stays disabled until the upload completes**. No engineer-entered date — the `.gt3x` is self-describing and the meaningful window is `data_start` → `data_end`; the htDash upload time is `filed_at`.
  - **Skip toggle: "Data could not be retrieved"** — when checked, the file input + progress are hidden, a **detailed reason is required** in Notes, and Save becomes enabled; when unchecked, the `.gt3x` upload must complete before Save enables
  - **Notes** (textarea) — optional when a file is uploaded; **required and detailed when the skip toggle is checked**
- **Save-button gating:** Save opens **disabled**. It enables only when `uploaded || skip` — i.e. the `.gt3x` has finished uploading, or the skip toggle is checked.
- **Two-step upload:**
  - `POST /api/patients/<homer_id>/upload-watch-data` (multipart; engineer/admin) fires on file-select. Validates the file is `.gt3x` and that an open `watch_data_upload` stub with that `event_id` exists, stores it at `actigraphs/<event_id>.gt3x` (idempotent), returns `{ok, original_filename}`. The client uses `XMLHttpRequest` (`upload.onprogress`) to drive the progress bar — `fetch` can't report upload progress.
  - `POST …/complete-event/watch-data-upload` is then a **JSON** call (no file) — see server actions.
- **Validation** (client + server, identical rules):
  - Not skipped → the staged `.gt3x` must exist (server verifies via `s3_key_exists` / `path.exists`)
  - Skipped → a non-empty reason (Notes) is required
- **Server actions** (complete call):
  - Not skipped: verify the staged `actigraphs/<event_id>.gt3x` exists; record `data_file`, `original_filename`
  - Skipped: best-effort delete any staged file (local); `data_file`/`original_filename` = `null`
  - `completion_date` = `filed_at[:16]` in both cases (the htDash upload/completion time)
  - Move the `watch_data_upload` entry from `incomplete` to `free.watch_data_upload`, adding `filed_at`, `filed_by`, `skipped` (bool), `notes`
  - Write device log `AG watch data uploaded` / `AG watch data upload skipped` to the watch's log
- **Download:** the uploaded `.gt3x` is downloadable by `admin`, `therapist`, and `engineer` — note this is a **deliberate exception** to the "admin/therapist only" attachment rule (engineers may download watch data). Surfaced on the Watch Records tab and the Timeline row. Endpoint: `GET /api/patients/<homer_id>/watch-data/<event_id>`
- **Visibility:** included in `_BROKEN_PROTOCOL_INTERACTIVE`, `_DISCONTINUED_VISIBLE`, and `_PAUSE_VISIBLE` — the data must never be lost and engineer work does not pause
- Log message: `AG watch data uploaded` (or `AG watch data upload skipped`)

---

## Future Requirements

### Device Repair (Devices page — not yet implemented)

**Context:** When a robot issue causes a training pause but the patient completes training (day 29) before the `resolve_robot_issue_visit` stub is filled, the stub is auto-discarded (robot is returned on day 29). However, the device may still be physically faulty — it has not been repaired and cannot be safely assigned to a new patient.

**Required feature:** A **"Repair Device"** action in the Devices page, available to `engineer` and `admin`, that:

- Lists Pluto/Mars devices flagged as faulty (i.e. their last robot issue was not formally resolved before training completion)
- Allows the engineer to record:
  - Repair date
  - Description of repair / action taken
  - Outcome: `repaired` | `condemned` (beyond repair, permanently retired)
- On save: clears the faulty flag on the device inventory record; if `condemned`, marks the device as inactive so it can never be assigned again
- Log message written to the device log

This ensures the device inventory accurately reflects availability for new patient assignments, independent of the patient protocol lifecycle.

### Fault Report Classification (Devices page — not yet implemented)

**Context:** When a device is swapped with `swap_type: "fault_driven"` in `robot_issue_visit` or `resolve_robot_issue_visit`, a pending fault report stub is created in `devices/fault_reports/<type>.json` with `resolution: null`. The engineer needs to complete this report when they have had time to diagnose the fault.

**Required feature:** A **"Complete Fault Report"** action in the Devices page, available to `engineer` and `admin`, that:

- Lists all pending fault report stubs (where `resolution: null`)
- For each stub, allows the engineer to record:
  - Fault description — what was wrong with the device
  - Action taken — what was done (repaired, parts replaced, etc.)
  - Outcome: `repaired` | `condemned` (beyond repair)
- On save: fills `resolution` on the stub; if `condemned`, marks the device as permanently inactive
- Log message written to the device log

**Note:** Swaps with `swap_type: "preventive"` do not create fault report stubs — the device is not considered faulty and can be reassigned immediately.

### Adverse Event Amendment (Future)

**Context:** Once an adverse event is filed, the description and action taken are locked. There is currently no way to correct a clerical error.

**Required feature:** An **"Amend"** action on each AE card in the Adverse Events tab, available to `admin` only, that:

- Opens a small modal with editable description and action taken fields pre-filled
- Requires an amendment reason (textarea, required)
- On save: updates the record in `free.adverse_event` and appends an `amendments` list entry recording the original values, the reason, and the amendment timestamp
- Log message: `Adverse event amended — <ae_id>`

## D01–D03 Broken Protocol Detection & Auto-Shift on Resume

> **Status: ✅ Implemented.**

### Background

The first three consecutive training days (D01 = activation, D02, D03) are a critical uninterrupted block. If any of these days is missed due to a training-blocking AE or robot issue, the patient cannot be counted in the study. The `training_blocked` flag continues to live in the "File AE" modal as it does today — home visit modals are not changed.

When training pauses, all non-AE/RI events are frozen in the upcoming section with an "On hold" badge — they never move to overdue. Only AE/RI follow-up stubs appear as overdue. The system detects when the D02/D03 window passes while still paused and alerts the therapist via the at-risk banner.

---

### Scenario summary

| Day | Situation | Training done? | Outcome |
|---|---|---|---|
| D01 | AE/RI before training | No | Activation never filed → existing activation window expiry rule → broken protocol |
| D01 | AE/RI after training | Yes | Normal pause flow (`trainingPausedDate` set) |
| D02 | Pause from D01 not resolved by D02 | No | Broken protocol |
| D02 | Pause from D01 resolves but D02 not filed | No | Broken protocol |
| D02 | AE/RI before training | No | Normal pause → broken protocol (D02 window passes while paused) |
| D02 | AE/RI after training | Yes | Normal pause flow |
| D03 | Pause from D02 not resolved by D03 | No | Broken protocol |
| D03 | Pause from D02 resolves but D03 not filed | No | Broken protocol |
| D03 | AE/RI before training | No | Normal pause → broken protocol (D03 window passes while paused) |
| D03 | AE/RI after training | Yes | Normal pause flow |

---

### Rule 1 — Broken protocol check inside pause-clearing routes

Implemented in `_clear_ae_pause_if_resolved()` and the two inline pause-clearing blocks in `routes/user_management.py`.

When a pause clears, `_check_d0203_broken_protocol(events_data, max_resume)` is called before writing the updated patient meta. If D02 or D03 is not in `complete` and its `scheduled_date[1]` is before `max_resume` (the date training can resume), `brokenProtocolDate` is set. The pause is still cleared — `derive_status()` reads `brokenProtocolDate` first and returns `broken_protocol` regardless of `trainingPausedDate`.

This catches: pause resolves but the D02/D03 window already passed before training could resume.

---

### Rule 2 — Dashboard live check for currently-paused patients

In `routes/dashboard.py`, the per-patient loop gains a live check for `paused` patients: if D02 or D03 is not in `complete` and its `scheduled_date[1]` < today, a `discontinuation_reminder` is injected immediately (without waiting for the pause to be cleared).

This catches: pause still ongoing when D02/D03 window expires — the dashboard flags it proactively.

Note: this check does **not** write `brokenProtocolDate` to disk (no side-effects from a GET endpoint). `brokenProtocolDate` is set when the pause is eventually cleared via Rule 1.

---

### Rule 3 — D02/D03 at-risk banner

Implemented via `_checkD0203AtRisk(p)` in `static/js/app/patient_detail.js`, called on every `loadPatientEvents()` refresh.

When a patient is paused and D02 or D03's window has passed (derived client-side from `activationDate + 1d` / `activationDate + 2d`), an orange banner appears on the overview tab above the pause banner. Message: *"Training at risk — Day 2/3 home visit window has passed while training is paused. Broken protocol will be flagged when the pause is cleared."* Banner clears when the condition no longer holds.

---

### Rule 4 — Auto-shift all future events on resume

Implemented via `_shift_future_incomplete_events(events_data, pause_days)` in `routes/user_management.py`, called at all three pause-clearing sites immediately after `trainingPausedDate` is cleared.

**Shift logic:**
- For every entry in `incomplete` with a non-null `scheduled_date [start, end]`: add `pause_days` calendar days to both elements.
- `pause_days` = `max(can_resume_from across all pausing AEs/RIs)` − `trainingPausedDate`.
- Applied server-side at the moment `trainingPausedDate` is cleared (same write as `cumulativePauseDays` update).
- Free events (null `scheduled_date`) and already-completed events are not touched.
- If broken protocol was set (Rule 1), the shift still runs — the shifted dates don't matter for a broken-protocol patient, but it keeps the data consistent.
