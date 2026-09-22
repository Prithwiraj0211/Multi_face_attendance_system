// Dashboard Logic & Event Handlers
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  loadStats();
  loadEmployees();
  loadLogs();
  setupAddEmployeeModal();
  setupFilters();
  setupLogout();
  setupSecurityTab();
});

// Tab Navigation
function initTabs() {
  const navLinks = document.querySelectorAll('.nav-item a[data-tab]');
  navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const tabId = link.getAttribute('data-tab');

      // Update active nav item
      document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
      link.parentElement.classList.add('active');

      // Update tab panels
      document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));
      const activePanel = document.getElementById(tabId);
      if (activePanel) {
        activePanel.classList.add('active');
      }

      // Refresh data on tab click
      if (tabId === 'overview') loadStats();
      if (tabId === 'employees') loadEmployees();
      if (tabId === 'attendance') loadLogs();
      if (tabId === 'security') {
        loadAdminProfile();
        loadAdminList();
      }
    });
  });
}

// 1. Overview KPIs & Recent Logs
async function loadStats() {
  try {
    const data = await API.get('/attendance/stats');

    document.getElementById('stat-total-emp').textContent = data.total_employees;
    document.getElementById('stat-today-checkins').textContent = data.today_checkins;
    document.getElementById('stat-currently-present').textContent = data.currently_present;
    document.getElementById('stat-attendance-rate').textContent = data.attendance_rate;

    // Database Status Badge
    const dbBadge = document.getElementById('db-status-badge');
    if (dbBadge && data.database) {
      dbBadge.textContent = `${data.database.type} Database Active`;
      dbBadge.className = data.database.is_postgres ? 'badge badge-success' : 'badge badge-warning';
    }

    // Recent Logs Table
    const tbody = document.getElementById('overview-recent-logs');
    if (tbody) {
      if (!data.recent_logs || data.recent_logs.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">No attendance punches recorded yet today.</td></tr>`;
        return;
      }

      tbody.innerHTML = data.recent_logs.map(log => `
        <tr>
          <td>
            <div class="user-cell">
              ${log.snapshot_url ? `<img src="${log.snapshot_url}" class="avatar" alt="${log.employee_name}" />` : `<div class="avatar">${log.employee_name.charAt(0)}</div>`}
              <div>
                <strong>${log.employee_name}</strong>
                <div style="font-size: 0.76rem; color: var(--text-muted);">${log.employee_code}</div>
              </div>
            </div>
          </td>
          <td>${log.department}</td>
          <td>
            <span class="badge ${log.punch_type === 'CHECK_IN' ? 'badge-success' : 'badge-info'}">
              ${log.punch_type}
            </span>
          </td>
          <td class="mono">${log.timestamp}</td>
          <td><span class="badge badge-info">${log.confidence}</span></td>
        </tr>
      `).join('');
    }
  } catch (err) {
    console.error('Failed to load dashboard stats:', err);
  }
}

