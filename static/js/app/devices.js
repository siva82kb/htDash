/* ============================================================
   devices.js — Device Management Page
   ============================================================ */

// ── State ─────────────────────────────────────────────────────
let _inventory  = null;
let _isAdmin    = false;
let _canManage  = false;   // admin or engineer

// ── Bootstrap ─────────────────────────────────────────────────
function initPage() {
  if (currentUser) {
    _isAdmin   = currentUser.privilege === 'admin';
    _canManage = currentUser.privilege !== 'user';
    const label = document.getElementById('devices-location-label');
    if (label) label.textContent = currentUser.place || '—';
  }
  document.addEventListener('click', e => {
    if (!e.target.closest('[id$="-dropdown-wrapper"]')) {
      _manageDropdownTypes.forEach(t => document.getElementById(`manage-${t}-dropdown`)?.classList.add('hidden'));
    }
  });
  loadDevicesPage();
}

async function loadDevicesPage() {
  _showLoading(true);
  try {
    const r = await fetch('/devices/api/inventory');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    _inventory = await r.json();
    _renderAll();
    _checkSimExpiry(_inventory.sims || []);
    _showButtonVisibility();
    _showLoading(false);
  } catch (e) {
    _showError('Failed to load device data. ' + e.message);
  }
}

// Silent refresh after mutations — no loading overlay flicker
async function _refreshInventory() {
  try {
    const r = await fetch('/devices/api/inventory');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    _inventory = await r.json();
    _renderAll();
    _checkSimExpiry(_inventory.sims || []);
  } catch (e) {
    showToast('Failed to refresh device data.', 'error');
  }
}

function _showButtonVisibility() {
  // Admin-only: Manage dropdowns
  const manageWrappers = [
    'manage-pluto-dropdown-wrapper', 'manage-mars-dropdown-wrapper',
    'manage-agwatch-dropdown-wrapper',
    'manage-modems-dropdown-wrapper', 'manage-laptops-dropdown-wrapper',
    'manage-sims-dropdown-wrapper',
  ];
  manageWrappers.forEach(id => {
    if (_isAdmin) document.getElementById(id)?.classList.remove('hidden');
  });

  // Clinic toggle — admin only (pluto/mars only)
  ['clinic-pluto-btn','clinic-mars-btn'].forEach(id => {
    if (_isAdmin) document.getElementById(id)?.classList.remove('hidden');
  });

  // Issue report — admin or engineer
  ['issue-pluto-btn','issue-mars-btn','issue-agwatch-btn','issue-modems-btn','issue-laptops-btn'].forEach(id => {
    if (_canManage) document.getElementById(id)?.classList.remove('hidden');
  });
}

// ── Manage dropdown ───────────────────────────────────────────

const _manageDropdownTypes = ['pluto','mars','agwatch','modems','laptops','sims'];

function toggleManageDropdown(type) {
  const dd = document.getElementById(`manage-${type}-dropdown`);
  if (!dd) return;
  const isOpen = !dd.classList.contains('hidden');
  // Close all
  _manageDropdownTypes.forEach(t => document.getElementById(`manage-${t}-dropdown`)?.classList.add('hidden'));
  if (!isOpen) dd.classList.remove('hidden');
}

function closeManageDropdown(type) {
  document.getElementById(`manage-${type}-dropdown`)?.classList.add('hidden');
}

// ── Tab switching ─────────────────────────────────────────────

let _activeDeviceTab = 'overview';

function switchDeviceTab(tab) {
  document.querySelectorAll('.dev-tab-btn').forEach(btn => {
    const active = btn.dataset.tab === tab;
    btn.classList.toggle('border-blue-600', active);
    btn.classList.toggle('text-blue-600', active);
    btn.classList.toggle('border-transparent', !active);
    btn.classList.toggle('text-slate-500', !active);
  });
  document.querySelectorAll('.dev-tab-pane').forEach(pane => {
    pane.classList.toggle('hidden', pane.id !== `dev-tab-${tab}`);
  });
  _activeDeviceTab = tab;
  if (tab === 'overview') _loadOverviewTab();
  else if (['pluto','mars','agwatch','modems','laptops'].includes(tab)) {
    _loadIssuesSection(tab);
    _loadSolutionsSection(tab);
  } else if (tab === 'sims') {
    _loadSimIssues();
  }
}

// ── Overview tab ──────────────────────────────────────────────

function _loadOverviewTab() {
  _renderDistributionCards();
  _loadRecentActivity();
}

function _renderDistributionCards() {
  if (!_inventory) return;
  const types = [
    { key: 'pluto',   label: 'Pluto',   icon: 'fa-robot',          color: 'violet' },
    { key: 'mars',    label: 'Mars',    icon: 'fa-satellite-dish',  color: 'rose' },
    { key: 'agwatch', label: 'Agwatch', icon: 'fa-clock',           color: 'teal' },
    { key: 'modems',  label: 'Modems',  icon: 'fa-wifi',            color: 'amber' },
    { key: 'laptops', label: 'Laptops', icon: 'fa-laptop',          color: 'indigo' },
    { key: 'sims',    label: 'SIMs',    icon: 'fa-sim-card',        color: 'sky' },
  ];
  const container = document.getElementById('overview-distribution');
  if (!container) return;
  container.innerHTML = types.map(t => {
    const allDevs = _inventory[t.key] || [];
    const devs = allDevs.filter(d => !d.removal_date);
    let available = 0, assigned = 0, faulty = 0;
    if (t.key === 'sims') {
      available = devs.filter(s => s.status === 'active' && !s.isExpired).length;
      faulty    = devs.filter(s => s.isExpired).length;
      assigned  = 0;
    } else {
      faulty   = devs.filter(d => d.faulty || d.has_issue).length;
      assigned = devs.filter(d => d.assigned_to && !d.faulty && !d.has_issue).length;
      available= devs.filter(d => !d.assigned_to && !d.faulty && !d.has_issue && !d.clinic_only && !d.lost).length;
    }
    return `
      <div class="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 cursor-pointer hover:shadow-md transition-shadow"
           onclick="switchDeviceTab('${t.key}')">
        <div class="flex items-center gap-2 mb-3">
          <div class="w-8 h-8 rounded-lg bg-${t.color}-100 flex items-center justify-center">
            <i class="fas ${t.icon} text-${t.color}-600 text-sm"></i>
          </div>
          <span class="text-sm font-semibold text-slate-700">${t.label}</span>
        </div>
        <div class="text-2xl font-bold text-slate-800 mb-1">${devs.length}</div>
        <div class="text-xs text-slate-500 space-y-0.5">
          <div><span class="inline-block w-2 h-2 rounded-full bg-green-400 mr-1"></span>${available} available</div>
          <div><span class="inline-block w-2 h-2 rounded-full bg-blue-400 mr-1"></span>${assigned} assigned</div>
          ${faulty > 0 ? `<div><span class="inline-block w-2 h-2 rounded-full bg-red-400 mr-1"></span>${faulty} issue</div>` : ''}
        </div>
      </div>`;
  }).join('');
}

async function _loadRecentActivity() {
  const container = document.getElementById('overview-activity');
  if (!container) return;
  container.innerHTML = '<div class="px-6 py-4 text-slate-400 text-sm">Loading…</div>';
  const types = ['pluto','mars','agwatch','modems','laptops','sims'];
  try {
    const all = await Promise.all(types.map(t =>
      fetch(`/devices/api/device-events?type=${t}`).then(r => r.json()).then(d => d.events || [])
    ));
    const merged = all.flat().sort((a, b) => (b.date || '').localeCompare(a.date || '')).slice(0, 20);
    if (!merged.length) {
      container.innerHTML = '<div class="px-6 py-8 text-center text-slate-400 text-sm">No activity recorded yet.</div>';
      return;
    }
    // Build SIM id → phoneNumber map for display
    const simPhoneMap = {};
    for (const s of (_inventory?.sims || [])) {
      if (s.id && s.phoneNumber) simPhoneMap[s.id] = s.phoneNumber;
    }
    const eventLabels = { assign:'Assigned', available:'Available', faulty:'Faulty', swap:'Swapped',
                          repair:'Repaired', retire:'Retired', discarded:'Discarded',
                          lost:'Lost', recharge:'Recharged', expired:'Expired' };
    const eventColors = { assign:'text-blue-600 bg-blue-50', available:'text-green-600 bg-green-50',
                          faulty:'text-red-600 bg-red-50', swap:'text-amber-600 bg-amber-50',
                          repair:'text-emerald-600 bg-emerald-50', retire:'text-slate-600 bg-slate-100',
                          discarded:'text-slate-600 bg-slate-100', lost:'text-red-600 bg-red-50',
                          recharge:'text-sky-600 bg-sky-50', expired:'text-red-600 bg-red-50' };
    container.innerHTML = merged.map(ev => {
      const displayId = simPhoneMap[ev.device_id] || ev.device_id;
      return `
      <div class="flex items-center gap-4 px-6 py-3 hover:bg-slate-50 transition-colors">
        <span class="text-xs px-2 py-0.5 rounded-full font-medium ${eventColors[ev.event_type] || 'text-slate-600 bg-slate-100'}">
          ${_esc(eventLabels[ev.event_type] || ev.event_type)}
        </span>
        <span class="font-mono text-sm text-slate-700 font-medium">${_esc(displayId)}</span>
        ${ev.homer_id ? `<span class="text-sm text-slate-500">→ ${_esc(ev.homer_id)}</span>` : ''}
        ${ev.notes ? `<span class="text-xs text-slate-400 truncate max-w-xs">${_esc(ev.notes)}</span>` : ''}
        <span class="ml-auto text-xs text-slate-400 whitespace-nowrap">${_fmtDate(ev.event_date || ev.date)} · ${_esc(ev.by)}</span>
      </div>`;
    }).join('');
  } catch (e) {
    container.innerHTML = '<div class="px-6 py-4 text-red-500 text-sm">Failed to load activity.</div>';
  }
}

