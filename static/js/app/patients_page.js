/* ============================================================
   patients_page.js — URL-routed /patients page
   HOMER Clinical Dashboard
   ============================================================ */

// allPatients and currentFilter are declared globally in app.js

function initPage() {
  setActiveFilterButton(currentFilter);   // highlight before async load
  loadPatients();
  if (currentUser && currentUser.privilege === 'admin') {
    document.getElementById('add-patient-btn')?.classList.remove('hidden');
  }
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadPatients() {
  document.getElementById('patient-list').innerHTML =
    '<div class="text-center py-12 text-slate-500"><i class="fas fa-spinner fa-spin text-2xl"></i></div>';
  try {
    const res = await fetch('/api/patients');
    if (!res.ok) throw new Error('Failed to load patients');
    allPatients = await res.json();
    updateFilterCounts();
    renderPatients();
    // Restore active filter button highlight
    setActiveFilterButton(currentFilter);
  } catch (e) {
    console.error('Error loading patients:', e);
    document.getElementById('patient-list').innerHTML =
      '<div class="text-center py-12 text-red-500">Error loading patients. Please refresh.</div>';
  }
}

// ── Filter counts ─────────────────────────────────────────────────────────────

// Each filter tab maps directly to one status
const FILTER_STATUS_MAP = {
  all:               ['unassigned', 'inactive', 'active', 'paused', 'post_training', 'broken_protocol', 'training_completed', 'a1_completed', 'all_completed', 'pre_discontinued', 'discontinued'],
  unassigned:        ['unassigned'],
  inactive:          ['inactive'],
  active:            ['active'],
  paused:            ['paused'],
  post_training:     ['post_training'],
  broken_protocol:   ['broken_protocol'],
  training_completed:['training_completed'],
  a1_completed:      ['a1_completed'],
  all_completed:     ['all_completed'],
  pre_discontinued:  ['pre_discontinued'],
  discontinued:      ['discontinued'],
};

function updateFilterCounts() {
  const counts = { all: 0, unassigned: 0, inactive: 0, active: 0, paused: 0, post_training: 0, broken_protocol: 0, training_completed: 0, a1_completed: 0, all_completed: 0, pre_discontinued: 0, discontinued: 0 };
  allPatients.forEach(p => {
    counts.all++;
    if (counts[p.status] !== undefined) counts[p.status]++;
  });
  const el = id => document.getElementById(id);
  el('count-all').textContent               = counts.all;
  el('count-unassigned').textContent        = counts.unassigned;
  el('count-inactive').textContent          = counts.inactive;
  el('count-active').textContent            = counts.active;
  el('count-paused').textContent            = counts.paused;
  el('count-post-training').textContent     = counts.post_training;
  el('count-broken-protocol').textContent   = counts.broken_protocol;
  el('count-training-completed').textContent= counts.training_completed;
  el('count-a1-completed').textContent      = counts.a1_completed;
  el('count-all-completed').textContent     = counts.all_completed;
  el('count-pre-discontinued').textContent  = counts.pre_discontinued;
  el('count-discontinued').textContent      = counts.discontinued;
}

// ── Filter tabs ───────────────────────────────────────────────────────────────

function filterPatients(filter) {
  currentFilter = filter;
  setActiveFilterButton(filter);
  renderPatients();
}

function setActiveFilterButton(filter) {
  const baseClasses   = 'bg-white text-slate-600 border-slate-200 shadow-sm';
  const activeClasses = {
    all:               'bg-gradient-to-r from-slate-600 to-slate-700 text-white border-transparent shadow-md',
    unassigned:        'bg-gradient-to-r from-slate-500 to-slate-600 text-white border-transparent shadow-md shadow-slate-200',
    inactive:          'bg-gradient-to-r from-orange-500 to-orange-600 text-white border-transparent shadow-md shadow-orange-200',
    active:            'bg-gradient-to-r from-blue-500 to-blue-600 text-white border-transparent shadow-md shadow-blue-200',
    paused:            'bg-gradient-to-r from-amber-500 to-amber-600 text-white border-transparent shadow-md shadow-amber-200',
    post_training:     'bg-gradient-to-r from-sky-500 to-sky-600 text-white border-transparent shadow-md shadow-sky-200',
    broken_protocol:   'bg-gradient-to-r from-red-500 to-red-600 text-white border-transparent shadow-md shadow-red-200',
    training_completed:'bg-gradient-to-r from-teal-500 to-teal-600 text-white border-transparent shadow-md shadow-teal-200',
    a1_completed:      'bg-gradient-to-r from-violet-500 to-violet-600 text-white border-transparent shadow-md shadow-violet-200',
    all_completed:     'bg-gradient-to-r from-emerald-500 to-teal-600 text-white border-transparent shadow-md shadow-emerald-200',
    pre_discontinued:  'bg-gradient-to-r from-orange-400 to-orange-500 text-white border-transparent shadow-md shadow-orange-200',
    discontinued:      'bg-red-500 text-white border-transparent shadow-md shadow-red-200',
  };

  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.className = `filter-btn px-3 py-1.5 text-sm font-medium rounded-xl border transition-all duration-150 ${baseClasses}`;
  });

  const active = document.querySelector(`[data-filter="${filter}"]`);
  if (active) {
    active.className = `filter-btn px-3 py-1.5 text-sm font-medium rounded-xl border transition-all duration-150 ${activeClasses[filter] || activeClasses.all}`;
  }
}

