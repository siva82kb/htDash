# AE / Robot Issue Logic

This document is the single source of truth for all adverse event and robot issue logic in htDash — stub creation, follow-up chains, training pause mechanics, broken protocol detection, and selective rescheduling on resume.

---

## Table of Contents

0. [Protocol Clock — Fundamental Rules](#0-protocol-clock--fundamental-rules)
1. [AE Identification — UUID and Alias](#1-ae-identification--uuid-and-alias)
2. [Adverse Event — Two-Phase Model](#2-adverse-event--two-phase-model)
3. [AE Follow-up Chain](#3-ae-follow-up-chain)
4. [ae_discussions Structure](#4-ae_discussions-structure)
5. [Robot Issue Chain](#5-robot-issue-chain)
6. [Training Pause — AE-Caused](#6-training-pause--ae-caused)
7. [Training Pause — Robot Issue-Caused](#7-training-pause--robot-issue-caused)
8. [Pause Clearing — Combined Logic](#8-pause-clearing--combined-logic)
9. [D01–D03 Broken Protocol Detection](#9-d01d03-broken-protocol-detection)
10. [Selective Rescheduling on Resume](#10-selective-rescheduling-on-resume)
11. [pauseHistory Structure](#11-pausehistory-structure)
12. [Event Visibility When Paused](#12-event-visibility-when-paused)
13. [Event Visibility When Broken Protocol](#13-event-visibility-when-broken-protocol)
14. [AE Trigger Cutoff Rules](#14-ae-trigger-cutoff-rules)
15. [Post-Day 28 Rules](#15-post-day-28-rules)
16. [D29 / A1 / A2 Special Handling](#16-d29--a1--a2-special-handling)
17. [Code Locations](#17-code-locations)

---

## 0. Protocol Clock — Fundamental Rules

The protocol clock is **absolute**. It starts on the activation date (Day 1) and ends on Day 28. Nothing moves the clock — not pauses, not missed events, not rescheduled visits. All event windows are fixed calendar dates derived from `activationDate`.

**Consequences:**

- D02 and D03 home visits are non-negotiable. If a pause overlaps their day, they are simply missed — broken protocol fires. They are never rescheduled.
- `scheduled_date` values are **immutable**. No event's window ever moves due to a pause. Events that were On Hold during a pause simply become overdue after it clears — the therapist completes them whenever possible, and `completion_date` records when it actually happened.
- The only active write on pause-clear is cancelling `followup_call_d21` if training cannot resume before Day 28 ends. See Section 10.
- All other events — D07, D15, D29, A1, A2, prescription events, agwatch timing, watch records — stay at their absolute protocol positions regardless of pausing.
- The intervention ends at Day 28. Pause state is terminated at that boundary. D29 is outside the intervention window.

### User-input-driven state changes

**The system makes state changes only in response to explicit user input. The system clock is used for display only (overdue/upcoming labels, day counters). No background jobs, no automatic state transitions.**

The single exception is **activation expiry**: `derive_status()` reads today's date to detect when the activation window has lapsed (today > enrollment + 5 days AND activation still incomplete). This clock-based check is intentional and unavoidable — activation is a true hard cutoff. All other state changes (`brokenProtocolDate`, `trainingPausedDate`, `discontinuationDate`, `cumulativePauseDays`) are written exclusively when a user submits a form.

**Why this matters:** therapists sometimes enter data retroactively with accurate past dates. If the system reacted to the system clock rather than entered dates, it would produce wrong state transitions for retroactively entered data. Entered `completion_date` values are the authoritative record of what happened and when.

---

## 1. AE Identification — UUID and Alias

Every adverse event has two identifiers:

### UUID

The `id` field on the completed `adverse_event` entry (a `uuid4` string). This is the **persistent, machine-readable key** used throughout the system:
- Stored in `free.adverse_event[]` in `protocol_events.json`.
- Referenced by `ae_discussions[*].adverse_event_id` on follow-up entries.
- Referenced by `triggered` / `triggered_by` cross-links.
- Used as the event attachment filename (`attachments/<uuid>.pdf`).

UUIDs are assigned at Phase 1 (stub creation) and never change.

### Alias (AExx)

A **stable human-readable label** assigned **server-side** when the AE is filed (Phase 2) and **stored in `protocol_events.json`**. Aliases are the primary title shown anywhere an AE is displayed — never the generic string "Adverse Event".

| Rule | Detail |
|---|---|
| Format | `AE01`, `AE02`, … (zero-padded to two digits) |
| Assignment | At Phase 2 filing: count existing entries in `free.adverse_event` at that moment (before appending the new one); alias = `AE{count + 1:02d}` |
| Scope | Per-patient — each patient's AEs are numbered independently |
| Stored on | The completed `adverse_event` entry in `free.adverse_event[]` as the `alias` field |
| Stability | Immutable once assigned — never recomputed or reassigned |

**Where aliases appear:**
- Adverse Events tab — card header (`AE01 · Ongoing`)
- Follow-up history rows — "for AE01, AE02" labels derived from `ae_discussions[*].adverse_event_id` → look up alias from the stored entry
- Timeline tab — event row title
- Dashboard events panel — event row title (resolved via a lookup by ID)

**JSON fragment (completed adverse_event entry):**
```json
{
  "id": "<uuid>",
  "alias": "AE02",
  "protocol_event_id": "adverse_event",
  ...
}
```

---

## 2. Adverse Event — Two-Phase Model

An AE is created in two phases.

**Filing cutoff:** AEs can be triggered from enrollment through the end of training. After training permanently ends, AE trigger toggles are hidden in primary training modals. Within an active AE follow-up chain, AE triggers remain available until all AEs are resolved. See Section 14 for the precise cutoff rules.

### Phase 1 — Trigger (in the triggering modal)

Triggered from: `activation`, `activation_attempt`, `home_visit_d02`, `home_visit_d03`, `home_visit_d15`, `d15_attempt`, `patient_call`, `followup_call_d07`, `followup_call_d21`, `adverse_event_followup`, `adverse_event_followup_visit`, `adverse_event_clinical_visit`.

When the "Adverse event" toggle is checked, saving the triggering modal:
- Appends a **stub** to `incomplete` in `protocol_events.json`:
  ```json
  {
    "id": "<uuid>",
    "protocol_event_id": "adverse_event",
    "scheduled_date": ["<now>", "<now>"],
    "triggered_by": { "type": "<triggering_event_type>", "id": "<triggering_event_id>" }
  }
  ```
- Stores `{ "type": "adverse_event", "id": "<stub_id>" }` in the triggering event's `triggered` list.
- The stub appears immediately as overdue.

### Phase 2 — Complete (via File Adverse Event modal)

The therapist opens the `adverse_event` stub row, fills in description, action taken, and whether training is blocked.

- Stub is removed from `incomplete`.
- Completed entry appended to `free.adverse_event`:
  ```json
  {
    "id": "<uuid>",
    "alias": "AE01",
    "protocol_event_id": "adverse_event",
    "completion_date": "<datetime>",
    "filed_at": "<datetime>",
    "description": "...",
    "action_taken": "...",
    "training_blocked": true/false,
    "triggered_by": { "type": "...", "id": "..." },
    "scheduled_followup_visit": "<datetime or null>",
    "scheduled_clinical_visit": "<datetime or null>",
    "attachment": "attachments/<event_id>.pdf or null"
  }
  ```
- `alias` is assigned by the server at this point: `len(free.adverse_event)` before appending gives the 0-based index; alias = `f"AE{index + 1:02d}"`.
- The `training_blocked` checkbox is **only shown in the AE modal when the patient has a valid `activationDate`**. For pre-activation AEs (triggered from an activation attempt), the checkbox is hidden and `training_blocked` is always stored as `false`.
- If `training_blocked`: set `trainingPausedDate` on patient JSON; append a new open entry to `pauseHistory`.
- If follow-up visit scheduled: create `adverse_event_followup_visit` stub in `incomplete`.
- If clinical visit scheduled: create `adverse_event_clinical_visit` stub in `incomplete`.
- **Always** seed or update the `adverse_event_followup` stub (see Section 3).

---

## 3. AE Follow-up Chain

A single `adverse_event_followup` stub exists at a time in `incomplete`. It carries `adverse_event_ids` — a list of **UUIDs** of all currently unresolved AEs. Wherever this list is shown to therapists (modal header, event row), each UUID is resolved to its stored `alias` (e.g. `AE01`, `AE03`) — UUIDs are never displayed directly.

### Seeding rules

| Situation | Action |
|---|---|
| New AE filed, no existing stub | Create new stub: `adverse_event_ids: [<new_ae_uuid>]`, `scheduled_date: [today, today + 1 day]` |
| New AE filed, stub already exists | Append `<new_ae_uuid>` to existing stub's `adverse_event_ids` |
| Follow-up completed, AEs remain unresolved | Seed new stub with UUIDs of unresolved AEs, `scheduled_date: [today, today + 1 day]` |
| Follow-up completed, all AEs resolved | No new stub; attempt pause clear (see Section 8) |

**Display:** UUIDs in `adverse_event_ids` are resolved to aliases at display time by looking up `alias` on each matching `free.adverse_event` entry. Concrete format:

| Location | Format |
|---|---|
| Event row (patient detail + dashboard) | `Follow-up: AE01, AE03` |
| Modal title | `Adverse Event Follow-up — AE01, AE03` |

### Follow-up event types

All three follow-up types carry `adverse_event_ids` and the `ae_discussions` field (see Section 4):

| Event type | Stub creator | Can schedule new visit | Can schedule new clinical visit | Cancellable |
|---|---|---|---|---|
| `adverse_event_followup` | Auto-seeded whenever any AE is unresolved | Yes | Yes | No |
| `adverse_event_followup_visit` | Any follow-up modal or File AE modal | Yes | Yes | Yes |
| `adverse_event_clinical_visit` | Any follow-up modal or File AE modal | Yes | Yes | Yes |

**Call stub always present:** as long as any AE remains unresolved, a new `adverse_event_followup` call stub is re-seeded after every completed follow-up interaction. There is no state in which unresolved AEs exist but no call stub is available — the call is always an option.

**Visit and clinical visit scheduling:** all three modal types include scheduling toggles for a new follow-up visit and/or a new clinical visit. The therapist schedules the next contact while the patient is still present (in person or on the phone), not after the fact.

**Cancellable stubs:** the modal shows a Cancel Visit button. Cancellation requires a `cancellation_reason` (textarea, required). The stub is moved to the top-level `cancelled` array in `protocol_events.json` with `cancelled_at` and `cancellation_reason`. No further stubs are auto-created by cancellation.

### New events reported during follow-up interactions

A patient may report a **new AE or robot issue** during a follow-up call, visit, or clinical visit. These follow-up modals include the same trigger toggles as primary event modals — subject to the AE trigger cutoff rules in Section 14.

**Key ordering rule:** any new AE/RI stub is created at save time, **before** the follow-up event is completed and before the next `adverse_event_followup` stub is seeded. The new AE ID is therefore picked up automatically by the follow-up chain seeding logic — it will appear in the **next** `adverse_event_followup` stub, not in the current one being completed.

| Trigger | Behaviour |
|---|---|
| New AE toggle checked | Creates AE stub in `incomplete` immediately; its ID enters the *next* follow-up stub |
| RI toggle checked (experimental only) | Creates `robot_issue_call` stub in `incomplete` immediately |
| Watch record toggle | Claims the existing open chain entry (see watch record section in CLAUDE.md) |

`training_blocked` on a new AE filed during a follow-up is handled identically to the primary path: sets `trainingPausedDate` if transitioning from null, or appends to the open `pauseHistory` epoch's `reasons` list.

### patient_initiated toggle

On `adverse_event_followup` modals: when the patient contacted the clinic first, the therapist should first log a `patient_call` (with `ae_discussed: true`), then open this follow-up. Setting `patient_initiated: true` reveals a **Related patient call** selector (required — dropdown of `patient_call` entries where `ae_discussed: true`). Stored as `related_patient_call_id` on the completed follow-up record.

---

## 4. ae_discussions Structure

`ae_discussions` is the per-AE outcome field stored on every completed follow-up event. Each entry:

```json
{
  "adverse_event_id": "<uuid of the adverse_event entry>",
  "notes": "what was discussed for this AE",
  "resolved": true/false,
  "can_resume_from": "YYYY-MM-DD or null"
}
```

**Rules:**
- Present on: `adverse_event_followup`, `adverse_event_followup_visit`, `adverse_event_clinical_visit`.
- `adverse_event_id` stores the UUID for internal linking. The modal renders each row with the corresponding `alias` (e.g. "AE02") as the row heading — never the raw UUID.
- `can_resume_from` is required (date only) when `resolved: true` AND the original AE had `training_blocked: true`. Hidden otherwise.
- Used by pause-clearing logic: `max(can_resume_from across all resolved pausing AEs)` determines the effective resume date.

---

## 5. Robot Issue Chain

Robot issues are engineer-owned and experimental-only. The chain starts directly at `robot_issue_call` — there is no intermediate `robot_issue` event.

```
robot_issue_call
  └─► (if visit needed) robot_issue_visit
        └─► (if device taken back without replacement) resolve_robot_issue_visit
              └─► (if still no replacement) another resolve_robot_issue_visit stub
```

### robot_issue_call

- Created by triggering modals (same set as AE triggers: `activation`, `home_visit_d02`, `home_visit_d03`, `home_visit_d15`, `patient_call`, `followup_call_d07`, `followup_call_d21`, `adverse_event_followup`, `adverse_event_followup_visit`, `adverse_event_clinical_visit`) when the "robot issue" toggle is checked.
- Stub appended to `incomplete` with `scheduled_date: [now, now]` and `triggered_by`.
- Completed by engineer: records call date, per-device outcomes (`resolved_over_call` / `visit_required`), notes.
- If any device has `visit_required`: auto-create one `robot_issue_visit` stub.

### robot_issue_visit

- Records what happened during the visit for both Pluto and Mars (outcome required for every device).
- Per-device outcomes:
  - **Repaired on site** — device stays assigned; no inventory change; no fault report.
  - **Swapped + fault-driven** — old device marked faulty; new assignment if replacement available; fault report stub created.
  - **Swapped + preventive** — no faulty flag; no fault report.
  - **Neither** — no change.
- If any device is taken back **without a replacement** (`new_device_id: null`): set `trainingPausedDate`; create `resolve_robot_issue_visit` stub.

### swap_type

| Value | Meaning | Old device marked faulty | Fault report stub created |
|---|---|---|---|
| `fault_driven` | Device suspected/confirmed faulty | Yes | Yes |
| `preventive` | Precautionary replacement | No | No |

### resolve_robot_issue_visit

- Created when a device is taken back with no replacement (from `robot_issue_visit` or a previous `resolve_robot_issue_visit`).
- Records delivery of replacement device(s) plus optional "other device" outcome.
- If replacement still unavailable: another `resolve_robot_issue_visit` stub is created.
- Records `can_resume_from` — used in pause-clearing formula.
- When no `resolve_robot_issue_visit` stubs remain AND no `adverse_event_followup` stubs remain: attempt pause clear.

### robot_fault_report stubs

Stored in `devices/<type>/faultReport.json` (one file per type). Created only for `fault_driven` swaps. Fields: `device_id`, `swap_event_id`, `created_at`, `resolution: null`. Completed via Devices page "Complete Fault Report" action (not yet implemented). `repaired_on_site` outcomes do **not** create fault report stubs.

---

## 6. Training Pause — AE-Caused

| Field | Set when | Cleared when |
|---|---|---|
| `trainingPausedDate` | `training_blocked: true` on `adverse_event` completion | All pausing AEs resolved + no `resolve_robot_issue_visit` stubs remain |
| `pauseHistory` | Same — new open epoch appended | Epoch closed (`end`, `days`, `end_event_id` filled) |

`trainingPausedDate` is not set if the AE did not have `training_blocked: true`. An AE can be filed and followed up without ever pausing training.

---

## 7. Training Pause — Robot Issue-Caused

| Field | Set when | Cleared when |
|---|---|---|
| `trainingPausedDate` | Device taken back with no replacement in `robot_issue_visit` or `resolve_robot_issue_visit` | All `resolve_robot_issue_visit` stubs resolved + no `adverse_event_followup` stubs remain |

Training only pauses when a patient is **left without a device**. A repaired or swapped device does not pause training.

---

## 8. Pause Clearing — Combined Logic

Pause clears when **both** conditions are true:
1. No `resolve_robot_issue_visit` stubs remain in `incomplete`
2. No `adverse_event_followup` stubs remain in `incomplete` (i.e., all AEs resolved)

### Formula

```python
training_paused = date.fromisoformat(patient_meta['trainingPausedDate'])
max_resume = max(
    can_resume_from values from all resolved pausing AEs in ae_discussions,
    can_resume_from values from all completed resolve_robot_issue_visit entries
)
pause_days = max(0, (max_resume - training_paused).days)
```

### Actions on clear

1. `cumulativePauseDays += pause_days`
2. Close open `pauseHistory` epoch: set `end`, `days = pause_days`, `end_event_id = <completing_event_id>`
3. Set `trainingPausedDate = null`
4. If `cumulativePauseDays > 10`: set `brokenProtocolDate` → `derive_status()` returns `broken_protocol`
5. Run D02/D03 Path 3 broken protocol check (see Section 9) — check whether the newly computed `max(can_resume_from)` fell after D02 or D03's window end and those visits are still unfiled
6. Run D21 cancellation check if `can_resume_from > Day 28` (see Section 10)

### Pause-clearing locations in code

All three locations in `routes/user_management.py` must apply the same logic:

| Location | Notes |
|---|---|
| `_clear_ae_pause_if_resolved()` | Called from `api_complete_ae_followup_visit` and `api_complete_ae_clinical_visit` |
| Inline in `api_complete_adverse_event_followup` | When all AEs resolve and no RI stubs remain |
| Inline in `api_complete_resolve_robot_issue_visit` | When no RI stubs remain and no AE stubs remain |

---

## 9. D01–D03 Broken Protocol Detection

D01 (activation), D02, and D03 are a critical uninterrupted training block. Broken protocol fires if training does not happen on D02 or D03, regardless of reason. There are three distinct paths.

**Key principle (see Section 0):** broken protocol state is written only in response to user input, never triggered by the system clock alone. Entered `completion_date` and `can_resume_from` values are the authoritative record.

---

### Path 1 — Training not completed at the visit (training_not_done)

The therapist visits on D02 or D03 but training cannot happen. The therapist selects "No" on the "Was training completed?" toggle in the home visit modal.

**Primary reason selection (mandatory single-select):**

The therapist must select one primary reason before saving:

| Reason | Stub created | `training_stopped` flag |
|---|---|---|
| `Adverse Event` | `adverse_event` stub in `incomplete` | `training_stopped: true` on stub → AE modal pre-checks `training_blocked` **only if `activationDate` is set**; otherwise `training_blocked` checkbox is hidden |
| `Robot Issue` *(experimental)* | `robot_issue_call` stub | `training_stopped: true` → RI call modal pre-checks `visit_required` for all devices |
| `Other Device Issue` *(experimental)* | `other_device_issue_call` stub | `training_stopped: true` → ODI call modal pre-checks `visit_required` for all devices |
| `Other` | No stub | Notes mandatory |

Secondary trigger toggles (for additional events arising from the visit) remain below the primary reason. The secondary toggle matching the primary reason is hidden to prevent duplicate stubs.

**Broken protocol confirmation:**
- **Double confirmation popup** is shown before save:
  - First: "Training was not completed on Day N. This will mark the patient as broken protocol. Continue?"
  - Second: "This cannot be undone without admin intervention. Confirm broken protocol?"
- On confirmation: `home_visit_d02` / `home_visit_d03` is saved as **complete** with `training_not_done: true`, `primary_reason`
- `brokenProtocolDate` is set **immediately** on save
- Status transitions to `broken_protocol` immediately

**Key guard:** this path only applies to D02 and D03. If training is not completed at the D15 visit, a `d15_attempt` is created instead and no broken protocol fires. The D15 NO path also uses the same primary reason selector.

---

### Path 2 — Training completed (date locked)

The therapist visits on D02 or D03 and training is completed. The therapist selects "Yes" on the toggle.

- The **session date is locked** by the system to the exact Day 2 or Day 3 calendar date derived from `activationDate`. The date portion of the session start/end fields is pre-filled and read-only — the therapist selects time only.
- Because the date is structurally correct, **no broken protocol check is needed or performed** on this path.
- Validation: session start and end must both fall on the locked date; end must be strictly after start.

This prevents entry errors (wrong date typed) while remaining honest — if training really happened on Day 2 or Day 3, it must have been on that calendar date.

---

### Path 3 — Pause from a prior day outlasts the window (AE follow-up filing)

Training was completed on D01 or D02, but an AE or robot issue triggered with `training_blocked: true` paused training before D02 or D03 could be completed. Those visits go **On Hold**.

The check fires **when the AE follow-up is filed** (user input), not at any clock-driven moment. At that point the system uses the entered `can_resume_from` values to determine the effective resume date.

Two outcomes:

| Outcome | Condition | Result |
|---|---|---|
| Pause clears in time | `max(can_resume_from) ≤ scheduled_date[1]` of the unfiled visit | No broken protocol — visit becomes active; therapist completes it |
| Pause clears too late | `max(can_resume_from) > scheduled_date[1]` of the unfiled visit AND visit still in `incomplete` | **Broken protocol territory** — double confirmation required |

**Double confirmation popup (Path 3):**
- First: "Day N training was missed during the pause period (resolved: \<date\>). This will mark the patient as broken protocol. Continue?"
- Second: "This cannot be undone without admin intervention. Confirm broken protocol?"
- On confirmation: `brokenProtocolDate` is written and the pause is still cleared.

Until the follow-up is filed, the patient's status remains `paused`.

---

### Scenario table

| Day | Situation | Training done? | Path | Outcome |
|---|---|---|---|---|
| D01 | AE/RI after activation, training completed | Yes | — | Normal pause; D02/D03 go On Hold |
| D02 | Therapist visits, training not completed | No | Path 1 | Double confirm → immediate broken protocol |
| D02 | Therapist visits, training completed | Yes | Path 2 | Date locked to Day 2; no broken protocol possible |
| D02 | Pause from D01 — follow-up filed, resolved before window end | N/A | Path 3 | D02 On Hold becomes active; therapist completes it |
| D02 | Pause from D01 — follow-up filed, resolved after window end | N/A | Path 3 | Double confirm → broken protocol at follow-up filing |
| D02 | Training completed, AE/RI after training | Yes | — | Normal pause; D03 goes On Hold |
| D03 | Therapist visits, training not completed | No | Path 1 | Double confirm → immediate broken protocol |
| D03 | Therapist visits, training completed | Yes | Path 2 | Date locked to Day 3; no broken protocol possible |
| D03 | Pause — follow-up filed, resolved before window end | N/A | Path 3 | D03 On Hold becomes active; therapist completes it |
| D03 | Pause — follow-up filed, resolved after window end | N/A | Path 3 | Double confirm → broken protocol at follow-up filing |
| D03 | Training completed, AE/RI after training | Yes | — | Normal pause; protocol continues |

---

### Path 1 detection — server-side

In `api_complete_home_visit` for `home_visit_d02` and `home_visit_d03`:
- If `training_not_done: true` in request body → set `brokenProtocolDate` immediately
- Client sends `confirmed_broken_protocol: true` flag (set by the double confirmation flow); server rejects if flag is absent

### Path 2 enforcement — server-side

In `api_complete_home_visit` for `home_visit_d02` and `home_visit_d03` when `training_not_done` is absent (training done path):
- Server computes the expected date: `activation_date + (N - 1) days` where N is the visit day
- Validates that `session_start` and `session_end` fall on that calendar date; rejects with 400 if not
- No broken protocol logic runs

### Path 3 detection — server-side (AE/RI follow-up routes)

`_check_d0203_broken_protocol(patient, events_data, max_resume_from)` called at all three pause-clearing sites **after** the epoch is closed:

For each of `home_visit_d02`, `home_visit_d03`:
- If already in `complete` → skip
- If still in `incomplete` AND `scheduled_date[1] < max_resume_from` → set `brokenProtocolDate`

Client sends `confirmed_broken_protocol: true` when the therapist confirms the double popup; server calls `_check_d0203_broken_protocol` only when that flag is present (or rejects with 409 if the check would fire but the flag is absent, prompting the client to show the confirmation).

### At-risk banner

`_checkD0203AtRisk(p)` in `static/js/app/patient_detail.js`: when patient is paused and D02 or D03's window has passed, an orange banner appears on the overview tab. Called on every `loadPatientEvents()` refresh. This is **display only** — it does not write any state.

### derive_status() and brokenProtocolDate

`derive_status()` in `utils/data_access.py` checks `brokenProtocolDate` before `cumulativePauseDays`. All three paths write `brokenProtocolDate`, so all converge on `broken_protocol` status. `cumulativePauseDays > 10` also sets `brokenProtocolDate` — all four conditions lead to the same status.

---

## 10. On Resume — D21 Cancellation

The protocol clock is absolute (see Section 0). `scheduled_date` values are never modified. When a pause clears, events that were On Hold simply become overdue at their absolute protocol positions. The therapist completes them whenever possible. No bulk or selective date shifting occurs.

The **only** active write operation on pause-clear is checking `followup_call_d21`:

| Condition | Action |
|---|---|
| `followup_call_d21` still incomplete AND `can_resume_from ≤ Day 28` | No action — event is overdue, therapist completes it when possible |
| `followup_call_d21` still incomplete AND `can_resume_from > Day 28` | Cancel: move to `cancelled` array with `cancellation_reason = "Intervention ended before training could resume"` |

All other events — D07, D15, D15 dependents, prescriptions, agwatch timing — stay at their absolute positions and are simply completed late. `completion_date` records when they actually happened.

### D15 dependents after a pause

`adl_prescription_d15`, `prescription_printout_d15`, `adl_agwatch_timing_d15`, `vcg_prescription_d15` (control), and `vcg_agwatch_timing_d15` (control) are blocked by `home_visit_d15` via `depends_on`. While the pause is active and Day 15 has passed, all of these show as "On Hold". Once the pause clears, `home_visit_d15` becomes overdue — when the therapist completes it, the dependents unblock and also become overdue. They are completed in sequence at whatever date that happens to be.

### Implementation note

The old `_shift_future_incomplete_events()` function (which incorrectly shifted all incomplete events by `pause_days`) must be **deleted**. It is replaced only by the D21 cancellation check above, run at all three pause-clearing sites.

---

## 11. pauseHistory Structure

Stored on `<homer_id>.json`. Tracks each continuous pause epoch.

```json
"pauseHistory": [
  {
    "start": "YYYY-MM-DDTHH:MM",
    "end": "YYYY-MM-DDTHH:MM or null",
    "days": 5,
    "end_event_id": "<uuid of the event that cleared the pause>",
    "reasons": [
      { "type": "adverse_event", "event_id": "<uuid>" },
      { "type": "robot_issue", "event_id": "<uuid>" }
    ]
  }
]
```

**Rules:**
- One entry per **continuous** pause period (not per cause).
- When `trainingPausedDate` transitions from `null`: append a new open entry (`end: null`).
- If a second cause fires while already paused: append to `reasons` of the current open entry (no new entry).
- When pause clears: fill `end`, `days`, `end_event_id`.
- `cumulativePauseDays` is still stored as a scalar on the patient JSON for quick `derive_status()`. It equals `sum(e["days"] for e in pauseHistory if e["days"] is not None)`.

**Locations that must keep pauseHistory in sync:**

| Location | What it does |
|---|---|
| `api_complete_adverse_event` | Opens new epoch on `training_blocked`; or appends to `reasons` if already paused |
| `api_complete_robot_issue_visit` | Same |
| `api_complete_adverse_event_followup` | Closes epoch when pause clears |
| `api_complete_ae_followup_visit` | Closes epoch (via `_clear_ae_pause_if_resolved`) |
| `api_complete_ae_clinical_visit` | Closes epoch (via `_clear_ae_pause_if_resolved`) |
| `api_complete_resolve_robot_issue_visit` | Closes epoch when pause clears |
| `api_create_patient` | Initialises `pauseHistory: []` |
| `scripts/reset_test_patient.py` | Initialises `pauseHistory: []` |
| `scripts/shift_activation.py` | Shifts `pauseHistory[*].start` and `pauseHistory[*].end` by N days |

---

## 12. Event Visibility When Paused

When `trainingPausedDate` is set, only AE/RI resolution events are actionable. All other incomplete events are frozen.

### Overdue list

Only events whose `protocol_event_id` is in `_PAUSE_VISIBLE` appear as overdue:

```python
_PAUSE_VISIBLE = frozenset({
    'adverse_event', 'adverse_event_followup', 'adverse_event_followup_visit',
    'adverse_event_clinical_visit', 'resolve_robot_issue_visit',
    'other_device_issue_call', 'other_device_issue_visit',
    'training_completion_d29',
})
```

### Upcoming list

- Events with `scheduled_date[0] > today` (window genuinely not yet open): shown normally with "Available from \<date\>" label.
- Events with `scheduled_date[0] ≤ today` that are NOT in `_PAUSE_VISIBLE` (window opened or passed while paused): shown with gray/muted styling and a slate **"On hold"** badge. Flagged `on_hold: true` in the server response. Non-clickable.

### Events excluded from On Hold

`a1_assessment` and `a2_assessment` are **never** marked "On Hold". Their fixed positions on the absolute protocol clock mean they are always upcoming or overdue — not held by the pause.

`training_completion_d29` is included in `_PAUSE_VISIBLE` so it surfaces as overdue after Day 29 even while paused. Training completion can be filed independently of the AE chain — a paused patient can still log D29 if Day 29 has arrived. See Section 16.

### Dashboard

On-hold events are omitted entirely from the dashboard (they are not actionable cross-patient events).

---

## 13. Event Visibility When Broken Protocol

When `brokenProtocolDate` is set and the patient has `broken_protocol` status, only a narrow set of events remain interactive. This is distinct from the paused state (Section 12) — broken protocol is terminal for training, whereas a pause is temporary.

### Interactive events (overdue list)

Only these event types appear in the overdue section and can be opened:

| Event type | Notes |
|---|---|
| `adverse_event` stubs | Outstanding stubs triggered before broken protocol — must still be filed |
| `adverse_event_followup` | Active follow-up call stubs |
| `adverse_event_followup_visit` | Active follow-up visit stubs |
| `adverse_event_clinical_visit` | Active clinical visit stubs |
| `robot_issue_call` | Outstanding RI call stubs — must still be filed |
| `robot_issue_visit` | Outstanding RI visit stubs — runs in broken-protocol mode (fault doc only) |
| `resolve_robot_issue_visit` | Outstanding resolve stubs — runs in broken-protocol mode |
| `other_device_issue_call` | Outstanding ODI call stubs — must still be filed |
| `other_device_issue_visit` | Outstanding ODI visit stubs — runs in broken-protocol mode (fault doc only) |
| `discontinuation_reminder` (synthetic) | Injected when no `discontinuation` event is on file |
| `a1_assessment` | Overdue if window has opened; upcoming if not yet reached |
| `a2_assessment` | Overdue if window has opened; upcoming if not yet reached |

### Non-interactive events

All other incomplete events (home visits, prescription events, watch record chain, follow-up calls, training completion, etc.) are **not shown** in the overdue list. They are not action items — they are moot once the protocol is broken. The complete event history remains intact and visible in the Timeline tab.

### RI / ODI visit modals in broken-protocol mode

When the patient is `broken_protocol`, the `robot_issue_visit`, `resolve_robot_issue_visit`, and `other_device_issue_visit` modals switch to a simplified **fault-documentation-only** mode:

- Outcome options (Repaired / Swapped / Neither) are removed.
- The engineer records: which devices are faulty + a fault description per device.
- Server actions: set `has_issue: true` on each faulted device; append a `faulty` device event.
- Device assignments are **NOT closed** — they remain open until the discontinuation modal is completed.
- No pause mechanics apply (`trainingPausedDate` is not modified; patient is already broken_protocol).
- The completed entry includes `broken_protocol_mode: true` to distinguish it from a normal visit entry.

The rationale: in broken protocol the patient will be discontinued, so device swap logistics and training-resume decisions are moot. The only meaningful action is to document what is faulty so the Devices page reflects accurate `has_issue` state and the eventual discontinuation modal can cleanly close all assignments.

### `api_patient_events` behavior for broken_protocol

The function must **not** return empty `complete` or `upcoming` lists. Full behavior:

- `complete` list — built from all completed and free events, identical to any other patient status.
- `overdue` list — filtered to `_BROKEN_PROTOCOL_INTERACTIVE` entries plus the synthetic `discontinuation_reminder`.
- `upcoming` list — `a1_assessment` and `a2_assessment` only, when their `scheduled_date[0]` > today.

```python
_BROKEN_PROTOCOL_INTERACTIVE = frozenset({
    'adverse_event', 'adverse_event_followup',
    'adverse_event_followup_visit', 'adverse_event_clinical_visit',
    'robot_issue_call', 'robot_issue_visit', 'resolve_robot_issue_visit',
    'other_device_issue_call', 'other_device_issue_visit',
})
```

`a1_assessment` and `a2_assessment` are handled separately (scheduled_date check) rather than via `_BROKEN_PROTOCOL_INTERACTIVE` because they may be either upcoming or overdue depending on the current date.

### `discontinuationDate` guard exemption for broken_protocol

Routes that complete AE follow-up events (`adverse_event_followup`, `adverse_event_followup_visit`, `adverse_event_clinical_visit`) must **not** reject requests solely because `discontinuationDate` is set. A patient may have been discontinued but still have open AEs that must be resolved. All other complete-event routes are still blocked after discontinuation.

### `api_patient_events` behavior for discontinued patients

When `discontinuationDate` is set, only a narrow set of events is shown — training is over and devices are returned, so the only remaining work is resolving open AEs and completing any pending assessments.

- `complete` list — all completed and free events, identical to any other status.
- `overdue` and `upcoming` lists — filtered to `_DISCONTINUED_VISIBLE` entries only:

```python
_DISCONTINUED_VISIBLE = frozenset({
    'adverse_event', 'adverse_event_followup',
    'adverse_event_followup_visit', 'adverse_event_clinical_visit',
    'a1_assessment', 'a2_assessment',
})
```

RI/ODI chains are excluded — devices are returned at discontinuation so robot and other-device issues are moot. All regular protocol events (home visits, calls, prescriptions, agwatch timing, etc.) are also hidden.

This filter applies in both `api_patient_events` (patient detail page) and the dashboard events API. It is checked before the broken_protocol filter: `is_discontinued` takes priority.

### Discontinuation flow

Discontinuation is a two-step process to prevent accidental triggering:

**Step 1 — Stub creation (non-broken-protocol patients):**
- The "Discontinue Patient" button in the header triggers a double confirmation popup.
- On confirm: server creates a `discontinuation` stub in `incomplete` with `scheduled_date: [now, now]`.
- Button becomes hidden once stub exists.

**Step 2 — Modal completion:**
- Therapist clicks the `discontinuation` stub in the overdue panel.
- Modal collects: Discontinuation Date, Reason, Notes, optional attachment.
- Server: removes stub from `incomplete`; sets `discontinuationDate`; closes **all** device assignments (writes `end_date` to every open assignment entry); clears `has_issue: false` on all assigned devices; appends entry to `free.discontinuation`.

**Broken-protocol path:**
- Button is hidden (replaced by `discontinuation_reminder` synthetic event).
- `discontinuation_reminder` opens the discontinuation modal directly, skipping the double confirmation (broken protocol is already a confirmed state).
- Same modal fields and server actions apply.

**Device assignment removal rule:** Assignments are closed **only** at discontinuation modal completion. No other event or route closes assignments. RI/ODI visits in broken-protocol mode document faults but leave assignments open.

---

## 14. AE Trigger Cutoff Rules

### When training permanently ends

"Training permanently ends" when any of the following is written to the patient record:

| Condition | What sets it |
|---|---|
| `training_completion_d29` filed | Therapist completes the D29 training completion event |
| `brokenProtocolDate` set | Broken protocol detected (D02/D03 missed, or cumulative pause > 10 days) |
| `discontinuationDate` set | Therapist files a Discontinuation event |

### Primary training modals — trigger toggle visibility

In the following modals, the AE, robot issue, and watch record trigger toggles are **hidden** once training has permanently ended:

- `activation`, `home_visit_d02`, `home_visit_d03`, `home_visit_d15`, `d15_attempt`
- `patient_call`
- `followup_call_d07`, `followup_call_d21`

**Client-side check:** `_trainingPermanentlyEnded(patient)` returns `true` when any of the following is true:
- `trainingCompletionDate` is non-null
- `brokenProtocolDate` is non-null
- `discontinuationDate` is non-null
- `today > activationDate + 28 days` (training window has expired — hides trigger toggles even if D29 not yet filed)

The Day 28 expiry condition suppresses AE/RI trigger toggles in primary training modals after the intervention window closes, without requiring D29 to be filed first. Note: `can_resume_from` in AE follow-up modals is handled naturally — after Day 28 pause auto-termination (Section 15), `trainingPausedDate` is null so the pause-clearing formula never runs and the field is not required.

### AE follow-up modals — AE trigger always visible while chain is active

In `adverse_event_followup`, `adverse_event_followup_visit`, and `adverse_event_clinical_visit` modals, the AE trigger toggle is shown **as long as any unresolved AEs exist**, regardless of whether training has permanently ended. This allows therapists to log new AEs that are related to the ongoing follow-up chain.

Once all AEs are resolved (no unresolved AEs remain), the AE trigger toggle disappears from all modals — including follow-up modals.

### Server-side enforcement

The server rejects new `adverse_event` stubs when:
- `trainingCompletionDate` is set AND no `adverse_event_followup` stubs are currently open (i.e., the follow-up chain is not active)
- `discontinuationDate` is set AND same condition above

When a follow-up chain **is** active (any `adverse_event_followup` stub exists in `incomplete`), the server permits new `adverse_event` stubs even after training has ended.

### Robot issue cutoff

Robot issue triggers follow the same rule as AE triggers in primary training modals — hidden once training permanently ends. Robot issue triggers are **not** present in AE follow-up modals (robot issues and AE follow-ups are independent chains). This means robot issues can only be reported while training is ongoing.

---

## 15. Post-Day 28 Rules

Day 28 is the last day of the intervention. The following rules apply once Day 28 has ended.

### Pause termination at Day 28

`trainingPausedDate` tracks the start of the current open pause epoch. It exists only while training is actively paused. Once Day 28 ends, the concept of "paused from training" no longer applies — there is no training to pause from.

If `trainingPausedDate` is still set when `today > activationDate + 28 days`:

1. Close the open `pauseHistory` epoch: `end = activationDate + 28 days (end-of-day)`, `days = (Day 28 − trainingPausedDate).days`, `end_event_id = null` (system-terminated, not closed by a follow-up event).
2. Add `days` to `cumulativePauseDays`.
3. Set `trainingPausedDate = null`.
4. If `cumulativePauseDays > 10` after the update: set `brokenProtocolDate`. (D02/D03 path 3 broken protocol check is NOT re-run — that only fires at follow-up filing.)
5. D21 cancellation check is NOT run — Day 28 has already passed.

**Effect on AE follow-up modals:** `can_resume_from` is required in AE follow-up routes only to compute pause duration when clearing `trainingPausedDate`. After Day 28 auto-termination, `trainingPausedDate = null`, so the pause-clearing formula never runs. `can_resume_from` is therefore naturally not required — no extra bypass check needed.

**The AE chain continues.** Auto-termination does not resolve any AEs. Outstanding `adverse_event_followup`, `adverse_event_followup_visit`, and `adverse_event_clinical_visit` stubs remain active and must be completed by the therapist.

**Implementation:** a lazy `_auto_terminate_pause_if_expired(patient, patient_meta)` helper runs at the start of `api_patient_events`. If `today > activationDate + 28` and `trainingPausedDate` is set, it applies the above writes and persists them before the event list is computed.

### `post_training` state

`post_training` is a **derived patient status** (never stored — computed by `derive_status()` on every request). It represents the period between Day 28 ending and D29 being formally filed.

**Derivation condition** (checked in `derive_status()` after `broken_protocol` and before `paused`/`active`):
```
activationDate is set
AND today > activationDate + 28 days
AND trainingCompletionDate is null
AND brokenProtocolDate is null
AND discontinuationDate is null
```

Because Day 28 auto-termination clears `trainingPausedDate` before `derive_status()` is called, a patient that was `paused` on Day 28 will show as `post_training` (not `paused`) on Day 29+.

**Dashboard:** a dedicated stat bubble — "Post Training" — shows the count of `post_training` patients. This is the primary reason for this state.

**Patient list:** "Post Training" filter tab, between "Paused" and "Training Complete".

**Patient detail:** amber status badge labelled "Post Training".

**Event visibility:** same as `active` — overdue and upcoming panels function normally. `training_completion_d29` surfaces as overdue once Day 29 has passed (it is in `_PAUSE_VISIBLE` and therefore not on-hold; see Section 12).

### Training period expiry banner

Once `today > activationDate + 28 days` and `trainingCompletionDate` is null, an **amber informational banner** is displayed above the events panels on the patient overview tab:

> Training period has ended (Day 28 passed). Training completion (D29) can be filed when ready.

This is purely informational. The banner disappears once `trainingCompletionDate` is set.

### Training completion (D29) independent of AE chain

`training_completion_d29` can be filed at any time after Day 29, regardless of whether open AEs remain unresolved. The AE follow-up chain continues independently after D29 is filed.

### AE filing cutoff

All AE trigger toggles in primary training modals are hidden once `_trainingPermanentlyEnded(patient)` returns true (see Section 14). AE follow-up modals continue to allow AE triggering while unresolved AEs remain.

### Existing open AEs after Day 28

AEs continue through their full follow-up chain. `adverse_event_followup`, `adverse_event_followup_visit`, and `adverse_event_clinical_visit` stubs remain active until all AEs are resolved.

### Patient calls after Day 28

`patient_call` events can still be logged. The modal after Day 28 is free-text only — all trigger toggles (AE, robot issue, watch record) are hidden.

---

## 16. D29 / A1 / A2 Special Handling

### D29 — Training Completion

`training_completion_d29` has a fixed window at Day 29 (one day after the intervention ends). It completes normally regardless of pause history — there is no concept of pausing after Day 28.

**Modal fields:**

| Field | Required | Notes |
|---|---|---|
| Event date | Yes | datetime-local; future-date guard applies |
| Feedback form | No | PDF upload — separate from the general attachment field |
| Event notes | No | Free text |
| Attachment | No | General document upload |

The feedback form upload is optional in all cases. If the therapist cannot obtain the form (patient condition, refusal, etc.), they leave it blank and document the reason in the notes if needed.

D29 does **not** receive an "On Hold" badge during a pause. It is always displayed at its absolute Day 29 position.

### A1 / A2 — Assessment Cancellation

A1 and A2 assessments have defined time windows in the protocol. They can be cancelled, but **only once the upper bound of the assessment window has passed**.

**Cancellation rules:**

| Rule | Detail |
|---|---|
| Cancellation availability | Only when `today > scheduled_date[1]` (upper window bound has passed) |
| Action | Explicit "Cancel Assessment" button in the modal (separate from normal completion) |
| Required field | Cancellation explanation (textarea, mandatory) |
| Storage | Moved to top-level `cancelled` array in `protocol_events.json` with `cancelled_at` and `cancellation_reason` |
| Irreversibility | A cancelled assessment cannot be uncancelled via the UI |

A1/A2 do **not** receive an "On Hold" badge during a pause. They are always displayed at their absolute protocol positions (upcoming or overdue).

---

## 17. Code Locations

| Concern | File | Function / section |
|---|---|---|
| AE stub creation (primary triggers) | `routes/user_management.py` | `api_complete_activation`, `api_complete_home_visit`, `api_complete_followup_call`, `api_complete_patient_call` |
| AE stub creation (follow-up triggers) | `routes/user_management.py` | `api_complete_adverse_event_followup`, `api_complete_ae_followup_visit`, `api_complete_ae_clinical_visit` (⬜ not yet implemented) |
| RI call stub creation (primary triggers) | `routes/user_management.py` | Same primary trigger routes as AE |
| RI call stub creation (follow-up triggers) | `routes/user_management.py` | Same follow-up routes (⬜ not yet implemented) |
| AE filing (phase 2) + alias assignment | `routes/user_management.py` | `api_complete_adverse_event` |
| AE follow-up chain seeding | `routes/user_management.py` | `_seed_next_ae_followup_or_clear` |
| Follow-up call completion | `routes/user_management.py` | `api_complete_adverse_event_followup` |
| Follow-up visit completion | `routes/user_management.py` | `api_complete_ae_followup_visit` |
| Clinical visit completion | `routes/user_management.py` | `api_complete_ae_clinical_visit` |
| Pause clear (AE path) | `routes/user_management.py` | `_clear_ae_pause_if_resolved` |
| Robot issue call | `routes/user_management.py` | `api_complete_robot_issue_call` |
| Robot issue visit | `routes/user_management.py` | `api_complete_robot_issue_visit` |
| Resolve robot issue visit | `routes/user_management.py` | `api_complete_resolve_robot_issue_visit` |
| D02/D03 broken protocol — Path 1 (training_not_done) | `routes/user_management.py` | `api_complete_home_visit` — checks `training_not_done` flag and `confirmed_broken_protocol` |
| D02/D03 broken protocol — Path 2 (date lock) | `routes/user_management.py` | `api_complete_home_visit` — validates session date equals expected Day 2/3 calendar date |
| D02/D03 broken protocol — Path 3 (AE follow-up) | `routes/user_management.py` | `_check_d0203_broken_protocol` — called from all three pause-clearing sites after epoch closes |
| Double confirmation guard — client | `static/js/app/patient_detail.js` | `saveHomeVisit()` (Path 1) and `saveAdverseEventFollowup()` / `saveAeFollowupVisit()` / `saveAeClinicalVisit()` / `saveResolveRobotIssueVisit()` (Path 3) |
| D21 cancellation on resume | `routes/user_management.py` | `_cancel_d21_if_needed` (replaces `_shift_future_incomplete_events`, which must be deleted) |
| Day 28 pause auto-termination | `routes/user_management.py` | `_auto_terminate_pause_if_expired(patient, patient_meta)` — ⬜ not yet implemented; called at start of `api_patient_events` |
| `post_training` status derivation | `utils/data_access.py` | `derive_status()` — ⬜ not yet implemented; check `today > activationDate + 28` after `broken_protocol`, before `paused`/`active` |
| Training period expiry banner | `static/js/app/patient_detail.js` | `_checkTrainingPeriodExpired(patient)` — ⬜ not yet implemented; called on every `loadPatientEvents()` refresh |
| AE trigger cutoff — client-side visibility | `static/js/app/patient_detail.js` | `_trainingPermanentlyEnded(patient)` — ⬜ not yet implemented; includes Day 28 expiry: `today > activationDate + 28 days` |
| Broken protocol event list (patient events) | `routes/user_management.py` | `api_patient_events` — replaces early return with full complete list + filtered overdue |
| Broken protocol event list (dashboard events) | `routes/dashboard.py` | `api_dashboard_events` — same filtering |
| Dashboard live D02/D03 check | `routes/dashboard.py` | `api_dashboard_events` loop |
| At-risk banner | `static/js/app/patient_detail.js` | `_checkD0203AtRisk` |
| On-hold flag (patient events) | `routes/user_management.py` | `api_patient_events` loop |
| On-hold flag (dashboard events) | `routes/dashboard.py` | `api_dashboard_events` loop |
| On-hold rendering | `static/js/app/patient_detail.js` | `patientEventRow` |
| Status derivation | `utils/data_access.py` | `derive_status` |
| pauseHistory epoch open | `routes/user_management.py` | `api_complete_adverse_event`, `api_complete_robot_issue_visit` |
| pauseHistory epoch close | `routes/user_management.py` | All three pause-clearing sites |
| D29 modal | `templates/patient_detail.html` | `#training-completion-modal` (⬜ needs dedicated modal, currently uses simple-event) |
| A1/A2 cancellation | `routes/user_management.py` | ⬜ not yet implemented |