// ── Issues section ────────────────────────────────────────────

async function _loadIssuesSection(type) {
  const container = document.getElementById(`issues-${type}`);
  if (!container) return;
  try {
    const r = await fetch(`/devices/api/issues?type=${type}`);
    const data = await r.json();
    const eventIssues = data.issues || [];

    // Fallback: also surface devices with faulty/has_issue flag in inventory (no event file yet)
    const eventDeviceIds = new Set(eventIssues.map(e => e.device_id));
    const allInvDevices = type === 'agwatch' ? (_inventory?.agwatch || []) : (type === 'sims' ? (_inventory?.sims || []) : (_inventory?.[type] || []));
    const invIssues = allInvDevices
      .filter(d => (d.faulty || d.has_issue) && !eventDeviceIds.has(d.id))
      .map(d => ({ device_id: d.id, event_type: 'faulty', date: null, by: '—', notes: '', homer_id: d.assigned_to?.homerID || null }));

    const issues = [...eventIssues, ...invIssues];

    // Determine which device IDs are retired
    const retiredIds = new Set(allInvDevices.filter(d => d.removal_date).map(d => d.id));

    if (!issues.length) {
      container.innerHTML = `
        <div class="bg-white rounded-2xl border border-slate-200 shadow-sm px-6 py-5 flex items-center gap-3 text-slate-400">
          <i class="fas fa-check-circle text-green-400"></i>
          <span class="text-sm">No open issues.</span>
        </div>`;
      return;
    }

    const activeIssues  = issues.filter(ev => !retiredIds.has(ev.device_id));
    const retiredIssues = issues.filter(ev =>  retiredIds.has(ev.device_id));

    const _attachLink = (ev, label, color) => {
      if (!ev?.attachment) return '';
      const url = `/devices/api/download-event-attachment?type=${encodeURIComponent(type)}&device_id=${encodeURIComponent(ev.device_id)}&event_id=${encodeURIComponent(ev.id)}`;
      return `<a href="${url}" class="inline-flex items-center gap-1 text-xs font-medium ${color} hover:underline" target="_blank">
        <i class="fas fa-paperclip"></i>${_esc(label)}
      </a>`;
    };

    container.innerHTML = `
      <div class="bg-white rounded-2xl border border-red-200 shadow-sm overflow-hidden">
        <div class="flex items-center gap-3 px-6 py-4 border-b border-red-100 bg-red-50">
          <i class="fas fa-exclamation-triangle text-red-500"></i>
          <h3 class="text-base font-semibold text-red-800">Open Issues (${activeIssues.length})</h3>
        </div>
        <div class="divide-y divide-slate-100">
          ${activeIssues.map(ev => `
            <div class="px-6 py-4 space-y-2">
              <div class="flex items-center gap-2">
                <span class="font-mono text-sm font-semibold text-slate-800">${_esc(ev.device_id)}</span>
                ${ev.homer_id ? `<span class="text-xs text-slate-500">Patient: ${_esc(ev.homer_id)}</span>` : ''}
              </div>
              ${ev.notes ? `<p class="text-sm text-slate-600"><span class="text-xs font-semibold text-red-600 mr-1">Issue:</span>${_esc(ev.notes)}</p>` : ''}
              <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                <span class="text-red-600 font-medium"><i class="fas fa-exclamation-circle mr-1"></i>${_fmtDate(ev.issue_occur_date || ev.event_date || ev.date)}</span>
                ${ev.by ? `<span class="text-slate-500">· ${_esc(ev.by)}</span>` : ''}
                ${_attachLink(ev, 'Report doc', 'text-blue-600')}
              </div>
              ${_canManage ? `
                <div class="pt-2">
                  <button onclick="openIssueModal('${type}', '${_esc(ev.device_id)}')"
                          class="px-3 py-1.5 text-xs font-semibold bg-green-100 text-green-700 rounded-lg hover:bg-green-200 active:scale-95 transition-all">
                    <i class="fas fa-check mr-1"></i>Resolve
                  </button>
                </div>` : ''}
            </div>`).join('')}
          ${retiredIssues.map(ev => `
            <div class="flex items-start gap-4 px-6 py-4 opacity-40 pointer-events-none">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1">
                  <span class="font-mono text-sm font-medium text-slate-500 line-through">${_esc(ev.device_id)}</span>
                  <span class="text-xs text-slate-400 italic">Retired</span>
                </div>
                ${ev.notes ? `<p class="text-sm text-slate-500">${_esc(ev.notes)}</p>` : ''}
                ${ev.date ? `<p class="text-xs text-slate-400 mt-1">${_fmtDate(ev.event_date || ev.date)}</p>` : ''}
              </div>
            </div>`).join('')}
        </div>
      </div>`;
  } catch (e) { container.innerHTML = ''; }
}

async function _loadSolutionsSection(type) {
  const container = document.getElementById(`solutions-${type}`);
  if (!container) return;
  try {
    const r = await fetch(`/devices/api/solutions?type=${type}`);
    const data = await r.json();
    const solutions = data.solutions || [];
    if (!solutions.length) { container.innerHTML = ''; return; }

    const _attachLink = (ev, label, color) => {
      if (!ev?.attachment) return '';
      const url = `/devices/api/download-event-attachment?type=${encodeURIComponent(type)}&device_id=${encodeURIComponent(ev.device_id)}&event_id=${encodeURIComponent(ev.id)}`;
      return `<a href="${url}" class="inline-flex items-center gap-1 text-xs font-medium ${color} hover:underline" target="_blank">
        <i class="fas fa-paperclip"></i>${_esc(label)}
      </a>`;
    };

    container.innerHTML = `
      <details class="bg-white rounded-2xl border border-emerald-200 shadow-sm overflow-hidden">
        <summary class="flex items-center gap-3 px-6 py-4 border-b border-emerald-100 bg-emerald-50 cursor-pointer">
          <i class="fas fa-check-circle text-emerald-500"></i>
          <h3 class="text-base font-semibold text-emerald-800">Resolved Issues (${solutions.length})</h3>
          <i class="fas fa-chevron-down ml-auto text-emerald-400 text-xs"></i>
        </summary>
        <div class="divide-y divide-slate-100">
          ${solutions.map(pair => `
            <div class="px-6 py-4 space-y-2">
              <div class="flex items-center gap-2">
                <span class="font-mono text-sm font-semibold text-slate-800">${_esc(pair.faulty.device_id)}</span>
                ${pair.faulty.homer_id ? `<span class="text-xs text-slate-500">Patient: ${_esc(pair.faulty.homer_id)}</span>` : ''}
              </div>
              <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                <span class="text-red-500 font-medium"><i class="fas fa-exclamation-circle mr-1"></i>${_fmtDate(pair.faulty.issue_occur_date || pair.faulty.event_date || pair.faulty.date)}</span>
                <i class="fas fa-arrow-right text-slate-300"></i>
                <span class="text-emerald-600 font-medium"><i class="fas fa-check-circle mr-1"></i>${_fmtDate(pair.resolved.event_date || pair.resolved.date)}</span>
                <span class="text-slate-400">· ${_esc(pair.resolved.event_type)} · ${_esc(pair.resolved.by)}</span>
              </div>
              ${pair.faulty.notes ? `<p class="text-sm text-slate-600"><span class="text-xs font-semibold text-red-500 mr-1">Issue:</span>${_esc(pair.faulty.notes)}</p>` : ''}
              ${pair.resolved.notes ? `<p class="text-sm text-slate-600"><span class="text-xs font-semibold text-emerald-600 mr-1">Resolution:</span>${_esc(pair.resolved.notes)}</p>` : ''}
              <div class="flex items-center gap-3 pt-1">
                ${_attachLink(pair.faulty, 'Fault doc', 'text-blue-600')}
                ${_attachLink(pair.resolved, 'Resolution doc', 'text-emerald-600')}
              </div>
            </div>`).join('')}
        </div>
      </details>`;
  } catch (e) { container.innerHTML = ''; }
}

function _loadSimIssues() {
  const container = document.getElementById('issues-sims');
  if (!container || !_inventory) return;
  const expiredSims = (_inventory.sims || []).filter(s => !s.removal_date && (s.isExpired || (s.daysUntilExpiry !== undefined && s.daysUntilExpiry <= 3)));
  if (!expiredSims.length) { container.innerHTML = ''; return; }
  container.innerHTML = `
    <div class="bg-white rounded-2xl border border-red-200 shadow-sm overflow-hidden">
      <div class="flex items-center gap-3 px-6 py-4 border-b border-red-100 bg-red-50">
        <i class="fas fa-exclamation-triangle text-red-500"></i>
        <h3 class="text-base font-semibold text-red-800">SIM Issues — Expired / Expiring Soon (${expiredSims.length})</h3>
      </div>
      <div class="divide-y divide-slate-100">
        ${expiredSims.map(s => `
          <div class="flex items-center gap-4 px-6 py-3">
            <span class="font-mono text-sm font-medium text-slate-800">${_esc(s.phoneNumber)}</span>
            <span class="text-xs text-slate-500">${_esc(s.network || '—')}</span>
            ${_simExpiryBadge(s)}
            ${_isAdmin ? `<button onclick="openRechargeSimModal('${_esc(s.id)}')" class="ml-auto px-3 py-1.5 text-xs font-semibold bg-sky-600 text-white rounded-lg hover:bg-sky-700 active:scale-95 transition-all"><i class="fas fa-bolt mr-1"></i>Recharge</button>` : ''}
          </div>`).join('')}
      </div>
    </div>`;
}