// ── Render patient list ───────────────────────────────────────────────────────

function renderPatients() {
  const list = document.getElementById('patient-list');
  const searchTerm = (document.getElementById('patient-search')?.value || '').toLowerCase().trim();

  const allowedStatuses = FILTER_STATUS_MAP[currentFilter] || [];
  let filtered = allPatients.filter(p => {
    if (currentFilter !== 'all' && !allowedStatuses.includes(p.status)) return false;
    if (searchTerm) {
      const id1 = (p.homerID    || '').toLowerCase();
      const id2 = (p.hospitalID || '').toLowerCase();
      if (!id1.includes(searchTerm) && !id2.includes(searchTerm)) return false;
    }
    return true;
  });

  if (!filtered.length) {
    list.innerHTML = '<div class="text-center py-12 text-slate-500">No patients found</div>';
    return;
  }

  // For active + inactive: group by experimental then control with sub-headers
  const showGroupHeaders = ['active', 'inactive'].includes(currentFilter) && !searchTerm;
  if (showGroupHeaders) {
    const exp  = filtered.filter(p => p.group === 'experimental');
    const ctrl = filtered.filter(p => p.group === 'control');
    const rest = filtered.filter(p => p.group !== 'experimental' && p.group !== 'control');
    list.innerHTML = `
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <div class="flex items-center gap-2 mb-3">
            <div class="h-px flex-1 bg-blue-100"></div>
            <span class="text-xs font-bold text-blue-500 uppercase tracking-wider px-2">
              <i class="fas fa-robot mr-1"></i>Experimental (${exp.length})
            </span>
            <div class="h-px flex-1 bg-blue-100"></div>
          </div>
          <div class="space-y-3">
            ${exp.length ? exp.map(renderCard).join('') : '<p class="text-center text-xs text-slate-400 py-4">No experimental patients</p>'}
          </div>
        </div>
        <div>
          <div class="flex items-center gap-2 mb-3">
            <div class="h-px flex-1 bg-violet-100"></div>
            <span class="text-xs font-bold text-violet-500 uppercase tracking-wider px-2">
              <i class="fas fa-user-check mr-1"></i>Control (${ctrl.length})
            </span>
            <div class="h-px flex-1 bg-violet-100"></div>
          </div>
          <div class="space-y-3">
            ${ctrl.length ? ctrl.map(renderCard).join('') : '<p class="text-center text-xs text-slate-400 py-4">No control patients</p>'}
          </div>
        </div>
      </div>
      ${rest.length ? '<div class="space-y-3 mt-4">' + rest.map(renderCard).join('') + '</div>' : ''}`;
  } else {
    list.innerHTML = '<div class="space-y-3">' + filtered.map(renderCard).join('') + '</div>';
  }
}

