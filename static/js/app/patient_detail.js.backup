/* ============================================================
   patient_detail.js — Patient detail page: overview, tabs, modals
   PATIENT_HOMER_ID is set inline by the template.
   ============================================================ */

let patientData = null;
let isAdmin      = false;
let userPrivilege = '';
let userLoginId   = '';   // current user's loginId (for "filed by You")
let eventsCache = [];

// ── Status helpers ────────────────────────────────────────────────────────────

const STATUS_LABEL = {
  unassigned:          'Unassigned',
  inactive:            'Inactive',
  active:              'Active',
  paused:              'Paused',
  post_training:       'Post Training',
  broken_protocol:     'Broken Protocol',
  training_completed:  'Training Complete',
  a1_completed:        'A1 Complete',
  all_completed:       'All Complete',
  pre_discontinued:    'Pre-Discontinued',
  discontinued:        'Discontinued',
};

const STATUS_CLASS = {
  unassigned:          'bg-slate-100 text-slate-600',
  inactive:            'bg-yellow-100 text-yellow-700',
  active:              'bg-blue-100 text-blue-700',
  paused:              'bg-amber-100 text-amber-700',
  post_training:       'bg-sky-100 text-sky-700',
  broken_protocol:     'bg-red-100 text-red-700',
  training_completed:  'bg-teal-100 text-teal-700',
  a1_completed:        'bg-violet-100 text-violet-700',
  all_completed:       'bg-green-100 text-green-700',
  pre_discontinued:    'bg-orange-100 text-orange-700',
  discontinued:        'bg-red-100 text-red-700',
};

const GROUP_CLASS = {
  experimental: 'text-blue-700',
  control:      'text-teal-700',
};

function fmtDate(iso) {
  if (!iso) return '—';
  return iso.replace('T', ' ');
}

// ── Training state helpers ────────────────────────────────────────────────────

function _checkTrainingPeriodExpired(patient) {
  const banner = document.getElementById('training-period-expiry-banner');
  if (!banner) return;
  banner.classList.toggle('hidden', !patient || patient.status !== 'post_training');
}

// ── Tab switching ─────────────────────────────────────────────────────────────

function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle('border-blue-600',  active);
    btn.classList.toggle('text-blue-600',    active);
    btn.classList.toggle('border-transparent', !active);
    btn.classList.toggle('text-slate-500',   !active);
  });
  document.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.toggle('hidden', pane.id !== `tab-${tab}`);
  });
  if (tab === 'devices')   loadDevicesTab();
  if (tab === 'adl')      loadAdlTab();
  if (tab === 'vcg')      loadVcgTab();
  if (tab === 'calls')         renderCallLogsTab();
  if (tab === 'adverse')       renderAdverseEventsTab();
  if (tab === 'watch-records') renderWatchRecordsTab();
  if (tab === 'device-issues') renderDeviceIssuesTab();
  if (tab === 'timeline')      renderTimelineTab();
  if (tab === 'notes')         renderNotesTab();
}

// ── Modal helpers ─────────────────────────────────────────────────────────────

function showModal(id) {
  const m = document.getElementById(id);
  if (!m) return;
  m.style.display = 'flex';
  // Date Rule Framework: apply universal completion-date bounds to every date
  // input in the modal that hasn't been constrained by the opener. The modal
  // root's data-date-error attribute names the <p> the keyboard validator
  // writes into.
  _applyDateBounds(m, m.dataset.dateError || '');
}

function hideModal(id) {
  const m = document.getElementById(id);
  if (m) m.style.display = 'none';
}

function setError(id, msg) {
  const el = document.getElementById(id);
  if (!el) return;
  if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
  else      { el.textContent = '';  el.classList.add('hidden'); }
}

function _nowForInput() {
  // Returns current LOCAL datetime truncated to minutes in YYYY-MM-DDTHH:MM format.
  // Must use local components — toISOString() returns UTC which breaks datetime-local
  // comparisons in non-UTC timezones (e.g. IST = UTC+5:30 would flag valid local times).
  const d   = new Date();
  const pad = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function _attachSessionEndGuard(startInputId, endInputId, errorId) {
  // Fires on change of the end input; validates same date and end > start immediately.
  const startInput = document.getElementById(startInputId);
  const endInput = document.getElementById(endInputId);
  if (!endInput || !startInput) return;

  if (endInput._sessionEndGuard) {
    endInput.removeEventListener('change', endInput._sessionEndGuard);
    endInput.removeEventListener('input', endInput._sessionEndGuard);
  }

  endInput._sessionEndGuard = () => {
    _validateSessionEndInput(startInput, endInput, errorId);
  };

  endInput.addEventListener('change', endInput._sessionEndGuard);
  endInput.addEventListener('input', endInput._sessionEndGuard);

  // Also validate start input changes
  if (startInput._sessionStartGuard) {
    startInput.removeEventListener('change', startInput._sessionStartGuard);
    startInput.removeEventListener('input', startInput._sessionStartGuard);
  }

  startInput._sessionStartGuard = () => {
    _validateSessionEndInput(startInput, endInput, errorId);
  };

  startInput.addEventListener('change', startInput._sessionStartGuard);
  startInput.addEventListener('input', startInput._sessionStartGuard);
}

function _validateSessionEndInput(startInput, endInput, errorId) {
  // Validate session start/end pairs for keyboard input
  const startVal = startInput?.value;
  const endVal   = endInput?.value;

  if (!startVal || !endVal) {
    setError(errorId, '');
    return true;
  }

  const startDate = startVal.split('T')[0];
  const endDate   = endVal.split('T')[0];

  if (startDate !== endDate) {
    setError(errorId, 'Session start and end must be on the same date.');
    return false;
  }

  if (endVal <= startVal) {
    setError(errorId, 'Session end must be after session start.');
    return false;
  }

  setError(errorId, '');
  return true;
}

function _attachDateGuard(inputId, errorId) {
  const input = document.getElementById(inputId);
  if (!input) return;
  input.max = _nowForInput();
  // Remove previously attached listeners to avoid duplicates on modal re-open.
  if (input._dateGuard) {
    input.removeEventListener('change',   input._dateGuard);
    input.removeEventListener('input',    input._dateGuard);
    input.removeEventListener('blur',     input._dateGuard);
    input.removeEventListener('focusout', input._dateGuard);
  }
  input._dateGuard = () => { _validateDateInput(input, errorId); };
  // Safari's native datetime-local picker does not reliably fire `change` or
  // `input` on commit (the user picks a date and dismisses the popup but the
  // event doesn't propagate). Listen on `blur` and `focusout` as well so the
  // error message updates whenever focus leaves the picker.
  input.addEventListener('change',   input._dateGuard);
  input.addEventListener('input',    input._dateGuard);
  input.addEventListener('blur',     input._dateGuard);
  input.addEventListener('focusout', input._dateGuard);
}

function _validateDateInput(input, errorId) {
  // Comprehensive validation for keyboard-entered dates against min/max constraints.
  // Error messages always include the time when the input is datetime-local so
  // datetime-precision bounds (e.g. "must be after device setup at 14:30") are
  // unambiguous. For date-only inputs the time is omitted.
  if (!input.value) {
    setError(errorId, '');
    return true;
  }

  const value = input.value;
  let errorMsg = '';

  if (input.min && value < input.min) {
    errorMsg = `Date cannot be before ${_formatDateForDisplay(input.min)}.`;
  } else if (input.max && value > input.max) {
    errorMsg = `Date cannot be after ${_formatDateForDisplay(input.max)}.`;
  }

  setError(errorId, errorMsg);
  return !errorMsg;
}

// Date Rule Framework — client mirror of utils/date_validation.py. The rules
// spec is rendered server-side as window.DATE_RULES (so client and server
// stay in lock-step). Each modal-open hooks _applyDateBounds via showModal;
// per-input data-event-id selects the per-event rule when present, otherwise
// the default rule applies. Inputs marked data-date-rule="scheduling" skip
// the framework entirely. See CLAUDE.md → "Date Rule Framework".

const _DSL_OFFSET = /^([A-Za-z_]\w*)\s*([+-])\s*(\d+)d$/;

function _dtFromInput(s) {
  // Parse 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM[:SS]' to a Date built from local
  // components (Date.parse with a date-only string treats it as UTC, which
  // shifts the date in non-UTC zones — avoid that).
  if (!s) return null;
  const v = s.replace(' ', 'T');
  const m = v.match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), 0, 0);
}
function _atMidnight(d) { return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 0, 0, 0, 0); }
function _atEod(d)      { return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 0, 0); }
function _addDays(d, n) { const r = new Date(d); r.setDate(r.getDate() + n); return r; }

function _latestCompletion(events, eventId) {
  // Most recent completion_date among completed entries (complete[] + free[*])
  // matching the given protocol_event_id. _completeEventsCache merges both.
  let best = null;
  for (const e of (events || [])) {
    if (e.protocol_event_id !== eventId || !e.completion_date) continue;
    if (best === null || e.completion_date > best) best = e.completion_date;
  }
  return best;
}

function _resolveToken(token, patient, events, role) {
  // role: 'floor' or 'ceiling'. Mirrors _resolve_token in utils/date_validation.py.
  const t = (token || '').trim();
  if (t === 'today') {
    const now = new Date();
    return role === 'ceiling'
      ? new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours(), now.getMinutes(), 0, 0)
      : _atMidnight(now);
  }
  if (t.startsWith('event:')) {
    const eid = t.slice('event:'.length).trim();
    const comp = _latestCompletion(_completeEventsCache, eid);
    return comp ? _dtFromInput(comp) : null;
  }
  const m = t.match(_DSL_OFFSET);
  if (m) {
    const [, field, sign, n] = m;
    const base = _dtFromInput((patient || {})[field]);
    if (!base) return null;
    const shifted = _addDays(base, sign === '+' ? +n : -+n);
    return role === 'ceiling' ? _atEod(shifted) : _atMidnight(shifted);
  }
  // Bare patient-field — normalized to midnight/EOD so a patient activated at
  // 11:00 still allows earlier-time events on the same day.
  const base = _dtFromInput((patient || {})[t]);
  if (!base) return null;
  return role === 'ceiling' ? _atEod(base) : _atMidnight(base);
}

function _ruleForEvent(eventId, group) {
  const rules = window.DATE_RULES || {};
  const spec  = (rules.events || {})[eventId];
  if (!spec || typeof spec !== 'object') return null;
  if ('experimental' in spec || 'control' in spec) return group ? spec[group] : null;
  return spec;
}

function _resolveDateBounds(eventId, ruleKind = 'completion') {
  // Returns {min: Date|null, max: Date|null} for the given event_id (or the
  // appropriate default rule when no per-event override exists).
  // `ruleKind === 'scheduling'` is used for future-date inputs marked with
  // data-date-rule="scheduling" — falls back to default_scheduling_rule
  // (typically not_before: today) instead of default_completion_rule.
  const rules   = window.DATE_RULES || {};
  const patient = patientData || {};
  const defaultRule = ruleKind === 'scheduling'
    ? rules.default_scheduling_rule
    : rules.default_completion_rule;
  const rule = _ruleForEvent(eventId, patient.group) || defaultRule || {};
  const nb = (rule.not_before || []).map(t => _resolveToken(t, patient, _completeEventsCache, 'floor')).filter(Boolean);
  const na = (rule.not_after  || []).map(t => _resolveToken(t, patient, _completeEventsCache, 'ceiling')).filter(Boolean);
  return {
    min: nb.length ? new Date(Math.max(...nb.map(d => d.getTime()))) : null,
    max: na.length ? new Date(Math.min(...na.map(d => d.getTime()))) : null,
  };
}

function _toInputValue(d, isDateTime) {
  // YYYY-MM-DD or YYYY-MM-DDTHH:MM in local time (mirrors _nowForInput style).
  const pad = n => String(n).padStart(2, '0');
  const ymd = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  return isDateTime ? `${ymd}T${pad(d.getHours())}:${pad(d.getMinutes())}` : ymd;
}

// Hooked into showModal — sweeps every <input type="date"> and <input
// type="datetime-local"> in the modal and applies bounds resolved by the DSL.
// Additive: only sets min/max when the opener hasn't already set a (stricter)
// bound, so per-modal custom bounds are preserved.
function _applyDateBounds(modalElOrId, errorId) {
  const modalEl = typeof modalElOrId === 'string'
    ? document.getElementById(modalElOrId) : modalElOrId;
  if (!modalEl) return;

  modalEl.querySelectorAll('input[type="date"], input[type="datetime-local"]').forEach(input => {
    const ruleKind = input.dataset.dateRule === 'scheduling' ? 'scheduling' : 'completion';
    const isDateTime = input.type === 'datetime-local';
    const { min: minDt, max: maxDt } = _resolveDateBounds(input.dataset.eventId || null, ruleKind);

    if (!input.min && minDt) input.min = _toInputValue(minDt, isDateTime);
    if (!input.max && maxDt) input.max = _toInputValue(maxDt, isDateTime);

    const errId = input.dataset.dateError || errorId;
    if (!errId) return;
    if (input._dateGuard) {
      input.removeEventListener('change',   input._dateGuard);
      input.removeEventListener('input',    input._dateGuard);
      input.removeEventListener('blur',     input._dateGuard);
      input.removeEventListener('focusout', input._dateGuard);
    }
    input._dateGuard = () => { _validateDateInput(input, errId); };
    // See _attachDateGuard for the Safari-quirk rationale on blur/focusout.
    input.addEventListener('change',   input._dateGuard);
    input.addEventListener('input',    input._dateGuard);
    input.addEventListener('blur',     input._dateGuard);
    input.addEventListener('focusout', input._dateGuard);
  });
}

function _formatDateForDisplay(dateStr) {
  // Format an input attribute value (YYYY-MM-DD or YYYY-MM-DDTHH:MM) for an
  // error message. When the string carries a time component (datetime-local
  // inputs), the time is always included — even at midnight — so the user
  // can see precisely where the bound falls (e.g. "after device setup at 14:30").
  try {
    if (typeof dateStr === 'string' && dateStr.includes('T')) {
      const d = new Date(dateStr);
      const date = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
      const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
      return `${date} ${time}`;
    }
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

function _hasDateValidationErrors(errorElementIds) {
  // Re-validates every date / datetime-local input in each modal that contains
  // one of the given error elements. Returns true if any input's value is
  // outside its min/max bounds.
  //
  // Important: this used to inspect the textual content of the named error
  // elements, but those elements are shared between the date validator and
  // other validation messages (outcome group, custom field errors). A leftover
  // non-date message would be misread as a date error and block submission
  // even after the underlying issue was fixed. Re-validating the inputs
  // directly is robust against that.
  if (!errorElementIds) return false;
  if (!Array.isArray(errorElementIds)) errorElementIds = [errorElementIds];

  const seenModals = new Set();
  for (const errorId of errorElementIds) {
    const el = document.getElementById(errorId);
    if (!el) continue;
    const modal = el.closest('[id$="-modal"]');
    if (!modal || seenModals.has(modal)) continue;
    seenModals.add(modal);
    for (const input of modal.querySelectorAll('input[type="date"], input[type="datetime-local"]')) {
      if (!input.value) continue;
      if (input.min && input.value < input.min) return true;
      if (input.max && input.value > input.max) return true;
    }
  }
  return false;
}

function setLoading(btnId, loading) {
  const btn = document.getElementById(btnId);
  if (!btn) return;
  btn.disabled = loading;
  btn.textContent = loading ? 'Please wait…' : btn.dataset.label;
}

// ── API helper ────────────────────────────────────────────────────────────────

async function apiPost(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { error: `Server error (${res.status})` }; }
  return { ok: res.ok, data };
}

async function apiGet(url) {
  const res  = await fetch(url);
  const text = await res.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { error: `Server error (${res.status})` }; }
  return { ok: res.ok, data };
}

// ── Render overview ───────────────────────────────────────────────────────────

function renderOverview(p) {
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val || '—'; };

  set('info-homer-id',      p.homerID);
  set('info-hospital-id',   p.hospitalID);
  set('info-training-side', p.trainingSide);
  set('info-enroll-date',   fmtDate(p.enrollDate));

  const groupEl = document.getElementById('info-group');
  if (groupEl) {
    groupEl.textContent = p.group ? p.group.charAt(0).toUpperCase() + p.group.slice(1) : '—';
    groupEl.className = `text-sm font-semibold ${GROUP_CLASS[p.group] || 'text-slate-800'}`;
  }

  const statusEl = document.getElementById('info-status');
  if (statusEl) {
    const label = STATUS_LABEL[p.status] || p.status;
    const cls   = STATUS_CLASS[p.status]  || 'bg-slate-100 text-slate-600';
    statusEl.innerHTML = `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${cls}">${label}</span>`;
  }

  // Subtitle
  const sub = document.getElementById('patient-subtitle');
  if (sub) {
    const label = STATUS_LABEL[p.status] || p.status;
    const cls   = STATUS_CLASS[p.status]  || 'bg-slate-100 text-slate-600';
    sub.innerHTML = `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${cls}">${label}</span>`;
  }

  set('date-a0',             fmtDate(p.a0CompletionDate));
  set('date-activation',     fmtDate(p.activationDate));
  set('date-training',       fmtDate(p.trainingCompletionDate));
  const discRow = document.getElementById('date-discontinuation-row');
  if (discRow) discRow.classList.toggle('hidden', !p.discontinuationDate);
  set('date-discontinuation',fmtDate(p.discontinuationDate));

  // A1 key date: Missed / Delayed / normal
  const a1DateEl = document.getElementById('date-a1');
  if (a1DateEl) {
    if (p.a1MissedDate) {
      a1DateEl.innerHTML = '<span class="text-slate-400 font-normal">Missed</span>';
    } else if (p.a1CompletionDate) {
      const a1Win = _assessmentWindows['a1_assessment'];
      const delayed = a1Win && p.a1CompletionDate.slice(0, 10) > a1Win.end;
      a1DateEl.innerHTML = fmtDate(p.a1CompletionDate)
        + (delayed ? ' <span class="inline-flex items-center gap-0.5 text-xs font-semibold bg-amber-100 text-amber-700 border border-amber-200 rounded-full px-1.5 py-0.5"><i class="fas fa-clock text-[9px]"></i>Delayed</span>' : '');
    } else {
      a1DateEl.textContent = '—';
    }
  }

  // A2 key date: Missed / Delayed / normal
  const a2DateEl = document.getElementById('date-a2');
  if (a2DateEl) {
    if (p.a2MissedDate) {
      a2DateEl.innerHTML = '<span class="text-slate-400 font-normal">Missed</span>';
    } else if (p.a2CompletionDate) {
      const a2Win = _assessmentWindows['a2_assessment'];
      const delayed = a2Win && p.a2CompletionDate.slice(0, 10) > a2Win.end;
      a2DateEl.innerHTML = fmtDate(p.a2CompletionDate)
        + (delayed ? ' <span class="inline-flex items-center gap-0.5 text-xs font-semibold bg-amber-100 text-amber-700 border border-amber-200 rounded-full px-1.5 py-0.5"><i class="fas fa-clock text-[9px]"></i>Delayed</span>' : '');
    } else {
      a2DateEl.textContent = '—';
    }
  }

  // Days elapsed counter
  const terminal  = new Set(['discontinued', 'all_completed', 'pre_discontinued']);
  const daysCard  = document.getElementById('days-card');
  if (daysCard) {
    if (terminal.has(p.status)) {
      daysCard.classList.add('hidden');
    } else {
      let display = '—';
      if (p.activationDate) {
        const today = new Date(); today.setHours(0,0,0,0);
        const ref   = new Date(p.activationDate); ref.setHours(0,0,0,0);
        const days  = Math.floor((today - ref) / 86400000) + 1;
        if (days > 0) display = days;
      }
      document.getElementById('days-elapsed-number').textContent = display;
      document.getElementById('days-elapsed-label').textContent  = 'Days Since Activation';
      daysCard.classList.remove('hidden');
    }
  }

  // VCG tab: control only
  const vcgBtn = document.getElementById('tab-btn-vcg');
  if (vcgBtn) vcgBtn.classList.toggle('hidden', p.group !== 'control');

  // Device Issues tab: experimental only (RI + ODI both apply only to experimental devices)
  const deviceIssuesBtn = document.getElementById('tab-btn-device-issues');
  if (deviceIssuesBtn) deviceIssuesBtn.classList.toggle('hidden', p.group !== 'experimental');

  renderPauseBanner(p);
  _checkD0203AtRisk(p);
  _checkTrainingPeriodExpired(p);
  renderPauseHistoryTable(p);
  renderActions(p);
  loadOverviewDevices();
}

// ── Overview devices ──────────────────────────────────────────────────────────

async function loadOverviewDevices() {
  const section = document.getElementById('overview-devices-section');
  const content = document.getElementById('overview-devices-content');
  if (!section || !content) return;

  const { ok, data } = await apiGet(`/api/patients/${PATIENT_HOMER_ID}/current-devices`);
  if (!ok || !data.devices || !data.devices.length) {
    section.classList.add('hidden');
    return;
  }

  content.innerHTML = `<div class="grid grid-cols-3 gap-x-4 gap-y-4">${data.devices.map(_deviceChip).join('')}</div>`;
  section.classList.remove('hidden');
}

function _deviceChip(d) {
  const TYPE_LABEL = { pluto: 'Pluto', mars: 'Mars', modems: 'Modem', laptops: 'Laptop', agwatch: 'Watch' };
  const label = TYPE_LABEL[d.type] || d.type;
  const limb  = d.limb ? ` (${d.limb.charAt(0).toUpperCase() + d.limb.slice(1)})` : '';
  const simLabel = d.sim ? ' (SIM)' : '';

  let badge = '';
  if (d.lost)           badge = '<span class="ml-1 text-xs font-semibold text-red-600 bg-red-50 px-1.5 py-0.5 rounded-full">Lost</span>';
  else if (d.has_issue) badge = '<span class="ml-1 text-xs font-semibold text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded-full">Issue</span>';

  const valueHtml = d.sim
    ? `<div class="flex items-baseline gap-1.5 flex-wrap">` +
      `<span class="text-sm font-semibold text-slate-800 font-mono whitespace-nowrap">${d.device_id}</span>` +
      `<span class="text-xs text-slate-400 font-mono whitespace-nowrap">(${d.sim})</span>` +
      `</div>`
    : `<p class="text-sm font-semibold text-slate-800 font-mono">${d.device_id}</p>`;

  return `<div>` +
         `<p class="text-xs text-slate-400 font-medium mb-0.5">${label}${limb}${simLabel}${badge}</p>` +
         `${valueHtml}` +
         `</div>`;
}

// ── Pause banner ──────────────────────────────────────────────────────────────

function renderPauseBanner(p) {
  const banner = document.getElementById('pause-banner');
  if (!banner) return;

  if (p.status !== 'paused') {
    banner.classList.add('hidden');
    return;
  }

  const today = new Date(); today.setHours(0,0,0,0);
  let daysThisPeriod = 0;
  if (p.trainingPausedDate) {
    const since = new Date(p.trainingPausedDate); since.setHours(0,0,0,0);
    daysThisPeriod = Math.max(0, Math.floor((today - since) / 86400000));
  }
  const priorDays = p.cumulativePauseDays || 0;
  const totalDays = priorDays + daysThisPeriod;
  const critical  = totalDays >= 8;

  document.getElementById('pause-since').textContent      = p.trainingPausedDate ? fmtDate(p.trainingPausedDate) : '—';
  document.getElementById('pause-days-label').textContent = totalDays;
  document.getElementById('pause-days-label').className   = `font-semibold ${critical ? 'text-red-700' : 'text-amber-800'}`;
  document.getElementById('pause-prior-days').textContent   = priorDays;
  document.getElementById('pause-current-days').textContent = daysThisPeriod;

  // Segmented progress bar — one slice per closed epoch + one for current open epoch
  const barContainer = document.getElementById('pause-bar-container');
  if (barContainer) {
    const history   = p.pauseHistory || [];
    const maxDays   = 10;
    // Palette for closed epochs (cycles if > colours available)
    const palette   = ['bg-amber-500', 'bg-yellow-500', 'bg-amber-600', 'bg-yellow-600'];
    const segments  = [];

    history.forEach((epoch, i) => {
      const d = epoch.days ?? 0;
      if (d <= 0) return;
      const pct = Math.min(100, Math.round(d / maxDays * 100));
      segments.push(`<div class="h-2 transition-all ${palette[i % palette.length]}" style="width:${pct}%"></div>`);
    });

    if (daysThisPeriod > 0) {
      const pct = Math.min(100, Math.round(daysThisPeriod / maxDays * 100));
      const cls = critical ? 'bg-red-400' : 'bg-orange-300';
      segments.push(`<div class="h-2 transition-all ${cls}" style="width:${pct}%"></div>`);
    }

    barContainer.innerHTML = segments.join('');
    barContainer.className = `w-full rounded-full h-2 flex overflow-hidden ${critical ? 'bg-red-100' : 'bg-amber-100'}`;
  }

  if (critical) {
    banner.className = banner.className.replace('bg-amber-50 border-amber-300', 'bg-red-50 border-red-300');
  } else {
    banner.className = banner.className.replace('bg-red-50 border-red-300', 'bg-amber-50 border-amber-300');
  }

  _renderPauseReasonPills();
  banner.classList.remove('hidden');
}

// ── D02/D03 at-risk banner ─────────────────────────────────────────────────────

function _checkD0203AtRisk(p) {
  const banner = document.getElementById('d0203-atrisk-banner');
  if (!banner) return;

  if (p.status !== 'paused' || !p.activationDate) {
    banner.classList.add('hidden');
    return;
  }

  const today      = new Date(); today.setHours(0, 0, 0, 0);
  const activation = new Date(p.activationDate); activation.setHours(0, 0, 0, 0);
  // 1-based day numbering: day 2 end = activation + 1d; day 3 end = activation + 2d
  const d02End = new Date(activation); d02End.setDate(d02End.getDate() + 1);
  const d03End = new Date(activation); d03End.setDate(d03End.getDate() + 2);

  const completeIds = new Set((_completeEventsCache || []).map(e => e.protocol_event_id));
  let atRiskLabel = null;
  if (!completeIds.has('home_visit_d02') && today > d02End) {
    atRiskLabel = 'Day 2';
  } else if (!completeIds.has('home_visit_d03') && today > d03End) {
    atRiskLabel = 'Day 3';
  }

  if (atRiskLabel) {
    const msgEl = document.getElementById('d0203-atrisk-msg');
    if (msgEl) {
      msgEl.textContent = `Training at risk — ${atRiskLabel} home visit window has passed while training is paused. Broken protocol will be flagged when the pause is cleared.`;
    }
    banner.classList.remove('hidden');
  } else {
    banner.classList.add('hidden');
  }
}

function _renderPauseReasonPills() {
  const pillsEl = document.getElementById('pause-reason-pills');
  if (!pillsEl) return;

  const pills = [];
  const cache = eventsCache || [];
  const hasRobotIssue = cache.some(e => e.protocol_event_id === 'resolve_robot_issue_visit');
  const hasAE         = cache.some(e => e.protocol_event_id === 'adverse_event_followup');

  if (hasRobotIssue)
    pills.push(`<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-700 border border-orange-200"><i class="fas fa-robot text-[10px]"></i>Robot issue pending</span>`);
  if (hasAE)
    pills.push(`<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 border border-red-200"><i class="fas fa-exclamation-circle text-[10px]"></i>Adverse event pending</span>`);
  if (!pills.length && cache.length)
    pills.push(`<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">Reason unknown</span>`);

  pillsEl.innerHTML = pills.join('');
}

function renderPauseHistoryTable(p) {
  const section = document.getElementById('pause-history-section');
  const content = document.getElementById('pause-history-content');
  if (!section || !content) return;

  const history = p.pauseHistory || [];
  if (!history.length) { section.classList.add('hidden'); return; }
  section.classList.remove('hidden');

  const _TYPE_LABEL = { robot_issue: 'Robot issue', adverse_event: 'Adverse event' };

  const rows = history.map((epoch, i) => {
    const epochNum  = i + 1;
    const startStr  = epoch.start ? fmtDate(epoch.start) : '—';
    const endStr    = epoch.end   ? fmtDate(epoch.end)   : '<span class="text-amber-600 font-medium">Ongoing</span>';
    const daysStr   = epoch.days != null ? `${epoch.days}d` : '<span class="text-amber-600 font-medium">—</span>';
    const reasons   = (epoch.reasons || []).map(r => {
      const label = _TYPE_LABEL[r.type] || r.type;
      return `<span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs bg-slate-100 text-slate-600 border border-slate-200 font-medium">${label}</span>`;
    }).join(' ');

    return `
      <tr class="${i % 2 === 0 ? '' : 'bg-slate-50'}">
        <td class="py-1.5 px-3 text-xs text-slate-500 font-medium">Epoch ${epochNum}</td>
        <td class="py-1.5 px-3 text-xs text-slate-700">${startStr}</td>
        <td class="py-1.5 px-3 text-xs text-slate-700">${endStr}</td>
        <td class="py-1.5 px-3 text-xs text-slate-700">${daysStr}</td>
        <td class="py-1.5 px-3 text-xs">${reasons || '<span class="text-slate-400">—</span>'}</td>
      </tr>`;
  }).join('');

  content.innerHTML = `
    <table class="w-full text-left">
      <thead>
        <tr class="border-b border-slate-100">
          <th class="pb-2 px-3 text-xs font-semibold text-slate-400 uppercase tracking-wide"></th>
          <th class="pb-2 px-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">Start</th>
          <th class="pb-2 px-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">End</th>
          <th class="pb-2 px-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">Days</th>
          <th class="pb-2 px-3 text-xs font-semibold text-slate-400 uppercase tracking-wide">Reasons</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// ── Action buttons ────────────────────────────────────────────────────────────

const ACTION_DEFS = {
  inactive: [
    { label: 'Activate',          color: 'bg-blue-600 hover:bg-blue-700 text-white',   action: () => openActivationModal(null) },
  ],
  active: [],
  paused: [],
  broken_protocol: [],
  training_completed: [
    { label: 'Record A1',         color: 'bg-violet-600 hover:bg-violet-700 text-white', action: () => openA1Modal() },
  ],
  a1_completed: [
    { label: 'Record A2',         color: 'bg-green-600 hover:bg-green-700 text-white', action: () => openA2Modal() },
  ],
};

function renderActions(p) {
  const card    = document.getElementById('actions-card');
  const buttons = document.getElementById('action-buttons');
  if (!card || !buttons) return;

  const defs = ACTION_DEFS[p.status];
  if (!defs || !defs.length || !isAdmin) { card.classList.add('hidden'); return; }

  card.classList.remove('hidden');
  buttons.innerHTML = '';
  defs.forEach(def => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `px-5 py-2.5 rounded-xl text-sm font-semibold transition-colors ${def.color}`;
    btn.textContent = def.label;
    btn.addEventListener('click', def.action);
    buttons.appendChild(btn);
  });
}

// ── Modal openers ─────────────────────────────────────────────────────────────


let _a1AssessmentEventId = null;
let _a2AssessmentEventId = null;
let _a2A1MissOkAt = null;   // epoch ms when user confirmed A2-auto-misses-A1; null if A1 not pending
let _schedA1EventId = null;
let _schedA2EventId = null;
let _a1ScheduledDate = null;
let _a2ScheduledDate = null;

function _openAssessmentModal(which, ev) {
  const color = which === 'a1' ? 'violet' : 'green';
  if (which === 'a1') { _a1AssessmentEventId = ev ? ev.id : null; }
  else                { _a2AssessmentEventId = ev ? ev.id : null; }

  document.getElementById(`${which}-date`).value  = '';
  document.getElementById(`${which}-notes`).value = '';
  document.getElementById(`${which}-cancel-reason`).value = '';
  document.getElementById(`${which}-out-of-window-reason`).value = '';
  document.getElementById(`${which}-out-of-window-section`).classList.add('hidden');
  setError(`${which}-error`, '');
  const max = new Date().toISOString().slice(0, 16);
  document.getElementById(`${which}-date`).max = max;
  _attachDateGuard(`${which}-date`, `${which}-error`);
  _setupAssessmentOutOfWindowGuard(which);

  const apptDate = ev && ev.appointment_date ? ev.appointment_date : null;
  if (which === 'a1') { _a1ScheduledDate = apptDate; }
  else                { _a2ScheduledDate = apptDate; }

  const rescheduleSection = document.getElementById(`${which}-reschedule-section`);
  const cancelSection = document.getElementById(`${which}-cancel-section`);
  const recordSection = document.getElementById(`${which}-record-section`);
  const noApptMsg = document.getElementById(`${which}-no-appointment-msg`);

  // Clear forms
  document.getElementById(`${which}-new-appointment-date`).value = '';
  document.getElementById(`${which}-reschedule-reason`).value = '';
  document.getElementById(`${which}-date`).value = '';

  const win = _assessmentWindows[`${which}_assessment`];
  const fmt = (s) => new Date(s + 'T00:00:00').toLocaleDateString('en-GB',
    { day: 'numeric', month: 'short', year: 'numeric' });

  if (apptDate) {
    // Appointment already scheduled: show reschedule, cancel, record sections
    const d = new Date(apptDate);
    const dateStr = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' });

    document.getElementById(`${which}-current-appt-display`).textContent = dateStr;
    document.getElementById(`${which}-scheduled-date-display`).textContent = dateStr;
    rescheduleSection.classList.remove('hidden');
    cancelSection.classList.remove('hidden');
    recordSection.classList.remove('hidden');
    noApptMsg.classList.add('hidden');
    document.getElementById(`${which}-mark-missed`).classList.remove('hidden');

    // Apply date bounds to reschedule date input and display window
    const apptInput = document.getElementById(`${which}-new-appointment-date`);
    const windowDisplay = document.getElementById(`${which}-reschedule-window-display`);

    if (win) {
      apptInput.min = win.start.slice(0, 10);
      apptInput.max = win.end.slice(0, 10);
      windowDisplay.textContent = `${fmt(win.start)} → ${fmt(win.end)}`;
    } else {
      apptInput.removeAttribute('min');
      apptInput.removeAttribute('max');
      windowDisplay.textContent = 'Unknown window';
    }
    _attachDateGuard(`${which}-new-appointment-date`, `${which}-error`);
    _attachDateGuard(`${which}-date`, `${which}-error`);
    _setupAssessmentOutOfWindowGuard(which);
  } else {
    // No appointment scheduled yet: assessment is locked (cannot be recorded)
    rescheduleSection.classList.add('hidden');
    cancelSection.classList.add('hidden');
    recordSection.classList.add('hidden');
    noApptMsg.classList.remove('hidden');
    document.getElementById(`${which}-mark-missed`).classList.add('hidden');
  }

  showModal(`${which}-modal`);
  _autoExpandAssessmentSection(which, apptDate);

  // Show appropriate buttons based on initial state
  const recordButtons = document.getElementById(`${which}-record-buttons`);
  const markMissed = document.getElementById(`${which}-mark-missed`);

  if (apptDate) {
    // Appointment exists: show record buttons
    if (recordButtons) recordButtons.classList.remove('hidden');
    if (markMissed) markMissed.classList.remove('hidden');
  } else {
    // No appointment: hide all buttons - assessment is locked
    if (recordButtons) recordButtons.classList.add('hidden');
    if (markMissed) markMissed.classList.add('hidden');
  }
}

// Reveal or hide the out-of-ideal-window reason section based on whether the
// currently-typed assessment date falls inside the protocol's ideal window
// (window_start..window_end on the stub, surfaced via _assessmentWindows). The
// "ideal window" IS the protocol window — same source of truth as the existing
// Delayed badge and overdue calculation, no duplicate definition.
function _setupAssessmentOutOfWindowGuard(which) {
  const dateInput = document.getElementById(`${which}-date`);
  const section   = document.getElementById(`${which}-out-of-window-section`);
  const display   = document.getElementById(`${which}-window-display`);
  const win       = _assessmentWindows[`${which}_assessment`];
  if (!dateInput || !section) return;

  // Surface the human-readable ideal window in the reason block.
  if (win && display) {
    const fmt = (s) => new Date(s + 'T00:00:00').toLocaleDateString('en-GB',
      { day: 'numeric', month: 'short', year: 'numeric' });
    display.textContent = `${fmt(win.start)} → ${fmt(win.end)}`;
  } else if (display) {
    display.textContent = '—';
  }

  const evaluate = () => {
    const v = dateInput.value;
    const outside = v && _isOutsideAssessmentWindow(which, v);
    section.classList.toggle('hidden', !outside);
    if (!outside) document.getElementById(`${which}-out-of-window-reason`).value = '';
  };
  // Replace any prior listener so re-opening the modal doesn't stack handlers.
  if (dateInput._outOfWindowGuard) {
    dateInput.removeEventListener('change', dateInput._outOfWindowGuard);
    dateInput.removeEventListener('input',  dateInput._outOfWindowGuard);
  }
  dateInput._outOfWindowGuard = evaluate;
  dateInput.addEventListener('change', evaluate);
  dateInput.addEventListener('input',  evaluate);
  evaluate();
}

// Toggle assessment section — collapse all, expand one
function toggleAssessmentSection(which, section) {
  const sections = ['reschedule', 'cancel', 'schedule', 'record'];
  const chevrons = ['reschedule-chevron', 'cancel-chevron', 'schedule-chevron', 'record-chevron'];

  sections.forEach((s, i) => {
    const body = document.getElementById(`${which}-${s}-body`);
    const chevron = document.getElementById(`${which}-${chevrons[i]}`);
    const isOpen = s === section;
    if (body) body.classList.toggle('hidden', !isOpen);
    if (chevron) chevron.classList.toggle('fa-chevron-down', isOpen);
    if (chevron) chevron.classList.toggle('fa-chevron-right', !isOpen);
  });

  // Show buttons only in the expanded section
  const recordButtons = document.getElementById(`${which}-record-buttons`);
  const scheduleButtons = document.getElementById(`${which}-schedule-buttons`);
  const markMissed = document.getElementById(`${which}-mark-missed`);

  if (section === 'record') {
    if (recordButtons) recordButtons.classList.remove('hidden');
    if (markMissed) markMissed.classList.remove('hidden');
    if (scheduleButtons) scheduleButtons.classList.add('hidden');
  } else if (section === 'schedule') {
    if (scheduleButtons) scheduleButtons.classList.remove('hidden');
    if (recordButtons) recordButtons.classList.add('hidden');
    if (markMissed) markMissed.classList.add('hidden');
  } else {
    // For reschedule and cancel sections, hide all buttons
    if (recordButtons) recordButtons.classList.add('hidden');
    if (scheduleButtons) scheduleButtons.classList.add('hidden');
    if (markMissed) markMissed.classList.add('hidden');
  }
}

// Auto-expand the first visible relevant section when modal opens
function _autoExpandAssessmentSection(which, apptDate) {
  if (apptDate) {
    // Appointment exists: auto-expand "Reschedule" section
    toggleAssessmentSection(which, 'reschedule');
  } else {
    // No appointment: auto-expand "Schedule" section
    toggleAssessmentSection(which, 'schedule');
  }
}

function openA1AssessmentModal(ev) { _openAssessmentModal('a1', ev); }

function openA2AssessmentModal(ev) {
  // Check if A1 is still incomplete (not missed, not complete)
  const a1Incomplete = (eventsCache || []).some(e => e.protocol_event_id === 'a1_assessment');
  _a2A1MissOkAt = null;
  if (a1Incomplete) {
    const ok = window.confirm(
      'A1 assessment has not been completed.\n\nFiling A2 will automatically mark A1 as missed.\n\nContinue?'
    );
    if (!ok) return;
    // Log OK-press time; A1 is missed only if A2 is committed (filed or marked missed).
    // The gap to the eventual action back-dates A1's filed_at server-side so it sorts before A2.
    _a2A1MissOkAt = Date.now();
  }
  _openAssessmentModal('a2', ev);
}

function openScheduleA1CallModal(ev) {
  _schedA1EventId = ev ? ev.id : null;
  document.getElementById('sa1-date').value        = '';
  document.getElementById('sa1-duration').value    = '';
  document.getElementById('sa1-notes').value       = '';
  document.getElementById('sa1-appointment').value = '';
  setError('sa1-error', '');
  _attachDateGuard('sa1-date', 'sa1-error');
  // Attach guard first (sets max=today), then override with window bounds.
  // _validateDateInput reads min/max at fire time, so the override takes effect.
  _attachDateGuard('sa1-appointment', 'sa1-error');
  const apptInput = document.getElementById('sa1-appointment');
  const win = _assessmentWindows['a1_assessment'];
  if (win) { apptInput.min = win.start; apptInput.max = win.end; }
  else      { apptInput.removeAttribute('min'); apptInput.removeAttribute('max'); }
  showModal('schedule-a1-call-modal');
}

function openScheduleA2CallModal(ev) {
  _schedA2EventId = ev ? ev.id : null;
  document.getElementById('sa2-date').value        = '';
  document.getElementById('sa2-duration').value    = '';
  document.getElementById('sa2-notes').value       = '';
  document.getElementById('sa2-appointment').value = '';
  setError('sa2-error', '');
  _attachDateGuard('sa2-date', 'sa2-error');
  // Attach guard first (sets max=today), then override with window bounds.
  _attachDateGuard('sa2-appointment', 'sa2-error');
  const apptInput = document.getElementById('sa2-appointment');
  const win = _assessmentWindows['a2_assessment'];
  if (win) { apptInput.min = win.start; apptInput.max = win.end; }
  else      { apptInput.removeAttribute('min'); apptInput.removeAttribute('max'); }
  showModal('schedule-a2-call-modal');
}

// Legacy openers used by ACTION_DEFS buttons — delegate to event-driven functions.
function openA1Modal() { openA1AssessmentModal(null); }
function openA2Modal() { openA2AssessmentModal(null); }

let _discEventId = null;

function openDiscontinueModal(ev) {
  _discEventId = ev ? ev.id : null;
  document.getElementById('discontinue-homer-id').textContent = PATIENT_HOMER_ID;
  document.getElementById('disc-date').value = '';
  document.getElementById('discontinue-reason').value = '';
  document.getElementById('discontinue-notes').value = '';
  _resetAttachment('disc');
  setError('discontinue-error', '');
  const now = new Date();
  const maxStr = now.toISOString().slice(0, 16);
  document.getElementById('disc-date').max = maxStr;
  _attachDateGuard('disc-date', 'discontinue-error');
  showModal('discontinue-modal');
}

async function _initiateDiscontinuation() {
  const confirmed1 = window.confirm(
    'Discontinuing a patient is a major and irreversible event.\nAre you sure you want to proceed?'
  );
  if (!confirmed1) return;
  const confirmed2 = window.confirm(
    'This will permanently close the patient record once the discontinuation event is completed.\nConfirm discontinuation?'
  );
  if (!confirmed2) return;

  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/create-discontinuation-stub`, {}
  );
  if (!ok) {
    alert(data.error || 'Failed to create discontinuation stub.');
    return;
  }
  await loadPatientEvents();  // sets _hasDiscontinuationStub = true
  loadPatient();              // re-evaluates button visibility using updated flag
}

// ── Modal submitters ──────────────────────────────────────────────────────────


function _isOutsideAssessmentWindow(which, dateVal) {
  const win = _assessmentWindows[`${which}_assessment`];
  if (!win) return false;
  const d = dateVal.slice(0, 10);
  return d < win.start || d > win.end;
}

// Shared helper for A1/A2: if the date falls outside the ideal window, require
// an explanation in the reason textarea AND a double-confirm. Returns the
// reason string when valid, an empty string when the date is in-window, or
// null when the user cancels or the reason is missing.
function _gateAssessmentOutOfWindow(which, date, label) {
  if (!_isOutsideAssessmentWindow(which, date)) return '';
  const reason = (document.getElementById(`${which}-out-of-window-reason`).value || '').trim();
  if (!reason) {
    setError(`${which}-error`, `Reason is required when the ${label} date is outside the ideal window.`);
    return null;
  }
  const ok = window.confirm(
    `The selected date is outside the ${label} assessment window. Are you sure you want to proceed?`
  );
  return ok ? reason : null;
}

async function saveA1Assessment() {
  const date  = document.getElementById('a1-date').value;
  const notes = document.getElementById('a1-notes').value.trim();
  if (!date) { setError('a1-error', 'Please select an assessment date.'); return; }
  if (_hasDateValidationErrors(['a1-error'])) return;
  const outOfWindowReason = _gateAssessmentOutOfWindow('a1', date, 'A1');
  if (outOfWindowReason === null) return;
  const payload = { completion_date: date, notes };
  if (outOfWindowReason) payload.out_of_window_reason = outOfWindowReason;
  if (_a1AssessmentEventId) payload.event_id = _a1AssessmentEventId;
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/a1-assessment`, payload
  );
  if (!ok) { setError('a1-error', data.error || 'Failed to record A1.'); return; }
  hideModal('a1-modal');
  await loadPatientEvents();
  loadPatient();
}

async function saveA2Assessment() {
  const date  = document.getElementById('a2-date').value;
  const notes = document.getElementById('a2-notes').value.trim();
  if (!date) { setError('a2-error', 'Please select an assessment date.'); return; }
  if (_hasDateValidationErrors(['a2-error'])) return;
  const outOfWindowReason = _gateAssessmentOutOfWindow('a2', date, 'A2');
  if (outOfWindowReason === null) return;
  // A1 is auto-missed atomically by the server (only if A2 is actually filed).
  // Send the measured gap from OK-press so the server back-dates A1's filed_at before A2's.
  const payload = { completion_date: date, notes };
  if (outOfWindowReason) payload.out_of_window_reason = outOfWindowReason;
  if (_a2AssessmentEventId) payload.event_id = _a2AssessmentEventId;
  if (_a2A1MissOkAt != null) payload.a1_miss_gap_seconds = (Date.now() - _a2A1MissOkAt) / 1000;
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/a2-assessment`, payload
  );
  if (!ok) { setError('a2-error', data.error || 'Failed to record A2.'); return; }
  _a2A1MissOkAt = null;
  hideModal('a2-modal');
  await loadPatientEvents();
  loadPatient();
}

async function markAssessmentMissed(which) {
  const label = which.toUpperCase();
  const ok1 = window.confirm(
    `Mark ${label} assessment as missed?\n\nThis indicates the patient confirmed they will not attend.`
  );
  if (!ok1) return;
  const ok2 = window.confirm(
    `Are you sure? Marking ${label} as missed cannot be undone.`
  );
  if (!ok2) return;
  const eventId = which === 'a1' ? _a1AssessmentEventId : _a2AssessmentEventId;
  const payload = { assessment_type: which };
  if (eventId) payload.event_id = eventId;
  // Marking A2 missed also auto-misses a pending A1; back-date A1 by the OK-press gap.
  if (which === 'a2' && _a2A1MissOkAt != null) payload.a1_miss_gap_seconds = (Date.now() - _a2A1MissOkAt) / 1000;
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/miss-assessment`, payload
  );
  if (!ok) { setError(`${which}-error`, data.error || `Failed to mark ${label} as missed.`); return; }
  _a2A1MissOkAt = null;
  hideModal(`${which}-modal`);
  await loadPatientEvents();
  loadPatient();
}

async function cancelAssessmentAppointment(which) {
  const reason = document.getElementById(`${which}-cancel-reason`).value.trim();
  if (!reason) { setError(`${which}-error`, 'Please enter a reason for cancellation.'); return; }

  const scheduledDate = which === 'a1' ? _a1ScheduledDate : _a2ScheduledDate;
  const displayEl     = document.getElementById(`${which}-scheduled-date-display`);
  const confirmed = window.confirm(
    `Cancel the scheduled ${which.toUpperCase()} assessment on ${displayEl.textContent}? This cannot be undone.`
  );
  if (!confirmed) return;

  const eventId = which === 'a1' ? _a1AssessmentEventId : _a2AssessmentEventId;
  const payload = { assessment_type: which, reason };
  if (eventId) payload.event_id = eventId;

  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/cancel-assessment-appointment`, payload
  );
  if (!ok) { setError(`${which}-error`, data.error || 'Failed to cancel appointment.'); return; }

  // Hide cancellation section — appointment_date is now null
  if (which === 'a1') { _a1ScheduledDate = null; }
  else                { _a2ScheduledDate = null; }
  document.getElementById(`${which}-cancel-section`).classList.add('hidden');
  document.getElementById(`${which}-cancel-reason`).value = '';
  setError(`${which}-error`, '');
  await loadPatientEvents();

  // Close modal after successful cancellation
  hideModal(`${which}-modal`);
}

async function scheduleAssessmentAppointmentDirect(which) {
  const errId = `${which}-error`;
  const apptDate = document.getElementById(`${which}-schedule-appointment-date`).value;

  if (!apptDate) { setError(errId, 'Appointment date is required.'); return; }

  const confirmed = window.confirm(
    `Schedule ${which.toUpperCase()} assessment for ${apptDate}?`
  );
  if (!confirmed) return;

  const eventId = which === 'a1' ? _a1AssessmentEventId : _a2AssessmentEventId;
  const payload = {
    assessment_type: which,
    appointment_date: apptDate
  };
  if (eventId) payload.event_id = eventId;

  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/schedule-assessment-appointment`, payload
  );
  if (!ok) { setError(errId, data.error || 'Failed to schedule appointment.'); return; }

  // Update local state
  if (which === 'a1') { _a1ScheduledDate = apptDate + 'T09:00'; }
  else { _a2ScheduledDate = apptDate + 'T09:00'; }

  // Clear form
  document.getElementById(`${which}-schedule-appointment-date`).value = '';
  setError(errId, '');

  // Refresh events and close modal
  await loadPatientEvents();

  // Close modal - user can reopen to record the assessment
  hideModal(`${which}-modal`);
}

async function rescheduleAssessmentAppointment(which) {
  const errId = `${which}-error`;
  const newDate = document.getElementById(`${which}-new-appointment-date`).value;
  const reason = document.getElementById(`${which}-reschedule-reason`).value.trim();

  if (!newDate) { setError(errId, 'New appointment date is required.'); return; }
  if (!reason) { setError(errId, 'Reason for rescheduling is required.'); return; }

  const currentApptEl = document.getElementById(`${which}-current-appt-display`);
  const confirmed = window.confirm(
    `Reschedule ${which.toUpperCase()} assessment from ${currentApptEl.textContent} to ${newDate}?`
  );
  if (!confirmed) return;

  const eventId = which === 'a1' ? _a1AssessmentEventId : _a2AssessmentEventId;
  const payload = {
    assessment_type: which,
    new_appointment_date: newDate,
    reason
  };
  if (eventId) payload.event_id = eventId;

  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/reschedule-assessment-appointment`, payload
  );
  if (!ok) { setError(errId, data.error || 'Failed to reschedule appointment.'); return; }

  // Update local state
  if (which === 'a1') { _a1ScheduledDate = newDate + 'T09:00'; }
  else { _a2ScheduledDate = newDate + 'T09:00'; }

  // Clear form
  document.getElementById(`${which}-new-appointment-date`).value = '';
  document.getElementById(`${which}-reschedule-reason`).value = '';
  setError(errId, '');

  // Refresh events and close modal
  await loadPatientEvents();

  // Close modal after successful reschedule
  hideModal(`${which}-modal`);
}

async function saveScheduleAssessmentCall(which) {
  const prefix   = which === 'a1' ? 'sa1' : 'sa2';
  const errId    = `${prefix}-error`;
  const callType = which === 'a1' ? 'schedule_a1_call' : 'schedule_a2_call';
  const eventId  = which === 'a1' ? _schedA1EventId : _schedA2EventId;

  const date    = document.getElementById(`${prefix}-date`).value;
  const dur     = document.getElementById(`${prefix}-duration`).value;
  const notes   = document.getElementById(`${prefix}-notes`).value.trim();
  const appt    = document.getElementById(`${prefix}-appointment`).value;

  if (!date)  { setError(errId, 'Call date is required.'); return; }
  if (!dur || parseInt(dur, 10) <= 0) { setError(errId, 'Duration must be a positive number.'); return; }
  if (!notes) { setError(errId, 'Notes are required.'); return; }
  if (!appt)  { setError(errId, 'New appointment date is required.'); return; }
  if (_hasDateValidationErrors([errId])) return;

  const payload = {
    call_type:          callType,
    completion_date:    date,
    duration_minutes:   parseInt(dur, 10),
    notes,
    new_appointment_date: appt,
  };
  if (eventId) payload.event_id = eventId;

  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/schedule-assessment-call`, payload
  );
  if (!ok) { setError(errId, data.error || 'Failed to save scheduling call.'); return; }
  hideModal(which === 'a1' ? 'schedule-a1-call-modal' : 'schedule-a2-call-modal');
  await loadPatientEvents();
}

async function saveDiscontinuation() {
  const date   = document.getElementById('disc-date').value;
  const reason = document.getElementById('discontinue-reason').value.trim();
  const notes  = document.getElementById('discontinue-notes').value.trim();
  const btn    = document.getElementById('discontinue-submit');

  if (!date)   { setError('discontinue-error', 'Please select a discontinuation date.'); return; }
  if (!reason) { setError('discontinue-error', 'Please enter a reason.'); return; }
  if (!_validateAttachment('disc', 'discontinue-error')) return;

  if (!window.confirm('This will permanently close the patient record and all device assignments. Are you sure?')) return;

  btn.disabled = true;
  setError('discontinue-error', '');
  const payload = { completion_date: date, reason, notes: notes || null };
  if (_discEventId && _discEventId !== 'discontinuation_reminder') {
    payload.event_id = _discEventId;
  }

  let ok, data;
  try {
    ({ ok, data } = await apiPost(`/api/patients/${PATIENT_HOMER_ID}/discontinue`, payload));
  } catch (e) {
    setError('discontinue-error', 'Server error — could not save discontinuation. Check the server logs.');
    btn.disabled = false;
    return;
  }
  if (!ok) { setError('discontinue-error', data?.error || 'Failed to discontinue patient.'); btn.disabled = false; return; }

  if (data.event_id) {
    const { file, caption } = _readAttachment('disc');
    if (file) {
      const uploaded = await _uploadAttachment(data.event_id, file, caption, 'discontinue-error');
      if (!uploaded) { btn.disabled = false; return; }
    }
  }

  hideModal('discontinue-modal');
  btn.disabled = false;
  await loadPatientEvents();
  loadPatient();
}

// ── Patient events ────────────────────────────────────────────────────────────

let _completeEventsCache    = null;   // null = not yet loaded
let _callLogsCache          = null;   // null = not yet loaded
let _patientDiscontinued    = false;  // true if patient has discontinuationDate
let _hasDiscontinuationStub = false;  // true if a real discontinuation stub is in incomplete
let _assessmentWindows      = {};     // { a1_assessment: {start, end}, a2_assessment: {start, end} }

async function loadPatientEvents() {
  const completedEl = document.getElementById('patient-completed-events');
  const overdueEl   = document.getElementById('patient-overdue-events');
  const upcomingEl  = document.getElementById('patient-upcoming-events');
  try {
    const [evRes, patRes] = await Promise.all([
      fetch(`/api/patients/${PATIENT_HOMER_ID}/events`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}`),
    ]);
    if (!evRes.ok) throw new Error('Failed to load events');
    const { overdue, upcoming, complete } = await evRes.json();
    if (patRes.ok) patientData = await patRes.json();
    eventsCache = [...overdue, ...upcoming];
    _completeEventsCache = complete || [];
    _callLogsCache = null;  // invalidate so call logs tab re-fetches

    // Cache assessment window bounds for use in scheduling call modals.
    _assessmentWindows = {};
    for (const e of eventsCache) {
      if ((e.protocol_event_id === 'a1_assessment' || e.protocol_event_id === 'a2_assessment')
          && e.window_start && e.window_end) {
        _assessmentWindows[e.protocol_event_id] = {
          start: e.window_start.slice(0, 10),
          end:   e.window_end.slice(0, 10),
        };
      }
    }
    _hasDiscontinuationStub = overdue.some(e => e.protocol_event_id === 'discontinuation');

    // Re-render overview now that _assessmentWindows is populated (needed for Delayed badge in key dates)
    if (patientData) renderOverview(patientData);

    // Set discontinued flag and show banner if patient is discontinued
    _patientDiscontinued = !!patientData?.discontinuationDate;
    const discontinuedBanner = document.getElementById('discontinued-readonly-banner');
    if (_patientDiscontinued && discontinuedBanner) {
      discontinuedBanner.classList.remove('hidden');
    } else if (!_patientDiscontinued && discontinuedBanner) {
      discontinuedBanner.classList.add('hidden');
    }
    _renderPauseReasonPills();
    // Re-render pause banner, at-risk banner, and history table with updated patient data
    renderPauseBanner(patientData);
    _checkD0203AtRisk(patientData);
    _checkTrainingPeriodExpired(patientData);
    renderPauseHistoryTable(patientData);
    renderTimelineTab();
    renderAdverseEventsTab();
    renderWatchRecordsTab();
    renderDeviceIssuesTab();

    document.getElementById('patient-completed-count').textContent = (complete || []).length;
    document.getElementById('patient-overdue-count').textContent   = overdue.length;
    document.getElementById('patient-upcoming-count').textContent  = upcoming.length;

    completedEl.innerHTML = complete && complete.length
      ? completedTimeline(complete)
      : emptyEventState('hourglass-start', 'text-slate-300', 'No events completed yet');
    overdueEl.innerHTML  = overdue.length  ? overdue.map(patientEventRow).join('')
                                           : emptyEventState('check-circle', 'text-green-500', 'No overdue events');
    upcomingEl.innerHTML = upcoming.length ? upcoming.map(patientEventRow).join('')
                                           : emptyEventState('calendar-check', 'text-slate-400', 'No upcoming events');
  } catch (e) {
    console.error('Error loading patient events:', e);
    completedEl.innerHTML = '<p class="text-xs text-red-500 text-center py-4">Error loading events</p>';
    overdueEl.innerHTML   = '<p class="text-xs text-red-500 text-center py-4">Error loading events</p>';
    upcomingEl.innerHTML  = '<p class="text-xs text-red-500 text-center py-4">Error loading events</p>';
  }
}

function _dayNumber(completionDate) {
  const actRaw = patientData?.activationDate;
  if (!actRaw || !completionDate) return null;
  const act  = new Date(actRaw.replace(' ', 'T'));
  const comp = new Date(completionDate.replace(' ', 'T'));
  if (isNaN(act) || isNaN(comp)) return null;
  return Math.round((comp - act) / 86400000) + 1;
}

function _fmtDateTime(raw) {
  if (!raw) return '—';
  const d = new Date(raw.replace(' ', 'T'));
  if (isNaN(d)) return raw;
  const date = d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
  const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  return `${date} · ${time}`;
}

function _fmtDate(raw) {
  if (!raw) return '—';
  if (Array.isArray(raw)) {
    const start = _fmtDate(raw[0]);
    const end   = _fmtDate(raw[1]);
    return raw[0] === raw[1] ? start : `${start} – ${end}`;
  }
  const d = new Date(raw.replace(' ', 'T'));
  return isNaN(d) ? raw : d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

// Newest-first comparator for completed-event lists. Primary key is
// completion_date (falling back to filed_at when absent — synthetic milestones,
// legacy data); tiebreaker is filed_at descending so events that share a
// clinical date appear in reverse filing order (last filed at the top). Mirrors
// the server-side sort in routes/user_management.py — keep the two in sync.
function _cmpCompletedDesc(a, b) {
  const ka = a.completion_date || a.filed_at || '';
  const kb = b.completion_date || b.filed_at || '';
  const c = kb.localeCompare(ka);
  if (c !== 0) return c;
  return (b.filed_at || '').localeCompare(a.filed_at || '');
}

// Should a completed event's "Filed: ..." secondary line be shown? True whenever
// filed_at is recorded — the line surfaces who/when the event was filed even on
// same-day filings (useful for audit). watch_data_upload is the one exception:
// its completion_date equals filed_at[:16] by construction (the upload time IS
// the completion time), so the second line would be pure repetition.
function _showFiledLine(ev) {
  if (!ev?.filed_at || !ev.completion_date) return false;
  if (ev.protocol_event_id === 'watch_data_upload') return false;
  return true;
}

// Fields always rendered in the main timeline layout — skip in extra fields
const _TIMELINE_BASE_FIELDS = new Set([
  'id', 'protocol_event_id', 'event_name', 'scheduled_date',
  'completion_date', 'filed_at', 'flagged', '_synthetic',
  'attachment', 'attachment_caption',
  // UUID-carrying internal references: human users don't need to see these
  // on the Timeline — they live elsewhere as aliases (AE##, RI##, etc.).
  'adverse_event_ids', 'related_patient_call_id', 'triggered_by_id',
  'event_notes',  // role-private; server strips but skip defensively
]);

// Matches v4-style UUIDs. Used to defensively skip any row whose value (or
// every element of whose array value) is just a raw UUID — those are internal
// references and never useful to show in the Timeline.
const _UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const _isUuid  = (s) => typeof s === 'string' && _UUID_RE.test(s);

// Preferred display order for known extra fields. 'notes' is always rendered last.
const _FIELD_ORDER = [
  'pluto_id', 'mars_id', 'demo_done',
  'ag_watch_right', 'ag_watch_left',
  'prescription_file',
  'description', 'action_taken', 'training_blocked',
  'visit_start', 'visit_end',
  'duration_minutes',
  'ae_discussions',
];

const _FIELD_LABELS = {
  ag_watch_right:      'Right Watch',
  ag_watch_left:       'Left Watch',
  pluto_id:            'Pluto Device',
  mars_id:             'Mars Device',
  modem_id:            'Modem Device',
  laptop_id:           'Laptop Device',
  sim_id:              'SIM Card',
  demo_done:           'Demo Done',
  prescription_file:   'Prescription File',
  duration_minutes:    'Duration',
  worn_datetime:       'Worn Date/Time',
  sync_datetime:       'Sync Date/Time',
  next_followup_days:  'Next Follow-up (days)',
  description:         'Description',
  action_taken:        'Action Taken',
  date_change_reason:  'Date Change Reason',
  out_of_window_reason: 'Out-of-window Reason',
  triggered_by:        'Triggered By',
  triggered:           'Triggered',
  faults:              'Faults',
  devices:             'Devices',
  device_outcomes:      'Device Outcomes',
  device_replacements:  'Device Replacements',
  other_device_outcomes: 'Other Device Outcomes',
  visit_required:       'Visit Required',
  visit_start:          'Visit Start',
  visit_end:            'Visit End',
  ae_discussions:       'AE Discussions',
  training_blocked:     'Training Blocked',
  paused:              'Paused',
  watch_id:            'Watch',
  limb:                'Limb',
  removed_date:        'Removed',
  data_start:          'Data From',
  data_end:            'Data To',
  data_file:           'Data File',
  original_filename:   'File Name',
  skipped:             'Skipped (no data)',
  notes:               'Notes',
};

function _timelineExtraFields(ev) {
  const known   = new Set(_FIELD_ORDER);
  const ordered = [
    ..._FIELD_ORDER,
    ...Object.keys(ev).filter(k => !known.has(k) && k !== 'notes'),
    'notes',
  ];

  const rows = [];
  for (const key of ordered) {
    if (_TIMELINE_BASE_FIELDS.has(key) || !(key in ev)) continue;
    const val = ev[key];
    if (val === null || val === undefined || val === '' || val === false) continue;
    if (Array.isArray(val) && val.length === 0) continue;
    // Watch data upload: the download link already shows the filename — skip the dup row.
    if (key === 'original_filename' && ev.data_file) continue;
    // Suppress any row whose value is just a UUID (or list of UUIDs) — these
    // are internal references with no human meaning on the Timeline.
    if (_isUuid(val)) continue;
    if (Array.isArray(val) && val.every(_isUuid)) continue;
    const label = _FIELD_LABELS[key] || key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
    let display;
    if (typeof val === 'boolean') {
      display = val ? 'Yes' : 'No';
    } else if (key === 'triggered_by' && val && typeof val === 'object') {
      const typeLabel   = _WR_TRIGGER_NAMES[val.type] || (val.type || '').replace(/_/g, ' ');
      const triggerEv   = (_completeEventsCache || []).find(e => e.id === val.id);
      const triggerDate = triggerEv?.completion_date ? ` — ${_fmtDateTime(triggerEv.completion_date)}` : '';
      display = typeLabel + triggerDate;
    } else if (key === 'triggered' && Array.isArray(val)) {
      if (!val.length) continue;
      display = val.map(t => _TRIGGERED_LABELS[t.type] || (t.type || '').replace(/_/g, ' ')).join(', ');
    } else if (key === 'faults' && Array.isArray(val)) {
      if (!val.length) continue;
      display = val.map(f => `${f.device}: ${f.fault_description}`).join('; ');
    } else if (key === 'devices' && Array.isArray(val)) {
      if (!val.length) continue;
      display = val.map(d => {
        const dev     = (d.device || '').charAt(0).toUpperCase() + (d.device || '').slice(1);
        const outcome = d.outcome === 'visit_required' ? 'Visit required' : 'Resolved';
        return d.notes ? `${dev}: ${outcome} (${d.notes})` : `${dev}: ${outcome}`;
      }).join('; ');
    } else if ((key === 'device_outcomes' || key === 'other_device_outcomes') && Array.isArray(val)) {
      if (!val.length) continue;
      display = val.map(d => {
        const dev = (d.device || '').charAt(0).toUpperCase() + (d.device || '').slice(1);
        if (d.outcome === 'repaired_on_site') {
          return d.notes ? `${dev}: Repaired (${d.notes})` : `${dev}: Repaired`;
        } else if (d.outcome === 'swapped') {
          const from     = d.old_device_id || '—';
          const to       = d.new_device_id || 'none';
          const swapDesc = d.swap_type === 'fault_driven' ? 'fault-driven' : d.swap_type === 'preventive' ? 'preventive' : '';
          const note     = d.notes ? ` — ${d.notes}` : '';
          const typeTag  = swapDesc ? ` [${swapDesc}]` : '';
          return `${dev}: Swapped ${from} → ${to}${typeTag}${note}`;
        } else if (d.outcome === 'neither') {
          return d.notes ? `${dev}: No action (${d.notes})` : `${dev}: No action`;
        }
        return `${dev}: ${d.outcome || '—'}`;
      }).join('; ');
    } else if (key === 'device_replacements' && Array.isArray(val)) {
      if (!val.length) continue;
      display = val.map(d => {
        const dev  = (d.device || '').charAt(0).toUpperCase() + (d.device || '').slice(1);
        const from = d.old_device_id || '—';
        const to   = d.new_device_id || 'none';
        const note = d.notes ? ` (${d.notes})` : '';
        return `${dev}: ${from} → ${to}${note}`;
      }).join('; ');
    } else if (key === 'ae_discussions' && Array.isArray(val)) {
      if (!val.length) continue;
      display = val.map(r => {
        const status = r.resolved ? '✓ Resolved' : '○ Ongoing';
        const resume = r.can_resume_from ? ` (resume from ${r.can_resume_from})` : '';
        const disc   = r.notes ? ` — ${r.notes}` : '';
        return `${status}${resume}${disc}`;
      }).join('; ');
    } else if (key === 'duration_minutes') {
      display = `${val} min`;
    } else if (key === 'data_file' && ev.id) {
      // .gt3x watch data → download link (admin/therapist/engineer)
      display = `<a href="/api/patients/${PATIENT_HOMER_ID}/watch-data/${ev.id}" target="_blank" ` +
                `class="text-blue-600 hover:underline">${ev.original_filename || val.split('/').pop()}</a>`;
    } else if (Array.isArray(val)) {
      display = val.join(', ');
    } else if (val && typeof val === 'object' && 'new_id' in val) {
      const nw = val.new_id ?? 'None';
      display = val.old_id ? `${val.old_id} → ${nw}` : nw;
    } else if (typeof val === 'string' && val.includes('/')) {
      display = val.split('/').pop();
    } else {
      display = String(val);
    }
    rows.push(`<div class="flex gap-1.5 text-xs"><span class="text-slate-400 shrink-0">${label}:</span><span class="text-slate-700">${display}</span></div>`);
  }
  // Attachment: render as download link with caption
  if (ev.attachment && ev.id) {
    rows.push(
      `<div class="flex gap-1.5 text-xs"><span class="text-slate-400 shrink-0">Attachment:</span>` +
      `<a href="/api/patients/${PATIENT_HOMER_ID}/download-attachment/${ev.id}" ` +
      `target="_blank" class="text-blue-600 hover:underline">Download PDF</a></div>`
    );
    if (ev.attachment_caption) {
      rows.push(
        `<div class="flex gap-1.5 text-xs"><span class="text-slate-300 shrink-0">Caption:</span>` +
        `<span class="text-slate-400">${ev.attachment_caption}</span></div>`
      );
    }
  }

  return rows.length
    ? `<div class="mt-2 space-y-0.5">${rows.join('')}</div>`
    : '';
}

// ── Attachment helpers ─────────────────────────────────────���──────────────────

function _resetAttachment(prefix) {
  const fi = document.getElementById(`${prefix}-attachment-file`);
  const ci = document.getElementById(`${prefix}-attachment-caption`);
  if (fi) fi.value = '';
  if (ci) { ci.value = ''; ci.disabled = true; }
  if (fi && ci) {
    fi.onchange = () => {
      ci.disabled = !fi.files.length;
      if (!fi.files.length) ci.value = '';
    };
  }
}

function _readAttachment(prefix) {
  const fi = document.getElementById(`${prefix}-attachment-file`);
  const ci = document.getElementById(`${prefix}-attachment-caption`);
  return {
    file:    fi?.files?.[0] || null,
    caption: ci?.value.trim() || '',
  };
}

function _validateAttachment(prefix, errorId) {
  const { file, caption } = _readAttachment(prefix);
  if (file && !caption) {
    setError(errorId, 'Please describe the attachment before saving.');
    return false;
  }
  return true;
}

async function _uploadAttachment(eventId, file, caption, errorId) {
  const form = new FormData();
  form.append('event_id', eventId);
  form.append('caption',  caption);
  form.append('file',     file);
  const res  = await fetch(`/api/patients/${PATIENT_HOMER_ID}/upload-attachment`, {
    method: 'POST',
    body:   form,
  });
  const data = await res.json();
  if (!res.ok) { setError(errorId, data.error || 'Failed to upload attachment.'); return false; }
  return true;
}

async function _uploadAttachmentNoCaption(eventId, file, errorId) {
  const form = new FormData();
  form.append('event_id', eventId);
  form.append('caption',  '');  // Empty caption for informed consent
  form.append('file',     file);
  const res  = await fetch(`/api/patients/${PATIENT_HOMER_ID}/upload-attachment`, {
    method: 'POST',
    body:   form,
  });
  const data = await res.json();
  if (!res.ok) { setError(errorId, data.error || 'Failed to upload attachment.'); return false; }
  return true;
}

function _syntheticPatientEvents() {
  const synthetic = [];
  if (patientData?.enrollDate) {
    synthetic.push({
      event_name:      'Patient Enrolled',
      completion_date: patientData.enrollDate,
      filed_at:        patientData.enrollDate,
      scheduled_date:  null,
      _synthetic:      true,
    });
  }
  if (patientData?.a0CompletionDate) {
    synthetic.push({
      event_name:      'A0 Assessment',
      completion_date: patientData.a0CompletionDate,
      filed_at:        patientData.a0CompletionDate,
      scheduled_date:  null,
      _synthetic:      true,
    });
  }
  return synthetic;
}

function _deriveTransitions(patient, events) {
  const map = new Map();
  const pauseHistory = patient.pauseHistory || [];

  // Events that triggered a pause — id in pauseHistory[*].reasons[*].event_id
  const pausingIds = new Set();
  for (const epoch of pauseHistory) {
    for (const reason of (epoch.reasons || [])) {
      if (reason.event_id) pausingIds.add(reason.event_id);
    }
  }

  const brokenDate     = (patient.brokenProtocolDate     || '').slice(0, 10);
  const discDate       = (patient.discontinuationDate    || '').slice(0, 10);
  const completionDate = (patient.trainingCompletionDate || '').slice(0, 10);

  // Suppress "Training resumed" if the pause cleared on or after any terminal date.
  const resumingIds = new Set();
  for (const epoch of pauseHistory) {
    if (!epoch.end_event_id || !epoch.end) continue;
    const epochEnd = epoch.end.slice(0, 10);
    if (completionDate && epochEnd >= completionDate) continue;
    if (brokenDate     && epochEnd >= brokenDate)     continue;
    if (discDate       && epochEnd >= discDate)        continue;
    resumingIds.add(epoch.end_event_id);
  }

  for (const ev of events) {
    if (ev._synthetic || !ev.id) continue;
    if (pausingIds.has(ev.id)) {
      map.set(ev.id, 'paused');
    } else if (resumingIds.has(ev.id)) {
      map.set(ev.id, 'resumed');
    } else if (brokenDate && (ev.completion_date || '').slice(0, 10) === brokenDate) {
      map.set(ev.id, 'broken_protocol');
    } else if (discDate && (ev.completion_date || '').slice(0, 10) === discDate) {
      map.set(ev.id, 'discontinued');
    }
  }
  return map;
}

function _transitionBadgeHtml(badge) {
  const cfg = {
    paused:          { label: 'Training paused', cls: 'bg-amber-100 text-amber-700 border-amber-200' },
    resumed:         { label: 'Training resumed', cls: 'bg-green-100 text-green-700 border-green-200' },
    broken_protocol: { label: 'Protocol broken',  cls: 'bg-red-100 text-red-700 border-red-200' },
    discontinued:    { label: 'Discontinued',      cls: 'bg-slate-100 text-slate-600 border-slate-200' },
  }[badge];
  if (!cfg) return '';
  return `<span class="inline-block mt-2 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.cls}">${cfg.label}</span>`;
}

// ── Timeline (master–detail) ───────────────────────────────────────────────────

let _timelineEvents      = [];     // sorted events backing the master list
let _timelineTransitions = null;   // Map<event_id, badge>
let _timelineSchedMap    = {};     // protocol_event_id → scheduled_date (for attempt fallback)
let _timelineSelectedIdx = null;   // currently selected master-row index
let _timelineSelectedId  = null;   // id of the selected real event (for restore across re-render)
const _ATTEMPT_PARENT    = { d15_attempt: 'home_visit_d15', activation_attempt: 'activation' };

function _eventSchedDate(ev) {
  return ev.scheduled_date
    || (_ATTEMPT_PARENT[ev.protocol_event_id] ? _timelineSchedMap[_ATTEMPT_PARENT[ev.protocol_event_id]] : null);
}

// Shared per-event presentation bits (circle colour, badges, flags).
function _timelineEventMeta(ev, transitions) {
  const isSynthetic = !!ev._synthetic;
  const isDisc      = ev.protocol_event_id === 'discontinuation';
  const isAssessmentEv = ev.protocol_event_id === 'a1_assessment' || ev.protocol_event_id === 'a2_assessment';
  const isMissed    = isAssessmentEv && !!ev.missed;
  const isDelayed   = isAssessmentEv && !isMissed && !!ev.completion_date && Array.isArray(ev.scheduled_date)
                      && ev.completion_date.slice(0, 10) > ev.scheduled_date[1].slice(0, 10);
  const circleCls   = isSynthetic ? 'bg-blue-500 ring-blue-300'
                    : isDisc      ? 'bg-red-500 ring-red-300'
                    : isMissed    ? 'bg-slate-400 ring-slate-300'
                    :               'bg-green-500 ring-green-300';
  const transBadge  = !isSynthetic ? _transitionBadgeHtml(transitions ? transitions.get(ev.id) : null) : '';
  const discBadge   = isDisc
    ? `<span class="inline-flex items-center gap-1 text-xs font-semibold bg-red-100 text-red-700 border border-red-200 rounded-full px-2 py-0.5"><i class="fas fa-ban text-[10px]"></i>Discontinued</span>` : '';
  const missedBadge = isMissed
    ? `<span class="inline-flex items-center gap-1 text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-300 rounded-full px-2 py-0.5"><i class="fas fa-times-circle text-[10px]"></i>Missed</span>` : '';
  const delayedBadge = isDelayed
    ? `<span class="inline-flex items-center gap-1 text-xs font-semibold bg-amber-100 text-amber-700 border border-amber-200 rounded-full px-2 py-0.5"><i class="fas fa-clock text-[10px]"></i>Delayed</span>` : '';
  return {
    isSynthetic, isDisc,
    isReal: !isSynthetic && !!ev.id,
    circleCls,
    badges: `${transBadge}${discBadge}${missedBadge}${delayedBadge}`,
  };
}

function renderTimelineTab() {
  const container = document.getElementById('timeline-tab-content');
  if (!container) return;

  // Merge protocol events with synthetic patient milestones, sort most-recent first
  const all = [...(_completeEventsCache || []), ..._syntheticPatientEvents()];
  all.sort(_cmpCompletedDesc);
  _timelineEvents = all;

  if (!all.length) {
    container.innerHTML = `
      <div class="flex flex-col items-center justify-center py-16 text-slate-300">
        <i class="fas fa-stream text-3xl mb-3"></i>
        <p class="text-sm">No completed events yet.</p>
      </div>`;
    return;
  }

  _timelineTransitions = _deriveTransitions(patientData || {}, all);
  _timelineSchedMap = {};
  for (const e of (eventsCache || [])) {
    if (e.protocol_event_id && e.scheduled_date) _timelineSchedMap[e.protocol_event_id] = e.scheduled_date;
  }

  const rows = all.map((ev, i) =>
    _timelineMasterRow(ev, i, i === all.length - 1, _timelineEventMeta(ev, _timelineTransitions))
  ).join('');

  // Two-pane, centered group (margins on wide screens — not full width). The original
  // rich timeline keeps its width on the left; the detailed notes view sits on the right.
  container.innerHTML = `
    <div class="flex h-full justify-center gap-8 px-6 py-4">
      <div class="flex-1 min-w-0 max-w-[640px] overflow-y-auto overflow-x-hidden pr-1">${rows}</div>
      <div id="timeline-detail" class="flex-1 min-w-0 max-w-[400px] overflow-y-auto overflow-x-hidden border-l border-slate-200 pl-8">
        ${_timelineDetailPlaceholder()}
      </div>
    </div>`;

  // Restore the previous selection by id (index may shift); else show the placeholder.
  let restoreIdx = null;
  if (_timelineSelectedId != null) {
    const i = all.findIndex(e => e.id === _timelineSelectedId);
    if (i >= 0) restoreIdx = i;
  }
  if (restoreIdx != null) {
    _selectTimelineEvent(restoreIdx);
  } else {
    _timelineSelectedIdx = null;
    _timelineSelectedId  = null;
  }
}

// Original rich 3-column row (name/scheduled/day/badges | line | completion/filed/extra),
// made selectable: hover highlight + click → detail. Synthetic rows are not selectable.
function _timelineMasterRow(ev, i, isLast, meta) {
  const schedDate = _eventSchedDate(ev);
  const schedStr  = _fmtDate(schedDate);
  const compStr   = ev.completion_date ? _fmtDateTime(ev.completion_date) : '—';
  const filedStr  = _showFiledLine(ev) ? _fmtDateTime(ev.filed_at) : '';
  const extra     = _timelineExtraFields(ev);
  const dayNum    = _dayNumber(ev.completion_date);
  const dayLabel  = dayNum !== null ? `Day ${dayNum}` : null;
  const rowBg     = i % 2 === 1 ? 'bg-slate-100' : '';
  const rowHighlight = meta.isDisc ? 'bg-red-50' : rowBg;
  const nameCls   = meta.isDisc ? 'text-sm font-bold text-red-700' : 'text-sm font-semibold text-slate-800';
  const selectable  = meta.isReal;
  const interactive = selectable ? 'cursor-pointer hover:bg-blue-100' : '';
  const selCls      = (_timelineSelectedIdx === i) ? 'ring-1 ring-blue-400 ring-inset' : '';
  const click       = selectable ? `onclick="_selectTimelineEvent(${i})"` : '';
  const noteCount   = ev.event_notes_count || 0;
  const noteBadge   = noteCount > 0
    ? `<span class="inline-flex items-center gap-1 text-[11px] font-medium bg-blue-50 text-blue-700 border border-blue-200 rounded-full px-2 py-0.5" title="${noteCount} note${noteCount === 1 ? '' : 's'}"><i class="fas fa-sticky-note text-[10px]"></i>${noteCount}</span>`
    : '';
  const badgeRow    = (meta.badges || noteBadge)
    ? `<div class="flex flex-wrap justify-end gap-1 mt-1">${meta.badges}${noteBadge}</div>`
    : '';
  return `
    <div ${click} data-tlrow="${i}"
         class="grid gap-x-4 px-2 -mx-2 rounded-lg transition-colors ${rowHighlight} ${interactive} ${selCls}"
         style="grid-template-columns:1fr 20px 1fr">
      <div class="text-right pb-${isLast ? '2' : '4'} pt-2">
        <p class="${nameCls}">${ev.event_name}</p>
        ${!meta.isSynthetic && schedDate ? `<p class="text-xs text-slate-400 mt-0.5">Scheduled: ${schedStr}</p>` : ''}
        ${dayLabel ? `<p class="text-sm font-semibold text-indigo-500 mt-1">${dayLabel}</p>` : ''}
        ${badgeRow}
      </div>
      <div class="flex flex-col items-center pt-2">
        <div class="w-3 h-3 rounded-full ${meta.circleCls} border-2 border-white ring-1 z-10 flex-shrink-0"></div>
        ${isLast ? '' : '<div class="flex-1 w-0.5 bg-green-200 -mb-2"></div>'}
      </div>
      <div class="flex flex-col pb-${isLast ? '2' : '4'} pt-2">
        <p class="text-xs font-medium text-slate-700">${compStr}</p>
        ${filedStr ? `<p class="text-xs text-slate-400 mt-0.5">Filed: ${filedStr}</p>` : ''}
        ${extra}
        ${ev.filed_by ? `<p class="text-[10px] italic text-slate-400 text-right mt-1 pr-3">– filed by ${ev.filed_by === userLoginId ? 'You' : _esc(ev.filed_by)}</p>` : ''}
      </div>
    </div>`;
}

function _timelineDetailPlaceholder() {
  return `
    <div class="flex flex-col items-center justify-center h-full text-slate-300 text-center px-6">
      <i class="fas fa-hand-pointer text-3xl mb-3"></i>
      <p class="text-sm">Select an event to see its notes.</p>
    </div>`;
}

function _selectTimelineEvent(idx) {
  const ev = _timelineEvents[idx];
  if (!ev) return;
  _timelineSelectedIdx = idx;
  _timelineSelectedId  = ev.id || null;
  document.querySelectorAll('[data-tlrow]').forEach(el => {
    const on = Number(el.dataset.tlrow) === idx;
    el.classList.toggle('ring-1', on);
    el.classList.toggle('ring-blue-400', on);
    el.classList.toggle('ring-inset', on);
  });
  _renderTimelineDetail(ev);
}

// Right pane: a compact event header + the detailed notes view. Event details stay
// inline in the timeline rows (left), so they're not duplicated here.
function _renderTimelineDetail(ev) {
  const panel = document.getElementById('timeline-detail');
  if (!panel) return;
  const meta    = _timelineEventMeta(ev, _timelineTransitions);
  const compStr = ev.completion_date ? _fmtDateTime(ev.completion_date)
                : (ev.filed_at ? _fmtDateTime(ev.filed_at) : '—');
  const nameCls = meta.isDisc ? 'text-lg font-bold text-red-700' : 'text-lg font-bold text-slate-800';

  const head = `
    <div class="flex items-start gap-2 pb-3 border-b border-slate-100">
      <div class="w-3 h-3 rounded-full ${meta.circleCls} border-2 border-white ring-1 mt-1.5 flex-shrink-0"></div>
      <div class="min-w-0">
        <p class="${nameCls}">${ev.event_name}</p>
        <p class="text-xs text-slate-400 mt-0.5">${compStr}</p>
        ${meta.badges ? `<div class="flex flex-wrap gap-1 mt-1">${meta.badges}</div>` : ''}
      </div>
    </div>`;
  const notesSection = meta.isReal
    ? `<div id="timeline-detail-notes" class="mt-4"><div class="text-xs text-slate-400">Loading notes…</div></div>`
    : `<p class="text-xs text-slate-400 italic mt-4">Notes can't be added to this milestone.</p>`;

  panel.innerHTML = `<div class="pb-6">${head}${notesSection}</div>`;
  if (meta.isReal) _loadTimelineDetailNotes(ev.id);
}

async function _loadTimelineDetailNotes(eventId) {
  const box = document.getElementById('timeline-detail-notes');
  if (!box) return;
  const { ok, data } = await apiGet(`/api/patients/${PATIENT_HOMER_ID}/events/${eventId}/notes`);
  if (!ok) {
    box.innerHTML = `<p class="text-xs text-red-500">${_esc(data.error || 'Failed to load notes.')}</p>`;
    return;
  }
  const notes   = data.notes || [];
  const isAdmin = !!data.is_admin;
  const cards = notes.length
    ? notes.map(n => _eventNoteCard(n, isAdmin)).join('')
    : `<p class="text-xs text-slate-400 italic">No notes on this event yet.</p>`;
  // Distinct, tinted block so the notes stand apart from the event header/details.
  box.innerHTML = `
    <div class="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <div class="flex items-center justify-between mb-3">
        <span class="inline-flex items-center gap-2 text-sm font-semibold text-slate-700">
          <i class="fas fa-sticky-note text-blue-500"></i> Notes${notes.length ? `<span class="text-xs font-medium text-slate-400">(${notes.length})</span>` : ''}
        </span>
        <button type="button" onclick="openEventNoteModal('${eventId}')"
          class="inline-flex items-center gap-1 px-2.5 py-1.5 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700">
          <i class="fas fa-plus text-[10px]"></i> Add Note
        </button>
      </div>
      ${cards}
    </div>`;
}

// ── Call Logs tab ─────────────────────────────────────────────────────────────

async function renderCallLogsTab() {
  const container = document.getElementById('call-logs-content');
  if (!container) return;
  if (_callLogsCache) { _renderCallLogs(container, _callLogsCache); return; }

  container.innerHTML = `<div class="flex items-center justify-center py-16 text-slate-300"><p class="text-sm">Loading…</p></div>`;

  try {
    const res  = await fetch(`/api/patients/${PATIENT_HOMER_ID}/call-logs`);
    const data = await res.json();
    _callLogsCache = data;
    _renderCallLogs(container, data);
  } catch {
    container.innerHTML = `<p class="text-sm text-red-500 p-4">Failed to load call logs.</p>`;
  }
}

function _renderCallLogs(container, data) {
  const all = [
    ...(data.followup_calls    || []).map(c => ({ ...c, _callType: 'followup'    })),
    ...(data.patient_calls     || []).map(c => ({ ...c, _callType: 'patient'     })),
    ...(data.ae_followup_calls || []).map(c => ({ ...c, _callType: 'ae_followup' })),
  ];
  all.sort(_cmpCompletedDesc);

  if (!all.length) {
    container.innerHTML = `
      <div class="flex flex-col items-center justify-center py-16 text-slate-300">
        <i class="fas fa-phone text-3xl mb-3"></i>
        <p class="text-sm">No calls recorded yet.</p>
      </div>`;
    return;
  }
  container.innerHTML = all.map(_callCard).join('');
}

const _TRIGGERED_LABELS = {
  adverse_event: 'Adverse event logged',
  robot_issue_call: 'Robot issue call logged',
  watch_record:  'Watch record triggered',
};

function _callCard(c) {
  const isFollowup   = c._callType === 'followup';
  const isAeFollowup = c._callType === 'ae_followup';

  // Theme + type-tag string by call type. headerBg uses solid backgrounds (no
  // border-b — the meta strip below the header carries its own border) so the
  // collapsible header reads as a single, tappable surface.
  let borderCls, headerBg, titleCls, dayBadgeCls, typeTag;
  if (isAeFollowup) {
    borderCls   = 'border-rose-200';
    headerBg    = 'bg-rose-50';
    titleCls    = 'text-rose-800';
    dayBadgeCls = 'text-rose-500';
    typeTag     = 'AE Follow-up';
  } else if (isFollowup) {
    borderCls   = 'border-blue-200';
    headerBg    = 'bg-blue-50';
    titleCls    = 'text-blue-800';
    dayBadgeCls = 'text-blue-500';
    typeTag     = c.protocol_event_id === 'followup_call_d07' ? 'Follow-up Day 07'
                : c.protocol_event_id === 'followup_call_d21' ? 'Follow-up Day 21'
                : (c.event_name || 'Follow-up Call');
  } else {
    borderCls   = 'border-violet-200';
    headerBg    = 'bg-violet-50';
    titleCls    = 'text-violet-800';
    dayBadgeCls = 'text-violet-500';
    typeTag     = 'Patient Call';
  }

  const alias     = c.alias || '';
  // Small chip surfaces patient-initiated AE follow-ups so the therapist can
  // distinguish them at a glance from the routine scheduled chain.
  const patientInitiatedChip = (isAeFollowup && c.patient_initiated)
    ? `<span class="inline-flex items-center gap-1 text-xs bg-amber-50 text-amber-800 border border-amber-200 rounded-full px-2 py-0.5"><i class="fas fa-phone-volume text-[10px]"></i>Patient-initiated</span>`
    : '';
  const titleText = alias ? `${_esc(alias)} <span class="text-slate-400 font-normal">·</span> ${_esc(typeTag)}`
                          : _esc(typeTag);

  const dayNum  = _dayNumber(c.completion_date);
  const dayBadge = dayNum !== null
    ? `<span class="text-xs font-semibold ${dayBadgeCls}">Day ${dayNum}</span>` : '';
  const dateStr  = c.completion_date ? _fmtDateTime(c.completion_date) : '—';
  const filedStr = _showFiledLine(c) ? _fmtDateTime(c.filed_at) : '';
  const duration = c.duration_minutes ? `${c.duration_minutes} min` : '—';
  const modeStr  = c.call_mode ? ` <span class="text-slate-300">·</span> <i class="fas fa-${c.call_mode === 'video' ? 'video' : 'phone-volume'} mr-0.5"></i>${c.call_mode === 'video' ? 'Video' : 'Audio'}` : '';

  // For AE follow-up, surface the AE aliases the call covered.
  const aeAliases = (c.ae_aliases || []).filter(Boolean);
  const aeRef = (isAeFollowup && aeAliases.length)
    ? `<p class="text-xs text-slate-500"><span class="text-slate-400">Re:</span> ${aeAliases.map(_esc).join(', ')}</p>`
    : '';

  const triggered = (c.triggered || []).map(t =>
    `<span class="inline-flex items-center gap-1 text-xs bg-amber-50 text-amber-700 border border-amber-200 rounded-full px-2 py-0.5">` +
    `<i class="fas fa-arrow-right text-[10px]"></i>${_TRIGGERED_LABELS[t.type] || t.type}</span>`
  ).join('');

  const reasonNote = c.date_change_reason
    ? `<p class="text-xs text-amber-600"><i class="fas fa-info-circle mr-1"></i>Date changed: ${_esc(c.date_change_reason)}</p>`
    : '';

  const attachmentLink = (c.attachment && c.id)
    ? `<a href="/api/patients/${PATIENT_HOMER_ID}/download-attachment/${c.id}" target="_blank" ` +
      `class="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline">` +
      `<i class="fas fa-paperclip"></i>Download attachment</a>`
    : '';

  const cardId    = (c.id || '').replace(/-/g, '');
  const noteCount = c.event_notes_count || 0;
  const noteCountBadge = `<span id="call-note-count-${cardId}"
      class="inline-flex items-center gap-1 text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 rounded-full px-2 py-0.5${noteCount > 0 ? '' : ' hidden'}"
      title="Event notes"><i class="fas fa-sticky-note text-[10px]"></i>${noteCount}</span>`;

  // Notes section at the bottom of the body. Target id = call entry's own id —
  // notes are about that specific call interaction (whatever its type).
  const notesSection = c.id ? `
    <div class="mt-3 pt-3 border-t border-slate-200">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm font-semibold text-slate-700 inline-flex items-center gap-1.5">
          <i class="fas fa-sticky-note text-blue-500"></i> Notes
        </span>
        <button type="button" onclick="openEventNoteModal('${c.id}')"
                class="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700">
          <i class="fas fa-plus text-[10px]"></i> Add Note
        </button>
      </div>
      <div id="call-notes-${cardId}" data-event-id="${c.id}">
        <p class="text-xs text-slate-400 italic">Loading…</p>
      </div>
    </div>` : '';

  return `
    <div class="bg-white rounded-xl border ${borderCls} shadow-sm mb-3 overflow-hidden">
      <div class="${headerBg} px-4 py-2.5 cursor-pointer select-none flex items-center justify-between"
           onclick="_toggleCallCard('${cardId}')">
        <div class="flex items-center gap-2.5 flex-wrap">
          <span class="text-sm font-semibold ${titleCls}">${titleText}</span>
          ${patientInitiatedChip}
          ${noteCountBadge}
        </div>
        <div class="flex items-center gap-3">
          <div class="flex flex-col items-end">
            <div class="flex items-center gap-3">
              ${dayBadge}
              <span class="text-xs text-slate-500">${dateStr}</span>
            </div>
            ${filedStr ? `<span class="text-xs text-slate-400">Filed: ${filedStr}</span>` : ''}
          </div>
          <i class="fas fa-chevron-down text-xs ${titleCls}" id="call-chevron-${cardId}"
             style="transition: transform 0.15s"></i>
        </div>
      </div>
      <div id="call-body-${cardId}" class="hidden bg-white px-4 py-3 space-y-1.5">
        <p class="text-xs text-slate-500"><i class="fas fa-clock mr-1"></i>${duration}${modeStr}</p>
        ${aeRef}
        ${c.notes ? `<p class="text-sm text-slate-700">${_esc(c.notes)}</p>` : ''}
        ${reasonNote}
        ${attachmentLink}
        ${triggered ? `<div class="flex flex-wrap gap-1.5 pt-1">${triggered}</div>` : ''}
        ${notesSection}
      </div>
    </div>`;
}

function _toggleCallCard(cardId) {
  const body    = document.getElementById(`call-body-${cardId}`);
  const chevron = document.getElementById(`call-chevron-${cardId}`);
  if (!body) return;
  const isHidden = body.classList.toggle('hidden');
  if (chevron) chevron.style.transform = isHidden ? '' : 'rotate(180deg)';
  if (!isHidden) {
    const notesBox = document.getElementById(`call-notes-${cardId}`);
    if (notesBox && !notesBox.dataset.loaded) {
      const evId = notesBox.dataset.eventId;
      if (evId) _loadCallCardNotes(evId, cardId);
    }
  }
}

async function _loadCallCardNotes(eventId, cardId) {
  const box = document.getElementById(`call-notes-${cardId}`);
  if (!box) return;
  const { ok, data } = await apiGet(`/api/patients/${PATIENT_HOMER_ID}/events/${eventId}/notes`);
  if (!ok) {
    box.innerHTML = `<p class="text-xs text-red-500">${_esc(data.error || 'Failed to load notes.')}</p>`;
    return;
  }
  const notes   = data.notes || [];
  const isAdmin = !!data.is_admin;
  box.dataset.loaded = '1';
  box.innerHTML = notes.length
    ? notes.map(n => _eventNoteCard(n, isAdmin)).join('')
    : `<p class="text-xs text-slate-400 italic">No notes on this event yet.</p>`;
}

function _refreshCallCardNotes(eventId) {
  if (!eventId) return;
  const cardId = (eventId || '').replace(/-/g, '');
  const ev     = (_completeEventsCache || []).find(e => e.id === eventId);
  const count  = ev?.event_notes_count || 0;
  // Mirror the bump into _callLogsCache so a tab switch + return doesn't
  // re-render with a stale count. The two caches are populated from
  // independent endpoints but represent the same underlying entries.
  if (_callLogsCache) {
    for (const bucket of ['followup_calls', 'patient_calls', 'ae_followup_calls']) {
      const arr = _callLogsCache[bucket];
      if (!Array.isArray(arr)) continue;
      const hit = arr.find(c => c.id === eventId);
      if (hit) hit.event_notes_count = count;
    }
  }
  const badge  = document.getElementById(`call-note-count-${cardId}`);
  if (badge) {
    badge.innerHTML = `<i class="fas fa-sticky-note text-[10px]"></i>${count}`;
    badge.classList.toggle('hidden', count <= 0);
  }
  const notesBox = document.getElementById(`call-notes-${cardId}`);
  if (notesBox) {
    delete notesBox.dataset.loaded;
    _loadCallCardNotes(eventId, cardId);
  }
}

// ── Adverse Events tab ────────────────────────────────────────────────────────

const _AEF_TYPE_LABELS = {
  adverse_event_followup:        'Follow-up Call',
  adverse_event_followup_visit:  'Follow-up Visit',
  adverse_event_clinical_visit:  'Clinical Visit',
};
const _AE_FOLLOWUP_TYPES = ['adverse_event_followup', 'adverse_event_followup_visit', 'adverse_event_clinical_visit'];

function renderAdverseEventsTab() {
  const container = document.getElementById('adverse-events-content');
  if (!container) return;

  const aeEvents = (_completeEventsCache || [])
    .filter(e => e.protocol_event_id === 'adverse_event')
    .sort(_cmpCompletedDesc); // newest first

  if (!aeEvents.length) {
    container.innerHTML = `
      <div class="flex flex-col items-center justify-center py-16 text-slate-300">
        <i class="fas fa-exclamation-triangle text-3xl mb-3"></i>
        <p class="text-sm">No adverse events recorded.</p>
      </div>`;
    return;
  }

  const followupEvents = (_completeEventsCache || []).filter(e => _AE_FOLLOWUP_TYPES.includes(e.protocol_event_id));
  container.innerHTML = aeEvents.map(ev => _adverseEventCard(ev, followupEvents)).join('');
}

function _toggleAeCard(cardId) {
  const body    = document.getElementById(`ae-body-${cardId}`);
  const chevron = document.getElementById(`ae-chevron-${cardId}`);
  if (!body) return;
  const isHidden = body.classList.toggle('hidden');
  if (chevron) chevron.style.transform = isHidden ? '' : 'rotate(180deg)';
  // Lazy-load event notes the first time the card opens. Subsequent opens
  // keep the rendered list (refreshed only after a save via _refreshAeCardNotes).
  if (!isHidden) {
    const notesBox = document.getElementById(`ae-notes-${cardId}`);
    if (notesBox && !notesBox.dataset.loaded) {
      const evId = notesBox.dataset.eventId;
      if (evId) _loadAeCardNotes(evId, cardId);
    }
  }
}

// Fetch the role-filtered event-notes for an AE and render them into the
// card's notes container. Same endpoint and same _eventNoteCard renderer as
// the Timeline detail pane — one storage path, two surfaces.
async function _loadAeCardNotes(eventId, cardId) {
  const box = document.getElementById(`ae-notes-${cardId}`);
  if (!box) return;
  const { ok, data } = await apiGet(`/api/patients/${PATIENT_HOMER_ID}/events/${eventId}/notes`);
  if (!ok) {
    box.innerHTML = `<p class="text-xs text-red-500">${_esc(data.error || 'Failed to load notes.')}</p>`;
    return;
  }
  const notes   = data.notes || [];
  const isAdmin = !!data.is_admin;
  box.dataset.loaded = '1';
  box.innerHTML = notes.length
    ? notes.map(n => _eventNoteCard(n, isAdmin)).join('')
    : `<p class="text-xs text-slate-400 italic">No notes on this event yet.</p>`;
}

// Called by the save-note handler when an AE card may be on screen. Updates
// the header note-count badge from the cache and re-loads the notes list so
// the new note appears immediately. No-op if the card isn't currently rendered.
function _refreshAeCardNotes(eventId) {
  if (!eventId) return;
  const cardId = (eventId || '').replace(/-/g, '');
  const ev     = (_completeEventsCache || []).find(e => e.id === eventId);
  const count  = ev?.event_notes_count || 0;
  const badge  = document.getElementById(`ae-note-count-${cardId}`);
  if (badge) {
    badge.innerHTML = `<i class="fas fa-sticky-note text-[10px]"></i>${count}`;
    badge.classList.toggle('hidden', count <= 0);
  }
  const notesBox = document.getElementById(`ae-notes-${cardId}`);
  if (notesBox) {
    delete notesBox.dataset.loaded;
    _loadAeCardNotes(eventId, cardId);
  }
}

function _adverseEventCard(ev, followupEvents) {
  // Find all follow-ups referencing this AE, sorted chronologically
  const related = followupEvents
    .filter(fe => (fe.ae_discussions || []).some(d => d.adverse_event_id === ev.id))
    .sort(_cmpCompletedDesc);

  let resolvedEntry = null;
  for (const fe of related) {
    const disc = (fe.ae_discussions || []).find(d => d.adverse_event_id === ev.id);
    if (disc?.resolved) { resolvedEntry = { fe, disc }; break; }
  }

  const isResolved = !!resolvedEntry;
  const isBlocked  = ev.training_blocked && !isResolved;

  // Color theme
  let borderCls, headerBg, headerText, statusBadge;
  if (isBlocked) {
    borderCls   = 'border-red-300';
    headerBg    = 'bg-red-100';
    headerText  = 'text-red-900';
    statusBadge = `<span class="inline-flex items-center gap-1 text-xs bg-red-600 text-white rounded-full px-2 py-0.5 font-medium">
                     <i class="fas fa-pause text-[10px]"></i>Ongoing — Training blocked</span>`;
  } else if (!isResolved) {
    borderCls   = 'border-amber-300';
    headerBg    = 'bg-amber-50';
    headerText  = 'text-amber-900';
    statusBadge = `<span class="inline-flex items-center gap-1 text-xs bg-amber-100 text-amber-800 border border-amber-300 rounded-full px-2 py-0.5">
                     <i class="fas fa-clock text-[10px]"></i>Ongoing</span>`;
  } else {
    borderCls   = 'border-green-200';
    headerBg    = 'bg-green-50';
    headerText  = 'text-green-900';
    statusBadge = `<span class="inline-flex items-center gap-1 text-xs bg-green-100 text-green-800 border border-green-200 rounded-full px-2 py-0.5">
                     <i class="fas fa-check text-[10px]"></i>Resolved</span>`;
  }

  // Dates and duration
  const reportDateStr = ev.completion_date ? _fmtDate(ev.completion_date) : '—';
  let resolveDateStr = '';
  let durationStr    = '';
  if (isResolved && resolvedEntry.fe.completion_date) {
    resolveDateStr = _fmtDate(resolvedEntry.fe.completion_date);
    const d1   = new Date(ev.completion_date);
    const d2   = new Date(resolvedEntry.fe.completion_date);
    const days = Math.max(0, Math.round((d2 - d1) / 86400000));
    durationStr = `${days} day${days !== 1 ? 's' : ''}`;
  } else if (!isResolved && ev.completion_date) {
    const days = Math.max(0, Math.round((Date.now() - new Date(ev.completion_date)) / 86400000));
    durationStr = `${days} day${days !== 1 ? 's' : ''} ongoing`;
  }

  const dayNum = _dayNumber(ev.completion_date);
  const filedReportStr = _showFiledLine(ev) ? _fmtDateTime(ev.filed_at) : '';
  const sep    = `<span class="text-slate-300 mx-1.5">|</span>`;
  const metaParts = [
    `<span class="text-xs text-slate-500"><span class="text-slate-400">Reported:</span> ${reportDateStr}${filedReportStr ? ` <span class="text-slate-300">(filed ${filedReportStr})</span>` : ''}</span>`,
    resolveDateStr ? `<span class="text-xs text-slate-500"><span class="text-slate-400">Resolved:</span> ${resolveDateStr}</span>` : '',
    durationStr    ? `<span class="text-xs text-slate-500"><span class="text-slate-400">Duration:</span> ${durationStr}</span>` : '',
    dayNum !== null ? `<span class="text-xs text-slate-400">Day ${dayNum}</span>` : '',
  ].filter(Boolean).join(sep);

  // Triggered by
  let triggerStr = '';
  if (ev.triggered_by) {
    const typeLabel   = _WR_TRIGGER_NAMES[ev.triggered_by.type] || (ev.triggered_by.type || '').replace(/_/g, ' ');
    const triggerEv   = (_completeEventsCache || []).find(e => e.id === ev.triggered_by.id);
    const triggerDate = triggerEv?.completion_date ? ` — ${_fmtDateTime(triggerEv.completion_date)}` : '';
    triggerStr = `<div class="text-xs text-slate-500"><span class="text-slate-400">Triggered by:</span> ${typeLabel}${triggerDate}</div>`;
  }

  const attachmentStr = (ev.attachment && ev.id)
    ? `<a href="/api/patients/${PATIENT_HOMER_ID}/download-attachment/${ev.id}" target="_blank"
         class="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline">
         <i class="fas fa-paperclip"></i>Attachment</a>`
    : '';

  // Follow-up history rows
  const followupRows = related.map(fe => {
    const disc      = (fe.ae_discussions || []).find(d => d.adverse_event_id === ev.id);
    const aeAliases = (fe.adverse_event_ids || [])
      .map(aeId => (_completeEventsCache || []).find(e => e.id === aeId)?.alias)
      .filter(Boolean).join(', ');
    const typeLabel = (_AEF_TYPE_LABELS[fe.protocol_event_id] || fe.protocol_event_id)
      + (aeAliases ? `: ${aeAliases}` : '');
    const feDate    = fe.completion_date ? _fmtDateTime(fe.completion_date) : '—';
    const feFiled   = _showFiledLine(fe) ? _fmtDateTime(fe.filed_at) : '';
    const patientInitiatedChip = (fe.protocol_event_id === 'adverse_event_followup' && fe.patient_initiated)
      ? ` <span class="inline-flex items-center gap-1 text-[10px] bg-amber-50 text-amber-800 border border-amber-200 rounded-full px-1.5 py-0.5"><i class="fas fa-phone-volume text-[9px]"></i>Patient-initiated</span>`
      : '';
    const feNotes   = fe.notes   ? `<p class="text-xs text-slate-500 mt-0.5">${fe.notes}</p>`        : '';
    const discNotes = disc?.notes ? `<p class="text-xs text-slate-500 mt-0.5 italic">${disc.notes}</p>` : '';
    const resumeStr = disc?.can_resume_from
      ? ` <span class="text-xs text-slate-400">(resume from ${disc.can_resume_from})</span>` : '';
    const statusEl  = disc?.resolved
      ? `<span class="inline-flex items-center gap-1 text-xs text-green-700"><i class="fas fa-check-circle text-[10px]"></i>Resolved${resumeStr}</span>`
      : `<span class="inline-flex items-center gap-1 text-xs text-amber-700"><i class="fas fa-circle text-[10px]"></i>Unresolved</span>`;
    const feAttach  = (fe.attachment && fe.id)
      ? `<a href="/api/patients/${PATIENT_HOMER_ID}/download-attachment/${fe.id}" target="_blank"
           class="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline">
           <i class="fas fa-paperclip"></i>Attachment</a>` : '';
    return `
      <div class="py-2 border-t border-slate-100">
        <div class="flex items-center justify-between flex-wrap gap-1 mb-0.5">
          <span class="text-xs font-medium text-slate-700">${typeLabel}${patientInitiatedChip}</span>
          <span class="text-xs text-slate-400">${feDate}${feFiled ? ` <span class="text-slate-300">(filed ${feFiled})</span>` : ''}</span>
        </div>
        ${feNotes}${discNotes}
        <div class="mt-1 flex items-center gap-3 flex-wrap">${statusEl}${feAttach}</div>
      </div>`;
  }).join('');

  const followupSection = related.length
    ? `<div class="mt-3 pt-2 border-t border-slate-200">
         <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Follow-up history</p>
         ${followupRows}
       </div>`
    : '';

  const cardId = ev.id.replace(/-/g, '');

  // Note-count badge in the header (server-stamped, role-filtered count from
  // api_patient_events). Hidden when zero so the header stays uncluttered.
  const noteCount = ev.event_notes_count || 0;
  const noteCountBadge = `<span id="ae-note-count-${cardId}"
      class="inline-flex items-center gap-1 text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 rounded-full px-2 py-0.5${noteCount > 0 ? '' : ' hidden'}"
      title="Event notes"><i class="fas fa-sticky-note text-[10px]"></i>${noteCount}</span>`;

  // Notes section at the bottom of the body. Lazy-loaded on expand via
  // _toggleAeCard → _loadAeCardNotes. The "Add Note" button opens the same
  // shared note-modal used by the Timeline; storage is the same `event_notes`
  // field on this AE entry.
  const notesSection = `
    <div class="mt-3 pt-3 border-t border-slate-200">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm font-semibold text-slate-700 inline-flex items-center gap-1.5">
          <i class="fas fa-sticky-note text-blue-500"></i> Notes
        </span>
        <button type="button" onclick="openEventNoteModal('${ev.id}')"
                class="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700">
          <i class="fas fa-plus text-[10px]"></i> Add Note
        </button>
      </div>
      <div id="ae-notes-${cardId}" data-event-id="${ev.id}">
        <p class="text-xs text-slate-400 italic">Loading…</p>
      </div>
    </div>`;

  return `
    <div class="rounded-xl border ${borderCls} shadow-sm mb-3 overflow-hidden">
      <div class="${headerBg} px-4 py-2.5 cursor-pointer select-none flex items-center justify-between"
           onclick="_toggleAeCard('${cardId}')">
        <div class="flex items-center gap-2.5 flex-wrap">
          <span class="text-sm font-bold ${headerText}">${ev.alias || ''}</span>
          ${statusBadge}
          ${noteCountBadge}
        </div>
        <i class="fas fa-chevron-down text-xs ${headerText}" id="ae-chevron-${cardId}"
           style="transition: transform 0.15s"></i>
      </div>
      <div class="px-4 py-2 border-b border-slate-100 bg-white flex items-center flex-wrap gap-0">${metaParts}</div>
      <div id="ae-body-${cardId}" class="hidden bg-white px-4 py-3 space-y-1.5">
        ${ev.description  ? `<p class="text-sm text-slate-700">${ev.description}</p>` : ''}
        ${ev.action_taken ? `<div class="text-xs text-slate-500"><span class="text-slate-400">Action taken:</span> ${ev.action_taken}</div>` : ''}
        ${triggerStr}
        ${attachmentStr}
        ${followupSection}
        ${notesSection}
      </div>
    </div>`;
}

// ── Watch Records tab ─────────────────────────────────────────────────────────

function renderWatchRecordsTab() {
  const container = document.getElementById('watch-records-content');
  if (!container) return;

  const records = (_completeEventsCache || [])
    .filter(e => e.protocol_event_id === 'watch_record')
    .sort(_cmpCompletedDesc);

  // Build wr-id → uploads map. Each `watch_data_upload` with
  // `triggered_by.type === 'watch_record'` and a matching id is nested under
  // its parent watch_record card. `device_return`-triggered uploads (when
  // that event ships) are intentionally not surfaced on this tab.
  const uploadsByWr = new Map();
  const _stash = (ev) => {
    const tb = ev.triggered_by;
    if (!tb || tb.type !== 'watch_record' || !tb.id) return;
    if (!uploadsByWr.has(tb.id)) uploadsByWr.set(tb.id, []);
    uploadsByWr.get(tb.id).push(ev);
  };
  (eventsCache || []).forEach(e => { if (e.protocol_event_id === 'watch_data_upload') _stash(e); });
  (_completeEventsCache || []).forEach(e => { if (e.protocol_event_id === 'watch_data_upload') _stash(e); });

  if (!records.length) {
    container.innerHTML = `
      <div class="flex flex-col items-center justify-center py-12 text-slate-300">
        <i class="fas fa-clock text-3xl mb-3"></i>
        <p class="text-sm">No watch records yet.</p>
      </div>`;
    return;
  }
  container.innerHTML = records.map(wr => _watchRecordCard(wr, uploadsByWr.get(wr.id) || [])).join('');
}

function _watchDataUploadOpenCard(ev) {
  const limb    = ev.limb ? ev.limb.charAt(0).toUpperCase() + ev.limb.slice(1) : '';
  const removed = ev.removed_date ? _fmtDateTime(ev.removed_date) : '—';
  const rangeFrom = ev.data_start ? _fmtDateTime(ev.data_start) : '—';
  const rangeTo   = ev.data_end   ? _fmtDateTime(ev.data_end)   : '—';
  return `
    <div class="bg-white rounded-xl border border-amber-200 shadow-sm mb-3 overflow-hidden">
      <div class="bg-amber-50 border-b border-amber-100 px-4 py-2.5 flex items-center justify-between">
        <span class="text-sm font-semibold text-amber-800">Watch ${ev.watch_id || '—'}${limb ? ` (${limb})` : ''}</span>
        <span class="inline-flex items-center gap-1 text-xs bg-amber-100 text-amber-800 border border-amber-300 rounded-full px-2 py-0.5">
          <i class="fas fa-clock text-[10px]"></i>Upload pending</span>
      </div>
      <div class="px-4 py-3 text-xs text-slate-500 space-y-0.5">
        <div><span class="text-slate-400">Removed:</span> ${removed}</div>
        <div><span class="text-slate-400">Expected range:</span> ${rangeFrom} → ${rangeTo}</div>
      </div>
    </div>`;
}

function _watchDataUploadDoneCard(ev) {
  const limb    = ev.limb ? ev.limb.charAt(0).toUpperCase() + ev.limb.slice(1) : '';
  const removed = ev.removed_date ? _fmtDateTime(ev.removed_date) : '—';
  const skipped = !!ev.skipped;
  const badge = skipped
    ? `<span class="inline-flex items-center gap-1 text-xs bg-slate-100 text-slate-600 border border-slate-300 rounded-full px-2 py-0.5"><i class="fas fa-ban text-[10px]"></i>No data</span>`
    : `<span class="inline-flex items-center gap-1 text-xs bg-green-100 text-green-800 border border-green-200 rounded-full px-2 py-0.5"><i class="fas fa-check text-[10px]"></i>Uploaded</span>`;
  const link = (!skipped && ev.data_file && ev.id)
    ? `<a href="/api/patients/${PATIENT_HOMER_ID}/watch-data/${ev.id}" target="_blank" class="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline mt-1"><i class="fas fa-download"></i>${ev.original_filename || 'Download .gt3x'}</a>`
    : '';
  const uploadedAt = (!skipped && ev.completion_date) ? `<div><span class="text-slate-400">Uploaded:</span> ${_fmtDateTime(ev.completion_date)}</div>` : '';
  const notes = ev.notes ? `<div class="mt-1"><span class="text-slate-400">Notes:</span> ${_esc(ev.notes)}</div>` : '';
  const borderCls = skipped ? 'border-slate-200' : 'border-green-200';
  const headerBg  = skipped ? 'bg-slate-50' : 'bg-green-50';
  const titleCls  = skipped ? 'text-slate-700' : 'text-green-800';
  return `
    <div class="bg-white rounded-xl border ${borderCls} shadow-sm mb-3 overflow-hidden">
      <div class="${headerBg} border-b border-slate-100 px-4 py-2.5 flex items-center justify-between">
        <span class="text-sm font-semibold ${titleCls}">Watch ${ev.watch_id || '—'}${limb ? ` (${limb})` : ''}</span>
        ${badge}
      </div>
      <div class="px-4 py-3 text-xs text-slate-500 space-y-0.5">
        <div><span class="text-slate-400">Removed:</span> ${removed}</div>
        ${uploadedAt}
        ${notes}
        ${link}
      </div>
    </div>`;
}

function _watchAssignmentRow(side, wr) {
  const key  = `ag_watch_${side}`;
  const data = wr[key];
  if (!data) return '';
  const { old_id, old_lost, new_id } = data;
  // Skip limb entirely if neither old nor new was ever assigned
  if (!old_id && !new_id) return '';

  let arrow;
  if (old_id === new_id) {
    arrow = `<span class="text-slate-500">${old_id ?? 'None'}</span> <span class="text-slate-300 text-xs">no change</span>`;
  } else {
    const oldPart = old_id
      ? `${old_id}${old_lost ? ' <span class="text-red-500 text-xs">(lost)</span>' : ''}`
      : '<span class="text-slate-400">—</span>';
    const newPart = new_id
      ? `<span class="font-medium text-slate-800">${new_id}</span>`
      : '<span class="text-slate-400 text-xs">None</span>';
    arrow = `${oldPart} <span class="text-slate-400 mx-1">→</span> ${newPart}`;
  }
  const label = side.charAt(0).toUpperCase() + side.slice(1);
  return `<div class="flex items-center gap-2 text-xs">
    <span class="text-slate-400 w-8 shrink-0">${label}</span>
    <span>${arrow}</span>
  </div>`;
}

function _watchRecordCard(wr, uploads) {
  const dayNum   = _dayNumber(wr.completion_date);
  const dayBadge = dayNum !== null ? `<span class="text-xs font-semibold text-indigo-500">Day ${dayNum}</span>` : '';
  const dateStr  = wr.completion_date ? _fmtDateTime(wr.completion_date) : '—';
  const filedStr = _showFiledLine(wr) ? _fmtDateTime(wr.filed_at) : '';

  const rightRow = _watchAssignmentRow('right', wr);
  const leftRow  = _watchAssignmentRow('left', wr);

  const syncStr  = wr.sync_datetime  ? `<div class="text-xs text-slate-500"><span class="text-slate-400">Sync:</span> ${_fmtDateTime(wr.sync_datetime)}</div>`  : '';
  const wornStr  = wr.worn_datetime  ? `<div class="text-xs text-slate-500"><span class="text-slate-400">Worn:</span> ${_fmtDateTime(wr.worn_datetime)}</div>`   : '';
  const nextStr  = wr.next_followup_days != null
    ? `<div class="text-xs text-slate-500"><span class="text-slate-400">Next check:</span> ${wr.next_followup_days} days</div>` : '';

  let triggerStr = '';
  if (wr.triggered_by) {
    const typeLabel  = _WR_TRIGGER_NAMES[wr.triggered_by.type] || (wr.triggered_by.type || '').replace(/_/g, ' ');
    const triggerEv  = (_completeEventsCache || []).find(e => e.id === wr.triggered_by.id);
    const triggerDate = triggerEv?.completion_date ? ` — ${_fmtDateTime(triggerEv.completion_date)}` : '';
    triggerStr = `<div class="text-xs text-slate-500"><span class="text-slate-400">Triggered by:</span> ${typeLabel}${triggerDate}</div>`;
  }

  const notesStr = wr.notes
    ? `<div class="text-xs text-slate-500 mt-1"><span class="text-slate-400">Notes:</span> ${_esc(wr.notes)}</div>` : '';

  const attachmentStr = (wr.attachment && wr.id)
    ? `<a href="/api/patients/${PATIENT_HOMER_ID}/download-attachment/${wr.id}" target="_blank"
         class="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline mt-1">
         <i class="fas fa-paperclip"></i>Download attachment</a>` : '';

  // Nested data-upload sub-section: sort with pending (no completion_date) first
  // so the engineer's outstanding work is visually surfaced, then completed
  // ones newest-first by completion_date.
  let uploadsSection = '';
  if (uploads && uploads.length) {
    const sorted = uploads.slice().sort((a, b) => {
      const aDone = !!a.completion_date;
      const bDone = !!b.completion_date;
      if (aDone !== bDone) return aDone ? 1 : -1;
      return (b.completion_date || '').localeCompare(a.completion_date || '');
    });
    const rows = sorted.map(up =>
      up.completion_date ? _watchDataUploadDoneCard(up) : _watchDataUploadOpenCard(up)
    ).join('');
    uploadsSection = `
      <div class="mt-3 pt-3 border-t border-slate-200">
        <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1.5">
          <i class="fas fa-database mr-1"></i>AG Watch Data Uploads
        </p>
        ${rows}
      </div>`;
  }

  const alias     = wr.alias || '';
  const titleText = alias ? `${_esc(alias)} <span class="text-slate-400 font-normal">·</span> Watch Record`
                          : 'Watch Record';
  const cardId    = (wr.id || '').replace(/-/g, '');

  return `
    <div class="bg-white rounded-xl border border-indigo-200 shadow-sm mb-3 overflow-hidden">
      <div class="bg-indigo-50 border-b border-indigo-100 px-4 py-2.5 cursor-pointer select-none flex items-center justify-between"
           onclick="_toggleWrCard('${cardId}')">
        <span class="text-sm font-semibold text-indigo-800">${titleText}</span>
        <div class="flex items-center gap-3">
          <div class="flex flex-col items-end">
            <div class="flex items-center gap-3">
              ${dayBadge}
              <span class="text-xs text-slate-500">${dateStr}</span>
            </div>
            ${filedStr ? `<span class="text-xs text-slate-400">Filed: ${filedStr}</span>` : ''}
          </div>
          <i class="fas fa-chevron-down text-xs text-indigo-800" id="wr-chevron-${cardId}"
             style="transition: transform 0.15s"></i>
        </div>
      </div>
      <div id="wr-body-${cardId}" class="hidden px-4 py-3 space-y-1.5">
        ${rightRow}
        ${leftRow}
        ${syncStr}${wornStr}${nextStr}${triggerStr}${notesStr}${attachmentStr}
        ${uploadsSection}
      </div>
    </div>`;
}

function _toggleWrCard(cardId) {
  const body    = document.getElementById(`wr-body-${cardId}`);
  const chevron = document.getElementById(`wr-chevron-${cardId}`);
  if (!body) return;
  const isHidden = body.classList.toggle('hidden');
  if (chevron) chevron.style.transform = isHidden ? '' : 'rotate(180deg)';
}

// ── Device Issues tab (RI + ODI unified) ─────────────────────────────────────

// Modeled on the Adverse Events tab. One collapsible card per call
// (`robot_issue_call` or `other_device_issue_call`); the expanded body shows
// faulty devices + triggered-by + visit history (engineer visit → resolve visit).
// Aliases (RI01… / ODI01…) are server-assigned and used as the card title.
//
// Visit chain walk:
//   robot_issue_call → robot_issue_visit (triggered_by.id == call.id)
//                    → resolve_robot_issue_visit (triggered_by.id == visit.id)
//   other_device_issue_call → other_device_issue_visit (triggered_by.id == call.id)
// Pending detection: any entry in eventsCache (incomplete) referencing this
// chain → status "open".

const _DI_DEVICE_OUTCOME_LABEL = {
  resolved:          'Resolved on call',
  resolved_over_call:'Resolved on call',
  visit_required:    'Visit required',
  repaired:          'Repaired',
  replaced:          'Replaced',
  swapped:           'Swapped',
  repaired_on_site:  'Repaired on site',
  neither:           'Not repaired / not swapped',
};

const _DI_TRIGGER_NAMES = {
  activation:           'Patient Activation',
  home_visit_d02:       'Home Visit Day 02',
  home_visit_d03:       'Home Visit Day 03',
  home_visit_d15:       'Home Visit Day 15',
  followup_call_d07:    'Follow-up Call Day 07',
  followup_call_d21:    'Follow-up Call Day 21',
  patient_call:         'Patient Call',
  robot_issue_call:     'Robot Issue Call',
  robot_issue_visit:    'Robot Issue Visit',
};

function renderDeviceIssuesTab() {
  const container = document.getElementById('device-issues-content');
  if (!container) return;

  const calls = (_completeEventsCache || [])
    .filter(e => e.protocol_event_id === 'robot_issue_call'
              || e.protocol_event_id === 'other_device_issue_call')
    .sort(_cmpCompletedDesc);

  if (!calls.length) {
    container.innerHTML = `
      <div class="flex flex-col items-center justify-center py-16 text-slate-300">
        <i class="fas fa-screwdriver-wrench text-3xl mb-3"></i>
        <p class="text-sm">No device issues recorded.</p>
      </div>`;
    return;
  }
  container.innerHTML = calls.map(_deviceIssueCard).join('');
}

function _toggleDiCard(cardId) {
  const body    = document.getElementById(`di-body-${cardId}`);
  const chevron = document.getElementById(`di-chevron-${cardId}`);
  if (!body) return;
  const isHidden = body.classList.toggle('hidden');
  if (chevron) chevron.style.transform = isHidden ? '' : 'rotate(180deg)';
  // Lazy-load event notes on first expand.
  if (!isHidden) {
    const notesBox = document.getElementById(`di-notes-${cardId}`);
    if (notesBox && !notesBox.dataset.loaded) {
      const evId = notesBox.dataset.eventId;
      if (evId) _loadDiCardNotes(evId, cardId);
    }
  }
}

async function _loadDiCardNotes(eventId, cardId) {
  const box = document.getElementById(`di-notes-${cardId}`);
  if (!box) return;
  const { ok, data } = await apiGet(`/api/patients/${PATIENT_HOMER_ID}/events/${eventId}/notes`);
  if (!ok) {
    box.innerHTML = `<p class="text-xs text-red-500">${_esc(data.error || 'Failed to load notes.')}</p>`;
    return;
  }
  const notes   = data.notes || [];
  const isAdmin = !!data.is_admin;
  box.dataset.loaded = '1';
  box.innerHTML = notes.length
    ? notes.map(n => _eventNoteCard(n, isAdmin)).join('')
    : `<p class="text-xs text-slate-400 italic">No notes on this event yet.</p>`;
}

function _refreshDiCardNotes(eventId) {
  if (!eventId) return;
  const cardId = (eventId || '').replace(/-/g, '');
  const ev     = (_completeEventsCache || []).find(e => e.id === eventId);
  const count  = ev?.event_notes_count || 0;
  const badge  = document.getElementById(`di-note-count-${cardId}`);
  if (badge) {
    badge.innerHTML = `<i class="fas fa-sticky-note text-[10px]"></i>${count}`;
    badge.classList.toggle('hidden', count <= 0);
  }
  const notesBox = document.getElementById(`di-notes-${cardId}`);
  if (notesBox) {
    delete notesBox.dataset.loaded;
    _loadDiCardNotes(eventId, cardId);
  }
}

// Walk the visit chain forward from a call. Returns visits in chronological
// (filed_at) order: engineer visit(s), then any resolve-visit triggered by
// those engineer visits (RI only). ODI has no resolve step.
function _diVisitsForCall(call) {
  const all = _completeEventsCache || [];
  const isRI = call.protocol_event_id === 'robot_issue_call';
  const visitType = isRI ? 'robot_issue_visit' : 'other_device_issue_visit';
  const visits = all
    .filter(e => e.protocol_event_id === visitType && e.triggered_by?.id === call.id);
  let resolves = [];
  if (isRI) {
    const visitIds = new Set(visits.map(v => v.id));
    resolves = all.filter(e =>
      e.protocol_event_id === 'resolve_robot_issue_visit'
      && visitIds.has(e.triggered_by?.id)
    );
  }
  // Chronological order (oldest first) by completion_date then filed_at.
  return [...visits, ...resolves].sort((a, b) => {
    const ka = (a.completion_date || a.filed_at || '');
    const kb = (b.completion_date || b.filed_at || '');
    return ka.localeCompare(kb);
  });
}

// Returns 'resolved' | 'pending_visit' | 'in_progress'. Coarse but useful:
//   - resolved      → no pending stubs in the chain, call had no visit_required or visits cleared everything
//   - pending_visit → call has visit_required AND no visit filed yet
//   - in_progress  → visit filed but follow-on stub (e.g. resolve_robot_issue_visit) still open
function _diStatus(call, visits) {
  // Pending stubs in eventsCache referencing this chain
  const visitIds = new Set(visits.map(v => v.id));
  const hasOpen = (eventsCache || []).some(e => {
    if (!e.triggered_by) return false;
    return e.triggered_by.id === call.id || visitIds.has(e.triggered_by.id);
  });
  if (hasOpen && visits.length === 0) return 'pending_visit';
  if (hasOpen) return 'in_progress';
  return 'resolved';
}

function _deviceIssueCard(call) {
  const isRI    = call.protocol_event_id === 'robot_issue_call';
  const visits  = _diVisitsForCall(call);
  const status  = _diStatus(call, visits);
  // "Training paused" overlay is meaningful only for RI; ODI doesn't pause.
  const showPaused = isRI && !!patientData?.trainingPausedDate
    && (patientData?.pauseHistory || []).some(epoch =>
         !epoch.end && (epoch.reasons || []).some(r => r.event_id === call.id));

  // Theme by type. Status badge overlaid by status.
  const theme = isRI
    ? { border: 'border-orange-300', headerBg: 'bg-orange-50', headerText: 'text-orange-900', label: 'Robot Issue' }
    : { border: 'border-purple-300', headerBg: 'bg-purple-50', headerText: 'text-purple-900', label: 'Other Device Issue' };

  let statusBadge;
  if (status === 'resolved') {
    statusBadge = `<span class="inline-flex items-center gap-1 text-xs bg-green-100 text-green-800 border border-green-200 rounded-full px-2 py-0.5">
                     <i class="fas fa-check text-[10px]"></i>Resolved</span>`;
  } else if (status === 'pending_visit') {
    statusBadge = `<span class="inline-flex items-center gap-1 text-xs bg-amber-100 text-amber-800 border border-amber-300 rounded-full px-2 py-0.5">
                     <i class="fas fa-clock text-[10px]"></i>Pending visit</span>`;
  } else {
    statusBadge = `<span class="inline-flex items-center gap-1 text-xs bg-amber-100 text-amber-800 border border-amber-300 rounded-full px-2 py-0.5">
                     <i class="fas fa-clock text-[10px]"></i>In progress</span>`;
  }
  const pausedBadge = showPaused
    ? `<span class="inline-flex items-center gap-1 text-xs bg-red-600 text-white rounded-full px-2 py-0.5 font-medium ml-1">
         <i class="fas fa-pause text-[10px]"></i>Training paused</span>`
    : '';

  // Meta strip — Reported / Resolved / Duration / Day
  const reportDateStr  = call.completion_date ? _fmtDate(call.completion_date) : '—';
  const filedReportStr = _showFiledLine(call) ? _fmtDateTime(call.filed_at) : '';
  let resolveDateStr = '';
  let durationStr    = '';
  if (status === 'resolved') {
    const lastVisit = visits[visits.length - 1];
    const resolvedAt = lastVisit?.completion_date || call.completion_date;
    if (resolvedAt) {
      resolveDateStr = _fmtDate(resolvedAt);
      if (call.completion_date) {
        const d1 = new Date(call.completion_date);
        const d2 = new Date(resolvedAt);
        const days = Math.max(0, Math.round((d2 - d1) / 86400000));
        durationStr = `${days} day${days !== 1 ? 's' : ''}`;
      }
    }
  } else if (call.completion_date) {
    const days = Math.max(0, Math.round((Date.now() - new Date(call.completion_date)) / 86400000));
    durationStr = `${days} day${days !== 1 ? 's' : ''} ongoing`;
  }
  const dayNum = _dayNumber(call.completion_date);
  const sep    = `<span class="text-slate-300 mx-1.5">|</span>`;
  const metaParts = [
    `<span class="text-xs text-slate-500"><span class="text-slate-400">Reported:</span> ${reportDateStr}${filedReportStr ? ` <span class="text-slate-300">(filed ${filedReportStr})</span>` : ''}</span>`,
    resolveDateStr ? `<span class="text-xs text-slate-500"><span class="text-slate-400">Resolved:</span> ${resolveDateStr}</span>` : '',
    durationStr    ? `<span class="text-xs text-slate-500"><span class="text-slate-400">Duration:</span> ${durationStr}</span>` : '',
    dayNum !== null ? `<span class="text-xs text-slate-400">Day ${dayNum}</span>` : '',
  ].filter(Boolean).join(sep);

  // Devices on the call (RI shape: {device, outcome}; ODI shape: {device_type, device_id, outcome})
  const deviceRowsHtml = (call.devices || []).map(d => {
    const label = isRI
      ? d.device
      : `${d.device_type || ''} ${d.device_id || ''}`.trim();
    const outcomeLabel = _DI_DEVICE_OUTCOME_LABEL[d.outcome] || d.outcome || '';
    const noteEl = d.notes ? `<p class="mt-0.5 text-slate-500">${_esc(d.notes)}</p>` : '';
    return `<div class="text-xs text-slate-600 bg-slate-50 rounded-lg px-3 py-2 border border-slate-100">
              <span class="font-medium capitalize">${_esc(label)}:</span>
              <span class="ml-1 text-slate-700">${outcomeLabel}</span>
              ${noteEl}
            </div>`;
  }).join('') || '<p class="text-xs text-slate-400 italic">No devices listed on this call.</p>';

  // Triggered-by row
  let triggerStr = '';
  if (call.triggered_by) {
    const typeLabel = _DI_TRIGGER_NAMES[call.triggered_by.type]
      || (call.triggered_by.type || '').replace(/_/g, ' ');
    const triggerEv = (_completeEventsCache || []).find(e => e.id === call.triggered_by.id);
    const triggerDate = triggerEv?.completion_date ? ` — ${_fmtDateTime(triggerEv.completion_date)}` : '';
    triggerStr = `<div class="text-xs text-slate-500"><span class="text-slate-400">Triggered by:</span> ${typeLabel}${triggerDate}</div>`;
  }
  if (call.issue_occur_date) {
    triggerStr += `<div class="text-xs text-slate-500"><span class="text-slate-400">Issue first occurred:</span> ${_fmtDate(call.issue_occur_date)}</div>`;
  }

  const attachmentStr = (call.attachment && call.id)
    ? `<a href="/api/patients/${PATIENT_HOMER_ID}/download-attachment/${call.id}" target="_blank"
         class="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline">
         <i class="fas fa-paperclip"></i>Attachment</a>`
    : '';

  // Visit history rows (engineer visits + any resolve visits)
  const visitRows = visits.map(v => {
    const typeLabel = v.protocol_event_id === 'robot_issue_visit'         ? 'Engineer Visit'
                    : v.protocol_event_id === 'resolve_robot_issue_visit' ? 'Replacement Visit'
                    : v.protocol_event_id === 'other_device_issue_visit'  ? 'Engineer Visit'
                    : v.protocol_event_id;
    const vDate  = v.completion_date ? _fmtDateTime(v.completion_date) : '—';
    const vFiled = _showFiledLine(v) ? _fmtDateTime(v.filed_at) : '';
    const outcomes = (v.device_outcomes || v.device_replacements || v.device_faults || []).map(o => {
      const label = (o.device || o.device_type || '').toString();
      const id    = o.device_id ? ` ${o.device_id}` : '';
      const outcomeLbl = _DI_DEVICE_OUTCOME_LABEL[o.outcome] || o.outcome || '';
      const newId = o.new_device_id ? ` → ${o.new_device_id}` : '';
      const note  = o.notes ? ` <span class="text-slate-400">(${_esc(o.notes)})</span>` : '';
      return `<div class="text-xs text-slate-600">• <span class="capitalize">${_esc(label)}</span>${id}: ${outcomeLbl}${newId}${note}</div>`;
    }).join('');
    const vNotes = v.notes ? `<p class="text-xs text-slate-500 mt-0.5 italic">${_esc(v.notes)}</p>` : '';
    const vResume = v.can_resume_from
      ? `<div class="text-xs text-slate-400 mt-0.5">Can resume from: ${_fmtDate(v.can_resume_from)}</div>` : '';
    const vAttach = (v.attachment && v.id)
      ? `<a href="/api/patients/${PATIENT_HOMER_ID}/download-attachment/${v.id}" target="_blank"
           class="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline mt-1">
           <i class="fas fa-paperclip"></i>Attachment</a>` : '';
    return `
      <div class="py-2 border-t border-slate-100">
        <div class="flex items-center justify-between flex-wrap gap-1 mb-0.5">
          <span class="text-xs font-medium text-slate-700">${typeLabel}</span>
          <span class="text-xs text-slate-400">${vDate}${vFiled ? ` <span class="text-slate-300">(filed ${vFiled})</span>` : ''}</span>
        </div>
        ${outcomes}
        ${vNotes}
        ${vResume}
        ${vAttach}
      </div>`;
  }).join('');

  const visitsSection = visits.length
    ? `<div class="mt-3 pt-2 border-t border-slate-200">
         <p class="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-1">Visit history</p>
         ${visitRows}
       </div>`
    : '';

  const cardId = (call.id || '').replace(/-/g, '');
  const alias  = call.alias || (isRI ? 'Robot Issue' : 'Other Device Issue');

  // Role-filtered event-note count, server-stamped on the entry. Hidden when zero.
  const noteCount = call.event_notes_count || 0;
  const noteCountBadge = `<span id="di-note-count-${cardId}"
      class="inline-flex items-center gap-1 text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 rounded-full px-2 py-0.5${noteCount > 0 ? '' : ' hidden'}"
      title="Event notes"><i class="fas fa-sticky-note text-[10px]"></i>${noteCount}</span>`;

  // Notes section at the bottom of the body. Notes target the call entry (the
  // whole issue), not individual visits — visit-level notes go on each visit
  // entry from the Timeline tab. Lazy-loaded on expand via _toggleDiCard.
  const notesSection = `
    <div class="mt-3 pt-3 border-t border-slate-200">
      <div class="flex items-center justify-between mb-2">
        <span class="text-sm font-semibold text-slate-700 inline-flex items-center gap-1.5">
          <i class="fas fa-sticky-note text-blue-500"></i> Notes
        </span>
        <button type="button" onclick="openEventNoteModal('${call.id}')"
                class="inline-flex items-center gap-1 px-2.5 py-1 bg-blue-600 text-white rounded-lg text-xs font-medium hover:bg-blue-700">
          <i class="fas fa-plus text-[10px]"></i> Add Note
        </button>
      </div>
      <div id="di-notes-${cardId}" data-event-id="${call.id}">
        <p class="text-xs text-slate-400 italic">Loading…</p>
      </div>
    </div>`;

  return `
    <div class="rounded-xl border ${theme.border} shadow-sm mb-3 overflow-hidden">
      <div class="${theme.headerBg} px-4 py-2.5 cursor-pointer select-none flex items-center justify-between"
           onclick="_toggleDiCard('${cardId}')">
        <div class="flex items-center gap-2.5 flex-wrap">
          <span class="text-sm font-bold ${theme.headerText}">${_esc(alias)}</span>
          <span class="text-xs text-slate-500">${theme.label}</span>
          ${statusBadge}${pausedBadge}${noteCountBadge}
        </div>
        <i class="fas fa-chevron-down text-xs ${theme.headerText}" id="di-chevron-${cardId}"
           style="transition: transform 0.15s"></i>
      </div>
      <div class="px-4 py-2 border-b border-slate-100 bg-white flex items-center flex-wrap gap-0">${metaParts}</div>
      <div id="di-body-${cardId}" class="hidden bg-white px-4 py-3 space-y-1.5">
        ${deviceRowsHtml}
        ${triggerStr}
        ${call.notes ? `<div class="text-xs text-slate-500"><span class="text-slate-400">Notes:</span> ${_esc(call.notes)}</div>` : ''}
        ${attachmentStr}
        ${visitsSection}
        ${notesSection}
      </div>
    </div>`;
}

// ── Adverse Event modal ────────────────────────────────────────────────────────

const _AE_TRIGGER_NAMES = {
  activation:         'Patient Activation',
  activation_attempt: 'Activation Attempt (training not completed)',
  primary_reason:     'Primary Reason',
  home_visit_d02:     'Home Visit Day 02',
  home_visit_d03:     'Home Visit Day 03',
  home_visit_d15:     'Home Visit Day 15',
  followup_call_d07:  'Follow-up Call Day 07',
  followup_call_d21:  'Follow-up Call Day 21',
  patient_call:       'Patient Call',
};

let _aeEventId = null;

function openAdverseEventModal(ev) {
  _aeEventId = ev.id;
  const triggerLabel = ev.triggered_by
    ? (_AE_TRIGGER_NAMES[ev.triggered_by.type] || ev.triggered_by.type)
    : 'Unknown';
  document.getElementById('ae-context-banner').textContent = `Triggered by: ${triggerLabel}`;
  document.getElementById('ae-date').value         = '';
  document.getElementById('ae-description').value  = '';
  document.getElementById('ae-action-taken').value = '';
  const isActivated = !!patientData?.activationDate;
  document.getElementById('ae-paused-wrap').classList.toggle('hidden', !isActivated);
  document.getElementById('ae-paused').checked = isActivated && !!ev.training_stopped;

  document.getElementById('ae-schedule-visit').checked    = false;
  document.getElementById('ae-visit-date-wrap').classList.add('hidden');
  document.getElementById('ae-visit-date').value           = '';
  document.getElementById('ae-schedule-clinical').checked  = false;
  document.getElementById('ae-clinical-date-wrap').classList.add('hidden');
  document.getElementById('ae-clinical-date').value        = '';

  document.getElementById('ae-schedule-visit').onchange = () => {
    const on = document.getElementById('ae-schedule-visit').checked;
    document.getElementById('ae-visit-date-wrap').classList.toggle('hidden', !on);
    if (!on) document.getElementById('ae-visit-date').value = '';
  };
  document.getElementById('ae-schedule-clinical').onchange = () => {
    const on = document.getElementById('ae-schedule-clinical').checked;
    document.getElementById('ae-clinical-date-wrap').classList.toggle('hidden', !on);
    if (!on) document.getElementById('ae-clinical-date').value = '';
  };

  _resetAttachment('ae');
  setError('ae-error', '');
  _attachDateGuard('ae-date', 'ae-error');
  showModal('adverse-event-modal');
}

async function saveAdverseEvent() {
  const date             = document.getElementById('ae-date').value;
  const description      = document.getElementById('ae-description').value.trim();
  const actionTaken      = document.getElementById('ae-action-taken').value.trim();
  const training_blocked = document.getElementById('ae-paused').checked;
  const saveBtn          = document.getElementById('ae-save');

  const scheduleVisit    = document.getElementById('ae-schedule-visit').checked;
  const visitDate        = document.getElementById('ae-visit-date').value;
  const scheduleClinical = document.getElementById('ae-schedule-clinical').checked;
  const clinicalDate     = document.getElementById('ae-clinical-date').value;

  if (!date)        { setError('ae-error', 'Event date is required.'); return; }
  if (!description) { setError('ae-error', 'Description is required.'); return; }
  if (!actionTaken) { setError('ae-error', 'Action taken is required.'); return; }
  if (scheduleVisit && !visitDate)    { setError('ae-error', 'Follow-up visit date is required.'); return; }
  if (scheduleClinical && !clinicalDate) { setError('ae-error', 'Clinical visit date is required.'); return; }
  if (!_validateAttachment('ae', 'ae-error')) return;

  saveBtn.disabled = true;
  const payload = {
    event_id: _aeEventId, completion_date: date, description,
    action_taken: actionTaken, training_blocked,
    scheduled_followup_visit:  scheduleVisit    ? visitDate    : null,
    scheduled_clinical_visit:  scheduleClinical ? clinicalDate : null,
  };
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/adverse-event`, payload
  );
  if (!ok) { setError('ae-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }

  const { file, caption } = _readAttachment('ae');
  if (file) {
    const uploaded = await _uploadAttachment(data.id, file, caption, 'ae-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  hideModal('adverse-event-modal');
  saveBtn.disabled = false;
  await loadPatientEvents();
}

// ── Device Issue Date Validation Helpers ───────────────────────────────────────

async function _fetchIssueValidationDates(triggeredById) {
  try {
    const res = await fetch(`/api/patients/${PATIENT_HOMER_ID}/issue-validation-dates`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ triggered_by_id: triggeredById || '' }),
    });
    if (!res.ok) {
      console.error(`API error: ${res.status}`);
      return { enroll_date: null, issue_occur_date: null };
    }
    const data = await res.json();
    return data;
  } catch (e) {
    console.error('Failed to fetch issue validation dates:', e);
    return { enroll_date: null, issue_occur_date: null };
  }
}

function _setIssueModalDateBounds(enrollDate, issueOccurDate, issueOccurInputId, visitInputId) {
  const today = new Date().toISOString().split('T')[0];

  function formatDateForInput(dateStr, inputElement) {
    if (!dateStr) return null;
    if (inputElement.type === 'datetime-local') {
      // datetime-local needs YYYY-MM-DDTHH:MM format
      return dateStr.includes('T') ? dateStr.substring(0, 16) : dateStr + 'T00:00';
    } else {
      // date input needs YYYY-MM-DD format
      return dateStr.split('T')[0];
    }
  }

  if (issueOccurInputId) {
    const inp = document.getElementById(issueOccurInputId);
    if (inp) {
      const formattedEnrollDate = formatDateForInput(enrollDate, inp);
      if (formattedEnrollDate) {
        inp.min = formattedEnrollDate;
      } else {
        inp.removeAttribute('min');
      }
      // For datetime-local, also format today
      if (inp.type === 'datetime-local') {
        inp.max = today + 'T23:59';
      } else {
        inp.max = today;
      }
    } else {
      console.warn(`Could not find input: ${issueOccurInputId}`);
    }
  }
  if (visitInputId) {
    const inp = document.getElementById(visitInputId);
    if (inp) {
      const formattedIssueDate = formatDateForInput(issueOccurDate, inp);
      if (formattedIssueDate) {
        inp.min = formattedIssueDate;
      } else {
        inp.removeAttribute('min');
      }
      // For datetime-local, also format today
      if (inp.type === 'datetime-local') {
        inp.max = today + 'T23:59';
      } else {
        inp.max = today;
      }
    } else {
      console.warn(`Could not find input: ${visitInputId}`);
    }
  }
}

// ── Robot Issue Call modal ─────────────────────────────────────────────────────

let _ricEventId = null;
let _ricIsBp    = false;

async function openRobotIssueCallModal(ev) {
  _ricEventId = ev.id;
  _ricIsBp    = !!patientData?.brokenProtocolDate;
  const triggerType  = ev.triggered_by?.type || '';
  const triggerName  = _AE_TRIGGER_NAMES[triggerType] || triggerType;
  const triggerEvent = (_completeEventsCache || []).find(e => e.id === ev.triggered_by?.id);
  const dateStr = triggerEvent?.completion_date ? ` on ${_fmtDateTime(triggerEvent.completion_date)}` : '';
  document.getElementById('ric-context-banner').textContent =
    `Robot issue reported during ${triggerName}${dateStr}`;
  document.getElementById('ric-bp-banner').classList.toggle('hidden', !_ricIsBp);
  document.getElementById('ric-date').value             = '';
  document.getElementById('ric-issue-occur-date').value = '';
  document.getElementById('ric-notes').value             = '';
  document.querySelectorAll('input[name="ric-call-mode"]').forEach(r => { r.checked = false; });
  _resetAttachment('ric');
  setError('ric-error', '');
  _attachDateGuard('ric-date', 'ric-error');

  // Build per-device inline sections
  const container = document.getElementById('ric-device-sections');
  container.innerHTML = '';
  for (const device of ['pluto', 'mars']) {
    const label = device.charAt(0).toUpperCase() + device.slice(1);
    const sec = document.createElement('div');
    sec.className = 'border border-slate-200 rounded-xl p-4';
    if (_ricIsBp) {
      sec.innerHTML = `
        <label class="flex items-center gap-2 cursor-pointer select-none">
          <input type="checkbox" id="ric-${device}-on" class="w-4 h-4 rounded border-slate-300 accent-orange-600">
          <span class="text-sm font-semibold text-slate-800">${label}</span>
        </label>
        <div id="ric-${device}-form" class="hidden mt-3 pl-6">
          <label class="block text-xs font-medium text-slate-600 mb-1">Fault description <span class="text-red-400">*</span></label>
          <textarea id="ric-${device}-notes" rows="2"
            class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 resize-none"
            placeholder="Describe the fault on ${label}…"></textarea>
        </div>
      `;
    } else {
      sec.innerHTML = `
        <label class="flex items-center gap-2 cursor-pointer select-none">
          <input type="checkbox" id="ric-${device}-on" class="w-4 h-4 rounded border-slate-300 accent-orange-600">
          <span class="text-sm font-semibold text-slate-800">${label}</span>
        </label>
        <div id="ric-${device}-form" class="hidden mt-3 space-y-3 pl-6">
          <div>
            <p class="text-xs font-medium text-slate-600 mb-2">Outcome <span class="text-red-400">*</span></p>
            <div class="space-y-1">
              <label class="flex items-center gap-2 cursor-pointer">
                <input type="radio" name="ric-${device}-outcome" value="resolved" class="w-4 h-4 accent-orange-600">
                <span class="text-sm text-slate-700">Resolved by call — no visit needed</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer">
                <input type="radio" name="ric-${device}-outcome" value="visit_required" class="w-4 h-4 accent-orange-600">
                <span class="text-sm text-slate-700">Visit required</span>
              </label>
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-600 mb-1">Notes <span class="text-red-400">*</span></label>
            <textarea id="ric-${device}-notes" rows="2"
              class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 resize-none"
              placeholder="What was discussed for ${label}…"></textarea>
          </div>
        </div>
      `;
    }
    container.appendChild(sec);

    document.getElementById(`ric-${device}-on`).onchange = function () {
      document.getElementById(`ric-${device}-form`).classList.toggle('hidden', !this.checked);
      if (!this.checked) {
        if (!_ricIsBp) {
          document.querySelectorAll(`input[name="ric-${device}-outcome"]`).forEach(r => r.checked = false);
        }
        document.getElementById(`ric-${device}-notes`).value = '';
      }
      _ricUpdateNotesLabel();
    };
  }

  // In normal mode only: pre-check visit_required when stub was the primary training-stop reason
  if (!_ricIsBp && ev.training_stopped) {
    for (const device of ['pluto', 'mars']) {
      const onCb = document.getElementById(`ric-${device}-on`);
      if (onCb && !onCb.checked) {
        onCb.checked = true;
        document.getElementById(`ric-${device}-form`).classList.remove('hidden');
        const visitRadio = document.querySelector(`input[name="ric-${device}-outcome"][value="visit_required"]`);
        if (visitRadio) visitRadio.checked = true;
      }
    }
  }

  _ricUpdateNotesLabel();

  // Fetch and set date validation bounds BEFORE showing modal
  const dates = await _fetchIssueValidationDates();
  _setIssueModalDateBounds(dates.enroll_date, null, 'ric-issue-occur-date', 'ric-date');

  showModal('robot-issue-call-modal');
}

function _ricUpdateNotesLabel() {
  const anyChecked = ['pluto', 'mars'].some(d => document.getElementById(`ric-${d}-on`)?.checked);
  document.getElementById('ric-notes-required-badge').classList.toggle('hidden', anyChecked);
  document.getElementById('ric-notes-optional-badge').classList.toggle('hidden', !anyChecked);
}

async function saveRobotIssueCall() {
  const date           = document.getElementById('ric-date').value;
  let issueOccurDate   = document.getElementById('ric-issue-occur-date').value || null;
  const callMode       = document.querySelector('input[name="ric-call-mode"]:checked')?.value || '';
  const notes          = document.getElementById('ric-notes').value.trim();
  const saveBtn        = document.getElementById('ric-save');

  // Convert dd-mm-yyyy to YYYY-MM-DD if needed
  if (issueOccurDate && /^\d{2}-\d{2}-\d{4}$/.test(issueOccurDate)) {
    const parts = issueOccurDate.split('-');
    issueOccurDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
  }

  if (!date)     { setError('ric-error', 'Call date is required.'); return; }
  if (!callMode) { setError('ric-error', 'Call mode (Audio / Video) is required.'); return; }

  const devices = [];
  for (const device of ['pluto', 'mars']) {
    if (!document.getElementById(`ric-${device}-on`).checked) continue;
    const devNotes = document.getElementById(`ric-${device}-notes`).value.trim();
    const label    = device.charAt(0).toUpperCase() + device.slice(1);
    if (!devNotes) { setError('ric-error', `${_ricIsBp ? 'Fault description' : 'Notes'} required for ${label}.`); return; }
    if (_ricIsBp) {
      devices.push({ device, notes: devNotes });
    } else {
      const outcome = document.querySelector(`input[name="ric-${device}-outcome"]:checked`)?.value || '';
      if (!outcome) { setError('ric-error', `Outcome is required for ${label}.`); return; }
      devices.push({ device, outcome, notes: devNotes });
    }
  }

  if (!devices.length && !notes) {
    setError('ric-error', 'Overall notes are required when no device is selected.');
    return;
  }
  if (!_validateAttachment('ric', 'ric-error')) return;

  // Validate dates
  const today = new Date().toISOString().split('T')[0];
  if (!issueOccurDate) {
    setError('ric-error', 'Issue occurred date is required.');
    return;
  }
  if (issueOccurDate > today) {
    setError('ric-error', 'Issue occurred date cannot be in the future.');
    return;
  }
  const minDate = document.getElementById('ric-issue-occur-date').min;
  if (minDate && issueOccurDate < minDate) {
    setError('ric-error', `Issue occurred date must be on or after activation date (${minDate}).`);
    return;
  }
  // Validate call date is after issue occurred date
  if (date.split('T')[0] < issueOccurDate) {
    setError('ric-error', 'Call date must be on or after issue occurred date.');
    return;
  }
  if (date.split('T')[0] > today) {
    setError('ric-error', 'Call date cannot be in the future.');
    return;
  }

  saveBtn.disabled = true;
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/robot-issue-call`,
    { event_id: _ricEventId, completion_date: date, issue_occur_date: issueOccurDate,
      call_mode: callMode, notes: notes || null, devices, broken_protocol_mode: _ricIsBp }
  );
  if (!ok) { setError('ric-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }

  const { file, caption } = _readAttachment('ric');
  if (file) {
    const uploaded = await _uploadAttachment(_ricEventId, file, caption, 'ric-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  hideModal('robot-issue-call-modal');
  saveBtn.disabled = false;
  await loadPatientEvents();
}

// ── Robot Issue Visit modal ────────────────────────────────────────────────────

let _rivEventId = null;
let _rivDevices = []; // [{device_type, old_device_id, available}]
let _rivIsBp    = false;

async function openRobotIssueVisitModal(ev) {
  _rivEventId = ev.id;
  _rivDevices = [];
  _rivIsBp    = !!patientData?.brokenProtocolDate;

  const callEvent = (_completeEventsCache || []).find(e => e.id === ev.triggered_by?.id);
  const dateStr   = callEvent?.completion_date ? ` on ${_fmtDateTime(callEvent.completion_date)}` : '';
  document.getElementById('riv-context-banner').textContent =
    `Robot issue call${dateStr}`;
  document.getElementById('riv-bp-banner').classList.toggle('hidden', !_rivIsBp);
  document.getElementById('riv-date').value  = '';
  document.getElementById('riv-notes').value = '';
  document.getElementById('riv-device-rows').innerHTML =
    '<p class="text-sm text-slate-400 italic">Loading device info…</p>';
  _resetAttachment('riv');
  setError('riv-error', '');
  _attachDateGuard('riv-date', 'riv-error');

  // Fetch and set date validation bounds BEFORE showing modal
  const dates = await _fetchIssueValidationDates(ev.triggered_by?.id);
  _setIssueModalDateBounds(null, dates.issue_occur_date, null, 'riv-date');

  showModal('robot-issue-visit-modal');

  try {
    const res = await fetch(`/api/patients/${PATIENT_HOMER_ID}/available-devices`);
    const devData = await res.json();
    for (const deviceType of ['pluto', 'mars']) {
      const cur = deviceType === 'pluto' ? devData.current_pluto : devData.current_mars;
      _rivDevices.push({
        device_type:   deviceType,
        old_device_id: cur,
        available:     devData[deviceType] || [],
      });
    }
    _buildRivDeviceRows();
  } catch (e) {
    document.getElementById('riv-device-rows').innerHTML =
      '<p class="text-sm text-red-500">Failed to load device info.</p>';
  }
}

function _rivBpFaultChange(deviceType) {
  const checked = document.getElementById(`riv-bp-${deviceType}-fault`)?.checked;
  document.getElementById(`riv-bp-${deviceType}-desc-wrap`)?.classList.toggle('hidden', !checked);
}

function _buildRivDeviceRows() {
  const container = document.getElementById('riv-device-rows');
  container.innerHTML = '';

  if (_rivIsBp) {
    for (const dev of _rivDevices) {
      const label = dev.device_type.charAt(0).toUpperCase() + dev.device_type.slice(1);
      const oldLabel = dev.old_device_id
        ? `<span class="font-mono">${dev.old_device_id}</span>`
        : '<span class="text-slate-400 italic">None assigned</span>';
      const rowDiv = document.createElement('div');
      rowDiv.className = 'border border-slate-200 rounded-xl p-4 space-y-3';
      rowDiv.innerHTML = `
        <div class="flex items-center justify-between">
          <span class="text-sm font-semibold text-slate-800">${label}</span>
          <span class="text-xs text-slate-500">Current: ${oldLabel}</span>
        </div>
        <div class="flex items-center gap-2">
          <input type="checkbox" id="riv-bp-${dev.device_type}-fault" class="w-4 h-4 accent-amber-600"
            onchange="_rivBpFaultChange('${dev.device_type}')">
          <label for="riv-bp-${dev.device_type}-fault" class="text-sm text-slate-700 cursor-pointer">This device has a fault</label>
        </div>
        <div id="riv-bp-${dev.device_type}-desc-wrap" class="hidden pl-2 border-l-2 border-amber-200">
          <label class="block text-xs font-medium text-slate-600 mb-1">Fault description <span class="text-red-400">*</span></label>
          <textarea id="riv-bp-${dev.device_type}-desc" rows="2"
            class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-200 resize-none"
            placeholder="Describe the fault…"></textarea>
        </div>
      `;
      container.appendChild(rowDiv);
    }
    return;
  }

  for (const dev of _rivDevices) {
    const label = dev.device_type.charAt(0).toUpperCase() + dev.device_type.slice(1);
    const oldLabel = dev.old_device_id
      ? `<span class="font-mono">${dev.old_device_id}</span>`
      : '<span class="text-slate-400 italic">None assigned</span>';

    let swapOptions = '<option value="">No device available</option>';
    for (const d of dev.available) {
      swapOptions += `<option value="${d.id}">${d.id}</option>`;
    }

    const rowDiv = document.createElement('div');
    rowDiv.className = 'border border-slate-200 rounded-xl p-4 space-y-3';
    rowDiv.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="text-sm font-semibold text-slate-800">${label}</span>
        <span class="text-xs text-slate-500">Current: ${oldLabel}</span>
      </div>
      <div>
        <p class="text-xs font-medium text-slate-600 mb-2">Outcome <span class="text-red-400">*</span></p>
        <div class="space-y-2">
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="radio" name="riv-${dev.device_type}-outcome" value="repaired_on_site" class="w-4 h-4 accent-orange-600"
              onchange="_rivOutcomeChange('${dev.device_type}')">
            <span class="text-sm text-slate-700">Repaired on site</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="radio" name="riv-${dev.device_type}-outcome" value="swapped" class="w-4 h-4 accent-orange-600"
              onchange="_rivOutcomeChange('${dev.device_type}')">
            <span class="text-sm text-slate-700">Swapped</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="radio" name="riv-${dev.device_type}-outcome" value="neither" class="w-4 h-4 accent-orange-600"
              onchange="_rivOutcomeChange('${dev.device_type}')">
            <span class="text-sm text-slate-700">Neither (no action taken)</span>
          </label>
        </div>
      </div>
      <!-- Repaired on site fields -->
      <div id="riv-${dev.device_type}-repaired-fields" class="hidden space-y-2 pl-2 border-l-2 border-orange-200">
        <div>
          <label class="block text-xs font-medium text-slate-600 mb-1">Notes <span class="text-red-400">*</span></label>
          <textarea id="riv-${dev.device_type}-repair-notes" rows="2"
            class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 resize-none"
            placeholder="Describe what was done to fix the device…"></textarea>
        </div>
      </div>
      <!-- Swapped fields -->
      <div id="riv-${dev.device_type}-swapped-fields" class="hidden space-y-2 pl-2 border-l-2 border-orange-200">
        <div>
          <p class="text-xs font-medium text-slate-600 mb-2">Swap type <span class="text-red-400">*</span></p>
          <div class="space-y-1">
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="riv-${dev.device_type}-swap-type" value="fault_driven" class="w-4 h-4 accent-orange-600">
              <span class="text-sm text-slate-700">Fault-driven (device suspected/confirmed faulty)</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="riv-${dev.device_type}-swap-type" value="preventive" class="w-4 h-4 accent-orange-600">
              <span class="text-sm text-slate-700">Preventive (precautionary replacement)</span>
            </label>
          </div>
        </div>
        <div>
          <label class="block text-xs font-medium text-slate-600 mb-1">New device <span class="text-red-400">*</span></label>
          <select id="riv-${dev.device_type}-new-device"
            class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 bg-white">
            ${swapOptions}
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-slate-600 mb-1">Notes <span class="text-slate-400 font-normal">(optional)</span></label>
          <textarea id="riv-${dev.device_type}-swap-notes" rows="2"
            class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 resize-none"
            placeholder="Reason for swap…"></textarea>
        </div>
      </div>
      <!-- Neither fields -->
      <div id="riv-${dev.device_type}-neither-fields" class="hidden pl-2 border-l-2 border-slate-200">
        <label class="block text-xs font-medium text-slate-600 mb-1">Notes <span class="text-red-400">*</span></label>
        <textarea id="riv-${dev.device_type}-neither-notes" rows="2"
          class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none"
          placeholder="Explain why no action was taken (e.g. only the other device was affected)…"></textarea>
      </div>
    `;
    container.appendChild(rowDiv);
  }
}

function _rivOutcomeChange(deviceType) {
  const outcome = document.querySelector(`input[name="riv-${deviceType}-outcome"]:checked`)?.value;
  document.getElementById(`riv-${deviceType}-repaired-fields`).classList.toggle('hidden', outcome !== 'repaired_on_site');
  document.getElementById(`riv-${deviceType}-swapped-fields`).classList.toggle('hidden', outcome !== 'swapped');
  document.getElementById(`riv-${deviceType}-neither-fields`).classList.toggle('hidden', outcome !== 'neither');
}

async function saveRobotIssueVisit() {
  const date    = document.getElementById('riv-date').value;
  const notes   = document.getElementById('riv-notes').value.trim();
  const saveBtn = document.getElementById('riv-save');

  if (!date) { setError('riv-error', 'Visit date is required.'); return; }

  // Validate visit date
  const today = new Date().toISOString().split('T')[0];
  if (date.split('T')[0] > today) {
    setError('riv-error', 'Visit date cannot be in the future.');
    return;
  }
  const minDate = document.getElementById('riv-date').min;
  if (minDate && date.split('T')[0] < minDate.split('T')[0]) {
    setError('riv-error', `Visit date must be on or after issue occurred date (${minDate.split('T')[0]}).`);
    return;
  }

  // ── Broken-protocol mode ──────────────────────────────────────────────────
  if (_rivIsBp) {
    const deviceFaults = [];
    for (const dev of _rivDevices) {
      const hasFault = document.getElementById(`riv-bp-${dev.device_type}-fault`)?.checked;
      if (hasFault) {
        const desc = document.getElementById(`riv-bp-${dev.device_type}-desc`)?.value.trim() || '';
        if (!desc) { setError('riv-error', `Please describe the fault for ${dev.device_type}.`); return; }
        deviceFaults.push({ device: dev.device_type, notes: desc });
      }
    }
    if (!_validateAttachment('riv', 'riv-error')) return;
    saveBtn.disabled = true;
    const { ok, data } = await apiPost(
      `/api/patients/${PATIENT_HOMER_ID}/complete-event/robot-issue-visit`,
      { event_id: _rivEventId, completion_date: date, notes, device_faults: deviceFaults, broken_protocol_mode: true }
    );
    if (!ok) { setError('riv-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }
    const { file, caption } = _readAttachment('riv');
    if (file) {
      const uploaded = await _uploadAttachment(_rivEventId, file, caption, 'riv-error');
      if (!uploaded) { saveBtn.disabled = false; return; }
    }
    hideModal('robot-issue-visit-modal');
    saveBtn.disabled = false;
    await loadPatientEvents();
    return;
  }
  // ─────────────────────────────────────────────────────────────────────────

  const deviceOutcomes = [];
  for (const dev of _rivDevices) {
    const outcome = document.querySelector(`input[name="riv-${dev.device_type}-outcome"]:checked`)?.value || '';
    const capLabel = dev.device_type.charAt(0).toUpperCase() + dev.device_type.slice(1);
    if (!outcome) { setError('riv-error', `Outcome is required for ${capLabel}.`); return; }

    let payload = { device: dev.device_type, outcome, old_device_id: dev.old_device_id };

    if (outcome === 'repaired_on_site') {
      const repairNotes = document.getElementById(`riv-${dev.device_type}-repair-notes`).value.trim();
      if (!repairNotes) { setError('riv-error', `${capLabel} repair notes are required.`); return; }
      payload.notes = repairNotes;
    } else if (outcome === 'swapped') {
      const swapType  = document.querySelector(`input[name="riv-${dev.device_type}-swap-type"]:checked`)?.value;
      const newDevice = document.getElementById(`riv-${dev.device_type}-new-device`).value || null;
      const swapNotes = document.getElementById(`riv-${dev.device_type}-swap-notes`).value.trim();
      if (!swapType) { setError('riv-error', `${capLabel} swap type is required.`); return; }
      payload.new_device_id = newDevice;
      payload.swap_type     = swapType;
      payload.notes         = swapNotes || null;
    } else {
      const neitherNotes = document.getElementById(`riv-${dev.device_type}-neither-notes`).value.trim();
      if (!neitherNotes) { setError('riv-error', `${capLabel} notes are required.`); return; }
      payload.notes = neitherNotes;
    }
    deviceOutcomes.push(payload);
  }

  if (!_validateAttachment('riv', 'riv-error')) return;

  saveBtn.disabled = true;
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/robot-issue-visit`,
    { event_id: _rivEventId, completion_date: date, notes, device_outcomes: deviceOutcomes }
  );
  if (!ok) { setError('riv-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }

  const { file, caption } = _readAttachment('riv');
  if (file) {
    const uploaded = await _uploadAttachment(_rivEventId, file, caption, 'riv-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  hideModal('robot-issue-visit-modal');
  saveBtn.disabled = false;
  await loadPatientEvents();
}

// ── Adverse Event Follow-up modal ─────────────────────────────────────────────

let _aefEventId    = null;
let _aefAeDetails  = [];   // [{id, date, training_blocked}] for each AE in stub

function _trainingPermanentlyEnded() {
  if (!patientData) return false;
  if (patientData.trainingCompletionDate || patientData.brokenProtocolDate || patientData.discontinuationDate) return true;
  if (patientData.activationDate) {
    const day28End = new Date(patientData.activationDate);
    day28End.setDate(day28End.getDate() + 28);
    if (new Date() > day28End) return true;
  }
  return false;
}

// `lockedFrom`, when provided, indicates this AE follow-up was opened as a
// post-save side effect of a parent visit/call (D29, D07, D21) where the AE
// discussion happened inside that same visit. In that case the call date and
// duration are sourced from the parent and the date input is made read-only —
// the AE follow-up isn't really a separate moment in time, it's a captured
// detail of the parent visit. Shape: `{date, duration?, label}`. When null,
// the standalone-open path runs with the framework's normal editable bounds.
function openAdverseEventFollowupModal(ev, lockedFrom = null) {
  _aefEventId   = ev.id;
  const aeIds   = ev.adverse_event_ids || [];

  // Look up each AE from the complete cache
  _aefAeDetails = aeIds.map(id => {
    const ae = (_completeEventsCache || []).find(e => e.id === id);
    return {
      id:               id,
      alias:            ae?.alias || '',
      date:             ae?.completion_date || '',
      training_blocked: ae?.training_blocked || false,
    };
  });

  // Set modal title with aliases
  const aliases = _aefAeDetails.map(ae => ae.alias).filter(Boolean);
  const titleEl = document.getElementById('aef-title');
  if (titleEl) titleEl.textContent = aliases.length
    ? `Adverse Event Follow-up — ${aliases.join(', ')}`
    : 'Adverse Event Follow-up';

  // Build context banner
  const banner = document.getElementById('aef-context-banner');
  banner.innerHTML = _aefAeDetails.length
    ? _aefAeDetails.map(ae => {
        const label    = ae.alias || 'Adverse Event';
        const dateStr  = ae.date ? ` — ${_fmtDateTime(ae.date)}` : '';
        const pauseTag = ae.training_blocked
          ? ' <span class="text-red-600 font-medium">(training blocked)</span>' : '';
        return `<div>${label}${dateStr}${pauseTag}</div>`;
      }).join('')
    : '<div class="text-slate-400">No adverse events found.</div>';

  // Build per-AE resolution rows
  const rowsEl = document.getElementById('aef-ae-rows');
  rowsEl.innerHTML = _aefAeDetails.map((ae, i) => {
    const dateStr = ae.date ? _fmtDateTime(ae.date) : 'Unknown date';
    const resumeField = (ae.training_blocked && !_trainingPermanentlyEnded())
      ? `<div id="aef-resume-wrap-${i}" class="hidden mt-2">
           <label class="block text-xs font-medium text-slate-600 mb-1">Can resume from <span class="text-red-400">*</span></label>
           <input type="date" id="aef-resume-${i}" class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-300">
         </div>` : '';
    return `<div class="p-3 rounded-xl border border-slate-200 bg-slate-50 space-y-2">
      <div class="text-sm font-medium text-slate-700">${ae.alias || 'Adverse Event'} — ${dateStr}</div>
      <div>
        <label class="block text-xs font-medium text-slate-600 mb-1">Discussion notes</label>
        <textarea id="aef-disc-${i}" rows="2" class="w-full px-3 py-2 border border-slate-200 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none" placeholder="What was discussed for this AE…"></textarea>
      </div>
      <label class="flex items-center gap-2 cursor-pointer select-none">
        <input type="checkbox" id="aef-resolved-${i}" onchange="_aefToggleResume(${i})" class="w-4 h-4 rounded border-slate-300">
        <span class="text-sm text-slate-700">Resolved</span>
      </label>
      ${resumeField}
    </div>`;
  }).join('');

  const dateInput = document.getElementById('aef-date');
  const lockHint  = document.getElementById('aef-date-lock-hint');
  const lockText  = document.getElementById('aef-date-lock-hint-text');
  dateInput.value     = '';
  dateInput.readOnly  = false;            // reset from any previous locked open
  dateInput.classList.remove('bg-slate-100', 'cursor-not-allowed');
  if (lockHint) lockHint.classList.add('hidden');
  document.getElementById('aef-duration').value  = '';
  document.getElementById('aef-notes').value     = '';
  document.querySelectorAll('input[name="aef-call-mode"]').forEach(r => { r.checked = false; });
  document.querySelectorAll('input[name="aef-initiator"]').forEach(r => { r.checked = false; });
  _setupAeSchedulingToggles('aef');
  _resetAttachment('aef');
  setError('aef-error', '');
  _attachDateGuard('aef-date', 'aef-error');

  // Apply lock when opened from a parent event: pre-fill date (always) and
  // duration (when known), and mark the date read-only with a small hint.
  if (lockedFrom && lockedFrom.date) {
    dateInput.value    = lockedFrom.date;
    dateInput.readOnly = true;
    dateInput.classList.add('bg-slate-100', 'cursor-not-allowed');
    if (lockHint && lockText) {
      lockText.textContent = `Synced from ${lockedFrom.label || 'parent visit'} — date cannot be changed.`;
      lockHint.classList.remove('hidden');
    }
    if (lockedFrom.duration) {
      document.getElementById('aef-duration').value = lockedFrom.duration;
    }
  }

  showModal('adverse-event-followup-modal');
}

function _aeAllResolved(prefix, count) {
  for (let i = 0; i < count; i++) {
    if (!document.getElementById(`${prefix}-resolved-${i}`)?.checked) return false;
  }
  return true;
}

function _aeUpdateSchedulingOnResolve(prefix, count) {
  const allResolved = _aeAllResolved(prefix, count);
  ['visit', 'clinical'].forEach(kind => {
    const cb       = document.getElementById(`${prefix}-schedule-${kind}`);
    const dateWrap = document.getElementById(`${prefix}-${kind}-date-wrap`);
    const dateInput = document.getElementById(`${prefix}-${kind}-date`);
    if (!cb) return;
    cb.disabled = allResolved;
    if (allResolved && cb.checked) {
      cb.checked = false;
      if (dateWrap)  dateWrap.classList.add('hidden');
      if (dateInput) dateInput.value = '';
    }
  });
}

function _aefToggleResume(i) {
  const resolved = document.getElementById(`aef-resolved-${i}`).checked;
  const wrap = document.getElementById(`aef-resume-wrap-${i}`);
  if (wrap) {
    wrap.classList.toggle('hidden', !resolved);
    if (!resolved) document.getElementById(`aef-resume-${i}`).value = '';
  }
  _aeUpdateSchedulingOnResolve('aef', _aefAeDetails.length);
}

async function saveAdverseEventFollowup() {
  const date      = document.getElementById('aef-date').value;
  const durStr    = document.getElementById('aef-duration').value.trim();
  const callMode  = document.querySelector('input[name="aef-call-mode"]:checked')?.value || '';
  const initiator = document.querySelector('input[name="aef-initiator"]:checked')?.value || '';
  const notes     = document.getElementById('aef-notes').value.trim();
  const saveBtn   = document.getElementById('aef-save');

  if (!date)      { setError('aef-error', 'Call date is required.'); return; }
  if (!durStr)    { setError('aef-error', 'Duration is required.'); return; }
  const duration  = parseInt(durStr, 10);
  if (!duration || duration <= 0) { setError('aef-error', 'Duration must be a positive number.'); return; }
  if (!callMode)  { setError('aef-error', 'Call mode (Audio / Video) is required.'); return; }
  if (!initiator) { setError('aef-error', 'Please indicate who initiated this call (Therapist / Patient).'); return; }
  if (!notes)     { setError('aef-error', 'Notes are required.'); return; }

  const ae_discussions = [];
  for (let i = 0; i < _aefAeDetails.length; i++) {
    const ae       = _aefAeDetails[i];
    const resolved = document.getElementById(`aef-resolved-${i}`).checked;
    let can_resume_from = null;
    if (resolved && ae.training_blocked && !_trainingPermanentlyEnded()) {
      can_resume_from = document.getElementById(`aef-resume-${i}`)?.value || '';
      if (!can_resume_from) {
        setError('aef-error', 'Can resume from date is required for resolved training-blocked events.');
        return;
      }
    }
    const notes = document.getElementById(`aef-disc-${i}`)?.value.trim() || null;
    ae_discussions.push({ adverse_event_id: ae.id, notes, resolved, can_resume_from });
  }

  const { scheduledFollowupVisit, scheduledClinicalVisit, error: schedError } = _collectAeScheduling('aef');
  if (schedError) { setError('aef-error', schedError); return; }
  if (!_validateAttachment('aef', 'aef-error')) return;

  saveBtn.disabled = true;
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/adverse-event-followup`,
    { event_id: _aefEventId, completion_date: date, duration_minutes: duration, call_mode: callMode,
      patient_initiated: initiator === 'patient', notes, ae_discussions,
      scheduled_followup_visit: scheduledFollowupVisit, scheduled_clinical_visit: scheduledClinicalVisit }
  );
  if (!ok) { setError('aef-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }

  const { file, caption } = _readAttachment('aef');
  if (file) {
    const uploaded = await _uploadAttachment(_aefEventId, file, caption, 'aef-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  hideModal('adverse-event-followup-modal');
  saveBtn.disabled = false;
  await loadPatientEvents();
}

// ── AE Follow-up Visit modal ──────────────────────────────────────────────────

let _aefvEventId   = null;
let _aefvAeDetails = [];

function _buildAeVisitRows(prefix, aeDetails) {
  return aeDetails.map((ae, i) => {
    const dateStr = ae.date ? _fmtDateTime(ae.date) : 'Unknown date';
    const pauseTag = ae.training_blocked
      ? ' <span class="text-xs text-red-600 font-medium">(training blocked)</span>' : '';
    const resumeField = (ae.training_blocked && !_trainingPermanentlyEnded())
      ? `<div id="${prefix}-resume-wrap-${i}" class="hidden mt-2">
           <label class="block text-xs font-medium text-slate-600 mb-1">Can resume from <span class="text-red-400">*</span></label>
           <input type="date" id="${prefix}-resume-${i}" class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-300">
         </div>` : '';
    return `<div class="p-3 rounded-xl border border-slate-200 bg-slate-50 space-y-2">
      <div class="text-sm font-medium text-slate-700">${ae.alias || 'Adverse Event'} — ${dateStr}${pauseTag}</div>
      <div>
        <label class="block text-xs font-medium text-slate-600 mb-1">Discussion notes</label>
        <textarea id="${prefix}-disc-${i}" rows="2" class="w-full px-3 py-2 border border-slate-200 rounded-xl text-xs focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none" placeholder="What was discussed for this AE…"></textarea>
      </div>
      <label class="flex items-center gap-2 cursor-pointer select-none">
        <input type="checkbox" id="${prefix}-resolved-${i}" onchange="_aeVisitToggleResume('${prefix}', ${i})" class="w-4 h-4 rounded border-slate-300">
        <span class="text-sm text-slate-700">Resolved</span>
      </label>
      ${resumeField}
    </div>`;
  }).join('');
}

function _aeVisitToggleResume(prefix, i) {
  const resolved = document.getElementById(`${prefix}-resolved-${i}`).checked;
  const wrap = document.getElementById(`${prefix}-resume-wrap-${i}`);
  if (wrap) {
    wrap.classList.toggle('hidden', !resolved);
    if (!resolved) document.getElementById(`${prefix}-resume-${i}`).value = '';
  }
  const count = prefix === 'aefv' ? _aefvAeDetails.length : _aecvAeDetails.length;
  _aeUpdateSchedulingOnResolve(prefix, count);
}

function _collectAeDiscussions(prefix, aeDetails) {
  // Returns {discussions, error}
  const discussions = [];
  for (let i = 0; i < aeDetails.length; i++) {
    const ae       = aeDetails[i];
    const notes    = document.getElementById(`${prefix}-disc-${i}`)?.value.trim() || null;
    const resolved = document.getElementById(`${prefix}-resolved-${i}`).checked;
    let can_resume_from = null;
    if (resolved && ae.training_blocked && !_trainingPermanentlyEnded()) {
      can_resume_from = document.getElementById(`${prefix}-resume-${i}`)?.value || '';
      if (!can_resume_from)
        return { discussions: null, error: 'Can resume from date is required for resolved training-blocked events.' };
    }
    discussions.push({ adverse_event_id: ae.id, notes, resolved, can_resume_from: can_resume_from || null });
  }
  return { discussions, error: null };
}

function _loadAeDetails(aeIds) {
  return aeIds.map(id => {
    const ae = (_completeEventsCache || []).find(e => e.id === id);
    return { id, alias: ae?.alias || '', date: ae?.completion_date || '', training_blocked: ae?.training_blocked || false };
  });
}

function _setupAeSchedulingToggles(prefix) {
  // Exclude the modal's own current event id from the "existing stub" search,
  // otherwise the AE follow-up VISIT modal would flag the visit stub it is
  // itself filling in. For the call modal (aef) this resolves to a stub id of
  // a different type, so the exclusion is a no-op there.
  const currentEventId =
    prefix === 'aef'  ? _aefEventId  :
    prefix === 'aefv' ? _aefvEventId :
    prefix === 'aecv' ? _aecvEventId : null;

  const kinds = [
    { kind: 'visit',    pid: 'adverse_event_followup_visit',  endpoint: 'ae-followup-visit',  label: 'Follow-up visit' },
    { kind: 'clinical', pid: 'adverse_event_clinical_visit',  endpoint: 'ae-clinical-visit',  label: 'Clinical visit'  },
  ];

  kinds.forEach(({ kind, pid, endpoint, label }) => {
    const wrap      = document.getElementById(`${prefix}-schedule-${kind}-wrap`);
    const cb        = document.getElementById(`${prefix}-schedule-${kind}`);
    const cbLabel   = cb?.closest('label');                  // the entire toggle-row label
    const dateWrap  = document.getElementById(`${prefix}-${kind}-date-wrap`);
    const dateInput = document.getElementById(`${prefix}-${kind}-date`);
    if (!wrap || !cb || !cbLabel) return;

    // Always reset the toggle/date to a clean state.
    cb.checked = false;
    if (dateWrap)  dateWrap.classList.add('hidden');
    if (dateInput) dateInput.value = '';
    cb.onchange = () => {
      if (dateWrap) dateWrap.classList.toggle('hidden', !cb.checked);
      if (!cb.checked && dateInput) dateInput.value = '';
    };

    // Look for a currently-pending stub of this kind, excluding the modal's own event.
    const existing = (eventsCache || []).find(e =>
      e.protocol_event_id === pid && e.id !== currentEventId
    );

    // Ensure a notice element exists in the wrap; lazily created once and reused.
    let notice = document.getElementById(`${prefix}-${kind}-existing-notice`);
    if (!notice) {
      notice = document.createElement('div');
      notice.id = `${prefix}-${kind}-existing-notice`;
      notice.className = 'hidden';
      wrap.insertBefore(notice, wrap.firstChild);
    }

    if (existing) {
      const dateStr = existing.scheduled_date?.[0] ? _fmtDateTime(existing.scheduled_date[0]) : '—';
      const aeAliases = (existing.adverse_event_ids || [])
        .map(aeId => (_completeEventsCache || []).find(e => e.id === aeId)?.alias)
        .filter(Boolean).join(', ');
      notice.innerHTML = `
        <div class="flex items-start gap-2">
          <i class="fas fa-info-circle text-blue-500 mt-0.5"></i>
          <div class="flex-1">
            <p class="text-sm font-medium text-slate-700">${label} already scheduled for ${dateStr}</p>
            ${aeAliases ? `<p class="text-xs text-slate-500 mt-0.5">Covering: ${_esc(aeAliases)}</p>` : ''}
          </div>
          <button type="button"
                  onclick="_cancelExistingAeStub('${prefix}', '${existing.id}', '${endpoint}')"
                  class="text-xs px-2.5 py-1 bg-red-50 text-red-700 border border-red-200 rounded-lg hover:bg-red-100 whitespace-nowrap">
            Cancel scheduled
          </button>
        </div>`;
      notice.classList.remove('hidden');
      cbLabel.classList.add('hidden');
      if (dateWrap) dateWrap.classList.add('hidden');
    } else {
      notice.classList.add('hidden');
      cbLabel.classList.remove('hidden');
    }
  });
}

// Cancel an existing AE visit/clinical stub from inside a parent modal. Refreshes
// the events cache, then re-runs the toggle setup so the modal switches back to
// "Schedule a …" mode without closing.
async function _cancelExistingAeStub(prefix, stubId, endpoint) {
  const reason = prompt('Reason for cancellation (required):');
  if (reason === null) return;
  if (!reason.trim()) { alert('Cancellation reason is required.'); return; }

  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/cancel-event/${endpoint}`,
    { event_id: stubId, cancellation_reason: reason.trim() }
  );
  if (!ok) { alert(data.error || 'Failed to cancel.'); return; }

  await loadPatientEvents();
  _setupAeSchedulingToggles(prefix);
}

function _collectAeScheduling(prefix) {
  // Returns {scheduledFollowupVisit, scheduledClinicalVisit, error}
  const visitCb      = document.getElementById(`${prefix}-schedule-visit`);
  const clinicalCb   = document.getElementById(`${prefix}-schedule-clinical`);
  const visitDate    = document.getElementById(`${prefix}-visit-date`)?.value    || '';
  const clinicalDate = document.getElementById(`${prefix}-clinical-date`)?.value || '';
  if (visitCb?.checked    && !visitDate)    return { error: 'Follow-up visit date is required.'  };
  if (clinicalCb?.checked && !clinicalDate) return { error: 'Clinical visit date is required.'   };
  return {
    scheduledFollowupVisit:  visitCb?.checked    ? visitDate    : null,
    scheduledClinicalVisit:  clinicalCb?.checked ? clinicalDate : null,
    error: null,
  };
}

function _buildAeContextBanner(prefix, aeDetails) {
  const el = document.getElementById(`${prefix}-context-banner`);
  el.innerHTML = aeDetails.length
    ? aeDetails.map(ae => {
        const label    = ae.alias || 'Adverse Event';
        const dateStr  = ae.date ? ` — ${_fmtDateTime(ae.date)}` : '';
        const pauseTag = ae.training_blocked
          ? ' <span class="text-red-600 font-medium">(training blocked)</span>' : '';
        return `<div>${label}${dateStr}${pauseTag}</div>`;
      }).join('')
    : '<div class="text-slate-400">No adverse events found.</div>';
}

// `lockedFrom`, when provided, opens the modal in **ad-hoc/locked mode**: the
// entry is being filed during a parent visit (e.g., D29) rather than against a
// pre-existing scheduled-visit stub. Visit Start/End collapse to a single
// "Visit Date/Time" field locked to the parent's `completion_date`. The
// server treats this as a brand-new entry (no stub to consume) and stamps
// `triggered_by` on it.
//
// Shape: `{date, label, triggeredBy: {type, id}, aeIds: [...]}`.
//   - date:        parent's completion_date (YYYY-MM-DDTHH:MM)
//   - label:       human-readable parent name for the lock hint
//   - triggeredBy: {type: 'training_completion_d29' | …, id: <parent_event_id>}
//   - aeIds:       AE ids the visit covers (sourced by the caller — typically
//                  from the daily `adverse_event_followup` call stub)
let _aefvLockedFrom = null;

function openAeFollowupVisitModal(ev, lockedFrom = null) {
  _aefvLockedFrom = lockedFrom;
  // In ad-hoc mode there is no stub — synthesize a minimal `ev` shape so the
  // rest of the opener stays a single code path.
  if (!ev && lockedFrom) ev = { id: null, adverse_event_ids: lockedFrom.aeIds || [] };

  _aefvEventId   = ev.id;
  _aefvAeDetails = _loadAeDetails(ev.adverse_event_ids || []);
  const aefvAliases = _aefvAeDetails.map(ae => ae.alias).filter(Boolean);
  const aefvTitle = document.getElementById('aefv-title');
  if (aefvTitle) aefvTitle.textContent = aefvAliases.length
    ? `Adverse Event Follow-up Visit — ${aefvAliases.join(', ')}`
    : 'Adverse Event Follow-up Visit';
  _buildAeContextBanner('aefv', _aefvAeDetails);
  document.getElementById('aefv-ae-rows').innerHTML = _buildAeVisitRows('aefv', _aefvAeDetails);

  const startInput = document.getElementById('aefv-start');
  const endInput   = document.getElementById('aefv-end');
  const startLabel = document.getElementById('aefv-start-label');
  const endWrap    = document.getElementById('aefv-end-wrap');
  const timesGrid  = document.getElementById('aefv-times-grid');
  const lockHint   = document.getElementById('aefv-start-lock-hint');
  const lockText   = document.getElementById('aefv-start-lock-hint-text');

  // Reset both inputs and any prior locked-state styling so a standalone re-open
  // after a locked open behaves cleanly.
  startInput.value      = '';
  startInput.readOnly   = false;
  startInput.classList.remove('bg-slate-100', 'cursor-not-allowed');
  endInput.value        = '';
  endInput.readOnly     = false;
  endInput.classList.remove('bg-slate-100', 'cursor-not-allowed');
  endWrap.classList.remove('hidden');
  timesGrid.classList.remove('grid-cols-1');
  timesGrid.classList.add('grid-cols-2');
  startLabel.innerHTML  = 'Visit Start <span class="text-red-500">*</span>';
  if (lockHint) lockHint.classList.add('hidden');

  document.getElementById('aefv-notes').value = '';
  _setupAeSchedulingToggles('aefv');
  _resetAttachment('aefv');
  setError('aefv-error', '');
  _attachSessionEndGuard('aefv-start', 'aefv-end', 'aefv-error');
  _attachDateGuard('aefv-start', 'aefv-error');

  if (lockedFrom && lockedFrom.date) {
    // Collapse the two-time-field layout into a single locked Visit Date/Time.
    startInput.value     = lockedFrom.date;
    startInput.readOnly  = true;
    startInput.classList.add('bg-slate-100', 'cursor-not-allowed');
    endInput.value       = lockedFrom.date;  // server gets visit_end = visit_start
    endWrap.classList.add('hidden');
    timesGrid.classList.remove('grid-cols-2');
    timesGrid.classList.add('grid-cols-1');
    startLabel.innerHTML = 'Visit Date/Time <span class="text-red-500">*</span>';
    if (lockHint && lockText) {
      lockText.textContent = `Synced from ${lockedFrom.label || 'parent visit'} — date cannot be changed.`;
      lockHint.classList.remove('hidden');
    }
  }

  showModal('ae-followup-visit-modal');
}

async function saveAeFollowupVisit() {
  const start   = document.getElementById('aefv-start').value;
  const end     = document.getElementById('aefv-end').value;
  const notes   = document.getElementById('aefv-notes').value.trim();
  const saveBtn = document.getElementById('aefv-save');
  const adHoc   = !!_aefvLockedFrom;

  if (!start) { setError('aefv-error', 'Visit start is required.'); return; }
  if (!end)   { setError('aefv-error', 'Visit end is required.'); return; }
  if (start.split('T')[0] !== end.split('T')[0]) { setError('aefv-error', 'Start and end must be on the same date.'); return; }
  // Ad-hoc/locked mode uses a single Visit Date/Time field (visit_end is set
  // equal to visit_start by the opener). Skip the strict "end > start" check
  // there. The normal path keeps the original constraint.
  if (!adHoc && end <= start) { setError('aefv-error', 'Visit end must be after visit start.'); return; }

  const { discussions, error } = _collectAeDiscussions('aefv', _aefvAeDetails);
  if (error) { setError('aefv-error', error); return; }

  const { scheduledFollowupVisit, scheduledClinicalVisit, error: schedError } = _collectAeScheduling('aefv');
  if (schedError) { setError('aefv-error', schedError); return; }
  if (!_validateAttachment('aefv', 'aefv-error')) return;

  saveBtn.disabled = true;
  const payload = {
    event_id: _aefvEventId,
    visit_start: start, visit_end: end,
    notes: notes || null,
    ae_discussions: discussions,
    scheduled_followup_visit: scheduledFollowupVisit,
    scheduled_clinical_visit: scheduledClinicalVisit,
  };
  if (adHoc) {
    // Tell the server this is a brand-new entry filed during a parent visit.
    // The server sources adverse_event_ids from the daily AE follow-up call
    // stub (which the user explicitly said stays untouched).
    payload.triggered_by = _aefvLockedFrom.triggeredBy;
  }
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/ae-followup-visit`, payload
  );
  if (!ok) { setError('aefv-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }

  const { file, caption } = _readAttachment('aefv');
  if (file) {
    const uploaded = await _uploadAttachment(data.id, file, caption, 'aefv-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  hideModal('ae-followup-visit-modal');
  saveBtn.disabled = false;
  await loadPatientEvents();
}

// ── AE Clinical Visit modal ───────────────────────────────────────────────────

let _aecvEventId   = null;
let _aecvAeDetails = [];

function openAeClinicalVisitModal(ev) {
  _aecvEventId   = ev.id;
  _aecvAeDetails = _loadAeDetails(ev.adverse_event_ids || []);
  const aecvAliases = _aecvAeDetails.map(ae => ae.alias).filter(Boolean);
  const aecvTitle = document.getElementById('aecv-title');
  if (aecvTitle) aecvTitle.textContent = aecvAliases.length
    ? `Adverse Event Clinical Visit — ${aecvAliases.join(', ')}`
    : 'Adverse Event Clinical Visit';
  _buildAeContextBanner('aecv', _aecvAeDetails);
  document.getElementById('aecv-ae-rows').innerHTML = _buildAeVisitRows('aecv', _aecvAeDetails);
  document.getElementById('aecv-start').value = '';
  document.getElementById('aecv-end').value   = '';
  document.getElementById('aecv-notes').value = '';
  _setupAeSchedulingToggles('aecv');
  _resetAttachment('aecv');
  setError('aecv-error', '');
  _attachSessionEndGuard('aecv-start', 'aecv-end', 'aecv-error');
  _attachDateGuard('aecv-start', 'aecv-error');
  showModal('ae-clinical-visit-modal');
}

async function saveAeClinicalVisit() {
  const start   = document.getElementById('aecv-start').value;
  const end     = document.getElementById('aecv-end').value;
  const notes   = document.getElementById('aecv-notes').value.trim();
  const saveBtn = document.getElementById('aecv-save');

  if (!start) { setError('aecv-error', 'Visit start is required.'); return; }
  if (!end)   { setError('aecv-error', 'Visit end is required.'); return; }
  if (start.split('T')[0] !== end.split('T')[0]) { setError('aecv-error', 'Start and end must be on the same date.'); return; }
  if (end <= start) { setError('aecv-error', 'Visit end must be after visit start.'); return; }

  const { discussions, error } = _collectAeDiscussions('aecv', _aecvAeDetails);
  if (error) { setError('aecv-error', error); return; }

  const { scheduledFollowupVisit, scheduledClinicalVisit, error: schedError } = _collectAeScheduling('aecv');
  if (schedError) { setError('aecv-error', schedError); return; }
  if (!_validateAttachment('aecv', 'aecv-error')) return;

  saveBtn.disabled = true;
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/ae-clinical-visit`,
    { event_id: _aecvEventId, visit_start: start, visit_end: end, notes: notes || null, ae_discussions: discussions,
      scheduled_followup_visit: scheduledFollowupVisit, scheduled_clinical_visit: scheduledClinicalVisit }
  );
  if (!ok) { setError('aecv-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }

  const { file, caption } = _readAttachment('aecv');
  if (file) {
    const uploaded = await _uploadAttachment(data.id, file, caption, 'aecv-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  hideModal('ae-clinical-visit-modal');
  saveBtn.disabled = false;
  await loadPatientEvents();
}

// ── AE visit cancellation ─────────────────────────────────────────────────────

async function _cancelAeVisit(prefix) {
  const reason = prompt('Reason for cancellation (required):');
  if (reason === null) return; // user dismissed
  if (!reason.trim()) { alert('Cancellation reason is required.'); return; }

  const eventId  = prefix === 'aefv' ? _aefvEventId : _aecvEventId;
  const modalId  = prefix === 'aefv' ? 'ae-followup-visit-modal' : 'ae-clinical-visit-modal';
  const endpoint = prefix === 'aefv' ? 'ae-followup-visit' : 'ae-clinical-visit';

  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/cancel-event/${endpoint}`,
    { event_id: eventId, cancellation_reason: reason.trim() }
  );
  if (!ok) { alert(data.error || 'Failed to cancel.'); return; }

  hideModal(modalId);
  await loadPatientEvents();
}

// ── Resolve Robot Issue Visit modal ───────────────────────────────────────────

let _rrivEventId      = null;
let _rrivDevices      = []; // [{device_type, old_device_id, available}] — taken-back devices
let _rrivOtherDevices = []; // [{device_type, old_device_id, available}] — still-assigned devices
let _rrivIsBp         = false;

async function openResolveRobotIssueVisitModal(ev) {
  _rrivEventId      = ev.id;
  _rrivDevices      = [];
  _rrivOtherDevices = [];
  _rrivIsBp         = !!patientData?.brokenProtocolDate;

  // Find the triggering robot_issue_visit in the completed events cache
  const triggeredBy = ev.triggered_by;
  let rivEvent = null;
  if (triggeredBy) {
    rivEvent = (_completeEventsCache || []).find(e => e.id === triggeredBy.id);
  }

  let bannerText = 'Robot issue visit';
  if (rivEvent?.completion_date) bannerText += ` on ${_fmtDateTime(rivEvent.completion_date)}`;
  bannerText += ' — device(s) taken back without replacement';
  document.getElementById('rriv-context-banner').textContent = bannerText;
  document.getElementById('rriv-date').value = '';
  document.getElementById('rriv-resume-date').value = '';
  document.getElementById('rriv-notes').value = '';
  document.getElementById('rriv-device-rows').innerHTML =
    '<p class="text-sm text-slate-400 italic">Loading device info…</p>';
  const otherSec = document.getElementById('rriv-other-device-section');
  if (otherSec) { otherSec.innerHTML = ''; otherSec.classList.add('hidden'); }
  _resetAttachment('rriv');
  setError('rriv-error', '');

  document.getElementById('rriv-date').onchange = function () {
    const val = this.value;
    if (val && val > _nowForInput()) {
      setError('rriv-error', 'Visit date cannot be in the future.');
      this.value = '';
    } else {
      setError('rriv-error', '');
    }
  };

  document.getElementById('rriv-resume-date').onchange = function () {
    const val = this.value;
    const today = _nowForInput().slice(0, 10);
    if (val && val > today) {
      setError('rriv-error', 'Can resume from date cannot be in the future.');
      this.value = '';
    } else {
      setError('rriv-error', '');
    }
  };

  // Fetch and set date validation bounds BEFORE showing modal
  const dates = await _fetchIssueValidationDates(ev.triggered_by?.id);
  _setIssueModalDateBounds(null, dates.issue_occur_date, null, 'rriv-date');

  // Toggle BP mode UI
  document.getElementById('rriv-bp-banner').classList.toggle('hidden', !_rrivIsBp);
  document.getElementById('rriv-normal-section').classList.toggle('hidden', _rrivIsBp);
  document.getElementById('rriv-bp-device-rows').innerHTML = '';

  showModal('resolve-robot-issue-visit-modal');

  try {
    const res = await fetch(`/api/patients/${PATIENT_HOMER_ID}/available-devices`);
    const devData = await res.json();

    // Devices taken back (swapped + null new_device_id)
    const takenBack = (rivEvent?.device_outcomes || []).filter(
      o => o.outcome === 'swapped' && o.new_device_id == null
    );
    const takenBackTypes = new Set(takenBack.map(o => o.device));

    for (const outcome of takenBack) {
      _rrivDevices.push({
        device_type:   outcome.device,
        old_device_id: outcome.old_device_id,
        available:     devData[outcome.device] || [],
      });
    }

    // Other devices still assigned to the patient (not taken back)
    for (const deviceType of ['pluto', 'mars']) {
      const cur = deviceType === 'pluto' ? devData.current_pluto : devData.current_mars;
      if (cur && !takenBackTypes.has(deviceType)) {
        _rrivOtherDevices.push({
          device_type:   deviceType,
          old_device_id: cur,
          available:     devData[deviceType] || [],
        });
      }
    }

    if (_rrivIsBp) {
      _buildRrivBpDeviceRows();
    } else {
      if (_rrivDevices.length === 0) {
        document.getElementById('rriv-device-rows').innerHTML =
          '<p class="text-sm text-slate-400 italic">No taken-back devices found.</p>';
      } else {
        _buildRrivDeviceRows();
      }
      _buildRrivOtherDeviceSection();
    }
  } catch (e) {
    document.getElementById('rriv-device-rows').innerHTML =
      '<p class="text-sm text-red-500">Failed to load device info.</p>';
  }
}

function _rrivBpFaultChange(deviceType) {
  const checked = document.getElementById(`rriv-bp-${deviceType}-fault`)?.checked;
  document.getElementById(`rriv-bp-${deviceType}-desc-wrap`)?.classList.toggle('hidden', !checked);
}

function _buildRrivBpDeviceRows() {
  const container = document.getElementById('rriv-bp-device-rows');
  container.innerHTML = '';
  for (const dev of _rrivDevices) {
    const label = dev.device_type.charAt(0).toUpperCase() + dev.device_type.slice(1);
    const oldLabel = dev.old_device_id
      ? `<span class="font-mono">${dev.old_device_id}</span>`
      : '<span class="text-slate-400 italic">None</span>';
    const rowDiv = document.createElement('div');
    rowDiv.className = 'border border-slate-200 rounded-xl p-4 space-y-3';
    rowDiv.innerHTML = `
      <div class="flex items-center gap-2">
        <span class="text-sm font-semibold text-slate-800">${label}</span>
        <span class="px-2 py-0.5 rounded-full bg-red-100 text-red-700 text-xs font-medium">Taken back</span>
        <span class="text-xs text-slate-500">Device: ${oldLabel}</span>
      </div>
      <div class="flex items-center gap-2">
        <input type="checkbox" id="rriv-bp-${dev.device_type}-fault" class="w-4 h-4 accent-amber-600"
          onchange="_rrivBpFaultChange('${dev.device_type}')">
        <label for="rriv-bp-${dev.device_type}-fault" class="text-sm text-slate-700 cursor-pointer">This device has a fault</label>
      </div>
      <div id="rriv-bp-${dev.device_type}-desc-wrap" class="hidden pl-2 border-l-2 border-amber-200">
        <label class="block text-xs font-medium text-slate-600 mb-1">Fault description <span class="text-red-400">*</span></label>
        <textarea id="rriv-bp-${dev.device_type}-desc" rows="2"
          class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-200 resize-none"
          placeholder="Describe the fault…"></textarea>
      </div>
    `;
    container.appendChild(rowDiv);
  }
}

function _buildRrivDeviceRows() {
  const container = document.getElementById('rriv-device-rows');
  container.innerHTML = '';

  for (const dev of _rrivDevices) {
    const label = dev.device_type.charAt(0).toUpperCase() + dev.device_type.slice(1);

    const oldLabel = dev.old_device_id
      ? `<span class="font-mono">${dev.old_device_id}</span>`
      : '<span class="text-slate-400 italic">None</span>';

    let optionsHtml = '<option value="">No device available</option>';
    for (const d of dev.available) {
      optionsHtml += `<option value="${d.id}">${d.id}</option>`;
    }

    const rowDiv = document.createElement('div');
    rowDiv.className = 'border border-slate-200 rounded-xl p-4 space-y-3';
    rowDiv.innerHTML = `
      <div class="flex items-center gap-2">
        <span class="text-sm font-semibold text-slate-800">${label}</span>
        <span class="px-2 py-0.5 rounded-full bg-red-100 text-red-700 text-xs font-medium">Taken back</span>
      </div>
      <div class="grid grid-cols-2 gap-3 items-end">
        <div>
          <p class="text-xs font-medium text-slate-500 mb-1">Device taken back</p>
          <p class="text-sm text-slate-700">${oldLabel}</p>
        </div>
        <div>
          <label class="block text-xs font-medium text-slate-500 mb-1">Replacement <span class="text-red-400">*</span></label>
          <select id="rriv-${dev.device_type}-select"
            class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 bg-white">
            ${optionsHtml}
          </select>
        </div>
      </div>
      <div id="rriv-${dev.device_type}-notes-row" class="hidden">
        <label class="block text-xs font-medium text-slate-500 mb-1">Reason no device available <span class="text-red-400">*</span></label>
        <textarea id="rriv-${dev.device_type}-notes" rows="2"
          class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none"
          placeholder="Explain why no replacement device is available…"></textarea>
      </div>
    `;
    container.appendChild(rowDiv);

    // Show/hide notes when "No device available" selected
    const sel = document.getElementById(`rriv-${dev.device_type}-select`);
    const notesRow = document.getElementById(`rriv-${dev.device_type}-notes-row`);
    // Show notes immediately if initial selection is "no device"
    notesRow.classList.toggle('hidden', sel.value !== '');
    sel.onchange = function () {
      const isNull = this.value === '';
      notesRow.classList.toggle('hidden', !isNull);
      if (!isNull) document.getElementById(`rriv-${dev.device_type}-notes`).value = '';
    };
  }
}

function _buildRrivOtherDeviceSection() {
  const section = document.getElementById('rriv-other-device-section');
  section.innerHTML = '';
  if (_rrivOtherDevices.length === 0) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');
  const deviceNames = _rrivOtherDevices
    .map(d => d.device_type.charAt(0).toUpperCase() + d.device_type.slice(1))
    .join(' / ');
  const wrapper = document.createElement('div');
  wrapper.className = 'border border-slate-200 rounded-xl p-4 space-y-3';
  wrapper.innerHTML = `
    <label class="flex items-center gap-2 cursor-pointer">
      <input type="checkbox" id="rriv-other-device-toggle" class="w-4 h-4 accent-orange-600">
      <span class="text-sm font-medium text-slate-700">Also attended to ${deviceNames}</span>
    </label>
    <div id="rriv-other-device-rows" class="hidden space-y-3 mt-2"></div>
  `;
  section.appendChild(wrapper);
  const toggle = document.getElementById('rriv-other-device-toggle');
  const rows   = document.getElementById('rriv-other-device-rows');
  toggle.onchange = function () {
    rows.classList.toggle('hidden', !this.checked);
    if (this.checked) _buildRrivOtherRows();
    else rows.innerHTML = '';
  };
}

function _buildRrivOtherRows() {
  const rows = document.getElementById('rriv-other-device-rows');
  rows.innerHTML = '';
  for (const dev of _rrivOtherDevices) {
    const label    = dev.device_type.charAt(0).toUpperCase() + dev.device_type.slice(1);
    const oldLabel = dev.old_device_id
      ? `<span class="font-mono">${dev.old_device_id}</span>`
      : '<span class="text-slate-400 italic">None assigned</span>';
    let swapOptions = '<option value="">No device available</option>';
    for (const d of dev.available) swapOptions += `<option value="${d.id}">${d.id}</option>`;

    const rowDiv = document.createElement('div');
    rowDiv.className = 'border border-slate-100 rounded-xl p-3 space-y-3 bg-slate-50';
    rowDiv.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="text-sm font-semibold text-slate-800">${label}</span>
        <span class="text-xs text-slate-500">Current: ${oldLabel}</span>
      </div>
      <div>
        <p class="text-xs font-medium text-slate-600 mb-2">Outcome <span class="text-red-400">*</span></p>
        <div class="space-y-2">
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="radio" name="rriv-other-${dev.device_type}-outcome" value="repaired_on_site" class="w-4 h-4 accent-orange-600"
              onchange="_rrivOtherOutcomeChange('${dev.device_type}')">
            <span class="text-sm text-slate-700">Repaired on site</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="radio" name="rriv-other-${dev.device_type}-outcome" value="swapped" class="w-4 h-4 accent-orange-600"
              onchange="_rrivOtherOutcomeChange('${dev.device_type}')">
            <span class="text-sm text-slate-700">Swapped</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input type="radio" name="rriv-other-${dev.device_type}-outcome" value="neither" class="w-4 h-4 accent-orange-600"
              onchange="_rrivOtherOutcomeChange('${dev.device_type}')">
            <span class="text-sm text-slate-700">Neither (no action taken)</span>
          </label>
        </div>
      </div>
      <div id="rriv-other-${dev.device_type}-repaired-fields" class="hidden space-y-2 pl-2 border-l-2 border-orange-200">
        <label class="block text-xs font-medium text-slate-600 mb-1">Notes <span class="text-red-400">*</span></label>
        <textarea id="rriv-other-${dev.device_type}-repair-notes" rows="2"
          class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 resize-none"
          placeholder="Describe what was done to fix the device…"></textarea>
      </div>
      <div id="rriv-other-${dev.device_type}-swapped-fields" class="hidden space-y-2 pl-2 border-l-2 border-orange-200">
        <div>
          <p class="text-xs font-medium text-slate-600 mb-2">Swap type <span class="text-red-400">*</span></p>
          <div class="space-y-1">
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="rriv-other-${dev.device_type}-swap-type" value="fault_driven" class="w-4 h-4 accent-orange-600">
              <span class="text-sm text-slate-700">Fault-driven (device suspected/confirmed faulty)</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="rriv-other-${dev.device_type}-swap-type" value="preventive" class="w-4 h-4 accent-orange-600">
              <span class="text-sm text-slate-700">Preventive (precautionary replacement)</span>
            </label>
          </div>
        </div>
        <div>
          <label class="block text-xs font-medium text-slate-600 mb-1">New device <span class="text-red-400">*</span></label>
          <select id="rriv-other-${dev.device_type}-new-device"
            class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 bg-white">
            ${swapOptions}
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-slate-600 mb-1">Notes <span class="text-slate-400 font-normal">(optional)</span></label>
          <textarea id="rriv-other-${dev.device_type}-swap-notes" rows="2"
            class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-orange-200 resize-none"
            placeholder="Reason for swap…"></textarea>
        </div>
      </div>
      <div id="rriv-other-${dev.device_type}-neither-fields" class="hidden pl-2 border-l-2 border-slate-200">
        <label class="block text-xs font-medium text-slate-600 mb-1">Notes <span class="text-red-400">*</span></label>
        <textarea id="rriv-other-${dev.device_type}-neither-notes" rows="2"
          class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 resize-none"
          placeholder="Explain why no action was taken…"></textarea>
      </div>
    `;
    rows.appendChild(rowDiv);
  }
}

function _rrivOtherOutcomeChange(deviceType) {
  const outcome = document.querySelector(`input[name="rriv-other-${deviceType}-outcome"]:checked`)?.value;
  document.getElementById(`rriv-other-${deviceType}-repaired-fields`).classList.toggle('hidden', outcome !== 'repaired_on_site');
  document.getElementById(`rriv-other-${deviceType}-swapped-fields`).classList.toggle('hidden', outcome !== 'swapped');
  document.getElementById(`rriv-other-${deviceType}-neither-fields`).classList.toggle('hidden', outcome !== 'neither');
}

async function saveResolveRobotIssueVisit() {
  const date       = document.getElementById('rriv-date').value;
  const resumeDate = document.getElementById('rriv-resume-date').value;
  const notes      = document.getElementById('rriv-notes').value.trim();
  const saveBtn    = document.getElementById('rriv-save');

  if (!date) { setError('rriv-error', 'Visit date is required.'); return; }

  // Validate visit date
  const today = new Date().toISOString().split('T')[0];
  if (date.split('T')[0] > today) {
    setError('rriv-error', 'Visit date cannot be in the future.');
    return;
  }
  const minDate = document.getElementById('rriv-date').min;
  if (minDate && date.split('T')[0] < minDate.split('T')[0]) {
    setError('rriv-error', `Visit date must be on or after issue occurred date (${minDate.split('T')[0]}).`);
    return;
  }

  // ── Broken-protocol mode ──────────────────────────────────────────────────
  if (_rrivIsBp) {
    const deviceFaults = [];
    for (const dev of _rrivDevices) {
      const hasFault = document.getElementById(`rriv-bp-${dev.device_type}-fault`)?.checked;
      if (hasFault) {
        const desc = document.getElementById(`rriv-bp-${dev.device_type}-desc`)?.value.trim() || '';
        if (!desc) { setError('rriv-error', `Please describe the fault for ${dev.device_type}.`); return; }
        deviceFaults.push({ device: dev.device_type, device_id: dev.old_device_id, notes: desc });
      }
    }
    if (!_validateAttachment('rriv', 'rriv-error')) return;
    saveBtn.disabled = true;
    const { ok, data } = await apiPost(
      `/api/patients/${PATIENT_HOMER_ID}/complete-event/resolve-robot-issue-visit`,
      { event_id: _rrivEventId, completion_date: date, notes, device_faults: deviceFaults, broken_protocol_mode: true }
    );
    if (!ok) { setError('rriv-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }
    const { file, caption } = _readAttachment('rriv');
    if (file) {
      const uploaded = await _uploadAttachment(_rrivEventId, file, caption, 'rriv-error');
      if (!uploaded) { saveBtn.disabled = false; return; }
    }
    hideModal('resolve-robot-issue-visit-modal');
    saveBtn.disabled = false;
    await loadPatientEvents();
    return;
  }
  // ─────────────────────────────────────────────────────────────────────────

  if (!resumeDate) { setError('rriv-error', 'Can resume from date is required.'); return; }
  if (resumeDate > today) {
    setError('rriv-error', 'Can resume from date cannot be in the future.');
    return;
  }

  const deviceReplacements = [];
  for (const dev of _rrivDevices) {
    const sel = document.getElementById(`rriv-${dev.device_type}-select`);
    if (!sel) continue;
    const newDeviceId = sel.value || null;
    const capLabel = dev.device_type.charAt(0).toUpperCase() + dev.device_type.slice(1);

    let devNotes = null;
    if (newDeviceId === null) {
      devNotes = (document.getElementById(`rriv-${dev.device_type}-notes`)?.value || '').trim();
      if (!devNotes) {
        setError('rriv-error', `Reason for no replacement ${capLabel} is required.`);
        return;
      }
    }

    deviceReplacements.push({
      device:        dev.device_type,
      old_device_id: dev.old_device_id,
      new_device_id: newDeviceId,
      notes:         devNotes,
    });
  }

  const otherDeviceOutcomes = [];
  const otherToggle = document.getElementById('rriv-other-device-toggle');
  if (otherToggle?.checked) {
    for (const dev of _rrivOtherDevices) {
      const outcome  = document.querySelector(`input[name="rriv-other-${dev.device_type}-outcome"]:checked`)?.value || '';
      const capLabel = dev.device_type.charAt(0).toUpperCase() + dev.device_type.slice(1);
      if (!outcome) { setError('rriv-error', `Outcome is required for ${capLabel}.`); return; }

      let otherPayload = { device: dev.device_type, outcome, old_device_id: dev.old_device_id };
      if (outcome === 'repaired_on_site') {
        const repairNotes = document.getElementById(`rriv-other-${dev.device_type}-repair-notes`).value.trim();
        if (!repairNotes) { setError('rriv-error', `${capLabel} repair notes are required.`); return; }
        otherPayload.notes = repairNotes;
      } else if (outcome === 'swapped') {
        const swapType  = document.querySelector(`input[name="rriv-other-${dev.device_type}-swap-type"]:checked`)?.value;
        const newDevice = document.getElementById(`rriv-other-${dev.device_type}-new-device`).value || null;
        const swapNotes = document.getElementById(`rriv-other-${dev.device_type}-swap-notes`).value.trim();
        if (!swapType) { setError('rriv-error', `${capLabel} swap type is required.`); return; }
        otherPayload.new_device_id = newDevice;
        otherPayload.swap_type     = swapType;
        otherPayload.notes         = swapNotes || null;
      } else {
        const neitherNotes = document.getElementById(`rriv-other-${dev.device_type}-neither-notes`).value.trim();
        if (!neitherNotes) { setError('rriv-error', `${capLabel} notes are required.`); return; }
        otherPayload.notes = neitherNotes;
      }
      otherDeviceOutcomes.push(otherPayload);
    }
  }

  if (!_validateAttachment('rriv', 'rriv-error')) return;

  saveBtn.disabled = true;
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/resolve-robot-issue-visit`,
    { event_id: _rrivEventId, completion_date: date, can_resume_from: resumeDate, notes,
      device_replacements: deviceReplacements, other_device_outcomes: otherDeviceOutcomes }
  );
  if (!ok) { setError('rriv-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }

  const { file, caption } = _readAttachment('rriv');
  if (file) {
    const uploaded = await _uploadAttachment(_rrivEventId, file, caption, 'rriv-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  hideModal('resolve-robot-issue-visit-modal');
  saveBtn.disabled = false;
  await loadPatientEvents();
}


function completedTimeline(events) {
  const _ASSESS_PIDS_CT = new Set(['a1_assessment', 'a2_assessment']);
  const _fmtCT = (raw) => {
    const d = raw ? new Date(raw) : null;
    return d ? d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: '2-digit' }) : '—';
  };
  const items = events.map((ev, i) => {
    const raw = ev.completion_date || ev.filed_at || '';
    const dateStr  = _fmtCT(raw);
    const filedStr = _showFiledLine(ev) ? _fmtDateTime(ev.filed_at) : '';
    const isLast  = i === events.length - 1;
    const isDisc  = ev.protocol_event_id === 'discontinuation';
    const isAssEv = _ASSESS_PIDS_CT.has(ev.protocol_event_id);
    const isMissedCT  = isAssEv && !!ev.missed;
    const isDelayedCT = isAssEv && !isMissedCT && !!ev.completion_date && Array.isArray(ev.scheduled_date)
                        && ev.completion_date.slice(0, 10) > ev.scheduled_date[1].slice(0, 10);
    const circleCls = isDisc     ? 'bg-red-500 ring-red-300'
                    : isMissedCT ? 'bg-slate-400 ring-slate-300'
                    :               'bg-green-500 ring-green-300';
    const nameCls   = isDisc ? 'text-sm font-bold text-red-700 leading-tight' : 'text-sm font-medium text-slate-800 leading-tight';
    const badge     = isDisc
      ? `<span class="inline-flex items-center gap-1 text-xs font-semibold bg-red-100 text-red-700 border border-red-200 rounded-full px-2 py-0.5 mt-1"><i class="fas fa-ban text-[10px]"></i>Discontinued</span>`
      : isMissedCT
      ? `<span class="inline-flex items-center gap-1 text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-300 rounded-full px-2 py-0.5 mt-1"><i class="fas fa-times-circle text-[10px]"></i>Missed</span>`
      : isDelayedCT
      ? `<span class="inline-flex items-center gap-1 text-xs font-semibold bg-amber-100 text-amber-700 border border-amber-200 rounded-full px-2 py-0.5 mt-1"><i class="fas fa-clock text-[10px]"></i>Delayed</span>`
      : '';
    return `
      <div class="relative pl-7 ${isLast ? '' : 'pb-4'}">
        <div class="absolute left-[3px] top-1.5 w-3 h-3 rounded-full ${circleCls} border-2 border-white ring-1 z-10"></div>
        ${isLast ? '' : '<div class="absolute left-[8px] top-4 bottom-0 w-0.5 bg-green-100"></div>'}
        <p class="${nameCls}">${ev.event_name}</p>
        <p class="text-xs text-slate-400 mt-0.5">${dateStr}</p>
        ${filedStr ? `<p class="text-xs text-slate-400 leading-tight">Filed: ${filedStr}</p>` : ''}
        ${badge}
      </div>`;
  }).join('');
  return `<div class="relative">${items}</div>`;
}

// Map protocol_event_id → opener function name
const EVENT_OPENERS = {
  informed_consent:          (ev) => openInformedConsentModal(ev),
  exp_device_install:        (ev) => openDeviceSetupModal(ev.id),
  activation:                (ev) => openActivationModal(ev.id),
  discontinuation_reminder:  (ev) => openDiscontinueModal(ev),
  discontinuation:           (ev) => openDiscontinueModal(ev),
  adl_prescription_d01:      (ev) => openAdlPrescriptionModal(ev),
  adl_prescription_d15:      (ev) => openAdlPrescriptionModal(ev),
  vcg_prescription_d01:      (ev) => openVcgPrescriptionModal(ev),
  vcg_prescription_d15:      (ev) => openVcgPrescriptionModal(ev),
  prescription_printout_d01: (ev) => openPrescriptionPrintoutModal(ev),
  prescription_printout_d15: (ev) => openPrescriptionPrintoutModal(ev),
  home_visit_d02:            (ev) => openHomeVisitModal(ev),
  home_visit_d03:            (ev) => openHomeVisitModal(ev),
  home_visit_d15:            (ev) => openHomeVisitModal(ev),
  followup_call_d07:         (ev) => openFollowupCallModal(ev),
  followup_call_d21:         (ev) => openFollowupCallModal(ev),
  training_completion_d29:   (ev) => openD29Modal(ev),
  agwatch_timing_d01:        (ev) => openAgwatchTimingModal(ev),
  agwatch_timing_d02:        (ev) => openAgwatchTimingModal(ev),
  agwatch_timing_d03:        (ev) => openAgwatchTimingModal(ev),
  agwatch_timing_d15:        (ev) => openAgwatchTimingModal(ev),
  watch_record:              (ev) => openWatchRecordModal(ev),
  watch_data_upload:         (ev) => openWatchDataUploadModal(ev),
  adverse_event:                (ev) => openAdverseEventModal(ev),
  robot_issue_call:             (ev) => openRobotIssueCallModal(ev),
  robot_issue_visit:            (ev) => openRobotIssueVisitModal(ev),
  adverse_event_followup:       (ev) => openAdverseEventFollowupModal(ev),
  adverse_event_followup_visit: (ev) => openAeFollowupVisitModal(ev),
  adverse_event_clinical_visit: (ev) => openAeClinicalVisitModal(ev),
  resolve_robot_issue_visit:    (ev) => openResolveRobotIssueVisitModal(ev),
  other_device_issue_call:      (ev) => openOtherDeviceIssueModal(ev),
  other_device_issue_visit:     (ev) => openOtherDeviceIssueVisitModal(ev),
  a1_assessment:                (ev) => openA1AssessmentModal(ev),
  a2_assessment:                (ev) => openA2AssessmentModal(ev),
  schedule_a1_call:             (ev) => openScheduleA1CallModal(ev),
  schedule_a2_call:             (ev) => openScheduleA2CallModal(ev),
  device_return:                (ev) => openDeviceReturnModal(ev),
};

function patientEventRow(ev) {
  const sched = ev.scheduled_date;
  const onHold = !!ev.on_hold;
  const isActiveWindow = !!ev.active_window;
  const isOverdue   = !isActiveWindow && ev.days <= 0;
  const isUpcoming  = !isActiveWindow && (ev.days > 0 || onHold);
  const abs = Math.abs(ev.days);
  const _fmtD = s => new Date(s.replace(' ', 'T')).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });

  const _ASSESSMENT_PIDS = new Set(['a1_assessment', 'a2_assessment']);
  const isAssessment = _ASSESSMENT_PIDS.has(ev.protocol_event_id);

  let dateStr, whenLabel, subLabel;
  if (isAssessment) {
    // Bottom-left: appointment date if scheduled, otherwise "Unscheduled"
    dateStr = ev.appointment_date ? _fmtD(ev.appointment_date) : 'Unscheduled';
    // Window range shown below the days counter
    const wsStr = ev.window_start ? _fmtD(ev.window_start) : null;
    const weStr = ev.window_end   ? _fmtD(ev.window_end)   : null;
    subLabel = wsStr && weStr ? `(${wsStr} – ${weStr})` : null;
    // days label uses ev.days which is window_end − today
    if (onHold) {
      whenLabel = 'On hold';
    } else if (isActiveWindow) {
      whenLabel = ev.days === 0 ? 'Due today' : `${ev.days}d left`;
    } else if (isOverdue) {
      whenLabel = ev.days === 0 ? 'Today' : `${abs}d overdue`;
    } else {
      whenLabel = ev.days === 1 ? '1d left' : `${ev.days}d left`;
    }
  } else {
    subLabel = null;
    // For display date: upcoming/on-hold → start, active-window or past-due → end
    const refDate = Array.isArray(sched) ? (isActiveWindow || isOverdue ? sched[1] : sched[0]) : sched;
    const d = new Date((refDate || '').replace(' ', 'T'));
    dateStr = d && !isNaN(d) ? d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) : '—';
    if (onHold) {
      whenLabel = 'On hold';
    } else if (isActiveWindow) {
      whenLabel = ev.days === 0 ? 'Due today' : `Due now · ${ev.days}d left`;
    } else if (isOverdue) {
      whenLabel = ev.days === 0 ? 'Today' : `${abs}d overdue`;
    } else {
      whenLabel = `Available from ${dateStr}`;
    }
  }
  const urgency   = isOverdue       ? 'border-red-200 bg-red-50'
                  : isActiveWindow  ? 'border-amber-200 bg-amber-50'
                  : ev.days <= 2    ? 'border-orange-200 bg-orange-50'
                  : 'border-slate-100 bg-slate-50';
  const textColor = isOverdue       ? 'text-red-600'
                  : isActiveWindow  ? 'text-amber-700'
                  : ev.days <= 2    ? 'text-orange-600'
                  : 'text-slate-500';

  const blocked   = !onHold && ev.blocked_by && ev.blocked_by.length > 0;
  const hasOpener = !!EVENT_OPENERS[ev.protocol_event_id];
  // Must be kept in sync with _DISCONTINUED_VISIBLE in routes/user_management.py
  // and routes/dashboard.py. If the server shows a row but this set omits its
  // type, the row appears but cannot be opened (silent clickability gate).
  const _DISCONTINUED_VISIBLE = new Set([
    'adverse_event', 'adverse_event_followup',
    'adverse_event_followup_visit', 'adverse_event_clinical_visit',
    'a1_assessment', 'a2_assessment',
    'schedule_a1_call', 'schedule_a2_call',
    'device_return',
    'watch_data_upload',
  ]);
  const discontinuedBlocks = _patientDiscontinued && !_DISCONTINUED_VISIBLE.has(ev.protocol_event_id);
  // Assessment events (A1/A2) clickable only when overdue or in active window (not upcoming).
  // Other upcoming events are non-clickable.
  const clickable = hasOpener && !blocked && (isAssessment ? (isOverdue || isActiveWindow) : !isUpcoming) && !onHold && !discontinuedBlocks;
  const tag       = clickable ? 'a' : 'div';
  const href      = clickable ? `href="?action=${ev.id}"` : '';
  const extra     = clickable ? 'cursor-pointer hover:shadow-md transition-shadow' : '';
  const subtitle  = `<div class="text-xs text-slate-500 mt-0.5">${dateStr}</div>`;
  const eventName = blocked
    ? `<div class="font-medium text-slate-800 text-sm truncate flex items-center gap-1"><i class="fas fa-lock text-slate-400 text-[10px]"></i>${ev.event_name}</div>`
    : `<div class="font-medium text-slate-800 text-sm truncate">${ev.event_name}</div>`;
  const rightLabel = blocked
    ? `<span class="text-xs font-semibold text-amber-600 bg-amber-50 border border-amber-200 rounded-full px-2 py-0.5 whitespace-nowrap flex-shrink-0">Needs: ${ev.blocked_by[0]}</span>`
    : onHold
    ? `<span class="text-xs font-semibold text-slate-600 bg-white border border-slate-300 rounded-full px-2 py-0.5 whitespace-nowrap flex-shrink-0">On hold</span>`
    : isAssessment && subLabel
    ? `<div class="flex flex-col items-end gap-0.5 flex-shrink-0">
         <span class="text-xs font-semibold ${textColor} whitespace-nowrap">${whenLabel}</span>
         <span class="text-xs text-slate-400 whitespace-nowrap">${subLabel}</span>
       </div>`
    : `<span class="text-xs font-semibold ${textColor} whitespace-nowrap flex-shrink-0">${whenLabel}</span>`;

  return `
    <${tag} ${href} class="flex items-center justify-between px-3 py-2.5 rounded-xl border ${urgency} ${extra} gap-3">
      <div class="min-w-0">
        ${eventName}
        ${subtitle}
      </div>
      <div class="flex items-center gap-1 flex-shrink-0">
        ${rightLabel}
      </div>
    </${tag}>`;
}


function emptyEventState(icon, colorClass, msg) {
  return `<div class="flex flex-col items-center justify-center py-6 ${colorClass}"><i class="fas fa-${icon} text-xl mb-1.5"></i><p class="text-xs">${msg}</p></div>`;
}

// ── Device setup modal ────────────────────────────────────────────────────────

// ── Informed Consent ───────────────────────────────────────────────────────

let _icEventId = null;

function openInformedConsentModal(ev) {
  _icEventId = ev ? ev.id : null;
  document.getElementById('ic-consent-date').value = '';
  document.getElementById('ic-notes').value = '';
  document.getElementById('ic-attachment-file').value = '';
  setError('ic-error', '');
  _attachDateGuard('ic-consent-date', 'ic-error');
  showModal('informed-consent-modal');
}

async function saveInformedConsent() {
  const consentDate = document.getElementById('ic-consent-date').value;
  const notes = document.getElementById('ic-notes').value;
  const fileInput = document.getElementById('ic-attachment-file');
  const file = fileInput?.files?.[0] || null;

  if (!consentDate) {
    setError('ic-error', 'Please select a consent date.');
    return;
  }

  if (_hasDateValidationErrors(['ic-error'])) return;

  // Validate that PDF is provided
  if (!file) {
    setError('ic-error', 'Please upload the signed consent form PDF.');
    return;
  }

  // Validate file is PDF
  if (!file.name.toLowerCase().endsWith('.pdf')) {
    setError('ic-error', 'Please upload a PDF file.');
    return;
  }

  // Complete event first (without attachment path)
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/informed-consent`,
    { event_id: _icEventId, consentDate: consentDate, notes: notes }
  );

  if (!ok) {
    setError('ic-error', data.error || 'Failed to save informed consent.');
    return;
  }

  // Upload attachment after event is created (no caption required for informed consent)
  if (file) {
    const eventId = data.id || _icEventId;
    const uploaded = await _uploadAttachmentNoCaption(eventId, file, 'ic-error');
    if (!uploaded) return;
  }

  hideModal('informed-consent-modal');
  loadPatientEvents();
}

let _deviceSetupEventId = null;

async function openDeviceSetupModal(ev) {
  _deviceSetupEventId = typeof ev === 'object' ? ev.id : ev;
  document.getElementById('device-setup-homer-id').textContent = PATIENT_HOMER_ID;
  document.getElementById('device-setup-date').value = '';
  document.getElementById('device-setup-demo').checked = false;
  document.getElementById('device-setup-notes').value = '';
  setError('device-setup-error', '');
  document.getElementById('device-setup-sim-warning')?.classList.add('hidden');
  window._setupSimExpiry = {};
  _resetAttachment('device-setup');
  _attachDateGuard('device-setup-date', 'device-setup-error');

  const plutoSel = document.getElementById('device-setup-pluto');
  const marsSel  = document.getElementById('device-setup-mars');
  const modemSel = document.getElementById('device-setup-modem');
  const laptopSel = document.getElementById('device-setup-laptop');
  const simSel = document.getElementById('device-setup-sim');

  plutoSel.innerHTML = '<option value="">Loading…</option>';
  marsSel.innerHTML  = '<option value="">Loading…</option>';
  modemSel.innerHTML = '<option value="">Loading…</option>';
  laptopSel.innerHTML = '<option value="">Loading…</option>';
  simSel.innerHTML = '<option value="">Loading…</option>';
  showModal('device-setup-modal');

  try {
    const res = await fetch(`/api/patients/${PATIENT_HOMER_ID}/available-devices`);
    if (!res.ok) throw new Error('Failed to fetch devices');
    const data = await res.json();
    const { pluto, mars, modem, laptop, sims } = data;

    plutoSel.innerHTML = '<option value="">Select Pluto device…</option>' +
      pluto.map(d => `<option value="${d.id}">${d.id} (${d.serial})</option>`).join('');
    marsSel.innerHTML  = '<option value="">Select Mars device…</option>' +
      mars.map(d => `<option value="${d.id}">${d.id} (${d.serial})</option>`).join('');
    modemSel.innerHTML = '<option value="">Select Modem device…</option>' +
      modem.map(d => `<option value="${d.id}">${d.id} (${d.serial})</option>`).join('');
    laptopSel.innerHTML = '<option value="">Select Laptop device…</option>' +
      laptop.map(d => `<option value="${d.id}">${d.id} (${d.serial})</option>`).join('');
    const today = new Date(); today.setHours(0,0,0,0);
    const simList = (sims || []).filter(s => {
      if (s.removal_date) return false; // exclude retired
      if (!s.expiryDate) return true;
      const exp = new Date(s.expiryDate); exp.setHours(0,0,0,0);
      return exp >= today; // exclude expired
    });
    window._setupSimExpiry = {};
    simList.forEach(s => {
      if (s.expiryDate) {
        const exp = new Date(s.expiryDate); exp.setHours(0,0,0,0);
        const days = Math.round((exp - today) / 86400000);
        window._setupSimExpiry[s.id] = days;
      }
    });
    simSel.innerHTML = '<option value="">Select SIM card…</option>' +
      simList.map(s => {
        const days = window._setupSimExpiry[s.id];
        const warn = days !== undefined && days <= 5 ? ` ⚠ Expires in ${days}d` : '';
        return `<option value="${s.id}">${s.phoneNumber || s.id}${warn}</option>`;
      }).join('');

    if (!pluto.length) plutoSel.innerHTML = '<option value="">No devices available</option>';
    if (!mars.length)  marsSel.innerHTML  = '<option value="">No devices available</option>';
    if (!modem.length) modemSel.innerHTML = '<option value="">No devices available</option>';
    if (!laptop.length) laptopSel.innerHTML = '<option value="">No devices available</option>';
    if (!simList.length) simSel.innerHTML = '<option value="">No SIM cards available</option>';
  } catch (e) {
    console.error('Error loading devices:', e);
    setError('device-setup-error', 'Failed to load available devices.');
  }
}

function onSetupSimChange() {
  const sel = document.getElementById('device-setup-sim');
  const warn = document.getElementById('device-setup-sim-warning');
  const warnText = document.getElementById('device-setup-sim-warning-text');
  const days = window._setupSimExpiry?.[sel.value];
  if (days !== undefined && days <= 5) {
    warnText.textContent = days === 0
      ? 'This SIM expires today. Recharge before assigning.'
      : `This SIM expires in ${days} day${days === 1 ? '' : 's'}. Consider recharging first.`;
    warn.classList.remove('hidden');
  } else {
    warn.classList.add('hidden');
  }
}

async function submitDeviceSetup() {
  // Check for date validation errors before proceeding
  if (_hasDateValidationErrors(['device-setup-error'])) {
    setError('device-setup-error', 'Please fix the date validation errors before submitting.');
    return;
  }

  const eventDate = document.getElementById('device-setup-date').value;
  const plutoId   = document.getElementById('device-setup-pluto').value;
  const marsId    = document.getElementById('device-setup-mars').value;
  const modemId   = document.getElementById('device-setup-modem').value;
  const laptopId  = document.getElementById('device-setup-laptop').value;
  const simId     = document.getElementById('device-setup-sim').value;
  const demoDone  = document.getElementById('device-setup-demo').checked;
  const notes     = document.getElementById('device-setup-notes').value;

  if (!eventDate) { setError('device-setup-error', 'Please select an event date.'); return; }
  if (!plutoId)   { setError('device-setup-error', 'Please select a Pluto device.'); return; }
  if (!marsId)    { setError('device-setup-error', 'Please select a Mars device.'); return; }
  if (!modemId)   { setError('device-setup-error', 'Please select a Modem device.'); return; }
  if (!laptopId)  { setError('device-setup-error', 'Please select a Laptop device.'); return; }
  if (!simId)     { setError('device-setup-error', 'Please select a SIM card.'); return; }
  if (!_validateAttachment('device-setup', 'device-setup-error')) return;

  setLoading('device-setup-submit', true);
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/exp_device_install`,
    { event_id: _deviceSetupEventId, eventDate, plutoId, marsId, modemId, laptopId, simId, demoDone, notes }
  );
  if (!ok) { setLoading('device-setup-submit', false); setError('device-setup-error', data.error || 'Failed to complete device setup.'); return; }

  const { file, caption } = _readAttachment('device-setup');
  if (file) {
    const uploaded = await _uploadAttachment(_deviceSetupEventId, file, caption, 'device-setup-error');
    if (!uploaded) { setLoading('device-setup-submit', false); return; }
  }
  setLoading('device-setup-submit', false);
  hideModal('device-setup-modal');
  loadPatientEvents();
}

// ── Activation modal ──────────────────────────────────────────────────────────

let _activationEventId = null;

let _activationTrainingCompleted = null; // null = not chosen, true = yes, false = no
let _actNoPrimaryReason          = null;

function _actNoToggleSubform(type) {
  const noteId = {
    adverse: 'act-no-adverse-note', robot: 'act-no-robot-note',
    'other-device': 'act-no-other-device-note',
  }[type];
  const checked = document.getElementById(`act-no-trigger-${type}`).checked;
  if (noteId) document.getElementById(noteId).classList.toggle('hidden', !checked);
}

function _setActNoPrimaryReason(reason) {
  _actNoPrimaryReason = reason;
  const pills = {
    adverse_event:           'act-no-reason-ae',
    robot_issue_call:        'act-no-reason-robot',
    other_device_issue_call: 'act-no-reason-odi',
    other:                   'act-no-reason-other',
  };
  const active   = ['bg-blue-600', 'text-white', 'border-blue-600'];
  const inactive = ['border-slate-200', 'text-slate-600'];
  Object.entries(pills).forEach(([r, id]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    const on = r === reason;
    active.forEach(c => btn.classList.toggle(c, on));
    inactive.forEach(c => btn.classList.toggle(c, !on));
  });

  const isExp = patientData?.group === 'experimental';
  const wrapVisibility = {
    'act-no-trigger-ae-wrap':           true,
    'act-no-trigger-robot-wrap':        isExp,
    'act-no-trigger-other-device-wrap': isExp,
  };
  const reasonToWrap = {
    adverse_event:           'act-no-trigger-ae-wrap',
    robot_issue_call:        'act-no-trigger-robot-wrap',
    other_device_issue_call: 'act-no-trigger-other-device-wrap',
  };
  Object.entries(wrapVisibility).forEach(([wrapId, groupVisible]) => {
    const wrap = document.getElementById(wrapId);
    if (!wrap) return;
    const isPrimary = reasonToWrap[reason] === wrapId;
    wrap.classList.toggle('hidden', !groupVisible || isPrimary);
    if (isPrimary || !groupVisible) {
      const cbId = wrapId === 'act-no-trigger-ae-wrap'    ? 'act-no-trigger-adverse'
                 : wrapId === 'act-no-trigger-robot-wrap' ? 'act-no-trigger-robot'
                 :                                          'act-no-trigger-other-device';
      const cb = document.getElementById(cbId);
      if (cb && cb.checked) { cb.checked = false; _actNoToggleSubform(cbId.replace('act-no-trigger-', '')); }
    }
  });

  const notesLabel = document.getElementById('act-no-notes-star');
  if (notesLabel) notesLabel.textContent = reason === 'other' ? '* — explain why training was not completed' : '';
  setError('activation-error', '');
}

function _setActivationTrainingToggle(val) {
  _activationTrainingCompleted = val;
  const yesBtn = document.getElementById('act-train-yes-btn');
  const noBtn  = document.getElementById('act-train-no-btn');
  const activeClass   = ['bg-blue-600', 'text-white', 'border-blue-600'];
  const inactiveClass = ['border-slate-200', 'text-slate-600'];
  if (val === true) {
    yesBtn.classList.add(...activeClass);    yesBtn.classList.remove(...inactiveClass);
    noBtn.classList.remove(...activeClass);  noBtn.classList.add(...inactiveClass);
  } else {
    noBtn.classList.add(...activeClass);     noBtn.classList.remove(...inactiveClass);
    yesBtn.classList.remove(...activeClass); yesBtn.classList.add(...inactiveClass);
  }
  document.getElementById('act-training-yes-section').classList.toggle('hidden', val !== true);
  document.getElementById('act-training-no-section').classList.toggle('hidden', val !== false);
  document.getElementById('activation-submit').textContent = val === false ? 'Log Attempt' : 'Activate Patient';
}

async function openActivationModal(evId) {
  _activationEventId        = typeof evId === 'object' ? evId.id : evId;
  _activationTrainingCompleted = null;
  document.getElementById('activation-homer-id').textContent = PATIENT_HOMER_ID;

  // Reset toggle to unselected state
  const activeClass   = ['bg-blue-600', 'text-white', 'border-blue-600'];
  const inactiveClass = ['border-slate-200', 'text-slate-600'];
  ['act-train-yes-btn', 'act-train-no-btn'].forEach(id => {
    const btn = document.getElementById(id);
    btn.classList.remove(...activeClass);
    btn.classList.add(...inactiveClass);
  });
  document.getElementById('act-training-yes-section').classList.add('hidden');
  document.getElementById('act-training-no-section').classList.add('hidden');
  document.getElementById('activation-submit').textContent = 'Activate Patient';

  // Reset YES section fields
  document.getElementById('activation-session-start').value = '';
  document.getElementById('activation-session-end').value   = '';
  document.getElementById('activation-notes').value         = '';
  _resetAttachment('activation');
  _attachDateGuard('activation-session-start', 'activation-error');
  _attachSessionEndGuard('activation-session-start', 'activation-session-end', 'activation-error');

  const isControl      = patientData?.group === 'control';
  const isExperimental = patientData?.group === 'experimental';
  const vcgRow = document.getElementById('activation-vcg-group-row');
  const vcgSel = document.getElementById('activation-vcg-group');
  if (vcgRow) vcgRow.classList.toggle('hidden', !isControl);
  if (vcgSel) vcgSel.value = '';

  // Outcome group visibility (group, watch-assigned, training-ended cutoff)
  // is centralised in _outcomeReset → _applyOutcomeVisibility.
  _outcomeReset('act');

  // Reset NO section fields
  _actNoPrimaryReason = null;
  document.getElementById('act-no-visit-date').value = '';
  document.getElementById('act-no-notes').value      = '';
  _attachDateGuard('act-no-visit-date', 'activation-error');

  // Reset primary reason pills
  const pillActive   = ['bg-blue-600', 'text-white', 'border-blue-600'];
  const pillInactive = ['border-slate-200', 'text-slate-600'];
  ['act-no-reason-ae', 'act-no-reason-robot', 'act-no-reason-odi', 'act-no-reason-other'].forEach(id => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.classList.remove(...pillActive);
    btn.classList.add(...pillInactive);
  });
  document.getElementById('act-no-reason-robot').classList.toggle('hidden', !isExperimental);
  document.getElementById('act-no-reason-odi').classList.toggle('hidden', !isExperimental);
  const actNoNotesLabel = document.getElementById('act-no-notes-star');
  if (actNoNotesLabel) actNoNotesLabel.textContent = '';

  // Reset secondary triggers
  ['adverse', 'robot', 'other-device'].forEach(type => {
    const cb = document.getElementById(`act-no-trigger-${type}`);
    if (cb) { cb.checked = false; _actNoToggleSubform(type); }
  });
  document.getElementById('act-no-trigger-ae-wrap').classList.remove('hidden');
  document.getElementById('act-no-trigger-robot-wrap').classList.toggle('hidden', !isExperimental);
  document.getElementById('act-no-trigger-other-device-wrap').classList.toggle('hidden', !isExperimental);

  setError('activation-error', '');
  showModal('activation-modal');
}

async function submitActivation() {
  if (_activationTrainingCompleted === null) {
    setError('activation-error', 'Please indicate whether training was completed.');
    return;
  }
  if (_activationTrainingCompleted === false) {
    await _submitActivationAttempt();
    return;
  }

  // ── YES path: full activation ────────────────────────────────────────
  if (_hasDateValidationErrors(['activation-error'])) {
    setError('activation-error', 'Please fix the date validation errors before submitting.');
    return;
  }

  const sessionStart = document.getElementById('activation-session-start').value;
  const sessionEnd   = document.getElementById('activation-session-end').value;
  const notes        = document.getElementById('activation-notes').value;

  if (!sessionStart || !sessionEnd) {
    setError('activation-error', 'Session start and end are required.');
    return;
  }
  if (sessionStart.split('T')[0] !== sessionEnd.split('T')[0]) {
    setError('activation-error', 'Session start and end must be on the same date.');
    return;
  }
  if (sessionStart >= sessionEnd) {
    setError('activation-error', 'Session end must be after session start.');
    return;
  }

  const body = { activationDate: sessionStart, sessionStart, sessionEnd, notes };
  if (patientData?.group === 'control') {
    const vcgGroup = document.getElementById('activation-vcg-group').value;
    if (!vcgGroup) { setError('activation-error', 'Please select a VCG group.'); return; }
    body.vcgGroup = vcgGroup;
  }
  if (!_validateAttachment('activation', 'activation-error')) return;

  const outcomeErrAct = _outcomeError('act');
  if (outcomeErrAct) { setError('activation-error', outcomeErrAct); return; }
  const { no_issue: noIssueAct, triggered } = _outcomeRead('act');
  body.triggered = triggered;
  body.no_issue  = noIssueAct;

  setLoading('activation-submit', true);
  const { ok, data } = await apiPost(`/api/patients/${PATIENT_HOMER_ID}/activate`, body);
  if (!ok) { setLoading('activation-submit', false); setError('activation-error', data.error || 'Failed to activate patient.'); return; }

  const { file, caption } = _readAttachment('activation');
  if (file) {
    const uploaded = await _uploadAttachment(_activationEventId, file, caption, 'activation-error');
    if (!uploaded) { setLoading('activation-submit', false); return; }
  }
  setLoading('activation-submit', false);
  hideModal('activation-modal');
  await loadPatient();
  loadPatientEvents();
}

async function _submitActivationAttempt() {
  if (_hasDateValidationErrors(['activation-error'])) {
    setError('activation-error', 'Please fix the date validation errors before submitting.');
    return;
  }

  const visitDate = document.getElementById('act-no-visit-date').value;
  const notes     = document.getElementById('act-no-notes').value.trim();

  if (!_actNoPrimaryReason) { setError('activation-error', 'Please select a reason why training was not completed.'); return; }
  if (!visitDate) { setError('activation-error', 'Visit date is required.'); return; }
  if (_actNoPrimaryReason === 'other' && !notes) { setError('activation-error', 'Notes are required when reason is "Other".'); return; }

  // Primary reason (non-"other") auto-creates its stub with training_stopped: true
  const triggered = [];
  if (_actNoPrimaryReason !== 'other') {
    triggered.push({ type: _actNoPrimaryReason, training_stopped: true });
  }
  // Secondary triggers (matching trigger wrap is already hidden, so no duplicates)
  if (_actNoPrimaryReason !== 'adverse_event' &&
      document.getElementById('act-no-trigger-adverse').checked)
    triggered.push({ type: 'adverse_event' });
  if (_actNoPrimaryReason !== 'robot_issue_call' &&
      !document.getElementById('act-no-trigger-robot-wrap').classList.contains('hidden') &&
      document.getElementById('act-no-trigger-robot').checked)
    triggered.push({ type: 'robot_issue_call' });
  if (_actNoPrimaryReason !== 'other_device_issue_call' &&
      !document.getElementById('act-no-trigger-other-device-wrap').classList.contains('hidden') &&
      document.getElementById('act-no-trigger-other-device').checked)
    triggered.push({ type: 'other_device_issue_call' });

  setLoading('activation-submit', true);
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/log-activation-attempt`,
    { visitDate, notes, primaryReason: _actNoPrimaryReason, triggered }
  );
  if (!ok) { setLoading('activation-submit', false); setError('activation-error', data.error || 'Failed to log activation attempt.'); return; }

  setLoading('activation-submit', false);
  hideModal('activation-modal');
  loadPatientEvents();
}

// ── Prescription modals (shared helpers) ──────────────────────────────────────

let _adlPrescEventId = null;
let _adlExercises    = [];
let _adlSelected     = [];  // { exercise, blocks, reps, notes, state: 'editing'|'compact' }

let _vcgPrescEventId = null;
let _vcgExercises    = [];
let _vcgSelected     = [];  // { exercise, blocks, reps, notes, state: 'editing'|'compact' }

const VCG_GROUP_LABELS = { vcg2: 'VCG 2', vcg3: 'VCG 3', vcg4_5: 'VCG 4–5' };

function _prescState(prefix) {
  return prefix === 'adl'
    ? { evId: _adlPrescEventId, exercises: _adlExercises, selected: _adlSelected }
    : { evId: _vcgPrescEventId, exercises: _vcgExercises, selected: _vcgSelected };
}

// Flush current editing-state DOM inputs into the data array.
// Must be called before any operation that changes array indices.
function _saveDOMValues(prefix) {
  const selected = prefix === 'adl' ? _adlSelected : _vcgSelected;
  selected.forEach((s, i) => {
    if (s.state !== 'editing') return;
    const blocksEl = document.getElementById(`${prefix}-blocks-${i}`);
    const repsEl   = document.getElementById(`${prefix}-reps-${i}`);
    const notesEl  = document.getElementById(`${prefix}-notes-${i}`);
    if (blocksEl) s.blocks = +blocksEl.value || s.blocks;
    if (repsEl)   s.reps   = +repsEl.value   || s.reps;
    if (notesEl)  s.notes  = notesEl.value;
  });
}

function _updatePrescSubmitBtn(prefix) {
  const selected = prefix === 'adl' ? _adlSelected : _vcgSelected;
  const btn = document.getElementById(`${prefix}-prescription-submit`);
  if (!btn) return;
  const anyEditing = selected.some(s => s.state === 'editing');
  btn.disabled = anyEditing;
  btn.classList.toggle('opacity-50', anyEditing);
  btn.classList.toggle('cursor-not-allowed', anyEditing);
}

function renderPrescSelected(prefix) {
  const { selected } = _prescState(prefix);
  const container = document.getElementById(`${prefix}-prescription-selected`);
  if (!container) return;
  if (!selected.length) {
    container.innerHTML = '<p class="text-xs text-slate-400 text-center py-3">No exercises selected. Use the search bar above to add exercises.</p>';
    _updatePrescSubmitBtn(prefix);
    return;
  }
  container.innerHTML = selected.map((s, i) => {
    if (s.state === 'editing') {
      return `
        <div class="border-2 border-blue-300 rounded-xl p-3 bg-blue-50">
          <div class="flex items-start justify-between mb-2">
            <span class="text-sm font-semibold text-slate-800">
              <span class="text-blue-500 mr-1">${i + 1}.</span>${s.exercise.name}
            </span>
            <button type="button" onclick="removeExercise('${prefix}',${i})"
                    class="text-slate-400 hover:text-red-500 ml-2 flex-shrink-0">
              <i class="fas fa-times text-sm"></i>
            </button>
          </div>
          <div class="grid grid-cols-2 gap-2 mb-2">
            <div>
              <label class="block text-xs text-slate-500 mb-1">Sets</label>
              <input id="${prefix}-blocks-${i}" type="number" min="1" value="${s.blocks}"
                     class="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
            <div>
              <label class="block text-xs text-slate-500 mb-1">Repetitions</label>
              <input id="${prefix}-reps-${i}" type="number" min="1" value="${s.reps}"
                     class="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
            </div>
          </div>
          <textarea id="${prefix}-notes-${i}" rows="2" placeholder="Notes for this exercise…"
                    class="w-full px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none">${s.notes}</textarea>
          <div class="mt-2 flex justify-end">
            <button type="button" onclick="saveExercise('${prefix}',${i})"
                    class="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-lg">
              Save
            </button>
          </div>
        </div>`;
    } else {
      return `
        <div class="border border-slate-200 rounded-xl px-4 py-3 bg-white flex items-center gap-3">
          <span class="flex-1 text-sm font-medium text-slate-800">
            <span class="text-slate-400 mr-1">${i + 1}.</span>${s.exercise.name}
          </span>
          <span class="text-xs text-slate-500 whitespace-nowrap">${s.blocks} blocks × ${s.reps} reps</span>
          <button type="button" onclick="editExercise('${prefix}',${i})"
                  class="text-slate-400 hover:text-blue-600 text-xs font-medium px-2 py-1 rounded border border-slate-200 hover:border-blue-300">
            Edit
          </button>
          <button type="button" onclick="removeExercise('${prefix}',${i})"
                  class="text-slate-400 hover:text-red-500 flex-shrink-0">
            <i class="fas fa-times text-sm"></i>
          </button>
        </div>`;
    }
  }).join('');
  _updatePrescSubmitBtn(prefix);
}

function saveExercise(prefix, i) {
  const selected = prefix === 'adl' ? _adlSelected : _vcgSelected;
  const s = selected[i];
  if (!s) return;
  const blocksEl = document.getElementById(`${prefix}-blocks-${i}`);
  const repsEl   = document.getElementById(`${prefix}-reps-${i}`);
  const notesEl  = document.getElementById(`${prefix}-notes-${i}`);
  const blocks = blocksEl ? (+blocksEl.value || 0) : s.blocks;
  const reps   = repsEl   ? (+repsEl.value   || 0) : s.reps;
  if (!blocks || !reps) {
    if (blocksEl && !+blocksEl.value) blocksEl.classList.add('border-red-400');
    if (repsEl   && !+repsEl.value)   repsEl.classList.add('border-red-400');
    return;
  }
  s.blocks = blocks;
  s.reps   = reps;
  s.notes  = notesEl ? notesEl.value : s.notes;
  s.state  = 'compact';
  renderPrescSelected(prefix);
}

function editExercise(prefix, i) {
  const selected = prefix === 'adl' ? _adlSelected : _vcgSelected;
  if (!selected[i]) return;
  selected[i].state = 'editing';
  renderPrescSelected(prefix);
}

function removeExercise(prefix, i) {
  const selected  = prefix === 'adl' ? _adlSelected : _vcgSelected;
  const container = document.getElementById(`${prefix}-prescription-selected`);
  _saveDOMValues(prefix);
  if (container) container.innerHTML = '';
  selected.splice(i, 1);
  renderPrescSelected(prefix);
}

function addExercise(prefix, exerciseId) {
  const exercises = prefix === 'adl' ? _adlExercises : _vcgExercises;
  const selected  = prefix === 'adl' ? _adlSelected  : _vcgSelected;
  const ex = exercises.find(e => e.id === exerciseId);
  if (!ex) return;
  selected.push({ exercise: ex, blocks: 1, reps: 10, notes: '', state: 'editing' });
  renderPrescSelected(prefix);
  const searchEl  = document.getElementById(`${prefix}-prescription-search`);
  const resultsEl = document.getElementById(`${prefix}-prescription-results`);
  if (searchEl)  searchEl.value = '';
  if (resultsEl) resultsEl.classList.add('hidden');
}

function _filterExercises(prefix, query) {
  const exercises = prefix === 'adl' ? _adlExercises : _vcgExercises;
  const selected  = prefix === 'adl' ? _adlSelected  : _vcgSelected;
  const selIds    = new Set(selected.map(s => s.exercise.id));
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return exercises.filter(e => e.name.toLowerCase().includes(q) && !selIds.has(e.id)).slice(0, 6);
}

function _setupPrescSearchListener(prefix) {
  const searchEl  = document.getElementById(`${prefix}-prescription-search`);
  const resultsEl = document.getElementById(`${prefix}-prescription-results`);
  if (!searchEl) return;
  searchEl.addEventListener('input', () => {
    const matches = _filterExercises(prefix, searchEl.value);
    if (!matches.length) { resultsEl.classList.add('hidden'); return; }
    resultsEl.innerHTML = matches.map(e =>
      `<div class="px-3 py-2 hover:bg-slate-100 cursor-pointer text-sm text-slate-700 border-b border-slate-100 last:border-b-0"
            onmousedown="addExercise('${prefix}','${e.id}')">${e.name}</div>`
    ).join('');
    resultsEl.classList.remove('hidden');
  });
  searchEl.addEventListener('blur', () => {
    setTimeout(() => resultsEl.classList.add('hidden'), 150);
  });
}

// ── ADL Prescription modal ────────────────��────────────────────────────────────

async function openAdlPrescriptionModal(ev) {
  _adlPrescEventId = typeof ev === 'object' ? ev.id : ev;
  const protocolId = typeof ev === 'object' ? ev.protocol_event_id : null;

  let dateValue, dateLabel;
  if (protocolId === 'adl_prescription_d15') {
    const hvEvent = (_completeEventsCache || []).find(e => e.protocol_event_id === 'home_visit_d15');
    dateValue = hvEvent?.completion_date || '';
    dateLabel = 'Home Visit Date';
  } else {
    dateValue = patientData?.activationDate || '';
    dateLabel = 'Activation Date';
  }

  document.getElementById('adl-prescription-homer-id').textContent = PATIENT_HOMER_ID;
  document.getElementById('adl-prescription-date-label').textContent = dateLabel;
  document.getElementById('adl-prescription-date').value = dateValue;
  document.getElementById('adl-prescription-notes').value = '';
  setError('adl-prescription-error', '');
  _adlSelected = [];
  renderPrescSelected('adl');
  showModal('adl-prescription-modal');

  try {
    if (!_adlExercises.length) {
      const res = await fetch('/api/exercises?type=adl');
      if (!res.ok) throw new Error();
      _adlExercises = await res.json();
    }
    // Pre-populate for d15 revision
    if (protocolId === 'adl_prescription_d15') {
      const res = await fetch(`/api/patients/${PATIENT_HOMER_ID}/prescription/adl_prescription_d01`);
      if (res.ok) {
        const prev = await res.json();
        _adlSelected = (prev.prescribed_exercises || []).map(pe => {
          const ex = _adlExercises.find(e => e.id === pe.exercise_id);
          return ex ? { exercise: ex, blocks: pe.blocks || 1, reps: pe.repetitions || 1, notes: pe.notes || '', state: 'compact' } : null;
        }).filter(Boolean);
        document.getElementById('adl-prescription-notes').value = '';
        renderPrescSelected('adl');
      }
    }
  } catch (_) {
    setError('adl-prescription-error', 'Failed to load exercises.');
  }
}

async function submitAdlPrescription() {
  if (!_adlSelected.length) { setError('adl-prescription-error', 'Please select at least one exercise.'); return; }
  if (_adlSelected.some(s => s.state === 'editing')) { setError('adl-prescription-error', 'Please save all exercise cards before submitting.'); return; }
  for (const s of _adlSelected) {
    if (!s.blocks || !s.reps) { setError('adl-prescription-error', 'Please enter blocks and repetitions for all exercises.'); return; }
  }

  const ev = eventsCache.find(e => e.id === _adlPrescEventId);
  const exercises = _adlSelected.map(s => ({
    exercise_id: s.exercise.id,
    blocks:      s.blocks,
    repetitions: s.reps,
    notes:       s.notes,
  }));
  const notes = document.getElementById('adl-prescription-notes').value.trim();

  setLoading('adl-prescription-submit', true);
  const { ok, data } = await apiPost(`/api/patients/${PATIENT_HOMER_ID}/adl-prescription`, {
    event_id:          _adlPrescEventId,
    protocol_event_id: ev?.protocol_event_id,
    exercises,
    notes,
  });
  setLoading('adl-prescription-submit', false);

  if (!ok) { setError('adl-prescription-error', data.error || 'Failed to save prescription.'); return; }
  hideModal('adl-prescription-modal');
  _adlTabLoaded = false;
  loadPatientEvents();
}

// ── VCG Prescription modal ─────────────────────────────────────────────────────

async function openVcgPrescriptionModal(ev) {
  _vcgPrescEventId = typeof ev === 'object' ? ev.id : ev;
  const protocolId = typeof ev === 'object' ? ev.protocol_event_id : null;
  const vcgGroup   = patientData?.vcgGroup || '';

  let vcgDateValue, vcgDateLabel;
  if (protocolId === 'vcg_prescription_d15') {
    const hvEvent = (_completeEventsCache || []).find(e => e.protocol_event_id === 'home_visit_d15');
    vcgDateValue = hvEvent?.completion_date || '';
    vcgDateLabel = 'Home Visit Date';
  } else {
    vcgDateValue = patientData?.activationDate || '';
    vcgDateLabel = 'Activation Date';
  }

  document.getElementById('vcg-prescription-homer-id').textContent = PATIENT_HOMER_ID;
  document.getElementById('vcg-prescription-date-label').textContent = vcgDateLabel;
  document.getElementById('vcg-prescription-date').value = vcgDateValue;
  document.getElementById('vcg-prescription-group-label').textContent = VCG_GROUP_LABELS[vcgGroup] || vcgGroup || '—';
  document.getElementById('vcg-prescription-notes').value = '';
  setError('vcg-prescription-error', '');
  _vcgSelected = [];
  renderPrescSelected('vcg');
  showModal('vcg-prescription-modal');

  if (!vcgGroup) {
    setError('vcg-prescription-error', 'No VCG group assigned to this patient.');
    return;
  }

  try {
    if (!_vcgExercises.length || _vcgExercises._group !== vcgGroup) {
      const res = await fetch(`/api/exercises?type=vcg&group=${vcgGroup}`);
      if (!res.ok) throw new Error();
      _vcgExercises = await res.json();
      _vcgExercises._group = vcgGroup;
    }
    // Pre-populate for d15 revision
    if (protocolId === 'vcg_prescription_d15') {
      const res = await fetch(`/api/patients/${PATIENT_HOMER_ID}/prescription/vcg_prescription_d01`);
      if (res.ok) {
        const prev = await res.json();
        _vcgSelected = (prev.prescribed_exercises || []).map(pe => {
          const ex = _vcgExercises.find(e => e.id === pe.exercise_id);
          return ex ? { exercise: ex, blocks: pe.blocks || 1, reps: pe.repetitions || 1, notes: pe.notes || '', state: 'compact' } : null;
        }).filter(Boolean);
        document.getElementById('vcg-prescription-notes').value = prev.notes || '';
        renderPrescSelected('vcg');
      }
    }
  } catch (_) {
    setError('vcg-prescription-error', 'Failed to load exercises.');
  }
}

async function submitVcgPrescription() {
  if (!_vcgSelected.length) { setError('vcg-prescription-error', 'Please select at least one exercise.'); return; }
  if (_vcgSelected.some(s => s.state === 'editing')) { setError('vcg-prescription-error', 'Please save all exercise cards before submitting.'); return; }
  for (const s of _vcgSelected) {
    if (!s.blocks || !s.reps) { setError('vcg-prescription-error', 'Please enter blocks and repetitions for all exercises.'); return; }
  }

  const ev = eventsCache.find(e => e.id === _vcgPrescEventId);
  const exercises = _vcgSelected.map(s => ({
    exercise_id: s.exercise.id,
    blocks:      s.blocks,
    repetitions: s.reps,
    notes:       s.notes,
  }));
  const notes = document.getElementById('vcg-prescription-notes').value.trim();

  setLoading('vcg-prescription-submit', true);
  const { ok, data } = await apiPost(`/api/patients/${PATIENT_HOMER_ID}/vcg-prescription`, {
    event_id:          _vcgPrescEventId,
    protocol_event_id: ev?.protocol_event_id,
    exercises,
    notes,
  });
  setLoading('vcg-prescription-submit', false);

  if (!ok) { setError('vcg-prescription-error', data.error || 'Failed to save prescription.'); return; }
  hideModal('vcg-prescription-modal');
  _vcgTabLoaded = false;
  loadPatientEvents();
}

// ── ADL / VCG prescription tab viewers ────────────────────────────────────────

let _adlTabLoaded = false;
let _vcgTabLoaded = false;

function _prescriptionCard(data, exercises, dayLabel, headerClass, attachmentPath, timingDataList) {
  const exMap = Object.fromEntries(exercises.map(e => [e.id, e]));

  // Build a timing map for each timing dataset in the array
  const timingMaps = (timingDataList || []).map(td =>
    td ? Object.fromEntries((td.timings || []).map(t => [t.exercise_id, t])) : {}
  );

  // Determine day labels based on array length (e.g., ['D01','D02','D03'] or ['D15'])
  const dayTags = timingDataList?.length === 1 ? ['D15'] : ['D01', 'D02', 'D03'];

  const rows = (data.prescribed_exercises || []).map((pe, i) => {
    const name = exMap[pe.exercise_id]?.name || pe.exercise_id;
    const notesHtml = pe.notes
      ? `<p class="text-xs text-slate-400 mt-0.5 italic">${pe.notes}</p>` : '';

    // Build timing HTML for each day
    const timingLines = timingMaps.map((tmap, idx) => {
      const t = tmap[pe.exercise_id];
      if (!t) return '';
      const start = t.start ? t.start.split('T')[1].slice(0, 5) : '—';
      const end = t.end ? t.end.split('T')[1].slice(0, 5) : '—';
      return `<p class="text-xs font-mono text-slate-400">${dayTags[idx]}: ${start} → ${end}</p>`;
    }).join('');

    return `
      <div class="flex items-start gap-3 py-2.5 border-b border-slate-100 last:border-b-0">
        <span class="w-5 h-5 rounded-full bg-slate-100 text-slate-500 text-xs font-bold flex items-center justify-center flex-shrink-0 mt-0.5">${i + 1}</span>
        <div class="flex-1 min-w-0">
          <span class="text-sm font-semibold text-slate-800">${name}</span>
          ${notesHtml}
        </div>
        <div class="flex-shrink-0 text-right">
          <p class="text-xs font-medium text-slate-500 whitespace-nowrap">${pe.blocks} sets × ${pe.repetitions} reps</p>
          ${timingLines}
        </div>
      </div>`;
  }).join('');

  const generalNotes = data.notes ? `
    <div class="mt-3 pt-3 border-t border-slate-100">
      <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-1">General Notes</p>
      <p class="text-sm text-slate-600">${data.notes}</p>
    </div>` : '';

  const downloadLink = attachmentPath ? `
    <a href="/api/patients/${PATIENT_HOMER_ID}/attachment/${attachmentPath}"
       download
       class="inline-flex items-center gap-1.5 text-xs font-semibold text-white/90 hover:text-white">
      <i class="fas fa-file-pdf"></i> Download PDF
    </a>` : '';

  return `
    <div class="bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">
      <div class="flex items-center justify-between px-5 py-3 ${headerClass}">
        <h3 class="text-sm font-bold">${dayLabel}</h3>
        <div class="flex items-center gap-4">
          ${downloadLink}
          <div class="text-right">
            <p class="text-xs opacity-70">Filed ${data.filed_at}</p>
            <p class="text-xs opacity-50">by ${data.filed_by}</p>
          </div>
        </div>
      </div>
      <div class="px-5 py-2">
        ${rows}
        ${generalNotes}
      </div>
    </div>`;
}

// ── Devices Tab (activity graph) ──────────────────────────────────────────────

let _devicesTabLoaded = false;
let _devicesCharts = {};  // device → Chart instance

async function loadDevicesTab() {
  if (_devicesTabLoaded) return;
  _devicesTabLoaded = true;
  const container = document.getElementById('devices-tab-content');
  if (!container) return;

  // Only show graph for experimental patients
  if (patientData?.group !== 'experimental') {
    container.innerHTML = `<div class="flex flex-col items-center justify-center py-16 text-slate-400">
      <i class="fas fa-mobile-alt text-3xl mb-3"></i>
      <p class="font-medium">No robot devices for control patients</p>
    </div>`;
    return;
  }

  await _renderDeviceGraphs(container);
}

async function _renderDeviceGraphs(container) {
  container.innerHTML = `<div class="flex items-center justify-center py-12 text-slate-400">
    <i class="fas fa-spinner fa-spin mr-2"></i><span>Loading device data…</span></div>`;

  try {
    const res  = await fetch(`/api/patients/${PATIENT_HOMER_ID}/activity`);
    const data = await res.json();
    const hasData = data.pluto || data.mars;

    const syncBtn = `<button onclick="_syncActivity()"
      class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-slate-700 text-white rounded-lg hover:bg-slate-800 active:scale-95 transition-all">
      <i class="fas fa-sync-alt text-[10px]"></i> Sync from S3
    </button>`;

    if (!hasData) {
      container.innerHTML = `
        <div class="flex items-center justify-end mb-4">${syncBtn}</div>
        <div class="flex flex-col items-center justify-center py-20 text-slate-400 bg-white rounded-2xl border border-slate-200">
          <i class="fas fa-chart-line text-4xl mb-4 opacity-40"></i>
          <p class="font-semibold text-slate-500">No device data available yet</p>
          <p class="text-sm mt-1 text-slate-400">Use "Sync from S3" to download the latest data.</p>
        </div>`;
      return;
    }

    container.innerHTML = `<div class="flex items-center justify-end mb-1">${syncBtn}</div>`;

    const DEVICE_CFG = {
      pluto: { label: 'Pluto',  color: '#2563eb', bg: '#eff6ff', accent: '#1d4ed8', iconColor: 'text-blue-600',  badgeBg: 'bg-blue-50',  badgeBorder: 'border-blue-200',  badgeText: 'text-blue-700'  },
      mars:  { label: 'Mars',   color: '#059669', bg: '#f0fdf4', accent: '#047857', iconColor: 'text-emerald-600', badgeBg: 'bg-emerald-50', badgeBorder: 'border-emerald-200', badgeText: 'text-emerald-700' },
    };

    for (const [deviceKey, cfg] of Object.entries(DEVICE_CFG)) {
      const d = data[deviceKey];
      if (!d) continue;

      // Stat: days with data, total minutes, avg
      const actualDays = d.data.filter(v => v !== null && v > 0).length;
      const totalMins  = d.data.reduce((s, v) => s + (v || 0), 0).toFixed(1);
      const avgMins    = actualDays ? (totalMins / actualDays).toFixed(1) : '—';

      // Check if there are actual CSV date files available for this device (dates_with_data)
      // If dates_with_data is missing, empty, or not an array, show "No data available"
      const hasDatesWithData = Array.isArray(d.dates_with_data) && d.dates_with_data.length > 0;
      if (!hasDatesWithData) {
        const card = document.createElement('div');
        card.className = 'bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden';
        card.innerHTML = `
          <div class="flex items-center gap-3 px-6 py-4 border-b border-slate-100" style="background:${cfg.bg}">
            <div class="w-9 h-9 rounded-xl flex items-center justify-center shadow-sm" style="background:${cfg.color}">
              <i class="fas fa-robot text-white text-sm"></i>
            </div>
            <div>
              <h3 class="text-sm font-bold text-slate-800">${cfg.label}</h3>
              <p class="text-xs text-slate-500">${d.start_date} → ${d.end_date} &nbsp;·&nbsp; Training side: <strong>${d.training_side}</strong></p>
            </div>
          </div>
          <div class="flex flex-col items-center justify-center py-16 text-slate-400 bg-white">
            <i class="fas fa-inbox text-3xl mb-3 opacity-40"></i>
            <p class="font-semibold text-slate-500">No data available</p>
            <p class="text-sm mt-1 text-slate-400">No activity recorded for this device during this period.</p>
          </div>`;
        container.appendChild(card);
        continue;
      }

      // Prescribed mechanism chips
      const mechChips = Object.entries(d.prescribed || {}).map(([mech, mins]) =>
        `<div class="flex flex-col items-center px-3 py-2 rounded-xl border ${cfg.badgeBorder} ${cfg.badgeBg} min-w-[56px]">
          <span class="text-[11px] font-bold ${cfg.badgeText} tracking-wide">${mech}</span>
          <span class="text-base font-bold ${cfg.badgeText} leading-tight">${mins}</span>
          <span class="text-[10px] text-slate-400 -mt-0.5">min/day</span>
        </div>`
      ).join('');

      const mismatchBanner = d.mismatch ? `
        <!-- Mismatch warning -->
        <div class="flex items-start gap-3 px-6 py-3 bg-orange-50 border-b border-orange-200">
          <i class="fas fa-exclamation-triangle text-orange-500 mt-0.5 shrink-0"></i>
          <div>
            <p class="text-sm font-semibold text-orange-800">Config date mismatch (${d.mismatch.diff_days > 0 ? '+' : ''}${d.mismatch.diff_days} day${Math.abs(d.mismatch.diff_days) !== 1 ? 's' : ''})</p>
            <p class="text-xs text-orange-600 mt-0.5">Config StartDate: <strong>${d.mismatch.config_start}</strong> · Activation date: <strong>${d.mismatch.activation}</strong>. The graph window may not align with actual therapy dates.</p>
          </div>
        </div>` : '';

      const card = document.createElement('div');
      card.className = 'bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden';
      card.innerHTML = `
        <!-- Card header -->
        <div class="flex items-center gap-3 px-6 py-4 border-b border-slate-100" style="background:${cfg.bg}">
          <div class="w-9 h-9 rounded-xl flex items-center justify-center shadow-sm" style="background:${cfg.color}">
            <i class="fas fa-robot text-white text-sm"></i>
          </div>
          <div>
            <h3 class="text-sm font-bold text-slate-800">${cfg.label}</h3>
            <p class="text-xs text-slate-500">${d.start_date} → ${d.end_date} &nbsp;·&nbsp; Training side: <strong>${d.training_side}</strong></p>
          </div>
          <div class="ml-auto flex items-center gap-4 text-right">
            <div>
              <p class="text-xs text-slate-400 leading-none">Total</p>
              <p class="text-lg font-bold leading-tight" style="color:${cfg.color}">${totalMins}<span class="text-xs font-normal text-slate-400 ml-0.5">min</span></p>
            </div>
            <div>
              <p class="text-xs text-slate-400 leading-none">Avg/day</p>
              <p class="text-lg font-bold leading-tight" style="color:${cfg.color}">${avgMins}<span class="text-xs font-normal text-slate-400 ml-0.5">min</span></p>
            </div>
            <div>
              <p class="text-xs text-slate-400 leading-none">Active days</p>
              <p class="text-lg font-bold leading-tight" style="color:${cfg.color}">${actualDays}<span class="text-xs font-normal text-slate-400 ml-0.5">/ 30</span></p>
            </div>
          </div>
        </div>

        <!-- Prescription row -->
        <div class="px-6 py-4 border-b border-slate-100 bg-slate-50">
          <div class="flex items-center gap-3 mb-3">
            <span class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Prescribed Mechanisms</span>
            <span class="text-xs text-slate-400">Daily target: <strong style="color:${cfg.color}">${d.target} min total</strong></span>
          </div>
          <div class="flex flex-wrap gap-2">${mechChips}</div>
        </div>

        ${mismatchBanner}

        <!-- Chart -->
        <div class="px-6 pt-5 pb-4">
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-semibold text-slate-500 uppercase tracking-wide">Daily Activity</span>
            <div class="flex items-center gap-4 text-xs text-slate-400">
              <span class="flex items-center gap-1.5"><span class="inline-block w-2.5 h-2.5 rounded-full" style="background:${cfg.color}"></span>Actual</span>
              <span class="flex items-center gap-1.5"><span class="inline-block w-3 h-0" style="border-top:2px dotted #f87171"></span>Target</span>
              <span class="flex items-center gap-1.5"><span class="inline-block w-2.5 h-2.5 rounded-full border-2" style="background:${cfg.color};border-color:white;box-shadow:0 0 0 2px ${cfg.color}"></span>Hover dot for breakdown</span>
            </div>
          </div>
          <div style="position:relative;height:220px">
            <canvas id="devices-chart-${deviceKey}"></canvas>
          </div>
        </div>

        <!-- Breakdown panel (hidden until dot clicked) -->
        <div id="devices-detail-${deviceKey}" class="hidden border-t border-slate-100"></div>`;

      container.appendChild(card);

      const ctx = document.getElementById(`devices-chart-${deviceKey}`).getContext('2d');
      if (_devicesCharts[deviceKey]) _devicesCharts[deviceKey].destroy();

      // Format labels as short dates for display
      const shortLabels = d.labels.map(lbl => {
        const dt = new Date(lbl);
        return dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
      });

      _devicesCharts[deviceKey] = new Chart(ctx, {
        type: 'line',
        data: {
          labels: shortLabels,
          datasets: [
            {
              label: 'Session (min)',
              data: d.data,
              borderColor: cfg.color,
              backgroundColor: cfg.color + '22',
              borderWidth: 2.5,
              pointRadius: d.labels.map(lbl => d.dates_with_data.includes(lbl) ? 5 : 3),
              pointBackgroundColor: d.labels.map(lbl =>
                d.dates_with_data.includes(lbl) ? cfg.color : cfg.color + '88'),
              pointHoverRadius: 7,
              fill: true,
              tension: 0.3,
              spanGaps: false,
              order: 2,
            },
            {
              label: 'Target',
              data: d.labels.map(() => d.target),
              borderColor: '#f87171',
              borderDash: [2, 2],
              borderWidth: 2,
              pointRadius: 0,
              fill: false,
              tension: 0,
              order: 1,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: '#1e293b',
              padding: 10,
              titleFont: { size: 12 },
              bodyFont: { size: 12 },
              callbacks: {
                title: items => d.labels[items[0].dataIndex],
                label: c => c.dataset.label === 'Target'
                  ? `  Target: ${c.parsed.y} min`
                  : `  Actual: ${c.parsed.y !== null ? c.parsed.y + ' min' : 'No session'}`,
                afterBody: () => {
                  // Hide the dot info comment box completely
                  return [];
                },
              },
            },
          },
          scales: {
            x: {
              grid: { display: false },
              ticks: { font: { size: 10 }, maxRotation: 45, minRotation: 0 },
            },
            y: {
              beginAtZero: true,
              grid: { color: '#f1f5f9' },
              ticks: { font: { size: 11 }, stepSize: 10 },
              title: { display: true, text: 'Minutes', font: { size: 11 }, color: '#94a3b8' },
            },
          },
          onHover: (evt, elements) => {
            if (!elements || !elements.length) {
              // Hide detail panel when not hovering
              const panel = document.getElementById(`devices-detail-${deviceKey}`);
              if (panel) panel.classList.add('hidden');
              return;
            }

            const hoveredElement = elements.find(el => el.datasetIndex === 0);
            if (!hoveredElement) return;

            const idx = hoveredElement.index;
            if (idx === undefined || idx === null) return;

            const hoveredDate = d.labels[idx];
            const actualValue = d.data[idx];
            const displayDate = shortLabels[idx];

            // Show detail only if the date has a data file (CSV exists in Dates folder)
            if (d.dates_with_data.includes(hoveredDate)) {
              _loadDeviceDetail(hoveredDate, deviceKey, cfg.label, cfg.color, displayDate);
            } else {
              // Show "No data available" message when hovering over a point with no data
              const panel = document.getElementById(`devices-detail-${deviceKey}`);
              if (panel) {
                panel.classList.remove('hidden');
                panel.innerHTML = `
                  <div class="px-6 py-6 flex flex-col items-center justify-center">
                    <i class="fas fa-inbox text-2xl mb-2 text-slate-300"></i>
                    <p class="text-sm text-slate-400 text-center">No data available for ${displayDate || hoveredDate}</p>
                  </div>`;
              }
            }
          },
        },
      });
    }
  } catch (e) {
    container.innerHTML = `<div class="flex items-center justify-center py-12 text-red-500 text-sm gap-2">
      <i class="fas fa-exclamation-circle"></i> Failed to load device data.
    </div>`;
  }
}

async function _syncActivity() {
  const container = document.getElementById('devices-tab-content');
  if (!container) return;
  container.innerHTML = `<div class="flex items-center justify-center py-10 text-slate-400">
    <i class="fas fa-sync-alt fa-spin mr-2"></i><span>Syncing from S3…</span></div>`;
  try {
    const r = await fetch(`/api/patients/${PATIENT_HOMER_ID}/sync-activity`, { method: 'POST' });
    const res = await r.json();
    if (!r.ok || res.error) {
      container.innerHTML = `<div class="flex flex-col items-center justify-center py-16 text-slate-400">
        <i class="fas fa-exclamation-circle text-2xl mb-3 text-red-400"></i>
        <p class="text-sm text-red-500">${res.error || 'Sync failed'}</p>
        <button onclick="_renderDeviceGraphs(document.getElementById('devices-tab-content'))"
          class="mt-4 px-3 py-1.5 text-xs font-semibold bg-slate-100 text-slate-600 rounded-lg hover:bg-slate-200">
          Try viewing existing data
        </button>
      </div>`;
      return;
    }
    _devicesTabLoaded = false;
    Object.values(_devicesCharts).forEach(c => c.destroy());
    _devicesCharts = {};
    await _renderDeviceGraphs(container);
  } catch (e) {
    container.innerHTML = `<div class="flex items-center justify-center py-10 text-red-500 text-sm">
      <i class="fas fa-exclamation-circle mr-2"></i>Network error during sync.
    </div>`;
  }
}

async function _loadDeviceDetail(date, deviceKey, deviceLabel, color, displayDate) {
  const panel = document.getElementById(`devices-detail-${deviceKey}`);
  if (!panel) {
    console.warn(`Panel not found: devices-detail-${deviceKey}`);
    return;
  }

  panel.classList.remove('hidden');
  panel.innerHTML = `<div class="flex items-center justify-center py-6 text-slate-400 text-sm">
    <i class="fas fa-spinner fa-spin mr-2"></i>Loading…</div>`;

  try {
    // Ensure date is in YYYY-MM-DD format
    let dateParam = date;
    if (date && typeof date === 'string' && date.includes('T')) {
      // Extract just the date part if it's ISO datetime
      dateParam = date.split('T')[0];
    }

    const url = `/api/patients/${PATIENT_HOMER_ID}/activity/${dateParam}/${deviceKey}`;
    const res = await fetch(url);
    if (!res.ok) {
      const errorData = await res.json().catch(() => ({}));
      console.error('API error:', res.status, errorData);
      panel.innerHTML = `<p class="text-sm text-slate-400 text-center py-4">${errorData.error || 'No data available'}</p>`;
      return;
    }

    const d = await res.json();
    if (d.error) {
      panel.innerHTML = `<p class="text-sm text-slate-400 text-center py-4">${d.error}</p>`;
      return;
    }

    if (!d.mechanisms || !d.durations || !d.target) {
      console.warn('Invalid data structure:', d);
      panel.innerHTML = `<p class="text-sm text-slate-400 text-center py-4">Invalid data structure</p>`;
      return;
    }

    const maxVal = Math.max(...d.durations, ...d.target, 1);
    const bars = d.mechanisms.map((mech, i) => {
      const used    = d.durations[i] || 0;
      const tgt     = d.target[i]    || 0;
      const pctUsed = maxVal > 0 ? Math.round((used / maxVal) * 100) : 0;
      const pctTgt  = maxVal > 0 ? Math.round((tgt  / maxVal) * 100) : 0;
      return `<div class="flex items-center gap-3">
        <span class="w-14 text-right text-xs font-medium text-slate-600 shrink-0">${mech}</span>
        <div class="flex-1 relative h-5 bg-slate-100 rounded-full overflow-hidden">
          <div class="absolute inset-y-0 left-0 rounded-full" style="width:${pctUsed}%;background:${color}88"></div>
          <div class="absolute inset-y-0 w-0.5 bg-red-400" style="left:${pctTgt}%"></div>
        </div>
        <span class="text-xs text-slate-500 w-28 shrink-0">${used} / ${tgt} min</span>
      </div>`;
    }).join('');

    panel.innerHTML = `
      <div class="px-6 py-4">
        <div class="flex items-center justify-between mb-3">
          <p class="text-xs font-semibold text-slate-600">${deviceLabel} — ${displayDate || date}</p>
          <span class="text-xs text-slate-400">Bar = used &nbsp;|&nbsp; <span class="text-red-400 font-bold">|</span> = target</span>
        </div>
        <div class="space-y-2">${bars}</div>
      </div>`;
  } catch (e) {
    console.error('Failed to load device detail:', e);
    panel.innerHTML = `<p class="text-sm text-red-400 text-center py-4">Failed to load breakdown: ${e.message}</p>`;
  }
}

async function loadAdlTab() {
  if (_adlTabLoaded) return;
  const container = document.getElementById('adl-tab-content');
  if (!container) return;

  try {
    const [exRes, d1Res, d15Res, t01Res, t02Res, t03Res, t15Res] = await Promise.all([
      fetch('/api/exercises?type=adl'),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/prescription/adl_prescription_d01`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/prescription/adl_prescription_d15`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/agwatch-timing/agwatch_timing_d01`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/agwatch-timing/agwatch_timing_d02`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/agwatch-timing/agwatch_timing_d03`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/agwatch-timing/agwatch_timing_d15`),
    ]);
    const exercises = exRes.ok  ? await exRes.json()  : [];
    const d1        = d1Res.ok  ? await d1Res.json()  : null;
    const d15       = d15Res.ok ? await d15Res.json() : null;
    const _filterAdl = td => td ? { ...td, timings: (td.timings || []).filter(t => t.type === 'adl') } : null;
    const t01       = _filterAdl(t01Res.ok ? await t01Res.json() : null);
    const t02       = _filterAdl(t02Res.ok ? await t02Res.json() : null);
    const t03       = _filterAdl(t03Res.ok ? await t03Res.json() : null);
    const t15       = _filterAdl(t15Res.ok ? await t15Res.json() : null);

    if (!d1 && !d15) {
      container.innerHTML = `
        <div class="bg-white rounded-2xl p-10 shadow-sm border border-slate-100 text-center text-slate-400">
          <i class="fas fa-dumbbell text-3xl mb-3 block"></i>
          <p class="font-medium">No ADL prescriptions recorded yet.</p>
        </div>`;
    } else {
      const printD1  = (_completeEventsCache || []).find(e => e.protocol_event_id === 'prescription_printout_d01');
      const printD15 = (_completeEventsCache || []).find(e => e.protocol_event_id === 'prescription_printout_d15');
      let html = '';
      if (d15) html += _prescriptionCard(d15, exercises, 'Day 15 Revision',    'bg-blue-600 text-white',  printD15?.attachment, [t15]);
      if (d1)  html += _prescriptionCard(d1,  exercises, 'Day 1 Prescription', 'bg-blue-400 text-white', printD1?.attachment,  [t01, t02, t03]);
      container.innerHTML = html;
    }
    _adlTabLoaded = true;
  } catch (_) {
    container.innerHTML = `<p class="text-sm text-red-500 p-4">Failed to load ADL prescriptions.</p>`;
  }
}

async function loadVcgTab() {
  if (_vcgTabLoaded) return;
  const container = document.getElementById('vcg-tab-content');
  if (!container) return;

  const vcgGroup  = patientData?.vcgGroup || '';
  const groupLabel = VCG_GROUP_LABELS[vcgGroup] || vcgGroup || '';

  try {
    const [exRes, d1Res, d15Res, t01Res, t02Res, t03Res, t15Res] = await Promise.all([
      fetch(`/api/exercises?type=vcg&group=${vcgGroup}`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/prescription/vcg_prescription_d01`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/prescription/vcg_prescription_d15`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/agwatch-timing/agwatch_timing_d01`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/agwatch-timing/agwatch_timing_d02`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/agwatch-timing/agwatch_timing_d03`),
      fetch(`/api/patients/${PATIENT_HOMER_ID}/agwatch-timing/agwatch_timing_d15`),
    ]);
    const exercises = exRes.ok  ? await exRes.json()  : [];
    const d1        = d1Res.ok  ? await d1Res.json()  : null;
    const d15       = d15Res.ok ? await d15Res.json() : null;
    const _filterVcg = td => td ? { ...td, timings: (td.timings || []).filter(t => t.type === 'vcg') } : null;
    const t01       = _filterVcg(t01Res.ok ? await t01Res.json() : null);
    const t02       = _filterVcg(t02Res.ok ? await t02Res.json() : null);
    const t03       = _filterVcg(t03Res.ok ? await t03Res.json() : null);
    const t15       = _filterVcg(t15Res.ok ? await t15Res.json() : null);

    if (!d1 && !d15) {
      container.innerHTML = `
        <div class="bg-white rounded-2xl p-10 shadow-sm border border-slate-100 text-center text-slate-400">
          <i class="fas fa-heartbeat text-3xl mb-3 block"></i>
          <p class="font-medium">No VCG prescriptions recorded yet.</p>
        </div>`;
    } else {
      const printD1  = (_completeEventsCache || []).find(e => e.protocol_event_id === 'prescription_printout_d01');
      const printD15 = (_completeEventsCache || []).find(e => e.protocol_event_id === 'prescription_printout_d15');
      const suffix = groupLabel ? ` · <span class="font-normal opacity-70">${groupLabel}</span>` : '';
      let html = '';
      if (d15) html += _prescriptionCard(d15, exercises, `Day 15 Revision${suffix}`,    'bg-teal-600 text-white',  printD15?.attachment, [t15]);
      if (d1)  html += _prescriptionCard(d1,  exercises, `Day 1 Prescription${suffix}`, 'bg-teal-400 text-white', printD1?.attachment,  [t01, t02, t03]);
      container.innerHTML = html;
    }
    _vcgTabLoaded = true;
  } catch (_) {
    container.innerHTML = `<p class="text-sm text-red-500 p-4">Failed to load VCG prescriptions.</p>`;
  }
}

// ── Prescription Printout modal ────────────────────────────────────────────────

const SITE_LANGUAGES = {
  'Ranipet':  ['english', 'tamil', 'telugu'],
  'Manipal':  ['english', 'kannada', 'hindi'],
  'Ludhiana': ['english', 'punjabi', 'hindi'],
};

const LANGUAGE_NAMES = {
  'english':  'English',
  'tamil':    'தமிழ்',
  'telugu':   'తెలుగు',
  'kannada':  'ಕನ್ನಡ',
  'hindi':    'हिंदी',
  'punjabi':  'ਪੰਜਾਬੀ',
};

let _prescPrintoutEventId     = null;
let _prescPrintoutProtocolId  = null;
let _prescPrintoutLanguage    = 'english';

function openPrescriptionPrintoutModal(ev) {
  _prescPrintoutEventId    = typeof ev === 'object' ? ev.id : ev;
  _prescPrintoutProtocolId = typeof ev === 'object' ? ev.protocol_event_id : null;
  // After setting _prescPrintoutLanguage = 'english', disable buttons
document.getElementById('prescription-printout-print').disabled = true;
document.getElementById('prescription-printout-save').disabled = true;

  const title = _prescPrintoutProtocolId === 'prescription_printout_d15'
    ? 'Revised Therapy Prescription Printout'
    : 'Therapy Prescription Printout';

  document.getElementById('prescription-printout-title').textContent = title;
  document.getElementById('prescription-printout-homer-id').textContent = PATIENT_HOMER_ID;
  setError('prescription-printout-error', '');

  // Create language buttons
  const buttonsContainer = document.getElementById('presc-printout-language-buttons');
  buttonsContainer.innerHTML = '';
  const languages = SITE_LANGUAGES[PATIENT_PLACE] || ['english'];

  languages.forEach(lang => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.dataset.language = lang;
    btn.textContent = LANGUAGE_NAMES[lang] || lang;
    btn.className = 'px-6 py-2 rounded-full text-sm font-medium transition-all ' +
                    'bg-slate-200 text-slate-700 hover:bg-slate-300';
    btn.onclick = () => selectPrescriptionLanguage(lang);
    buttonsContainer.appendChild(btn);
  });

  _prescPrintoutLanguage = 'english';

  // Reset preview
  document.getElementById('presc-printout-preview').innerHTML =
    '<p class="text-slate-400 text-center py-12 text-sm">Select a language to preview the pamphlet</p>';

  showModal('prescription-printout-modal');
}

function selectPrescriptionLanguage(lang) {
  _prescPrintoutLanguage = lang;

  // Update button styles
  document.querySelectorAll('#presc-printout-language-buttons button').forEach(btn => {
    if (btn.dataset.language === lang) {
      btn.className = 'px-6 py-2 rounded-full text-sm font-medium transition-all ' +
                      'bg-blue-500 text-white hover:bg-blue-600';
    } else {
      btn.className = 'px-6 py-2 rounded-full text-sm font-medium transition-all ' +
                      'bg-slate-200 text-slate-700 hover:bg-slate-300';
    }
  });
     // After loading pamphlet, enable buttons
  document.getElementById('prescription-printout-print').disabled = false;
  document.getElementById('prescription-printout-save').disabled = false;

  _loadPrescriptionPamphlet();
}

async function _loadPrescriptionPamphlet() {
  if (!_prescPrintoutLanguage) {
    document.getElementById('presc-printout-preview').innerHTML =
      '<p class="text-slate-400 text-center py-12 text-sm">Select a language to preview the pamphlet</p>';
    return;
  }

  const preview = document.getElementById('presc-printout-preview');
  preview.innerHTML = '<p class="text-slate-400 text-center py-12 text-sm">Loading pamphlet...</p>';

  try {
    const res = await fetch(
      `/api/patients/${PATIENT_HOMER_ID}/prescription-pamphlet?event_id=${_prescPrintoutEventId}&language=${_prescPrintoutLanguage}`
    );
    if (!res.ok) {
      preview.innerHTML = '<p class="text-red-500 text-center py-12 text-sm">Failed to load pamphlet</p>';
      return;
    }
    const html = await res.text();
    preview.innerHTML = html;
  } catch (e) {
    preview.innerHTML = '<p class="text-red-500 text-center py-12 text-sm">Error loading pamphlet</p>';
  }
}

async function savePrescriptionPrintout() {
  if (!_prescPrintoutLanguage) {
    setError('prescription-printout-error', 'Please select a language first');
    return;
  }

  setLoading('prescription-printout-save', true);

  try {
    const previewDiv = document.getElementById('presc-printout-preview');
    const htmlContent = previewDiv.innerHTML;

    // Send HTML to server for server-side PDF generation with Puppeteer
    const { ok: renderOk, data: renderData } = await apiPost(
      `/api/patients/${PATIENT_HOMER_ID}/generate-prescription-pdf`,
      {
        event_id: _prescPrintoutEventId,
        protocol_event_id: _prescPrintoutProtocolId,
        language: _prescPrintoutLanguage,
        html_content: htmlContent,
        caption: `Exercise Prescription Printout (${_prescPrintoutLanguage})`
      }
    );

    if (!renderOk) {
      throw new Error(renderData.error || 'Failed to generate PDF');
    }

    // Success: close modal and refresh events
    hideModal('prescription-printout-modal');
    loadPatientEvents();

  } catch (err) {
    setError('prescription-printout-error', err.message || 'Failed to generate and save PDF');
  } finally {
    setLoading('prescription-printout-save', false);
  }
}

/* OLD CLIENT-SIDE PDF CODE (DISABLED - using server-side rendering now)
async function savePrescriptionPrintout_OLD() {
  try {
    const previewDiv = document.getElementById('presc-printout-preview');

    // Get jsPDF constructor - DISABLED (old code below for reference)
    let jsPDFConstructor = null;
    if (window.jsPDF && typeof window.jsPDF === 'function') {
      jsPDFConstructor = window.jsPDF;
    } else if (window.jspdf && typeof window.jspdf === 'function') {
      jsPDFConstructor = window.jspdf;
    } else if (window.jsPDF && window.jsPDF.jsPDF && typeof window.jsPDF.jsPDF === 'function') {
      jsPDFConstructor = window.jsPDF.jsPDF;
    } else if (window.jspdf && window.jspdf.jsPDF && typeof window.jspdf.jsPDF === 'function') {
      jsPDFConstructor = window.jspdf.jsPDF;
    } else if (window.jsPDF && window.jsPDF.default && typeof window.jsPDF.default === 'function') {
      jsPDFConstructor = window.jsPDF.default;
    } else if (window.jspdf && window.jspdf.default && typeof window.jspdf.default === 'function') {
      jsPDFConstructor = window.jspdf.default;
    }

    if (!jsPDFConstructor) {
      throw new Error('jsPDF library not loaded. Please refresh the page and try again.');
    }

    console.log('Capturing full preview content...');

    // Temporarily remove height constraints to capture all content
    const originalMaxHeight = previewDiv.style.maxHeight;
    const originalOverflow = previewDiv.style.overflowY;
    const originalHeight = previewDiv.style.height;

    previewDiv.style.maxHeight = 'none';
    previewDiv.style.overflowY = 'visible';
    previewDiv.style.height = 'auto';

    // Capture with html2canvas
    const canvas = await html2canvas(previewDiv, {
      scale: 1.5,
      useCORS: true,
      logging: false,
      allowTaint: true,
      backgroundColor: '#ffffff',
      windowHeight: previewDiv.scrollHeight
    });

    // Restore original styles
    previewDiv.style.maxHeight = originalMaxHeight;
    previewDiv.style.overflowY = originalOverflow;
    previewDiv.style.height = originalHeight;

}
*/

// ── Custom PDF Dialog Modal ────────────────────────────────────────

let _pdfDialogSettings = {
  pageSize: 'a4',
  scale: 100,
  margins: 10
};

function openPrescriptionPdfDialog() {
  if (!_prescPrintoutLanguage) {
    setError('prescription-printout-error', 'Please select a language first');
    return;
  }

  console.log('Opening PDF dialog...');

  // Reset settings to defaults
  _pdfDialogSettings = {
    pageSize: 'a4',
    scale: 100,
    margins: 10
  };

  // Update UI
  document.getElementById('pdf-page-size').value = 'a4';
  document.getElementById('pdf-scale').value = 100;
  document.getElementById('pdf-scale-value').textContent = '100%';
  document.getElementById('pdf-margins').value = 10;

  // Show preview
  updatePdfPreview();

  // Setup event listeners
  document.getElementById('pdf-page-size').addEventListener('change', (e) => {
    _pdfDialogSettings.pageSize = e.target.value;
    updatePdfPreview();
  });

  document.getElementById('pdf-scale').addEventListener('input', (e) => {
    _pdfDialogSettings.scale = parseInt(e.target.value);
    document.getElementById('pdf-scale-value').textContent = _pdfDialogSettings.scale + '%';
    updatePdfPreview();
  });

  document.getElementById('pdf-margins').addEventListener('change', (e) => {
    _pdfDialogSettings.margins = parseInt(e.target.value) || 10;
  });

  // Show modal
  showModal('prescription-pdf-dialog-modal');
}

function updatePdfPreview() {
  const previewDiv = document.getElementById('presc-printout-preview');
  const previewPane = document.getElementById('pdf-preview-pane');

  if (!previewDiv) return;

  // Clone preview content with current scale
  const clone = previewDiv.cloneNode(true);
  clone.style.transform = `scale(${_pdfDialogSettings.scale / 100})`;
  clone.style.transformOrigin = 'top left';
  clone.style.width = `${100 / (_pdfDialogSettings.scale / 100)}%`;

  previewPane.innerHTML = '';
  previewPane.appendChild(clone);
}

async function savePrescriptionPdfFromDialog() {
  setLoading('prescription-pdf-save-dialog', true);

  try {
    const previewDiv = document.getElementById('presc-printout-preview');

    // Get jsPDF constructor
    let jsPDFConstructor = null;
    if (window.jsPDF && typeof window.jsPDF === 'function') {
      jsPDFConstructor = window.jsPDF;
    } else if (window.jsPDF && window.jsPDF.jsPDF && typeof window.jsPDF.jsPDF === 'function') {
      jsPDFConstructor = window.jsPDF.jsPDF;
    } else if (window.jspdf && window.jspdf.jsPDF && typeof window.jspdf.jsPDF === 'function') {
      jsPDFConstructor = window.jspdf.jsPDF;
    }

    if (!jsPDFConstructor) {
      throw new Error('jsPDF library not loaded. Please refresh and try again.');
    }

    console.log('Generating PDF with user settings...');

    // Prepare element for capture
    const originalMaxHeight = previewDiv.style.maxHeight;
    const originalOverflow = previewDiv.style.overflowY;
    const originalHeight = previewDiv.style.height;

    previewDiv.style.maxHeight = 'none';
    previewDiv.style.overflowY = 'visible';
    previewDiv.style.height = 'auto';

    // Capture with html2canvas using user's scale setting
    const canvas = await html2canvas(previewDiv, {
      scale: _pdfDialogSettings.scale / 100,
      useCORS: true,
      logging: false,
      allowTaint: true,
      backgroundColor: '#ffffff',
      windowHeight: previewDiv.scrollHeight
    });

    // Restore original styles
    previewDiv.style.maxHeight = originalMaxHeight;
    previewDiv.style.overflowY = originalOverflow;
    previewDiv.style.height = originalHeight;

    console.log('Canvas created, creating PDF...');

    // Get page dimensions based on user settings
    const pageSizes = {
      a4: { width: 210, height: 297 },
      letter: { width: 216, height: 279 },
      a3: { width: 297, height: 420 }
    };
    const pageSize = pageSizes[_pdfDialogSettings.pageSize];
    const margins = _pdfDialogSettings.margins;
    const contentWidth = pageSize.width - (margins * 2);

    // Create PDF
    const imgData = canvas.toDataURL('image/png');
    const pdf = new jsPDFConstructor('p', 'mm', _pdfDialogSettings.pageSize);

    const imgHeight = (canvas.height * contentWidth) / canvas.width;
    let heightLeft = imgHeight;
    let position = margins;

    pdf.addImage(imgData, 'PNG', margins, position, contentWidth, imgHeight);
    heightLeft -= (pageSize.height - (margins * 2));

    while (heightLeft > 0) {
      position = heightLeft - imgHeight;
      pdf.addPage();
      pdf.addImage(imgData, 'PNG', margins, position, contentWidth, imgHeight);
      heightLeft -= (pageSize.height - (margins * 2));
    }

    const pdfBlob = pdf.output('blob');
    console.log('PDF created, size:', pdfBlob.size, 'bytes');

    // Mark event complete
    console.log('Marking event as complete...');
    const { ok: completeOk, data: completeData } = await apiPost(
      `/api/patients/${PATIENT_HOMER_ID}/complete-event/prescription-printout`,
      {
        event_id: _prescPrintoutEventId,
        protocol_event_id: _prescPrintoutProtocolId,
        language: _prescPrintoutLanguage,
      }
    );

    if (!completeOk) {
      throw new Error(completeData.error || 'Failed to mark event complete');
    }

    console.log('Event marked complete, uploading PDF...');

    // Upload attachment
    const formData = new FormData();
    formData.append('event_id', _prescPrintoutEventId);
    formData.append('caption', `Exercise Prescription Printout (${_prescPrintoutLanguage})`);
    formData.append('file', pdfBlob, `prescription_${_prescPrintoutLanguage}.pdf`);

    const uploadRes = await fetch(`/api/patients/${PATIENT_HOMER_ID}/upload-attachment`, {
      method: 'POST',
      body: formData,
    });

    if (!uploadRes.ok) {
      throw new Error('Failed to upload PDF');
    }

    console.log('PDF uploaded successfully');

    // Success
    hideModal('prescription-pdf-dialog-modal');
    hideModal('prescription-printout-modal');
    loadPatientEvents();

  } catch (err) {
    setError('prescription-printout-error', err.message || 'Failed to save PDF');
  } finally {
    setLoading('prescription-pdf-save-dialog', false);
  }
}

async function printPrescriptionPamphlet() {
  const previewDiv = document.getElementById('presc-printout-preview');
  // Check if we need to save first
    const event = _completeEventsCache?.find(e => e.id === _prescPrintoutEventId);
    if (!event) {
      // Event not yet complete - auto save first
      await savePrescriptionPrintout();
      // After save, proceed with print
    }
  // Check if pamphlet is loaded
  if (!previewDiv.innerHTML || previewDiv.innerHTML.includes('Select a language') || previewDiv.innerHTML.includes('Loading')) {
    setError('prescription-printout-error', 'Please select a language and wait for the preview to load first');
    return;
  }

  // Create a new window for printing
  const printWindow = window.open('', '', 'height=800,width=1000');

  if (!printWindow) {
    setError('prescription-printout-error', 'Pop-up window was blocked. Please allow pop-ups for this site.');
    return;
  }

  // Get the HTML content from the preview
  const htmlContent = previewDiv.innerHTML;

  // Build the complete HTML document
  const printHtml = `
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>Exercise Prescription Pamphlet</title>
      <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600&family=Noto+Sans+Devanagari:wght@400;500;600&family=Noto+Sans+Tamil:wght@400;500;600&family=Noto+Sans+Telugu:wght@400;500;600&family=Noto+Sans+Kannada:wght@400;500;600&family=Noto+Sans+Gurmukhi:wght@400;500;600&display=swap');

        * {
          margin: 0;
          padding: 0;
          box-sizing: border-box;
        }

        body {
          font-family: 'Noto Sans', 'Noto Sans Devanagari', 'Noto Sans Tamil', 'Noto Sans Telugu', 'Noto Sans Kannada', 'Noto Sans Gurmukhi', sans-serif;
          line-height: 1.5;
          color: #333;
          padding: 20px;
        }

        @media print {
          body { padding: 0; }
          .container { max-width: 100%; padding: 0; }
          .exercise-card { page-break-inside: avoid; page-break-before: always; }
          .exercise-card.first-exercise { page-break-before: auto; }
        }
      </style>
    </head>
    <body>
      ${htmlContent}
    </body>
    </html>
  `;

  // Write content directly to the new window (document.write is most reliable for print windows)
  // @ts-ignore - document.write is deprecated but necessary for reliable print window population
  printWindow.document.write(printHtml);
  printWindow.document.close();

  // Trigger print dialog immediately after content is written
  setTimeout(() => {
    printWindow.focus();
    printWindow.print();
  }, 100);
 
}

// ── Training Completion D29 modal ─────────────────────────────────────────────

let _d29EventId = null;

function openD29Modal(ev) {
  _d29EventId = ev.id;
  const nowStr = new Date().toISOString().slice(0, 16);
  const dateEl = document.getElementById('d29-date');
  dateEl.max   = nowStr;
  dateEl.value = '';
  document.getElementById('d29-notes').value          = '';
  document.getElementById('d29-feedback-file').value  = '';
  document.getElementById('d29-feedback-notes').value = '';
  document.getElementById('d29-audio-file').value     = '';
  document.getElementById('d29-scan-file').value      = '';
  document.getElementById('d29-qual-recruited').value = '';
  document.getElementById('d29-qual-uploads').classList.add('hidden');
  _d29UpdateFeedbackLabel();
  _d29StyleQualBtn(null);
  _resetAttachment('d29');
  const errEl = document.getElementById('d29-error');
  errEl.classList.add('hidden');
  errEl.textContent = '';

  // Attach guard first (sets max=today), then override with window bounds.
  _attachDateGuard('d29-a1-appointment', 'd29-error');
  const a1ApptInput = document.getElementById('d29-a1-appointment');
  if (a1ApptInput) {
    a1ApptInput.value = '';
    const a1Win = _assessmentWindows['a1_assessment'];
    if (a1Win) { a1ApptInput.min = a1Win.start; a1ApptInput.max = a1Win.end; }
    else        { a1ApptInput.removeAttribute('min'); a1ApptInput.removeAttribute('max'); }
  }

  // Show AE discussion section only when an adverse_event_followup stub exists.
  const hasAefStub = eventsCache.some(e => e.protocol_event_id === 'adverse_event_followup');
  const aeSect = document.getElementById('d29-ae-section');
  if (aeSect) aeSect.classList.toggle('hidden', !hasAefStub);
  document.getElementById('d29-ae-discussed').value = '';
  _d29StyleAeBtn(null);

  document.getElementById('d29-feedback-file').onchange = _d29UpdateFeedbackLabel;
  _attachDateGuard('d29-date', 'd29-error');
  showModal('d29-modal');
}

function _d29UpdateFeedbackLabel() {
  const hasFile = document.getElementById('d29-feedback-file').files.length > 0;
  const lbl     = document.getElementById('d29-feedback-notes-label');
  lbl.innerHTML = hasFile
    ? 'Notes <span class="text-slate-400 font-normal">(optional)</span>'
    : 'Notes <span class="text-red-500">*</span><span class="text-slate-400 font-normal"> (required — no PDF uploaded)</span>';
}

function _d29SelectQual(recruited) {
  document.getElementById('d29-qual-recruited').value = recruited ? 'true' : 'false';
  document.getElementById('d29-qual-uploads').classList.toggle('hidden', !recruited);
  if (!recruited) {
    document.getElementById('d29-audio-file').value = '';
    document.getElementById('d29-scan-file').value  = '';
  }
  _d29StyleQualBtn(recruited);
}

function _d29StyleQualBtn(recruited) {
  const yes = document.getElementById('d29-qual-yes-btn');
  const no  = document.getElementById('d29-qual-no-btn');
  const base     = 'flex-1 px-3 py-2 border rounded-xl text-sm font-medium transition-colors';
  const active   = 'bg-blue-600 border-blue-600 text-white';
  const inactive = 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100';
  yes.className = `${base} ${recruited === true  ? active : inactive}`;
  no.className  = `${base} ${recruited === false ? active : inactive}`;
}

function _d29SelectAeDiscussed(discussed) {
  document.getElementById('d29-ae-discussed').value = discussed ? 'yes' : 'no';
  _d29StyleAeBtn(discussed);
}

function _d29StyleAeBtn(discussed) {
  const yes = document.getElementById('d29-ae-yes-btn');
  const no  = document.getElementById('d29-ae-no-btn');
  if (!yes || !no) return;
  const base     = 'flex-1 px-3 py-2 border rounded-xl text-sm font-medium transition-colors';
  const active   = 'bg-amber-600 border-amber-600 text-white';
  const inactive = 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100';
  yes.className = `${base} ${discussed === true  ? active : inactive}`;
  no.className  = `${base} ${discussed === false ? active : inactive}`;
}

async function saveD29() {
  const err = document.getElementById('d29-error');
  const setErr = (msg) => { err.textContent = msg; err.classList.remove('hidden'); };
  err.classList.add('hidden');

  const completionDate = document.getElementById('d29-date').value;
  if (!completionDate) return setErr('Visit date is required.');

  const feedbackFile  = document.getElementById('d29-feedback-file').files[0] || null;
  const feedbackNotes = document.getElementById('d29-feedback-notes').value.trim();
  if (!feedbackFile && !feedbackNotes) return setErr('Feedback form: upload the PDF or provide notes.');

  const qualStr = document.getElementById('d29-qual-recruited').value;
  if (!qualStr) return setErr('Please indicate whether the patient was recruited for qualitative analysis.');
  const qualRecruited = qualStr === 'true';

  let audioFile = null;
  let scanFile  = null;
  if (qualRecruited) {
    audioFile = document.getElementById('d29-audio-file').files[0] || null;
    if (!audioFile) return setErr('Audio recording is required for qualitative analysis.');
    scanFile = document.getElementById('d29-scan-file').files[0] || null;
  }

  const { file: genericFile, caption: genericCaption } = _readAttachment('d29');
  if (genericFile && !genericCaption) return setErr('Please describe the attachment before saving.');

  const aeSectVisible = !document.getElementById('d29-ae-section')?.classList.contains('hidden');
  const aeDiscussed   = document.getElementById('d29-ae-discussed').value;
  if (aeSectVisible && !aeDiscussed) return setErr('Please indicate whether any AE-related discussion happened during this visit.');

  const form = new FormData();
  form.append('event_id',              _d29EventId || '');
  form.append('completion_date',       completionDate);
  form.append('notes',                 document.getElementById('d29-notes').value.trim());
  const a1Appt = (document.getElementById('d29-a1-appointment')?.value || '').trim();
  if (a1Appt) form.append('a1_appointment_date', a1Appt);
  form.append('feedback_form_notes',   feedbackNotes);
  form.append('qualitative_recruited', qualStr);
  if (feedbackFile) form.append('feedback_form_file', feedbackFile);
  if (audioFile)    form.append('qualitative_audio_file', audioFile);
  if (scanFile)     form.append('qualitative_scan_file', scanFile);
  if (genericFile)  { form.append('attachment_file', genericFile); form.append('attachment_caption', genericCaption); }

  const btn = document.querySelector('#d29-modal button[onclick="saveD29()"]');
  if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }

  try {
    const res  = await fetch(`/api/patients/${PATIENT_HOMER_ID}/complete-event/training-completion`, { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) return setErr(data.error || 'Save failed.');
    hideModal('d29-modal');
    await loadPatientEvents();
    if (aeDiscussed === 'yes') {
      // D29 is a home visit, not a call. The AE discussion happened *during*
      // the visit, so we file an `adverse_event_followup_visit` entry (not an
      // `adverse_event_followup` call entry). The daily call stub in
      // incomplete[] is left untouched — the visit is an additional record
      // stamped with triggered_by pointing at this D29 entry. AE ids come
      // from the daily call stub (it tracks the active AE chain).
      const aefStub = eventsCache.find(e => e.protocol_event_id === 'adverse_event_followup');
      if (aefStub) {
        openAeFollowupVisitModal(null, {
          date:        completionDate,
          label:       'D29 visit',
          triggeredBy: { type: 'training_completion_d29', id: _d29EventId },
          aeIds:       aefStub.adverse_event_ids || [],
        });
      }
    }
  } catch (e) {
    setErr('Network error. Please try again.');
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = 'Save'; }
  }
}

// ── Simple event modal (home visits, follow-up calls, training completion) ────

let _simpleEventId         = null;
let _simpleProtocolEventId = null;

function openSimpleEventModal(ev) {
  _simpleEventId         = ev.id;
  _simpleProtocolEventId = ev.protocol_event_id;
  document.getElementById('simple-event-title').textContent = ev.event_name;
  document.getElementById('simple-event-notes').value       = '';
  _resetAttachment('simple-event');
  const err         = document.getElementById('simple-event-error');
  const dateWrap    = document.getElementById('simple-event-date-wrap');
  const sessionWrap = document.getElementById('simple-event-session-wrap');
  err.textContent = '';
  err.classList.add('hidden');

  const HOME_VISIT_SESSION_IDS = new Set(['home_visit_d02', 'home_visit_d03', 'home_visit_d15']);
  const isHomeVisit = HOME_VISIT_SESSION_IDS.has(ev.protocol_event_id);

  // Home visits: show session start/end datetime inputs; hide single date field
  dateWrap.classList.toggle('hidden', isHomeVisit);
  sessionWrap.classList.toggle('hidden', !isHomeVisit);
  document.getElementById('simple-event-session-start').value = '';
  document.getElementById('simple-event-session-end').value   = '';

  if (isHomeVisit) {
    // d02/d03: pre-fill session start with fixed visit date (activation + offset) at 09:00
    const ACTIVATION_OFFSETS = { home_visit_d02: 1, home_visit_d03: 2 };
    const offset = ACTIVATION_OFFSETS[ev.protocol_event_id];
    if (offset !== undefined && patientData?.activationDate) {
      const d = new Date(patientData.activationDate);
      d.setDate(d.getDate() + offset);
      document.getElementById('simple-event-session-start').value = d.toISOString().slice(0, 10) + 'T09:00';
    }
    _attachDateGuard('simple-event-session-start', 'simple-event-error');
    _attachSessionEndGuard('simple-event-session-start', 'simple-event-session-end', 'simple-event-error');
  } else {
    const dateInput = document.getElementById('simple-event-date');
    dateInput.value    = '';
    dateInput.readOnly = false;
    dateInput.classList.remove('bg-slate-50', 'cursor-not-allowed');
    _attachDateGuard('simple-event-date', 'simple-event-error');
  }

  showModal('simple-event-modal');
}

async function saveSimpleEvent() {
  const notes = document.getElementById('simple-event-notes').value.trim();
  const err   = document.getElementById('simple-event-error');
  err.classList.add('hidden');

  const HOME_VISIT_SESSION_IDS = new Set(['home_visit_d02', 'home_visit_d03', 'home_visit_d15']);
  let completionDate, sessionStart = null, sessionEnd = null;

  if (HOME_VISIT_SESSION_IDS.has(_simpleProtocolEventId)) {
    sessionStart = document.getElementById('simple-event-session-start').value;
    sessionEnd   = document.getElementById('simple-event-session-end').value;
    if (!sessionStart || !sessionEnd) {
      err.textContent = 'Session start and end are required.';
      err.classList.remove('hidden');
      return;
    }
    if (sessionStart.split('T')[0] !== sessionEnd.split('T')[0]) {
      err.textContent = 'Session start and end must be on the same date.';
      err.classList.remove('hidden');
      return;
    }
    if (sessionStart >= sessionEnd) {
      err.textContent = 'Session end must be after session start.';
      err.classList.remove('hidden');
      return;
    }
    completionDate = sessionStart;
  } else {
    completionDate = document.getElementById('simple-event-date').value;
    if (!completionDate) {
      err.textContent = 'Event date is required.';
      err.classList.remove('hidden');
      return;
    }
  }

  if (!_validateAttachment('simple-event', 'simple-event-error')) return;

  const res  = await fetch(`/api/patients/${PATIENT_HOMER_ID}/complete-event/simple`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({
      event_id:          _simpleEventId,
      protocol_event_id: _simpleProtocolEventId,
      completion_date:   completionDate,
      session_start:     sessionStart,
      session_end:       sessionEnd,
      notes,
    }),
  });
  const data = await res.json();
  if (!res.ok) { err.textContent = data.error || 'Failed to save.'; err.classList.remove('hidden'); return; }

  const { file, caption } = _readAttachment('simple-event');
  if (file) {
    const uploaded = await _uploadAttachment(_simpleEventId, file, caption, 'simple-event-error');
    if (!uploaded) return;
  }
  hideModal('simple-event-modal');
  await loadPatientEvents();
}

// ── Home Visit modal ───────────────────────────────────────────────────────────

let _hvEventId           = null;
let _hvProtocolEventId   = null;
let _hvTrainingCompleted = null;
let _hvNoPrimaryReason   = null;

const _HV_ACTIVATION_OFFSETS = { home_visit_d02: 1, home_visit_d03: 2 };


function _hvNoToggleSubform(type) {
  const map = {
    adverse:        'hv-no-adverse-note',
    robot:          'hv-no-robot-note',
    'other-device': 'hv-no-other-device-note',
  };
  const noteId = map[type];
  if (!noteId) return;
  const checked = document.getElementById(`hv-no-trigger-${type}`).checked;
  document.getElementById(noteId).classList.toggle('hidden', !checked);
}

function _setHvNoPrimaryReason(reason) {
  _hvNoPrimaryReason = reason;
  const pills = {
    adverse_event:           'hv-no-reason-ae',
    robot_issue_call:        'hv-no-reason-robot',
    other_device_issue_call: 'hv-no-reason-odi',
    other:                   'hv-no-reason-other',
  };
  const active   = ['bg-blue-600', 'text-white', 'border-blue-600'];
  const inactive = ['border-slate-200', 'text-slate-600'];
  Object.entries(pills).forEach(([r, id]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    const on = r === reason;
    active.forEach(c => btn.classList.toggle(c, on));
    inactive.forEach(c => btn.classList.toggle(c, !on));
  });

  const isExp = patientData?.group === 'experimental';
  // Reset secondary trigger wraps to group-based visibility, then hide primary's wrap
  const wrapVisibility = {
    'hv-no-trigger-ae-wrap':           true,
    'hv-no-trigger-robot-wrap':        isExp,
    'hv-no-trigger-other-device-wrap': isExp,
  };
  const reasonToWrap = {
    adverse_event:           'hv-no-trigger-ae-wrap',
    robot_issue_call:        'hv-no-trigger-robot-wrap',
    other_device_issue_call: 'hv-no-trigger-other-device-wrap',
  };
  Object.entries(wrapVisibility).forEach(([wrapId, groupVisible]) => {
    const wrap = document.getElementById(wrapId);
    if (!wrap) return;
    const isPrimary = reasonToWrap[reason] === wrapId;
    wrap.classList.toggle('hidden', !groupVisible || isPrimary);
    if (isPrimary || !groupVisible) {
      // Uncheck and collapse the hidden trigger
      const cbId = wrapId === 'hv-no-trigger-ae-wrap'    ? 'hv-no-trigger-adverse'
                 : wrapId === 'hv-no-trigger-robot-wrap' ? 'hv-no-trigger-robot'
                 :                                          'hv-no-trigger-other-device';
      const cb = document.getElementById(cbId);
      if (cb && cb.checked) { cb.checked = false; _hvNoToggleSubform(cbId.replace('hv-no-trigger-', '')); }
    }
  });

  // Notes label: required asterisk only for 'other'
  const notesLabel = document.getElementById('hv-no-notes-star');
  if (notesLabel) notesLabel.textContent = reason === 'other' ? '* — explain why training was not completed' : '';
  setError('hv-error', '');
}

function _setHvTrainingToggle(val) {
  _hvTrainingCompleted = val;
  const yesBtn = document.getElementById('hv-train-yes-btn');
  const noBtn  = document.getElementById('hv-train-no-btn');
  const activeClass   = ['bg-blue-600', 'text-white', 'border-blue-600'];
  const inactiveClass = ['border-slate-200', 'text-slate-600'];
  if (val === true) {
    yesBtn.classList.add(...activeClass);    yesBtn.classList.remove(...inactiveClass);
    noBtn.classList.remove(...activeClass);  noBtn.classList.add(...inactiveClass);
  } else {
    noBtn.classList.add(...activeClass);     noBtn.classList.remove(...inactiveClass);
    yesBtn.classList.remove(...activeClass); yesBtn.classList.add(...inactiveClass);
  }
  document.getElementById('hv-yes-section').classList.toggle('hidden', val !== true);
  document.getElementById('hv-no-section').classList.toggle('hidden',  val !== false);
  setError('hv-error', '');
}

function openHomeVisitModal(ev) {
  _hvEventId           = ev.id;
  _hvProtocolEventId   = ev.protocol_event_id;
  _hvTrainingCompleted = null;
  document.getElementById('hv-title').textContent = ev.event_name;
  setError('hv-error', '');

  // Reset toggle to unselected
  const activeClass   = ['bg-blue-600', 'text-white', 'border-blue-600'];
  const inactiveClass = ['border-slate-200', 'text-slate-600'];
  ['hv-train-yes-btn', 'hv-train-no-btn'].forEach(id => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.classList.remove(...activeClass);
    btn.classList.add(...inactiveClass);
  });
  document.getElementById('hv-yes-section').classList.add('hidden');
  document.getElementById('hv-no-section').classList.add('hidden');

  // ── YES section setup ──
  document.getElementById('hv-notes').value = '';
  _resetAttachment('hv');

  const offset   = _HV_ACTIVATION_OFFSETS[ev.protocol_event_id];
  const isLocked = offset !== undefined && patientData?.activationDate;
  // Attach guards first, then override min/max for locked dates (guards set max=now by default)
  _attachDateGuard('hv-session-start', 'hv-error');
  _attachSessionEndGuard('hv-session-start', 'hv-session-end', 'hv-error');

  if (isLocked) {
    // Use event's scheduled_date[0] as the authoritative locked date (from protocol_events.json)
    // Fall back to calculating from activation date if scheduled_date not available
    let lockedDate;
    if (ev.scheduled_date && ev.scheduled_date[0]) {
      lockedDate = ev.scheduled_date[0].slice(0, 10);
    } else {
      const d = new Date(patientData.activationDate);
      d.setDate(d.getDate() + offset);
      lockedDate = d.toISOString().slice(0, 10);
    }
    const dayNum = offset + 1;
    document.getElementById('hv-session-start').value = lockedDate + 'T09:00';
    document.getElementById('hv-session-end').value   = lockedDate + 'T10:00';
    document.getElementById('hv-session-start').min   = lockedDate + 'T00:00';
    document.getElementById('hv-session-start').max   = lockedDate + 'T23:59';
    document.getElementById('hv-session-end').min     = lockedDate + 'T00:00';
    document.getElementById('hv-session-end').max     = lockedDate + 'T23:59';
    document.getElementById('hv-date-lock-label').textContent = `Day ${dayNum} (${lockedDate})`;
    document.getElementById('hv-date-lock-note').classList.remove('hidden');
  } else {
    document.getElementById('hv-session-start').value = '';
    document.getElementById('hv-session-end').value   = '';
    document.getElementById('hv-session-start').min   = '';
    document.getElementById('hv-session-start').max   = '';
    document.getElementById('hv-session-end').min     = '';
    document.getElementById('hv-session-end').max     = '';
    document.getElementById('hv-date-lock-note').classList.add('hidden');
  }

  // Outcome group visibility (group, watch-assigned, training-ended cutoff)
  // is centralised in _outcomeReset → _applyOutcomeVisibility.
  _outcomeReset('hv');

  // ── NO section setup ──
  _hvNoPrimaryReason = null;
  document.getElementById('hv-no-notes').value      = '';
  document.getElementById('hv-no-visit-date').value = '';
  _resetAttachment('hv-no');
  _attachDateGuard('hv-no-visit-date', 'hv-error');

  const isD0203 = ev.protocol_event_id === 'home_visit_d02' || ev.protocol_event_id === 'home_visit_d03';
  document.getElementById('hv-no-broken-protocol-warn').classList.toggle('hidden', !isD0203);

  // Reset primary reason pills
  const isExp = patientData?.group === 'experimental';
  const pillActive   = ['bg-blue-600', 'text-white', 'border-blue-600'];
  const pillInactive = ['border-slate-200', 'text-slate-600'];
  ['hv-no-reason-ae', 'hv-no-reason-robot', 'hv-no-reason-odi', 'hv-no-reason-other'].forEach(id => {
    const btn = document.getElementById(id);
    if (!btn) return;
    btn.classList.remove(...pillActive);
    btn.classList.add(...pillInactive);
  });
  document.getElementById('hv-no-reason-robot').classList.toggle('hidden', !isExp);
  document.getElementById('hv-no-reason-odi').classList.toggle('hidden', !isExp);
  const notesLabel = document.getElementById('hv-no-notes-star');
  if (notesLabel) notesLabel.textContent = '';

  // Reset secondary triggers
  ['adverse', 'robot', 'other-device'].forEach(type => {
    const cb = document.getElementById(`hv-no-trigger-${type}`);
    if (cb) { cb.checked = false; _hvNoToggleSubform(type); }
  });
  document.getElementById('hv-no-trigger-ae-wrap').classList.remove('hidden');
  document.getElementById('hv-no-trigger-robot-wrap').classList.toggle('hidden', !isExp);
  document.getElementById('hv-no-trigger-other-device-wrap').classList.toggle('hidden', !isExp);

  showModal('home-visit-modal');
}

async function saveHomeVisit() {
  if (_hvTrainingCompleted === null) {
    setError('hv-error', 'Please indicate whether training was completed.');
    return;
  }
  if (_hvTrainingCompleted) {
    await _saveHomeVisitYes();
  } else {
    await _saveHomeVisitNo();
  }
}

async function _saveHomeVisitYes() {
  if (_hasDateValidationErrors(['hv-error'])) {
    setError('hv-error', 'Please fix the date validation errors before submitting.');
    return;
  }

  const sessionStart = document.getElementById('hv-session-start').value;
  const sessionEnd   = document.getElementById('hv-session-end').value;
  const notes        = document.getElementById('hv-notes').value.trim();
  const saveBtn      = document.getElementById('hv-save');

  if (!sessionStart || !sessionEnd) { setError('hv-error', 'Session start and end are required.'); return; }
  if (sessionStart.split('T')[0] !== sessionEnd.split('T')[0]) { setError('hv-error', 'Session start and end must be on the same date.'); return; }
  if (sessionStart >= sessionEnd) { setError('hv-error', 'Session end must be after session start.'); return; }
  if (!_validateAttachment('hv', 'hv-error')) return;

  const outcomeErrHv = _outcomeError('hv');
  if (outcomeErrHv) { setError('hv-error', outcomeErrHv); return; }
  const { no_issue: noIssueHv, triggered } = _outcomeRead('hv');

  saveBtn.disabled = true;
  const { ok, data } = await apiPost(`/api/patients/${PATIENT_HOMER_ID}/complete-event/home-visit`, {
    event_id:          _hvEventId,
    protocol_event_id: _hvProtocolEventId,
    session_start:     sessionStart,
    session_end:       sessionEnd,
    notes,
    no_issue:          noIssueHv,
    triggered,
  });
  if (!ok) { setError('hv-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }

  const { file, caption } = _readAttachment('hv');
  if (file) {
    const uploaded = await _uploadAttachment(_hvEventId, file, caption, 'hv-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  hideModal('home-visit-modal');
  saveBtn.disabled = false;
  await loadPatientEvents();
}

async function _saveHomeVisitNo() {
  const visitDate = document.getElementById('hv-no-visit-date').value;
  const notes     = document.getElementById('hv-no-notes').value.trim();
  const saveBtn   = document.getElementById('hv-save');

  if (!_hvNoPrimaryReason) { setError('hv-error', 'Please select a reason why training was not completed.'); return; }
  if (!visitDate) { setError('hv-error', 'Visit date is required.'); return; }
  if (new Date(visitDate) > new Date()) { setError('hv-error', 'Visit date cannot be in the future.'); return; }
  if (_hvNoPrimaryReason === 'other' && !notes) { setError('hv-error', 'Notes are required when reason is "Other".'); return; }
  if (!_validateAttachment('hv-no', 'hv-error')) return;

  // Build triggered list: primary reason first (with training_stopped flag), then secondary triggers
  const triggered = [];
  if (_hvNoPrimaryReason !== 'other') {
    triggered.push({ type: _hvNoPrimaryReason, training_stopped: true });
  }
  if (_hvNoPrimaryReason !== 'adverse_event' &&
      document.getElementById('hv-no-trigger-adverse').checked)
    triggered.push({ type: 'adverse_event' });
  if (_hvNoPrimaryReason !== 'robot_issue_call' &&
      !document.getElementById('hv-no-trigger-robot-wrap').classList.contains('hidden') &&
      document.getElementById('hv-no-trigger-robot').checked)
    triggered.push({ type: 'robot_issue_call' });
  if (_hvNoPrimaryReason !== 'other_device_issue_call' &&
      !document.getElementById('hv-no-trigger-other-device-wrap').classList.contains('hidden') &&
      document.getElementById('hv-no-trigger-other-device').checked)
    triggered.push({ type: 'other_device_issue_call' });

  const isD0203 = _hvProtocolEventId === 'home_visit_d02' || _hvProtocolEventId === 'home_visit_d03';
  let confirmedBrokenProtocol = false;
  if (isD0203) {
    const dayLabel = _hvProtocolEventId === 'home_visit_d02' ? 'Day 2' : 'Day 3';
    if (!window.confirm(`Training was not completed on ${dayLabel}. This will mark the patient as BROKEN PROTOCOL. Continue?`)) return;
    if (!window.confirm('Are you sure? This action cannot be undone. The patient will be marked as broken protocol.')) return;
    confirmedBrokenProtocol = true;
  }

  saveBtn.disabled = true;
  const { ok, data } = await apiPost(`/api/patients/${PATIENT_HOMER_ID}/complete-event/home-visit`, {
    event_id:                  _hvEventId,
    protocol_event_id:         _hvProtocolEventId,
    training_not_done:         true,
    primary_reason:            _hvNoPrimaryReason,
    visit_date:                visitDate,
    notes,
    triggered,
    confirmed_broken_protocol: confirmedBrokenProtocol,
  });
  if (!ok) { setError('hv-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }

  const { file, caption } = _readAttachment('hv-no');
  if (file) {
    const uploadId = (_hvProtocolEventId === 'home_visit_d15') ? data.attempt_id : _hvEventId;
    const uploaded = await _uploadAttachment(uploadId, file, caption, 'hv-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  hideModal('home-visit-modal');
  saveBtn.disabled = false;
  await loadPatientEvents();
}

// ── Follow-up Call modal ───────────────────────────────────────────────────────

let _followupCallEventId         = null;
let _followupCallProtocolEventId = null;
let _followupCallScheduledDate   = null;

function _followupCallCheckDateChange() {
  const dateVal     = document.getElementById('followup-call-date').value;
  const reasonWrap  = document.getElementById('followup-call-date-reason-wrap');
  const reasonInput = document.getElementById('followup-call-date-reason');
  const isDifferent = dateVal && _followupCallScheduledDate && dateVal.slice(0, 10) !== _followupCallScheduledDate;
  if (isDifferent) {
    reasonWrap.classList.remove('hidden');
  } else {
    reasonWrap.classList.add('hidden');
    reasonInput.value = '';
  }
}

function _fcSelectAeDiscussed(discussed) {
  document.getElementById('fc-ae-discussed').value = discussed ? 'yes' : 'no';
  _fcStyleAeBtn(discussed);
}

function _fcStyleAeBtn(discussed) {
  const yes = document.getElementById('fc-ae-yes-btn');
  const no  = document.getElementById('fc-ae-no-btn');
  if (!yes || !no) return;
  const base     = 'flex-1 px-3 py-2 border rounded-xl text-sm font-medium transition-colors';
  const active   = 'bg-amber-600 border-amber-600 text-white';
  const inactive = 'bg-slate-50 border-slate-200 text-slate-600 hover:bg-slate-100';
  yes.className = `${base} ${discussed === true  ? active : inactive}`;
  no.className  = `${base} ${discussed === false ? active : inactive}`;
}

function openFollowupCallModal(ev) {
  _followupCallEventId         = ev.id;
  _followupCallProtocolEventId = ev.protocol_event_id;
  _followupCallScheduledDate   = ev.scheduled_date ? ev.scheduled_date[0].slice(0, 10) : null;

  document.getElementById('followup-call-title').textContent             = ev.event_name;
  // Set data-event-id dynamically so the Date Rule Framework picks up the
  // d07-vs-d21-specific bounds (event:home_visit_d03 / event:followup_call_d07
  // lower; activationDate + 19d / + 26d upper). Read by _applyDateBounds
  // when showModal() fires below.
  document.getElementById('followup-call-date').dataset.eventId          = ev.protocol_event_id || '';
  document.getElementById('followup-call-date').value                    = '';
  document.getElementById('followup-call-duration').value                = '';
  document.querySelectorAll('input[name="fc-call-mode"]').forEach(r => { r.checked = false; });
  document.getElementById('followup-call-notes').value                   = '';
  _resetAttachment('followup-call');
  document.getElementById('followup-call-date-reason').value             = '';
  document.getElementById('followup-call-date-reason-wrap').classList.add('hidden');
  document.getElementById('followup-call-scheduled-display').textContent = _followupCallScheduledDate || '';
  document.getElementById('followup-call-date').addEventListener('change', _followupCallCheckDateChange, { once: false });

  // Outcome group visibility (group, watch-assigned, training-ended cutoff)
  // is centralised in _outcomeReset → _applyOutcomeVisibility.
  _outcomeReset('fc');

  // Show AE discussion section only when an adverse_event_followup stub exists.
  const hasAefStubFc = eventsCache.some(e => e.protocol_event_id === 'adverse_event_followup');
  const fcAeSect = document.getElementById('fc-ae-section');
  if (fcAeSect) fcAeSect.classList.toggle('hidden', !hasAefStubFc);
  document.getElementById('fc-ae-discussed').value = '';
  _fcStyleAeBtn(null);

  const err = document.getElementById('followup-call-error');
  err.textContent = '';
  err.classList.add('hidden');
  _attachDateGuard('followup-call-date', 'followup-call-error');
  showModal('followup-call-modal');
}

async function saveFollowupCall() {
  const dateVal    = document.getElementById('followup-call-date').value;
  const duration   = document.getElementById('followup-call-duration').value.trim();
  const notes      = document.getElementById('followup-call-notes').value.trim();
  const reasonWrap = document.getElementById('followup-call-date-reason-wrap');
  const dateReason = document.getElementById('followup-call-date-reason').value.trim();
  const err        = document.getElementById('followup-call-error');
  const saveBtn    = document.getElementById('followup-call-save');
  err.classList.add('hidden');

  const dateChanged = !reasonWrap.classList.contains('hidden');
  const callMode    = document.querySelector('input[name="fc-call-mode"]:checked')?.value || '';

  if (!dateVal)                            { err.textContent = 'Call date is required.';                    err.classList.remove('hidden'); return; }
  if (!duration || parseInt(duration) < 1) { err.textContent = 'Duration must be at least 1 minute.';       err.classList.remove('hidden'); return; }
  if (!callMode)                           { err.textContent = 'Call mode (Audio / Video) is required.';    err.classList.remove('hidden'); return; }
  if (dateChanged && !dateReason)          { err.textContent = 'Please explain why the date is different.'; err.classList.remove('hidden'); return; }
  if (!notes)                              { err.textContent = 'Notes are required.';                       err.classList.remove('hidden'); return; }
  if (!_validateAttachment('followup-call', 'followup-call-error')) return;

  const fcAeSectVisible = !document.getElementById('fc-ae-section')?.classList.contains('hidden');
  const fcAeDiscussed   = document.getElementById('fc-ae-discussed').value;
  if (fcAeSectVisible && !fcAeDiscussed) {
    err.textContent = 'Please indicate whether any AE-related discussion happened during this call.';
    err.classList.remove('hidden');
    return;
  }

  const outcomeErr = _outcomeError('fc');
  if (outcomeErr) { err.textContent = outcomeErr; err.classList.remove('hidden'); return; }
  const { no_issue: noIssueFc, triggered } = _outcomeRead('fc');

  const body = {
    event_id:          _followupCallEventId,
    protocol_event_id: _followupCallProtocolEventId,
    completion_date:   dateVal,
    duration_minutes:  parseInt(duration),
    call_mode:         callMode,
    notes,
    no_issue:          noIssueFc,
    triggered,
    ...(dateChanged ? { date_change_reason: dateReason } : {}),
  };

  saveBtn.disabled = true;
  const { ok, data } = await apiPost(`/api/patients/${PATIENT_HOMER_ID}/complete-event/followup-call`, body);
  if (!ok) {
    saveBtn.disabled = false;
    err.textContent = data.error || 'Failed to save.';
    err.classList.remove('hidden');
    return;
  }

  const { file, caption } = _readAttachment('followup-call');
  if (file) {
    const uploaded = await _uploadAttachment(_followupCallEventId, file, caption, 'followup-call-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  saveBtn.disabled = false;
  hideModal('followup-call-modal');
  await loadPatientEvents();
  if (fcAeDiscussed === 'yes') {
    const aefStub = eventsCache.find(e => e.protocol_event_id === 'adverse_event_followup');
    if (aefStub) {
      // AE discussion happened during this D07/D21 call — lock the AE follow-up
      // date to the parent call's completion date and pre-fill duration.
      const label = _followupCallProtocolEventId === 'followup_call_d07' ? 'Day 07 follow-up call'
                  : _followupCallProtocolEventId === 'followup_call_d21' ? 'Day 21 follow-up call'
                  : 'follow-up call';
      openAdverseEventFollowupModal(aefStub, { date: dateVal, duration, label });
    }
  }
}

// ── Outcome group ("What came out of this …?") — shared by patient_call,
// followup_call, activation, home_visit modals ────────────────────────────────
//
// Each modal that uses the outcome group has five toggles with a shared naming
// convention: `{prefix}-trigger-no-issue` plus four issue toggles
// `{prefix}-trigger-{adverse|robot|watch|other-device}`. Per-toggle info notes
// are at `{prefix}-{type}-note`. Visibility wraps are at
// `{prefix}-trigger-{type}-wrap` (used to hide group/feature-specific toggles —
// e.g. robot/other-device are hidden for control patients). The four prefixes:
//   'pc'  → patient_call modal
//   'fc'  → followup_call modal
//   'act' → activation modal (YES path)
//   'hv'  → home_visit modal (YES path)
//
// Convention: "No issue" is mutually exclusive with the four issue toggles.
// Checking one side disables and dims the other. Save is gated on either
// "No issue" or at least one issue toggle being checked. See CLAUDE.md →
// "Outcome group convention".

const _OUTCOME_ISSUE_TYPES = ['adverse', 'robot', 'watch', 'other-device'];

const _OUTCOME_TRIGGER_API_TYPES = {
  adverse:        'adverse_event',
  robot:          'robot_issue_call',
  watch:          'watch_record',
  'other-device': 'other_device_issue_call',
};

// Show/hide the inline info note for an issue toggle.
function _outcomeUpdateNote(prefix, type) {
  const note = document.getElementById(`${prefix}-${type}-note`);
  if (!note) return;
  const cb = document.getElementById(`${prefix}-trigger-${type}`);
  note.classList.toggle('hidden', !cb?.checked);
}

// Mutual-exclusion driver. Called by each toggle's onchange handler with the
// type of the changed toggle (so we can update its info note), or with no
// argument when called from a reset / initial render.
function _outcomeChange(prefix, changedType) {
  if (changedType) _outcomeUpdateNote(prefix, changedType);

  const noIssueCb   = document.getElementById(`${prefix}-trigger-no-issue`);
  if (!noIssueCb) return;
  const noIssueNote = document.getElementById(`${prefix}-no-issue-note`);

  const anyIssueChecked = _OUTCOME_ISSUE_TYPES.some(t => {
    const cb = document.getElementById(`${prefix}-trigger-${t}`);
    return cb && cb.checked;
  });

  if (noIssueNote) noIssueNote.classList.toggle('hidden', !noIssueCb.checked);

  noIssueCb.disabled = anyIssueChecked;
  _OUTCOME_ISSUE_TYPES.forEach(t => {
    const cb = document.getElementById(`${prefix}-trigger-${t}`);
    if (!cb) return;
    cb.disabled = noIssueCb.checked;
    const label = cb.closest('label');
    if (label) label.classList.toggle('opacity-50', cb.disabled);
  });
  const noIssueLabel = noIssueCb.closest('label');
  if (noIssueLabel) noIssueLabel.classList.toggle('opacity-50', noIssueCb.disabled);

  // Quality-of-life: if the user just made the outcome valid by selecting
  // something, clear the stale "Please indicate what came out of this..."
  // message so the error display matches the new state. Only clear when the
  // current message is an outcome-group error — avoids wiping unrelated
  // messages from other validators.
  if (changedType !== undefined && (noIssueCb.checked || anyIssueChecked)) {
    const modal = noIssueCb.closest('[id$="-modal"]');
    const errId = modal && modal.dataset.dateError;
    const errEl = errId && document.getElementById(errId);
    if (errEl && errEl.textContent.includes('came out of this')) {
      setError(errId, '');
    }
  }
}

// Single source of truth for which issue toggles are hidden, per the current
// patient state. Returns Map<type, hidden:bool>. Rules in one place rather
// than duplicated across four modal openers:
//   - adverse:      hidden when training has permanently ended (any path)
//   - robot:        hidden for control patients OR training ended
//   - watch:        hidden when no watch is currently assigned OR training ended
//   - other-device: hidden for control patients OR training ended
// See CLAUDE.md → "Trigger toggle visibility cutoff".
function _outcomeIssueVisibility() {
  const p        = patientData || {};
  const isExp    = p.group === 'experimental';
  const hasWatch = !!(p.agWatchRightID || p.agWatchLeftID);
  const ended    = _trainingPermanentlyEnded();
  return {
    'adverse':       ended,
    'robot':         !isExp || ended,
    'watch':         !hasWatch || ended,
    'other-device':  !isExp || ended,
  };
}

// Apply per-toggle visibility to the wrap elements. Each issue toggle has a
// wrap element with id `{prefix}-trigger-{type}-wrap`; if any wrap is missing
// in the template the rule is silently skipped (no DOM error).
//
// When every issue toggle is hidden (training has permanently ended), the
// entire outcome group `{prefix}-outcome-group` is hidden and the sibling
// note `{prefix}-outcome-ended-note` is shown in its place. Required-selection
// is then satisfied automatically by `_outcomeRead` (returns no_issue: true);
// no user click needed since there's no meaningful choice to make.
function _applyOutcomeVisibility(prefix) {
  const vis = _outcomeIssueVisibility();
  for (const t of _OUTCOME_ISSUE_TYPES) {
    const wrap = document.getElementById(`${prefix}-trigger-${t}-wrap`);
    if (wrap) wrap.classList.toggle('hidden', !!vis[t]);
  }
  const allHidden = _OUTCOME_ISSUE_TYPES.every(t => !!vis[t]);
  const groupEl = document.getElementById(`${prefix}-outcome-group`);
  const noteEl  = document.getElementById(`${prefix}-outcome-ended-note`);
  if (groupEl) groupEl.classList.toggle('hidden', allHidden);
  if (noteEl)  noteEl.classList.toggle('hidden', !allHidden);
}

// Reset every toggle in the outcome group to unchecked, apply visibility
// rules, and refresh notes + disabled/dimmed state. Called by each modal's
// opener — the opener doesn't need to know any of the per-toggle visibility
// rules, they're all centralised here.
function _outcomeReset(prefix) {
  const noIssueCb = document.getElementById(`${prefix}-trigger-no-issue`);
  if (noIssueCb) noIssueCb.checked = false;
  _OUTCOME_ISSUE_TYPES.forEach(t => {
    const cb = document.getElementById(`${prefix}-trigger-${t}`);
    if (cb) cb.checked = false;
    _outcomeUpdateNote(prefix, t);
  });
  _applyOutcomeVisibility(prefix);
  _outcomeChange(prefix);
}

// Read the outcome group's current state. Returns { no_issue, triggered }.
// Toggles whose visibility wrap (`{prefix}-trigger-{type}-wrap`) is hidden are
// treated as unchecked, so non-experimental patients don't accidentally send
// robot/other-device triggers even if the checkbox state survived a re-open.
//
// When the entire outcome group is hidden (training permanently ended — every
// issue toggle is unavailable), auto-confirms `{no_issue: true, triggered: []}`
// regardless of checkbox state. The user is not asked to click the only
// remaining option; the system records the outcome on their behalf.
function _outcomeRead(prefix) {
  const groupEl = document.getElementById(`${prefix}-outcome-group`);
  if (groupEl && groupEl.classList.contains('hidden')) {
    return { no_issue: true, triggered: [] };
  }
  const noIssue = !!document.getElementById(`${prefix}-trigger-no-issue`)?.checked;
  const triggered = [];
  for (const t of _OUTCOME_ISSUE_TYPES) {
    const wrap = document.getElementById(`${prefix}-trigger-${t}-wrap`);
    if (wrap && wrap.classList.contains('hidden')) continue;
    const cb = document.getElementById(`${prefix}-trigger-${t}`);
    if (cb?.checked) triggered.push({ type: _OUTCOME_TRIGGER_API_TYPES[t] });
  }
  return { no_issue: noIssue, triggered };
}

// Returns an error string when the outcome selection is invalid (neither side
// picked), else null. UI also disables the opposite side once one is selected,
// but this is the defensive gate before submit.
function _outcomeError(prefix) {
  const { no_issue, triggered } = _outcomeRead(prefix);
  if (!no_issue && triggered.length === 0) {
    return 'Please indicate what came out of this (select "No issue" or one of the issue types).';
  }
  return null;
}

// ── Patient Call modal ────────────────────────────────────────────────────────

function _pcToggleTherapistInitiated() {
  const checked = document.getElementById('pc-therapist-initiated').checked;
  document.getElementById('pc-reason-wrap').classList.toggle('hidden', !checked);
}

function openPatientCallModal() {
  document.getElementById('pc-date').value     = '';
  document.getElementById('pc-duration').value = '';
  document.getElementById('pc-notes').value    = '';
  document.querySelectorAll('input[name="pc-call-mode"]').forEach(r => { r.checked = false; });
  document.getElementById('pc-therapist-initiated').checked = false;
  document.getElementById('pc-reason-wrap').classList.add('hidden');
  document.getElementById('pc-reason').value = '';
  _resetAttachment('pc');

  // Outcome group visibility (group, watch-assigned, training-ended cutoff)
  // is centralised in _outcomeReset → _applyOutcomeVisibility.
  _outcomeReset('pc');

  setError('pc-error', '');
  _attachDateGuard('pc-date', 'pc-error');
  showModal('patient-call-modal');
}

async function savePatientCall() {
  const dateVal  = document.getElementById('pc-date').value;
  const duration = document.getElementById('pc-duration').value.trim();
  const notes    = document.getElementById('pc-notes').value.trim();
  const saveBtn  = document.getElementById('pc-save');

  const callMode = document.querySelector('input[name="pc-call-mode"]:checked')?.value || '';

  if (!dateVal)                            { setError('pc-error', 'Call date is required.'); return; }
  if (!duration || parseInt(duration) < 1) { setError('pc-error', 'Duration must be at least 1 minute.'); return; }
  if (!callMode)                           { setError('pc-error', 'Call mode (Audio / Video) is required.'); return; }
  if (!notes)                              { setError('pc-error', 'Notes are required.'); return; }
  if (!_validateAttachment('pc', 'pc-error')) return;

  const outcomeErr = _outcomeError('pc');
  if (outcomeErr) { setError('pc-error', outcomeErr); return; }
  const { no_issue: noIssue, triggered } = _outcomeRead('pc');

  const therapistInitiated = document.getElementById('pc-therapist-initiated').checked;
  const reason = document.getElementById('pc-reason').value.trim();
  if (therapistInitiated && !reason) { setError('pc-error', 'Reason is required for therapist-initiated calls.'); return; }

  const call_type = therapistInitiated ? 'therapist_initiated' : 'patient_initiated';

  saveBtn.disabled = true;
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/log-patient-call`,
    { completion_date: dateVal, duration_minutes: parseInt(duration), notes, triggered, no_issue: noIssue,
      call_type, call_mode: callMode, reason: therapistInitiated ? reason : undefined }
  );
  if (!ok) { setError('pc-error', data.error || 'Failed to save.'); saveBtn.disabled = false; return; }

  const { file, caption } = _readAttachment('pc');
  if (file) {
    const uploaded = await _uploadAttachment(data.id, file, caption, 'pc-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  saveBtn.disabled = false;
  hideModal('patient-call-modal');

  // Update cache and re-render immediately without re-fetching
  const newCall = {
    id: data.id,
    completion_date: dateVal,
    duration_minutes: parseInt(duration),
    notes,
    call_type,
    reason: therapistInitiated ? reason : undefined,
    attachment: data.attachment,
    attachment_caption: data.attachment_caption,
  };

  if (!_callLogsCache) _callLogsCache = { patient_calls: [], followup_calls: [] };
  if (!_callLogsCache.patient_calls) _callLogsCache.patient_calls = [];
  _callLogsCache.patient_calls.push(newCall);

  const container = document.getElementById('call-logs-content');
  if (container) _renderCallLogs(container, _callLogsCache);

  await loadPatientEvents();
}

// ── Watch Record modal ────────────────────────────────────────────────────────

const _WR_TRIGGER_NAMES = {
  activation:        'Patient Activation',
  home_visit_d02:    'Home Visit Day 02',
  home_visit_d03:    'Home Visit Day 03',
  home_visit_d15:    'Home Visit Day 15',
  followup_call_d07: 'Follow-up Call Day 07',
  followup_call_d21: 'Follow-up Call Day 21',
  patient_call:      'Patient Call',
};

let _wrEventId  = null;
let _wrOldRight = null;
let _wrOldLeft  = null;

async function openWatchRecordModal(ev) {
  _wrEventId = ev.id;

  // Context banner
  const banner = document.getElementById('wr-context-banner');
  if (ev.triggered_by) {
    const label = _WR_TRIGGER_NAMES[ev.triggered_by.type] || ev.triggered_by.type;
    banner.textContent = `Triggered by: ${label}`;
    banner.className = 'px-4 py-2 rounded-xl text-sm font-medium bg-blue-50 text-blue-700 border border-blue-100';
  } else {
    banner.textContent = 'Scheduled chain follow-up';
    banner.className = 'px-4 py-2 rounded-xl text-sm font-medium bg-slate-50 text-slate-600 border border-slate-200';
  }

  // Current watches + Lost checkboxes
  _wrOldRight = patientData?.agWatchRightID || null;
  _wrOldLeft  = patientData?.agWatchLeftID  || null;
  // Initial assignment (activation): neither watch exists yet — treat as two-watch.
  const bothNull   = !_wrOldRight && !_wrOldLeft;
  const twoWatches = !!(_wrOldRight && _wrOldLeft) || bothNull;
  const showRight  = !!_wrOldRight || bothNull;
  const showLeft   = !!_wrOldLeft  || bothNull;

  document.getElementById('wr-old-right').textContent = _wrOldRight || '';
  document.getElementById('wr-old-left').textContent  = _wrOldLeft  || '';
  document.getElementById('wr-right-lost-wrap').classList.toggle('hidden', !_wrOldRight);
  document.getElementById('wr-left-lost-wrap').classList.toggle('hidden',  !_wrOldLeft);
  document.getElementById('wr-no-watches-msg').classList.toggle('hidden',  !bothNull);
  document.getElementById('wr-right-lost').checked = false;
  document.getElementById('wr-left-lost').checked  = false;

  // Show/hide selectors and sync based on watch count
  document.getElementById('wr-right-current-row').classList.toggle('hidden', !_wrOldRight);
  document.getElementById('wr-left-current-row').classList.toggle('hidden',  !_wrOldLeft);
  document.getElementById('wr-right-wrap').classList.toggle('hidden', !showRight);
  document.getElementById('wr-left-wrap').classList.toggle('hidden',  !showLeft);
  document.getElementById('wr-sync-wrap').classList.toggle('hidden',  !twoWatches);

  // Reset fields
  document.getElementById('wr-new-right').innerHTML  = '<option value="">Loading…</option>';
  document.getElementById('wr-new-left').innerHTML   = '<option value="">Loading…</option>';
  document.getElementById('wr-sync-datetime').value  = '';
  document.getElementById('wr-worn-datetime').value  = '';
  document.getElementById('wr-next-days').value      = '';
  document.getElementById('wr-notes').value          = '';
  _resetAttachment('wr');
  setError('wr-error', '');

  _attachDateGuard('wr-sync-datetime', 'wr-error');
  _attachDateGuard('wr-worn-datetime', 'wr-error');

  showModal('watch-record-modal');

  try {
    const res = await fetch(`/api/patients/${PATIENT_HOMER_ID}/available-agwatches`);
    const { agwatch, current_right, current_left } = await res.json();
    const NO_WATCH_VAL = '__none__';
    const NO_WATCH_OPT = `<option value="${NO_WATCH_VAL}">No Watch Available</option>`;

    const rightSel    = document.getElementById('wr-new-right');
    const leftSel     = document.getElementById('wr-new-left');
    const syncInput   = document.getElementById('wr-sync-datetime');
    const wornInput   = document.getElementById('wr-worn-datetime');
    const rightLostCb = document.getElementById('wr-right-lost');
    const leftLostCb  = document.getElementById('wr-left-lost');

    // True if any watch is being marked lost — overrides the right-as-reference lock.
    function anyLost() {
      return (rightLostCb.checked && !!_wrOldRight) ||
             (leftLostCb.checked  && !!_wrOldLeft);
    }

    // Sync/worn disabled only when both watches are kept as current (and none lost).
    function updateDatetimeFields() {
      const bothCurrent = !anyLost() && twoWatches &&
        current_right && rightSel.value === current_right.id &&
        current_left  && leftSel.value  === current_left.id;
      const syncRequired = twoWatches && !bothCurrent;
      const wornRequired = !bothCurrent;
      syncInput.disabled = !syncRequired;
      wornInput.disabled = !wornRequired;
      if (!syncRequired) syncInput.value = '';
      if (!wornRequired) wornInput.value = '';
    }

    // Right options: current option excluded if right is lost (can't keep a lost watch).
    function buildRightOpts() {
      const rightLost  = rightLostCb.checked && !!current_right;
      const currentOpt = (current_right && !rightLost)
        ? `<option value="${current_right.id}">${current_right.id} (${current_right.serial}) — current</option>`
        : '';
      return '<option value="">Select watch…</option>' +
        currentOpt +
        agwatch.map(d => `<option value="${d.id}">${d.id} (${d.serial})</option>`).join('') +
        NO_WATCH_OPT;
    }

    // Left options:
    //   anyLost OR right ≠ current → new mode (pool + NO_WATCH, no current option, left unlocked)
    //   right = current AND no lost → left auto-locks to current (disabled)
    function updateLeftOpts() {
      const rightIsCurrent = !anyLost() && current_right && rightSel.value === current_right.id;
      if (rightIsCurrent) {
        leftSel.innerHTML = current_left
          ? `<option value="${current_left.id}">${current_left.id} (${current_left.serial}) — current</option>`
          : '<option value="">No current watch</option>';
        if (current_left) leftSel.value = current_left.id;
        leftSel.disabled = true;
      } else {
        leftSel.disabled = false;
        const excludeId = (rightSel.value && rightSel.value !== NO_WATCH_VAL) ? rightSel.value : null;
        const pool = agwatch.filter(d => d.id !== excludeId);
        leftSel.innerHTML = '<option value="">Select watch…</option>' +
          pool.map(d => `<option value="${d.id}">${d.id} (${d.serial})</option>`).join('') +
          NO_WATCH_OPT;
      }
      updateDatetimeFields();
    }

    // Rebuild right options (lost state may add/remove the current option) then update left.
    function updateAll() {
      const prev = rightSel.value;
      rightSel.innerHTML = buildRightOpts();
      if (prev && [...rightSel.options].some(o => o.value === prev)) rightSel.value = prev;
      updateLeftOpts();
    }

    rightSel.innerHTML = buildRightOpts();
    updateLeftOpts();   // initialise left based on right's default (empty → new mode)

    rightSel.onchange    = () => updateLeftOpts();
    rightLostCb.onchange = () => updateAll();
    leftLostCb.onchange  = () => updateAll();
  } catch (e) {
    setError('wr-error', 'Failed to load available watches.');
  }
}

async function saveWatchRecord() {
  const newRight = document.getElementById('wr-new-right').value;
  const newLeft  = document.getElementById('wr-new-left').value;
  const syncDt   = document.getElementById('wr-sync-datetime').value;
  const wornDt   = document.getElementById('wr-worn-datetime').value;
  const nextDays = document.getElementById('wr-next-days').value;
  const notes    = document.getElementById('wr-notes').value.trim();
  const NO_WATCH   = '__none__';
  const bothNull   = !_wrOldRight && !_wrOldLeft;
  const twoWatches = !!(_wrOldRight && _wrOldLeft) || bothNull;
  const showRight  = !!_wrOldRight || bothNull;
  const showLeft   = !!_wrOldLeft  || bothNull;

  if (showRight && !newRight) { setError('wr-error', 'Please select a right watch or "No Watch Available".'); return; }
  if (showLeft  && !newLeft)  { setError('wr-error', 'Please select a left watch or "No Watch Available".'); return; }
  if (twoWatches && newRight !== NO_WATCH && newRight === newLeft) {
    setError('wr-error', 'Right and left watches must be different.'); return;
  }

  const rightLost = (document.getElementById('wr-right-lost')?.checked && !!_wrOldRight) || false;
  const leftLost  = (document.getElementById('wr-left-lost')?.checked  && !!_wrOldLeft)  || false;
  const anyLost   = rightLost || leftLost;

  // Determine whether either watch is changing vs being kept as-is
  const bothCurrent = !bothNull && twoWatches && !anyLost && newRight === _wrOldRight && newLeft === _wrOldLeft;
  const syncRequired = twoWatches && !bothCurrent;
  const wornRequired = !bothCurrent;

  if (syncRequired && !syncDt) { setError('wr-error', 'Sync date & time is required when watches are changed.'); return; }
  if (wornRequired && !wornDt) { setError('wr-error', 'Worn date & time is required.'); return; }
  if (!nextDays || parseInt(nextDays) < 1) { setError('wr-error', 'Next follow-up days must be at least 1.'); return; }
  const rightNoWatch = showRight && newRight === NO_WATCH;
  const leftNoWatch  = showLeft  && newLeft  === NO_WATCH;
  if ((rightNoWatch || leftNoWatch) && !notes) {
    setError('wr-error', 'Notes are required when a watch is not assigned — explain why.'); return;
  }
  if (!_validateAttachment('wr', 'wr-error')) return;

  // Resolve final watch IDs (null for unshown limbs or "No Watch Available")
  const finalRight = showRight ? (newRight === NO_WATCH ? null : newRight) : null;
  const finalLeft  = showLeft  ? (newLeft  === NO_WATCH ? null : newLeft)  : null;

  const saveBtn = document.getElementById('wr-save');
  const body = {
    event_id:                 _wrEventId,
    ag_watch_right_new:       finalRight,
    ag_watch_left_new:        finalLeft,
    ag_watch_right_old_lost:  rightLost,
    ag_watch_left_old_lost:   leftLost,
    sync_datetime:            syncDt,
    worn_datetime:            wornDt,
    next_followup_days:       parseInt(nextDays),
    notes,
  };

  saveBtn.disabled = true;
  const { ok, data } = await apiPost(`/api/patients/${PATIENT_HOMER_ID}/complete-event/watch-record`, body);
  if (!ok) {
    saveBtn.disabled = false;
    setError('wr-error', data.error || 'Failed to save.');
    return;
  }

  const { file: wrFile, caption: wrCaption } = _readAttachment('wr');
  if (wrFile) {
    const uploaded = await _uploadAttachment(_wrEventId, wrFile, wrCaption, 'wr-error');
    if (!uploaded) { saveBtn.disabled = false; return; }
  }

  saveBtn.disabled = false;
  hideModal('watch-record-modal');
  await loadPatient();
  loadPatientEvents();
}

// ── AG Watch Data Upload modal ─────────────────────────────────────────────────

let _wduEventId         = null;
let _wduUploaded        = false;  // true once the .gt3x has fully uploaded (staged on server)
let _wduOriginalFilename = null;
let _wduXhr             = null;   // in-flight upload, so a re-selection can abort it

function openWatchDataUploadModal(ev) {
  _wduEventId          = ev.id;
  _wduUploaded         = false;
  _wduOriginalFilename = null;
  if (_wduXhr) { try { _wduXhr.abort(); } catch {} _wduXhr = null; }

  // Context banner — watch id, limb, removed date, expected data range (read-only)
  const limb      = ev.limb ? ev.limb.charAt(0).toUpperCase() + ev.limb.slice(1) : '—';
  const removed   = ev.removed_date ? _fmtDateTime(ev.removed_date) : '—';
  const rangeFrom = ev.data_start ? _fmtDateTime(ev.data_start) : '—';
  const rangeTo   = ev.data_end   ? _fmtDateTime(ev.data_end)   : '—';
  document.getElementById('wdu-context-banner').innerHTML =
    `<div class="font-semibold mb-1">Watch ${ev.watch_id || '—'} <span class="font-normal text-indigo-600">(${limb})</span></div>` +
    `<div class="text-xs text-indigo-700">Removed: ${removed}</div>` +
    `<div class="text-xs text-indigo-700">Expected data range: ${rangeFrom} → ${rangeTo}</div>`;

  // Reset fields
  document.getElementById('wdu-skip').checked = false;
  document.getElementById('wdu-file').value   = '';
  document.getElementById('wdu-notes').value  = '';
  _wduHideProgress();
  setError('wdu-error', '');

  const skipCb   = document.getElementById('wdu-skip');
  const fileWrap = document.getElementById('wdu-file-wrap');
  const notesReq = document.getElementById('wdu-notes-req');
  const fileEl   = document.getElementById('wdu-file');

  // Skip toggle: hide file/progress, flip Notes to required, re-gate Save.
  function syncSkip() {
    const skip = skipCb.checked;
    fileWrap.classList.toggle('hidden', skip);
    notesReq.textContent = skip ? '(required — explain why)' : '(optional)';
    if (skip) _wduHideProgress();
    _wduUpdateSave();
  }
  skipCb.onchange = syncSkip;

  // File-select: validate and upload immediately, showing progress; Save stays
  // disabled until the upload completes.
  fileEl.onchange = () => _wduStartUpload(fileEl.files[0] || null);

  syncSkip();
  _wduUpdateSave();        // Save opens disabled (nothing uploaded, skip off)
  showModal('watch-data-upload-modal');
}

// Save enables only when the file has finished uploading, or skip is checked.
function _wduUpdateSave() {
  const skip = document.getElementById('wdu-skip').checked;
  document.getElementById('wdu-save').disabled = !(_wduUploaded || skip);
}

function _wduShowProgress(pct, done) {
  const wrap = document.getElementById('wdu-progress-wrap');
  const bar  = document.getElementById('wdu-progress-bar');
  const txt  = document.getElementById('wdu-progress-text');
  wrap.classList.remove('hidden');
  bar.style.width = `${pct}%`;
  bar.classList.toggle('bg-green-500', !!done);
  bar.classList.toggle('bg-blue-500',  !done);
  txt.textContent = done ? 'Uploaded ✓' : `Uploading… ${pct}%`;
}

function _wduHideProgress() {
  const wrap = document.getElementById('wdu-progress-wrap');
  if (wrap) wrap.classList.add('hidden');
  const bar = document.getElementById('wdu-progress-bar');
  if (bar) bar.style.width = '0%';
}

function _wduStartUpload(file) {
  setError('wdu-error', '');
  _wduUploaded = false;
  _wduOriginalFilename = null;
  if (_wduXhr) { try { _wduXhr.abort(); } catch {} _wduXhr = null; }
  _wduUpdateSave();

  if (!file) { _wduHideProgress(); return; }
  if (!file.name.toLowerCase().endsWith('.gt3x')) {
    setError('wdu-error', 'Data file must be a .gt3x file.');
    document.getElementById('wdu-file').value = '';
    _wduHideProgress();
    return;
  }

  _wduShowProgress(0, false);

  const fd = new FormData();
  fd.append('event_id', _wduEventId);
  fd.append('file', file);

  // XMLHttpRequest (not fetch) so we get upload.onprogress for the progress bar.
  const xhr = new XMLHttpRequest();
  _wduXhr = xhr;
  xhr.open('POST', `/api/patients/${PATIENT_HOMER_ID}/upload-watch-data`);
  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) _wduShowProgress(Math.round((e.loaded / e.total) * 100), false);
  };
  xhr.onload = () => {
    _wduXhr = null;
    let data = {};
    try { data = JSON.parse(xhr.responseText); } catch {}
    if (xhr.status >= 200 && xhr.status < 300 && data.ok) {
      _wduUploaded = true;
      _wduOriginalFilename = data.original_filename || file.name;
      _wduShowProgress(100, true);
    } else {
      setError('wdu-error', data.error || 'Upload failed. Please try again.');
      _wduHideProgress();
    }
    _wduUpdateSave();
  };
  xhr.onerror = () => {
    _wduXhr = null;
    setError('wdu-error', 'Network error during upload. Please try again.');
    _wduHideProgress();
    _wduUpdateSave();
  };
  xhr.onabort = () => { _wduXhr = null; };
  xhr.send(fd);
}

async function saveWatchDataUpload() {
  const skip  = document.getElementById('wdu-skip').checked;
  const notes = document.getElementById('wdu-notes').value.trim();

  if (skip) {
    if (!notes) { setError('wdu-error', 'Please give a detailed reason for skipping the upload.'); return; }
  } else {
    if (!_wduUploaded) { setError('wdu-error', 'Please choose and upload a .gt3x file first.'); return; }
  }

  const saveBtn = document.getElementById('wdu-save');
  saveBtn.disabled = true;

  const body = { event_id: _wduEventId, skipped: skip, notes };
  if (!skip) body.original_filename = _wduOriginalFilename;

  const { ok, data } = await apiPost(`/api/patients/${PATIENT_HOMER_ID}/complete-event/watch-data-upload`, body);
  if (!ok) {
    _wduUpdateSave();
    setError('wdu-error', data.error || 'Failed to save.');
    return;
  }
  hideModal('watch-data-upload-modal');
  loadPatientEvents();
}

// ── AG Watch Timing modal ─────────────────────────────────────────────────────

let _agwatchEventId         = null;
let _agwatchProtocolEventId = null;
let _agwatchSessionStart    = null;
let _agwatchSessionEnd      = null;
let _agwatchSessionDate     = null;

async function openAgwatchTimingModal(ev) {
  _agwatchEventId         = ev.id;
  _agwatchProtocolEventId = ev.protocol_event_id;

  document.getElementById('agwatch-timing-title').textContent = ev.event_name;
  document.getElementById('agwatch-timing-notes').value       = '';
  _resetAttachment('agwatch');
  const errEl = document.getElementById('agwatch-timing-error');
  errEl.textContent = '';
  errEl.classList.add('hidden');

  _agwatchSessionStart = null;
  _agwatchSessionEnd   = null;
  document.getElementById('agwatch-session-window-wrap').classList.add('hidden');

  const bodyEl = document.getElementById('agwatch-timing-body');
  bodyEl.innerHTML = '<p class="text-sm text-slate-500 px-3 py-4">Loading exercises…</p>';
  showModal('agwatch-timing-modal');

  try {
    const res  = await fetch(
      `/api/patients/${PATIENT_HOMER_ID}/agwatch-timing-exercises/${ev.protocol_event_id}`
    );
    const data = await res.json();
    if (!res.ok) {
      bodyEl.innerHTML = `<p class="text-sm text-red-500 px-3">${data.error || 'Failed to load exercises.'}</p>`;
      return;
    }

    // Session window banner
    _agwatchSessionStart = data.session_start || null;
    _agwatchSessionEnd   = data.session_end   || null;
    const windowWrap = document.getElementById('agwatch-session-window-wrap');
    const windowEl   = document.getElementById('agwatch-session-window');
    if (_agwatchSessionStart && _agwatchSessionEnd) {
      windowEl.textContent = `Session window: ${_agwatchSessionStart.split('T')[1].slice(0,5)} – ${_agwatchSessionEnd.split('T')[1].slice(0,5)}  (all exercise times must fall within this range)`;
      windowWrap.classList.remove('hidden');
    }

    // Derive session date from session_start, fallback to scheduled_date
    _agwatchSessionDate = _agwatchSessionStart
      ? _agwatchSessionStart.split('T')[0]
      : (Array.isArray(ev.scheduled_date) ? ev.scheduled_date[0] : ev.scheduled_date || '').split('T')[0];

    // Build table rows
    bodyEl.innerHTML = data.exercises.map((ex, i) => {
      const typeTag = ex.type === 'vcg'
        ? '<span class="text-[10px] font-bold uppercase tracking-wide text-teal-600 bg-teal-50 border border-teal-200 rounded px-1">VCG</span>'
        : '<span class="text-[10px] font-bold uppercase tracking-wide text-blue-600 bg-blue-50 border border-blue-200 rounded px-1">ADL</span>';
      const dosage = (ex.blocks && ex.repetitions) ? `${ex.blocks}×${ex.repetitions}` : '';
      return `
        <div class="grid grid-cols-[2fr_1fr_1fr_2fr] gap-3 items-center px-3 py-2 rounded-xl border border-slate-100 hover:border-slate-200" data-ex-idx="${i}">
          <div class="flex items-center gap-2 min-w-0">
            ${typeTag}
            <span class="text-sm font-medium text-slate-800 truncate">${ex.name}</span>
            ${dosage ? `<span class="text-xs text-slate-400 flex-shrink-0">${dosage}</span>` : ''}
          </div>
          <input type="hidden" class="agwatch-ex-id" value="${ex.exercise_id}">
          <input type="hidden" class="agwatch-ex-type" value="${ex.type}">
          <div>
            <input type="time" class="agwatch-start w-full px-2 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              placeholder="HH:MM" oninput="_agwatchValidateRow(${i})" onchange="_agwatchValidateRow(${i})">
          </div>
          <div>
            <input type="time" class="agwatch-end w-full px-2 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              placeholder="HH:MM" oninput="_agwatchValidateRow(${i})" onchange="_agwatchValidateRow(${i})">
          </div>
          <div>
            <input type="text" class="agwatch-notes w-full px-2 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300"
              placeholder="Required if no times">
            <p class="agwatch-row-error text-xs text-red-500 mt-0.5 hidden"></p>
          </div>
        </div>`;
    }).join('');

  } catch (e) {
    bodyEl.innerHTML = '<p class="text-sm text-red-500 px-3">Network error loading exercises.</p>';
  }
}

function _agwatchValidateRow(idx) {
  const rows = document.querySelectorAll('#agwatch-timing-body > div[data-ex-idx]');
  const row  = rows[idx];
  if (!row) return;
  const startEl = row.querySelector('.agwatch-start');
  const endEl   = row.querySelector('.agwatch-end');
  const errEl   = row.querySelector('.agwatch-row-error');
  const start   = startEl.value;
  const end     = endEl.value;

  const clearRowErr = () => { errEl.textContent = ''; errEl.classList.add('hidden'); startEl.classList.remove('border-red-400'); endEl.classList.remove('border-red-400'); };
  const setRowErr = (msg, els = []) => {
    errEl.textContent = msg; errEl.classList.remove('hidden');
    els.forEach(el => el.classList.add('border-red-400'));
  };
  clearRowErr();
  if (!start && !end) return;

  if (start && end) {
    if (start >= end) { setRowErr('Start must be before end.', [startEl, endEl]); return; }
    // Within session bounds
    if (_agwatchSessionStart && start < _agwatchSessionStart.split('T')[1].slice(0,5))
      { setRowErr(`Start is before session start (${_agwatchSessionStart.split('T')[1].slice(0,5)}).`, [startEl]); return; }
    if (_agwatchSessionEnd && end > _agwatchSessionEnd.split('T')[1].slice(0,5))
      { setRowErr(`End is after session end (${_agwatchSessionEnd.split('T')[1].slice(0,5)}).`, [endEl]); return; }
  }
  if ((start && !end) || (!start && end))
    setRowErr('Both start and end are required.', [startEl, endEl]);
}

async function saveAgwatchTiming() {
  const errEl = document.getElementById('agwatch-timing-error');
  errEl.textContent = '';
  errEl.classList.add('hidden');

  const rows    = document.querySelectorAll('#agwatch-timing-body > div[data-ex-idx]');
  const timings = [];

  function toDatetime(timeVal) {
    if (!timeVal || !_agwatchSessionDate) return null;
    return `${_agwatchSessionDate}T${timeVal}`;
  }

  for (let i = 0; i < rows.length; i++) {
    const row   = rows[i];
    const exId  = row.querySelector('.agwatch-ex-id').value;
    const exType = row.querySelector('.agwatch-ex-type').value;
    const start = row.querySelector('.agwatch-start').value;
    const end   = row.querySelector('.agwatch-end').value;
    const notes = row.querySelector('.agwatch-notes').value.trim();

    // Incomplete entry
    if ((start && !end) || (!start && end)) {
      errEl.textContent = `Exercise ${i + 1}: both start and end are required, or leave both empty.`;
      errEl.classList.remove('hidden'); return;
    }
    // Start < end
    if (start && end && start >= end) {
      errEl.textContent = `Exercise ${i + 1}: start time must be before end time.`;
      errEl.classList.remove('hidden'); return;
    }
    // Within session bounds
    if (_agwatchSessionStart && start && start < _agwatchSessionStart.split('T')[1].slice(0,5)) {
      errEl.textContent = `Exercise ${i + 1}: start is before session start (${_agwatchSessionStart.split('T')[1].slice(0,5)}).`;
      errEl.classList.remove('hidden'); return;
    }
    if (_agwatchSessionEnd && end && end > _agwatchSessionEnd.split('T')[1].slice(0,5)) {
      errEl.textContent = `Exercise ${i + 1}: end is after session end (${_agwatchSessionEnd.split('T')[1].slice(0,5)}).`;
      errEl.classList.remove('hidden'); return;
    }
    // Notes required when both empty
    if (!start && !end && !notes) {
      errEl.textContent = `Exercise ${i + 1}: notes are required when no timing is recorded.`;
      errEl.classList.remove('hidden'); return;
    }
    timings.push({ exercise_id: exId, type: exType, start: toDatetime(start), end: toDatetime(end), notes });
  }

  // Overlap check across all rows
  const timed = timings.filter(t => t.start && t.end);
  for (let a = 0; a < timed.length; a++) {
    for (let b = a + 1; b < timed.length; b++) {
      if (timed[a].start < timed[b].end && timed[b].start < timed[a].end) {
        const aIdx = timings.indexOf(timed[a]) + 1;
        const bIdx = timings.indexOf(timed[b]) + 1;
        errEl.textContent = `Exercises ${aIdx} and ${bIdx} have overlapping times.`;
        errEl.classList.remove('hidden'); return;
      }
    }
  }

  if (!_validateAttachment('agwatch', 'agwatch-timing-error')) return;

  const globalNotes = document.getElementById('agwatch-timing-notes').value.trim();
  const { ok, data } = await apiPost(`/api/patients/${PATIENT_HOMER_ID}/complete-event/agwatch-timing`, {
    event_id:          _agwatchEventId,
    protocol_event_id: _agwatchProtocolEventId,
    timings,
    notes: globalNotes,
  });
  if (!ok) {
    errEl.textContent = data.error || 'Failed to save.';
    errEl.classList.remove('hidden'); return;
  }

  const { file: awFile, caption: awCaption } = _readAttachment('agwatch');
  if (awFile) {
    const uploaded = await _uploadAttachment(_agwatchEventId, awFile, awCaption, 'agwatch-timing-error');
    if (!uploaded) return;
  }

  hideModal('agwatch-timing-modal');
  _adlTabLoaded = false;
  _vcgTabLoaded = false;
  await loadPatientEvents();
}

// ── Load patient ──────────────────────────────────────────────────────────────

async function loadPatient() {
  try {
    const res = await fetch(`/api/patients/${PATIENT_HOMER_ID}`);
    patientData = await res.json();
    if (!res.ok) {
      console.error('Could not load patient:', patientData.error);
      return;
    }
    renderOverview(patientData);
    // Show "Log Call" button until patient is all_completed (A2 done/missed/delayed).
    const _CALL_BTN_STATUSES = new Set([
      'active', 'paused', 'post_training', 'training_completed',
      'a1_completed', 'broken_protocol', 'discontinued',
    ]);
    const logCallBtn = document.getElementById('log-call-btn');
    if (logCallBtn && _CALL_BTN_STATUSES.has(patientData.status) &&
        (userPrivilege === 'admin' || userPrivilege === 'therapist')) {
      logCallBtn.classList.remove('hidden');
      logCallBtn.classList.add('flex');
    } else if (logCallBtn) {
      logCallBtn.classList.add('hidden');
      logCallBtn.classList.remove('flex');
    }

    // Show "Discontinue" button for admin only when patient is inactive, active, or paused.
    const discBtn = document.getElementById('discontinue-btn');
    const _DISC_BTN_STATUSES = new Set(['inactive', 'active', 'paused']);
    if (discBtn && isAdmin && _DISC_BTN_STATUSES.has(patientData.status) && !_hasDiscontinuationStub) {
      discBtn.classList.remove('hidden');
      discBtn.classList.add('flex');
    } else if (discBtn) {
      discBtn.classList.add('hidden');
      discBtn.classList.remove('flex');
    }
  } catch (e) {
    console.error('Error loading patient:', e);
  }
}

async function loadPrivilege() {
  try {
    const res = await fetch('/api/me');
    if (res.ok) {
      const s = await res.json();
      userPrivilege = s.privilege || '';
      userLoginId   = s.loginId || '';
      isAdmin = userPrivilege === 'admin';
    }
  } catch (_) {}
}

// ── Init ──────────────────────────────────────────────────────────────────────

function _startClock() {
  function _tick() {
    const now  = new Date();
    const time = now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    const date = now.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' });
    const el   = document.getElementById('patient-overdue-clock');
    if (el) el.textContent = `${date}  ${time}`;
  }
  _tick();
  setInterval(_tick, 60000);
}

document.addEventListener('DOMContentLoaded', async () => {
  // Store submit button labels for loading state
  [
    'a1-submit', 'a2-submit', 'discontinue-submit',
    'device-setup-submit', 'activation-submit',
    'adl-prescription-submit', 'vcg-prescription-submit',
    'prescription-printout-save', 'prescription-printout-print',
    'wr-save', 'note-save',
  ].forEach(id => {
    const btn = document.getElementById(id);
    if (btn) btn.dataset.label = btn.textContent;
  });

  // Set up prescription search bar listeners
  _setupPrescSearchListener('adl');
  _setupPrescSearchListener('vcg');

  _startClock();
  await loadPrivilege();
  await loadPatient();
  await loadPatientEvents();
  switchTab('overview');

  // Auto-open modal if ?action=<event_id> is in the URL, then clean up the URL
  const actionId = new URLSearchParams(window.location.search).get('action');

  if (actionId) {
    history.replaceState(null, '', window.location.pathname);
    const ev = eventsCache.find(e => e.id === actionId);
    if (ev) {
      const opener = EVENT_OPENERS[ev.protocol_event_id];
      if (opener) opener(ev);
    }
  }
});

// ── Other Device Issue Modal ──────────────────────────────────────────────────

function _esc(s) { return String(s ?? '').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

let _odiEventId         = null;
let _odiAssigned        = []; // [{dtype, device_id, label}] assigned to patient
let _odiTrainingStopped = false;
let _odiIsBp            = false;

async function openOtherDeviceIssueModal(ev) {
  _odiEventId         = ev.id;
  _odiAssigned        = [];
  _odiTrainingStopped = !!ev.training_stopped;
  _odiIsBp            = !!patientData?.brokenProtocolDate;
  setError('odi-error', '');

  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const nowStr = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const todayDate = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}`;
  document.getElementById('odi-completion-date').value = nowStr;
  document.getElementById('odi-completion-date').max   = nowStr;
  document.getElementById('odi-issue-occur-date').value = '';
  document.getElementById('odi-issue-occur-date').max   = todayDate;
  document.getElementById('odi-notes').value = '';
  document.querySelectorAll('input[name="odi-call-mode"]').forEach(r => { r.checked = false; });
  document.getElementById('odi-device-rows').innerHTML =
    '<p class="text-sm text-slate-400 italic">Loading devices…</p>';

  const ctx = document.getElementById('odi-context');
  if (ev.triggered_by) {
    const triggerName = _AE_TRIGGER_NAMES[ev.triggered_by.type] || ev.triggered_by.type.replace(/_/g, ' ');
    const triggerEv   = (_completeEventsCache || []).find(e => e.id === ev.triggered_by.id);
    const dateStr     = triggerEv?.completion_date ? ` on ${_fmtDateTime(triggerEv.completion_date)}` : '';
    ctx.textContent   = `Other device issue reported during ${triggerName}${dateStr}`;
    ctx.classList.remove('hidden');
  } else {
    ctx.classList.add('hidden');
  }
  document.getElementById('odi-bp-banner').classList.toggle('hidden', !_odiIsBp);

  // Fetch and set date validation bounds BEFORE showing modal
  const dates = await _fetchIssueValidationDates();
  _setIssueModalDateBounds(dates.enroll_date, null, 'odi-issue-occur-date', 'odi-completion-date');

  showModal('other-device-issue-modal');

  try {
    const res = await fetch('/devices/api/inventory');
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    const inv = await res.json();

    // Build flat list of devices assigned to this patient
    (inv.modems  || []).filter(d => !d.removal_date && d.assigned_to?.homerID === PATIENT_HOMER_ID)
                       .forEach(d => _odiAssigned.push({ dtype: 'modems',  device_id: d.id, label: `Modem — ${d.id}` }));
    (inv.laptops || []).filter(d => !d.removal_date && d.assigned_to?.homerID === PATIENT_HOMER_ID)
                       .forEach(d => _odiAssigned.push({ dtype: 'laptops', device_id: d.id, label: `Laptop — ${d.id}` }));
    // SIM linked to patient's modem
    const patientModem = (inv.modems || []).find(d => !d.removal_date && d.assigned_to?.homerID === PATIENT_HOMER_ID);
    if (patientModem?.sim_id) {
      const sim = (inv.sims || []).find(s => s.id === patientModem.sim_id && !s.removal_date);
      if (sim) _odiAssigned.push({ dtype: 'sims', device_id: sim.id, label: `SIM — ${sim.phoneNumber || sim.id}` });
    }

    _odiBuildSections();
  } catch (e) {
    setError('odi-error', 'Failed to load device inventory: ' + e.message);
    document.getElementById('odi-device-rows').innerHTML = '';
  }
}

function _odiBuildSections() {
  const container = document.getElementById('odi-device-rows');
  container.innerHTML = '';

  if (!_odiAssigned.length) {
    container.innerHTML = '<p class="text-sm text-slate-400 italic">No modem, laptop or SIM assigned to this patient.</p>';
    return;
  }

  _odiAssigned.forEach((dev, i) => {
    const sec = document.createElement('div');
    sec.className = 'border border-slate-200 rounded-xl p-4';
    if (_odiIsBp) {
      sec.innerHTML = `
        <label class="flex items-center gap-2 cursor-pointer select-none">
          <input type="checkbox" id="odi-on-${i}" class="w-4 h-4 rounded border-slate-300 accent-purple-600">
          <span class="text-sm font-semibold text-slate-800">${_esc(dev.label)}</span>
        </label>
        <div id="odi-form-${i}" class="hidden mt-3 pl-6">
          <label class="block text-xs font-medium text-slate-600 mb-1">Fault description <span class="text-red-400">*</span></label>
          <textarea id="odi-notes-${i}" rows="2"
            class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-purple-200 resize-none"
            placeholder="Describe the fault…"></textarea>
        </div>
      `;
    } else {
      sec.innerHTML = `
        <label class="flex items-center gap-2 cursor-pointer select-none">
          <input type="checkbox" id="odi-on-${i}" class="w-4 h-4 rounded border-slate-300 accent-purple-600">
          <span class="text-sm font-semibold text-slate-800">${_esc(dev.label)}</span>
        </label>
        <div id="odi-form-${i}" class="hidden mt-3 space-y-3 pl-6">
          <div>
            <p class="text-xs font-medium text-slate-600 mb-2">Outcome <span class="text-red-400">*</span></p>
            <div class="space-y-1">
              <label class="flex items-center gap-2 cursor-pointer">
                <input type="radio" name="odi-outcome-${i}" value="visit_required" class="w-4 h-4 accent-purple-600">
                <span class="text-sm text-slate-700">Visit required — engineer needs to come</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer">
                <input type="radio" name="odi-outcome-${i}" value="resolved_over_call" class="w-4 h-4 accent-purple-600">
                <span class="text-sm text-slate-700">Resolved over call — no visit needed</span>
              </label>
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-slate-600 mb-1">Notes <span class="text-slate-400 font-normal">(optional)</span></label>
            <textarea id="odi-notes-${i}" rows="2"
              class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-purple-200 resize-none"
              placeholder="Device-specific notes…"></textarea>
          </div>
        </div>
      `;
    }
    container.appendChild(sec);

    document.getElementById(`odi-on-${i}`).onchange = function () {
      document.getElementById(`odi-form-${i}`).classList.toggle('hidden', !this.checked);
      if (!this.checked) {
        if (!_odiIsBp) {
          document.querySelectorAll(`input[name="odi-outcome-${i}"]`).forEach(r => r.checked = false);
        }
        document.getElementById(`odi-notes-${i}`).value = '';
      }
    };

    // In normal mode only: pre-check visit_required when stub was the primary training-stop reason
    if (!_odiIsBp && _odiTrainingStopped) {
      document.getElementById(`odi-on-${i}`).checked = true;
      document.getElementById(`odi-form-${i}`).classList.remove('hidden');
      const visitRadio = document.querySelector(`input[name="odi-outcome-${i}"][value="visit_required"]`);
      if (visitRadio) visitRadio.checked = true;
    }
  });
}

async function saveOtherDeviceIssueCall() {
  const completionDate  = document.getElementById('odi-completion-date').value;
  let issueOccurDate    = document.getElementById('odi-issue-occur-date').value;
  const callMode        = document.querySelector('input[name="odi-call-mode"]:checked')?.value || '';
  const notes           = document.getElementById('odi-notes').value.trim();

  // Convert dd-mm-yyyy to YYYY-MM-DD if needed
  if (issueOccurDate && /^\d{2}-\d{2}-\d{4}$/.test(issueOccurDate)) {
    const parts = issueOccurDate.split('-');
    issueOccurDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
  }

  if (!completionDate)  { setError('odi-error', 'Call date is required.'); return; }
  if (!issueOccurDate)  { setError('odi-error', 'Issue first occurred date is required.'); return; }
  if (!callMode)        { setError('odi-error', 'Call mode (Audio / Video) is required.'); return; }

  // Validate dates
  const today = new Date().toISOString().split('T')[0];
  const callDateStr = completionDate.split('T')[0];

  if (issueOccurDate > today) {
    setError('odi-error', 'Issue occurred date cannot be in the future.');
    return;
  }
  const minDate = document.getElementById('odi-issue-occur-date').min;
  if (minDate && issueOccurDate < minDate) {
    setError('odi-error', `Issue occurred date must be on or after enrollment date (${minDate}).`);
    return;
  }
  if (callDateStr > today) {
    setError('odi-error', 'Call date cannot be in the future.');
    return;
  }
  if (callDateStr < issueOccurDate) {
    setError('odi-error', 'Call date must be on or after issue occurred date.');
    return;
  }

  const devices = [];
  for (let i = 0; i < _odiAssigned.length; i++) {
    if (!document.getElementById(`odi-on-${i}`)?.checked) continue;
    const devNotes = document.getElementById(`odi-notes-${i}`)?.value.trim();
    const dev      = _odiAssigned[i];
    if (!devNotes) { setError('odi-error', `Fault description required for ${dev.label}.`); return; }
    if (_odiIsBp) {
      devices.push({ device_type: dev.dtype, device_id: dev.device_id, notes: devNotes });
    } else {
      const outcome = document.querySelector(`input[name="odi-outcome-${i}"]:checked`)?.value || '';
      if (!outcome) { setError('odi-error', `Select an outcome for ${dev.label}.`); return; }
      devices.push({ device_type: dev.dtype, device_id: dev.device_id, outcome, notes: devNotes || null });
    }
  }

  if (!devices.length) { setError('odi-error', 'Select at least one device with an issue.'); return; }

  setLoading('odi-save', true);
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/other-device-issue-call`,
    { event_id: _odiEventId, completion_date: completionDate,
      issue_occur_date: issueOccurDate, call_mode: callMode,
      notes: notes || null, devices, broken_protocol_mode: _odiIsBp }
  );
  setLoading('odi-save', false);
  if (!ok) { setError('odi-error', data.error || 'Failed to save.'); return; }

  hideModal('other-device-issue-modal');
  loadPatientEvents();
}

// ── Other Device Issue — Engineer Visit ──────────────────────────────────────

let _odivEventId   = null;
let _odivDevices   = []; // devices that need visit (from linked call event)
let _odivInventory = {}; // available replacement devices by type
let _odivIsBp      = false;

async function openOtherDeviceIssueVisitModal(ev) {
  _odivEventId = ev.id;
  _odivIsBp    = !!patientData?.brokenProtocolDate;
  setError('odiv-error', '');

  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const nowStr = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
  document.getElementById('odiv-completion-date').value = nowStr;
  document.getElementById('odiv-completion-date').max   = nowStr;
  document.getElementById('odiv-notes').value = '';
  document.getElementById('odiv-device-rows').innerHTML =
    '<p class="text-sm text-slate-400 italic">Loading device info…</p>';

  // Context and issue_occur_date from linked call
  const callId    = (ev.triggered_by || {}).id;
  const callEvent = (_completeEventsCache || []).concat(
    Object.values((eventsCache?.free || {})).flat()
  ).find(e => e.id === callId);
  const issueOccurDate = callEvent?.issue_occur_date || null;

  const ctx = document.getElementById('odiv-context');
  ctx.textContent = callEvent
    ? `Following call on ${callEvent.completion_date?.slice(0, 16).replace('T', ' ') || '—'}`
    : 'Engineer visit';
  ctx.classList.remove('hidden');

  const occRow = document.getElementById('odiv-issue-occur-row');
  const occDiv = document.getElementById('odiv-issue-occur-date');
  if (issueOccurDate) {
    occDiv.textContent = issueOccurDate.slice(0, 16).replace('T', ' ');
    occRow.classList.remove('hidden');
  } else {
    occRow.classList.add('hidden');
  }

  // Fetch and set date validation bounds BEFORE showing modal
  const dates = await _fetchIssueValidationDates(ev.triggered_by?.id);
  _setIssueModalDateBounds(null, dates.issue_occur_date, null, 'odiv-completion-date');

  // Toggle BP mode UI
  document.getElementById('odiv-bp-banner').classList.toggle('hidden', !_odivIsBp);
  document.getElementById('odiv-normal-section').classList.toggle('hidden', _odivIsBp);
  document.getElementById('odiv-bp-device-rows').innerHTML = '';

  showModal('other-device-issue-visit-modal');

  try {
    const res = await fetch('/devices/api/inventory');
    if (!res.ok) throw new Error();
    const inv = await res.json();
    _odivInventory = {
      modems:  (inv.modems  || []).filter(d => !d.removal_date && !d.assigned_to),
      laptops: (inv.laptops || []).filter(d => !d.removal_date && !d.assigned_to),
      sims:    (inv.sims    || []).filter(s => !s.removal_date),
    };

    const visitDevices = (callEvent?.devices || []).filter(d => d.outcome === 'visit_required');
    _odivDevices = visitDevices;

    if (_odivIsBp) {
      _buildOdivBpDeviceRows(visitDevices);
      return;
    }

    const container = document.getElementById('odiv-device-rows');
    container.innerHTML = '';
    if (!visitDevices.length) {
      container.innerHTML = '<p class="text-sm text-slate-400 italic">No devices flagged for visit.</p>';
      return;
    }
    visitDevices.forEach((d, i) => _odivBuildRow(container, d, i));
  } catch (e) {
    setError('odiv-error', 'Failed to load device inventory.');
    document.getElementById('odiv-device-rows').innerHTML = '';
  }
}

function _odivBpFaultChange(idx) {
  const checked = document.getElementById(`odiv-bp-fault-${idx}`)?.checked;
  document.getElementById(`odiv-bp-desc-wrap-${idx}`)?.classList.toggle('hidden', !checked);
}

function _buildOdivBpDeviceRows(devices) {
  const container = document.getElementById('odiv-bp-device-rows');
  container.innerHTML = '';
  if (!devices.length) {
    container.innerHTML = '<p class="text-sm text-slate-400 italic">No devices flagged for visit.</p>';
    return;
  }
  devices.forEach((d, idx) => {
    const dtype   = d.device_type || d.dtype;
    const deviceId = d.device_id;
    const label   = dtype === 'modems' ? 'Modem' : dtype === 'laptops' ? 'Laptop' : 'SIM';
    const rowDiv  = document.createElement('div');
    rowDiv.className = 'border border-slate-200 rounded-xl p-4 space-y-3';
    rowDiv.innerHTML = `
      <div class="flex items-center justify-between">
        <span class="text-sm font-semibold text-slate-800">${_esc(label)}</span>
        <span class="text-xs text-slate-500">Device: <span class="font-mono">${_esc(deviceId)}</span></span>
      </div>
      <div class="flex items-center gap-2">
        <input type="checkbox" id="odiv-bp-fault-${idx}" class="w-4 h-4 accent-amber-600"
          onchange="_odivBpFaultChange(${idx})">
        <label for="odiv-bp-fault-${idx}" class="text-sm text-slate-700 cursor-pointer">This device has a fault</label>
      </div>
      <div id="odiv-bp-desc-wrap-${idx}" class="hidden pl-2 border-l-2 border-amber-200">
        <label class="block text-xs font-medium text-slate-600 mb-1">Fault description <span class="text-red-400">*</span></label>
        <textarea id="odiv-bp-desc-${idx}" rows="2"
          class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-amber-200 resize-none"
          placeholder="Describe the fault…"></textarea>
      </div>
    `;
    container.appendChild(rowDiv);
  });
}

function _odivBuildRow(container, d, idx) {
  const dtype    = d.device_type || d.dtype;
  const deviceId = d.device_id;
  const label    = dtype === 'modems' ? 'Modem' : dtype === 'laptops' ? 'Laptop' : 'SIM';
  const avail    = _odivInventory[dtype] || [];
  // For SIMs, filter to only unlinked SIMs (where !modem_id)
  const filtered = dtype === 'sims'
                   ? avail.filter(r => !r.removal_date && !r.modem_id)
                   : avail.filter(r => !r.removal_date && !r.assigned_to);
  const replOpts = filtered.filter(r => r.id !== deviceId)
                           .map(r => `<option value="${_esc(r.id)}">${_esc(r.id)}</option>`).join('');

  const row = document.createElement('div');
  row.className = 'border border-slate-200 rounded-xl p-4 space-y-3';
  row.innerHTML = `
    <div class="flex items-center justify-between">
      <span class="text-sm font-semibold text-slate-800">${_esc(label)}</span>
      <span class="text-xs text-slate-500">Current: <span class="font-mono">${_esc(deviceId)}</span></span>
    </div>
    <div>
      <p class="text-xs font-medium text-slate-600 mb-2">Outcome <span class="text-red-400">*</span></p>
      <div class="space-y-2">
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="radio" name="odiv-outcome-${idx}" value="repaired" class="w-4 h-4 accent-purple-600"
            onchange="_odivOutcomeChange(${idx})">
          <span class="text-sm text-slate-700">Repaired on site</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="radio" name="odiv-outcome-${idx}" value="replaced" class="w-4 h-4 accent-purple-600"
            onchange="_odivOutcomeChange(${idx})">
          <span class="text-sm text-slate-700">Replaced with another device</span>
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="radio" name="odiv-outcome-${idx}" value="neither" class="w-4 h-4 accent-purple-600"
            onchange="_odivOutcomeChange(${idx})">
          <span class="text-sm text-slate-700">Neither — still has issue</span>
        </label>
      </div>
    </div>
    <div id="odiv-replace-section-${idx}" class="hidden space-y-2 pl-2 border-l-2 border-purple-200">
      <label class="block text-xs font-medium text-slate-600 mb-1">Replacement Device <span class="text-red-400">*</span></label>
      <select id="odiv-new-device-${idx}"
              class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-purple-200 bg-white">
        <option value="">Select replacement…</option>
        ${replOpts || '<option value="" disabled>No available devices</option>'}
      </select>
    </div>
    <div class="pl-2 border-l-2 border-slate-100">
      <label class="block text-xs font-medium text-slate-600 mb-1">Notes <span class="text-slate-400 font-normal">(optional)</span></label>
      <textarea id="odiv-device-notes-${idx}" rows="2"
                class="w-full px-3 py-2 border border-slate-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-purple-200 resize-none"
                placeholder="What was done…"></textarea>
    </div>
  `;
  container.appendChild(row);
}

function _odivOutcomeChange(idx) {
  const outcome = document.querySelector(`input[name="odiv-outcome-${idx}"]:checked`)?.value;
  document.getElementById(`odiv-replace-section-${idx}`).classList.toggle('hidden', outcome !== 'replaced');
}

async function saveOtherDeviceIssueVisit() {
  const completionDate = document.getElementById('odiv-completion-date').value;
  const notes          = document.getElementById('odiv-notes').value.trim();

  if (!completionDate) { setError('odiv-error', 'Visit date is required.'); return; }

  // Validate visit date
  const today = new Date().toISOString().split('T')[0];
  if (completionDate.split('T')[0] > today) {
    setError('odiv-error', 'Visit date cannot be in the future.');
    return;
  }
  const minDate = document.getElementById('odiv-completion-date').min;
  if (minDate && completionDate.split('T')[0] < minDate.split('T')[0]) {
    setError('odiv-error', `Visit date must be on or after issue occurred date (${minDate.split('T')[0]}).`);
    return;
  }

  // ── Broken-protocol mode ──────────────────────────────────────────────────
  if (_odivIsBp) {
    const deviceFaults = [];
    for (let i = 0; i < _odivDevices.length; i++) {
      const d       = _odivDevices[i];
      const dtype   = d.device_type || d.dtype;
      const hasFault = document.getElementById(`odiv-bp-fault-${i}`)?.checked;
      if (hasFault) {
        const desc = document.getElementById(`odiv-bp-desc-${i}`)?.value.trim() || '';
        const label = dtype === 'modems' ? 'Modem' : dtype === 'laptops' ? 'Laptop' : 'SIM';
        if (!desc) { setError('odiv-error', `Please describe the fault for ${label} ${d.device_id}.`); return; }
        deviceFaults.push({ device_type: dtype, device_id: d.device_id, notes: desc });
      }
    }
    setLoading('odiv-save', true);
    const { ok, data } = await apiPost(
      `/api/patients/${PATIENT_HOMER_ID}/complete-event/other-device-issue-visit`,
      { event_id: _odivEventId, completion_date: completionDate, notes: notes || null,
        device_faults: deviceFaults, broken_protocol_mode: true }
    );
    setLoading('odiv-save', false);
    if (!ok) { setError('odiv-error', data.error || 'Failed to save.'); return; }
    hideModal('other-device-issue-visit-modal');
    loadPatientEvents();
    return;
  }
  // ─────────────────────────────────────────────────────────────────────────

  const outcomes = [];
  for (let i = 0; i < _odivDevices.length; i++) {
    const d       = _odivDevices[i];
    const outcome = document.querySelector(`input[name="odiv-outcome-${i}"]:checked`)?.value || '';
    const newId   = document.getElementById(`odiv-new-device-${i}`)?.value || null;
    const dNotes  = document.getElementById(`odiv-device-notes-${i}`)?.value.trim() || null;
    const dtype   = d.device_type || d.dtype;
    const label   = dtype === 'modems' ? 'Modem' : dtype === 'laptops' ? 'Laptop' : 'SIM';

    if (!outcome) { setError('odiv-error', `Select an outcome for ${label} ${d.device_id}.`); return; }
    if (outcome === 'replaced' && !newId) { setError('odiv-error', `Select a replacement device for ${label} ${d.device_id}.`); return; }

    outcomes.push({ device_type: dtype, device_id: d.device_id, outcome, new_device_id: newId, notes: dNotes });
  }

  if (!outcomes.length) { setError('odiv-error', 'No device outcomes to record.'); return; }

  setLoading('odiv-save', true);
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/other-device-issue-visit`,
    { event_id: _odivEventId, completion_date: completionDate, notes: notes || null, device_outcomes: outcomes }
  );
  setLoading('odiv-save', false);
  if (!ok) { setError('odiv-error', data.error || 'Failed to save.'); return; }

  hideModal('other-device-issue-visit-modal');
  loadPatientEvents();
}

// ── Device Return ────────────────────────────────────────────────────────────

let _drEventId  = null;
let _drDevices  = [];

async function openDeviceReturnModal(ev) {
  _drEventId = ev.id;

  document.getElementById('dr-homer-id').textContent = PATIENT_HOMER_ID;
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const nowStr = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
  const dateEl = document.getElementById('dr-date');
  dateEl.max   = nowStr;
  dateEl.value = nowStr;
  document.getElementById('dr-date-error').classList.add('hidden');
  document.getElementById('dr-notes').value = '';
  document.getElementById('dr-error').classList.add('hidden');
  _resetAttachment('dr');

  // Fetch currently assigned devices
  const { ok, data } = await apiGet(`/api/patients/${PATIENT_HOMER_ID}/device-return-devices`);
  if (!ok) {
    setError('dr-error', data.error || 'Could not load assigned devices.');
    showModal('device-return-modal');
    return;
  }
  _drDevices = data.devices || [];
  _renderDeviceReturnCards();

  // Keyboard validation for date
  _attachDateGuard(dateEl, 'dr-date-error');

  showModal('device-return-modal');
}

function _renderDeviceReturnCards() {
  const container = document.getElementById('dr-devices-container');
  if (!_drDevices.length) {
    container.innerHTML = '<p class="text-sm text-slate-500 italic">No devices currently assigned to this patient.</p>';
    return;
  }
  container.innerHTML = _drDevices.map((d, i) => _deviceReturnCard(d, i)).join('');

  // onchange is wired inline in the select element
}

function _deviceReturnCard(d, i) {
  const today = new Date().toISOString().slice(0, 10);
  const TYPE_LABEL = { pluto: 'Pluto', mars: 'Mars', modems: 'Modem', laptops: 'Laptop', agwatch: 'AG Watch', sims: 'SIM Card' };
  const typeLabel  = TYPE_LABEL[d.type] || d.type;
  const idBadge    = d.device_id;
  const limbSuffix = d.limb ? ` (${d.limb.charAt(0).toUpperCase() + d.limb.slice(1)})` : '';

  const lowBatteryOption = d.type === 'agwatch'
    ? `<option value="low_battery">Low Battery</option>` : '';

  return `
    <div class="border border-slate-200 rounded-xl p-3">
      <div class="flex items-center gap-2 mb-2">
        <span class="px-2 py-0.5 bg-slate-100 text-slate-700 text-xs rounded font-mono">${idBadge}</span>
        <span class="text-sm font-medium text-slate-700">${typeLabel}${limbSuffix}</span>
      </div>
      <div class="flex gap-2 items-start">
        <select id="dr-status-${i}" onchange="_updateDrIssueDateVisibility(${i})"
          class="flex-shrink-0 px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300 bg-white">
          <option value="working">Working</option>
          <option value="lost">Lost</option>
          <option value="faulty">Faulty</option>
          ${lowBatteryOption}
        </select>
        <input type="date" id="dr-issue-date-${i}" max="${today}"
          class="hidden flex-shrink-0 px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-300">
        <input type="text" id="dr-dev-notes-${i}"
          class="flex-1 min-w-0 px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:outline-none" placeholder="Notes (optional)">
      </div>
    </div>`;
}

function _updateDrIssueDateVisibility(i) {
  const val   = document.getElementById(`dr-status-${i}`)?.value;
  const field = document.getElementById(`dr-issue-date-${i}`);
  if (field) field.classList.toggle('hidden', val === 'working');
}

async function saveDeviceReturn() {
  const completionDate = document.getElementById('dr-date').value;
  if (!completionDate) { setError('dr-error', 'Return date/time is required.'); return; }
  const now = new Date();
  if (new Date(completionDate) > now) { setError('dr-error', 'Return date cannot be in the future.'); return; }

  // Collect per-device data
  const deviceEntries = [];
  for (let i = 0; i < _drDevices.length; i++) {
    const d         = _drDevices[i];
    const status    = document.getElementById(`dr-status-${i}`)?.value || 'working';
    const issueDate = document.getElementById(`dr-issue-date-${i}`)?.value || '';
    const notes     = document.getElementById(`dr-dev-notes-${i}`)?.value.trim() || null;
    if (status !== 'working' && !issueDate) {
      setError('dr-error', `Please enter when the issue occurred for ${d.device_id || d.sim_id || 'device'}.`);
      return;
    }
    const entry = { type: d.type, status, issue_date: issueDate || null, notes };
    if (d.type === 'agwatch') { entry.device_id = d.device_id; entry.limb = d.limb; }
    else if (d.type === 'sims') { entry.sim_id = d.sim_id; }
    else { entry.device_id = d.device_id; }
    deviceEntries.push(entry);
  }

  const notes = document.getElementById('dr-notes').value.trim() || null;

  // Upload attachment first if present
  const attachFile    = document.getElementById('dr-attachment-file')?.files[0];
  const attachCaption = document.getElementById('dr-attachment-caption')?.value.trim() || null;
  if (attachFile && !attachCaption) {
    setError('dr-error', 'Please add a caption for the attachment.');
    return;
  }

  setLoading('dr-save', true);
  const { ok, data } = await apiPost(
    `/api/patients/${PATIENT_HOMER_ID}/complete-event/device-return`,
    { event_id: _drEventId, completion_date: completionDate, notes, devices: deviceEntries }
  );
  if (!ok) { setLoading('dr-save', false); setError('dr-error', data.error || 'Failed to save.'); return; }

  if (attachFile) {
    await _uploadAttachment(data.event_id, attachFile, attachCaption, 'dr-error');
  }

  setLoading('dr-save', false);
  hideModal('device-return-modal');
  loadPatientEvents();
}

// ── Notes tab ──────────────────────────────────────────────────────────────────
// Free-text, immutable notes per patient. Role-keyed server-side (each role sees
// only its own bucket; admin sees all). See docs/pages.md → Create Note.

let _noteQuill        = null;   // lazy-initialised Quill instance
let _noteModalOpenAt  = null;   // epoch ms when the Create Note modal opened
let _noteTargetEventId = null;  // null = free note; else event id for a retrospective event note
let _notesCache       = [];
let _notesIsAdmin     = false;

function _ensureNoteQuill() {
  if (_noteQuill || typeof Quill === 'undefined') return _noteQuill;
  _noteQuill = new Quill('#note-editor', {
    theme: 'snow',
    placeholder: 'Write the note…',
    modules: {
      toolbar: [
        [{ header: [1, 2, 3, false] }],
        ['bold', 'italic', 'underline'],
        [{ list: 'ordered' }, { list: 'bullet' }],
        ['link', 'blockquote'],
        ['clean'],
      ],
    },
  });
  return _noteQuill;
}

function _openNoteModalCommon() {
  setError('note-error', '');
  document.getElementById('note-title').value = '';
  _resetAttachment('note');
  const q = _ensureNoteQuill();
  if (q) q.setContents([]);                          // clear body
  else  document.getElementById('note-editor').innerHTML = '';
  _noteModalOpenAt = Date.now();                     // for created_at = committed_at − gap
  showModal('note-modal');
  // Focus the title once the modal is visible.
  setTimeout(() => document.getElementById('note-title')?.focus(), 50);
}

// Free note (Notes tab)
function openNoteModal() {
  _noteTargetEventId = null;
  _openNoteModalCommon();
}

// Retrospective note on a Timeline event
function openEventNoteModal(eventId) {
  _noteTargetEventId = eventId;
  _openNoteModalCommon();
}

async function saveNote() {
  const title = document.getElementById('note-title').value.trim();
  const html  = _noteQuill ? _noteQuill.root.innerHTML : '';
  const plain = _noteQuill ? _noteQuill.getText().trim() : '';

  if (!title)  { setError('note-error', 'Please enter a title.'); return; }
  if (!plain)  { setError('note-error', 'Please write the note.'); return; }
  if (!_validateAttachment('note', 'note-error')) return;

  const { file, caption } = _readAttachment('note');
  const gap = _noteModalOpenAt != null ? (Date.now() - _noteModalOpenAt) / 1000 : 0;

  const form = new FormData();
  form.append('title', title);
  form.append('content_html', html);
  form.append('gap_seconds', String(gap));
  if (file) {
    form.append('file', file);
    form.append('caption', caption);
  }

  const targetEventId = _noteTargetEventId;
  const url = targetEventId
    ? `/api/patients/${PATIENT_HOMER_ID}/events/${targetEventId}/notes`
    : `/api/patients/${PATIENT_HOMER_ID}/notes`;

  setLoading('note-save', true);
  const res  = await fetch(url, { method: 'POST', body: form });
  let data;
  try { data = await res.json(); } catch { data = { error: `Server error (${res.status})` }; }
  setLoading('note-save', false);
  if (!res.ok) { setError('note-error', data.error || 'Failed to save note.'); return; }

  _noteModalOpenAt = null;
  _noteTargetEventId = null;
  hideModal('note-modal');
  if (targetEventId) {
    // Bump the cached count (own bucket +1 — matches the viewer's role-filtered count),
    // then re-render so the row badge updates; selection is restored and notes reloaded.
    const ev = (_completeEventsCache || []).find(e => e.id === targetEventId);
    if (ev) ev.event_notes_count = (ev.event_notes_count || 0) + 1;
    renderTimelineTab();
    // Also refresh whichever card surface is on screen (no-op when the card
    // isn't rendered). One save updates every surface that's currently showing
    // the same `event_notes` data.
    _refreshAeCardNotes(targetEventId);
    _refreshDiCardNotes(targetEventId);
    _refreshCallCardNotes(targetEventId);
  } else {
    renderNotesTab();
  }
}

async function renderNotesTab() {
  const container = document.getElementById('notes-content');
  if (!container) return;
  container.innerHTML = `
    <div class="flex items-center justify-center py-10 text-slate-400">
      <i class="fas fa-spinner fa-spin mr-2"></i><span>Loading…</span>
    </div>`;

  const { ok, data } = await apiGet(`/api/patients/${PATIENT_HOMER_ID}/notes`);
  if (!ok) {
    container.innerHTML = `<p class="text-sm text-red-500 py-6 text-center">${_esc(data.error || 'Failed to load notes.')}</p>`;
    return;
  }
  _notesCache   = data.notes || [];
  _notesIsAdmin = !!data.is_admin;

  if (!_notesCache.length) {
    container.innerHTML = `
      <div class="flex flex-col items-center justify-center py-16 text-slate-300">
        <i class="fas fa-sticky-note text-3xl mb-3"></i>
        <p class="text-sm">No notes yet.</p>
      </div>`;
    return;
  }
  container.innerHTML = _notesCache.map(n => _noteCard(n, _notesIsAdmin)).join('');
}

function _toggleNoteCard(cardId) {
  const body    = document.getElementById(`note-body-${cardId}`);
  const chevron = document.getElementById(`note-chevron-${cardId}`);
  if (!body) return;
  const isHidden = body.classList.toggle('hidden');
  if (chevron) chevron.style.transform = isHidden ? '' : 'rotate(180deg)';
}

// Free-note card (Notes tab)
function _noteCard(note, isAdmin) {
  const attachUrl = note.attachment ? `/api/patients/${PATIENT_HOMER_ID}/notes/${note.id}/attachment` : null;
  return _noteCardHtml(note, isAdmin, attachUrl);
}

// Event-note card (Timeline) — same look, different attachment endpoint
function _eventNoteCard(note, isAdmin) {
  const attachUrl = note.attachment ? `/api/patients/${PATIENT_HOMER_ID}/event-notes/${note.id}/attachment` : null;
  return _noteCardHtml(note, isAdmin, attachUrl);
}

// Shared collapsible card for both note kinds. cardId (note.id) is a UUID, so the
// toggle/body element ids never collide across free notes and event notes.
function _noteCardHtml(note, isAdmin, attachUrl) {
  const cardId       = note.id;
  const createdStr   = note.created_at   ? _fmtDateTime(note.created_at)   : '—';
  const committedStr = note.committed_at ? _fmtDateTime(note.committed_at) : '—';
  const safeBody  = (typeof DOMPurify !== 'undefined')
    ? DOMPurify.sanitize(note.content_html || '')
    : (note.content_html || '');
  const authorRow = isAdmin
    ? `<div class="text-xs text-slate-500"><span class="text-slate-400">Author:</span> ${_esc(note.author || '—')}</div>`
    : '';
  const attachRow = attachUrl
    ? `<a href="${attachUrl}" target="_blank"
          class="inline-flex items-center gap-1.5 text-xs text-blue-600 hover:text-blue-700 hover:underline">
         <i class="fas fa-file-pdf"></i> ${_esc(note.attachment_caption || 'Attachment')}
       </a>`
    : '';

  return `
    <div class="border border-slate-200 rounded-xl mb-3 last:mb-0 overflow-hidden bg-white shadow-sm">
      <div class="flex items-center justify-between px-4 py-3 cursor-pointer hover:bg-slate-50 select-none"
           onclick="_toggleNoteCard('${cardId}')">
        <div class="flex items-center gap-3 min-w-0">
          <span class="text-xs font-semibold text-blue-700 bg-blue-50 border border-blue-200 rounded-full px-2 py-0.5 shrink-0">${_esc(note.alias || 'Note')}</span>
          <span class="text-sm font-medium text-slate-800 truncate">${_esc(note.title || '')}</span>
        </div>
        <div class="flex items-center gap-3 shrink-0">
          <span class="text-xs text-slate-400">${createdStr}</span>
          <i id="note-chevron-${cardId}" class="fas fa-chevron-down text-slate-400 text-xs transition-transform"></i>
        </div>
      </div>
      <div id="note-body-${cardId}" class="hidden px-4 pb-4 pt-1 border-t border-slate-100 space-y-3">
        <div class="note-rich text-sm text-slate-700">${safeBody}</div>
        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1">
          <div class="text-xs text-slate-500"><span class="text-slate-400">Created:</span> ${createdStr}</div>
          <div class="text-xs text-slate-500"><span class="text-slate-400">Committed:</span> ${committedStr}</div>
          ${authorRow}
        </div>
        ${attachRow}
      </div>
    </div>`;
}

// Event-note loading/rendering for the Timeline detail panel lives with the
// Timeline (master–detail) code above: _loadTimelineDetailNotes().