function _fmtDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric' })
           + ' ' + d.toLocaleTimeString('en-GB', { hour:'2-digit', minute:'2-digit' });
  } catch { return iso; }
}

// ── Render all sections ───────────────────────────────────────

function _renderAll() {
  _renderSection('pluto',  _inventory.pluto   || []);
  _renderSection('mars',   _inventory.mars    || []);
  _renderAgwatches(_inventory.agwatch || []);
  _renderModems(_inventory.modems   || []);
  _renderSims(_inventory.sims      || []);
  _renderLaptops(_inventory.laptops  || []);
  document.getElementById('devices-tabs-wrapper').classList.remove('hidden');
  document.getElementById('devices-tab-panes').classList.remove('hidden');
  switchDeviceTab(_activeDeviceTab || 'overview');
}

// ── Pluto / Mars ──────────────────────────────────────────────

function _renderSection(type, devices) {
  const container = document.getElementById(`table-${type}`);
  if (!container) return;

  const active   = devices.filter(d => !d.removal_date);
  const assigned = active.filter(d => d.assigned_to).length;
  const avail    = active.filter(d => !d.assigned_to && !d.faulty && !d.clinic_only).length;
  document.getElementById(`badge-${type}`).textContent =
    `${active.length} total · ${avail} available · ${assigned} assigned`;

  if (active.length === 0) { container.innerHTML = _emptyRow('No devices in inventory'); return; }

  container.innerHTML = `
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-slate-100 text-left">
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-32">Device ID</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Serial</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-32">Status</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Assigned Patient</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-50">
        ${devices.map(d => {
          const retired = !!d.removal_date;
          const rowClass = retired ? 'opacity-40' : 'hover:bg-slate-50 transition-colors';
          return `
          <tr class="${rowClass}">
            <td class="px-6 py-3.5 font-mono font-medium text-slate-800">${_esc(d.id)}</td>
            <td class="px-6 py-3.5 text-slate-600">${_esc(d.serial) || '—'}</td>
            <td class="px-6 py-3.5">${_statusBadge(d)}</td>
            <td class="px-6 py-3.5">${retired ? '<span class="text-xs text-slate-400 italic">—</span>' : _assignedCell(d.assigned_to)}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;
}

// ── Agwatch ───────────────────────────────────────────────────

function _renderAgwatches(devices) {
  const active   = devices.filter(d => !d.removal_date && !d.lost);
  const assigned = active.filter(d => d.assigned_to).length;
  const avail    = active.filter(d => !d.assigned_to && !d.has_issue && !d.clinic_only).length;
  document.getElementById('badge-agwatch').textContent =
    `${active.length} total · ${avail} available · ${assigned} assigned`;

  const container = document.getElementById('table-agwatch');
  if (!container) return;
  if (devices.length === 0) { container.innerHTML = _emptyRow('No watches in inventory'); return; }

  container.innerHTML = `
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-slate-100 text-left">
          <th class="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Device ID</th>
          <th class="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Serial</th>
          <th class="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-28">Status</th>
          <th class="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Assigned Patient</th>
          <th class="px-5 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Limb</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-50">
        ${devices.map(d => {
          const retired = !!d.removal_date;
          const limb = d.assigned_to?.limb || '—';
          return `
          <tr class="${retired ? 'opacity-40' : 'hover:bg-slate-50 transition-colors'}">
            <td class="px-5 py-3.5 font-mono font-medium text-slate-800">${_esc(d.id)}</td>
            <td class="px-5 py-3.5 text-slate-600">${_esc(d.serial) || '—'}</td>
            <td class="px-5 py-3.5">${_watchStatusBadge(d)}</td>
            <td class="px-5 py-3.5">${retired ? '<span class="text-xs text-slate-400 italic">—</span>' : _assignedCell(d.assigned_to)}</td>
            <td class="px-5 py-3.5 text-slate-500 text-xs">${retired ? '—' : _esc(limb)}</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table>`;
}

// ── Modems ────────────────────────────────────────────────────

function _renderModems(devices) {
  const container = document.getElementById('table-modems');
  if (!container) return;
  const active   = devices.filter(d => !d.removal_date);
  const assigned = active.filter(d => d.assigned_to).length;
  const avail    = active.filter(d => !d.assigned_to).length;
  document.getElementById('badge-modems').textContent =
    `${active.length} total · ${avail} available · ${assigned} assigned`;

  if (devices.length === 0) { container.innerHTML = _emptyRow('No modems in inventory'); return; }

  container.innerHTML = `
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-slate-100 text-left">
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-32">Modem ID</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Serial</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">SIM Card</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-28">Status</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Assigned Patient</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-50">
        ${devices.map(d => {
          const simCell = d.sim_info
            ? `<span class="font-medium text-slate-700">${_esc(d.sim_info.network || '—')}</span>
               <span class="text-xs text-slate-400 ml-1">${_esc(d.sim_info.phoneNumber || '')}</span>`
            : '<span class="text-slate-400 italic text-xs">Not linked</span>';
          const hasIssue = !!d.has_issue;
          const retired  = !!d.removal_date;
          const statusBadge = hasIssue
            ? '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-700"><i class="fas fa-exclamation-circle"></i>Issue</span>'
            : d.assigned_to
              ? '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-700"><i class="fas fa-user-check"></i>Assigned</span>'
              : '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-700"><i class="fas fa-check-circle"></i>Available</span>';
          return `
            <tr class="${retired ? 'opacity-40' : 'hover:bg-slate-50 transition-colors'}">
              <td class="px-6 py-3.5 font-mono font-medium text-slate-800">${_esc(d.id)}</td>
              <td class="px-6 py-3.5 text-slate-600">${_esc(d.serial) || '—'}</td>
              <td class="px-6 py-3.5">${retired ? '<span class="text-xs text-slate-400 italic">—</span>' : simCell}</td>
              <td class="px-6 py-3.5">${retired ? '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-400"><i class="fas fa-archive"></i>Retired</span>' : statusBadge}</td>
              <td class="px-6 py-3.5">${retired ? '<span class="text-xs text-slate-400 italic">—</span>' : _assignedCell(d.assigned_to)}</td>
            </tr>`;
        }).join('')}
      </tbody>
    </table>`;
}

// ── SIM Cards ─────────────────────────────────────────────────

function _renderSims(sims) {
  const container = document.getElementById('table-sims');
  if (!container) return;

  const activeSims = sims.filter(s => !s.removal_date);
  const expired = activeSims.filter(s => s.isExpired).length;
  document.getElementById('badge-sims').textContent =
    expired > 0 ? `${activeSims.length} total · ${expired} expired` : `${activeSims.length} total`;

  if (sims.length === 0) { container.innerHTML = _emptyRow('No SIM cards recorded'); return; }

  container.innerHTML = `
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-slate-100 text-left">
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Phone</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Network</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Plan</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Modem</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Recharge Cycle</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-50">
        ${sims.map(s => {
          const modemLabel = s.modem_id
            ? `<span class="font-mono text-xs text-slate-700">${_esc(s.modem_id)}</span>`
            : '<span class="text-slate-400 italic text-xs">Not linked</span>';
          const planLabel = s.dataPlan ? `${_esc(s.dataPlan)}d` : '—';
          const retired = !!s.removal_date;
          return `
            <tr class="${retired ? 'opacity-40' : 'hover:bg-slate-50 transition-colors'}">
              <td class="px-6 py-3.5 font-mono ${retired ? 'text-slate-400 line-through' : 'text-slate-800'}">${_esc(s.phoneNumber || '—')}</td>
              <td class="px-6 py-3.5 text-slate-600">${retired ? '—' : _esc(s.network || '—')}</td>
              <td class="px-6 py-3.5 text-slate-600">${retired ? '—' : planLabel}</td>
              <td class="px-6 py-3.5">${retired ? '—' : modemLabel}</td>
              <td class="px-6 py-3.5">
                ${retired
                  ? '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-400"><i class="fas fa-archive"></i>Retired</span>'
                  : `<div class="flex items-center gap-3">
                      ${_simCycleWidget(s)}
                      ${_isAdmin ? `<button onclick="openRechargeSimModal('${_esc(s.id)}')" class="ml-auto flex-shrink-0 px-2.5 py-1 text-xs font-semibold text-white bg-sky-600 rounded-lg hover:bg-sky-700 active:scale-95 transition-all"><i class="fas fa-bolt mr-1"></i>Recharge</button>` : ''}
                    </div>`}
              </td>
            </tr>`;
        }).join('')}
      </tbody>
    </table>`;
}

function _simExpiryBadge(s) {
  if (!s.expiryDate) return '<span class="text-slate-400 italic text-xs">No expiry set</span>';
  if (s.isExpired)
    return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-700"><i class="fas fa-times-circle"></i>Expired</span>`;
  const d = s.daysUntilExpiry;
  if (d <= 3)
    return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-700"><i class="fas fa-exclamation-circle"></i>Expires in ${d}d</span>`;
  if (d <= 5)
    return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700"><i class="fas fa-exclamation-triangle"></i>Expires in ${d}d</span>`;
  return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-700"><i class="fas fa-check-circle"></i>${_esc(s.expiryDate)}</span>`;
}