function renderCard(p) {
  const groupColors = {
    experimental: { avatar: 'bg-gradient-to-br from-blue-500 to-blue-600 shadow-blue-200' },
    control:      { avatar: 'bg-gradient-to-br from-violet-500 to-violet-600 shadow-violet-200' },
  };
  const avatarClass = (groupColors[p.group] || { avatar: 'bg-gradient-to-br from-slate-400 to-slate-500 shadow-slate-200' }).avatar;

  const statusConfig = {
    active:              { bg: 'bg-blue-50',    text: 'text-blue-600',    icon: 'fa-check-circle',    label: 'Active' },
    inactive:            { bg: 'bg-orange-50',  text: 'text-orange-600',  icon: 'fa-clock',           label: 'Inactive' },
    unassigned:          { bg: 'bg-slate-100',  text: 'text-slate-500',   icon: 'fa-question-circle', label: 'Unassigned' },
    discontinued:        { bg: 'bg-red-50',     text: 'text-red-500',     icon: 'fa-user-minus',      label: 'Discontinued' },
    pre_discontinued:    { bg: 'bg-orange-50',  text: 'text-orange-500',  icon: 'fa-user-slash',      label: 'Pre-Discontinued' },
    post_training:       { bg: 'bg-sky-50',     text: 'text-sky-600',     icon: 'fa-flag',            label: 'Post Training' },
    training_completed:  { bg: 'bg-teal-50',    text: 'text-teal-600',    icon: 'fa-dumbbell',        label: 'Training Complete' },
    a1_completed:        { bg: 'bg-violet-50',  text: 'text-violet-600',  icon: 'fa-clipboard-check', label: 'A1 Complete' },
    all_completed:       { bg: 'bg-emerald-50', text: 'text-emerald-600', icon: 'fa-flag-checkered',  label: 'All Complete' },
  }[p.status] || { bg: 'bg-slate-100', text: 'text-slate-500', icon: 'fa-question-circle', label: p.status };

  const statusBadge = `<span class="px-3 py-1.5 ${statusConfig.bg} ${statusConfig.text} rounded-full text-xs font-medium flex items-center gap-1.5 shadow-sm whitespace-nowrap">
    <i class="fas ${statusConfig.icon} text-xs"></i>${statusConfig.label}</span>`;

  const groupLabel  = p.group ? p.group.charAt(0).toUpperCase() + p.group.slice(1) : 'Unassigned';
  const sideLabel   = p.trainingSide ? `${p.trainingSide} side · ` : '';
  const activeSince = p.activationDate
    ? `<span class="text-xs text-slate-400 ml-1">since ${new Date(p.activationDate).toLocaleDateString('en-GB', {day:'2-digit', month:'short'})}</span>`
    : '';

  const isDropped = ['discontinued', 'pre_discontinued'].includes(p.status);
  const cardBg    = isDropped ? 'bg-white/50 opacity-70 border border-slate-200' : 'bg-white border border-slate-100 hover:border-blue-200 hover:shadow-lg hover:shadow-blue-100/50';

  const isAdmin      = currentUser && currentUser.privilege === 'admin';
  const isUnassigned = p.status === 'unassigned';
  const cardOnClick  = isUnassigned ? '' : `onclick="window.location.href='/patients/${p.homerID}'"`;
  const cardCursor   = isUnassigned ? '' : 'cursor-pointer';

  const actionBtn = isUnassigned
    ? (isAdmin
        ? `<div class="flex items-center gap-2">
             <button onclick="showPreDiscontinueModal('${p.homerID}')"
                     class="px-3 py-2 bg-orange-500 hover:bg-orange-600 active:bg-orange-700 text-white text-sm font-medium rounded-xl shadow-md hover:shadow-lg cursor-pointer transition-all duration-200 flex items-center gap-1.5">
               <i class="fas fa-user-slash text-xs"></i>Pre-DC
             </button>
             <button onclick="showAssignGroupModal('${p.homerID}')"
                     class="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 active:bg-emerald-700 text-white text-sm font-medium rounded-xl shadow-md hover:shadow-lg cursor-pointer transition-all duration-200 flex items-center gap-2">
               <i class="fas fa-tags text-xs"></i>Assign
             </button>
           </div>`
        : '')
    : `<button onclick="event.stopPropagation(); window.location.href='/patients/${p.homerID}'"
              class="px-4 py-2 ${isDropped ? 'bg-slate-300' : 'bg-blue-500 hover:bg-blue-600 active:bg-blue-700'} text-white text-sm font-medium rounded-xl shadow-md hover:shadow-lg transform hover:scale-105 active:scale-95 transition-all duration-200 flex items-center gap-2">
         <i class="fas fa-eye text-xs"></i>View
       </button>`;

  return `
    <div class="group hover:-translate-y-0.5 transition-all duration-300 ease-out">
      <div class="${cardBg} rounded-2xl p-4 ${cardCursor} ${isUnassigned ? '' : 'active:scale-[0.98]'} transition-transform"
           ${cardOnClick}>
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-4">
            <div class="w-14 h-14 ${avatarClass} rounded-2xl flex items-center justify-center shadow-md transform group-hover:scale-105 transition-transform duration-300">
              <span class="text-white font-semibold text-base tracking-wide">${(p.homerID || '--').slice(0,2).toUpperCase()}</span>
            </div>
            <div>
              <p class="font-semibold ${isDropped ? 'text-slate-400 line-through decoration-slate-300' : 'text-slate-800'} text-base">
                ${p.homerID}${activeSince}
              </p>
              <p class="text-sm ${isDropped ? 'text-slate-400' : 'text-slate-500'}">
                ${p.hospitalID ? p.hospitalID + ' · ' : ''}${sideLabel}<span class="capitalize">${groupLabel}</span>
              </p>
            </div>
          </div>
          <div class="flex items-center gap-3">
            ${statusBadge}
            ${actionBtn}
          </div>
        </div>
      </div>
    </div>`;
}