// 2. Employees Management
async function loadEmployees() {
  const tbody = document.getElementById('employees-table-body');
  if (!tbody) return;

  try {
    const employees = await API.get('/employees/');
    if (employees.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 36px;">No employees registered yet. Click "+ Add Employee" to enroll.</td></tr>`;
      return;
    }

    tbody.innerHTML = employees.map(emp => `
      <tr>
        <td>
          <div class="user-cell">
            ${emp.avatar_url ? `<img src="${emp.avatar_url}" class="avatar" alt="${emp.full_name}" />` : `<div class="avatar">${emp.first_name.charAt(0)}</div>`}
            <div>
              <strong>${emp.full_name}</strong>
              <div style="font-size: 0.76rem; color: var(--text-muted);">${emp.email || 'No email registered'}</div>
            </div>
          </div>
        </td>
        <td class="mono">${emp.employee_code}</td>
        <td>${emp.department}</td>
        <td>${emp.designation}</td>
        <td>
          ${emp.has_face_enrolled 
            ? `<span class="badge badge-success"><span class="pulse-dot green"></span> Enrolled</span>` 
            : `<span class="badge badge-warning">Pending Face</span>`}
        </td>
        <td>
          <div style="display: flex; gap: 8px;">
            <button class="btn btn-secondary btn-sm" onclick="openEnrollFaceModal(${emp.id}, '${emp.full_name}')" title="Enroll/Update Face">
              <svg class="ui-icon ui-icon-xs" viewBox="0 0 24 24"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>
              Enroll Face
            </button>
            <button class="btn btn-danger btn-sm" onclick="deleteEmployee(${emp.id}, '${emp.full_name}')" title="Delete Profile">
              <svg class="ui-icon ui-icon-xs" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
            </button>
          </div>
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Failed to load employees:', err);
  }
}

// 3. Add Employee Modal
let selectedEmployeeIdForEnroll = null;

function setupAddEmployeeModal() {
  const modal = document.getElementById('add-employee-modal');
  const openBtn = document.getElementById('btn-open-add-emp');
  const closeBtn = document.getElementById('btn-close-add-emp');
  const form = document.getElementById('add-employee-form');

  if (openBtn) {
    openBtn.addEventListener('click', () => {
      form.reset();
      modal.classList.add('active');
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', () => modal.classList.remove('active'));
  }

  if (form) {
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const code = document.getElementById('emp-code').value.trim();
      const firstName = document.getElementById('emp-first-name').value.trim();
      const lastName = document.getElementById('emp-last-name').value.trim();
      const email = document.getElementById('emp-email').value.trim();
      const department = document.getElementById('emp-dept').value.trim();
      const designation = document.getElementById('emp-desig').value.trim();

      try {
        const emp = await API.post('/employees/', {
          employee_code: code,
          first_name: firstName,
          last_name: lastName,
          email: email || null,
          department: department || 'Engineering',
          designation: designation || 'Specialist'
        });

        modal.classList.remove('active');
        loadEmployees();

        // Immediately prompt to enroll face
        openEnrollFaceModal(emp.id, emp.full_name);
      } catch (err) {
        alert(err.message);
      }
    });
  }

  // Enroll Face Modal Handlers
  const enrollModal = document.getElementById('enroll-face-modal');
  const closeEnrollBtn = document.getElementById('btn-close-enroll');
  if (closeEnrollBtn) {
    closeEnrollBtn.addEventListener('click', () => enrollModal.classList.remove('active'));
  }

  // Camera Capture Button
  const btnCaptureCamera = document.getElementById('btn-capture-camera');
  if (btnCaptureCamera) {
    btnCaptureCamera.addEventListener('click', async () => {
      if (!selectedEmployeeIdForEnroll) return;
      btnCaptureCamera.disabled = true;
      btnCaptureCamera.innerHTML = `
        <span class="pulse-dot blue" style="margin-right: 6px;"></span> Processing Biometric...
      `;

      try {
        const res = await API.post(`/employees/${selectedEmployeeIdForEnroll}/capture-camera`, {});
        alert(`Success: ${res.message}`);
        enrollModal.classList.remove('active');
        loadEmployees();
        loadStats();
      } catch (err) {
        alert(`Enrollment Error: ${err.message}`);
      } finally {
        btnCaptureCamera.disabled = false;
        btnCaptureCamera.innerHTML = `
          <svg class="ui-icon ui-icon-sm" viewBox="0 0 24 24"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"></path><circle cx="12" cy="13" r="4"></circle></svg>
          Snap Face from Live Camera (1-Click)
        `;
      }
    });
  }

  // Photo Upload Button
  const fileInput = document.getElementById('enroll-file-input');
  if (fileInput) {
    fileInput.addEventListener('change', async (e) => {
      if (!selectedEmployeeIdForEnroll || !e.target.files[0]) return;
      const file = e.target.files[0];
      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await API.post(`/employees/${selectedEmployeeIdForEnroll}/upload-face`, formData);
        alert(`Success: ${res.message}`);
        enrollModal.classList.remove('active');
        loadEmployees();
        loadStats();
      } catch (err) {
        alert(`Upload Error: ${err.message}`);
      }
    });
  }
}

window.openEnrollFaceModal = function(empId, empName) {
  selectedEmployeeIdForEnroll = empId;
  const enrollModal = document.getElementById('enroll-face-modal');
  const title = document.getElementById('enroll-modal-title');
  if (title) title.textContent = `Enroll Face for ${empName}`;

  // Start preview feed in modal
  const previewImg = document.getElementById('enroll-camera-feed');
  if (previewImg) {
    previewImg.src = `/api/stream/raw_feed?t=${Date.now()}`;
  }

  enrollModal.classList.add('active');
};

window.deleteEmployee = async function(empId, empName) {
  if (!confirm(`Are you sure you want to delete ${empName}? All biometric face data and logs will be permanently removed.`)) {
    return;
  }
  try {
    await API.delete(`/employees/${empId}`);
    loadEmployees();
    loadStats();
  } catch (err) {
    alert(err.message);
  }
};

// 4. Attendance Logs Filter & Export
function setupFilters() {
  const dateInput = document.getElementById('log-filter-date');
  const typeSelect = document.getElementById('log-filter-type');
  const btnExport = document.getElementById('btn-export-csv');

  // Default to today
  if (dateInput && !dateInput.value) {
    const today = new Date().toISOString().split('T')[0];
    dateInput.value = today;
  }

  if (dateInput) dateInput.addEventListener('change', () => loadLogs());
  if (typeSelect) typeSelect.addEventListener('change', () => loadLogs());

  if (btnExport) {
    btnExport.addEventListener('click', () => {
      const date = dateInput ? dateInput.value : '';
      const punchType = typeSelect ? typeSelect.value : '';
      let url = `/api/attendance/export-csv?`;
      if (date) url += `date=${encodeURIComponent(date)}&`;
      if (punchType) url += `punch_type=${encodeURIComponent(punchType)}&`;
      window.location.href = url;
    });
  }
}

async function loadLogs() {
  const tbody = document.getElementById('attendance-table-body');
  if (!tbody) return;

  const dateInput = document.getElementById('log-filter-date');
  const typeSelect = document.getElementById('log-filter-type');

  const date = dateInput ? dateInput.value : '';
  const punchType = typeSelect ? typeSelect.value : '';

  let query = `?limit=100`;
  if (date) query += `&date=${date}`;
  if (punchType) query += `&punch_type=${punchType}`;

  try {
    const data = await API.get(`/attendance/logs${query}`);
    if (!data.items || data.items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 36px;">No attendance logs found matching the selected filters.</td></tr>`;
      return;
    }

    tbody.innerHTML = data.items.map(log => `
      <tr>
        <td>
          <div class="user-cell">
            ${log.snapshot_url ? `<img src="${log.snapshot_url}" class="avatar" alt="${log.employee_name}" />` : `<div class="avatar">${log.employee_name.charAt(0)}</div>`}
            <div>
              <strong>${log.employee_name}</strong>
              <div style="font-size: 0.76rem; color: var(--text-muted);">${log.employee_code}</div>
            </div>
          </div>
        </td>
        <td>${log.department}</td>
        <td>
          <span class="badge ${log.punch_type === 'CHECK_IN' ? 'badge-success' : 'badge-info'}">
            ${log.punch_type}
          </span>
        </td>
        <td class="mono">${log.timestamp}</td>
        <td><span class="badge badge-info">${log.confidence}</span></td>
        <td>
          ${log.snapshot_url ? `<a href="${log.snapshot_url}" target="_blank" class="btn btn-secondary btn-sm" style="gap: 6px;"><svg class="ui-icon ui-icon-xs" viewBox="0 0 24 24"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></svg> Proof</a>` : '-'}
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Failed to load logs:', err);
  }
}

// 5. Logout
function setupLogout() {
  const btnLogout = document.getElementById('btn-logout');
  if (btnLogout) {
    btnLogout.addEventListener('click', async (e) => {
      e.preventDefault();
      await API.post('/auth/logout', {});
      localStorage.removeItem('token');
      window.location.href = '/admin/login';
    });
  }
}

// 6. Security & Admin User Management
async function loadAdminProfile() {
  try {
    const profile = await API.get('/auth/me');
    const userField = document.getElementById('profile-username');
    const nameField = document.getElementById('profile-fullname');
    if (userField && profile.username) userField.value = profile.username;
    if (nameField && profile.full_name) nameField.value = profile.full_name;
  } catch (err) {
    console.error('Failed to load profile:', err);
  }
}

async function loadAdminList() {
  const tbody = document.getElementById('admins-table-body');
  if (!tbody) return;

  try {
    const admins = await API.get('/auth/admins');
    if (!admins || admins.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 24px;">No administrators found.</td></tr>';
      return;
    }

    tbody.innerHTML = admins.map(a => `
      <tr>
        <td>
          <div class="user-cell">
            <div class="avatar" style="background: ${a.is_current ? 'rgba(99, 102, 241, 0.25)' : '#1e293b'}; color: ${a.is_current ? '#818cf8' : '#fff'};">
              ${a.username.charAt(0).toUpperCase()}
            </div>
            <div>
              <strong>${a.username}</strong> ${a.is_current ? '<span class="badge badge-info" style="margin-left: 6px; font-size: 0.65rem; padding: 2px 6px;">You</span>' : ''}
              <div style="font-size: 0.76rem; color: var(--text-muted);">${a.full_name || 'Administrator'}</div>
            </div>
          </div>
        </td>
        <td>
          <span class="badge ${a.role === 'SUPER_ADMIN' ? 'badge-success' : 'badge-info'}">
            ${a.role}
          </span>
        </td>
        <td class="mono" style="font-size: 0.8rem;">${a.created_at}</td>
        <td>
          ${a.is_current ? `
            <span style="font-size: 0.78rem; color: var(--text-muted);">Active Session</span>
          ` : `
            <button class="btn btn-danger btn-sm" onclick="deleteAdmin(${a.id}, '${a.username}')" title="Delete Administrator">
              <svg class="ui-icon ui-icon-xs" viewBox="0 0 24 24"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
            </button>
          `}
        </td>
      </tr>
    `).join('');
  } catch (err) {
    console.error('Failed to load admins list:', err);
  }
}

function setupSecurityTab() {
  const profileForm = document.getElementById('update-profile-form');
  const statusMsg = document.getElementById('profile-status-msg');

  if (profileForm) {
    profileForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = document.getElementById('profile-username').value.trim();
      const fullName = document.getElementById('profile-fullname').value.trim();
      const currentPwd = document.getElementById('profile-current-pwd').value;
      const newPwd = document.getElementById('profile-new-pwd').value;
      const confirmPwd = document.getElementById('profile-confirm-pwd').value;

      statusMsg.style.display = 'none';

      if (newPwd) {
        if (newPwd !== confirmPwd) {
          showProfileMsg('New passwords do not match.', false);
          return;
        }
        if (!currentPwd) {
          showProfileMsg('Please enter your current password to authorize password change.', false);
          return;
        }
      }

      const payload = {
        username: username,
        full_name: fullName
      };
      if (newPwd) {
        payload.current_password = currentPwd;
        payload.new_password = newPwd;
      }

      try {
        const res = await API.put('/auth/profile', payload);
        showProfileMsg(res.message || 'Profile updated successfully.', true);

        // Update token if username changed
        if (res.access_token) {
          localStorage.setItem('token', res.access_token);
        }

        // Update top bar admin name
        const topBarAdmin = document.querySelector('.top-bar-left p strong');
        if (topBarAdmin && res.user) {
          topBarAdmin.textContent = res.user.username;
        }

        // Clear password fields
        document.getElementById('profile-current-pwd').value = '';
        document.getElementById('profile-new-pwd').value = '';
        document.getElementById('profile-confirm-pwd').value = '';

        loadAdminList();
      } catch (err) {
        showProfileMsg(err.message || 'Failed to update profile.', false);
      }
    });
  }

  function showProfileMsg(text, isSuccess) {
    if (!statusMsg) return;
    statusMsg.textContent = text;
    statusMsg.style.display = 'block';
    if (isSuccess) {
      statusMsg.style.background = 'rgba(16, 185, 129, 0.15)';
      statusMsg.style.color = '#34d399';
      statusMsg.style.border = '1px solid rgba(16, 185, 129, 0.3)';
    } else {
      statusMsg.style.background = 'rgba(244, 63, 94, 0.15)';
      statusMsg.style.color = '#fb7185';
      statusMsg.style.border = '1px solid rgba(244, 63, 94, 0.3)';
    }
  }

  // Add Admin Modal
  const addAdminModal = document.getElementById('add-admin-modal');
  const openAddAdminBtn = document.getElementById('btn-open-add-admin');
  const closeAddAdminBtn = document.getElementById('btn-close-add-admin');
  const addAdminForm = document.getElementById('add-admin-form');
  const newAdminError = document.getElementById('new-admin-error');

  if (openAddAdminBtn) {
    openAddAdminBtn.addEventListener('click', () => {
      if (addAdminForm) addAdminForm.reset();
      if (newAdminError) newAdminError.style.display = 'none';
      if (addAdminModal) addAdminModal.classList.add('active');
    });
  }

  if (closeAddAdminBtn) {
    closeAddAdminBtn.addEventListener('click', () => {
      if (addAdminModal) addAdminModal.classList.remove('active');
    });
  }

  if (addAdminForm) {
    addAdminForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const username = document.getElementById('new-admin-username').value.trim();
      const fullName = document.getElementById('new-admin-fullname').value.trim();
      const password = document.getElementById('new-admin-password').value;
      const role = document.getElementById('new-admin-role').value;

      if (newAdminError) newAdminError.style.display = 'none';

      try {
        const res = await API.post('/auth/admins', {
          username,
          full_name: fullName,
          password,
          role
        });
        alert(res.message || 'Administrator created successfully.');
        addAdminModal.classList.remove('active');
        loadAdminList();
      } catch (err) {
        if (newAdminError) {
          newAdminError.textContent = err.message || 'Failed to create administrator.';
          newAdminError.style.display = 'block';
        } else {
          alert(err.message);
        }
      }
    });
  }
}

window.deleteAdmin = async function(adminId, adminUsername) {
  if (!confirm(`Are you sure you want to revoke access and delete administrator '${adminUsername}'?`)) {
    return;
  }

  try {
    const res = await API.delete(`/auth/admins/${adminId}`);
    alert(res.message || 'Administrator deleted.');
    loadAdminList();
  } catch (err) {
    alert(err.message);
  }
};