function _simCycleWidget(s) {
  if (!s.rechargeDate && !s.expiryDate) {
    return '<span class="text-slate-400 italic text-xs">No dates set</span>';
  }

  if (!s.dataPlan || !s.rechargeDate || !s.expiryDate) {
    return `<div class="space-y-1">
      ${s.rechargeDate ? `<div class="text-xs text-slate-500">Recharged: <span class="font-medium text-slate-700">${_esc(s.rechargeDate)}</span></div>` : ''}
      ${_simExpiryBadge(s)}
    </div>`;
  }

  const planDays  = parseInt(s.dataPlan);
  const recharge  = new Date(s.rechargeDate);
  const now       = new Date();
  const elapsed   = Math.max(0, Math.floor((now - recharge) / 86400000));
  const rawPct    = Math.min(100, Math.round((elapsed / planDays) * 100));
  const daysLeft  = s.daysUntilExpiry;

  let barColor, textColor;
  if (s.isExpired || daysLeft <= 3)        { barColor = 'bg-red-500';   textColor = 'text-red-600'; }
  else if (daysLeft <= 5)                   { barColor = 'bg-amber-400'; textColor = 'text-amber-600'; }
  else                                      { barColor = 'bg-emerald-400'; textColor = 'text-emerald-700'; }

  const pctLabel = s.isExpired ? 'EXPIRED' : `${elapsed}/${planDays}d`;
  const expLabel = s.isExpired
    ? '<span class="text-xs font-semibold text-red-600">EXPIRED</span>'
    : `<span class="text-xs ${textColor} font-medium">${daysLeft}d left</span>`;

  return `<div class="space-y-1 min-w-[180px]">
    <div class="text-xs text-slate-500">Recharged: <span class="font-medium text-slate-700">${_esc(s.rechargeDate)}</span></div>
    <div class="flex items-center gap-2">
      <div class="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div class="${barColor} h-2 rounded-full transition-all" style="width:${rawPct}%"></div>
      </div>
      <span class="text-xs text-slate-400 whitespace-nowrap">${_esc(pctLabel)}</span>
    </div>
    <div class="flex items-center gap-2">
      <span class="text-xs text-slate-400">Expires: <span class="text-slate-600">${_esc(s.expiryDate)}</span></span>
      ${expLabel}
    </div>
  </div>`;
}

// ── Laptops ───────────────────────────────────────────────────

function _renderLaptops(devices) {
  const container = document.getElementById('table-laptops');
  if (!container) return;

  const active   = devices.filter(d => !d.removal_date);
  const assigned = active.filter(d => d.assigned_to).length;
  const avail    = active.filter(d => !d.assigned_to).length;
  document.getElementById('badge-laptops').textContent =
    `${active.length} total · ${avail} available · ${assigned} assigned`;

  if (devices.length === 0) { container.innerHTML = _emptyRow('No laptops in inventory'); return; }

  container.innerHTML = `
    <table class="w-full text-sm">
      <thead>
        <tr class="border-b border-slate-100 text-left">
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-32">Laptop ID</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Serial</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide w-32">Status</th>
          <th class="px-6 py-3 text-xs font-semibold text-slate-500 uppercase tracking-wide">Assigned Patient</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-slate-50">
        ${devices.map(d => {
          const hasIssue = !!d.has_issue;
          const retired  = !!d.removal_date;
          const statusBadge = hasIssue
            ? '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-700"><i class="fas fa-exclamation-circle"></i>Issue</span>'
            : d.assigned_to
              ? '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-700"><i class="fas fa-user-check"></i>Assigned</span>'
              : '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-700"><i class="fas fa-check-circle"></i>Available</span>';
          return `
            <tr class="${retired ? 'opacity-40' : 'hover:bg-slate-50 transition-colors'}">
              <td class="px-6 py-3.5 font-mono font-medium text-slate-800">${_esc(d.id)}</td>
              <td class="px-6 py-3.5 text-slate-600">${_esc(d.serial) || '—'}</td>
              <td class="px-6 py-3.5">${retired ? '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-400"><i class="fas fa-archive"></i>Retired</span>' : statusBadge}</td>
              <td class="px-6 py-3.5">${retired ? '<span class="text-xs text-slate-400 italic">—</span>' : _assignedCell(d.assigned_to)}</td>
            </tr>`;
        }).join('')}
      </tbody>
    </table>`;
}

// ── Cell helpers ──────────────────────────────────────────────

function _statusBadge(d) {
  if (d.removal_date) return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-400"><i class="fas fa-archive"></i>Retired</span>';
  if (d.faulty)      return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-700"><i class="fas fa-exclamation-circle"></i>Issue</span>';
  if (d.clinic_only) return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-500"><i class="fas fa-hospital"></i>Clinic Only</span>';
  if (d.assigned_to) return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-700"><i class="fas fa-user-check"></i>Assigned</span>';
  return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-700"><i class="fas fa-check-circle"></i>Available</span>';
}

function _watchStatusBadge(d) {
  if (d.removal_date) return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-400"><i class="fas fa-archive"></i>Retired</span>';
  if (d.has_issue)   return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-700"><i class="fas fa-exclamation-circle"></i>Issue</span>';
  if (d.lost)        return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-500"><i class="fas fa-times-circle"></i>Lost</span>';
  if (d.clinic_only) return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-500"><i class="fas fa-hospital"></i>Clinic Only</span>';
  if (d.assigned_to) return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-blue-100 text-blue-700"><i class="fas fa-user-check"></i>Assigned</span>';
  return '<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-700"><i class="fas fa-check-circle"></i>Available</span>';
}

function _assignedCell(assigned_to) {
  if (!assigned_to) return '<span class="text-slate-400 italic text-xs">Not Assigned</span>';
  const homer    = _esc(assigned_to.homerID    || '—');
  const hospital = _esc(assigned_to.hospitalID || '—');
  return `<a href="/patients/${_esc(assigned_to.homerID)}" class="inline-flex items-center gap-2 group">
    <span class="font-medium text-blue-600 group-hover:text-blue-800 group-hover:underline">${homer}</span>
    <span class="text-xs text-slate-400">${hospital}</span>
  </a>`;
}

function _emptyRow(msg) {
  return `<div class="px-6 py-8 text-center text-sm text-slate-400 italic">${msg}</div>`;
}

// ── SIM expiry notification ───────────────────────────────────

function _checkSimExpiry(sims) {
  const banner   = document.getElementById('sim-expiry-banner');
  const warnings = sims.filter(s => !s.removal_date && s.daysUntilExpiry !== undefined && s.daysUntilExpiry <= 5);
  if (!warnings.length) {
    banner?.classList.add('hidden');
    return;
  }
  const expired  = warnings.filter(s => s.isExpired);
  const expiring = warnings.filter(s => !s.isExpired);
  const parts    = [];
  if (expired.length)  parts.push(`${expired.length} SIM${expired.length > 1 ? 's' : ''} expired`);
  if (expiring.length) parts.push(`${expiring.length} SIM${expiring.length > 1 ? 's' : ''} expiring in ≤5 days`);
  const msg = parts.join(', ');
  document.getElementById('sim-expiry-msg').textContent = msg;
  banner?.classList.remove('hidden');
  showToast(msg, expired.length ? 'error' : 'info');
}

// ── Clinic Toggle Modal ───────────────────────────────────────

let _clinicType = null;

function openClinicModal(type) {
  _clinicType = type;
  const labels = { pluto: 'Pluto', mars: 'Mars' };
  document.getElementById('clinic-modal-title').textContent = `Toggle Clinic — ${labels[type] || type}`;
  _setError('clinic-modal-error', '');
  document.getElementById('clinic-current-status').textContent = '';

  const sel = document.getElementById('clinic-device-select');
  sel.innerHTML = '<option value="">Select device…</option>';

  const allDevices = _inventory?.[type] || [];
  // Eligible for clinic toggle:
  //   - Currently clinic (can be cleared): no restrictions
  //   - Currently available (can be set to clinic): not assigned, not faulty/issue
  // Exclude: assigned devices, devices with issues (Issue overrides all)
  const devices = allDevices.filter(d =>
    !d.removal_date && (
      d.clinic_only ||                                      // already clinic → can clear it
      (!d.assigned_to && !d.faulty && !d.has_issue)         // available → can set to clinic
    )
  );

  if (!devices.length) {
    _setError('clinic-modal-error', 'No eligible devices. Devices must be Available (not assigned, not issue) to change clinic status.');
  }

  devices.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d.id;
    const label = d.clinic_only ? `${d.id} — Clinic Only` : `${d.id} — Available`;
    opt.textContent = label;
    sel.appendChild(opt);
  });

  sel.onchange = () => {
    const d = devices.find(x => x.id === sel.value);
    const info = document.getElementById('clinic-current-status');
    if (d) {
      info.textContent = d.clinic_only
        ? 'Currently: Clinic Only → will become Available'
        : 'Currently: Available → will become Clinic Only (replaces any existing clinic device)';
      const btn = document.getElementById('clinic-save-btn');
      btn.textContent = d.clinic_only ? 'Mark Available' : 'Mark Clinic Only';
    } else {
      info.textContent = '';
    }
  };

  document.getElementById('clinic-modal').classList.remove('hidden');
}

function closeClinicModal() {
  document.getElementById('clinic-modal').classList.add('hidden');
}