// ── Assign Group modal ────────────────────────────────────────────────────────

let _assignGroupHomerID = null;

function showAssignGroupModal(homerID) {
  _assignGroupHomerID = homerID;
  document.getElementById('assign-group-homer-id').textContent = homerID;
  document.getElementById('assign-group-value').value = '';
  const a0Input = document.getElementById('assign-group-a0-date');
  a0Input.value = '';
  // Set max to current local datetime (YYYY-MM-DDTHH:MM) to block future selection
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  a0Input.max = `${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
  document.getElementById('assign-group-error').classList.add('hidden');
  ['experimental', 'control'].forEach(g => {
    const btn = document.getElementById(`group-${g}-btn`);
    btn.style.background  = '';
    btn.style.color       = '';
    btn.style.borderColor = '';
  });
  document.getElementById('assign-group-modal').classList.remove('hidden');
}

function hideAssignGroupModal() {
  document.getElementById('assign-group-modal').classList.add('hidden');
  _assignGroupHomerID = null;
}

function selectGroup(group) {
  document.getElementById('assign-group-value').value = group;
  const colors = { experimental: '#3b82f6', control: '#7c3aed' };
  ['experimental', 'control'].forEach(g => {
    const btn = document.getElementById(`group-${g}-btn`);
    const selected = g === group;
    btn.style.background  = selected ? colors[g] : '';
    btn.style.color       = selected ? '#ffffff' : '';
    btn.style.borderColor = selected ? colors[g] : '';
  });
}

async function submitAssignGroup() {
  const group   = document.getElementById('assign-group-value').value;
  const a0Date  = document.getElementById('assign-group-a0-date').value;
  const errEl   = document.getElementById('assign-group-error');
  const btn     = document.getElementById('assign-group-submit');
  errEl.classList.add('hidden');

  if (!group) {
    errEl.textContent = 'Please select a group.';
    errEl.classList.remove('hidden');
    return;
  }
  if (!a0Date) {
    errEl.textContent = 'Please enter the A0 assessment date.';
    errEl.classList.remove('hidden');
    return;
  }
  if (new Date(a0Date) > new Date()) {
    errEl.textContent = 'A0 assessment date cannot be in the future.';
    errEl.classList.remove('hidden');
    return;
  }

  // Show confirmation dialog
  const groupLabel = group === 'experimental' ? 'Experimental (with Robot Therapy)' : 'Control (Standard Therapy)';
  const confirmed = window.confirm(
    `Are you sure you want to assign ${_assignGroupHomerID} to the ${groupLabel} group?\n\nThis action CANNOT be undone. The patient will be permanently assigned to this group for the duration of the study.`
  );
  if (!confirmed) return;

  btn.disabled = true;
  btn.textContent = 'Assigning…';
  try {
    const res = await fetch(`/api/patients/${_assignGroupHomerID}/group`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ group, a0CompletionDate: a0Date }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.error || 'Failed to assign group';
      errEl.classList.remove('hidden');
      return;
    }
    hideAssignGroupModal();
    showToast(`${_assignGroupHomerID || data.homerID} assigned to ${group}`);
    await loadPatients();
  } catch (e) {
    errEl.textContent = 'Network error — please try again';
    errEl.classList.remove('hidden');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Assign';
  }
}

// ── Add Patient modal ─────────────────────────────────────────────────────────

function selectTrainingSide(side) {
  document.getElementById('new-training-side').value = side;
  ['Left', 'Right'].forEach(s => {
    const btn = document.getElementById(`side-${s.toLowerCase()}-btn`);
    const selected = s === side;
    btn.style.background   = selected ? '#3b82f6' : '';
    btn.style.color        = selected ? '#ffffff' : '';
    btn.style.borderColor  = selected ? '#3b82f6' : '';
  });
}

function showAddPatientModal() {
  document.getElementById('add-patient-modal').classList.remove('hidden');
  document.getElementById('add-patient-error').classList.add('hidden');
  document.getElementById('add-patient-form').reset();
  // Reset side buttons
  ['left', 'right'].forEach(s => {
    const btn = document.getElementById(`side-${s}-btn`);
    btn.style.background  = '';
    btn.style.color       = '';
    btn.style.borderColor = '';
  });
}

function hideAddPatientModal() {
  document.getElementById('add-patient-modal').classList.add('hidden');
}

async function submitAddPatient(e) {
  e.preventDefault();
  const hospitalID   = document.getElementById('new-hospital-id').value.trim();
  const trainingSide = document.getElementById('new-training-side').value;
  const errEl        = document.getElementById('add-patient-error');
  const submitBtn    = document.getElementById('add-patient-submit');

  errEl.classList.add('hidden');
  if (!trainingSide) {
    errEl.textContent = 'Please select a training side.';
    errEl.classList.remove('hidden');
    return;
  }
  submitBtn.disabled = true;
  submitBtn.textContent = 'Creating…';

  try {
    const res = await fetch('/api/patients', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hospitalID, trainingSide }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.error || 'Failed to create patient';
      errEl.classList.remove('hidden');
      return;
    }
    hideAddPatientModal();
    showToast('Patient created: ' + data.homerID);
    await loadPatients();
  } catch (err) {
    errEl.textContent = 'Network error — please try again';
    errEl.classList.remove('hidden');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Create Patient';
  }
}

// ── Pre-Discontinue modal ─────────────────────────────────────────────────────

let _preDiscHomerID = null;

function showPreDiscontinueModal(homerID) {
  _preDiscHomerID = homerID;
  const modal    = document.getElementById('pre-dc-modal');
  const homerEl  = document.getElementById('pre-dc-homer-id');
  const reasonEl = document.getElementById('pre-dc-reason');
  const errorEl  = document.getElementById('pre-dc-error');
  if (!modal) { console.error('pre-dc-modal not found in DOM'); return; }
  if (homerEl)  homerEl.textContent    = homerID;
  if (reasonEl) reasonEl.value         = '';
  if (errorEl)  errorEl.style.display  = 'none';
  modal.style.display = 'flex';
  if (reasonEl) reasonEl.focus();
}

function hidePreDiscontinueModal() {
  document.getElementById('pre-dc-modal').style.display = 'none';
  _preDiscHomerID = null;
}

async function submitPreDiscontinue() {
  const reason = document.getElementById('pre-dc-reason').value.trim();
  const errEl  = document.getElementById('pre-dc-error');
  const btn    = document.getElementById('pre-dc-submit');
  errEl.style.display = 'none';

  if (!reason) {
    errEl.textContent = 'Please enter a reason for pre-discontinuation.';
    errEl.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Confirming…';
  try {
    const res = await fetch(`/api/patients/${_preDiscHomerID}/discontinue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.error || 'Failed to pre-discontinue patient';
      errEl.style.display = 'block';
      return;
    }
    hidePreDiscontinueModal();
    showToast(`${_preDiscHomerID} marked as pre-discontinued`, 'info');
    await loadPatients();
  } catch (e) {
    errEl.textContent = 'Network error — please try again';
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Confirm';
  }
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(message, type = 'success') {
  const colors = { success: 'bg-green-600', error: 'bg-red-600', info: 'bg-blue-600' };
  const icons  = { success: 'fa-check-circle', error: 'fa-exclamation-circle', info: 'fa-info-circle' };
  const toast  = document.createElement('div');
  toast.className = `fixed bottom-6 right-6 z-[100] flex items-center gap-3 px-5 py-3 rounded-xl text-white shadow-xl ${colors[type]} transition-all duration-300`;
  toast.innerHTML = `<i class="fas ${icons[type]}"></i><span class="text-sm font-medium">${message}</span>`;
  document.body.appendChild(toast);
  setTimeout(() => { toast.style.opacity = '0'; setTimeout(() => toast.remove(), 300); }, 3000);
}
