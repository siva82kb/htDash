/* ============================================================
   app.js — Global state, auth, session restore, navigation, logout, sidebar toggle
   HOMER Clinical Dashboard
   ============================================================ */

    // Global State
    let currentUser = null;
    let currentPage = 'dashboard';
    let allPatients = [];
    let currentFilter = 'all';
    let droppedOutPatients = new Set();      // Track patients who have dropped out
    let trialCompletedPatients = new Set(); // Track patients whose trial is fully complete
    let selectedPatientData = null;
    let exercisesData = {};
    let currentExercisesPage = 'overview';
    let selectedExercises = [];
    let allDeviceSets = [];   // Cached device sets for assignment filtering
    let allWatches = [];      // Cached watches for assignment filtering

    // Initialize — await auth before running page-specific init
    document.addEventListener('DOMContentLoaded', async () => {
      try {
        await checkAuth();
      } catch(e) {
        console.error('Auth error:', e);
        return;
      }
      if (typeof initPage === 'function') {
        try { initPage(); } catch(e) { console.error('Page init error:', e); }
      }
    });

    async function checkAuth() {
      if (USE_LOCAL_STORAGE) {
        const stored = localStorage.getItem('user');
        if (stored) {
          currentUser = JSON.parse(stored);
          updateUserInfo();
          return;
        }
      }
      try {
        const response = await fetch('/api/me');
        if (!response.ok) { window.location.href = '/login'; return; }
        currentUser = await response.json();
        if (USE_LOCAL_STORAGE) localStorage.setItem('user', JSON.stringify(currentUser));
        updateUserInfo();
      } catch(e) {
        window.location.href = '/login';
      }
    }

    function updateUserInfo() {
      if (currentUser) {
        document.getElementById('user-initials').textContent = currentUser.loginId.slice(0, 2).toUpperCase();
        document.getElementById('user-name').textContent = currentUser.loginId;
        document.getElementById('user-place').textContent = `${currentUser.place} • ${currentUser.privilege}`;
        const locationName = document.getElementById('location-name');
        if (locationName) locationName.textContent = currentUser.place;
        const locationPrivilege = document.getElementById('location-privilege');
        if (locationPrivilege) locationPrivilege.textContent = currentUser.privilege === 'admin' ? 'Full Administrative Access' : 'Site Access';
        if (currentUser.privilege === 'admin') {
          document.getElementById('add-patient-btn')?.classList.remove('hidden');
          document.getElementById('filter-unassigned')?.classList.remove('hidden');
        }
        // Hide Devices nav link for therapists (only engineers and admins)
        if (currentUser.privilege !== 'admin' && currentUser.privilege !== 'engineer') {
          document.querySelector('a[href="/devices"]')?.classList.add('hidden');
        }
      }
    }

    // Load Exercises Data
    async function loadExercisesData() {
      try {
        const response = await fetch('/static/data/exercises_data.json');
        exercisesData = await response.json();
      } catch (error) {
        console.error('Error loading exercises:', error);
      }
    }

    // Navigation
    function navigate(page) {
      // Close patient detail modal if open
      const patientModal = document.getElementById('patient-detail-modal');
      if (patientModal && !patientModal.classList.contains('hidden')) {
        patientModal.classList.add('hidden');
        selectedPatientData = null;
      }
      
      document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
      document.getElementById(`nav-${page}`).classList.add('active');
      document.querySelectorAll('[id^="content-"]').forEach(el => el.classList.add('hidden'));
      const target = document.getElementById(`content-${page}`);
      target.classList.remove('hidden');
      
      const titles = {
        'dashboard': { title: 'Dashboard', subtitle: 'Overview' },
        'patients': { title: 'Patients', subtitle: 'Manage patients' },
        'devices': { title: 'Device Management', subtitle: 'Manage devices and watches' },
        'sims': { title: 'SIM Cards', subtitle: 'Manage SIM cards' }
      };
      document.getElementById('page-title').textContent = titles[page].title;
      document.getElementById('page-subtitle').textContent = titles[page].subtitle;
      currentPage = page;
      if (page === 'patients') {
        loadPatients();
        logActivity('VIEWED_PATIENTS');
      } else if (page === 'devices') {
        loadDevicesPage();
        logActivity('VIEWED_DEVICES');
      } else if (page === 'sims') {
        loadSimsPage();
        logActivity('VIEWED_SIMS');
      } else if (page === 'dashboard') {
        logActivity('VIEWED_DASHBOARD');
      }
      const sidebar = document.getElementById('sidebar');
      if (window.innerWidth < 1024) { sidebar.classList.add('-translate-x-full'); document.getElementById('sidebar-overlay').classList.add('hidden'); }
    }

    function logout() {
      if (USE_LOCAL_STORAGE) localStorage.removeItem('user');
      fetch('/logout', { method: 'POST' }).finally(() => {
        window.location.href = '/login';
      });
    }


    // ============================================================
    // Activity Logging Utility
    // Logs all user activities to the backend for tracking
    // ============================================================
    async function logActivity(action, details = null) {
      if (!currentUser || !currentUser.loginId) return;
      
      const activityData = {
        user_id: currentUser.loginId,
        action: action,
        details: details
      };
      
      try {
        await fetch('/track-activity', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(activityData)
        });
      } catch (e) {
        console.warn('Activity log failed:', e);
      }
    }

    function toggleSidebar() {
      const sidebar = document.getElementById('sidebar'), overlay = document.getElementById('sidebar-overlay');
      if (sidebar.classList.contains('-translate-x-full')) { sidebar.classList.remove('-translate-x-full'); overlay.classList.remove('hidden'); }
      else { sidebar.classList.add('-translate-x-full'); overlay.classList.add('hidden'); }
    }