async function saveClinicToggle() {
  const device_id = document.getElementById('clinic-device-select').value;
  if (!device_id) { _setError('clinic-modal-error', 'Please select a device.'); return; }

  const devices = _inventory?.[_clinicType] || [];
  const d = devices.find(x => x.id === device_id);
  if (!d) return;

  _setError('clinic-modal-error', '');
  try {
    const r = await fetch('/devices/api/toggle-clinic', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_type: _clinicType, device_id }),
    });
    const res = await r.json();
    if (res.error) { _setError('clinic-modal-error', res.error); return; }
    closeClinicModal();
    showToast(res.clinic_only ? 'Marked as clinic-only' : 'Marked as available', 'success');
    await _refreshInventory();
  } catch (e) {
    _setError('clinic-modal-error', 'Network error — please try again.');
  }
}

// ── Issue Report Modal ────────────────────────────────────────

let _issueType = null;

function openIssueModal(type, preselectedId) {
  _issueType = type;
  const labels = { pluto: 'Pluto', mars: 'Mars', agwatch: 'Agwatch', modems: 'Modem', laptops: 'Laptop' };
  document.getElementById('issue-modal-title').textContent = `Report / Resolve Issue — ${labels[type] || type}`;
  _setError('issue-modal-error', '');
  document.getElementById('issue-device-info').classList.add('hidden');
  document.getElementById('issue-occur-date-info').classList.add('hidden');
  document.getElementById('issue-swap-section').classList.add('hidden');
  document.getElementById('issue-notes').value = '';
  document.getElementById('issue-attachment-file').value = '';
  document.getElementById('issue-resolve-date').value = '';
  document.getElementById('issue-resolve-date-section').classList.add('hidden');
  document.getElementById('issue-occurred-date').value = '';
  document.getElementById('issue-occurred-date-section').classList.add('hidden');

  const sel = document.getElementById('issue-device-select');
  sel.innerHTML = '<option value="">Select device…</option>';

  const devices = type === 'agwatch' ? (_inventory?.agwatch || []) : (_inventory?.[type] || []);
  devices.filter(d => !d.lost && !d.removal_date && (!d.assigned_to || d.faulty || d.has_issue)).forEach(d => {
    const opt = document.createElement('option');
    opt.value = d.id;
    const hasIssue = d.faulty || d.has_issue;
    opt.textContent = hasIssue ? `${d.id} — Has Issue` : `${d.id} — OK`;
    sel.appendChild(opt);
  });

  if (preselectedId) {
    sel.value = preselectedId;
    onIssueDeviceChange();
  }
  document.getElementById('issue-modal').classList.remove('hidden');
}

function closeIssueModal() {
  document.getElementById('issue-modal').classList.add('hidden');
}

function onIssueDeviceChange() {
  const type    = _issueType;
  const sel     = document.getElementById('issue-device-select');
  const devices = type === 'agwatch' ? (_inventory?.agwatch || []) : (_inventory?.[type] || []);
  const d = devices.find(x => x.id === sel.value);

  const infoEl  = document.getElementById('issue-device-info');
  const swapEl  = document.getElementById('issue-swap-section');
  const saveBtn = document.getElementById('issue-save-btn');

  if (!d) {
    infoEl.classList.add('hidden');
    swapEl.classList.add('hidden');
    _clearDateBounds();
    return;
  }

  // Fetch patient enrollment date and device issue date for validation
  _setDateValidationBounds(type, sel.value);

  // Attach real-time keyboard validation for date inputs
  _attachDateKeyboardValidation('issue-occurred-date', 'issue-modal-error');
  _attachDateKeyboardValidation('issue-resolve-date', 'issue-modal-error');

  const hasIssue = d.faulty || d.has_issue;

  // Show status info
  infoEl.classList.remove('hidden');
  infoEl.innerHTML = `
    <div>Status: ${hasIssue ? '<strong class="text-red-600">Has Issue</strong>' : '<strong class="text-green-600">OK</strong>'}</div>
    ${d.assigned_to ? `<div>Assigned to: <strong>${_esc(d.assigned_to.homerID)}</strong></div>` : '<div>Not assigned</div>'}`;

  if (hasIssue) {
    saveBtn.textContent = 'Resolve Issue';
    saveBtn.className = 'px-5 py-2 text-sm font-semibold text-white bg-green-600 rounded-xl hover:bg-green-700 active:scale-95 transition-all';
    swapEl.classList.add('hidden');
    document.getElementById('issue-resolve-date-section').classList.remove('hidden');
    document.getElementById('issue-occurred-date-section').classList.add('hidden');
    // Fetch issue_occur_date from device events
    document.getElementById('issue-occur-date-info').classList.add('hidden');
    fetch(`/devices/api/device-events?type=${encodeURIComponent(type)}&device_id=${encodeURIComponent(sel.value)}`)
      .then(r => r.json())
      .then(data => {
        const events = (data.events || []).slice().sort((a, b) => (b.date || '').localeCompare(a.date || ''));
        const faultyEv = events.find(e => e.event_type === 'faulty' && e.issue_occur_date);
        if (faultyEv?.issue_occur_date) {
          document.getElementById('issue-occur-date-value').textContent =
            faultyEv.issue_occur_date.slice(0, 16).replace('T', ' ');
          document.getElementById('issue-occur-date-info').classList.remove('hidden');
        }
      }).catch(() => {});
  } else {
    document.getElementById('issue-resolve-date-section').classList.add('hidden');
    document.getElementById('issue-occurred-date-section').classList.remove('hidden');
    saveBtn.textContent = 'Report Issue';
    saveBtn.className = 'px-5 py-2 text-sm font-semibold text-white bg-red-600 rounded-xl hover:bg-red-700 active:scale-95 transition-all';

    // If device is assigned, offer swap (only show available devices)
    if (d.assigned_to) {
      swapEl.classList.remove('hidden');
      const allDevices = type === 'agwatch' ? (_inventory?.agwatch || []) : (_inventory?.[type] || []);
      const swapSel = document.getElementById('issue-swap-select');
      swapSel.innerHTML = '<option value="">No swap — just mark as issue</option>';
      allDevices.forEach(av => {
        if (av.id === d.id) return;
        if (av.assigned_to || av.faulty || av.has_issue || av.clinic_only || av.lost || av.removal_date) return;
        const opt = document.createElement('option');
        opt.value = av.id;
        opt.textContent = `${av.id} (${av.serial || 'no serial'})`;
        swapSel.appendChild(opt);
      });
    } else {
      swapEl.classList.add('hidden');
    }
  }
}

async function _setDateValidationBounds(dtype, deviceId) {
  try {
    const res = await fetch('/devices/api/device-validation-dates', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_type: dtype, device_id: deviceId }),
    });

    if (!res.ok) {
      console.error(`API error: ${res.status} ${res.statusText}`);
      _clearDateBounds();
      return;
    }

    const data = await res.json();
    if (!data.enroll_date && !data.issue_occur_date) {
      _clearDateBounds();
      return;
    }

    const occurrInput = document.getElementById('issue-occurred-date');
    const resolveInput = document.getElementById('issue-resolve-date');
    const today = new Date().toISOString().split('T')[0];

    // Set bounds for issue-occurred-date (Report Issue flow)
    if (data.enroll_date) {
      occurrInput.min = data.enroll_date;
    } else {
      occurrInput.removeAttribute('min');
    }
    occurrInput.max = today;

    // Set bounds for issue-resolve-date (Resolve Issue flow)
    if (data.issue_occur_date) {
      resolveInput.min = data.issue_occur_date;
      resolveInput.max = today;
    } else {
      resolveInput.removeAttribute('min');
      resolveInput.max = today;
    }
  } catch (e) {
    console.error('Failed to set date bounds:', e);
    _clearDateBounds();
  }
}

function _clearDateBounds() {
  const occurrInput = document.getElementById('issue-occurred-date');
  const resolveInput = document.getElementById('issue-resolve-date');
  occurrInput.removeAttribute('min');
  occurrInput.removeAttribute('max');
  resolveInput.removeAttribute('min');
  resolveInput.removeAttribute('max');
  // Remove keyboard validation listeners
  if (occurrInput._keyboardValidate) {
    occurrInput.removeEventListener('input', occurrInput._keyboardValidate);
    occurrInput.removeEventListener('change', occurrInput._keyboardValidate);
  }
  if (resolveInput._keyboardValidate) {
    resolveInput.removeEventListener('input', resolveInput._keyboardValidate);
    resolveInput.removeEventListener('change', resolveInput._keyboardValidate);
  }
}

function _attachDateKeyboardValidation(inputId, errorId) {
  // Real-time validation for keyboard-entered dates against min/max constraints
  const input = document.getElementById(inputId);
  if (!input) return;

  // Remove previous listeners to avoid duplicates
  if (input._keyboardValidate) {
    input.removeEventListener('input', input._keyboardValidate);
    input.removeEventListener('change', input._keyboardValidate);
  }

  input._keyboardValidate = () => {
    if (!input.value) {
      _setError(errorId, '');
      return;
    }

    const value = input.value;
    const today = new Date().toISOString().split('T')[0];
    let errorMsg = '';

    // Check min constraint
    if (input.min && value < input.min) {
      errorMsg = `Date cannot be before ${_formatDateForKeyboardValidation(input.min)}.`;
    }

    // Check max constraint
    if (!errorMsg && input.max && value > input.max) {
      errorMsg = `Date cannot be after ${_formatDateForKeyboardValidation(input.max)}.`;
    }

    _setError(errorId, errorMsg);
  };

  input.addEventListener('input', input._keyboardValidate);
  input.addEventListener('change', input._keyboardValidate);
}

function _formatDateForKeyboardValidation(dateStr) {
  // Convert YYYY-MM-DD to readable format (e.g., "30 Apr 2026")
  try {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  } catch {
    return dateStr;
  }
}

function _hasDateValidationErrors(errorElementId) {
  // Check if date validation error element has visible errors
  const el = document.getElementById(errorElementId);
  return el && !el.classList.contains('hidden') && el.textContent.trim();
}

async function saveIssueAction() {
  // Check for date validation errors before proceeding
  if (_hasDateValidationErrors('issue-modal-error')) {
    _setError('issue-modal-error', 'Please fix the date validation errors before submitting.');
    return;
  }

  const device_id = document.getElementById('issue-device-select').value;
  if (!device_id) { _setError('issue-modal-error', 'Please select a device.'); return; }

  const devices = _issueType === 'agwatch' ? (_inventory?.agwatch || []) : (_inventory?.[_issueType] || []);
  const d = devices.find(x => x.id === device_id);
  if (!d) return;

  const hasIssue = d.faulty || d.has_issue;
  const notes    = (document.getElementById('issue-notes').value || '').trim();
  _setError('issue-modal-error', '');

  const attachFile   = document.getElementById('issue-attachment-file')?.files?.[0] || null;
  const resolveDate  = document.getElementById('issue-resolve-date')?.value || null;
  const occurredDate = document.getElementById('issue-occurred-date')?.value || null;
  const today = new Date().toISOString().split('T')[0];

  // Validate dates
  if (hasIssue && occurredDate) {
    if (occurredDate > today) {
      _setError('issue-modal-error', 'Issue occurred date cannot be in the future.');
      return;
    }
    const minDate = document.getElementById('issue-occurred-date').min;
    if (minDate && occurredDate < minDate) {
      _setError('issue-modal-error', `Issue occurred date must be on or after activation date (${minDate}).`);
      return;
    }
  }
  if (!hasIssue && resolveDate) {
    if (resolveDate > today) {
      _setError('issue-modal-error', 'Resolution date cannot be in the future.');
      return;
    }
    const minDate = document.getElementById('issue-resolve-date').min;
    if (minDate && resolveDate < minDate) {
      _setError('issue-modal-error', `Resolution date must be on or after issue occurred date (${minDate}).`);
      return;
    }
  }
  // Validate issue-occurred-date against activation date for Report Issue flow
  if (!hasIssue && occurredDate) {
    if (occurredDate > today) {
      _setError('issue-modal-error', 'Issue occurred date cannot be in the future.');
      return;
    }
    const minDate = document.getElementById('issue-occurred-date').min;
    if (minDate && occurredDate < minDate) {
      _setError('issue-modal-error', `Issue occurred date must be on or after activation date (${minDate}).`);
      return;
    }
  }

  // Resolving issue
  if (hasIssue) {
    try {
      const r = await fetch('/devices/api/toggle-issue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_type: _issueType, device_id, has_issue: false, notes, resolve_date: resolveDate }),
      });
      const res = await r.json();
      if (res.error) { _setError('issue-modal-error', res.error); return; }
      if (attachFile && res.event_id) {
        await _uploadDeviceEventAttachment(_issueType, device_id, res.event_id, attachFile);
      }
      closeIssueModal();
      showToast('Issue resolved', 'success');
      await _refreshInventory();
      // Ensure device flags are cleared in local inventory
      const devices = _issueType === 'agwatch' ? (_inventory?.agwatch || []) : (_inventory?.[_issueType] || []);
      const dev = devices.find(x => x.id === device_id);
      if (dev) { dev.faulty = false; dev.has_issue = false; }
      _loadIssuesSection(_issueType);
      _loadSolutionsSection(_issueType);
    } catch (e) {
      _setError('issue-modal-error', 'Network error — please try again.');
    }
    return;
  }

  // Reporting issue — check if swap requested
  const swapTo = document.getElementById('issue-swap-select')?.value || '';

  if (swapTo && d.assigned_to) {
    // Swap: marks old device faulty AND reassigns patient to new device
    try {
      const r = await fetch('/devices/api/swap-device', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_type: _issueType, old_device_id: device_id, new_device_id: swapTo, notes, issue_date: occurredDate }),
      });
      const res = await r.json();
      if (res.error) { _setError('issue-modal-error', res.error); return; }
      if (attachFile && res.event_id) {
        await _uploadDeviceEventAttachment(_issueType, device_id, res.event_id, attachFile);
      }
      closeIssueModal();
      showToast(`Issue reported; ${res.homer_id || 'patient'} swapped to ${swapTo}`, 'success');
      await _refreshInventory();
      const devices = _issueType === 'agwatch' ? (_inventory?.agwatch || []) : (_inventory?.[_issueType] || []);
      const dev = devices.find(x => x.id === device_id);
      if (dev) { dev.faulty = true; dev.has_issue = true; }
      _loadIssuesSection(_issueType);
      _loadSolutionsSection(_issueType);
      _loadRecentActivity();
    } catch (e) {
      _setError('issue-modal-error', 'Network error — please try again.');
    }
  } else {
    // Just mark issue, no swap
    try {
      const r = await fetch('/devices/api/toggle-issue', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_type: _issueType, device_id, has_issue: true, notes, issue_date: occurredDate }),
      });
      const res = await r.json();
      if (res.error) { _setError('issue-modal-error', res.error); return; }
      if (attachFile && res.event_id) {
        await _uploadDeviceEventAttachment(_issueType, device_id, res.event_id, attachFile);
      }
      closeIssueModal();
      showToast('Issue reported', 'error');
      await _refreshInventory();
      const devices = _issueType === 'agwatch' ? (_inventory?.agwatch || []) : (_inventory?.[_issueType] || []);
      const dev = devices.find(x => x.id === device_id);
      if (dev) { dev.faulty = true; dev.has_issue = true; }
      _loadIssuesSection(_issueType);
      _loadSolutionsSection(_issueType);
    } catch (e) {
      _setError('issue-modal-error', 'Network error — please try again.');
    }
  }
}

async function _uploadDeviceEventAttachment(type, deviceId, eventId, file) {
  const fd = new FormData();
  fd.append('device_type', type);
  fd.append('device_id', deviceId);
  fd.append('event_id', eventId);
  fd.append('file', file);
  try {
    await fetch('/devices/api/upload-event-attachment', { method: 'POST', body: fd });
  } catch (e) {
    console.warn('Attachment upload failed:', e);
  }
}

// ── Add Device Modal (Pluto / Mars) ───────────────────────────

let _addDeviceType = 'pluto';

function openAddDeviceModal(type) {
  _addDeviceType = type;
  const labels = { pluto: 'Pluto', mars: 'Mars' };
  document.getElementById('add-device-title').textContent = `Add ${labels[type] || type} Device`;
  document.getElementById('add-device-id').value     = '';
  document.getElementById('add-device-serial').value = '';
  _setError('add-device-error', '');
  document.getElementById('add-device-modal').classList.remove('hidden');
}

function closeAddDeviceModal() {
  document.getElementById('add-device-modal').classList.add('hidden');
}

async function saveNewDevice() {
  const id     = document.getElementById('add-device-id').value.trim();
  const serial = document.getElementById('add-device-serial').value.trim();
  if (!id)     { _setError('add-device-error', 'Device ID is required.'); return; }
  if (!serial) { _setError('add-device-error', 'Serial number is required.'); return; }
  _setError('add-device-error', '');
  try {
    const r = await fetch('/devices/api/add', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_type: _addDeviceType, id, serial }),
    });
    const d = await r.json();
    if (d.error) { _setError('add-device-error', d.error); return; }
    closeAddDeviceModal();
    showToast(`Device ${id} added`, 'success');
    await _refreshInventory();
  } catch (e) { _setError('add-device-error', 'Network error — please try again.'); }
}

// ── Add Watch Modal ───────────────────────────────────────────

function openAddWatchModal() {
  document.getElementById('add-watch-id').value    = '';
  document.getElementById('add-watch-serial').value = '';
  _setError('add-watch-error', '');
  document.getElementById('add-watch-modal').classList.remove('hidden');
}

function closeAddWatchModal() {
  document.getElementById('add-watch-modal').classList.add('hidden');
}

async function saveNewWatch() {
  const id     = document.getElementById('add-watch-id').value.trim();
  const serial = document.getElementById('add-watch-serial').value.trim();
  if (!id)     { _setError('add-watch-error', 'Device ID is required.'); return; }
  if (!serial) { _setError('add-watch-error', 'Serial number is required.'); return; }
  _setError('add-watch-error', '');
  try {
    const r = await fetch('/devices/api/add', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_type: 'agwatch', id, serial }),
    });
    const d = await r.json();
    if (d.error) { _setError('add-watch-error', d.error); return; }
    closeAddWatchModal();
    showToast(`Watch ${id} added`, 'success');
    await _refreshInventory();
  } catch (e) { _setError('add-watch-error', 'Network error — please try again.'); }
}

// ── Add Modem Modal ───────────────────────────────────────────

function openAddModemModal() {
  document.getElementById('add-modem-id').value     = '';
  document.getElementById('add-modem-serial').value = '';
  _setError('add-modem-error', '');
  document.getElementById('add-modem-modal').classList.remove('hidden');
}

function closeAddModemModal() {
  document.getElementById('add-modem-modal').classList.add('hidden');
}

async function saveNewModem() {
  const id     = document.getElementById('add-modem-id').value.trim();
  const serial = document.getElementById('add-modem-serial').value.trim();
  if (!id)     { _setError('add-modem-error', 'Modem ID is required.'); return; }
  if (!serial) { _setError('add-modem-error', 'Serial number is required.'); return; }
  _setError('add-modem-error', '');
  try {
    const r = await fetch('/devices/api/add', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_type: 'modem', id, serial }),
    });
    const d = await r.json();
    if (d.error) { _setError('add-modem-error', d.error); return; }
    closeAddModemModal();
    showToast(`Modem ${id} added`, 'success');
    await _refreshInventory();
  } catch (e) { _setError('add-modem-error', 'Network error — please try again.'); }
}

// ── Add SIM Modal ─────────────────────────────────────────────

function openAddSimModal() {
  document.getElementById('add-sim-phone').value    = '';
  document.getElementById('add-sim-network').value  = '';
  document.getElementById('add-sim-recharge').value = '';
  document.getElementById('add-sim-plan').value     = '';
  document.getElementById('add-sim-expiry').value   = '';
  document.getElementById('add-sim-expiry').readOnly = false;
  document.getElementById('add-sim-expiry-note').textContent = '';
  document.getElementById('add-sim-reminder').value = '5';
  _setError('add-sim-error', '');
  // Attach real-time keyboard validation
  _attachDateKeyboardValidation('add-sim-recharge', 'add-sim-error');
  _attachDateKeyboardValidation('add-sim-expiry', 'add-sim-error');
  document.getElementById('add-sim-modal').classList.remove('hidden');
}

function closeAddSimModal() {
  document.getElementById('add-sim-modal').classList.add('hidden');
}

function _addDays(dateStr, days) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().split('T')[0];
}

function onSimRechargeChange() {
  const plan = document.getElementById('add-sim-plan').value;
  if (plan && plan !== 'custom') {
    const recharge = document.getElementById('add-sim-recharge').value;
    if (recharge) {
      document.getElementById('add-sim-expiry').value = _addDays(recharge, parseInt(plan));
    }
  }
}

function onSimPlanChange() {
  const plan = document.getElementById('add-sim-plan').value;
  const expiryInput = document.getElementById('add-sim-expiry');
  const note = document.getElementById('add-sim-expiry-note');
  if (!plan || plan === 'custom') {
    expiryInput.readOnly = false;
    expiryInput.classList.remove('bg-slate-100');
    note.textContent = '';
  } else {
    expiryInput.readOnly = true;
    expiryInput.classList.add('bg-slate-100');
    note.textContent = '(auto-computed)';
    const recharge = document.getElementById('add-sim-recharge').value;
    if (recharge) {
      expiryInput.value = _addDays(recharge, parseInt(plan));
    }
  }
}

async function saveNewSim() {
  const phone    = document.getElementById('add-sim-phone').value.trim();
  const network  = document.getElementById('add-sim-network').value.trim();
  const recharge = document.getElementById('add-sim-recharge').value;
  const expiry   = document.getElementById('add-sim-expiry').value;
  const plan     = document.getElementById('add-sim-plan').value;
  const reminder = parseInt(document.getElementById('add-sim-reminder').value) || 5;

  if (!phone) { _setError('add-sim-error', 'Phone number is required.'); return; }
  _setError('add-sim-error', '');
  try {
    const r = await fetch('/devices/api/add', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_type:  'sim',
        phoneNumber:  phone,
        network,
        rechargeDate: recharge || null,
        expiryDate:   expiry   || null,
        dataPlan:     (plan && plan !== 'custom') ? plan : null,
        reminderDays: reminder,
      }),
    });
    const d = await r.json();
    if (d.error) { _setError('add-sim-error', d.error); return; }
    closeAddSimModal();
    showToast(`SIM ${phone} added`, 'success');
    await _refreshInventory();
  } catch (e) { _setError('add-sim-error', 'Network error — please try again.'); }
}

// ── Add Laptop Modal ──────────────────────────────────────────

function openAddLaptopModal() {
  document.getElementById('add-laptop-id').value     = '';
  document.getElementById('add-laptop-serial').value = '';
  _setError('add-laptop-error', '');
  document.getElementById('add-laptop-modal').classList.remove('hidden');
}

function closeAddLaptopModal() {
  document.getElementById('add-laptop-modal').classList.add('hidden');
}

async function saveNewLaptop() {
  const id     = document.getElementById('add-laptop-id').value.trim();
  const serial = document.getElementById('add-laptop-serial').value.trim();
  if (!id)     { _setError('add-laptop-error', 'Laptop ID is required.'); return; }
  if (!serial) { _setError('add-laptop-error', 'Serial number is required.'); return; }
  _setError('add-laptop-error', '');
  try {
    const r = await fetch('/devices/api/add', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_type: 'laptop', id, serial }),
    });
    const d = await r.json();
    if (d.error) { _setError('add-laptop-error', d.error); return; }
    closeAddLaptopModal();
    showToast(`Laptop ${id} added`, 'success');
    await _refreshInventory();
  } catch (e) { _setError('add-laptop-error', 'Network error — please try again.'); }
}

// ── Recharge SIM Modal ───────────────────────────────────────

let _rechargeSimId = null;

function openRechargeSimModal(simId) {
  _rechargeSimId = simId;
  document.getElementById('recharge-sim-recharge').value = '';
  document.getElementById('recharge-sim-plan').value = '';
  document.getElementById('recharge-sim-expiry').value = '';
  document.getElementById('recharge-sim-expiry').readOnly = false;
  document.getElementById('recharge-sim-expiry').classList.remove('bg-slate-100');
  document.getElementById('recharge-sim-expiry-note').textContent = '';
  _setError('recharge-sim-error', '');
  // Attach real-time keyboard validation
  _attachDateKeyboardValidation('recharge-sim-recharge', 'recharge-sim-error');
  _attachDateKeyboardValidation('recharge-sim-expiry', 'recharge-sim-error');
  document.getElementById('recharge-sim-modal').classList.remove('hidden');
}

function closeRechargeSimModal() {
  document.getElementById('recharge-sim-modal').classList.add('hidden');
}

function onRechargeSimRechargeChange() {
  const plan = document.getElementById('recharge-sim-plan').value;
  if (plan && plan !== 'custom') {
    const recharge = document.getElementById('recharge-sim-recharge').value;
    if (recharge) {
      document.getElementById('recharge-sim-expiry').value = _addDays(recharge, parseInt(plan));
    }
  }
}

function onRechargeSimPlanChange() {
  const plan = document.getElementById('recharge-sim-plan').value;
  const expiryInput = document.getElementById('recharge-sim-expiry');
  const note = document.getElementById('recharge-sim-expiry-note');
  if (!plan || plan === 'custom') {
    expiryInput.readOnly = false;
    expiryInput.classList.remove('bg-slate-100');
    note.textContent = '';
  } else {
    expiryInput.readOnly = true;
    expiryInput.classList.add('bg-slate-100');
    note.textContent = '(auto-computed)';
    const recharge = document.getElementById('recharge-sim-recharge').value;
    if (recharge) {
      expiryInput.value = _addDays(recharge, parseInt(plan));
    }
  }
}

async function saveRechargeSimModal() {
  const recharge = document.getElementById('recharge-sim-recharge').value;
  const plan     = document.getElementById('recharge-sim-plan').value;
  const expiry   = document.getElementById('recharge-sim-expiry').value;
  if (!recharge) { _setError('recharge-sim-error', 'Recharge date is required.'); return; }
  _setError('recharge-sim-error', '');
  try {
    const r = await fetch('/devices/api/recharge-sim', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sim_id:       _rechargeSimId,
        rechargeDate: recharge,
        dataPlan:     (plan && plan !== 'custom') ? plan : null,
        expiryDate:   expiry || null,
      }),
    });
    const d = await r.json();
    if (d.error) { _setError('recharge-sim-error', d.error); return; }
    closeRechargeSimModal();
    showToast('SIM recharged', 'success');
    await _refreshInventory();
  } catch (e) { _setError('recharge-sim-error', 'Network error — please try again.'); }
}

// ── Link SIM Modal ────────────────────────────────────────────

let _linkSimModemId = null;

function openLinkSimModal(modemId) {
  _linkSimModemId = modemId;
  document.getElementById('link-sim-modem-label').textContent = modemId;
  _setError('link-sim-error', '');
  const modem = (_inventory?.modems || []).find(m => m.id === modemId);
  const currentSimId = modem?.sim_id || null;
  // SIMs already linked to other modems (that are assigned to a patient) are excluded
  const assignedModemIds = new Set(
    (_inventory?.modems || []).filter(m => m.assigned_to && m.id !== modemId).map(m => m.id)
  );
  const linkedSimIds = new Set(
    (_inventory?.modems || [])
      .filter(m => m.sim_id && m.id !== modemId && assignedModemIds.has(m.id))
      .map(m => m.sim_id)
  );
  const sel = document.getElementById('link-sim-select');
  sel.innerHTML = '<option value="">None (unlink)</option>';
  for (const s of (_inventory?.sims || [])) {
    if (!linkedSimIds.has(s.id) || s.id === currentSimId) {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = `${s.network || '?'} — ${s.phoneNumber || s.id}`;
      if (s.id === currentSimId) opt.selected = true;
      sel.appendChild(opt);
    }
  }
  document.getElementById('link-sim-modal').classList.remove('hidden');
}

function closeLinkSimModal() {
  document.getElementById('link-sim-modal').classList.add('hidden');
}

async function saveLinkSim() {
  const sim_id = document.getElementById('link-sim-select').value.trim() || null;
  _setError('link-sim-error', '');
  try {
    const r = await fetch('/devices/api/link-sim', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modem_id: _linkSimModemId, sim_id }),
    });
    const d = await r.json();
    if (d.error) { _setError('link-sim-error', d.error); return; }
    closeLinkSimModal();
    showToast(sim_id ? 'SIM linked' : 'SIM unlinked', 'success');
    await _refreshInventory();
  } catch (e) { _setError('link-sim-error', 'Network error — please try again.'); }
}

// ── Retire Device Modal ───────────────────────────────────────

let _retireType = null;

function openRetireModal(type) {
  _retireType = type;
  const labels = { pluto:'Pluto', mars:'Mars', agwatch:'Agwatch Watch', modems:'Modem', laptops:'Laptop', sims:'SIM Card' };
  document.getElementById('retire-modal-title').textContent = `Retire ${labels[type] || type}`;
  _setError('retire-error', '');
  document.getElementById('retire-notes').value = '';

  const sel = document.getElementById('retire-device-select');
  sel.innerHTML = '<option value="">Select device…</option>';

  let devices;
  if (type === 'agwatch') {
    devices = (_inventory?.agwatch || []).filter(d => !d.assigned_to && !d.removal_date && !d.lost);
    devices.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = d.id;
      sel.appendChild(opt);
    });
  } else if (type === 'sims') {
    devices = (_inventory?.sims || []).filter(s => !s.removal_date && !s.modem_id);
    devices.forEach(s => {
      const opt = document.createElement('option');
      opt.value = s.id;
      opt.textContent = `${s.network || '?'} — ${s.phoneNumber || s.id}`;
      sel.appendChild(opt);
    });
  } else {
    const key = type;
    devices = (_inventory?.[key] || []).filter(d => !d.assigned_to && !d.removal_date);
    devices.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.id;
      opt.textContent = d.id;
      sel.appendChild(opt);
    });
  }

  if (sel.options.length === 1) {
    _setError('retire-error', 'No eligible devices. Only unassigned devices can be retired.');
  }

  document.getElementById('retire-modal').classList.remove('hidden');
}

function closeRetireModal() {
  document.getElementById('retire-modal').classList.add('hidden');
}

async function saveRetireDevice() {
  const device_id = document.getElementById('retire-device-select').value;
  if (!device_id) { _setError('retire-error', 'Please select a device.'); return; }
  const notes = (document.getElementById('retire-notes').value || '').trim();
  _setError('retire-error', '');
  try {
    const r = await fetch('/devices/api/log-event', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_type: _retireType, device_id, event_type: 'retire', notes }),
    });
    const res = await r.json();
    if (res.error) { _setError('retire-error', res.error); return; }
    closeRetireModal();
    showToast(`${device_id} retired`, 'success');
    await _refreshInventory();
    if (['pluto','mars','agwatch','modems','laptops'].includes(_retireType)) {
      _loadIssuesSection(_retireType);
      _loadSolutionsSection(_retireType);
    }
  } catch (e) { _setError('retire-error', 'Network error — please try again.'); }
}

// ── Assign / Unassign Modem / Laptop ─────────────────────────

let _assignDeviceType = null;
let _assignDeviceId   = null;

function openAssignModal(type, deviceId) {
  _assignDeviceType = type;
  _assignDeviceId   = deviceId;
  document.getElementById('assign-device-label').textContent = `${type.charAt(0).toUpperCase() + type.slice(1)} ${deviceId}`;
  document.getElementById('assign-patient-search').value = '';
  _setError('assign-modal-error', '');

  // SIM expiry warning for modems
  const warning = document.getElementById('assign-sim-warning');
  warning.classList.add('hidden');
  if (type === 'modem') {
    const modem = (_inventory?.modems || []).find(m => m.id === deviceId);
    const sim   = modem?.sim_id ? (_inventory?.sims || []).find(s => s.id === modem.sim_id) : null;
    if (sim && sim.daysUntilExpiry !== undefined) {
      const icon = document.getElementById('assign-sim-warning-icon');
      const msg  = document.getElementById('assign-sim-warning-msg');
      if (sim.isExpired) {
        warning.className = 'rounded-xl p-3 text-sm flex flex-col gap-2 bg-red-50 text-red-700 border border-red-200';
        icon.className    = 'fas fa-times-circle mt-0.5 shrink-0 text-red-500';
        msg.textContent   = `SIM ${sim.phoneNumber} is expired. The modem will have no data connectivity. Recharge before assigning or assign and recharge later.`;
        warning.classList.remove('hidden');
      } else if (sim.daysUntilExpiry <= 5) {
        warning.className = 'rounded-xl p-3 text-sm flex flex-col gap-2 bg-amber-50 text-amber-700 border border-amber-200';
        icon.className    = 'fas fa-exclamation-triangle mt-0.5 shrink-0 text-amber-500';
        msg.textContent   = `SIM ${sim.phoneNumber} expires in ${sim.daysUntilExpiry} day${sim.daysUntilExpiry === 1 ? '' : 's'}. Consider recharging before assigning.`;
        warning.classList.remove('hidden');
      }
    }
  }

  const sel = document.getElementById('assign-homer-select');
  sel.innerHTML = '';

  // Exclude patients already assigned to this device type
  const assignedHomerIds = new Set(
    (_inventory?.[type === 'modem' ? 'modems' : 'laptops'] || [])
      .filter(d => d.assigned_to && d.id !== deviceId)
      .map(d => d.assigned_to.homerID)
  );

  const patients = (_inventory?.patients || []).filter(p => !assignedHomerIds.has(p.homerID));
  if (!patients.length) {
    const opt = document.createElement('option');
    opt.disabled = true;
    opt.textContent = 'No eligible patients';
    sel.appendChild(opt);
  } else {
    patients.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.homerID;
      opt.textContent = `${p.homerID} — ${p.hospitalID}`;
      sel.appendChild(opt);
    });
  }

  document.getElementById('assign-modal').classList.remove('hidden');
}

function openRechargeFromAssign() {
  // Find the SIM linked to the modem being assigned, open the recharge modal
  const modem = (_inventory?.modems || []).find(m => m.id === _assignDeviceId);
  const sim   = modem?.sim_id ? (_inventory?.sims || []).find(s => s.id === modem.sim_id) : null;
  if (!sim) return;
  closeAssignModal();
  openRechargeSimModal(sim.id);
}

function filterAssignPatients() {
  const q = document.getElementById('assign-patient-search').value.toLowerCase();
  const sel = document.getElementById('assign-homer-select');
  for (const opt of sel.options) {
    opt.hidden = q ? !opt.textContent.toLowerCase().includes(q) : false;
  }
}

function closeAssignModal() {
  document.getElementById('assign-modal').classList.add('hidden');
}

async function saveAssignDevice() {
  const homer_id = (document.getElementById('assign-homer-select').value || '').trim();
  if (!homer_id) { _setError('assign-modal-error', 'Please select a patient.'); return; }
  _setError('assign-modal-error', '');
  try {
    const r = await fetch('/devices/api/assign-device', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_type: _assignDeviceType, device_id: _assignDeviceId, homer_id }),
    });
    const res = await r.json();
    if (res.error) { _setError('assign-modal-error', res.error); return; }
    closeAssignModal();
    showToast('Device assigned', 'success');
    await _refreshInventory();
  } catch (e) { _setError('assign-modal-error', 'Network error — please try again.'); }
}

async function unassignDevice(type, deviceId) {
  if (!confirm(`Return ${type} ${deviceId} from patient?`)) return;
  try {
    const r = await fetch('/devices/api/unassign-device', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_type: type, device_id: deviceId }),
    });
    const res = await r.json();
    if (res.error) { showToast(res.error, 'error'); return; }
    showToast('Device returned to available', 'success');
    await _refreshInventory();
  } catch (e) { showToast('Network error — please try again.', 'error'); }
}

// ── UI helpers ────────────────────────────────────────────────

function _showLoading(show) {
  document.getElementById('devices-loading').classList.toggle('hidden', !show);
  document.getElementById('devices-error').classList.add('hidden');
  if (show) {
    document.getElementById('devices-tabs-wrapper')?.classList.add('hidden');
    document.getElementById('devices-tab-panes')?.classList.add('hidden');
  }
}

function _showError(msg) {
  document.getElementById('devices-loading').classList.add('hidden');
  document.getElementById('devices-error').classList.remove('hidden');
  document.getElementById('devices-error-msg').textContent = msg;
}

function _setError(elId, msg) {
  const el = document.getElementById(elId);
  if (!el) return;
  if (msg) { el.textContent = msg; el.classList.remove('hidden'); }
  else     { el.classList.add('hidden'); }
}

function _esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function showToast(message, type = 'info') {
  const colours = { success: 'bg-green-600', error: 'bg-red-600', info: 'bg-blue-600' };
  const icons   = { success: 'fa-check-circle', error: 'fa-exclamation-circle', info: 'fa-info-circle' };
  const toast = document.createElement('div');
  toast.className = `fixed bottom-6 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-xl shadow-lg text-white text-sm font-medium ${colours[type] || colours.info} transition-all duration-300 opacity-0 translate-y-2`;
  toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${_esc(message)}</span>`;
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.remove('opacity-0', 'translate-y-2'));
  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ── Close modals on backdrop click ────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  [
    ['add-device-modal',  closeAddDeviceModal],
    ['clinic-modal',      closeClinicModal],
    ['issue-modal',       closeIssueModal],
    ['add-watch-modal',   closeAddWatchModal],
    ['add-modem-modal',   closeAddModemModal],
    ['add-sim-modal',     closeAddSimModal],
    ['add-laptop-modal',  closeAddLaptopModal],
    ['link-sim-modal',    closeLinkSimModal],
    ['recharge-sim-modal',closeRechargeSimModal],
  ].forEach(([id, fn]) => {
    document.getElementById(id)?.addEventListener('click', e => {
      if (e.target === e.currentTarget) fn();
    });
  });
});
