let adminComplaintItems = [];
let adminDepartmentStaff = [];
let adminManagedDepartments = [];

const PREDEFINED_ADMIN_DEPARTMENTS = [
  'Administration Office',
  'Sanitation Department',
  'Electrical & Street Lighting Department',
  'Electricity Department',
  'Water Supply Department',
  'Waste Management Department',
  'Road & Transport Department',
  'Drainage Department',
  'Public Infrastructure Department',
  'Street Lighting Department',
  'Campus Facilities Department',
  'Health Department',
  'Education Department',
  'Public Works Department',
  'Parks & Gardens Department',
  'Animal Control Department',
  'Fire & Emergency Services Department',
  'Town Planning Department'
];

document.addEventListener('DOMContentLoaded', async () => {
  const token = localStorage.getItem('resolve_token');
  if (!token) {
    location.href = 'login.html';
    return;
  }

  const user = JSON.parse(localStorage.getItem('resolve_user') || '{}');
  if (user.role !== 'admin') {
    location.href = user.role === 'department_staff' ? 'department.html' : 'dashboard.html';
    return;
  }

  document.querySelectorAll('[data-user-name]').forEach((element) => {
    element.textContent = user.name || 'Admin';
  });
  document.querySelectorAll('[data-user-initial]').forEach((element) => {
    element.textContent = (user.name || 'A')[0].toUpperCase();
  });

  await loadAdminDashboard();
  await loadAdminDepartmentManagement();

  document.getElementById('adminSearch')?.addEventListener('input', renderAdminComplaints);
  ['adminStatusFilter', 'adminPriorityFilter', 'adminDepartmentFilter'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', renderAdminComplaints);
  });
  document.addEventListener('resolveai:languagechange', () => {
    updateAdminDepartmentFilterOptions();
    renderAdminComplaints();
    renderAdminDepartmentManagement();
    window.refreshAdminCivicRewards?.();
    const modal = document.getElementById('adminDetailModal');
    if (modal?.dataset.complaintId) {
      modal.querySelector('[data-detail-status]').textContent = t(modal.dataset.status || '');
      modal.querySelector('[data-detail-department]').textContent = t(modal.dataset.department || '—');
      modal.querySelector('[data-detail-priority]').textContent = t(modal.dataset.priority || '—');
    }
    document.querySelectorAll('#adminDepartment option').forEach(option => {
      option.textContent = t(option.value);
    });
  });

  document.getElementById('departmentStaffForm')?.addEventListener('submit', createDepartmentStaff);
  document.getElementById('departmentCreateForm')?.addEventListener('submit', createDepartment);
  document.getElementById('departmentStaffRows')?.addEventListener('click', toggleDepartmentStaff);

  document.querySelector('[data-close]')?.addEventListener('click', () => {
    document.getElementById('adminDetailModal').classList.remove('show');
  });

  document.getElementById('saveAdminUpdate')?.addEventListener('click', async () => {
    const currentId = document.getElementById('adminDetailModal').dataset.complaintId;
    if (!currentId) return;

    const payload = {
      status: document.getElementById('adminStatus').value,
      department: document.getElementById('adminDepartment').value,
      assigned_officer: document.getElementById('adminAssignedOfficer').value.trim(),
      priority: document.getElementById('adminPriority').value,
      resolution: document.getElementById('adminResolution').value.trim(),
      reason: 'Administrator updated the complaint record.'
    };

    try {
      const response = await fetch(window.resolveApiUrl(`/api/admin/complaints/${currentId}`), {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(payload)
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || 'Unable to update complaint.');
      }
      alert(t('Complaint updated successfully.'));
      document.getElementById('adminDetailModal').classList.remove('show');
      await loadAdminDashboard();
    } catch (error) {
      alert(t(error.message));
    }
  });
});

async function loadAdminDashboard() {
  const token = localStorage.getItem('resolve_token');
  try {
    const dashboardResponse = await fetch(window.resolveApiUrl('/api/admin/dashboard'), {
      headers: { Authorization: `Bearer ${token}` }
    });
    const dashboardData = await dashboardResponse.json();
    if (!dashboardResponse.ok) {
      throw new Error(dashboardData.error || 'Unable to load admin dashboard.');
    }

    Object.entries(dashboardData.stats).forEach(([key, value]) => {
      const element = document.querySelector(`[data-admin-stat="${key}"]`);
      if (element) element.textContent = value;
    });

    const complaintsResponse = await fetch(window.resolveApiUrl('/api/admin/complaints'), {
      headers: { Authorization: `Bearer ${token}` }
    });
    const complaintsData = await complaintsResponse.json();
    if (!complaintsResponse.ok) {
      throw new Error(complaintsData.error || 'Unable to load complaint list.');
    }

    adminComplaintItems = complaintsData.complaints || [];
    updateAdminDepartmentFilterOptions();
    renderAdminComplaints();

    document.querySelectorAll('[data-admin-view]').forEach((button) => {
      if (button.dataset.detailHandlerBound) return;
      button.dataset.detailHandlerBound = 'true';
      button.addEventListener('click', async () => {
        const complaintId = button.getAttribute('data-admin-view');
        const detailResponse = await fetch(window.resolveApiUrl(`/api/complaints/${complaintId}`), {
          headers: { Authorization: `Bearer ${token}` }
        });
        const detailData = await detailResponse.json();
        if (!detailResponse.ok) {
          alert(t(detailData.error || 'Unable to load complaint details.'));
          return;
        }

        const complaint = detailData.complaint;
        const modal = document.getElementById('adminDetailModal');
        modal.dataset.complaintId = complaint.id;
        modal.dataset.status = complaint.status || '';
        modal.dataset.department = complaint.department || '—';
        modal.dataset.priority = complaint.priority || '—';
        modal.querySelector('[data-detail-title]').textContent = complaint.title;
        modal.querySelector('[data-detail-description]').textContent = complaint.description;
        modal.querySelector('[data-detail-id]').textContent = complaint.id;
        modal.querySelector('[data-detail-status]').textContent = t(complaint.status);
        modal.querySelector('[data-detail-department]').textContent = t(complaint.department || '—');
        modal.querySelector('[data-detail-priority]').textContent = t(complaint.priority || '—');
        document.getElementById('adminStatus').value = complaint.status || 'Pending';
        setAdminDepartmentAssignment(complaint.department);
        document.getElementById('adminPriority').value = complaint.priority || 'Medium';
        document.getElementById('adminResolution').value = complaint.resolution || '';
        modal.classList.add('show');
      });
    });
  } catch (error) {
    alert(t(error.message));
  }
}

async function loadAdminDepartmentManagement() {
  try {
    const [departments, staff] = await Promise.all([
      apiRequest('/api/admin/departments'),
      apiRequest('/api/admin/department-staff')
    ]);
    adminManagedDepartments = departments.departments || [];
    adminDepartmentStaff = staff.staff || [];
    renderAdminDepartmentManagement();
  } catch (error) {
    setDepartmentStaffMessage(error.message, true);
  }
}

function renderAdminDepartmentManagement() {
  const departmentSelect = document.getElementById('departmentStaffDepartment');
  const staffRows = document.getElementById('departmentStaffRows');
  if (!departmentSelect || !staffRows) return;

  const selectedDepartment = departmentSelect.value;
  departmentSelect.replaceChildren(new Option(t('Select a department'), ''));
  adminManagedDepartments.forEach(department => {
    departmentSelect.add(new Option(t(department.name), department.name));
  });
  departmentSelect.value = selectedDepartment;

  staffRows.innerHTML = adminDepartmentStaff.map(staff => `
    <tr>
      <td>${escapeHtml(staff.name)}</td>
      <td>${escapeHtml(staff.email)}</td>
      <td>${escapeHtml(t(staff.department))}</td>
      <td>${escapeHtml(t(staff.is_active ? 'Active' : 'Disabled'))}</td>
      <td><button class="view" type="button" data-staff-toggle="${staff.id}" data-active="${staff.is_active ? 'true' : 'false'}">${escapeHtml(t(staff.is_active ? 'Disable' : 'Enable'))}</button></td>
    </tr>
  `).join('') || `<tr><td colspan="5">${escapeHtml(t('No department staff accounts yet.'))}</td></tr>`;
}

async function createDepartmentStaff(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await apiRequest('/api/admin/department-staff', {
      method: 'POST',
      body: JSON.stringify({
        name: document.getElementById('departmentStaffName').value.trim(),
        email: document.getElementById('departmentStaffEmail').value.trim(),
        password: document.getElementById('departmentStaffPassword').value,
        department: document.getElementById('departmentStaffDepartment').value
      })
    });
    form.reset();
    setDepartmentStaffMessage('Department staff account created.');
    await loadAdminDepartmentManagement();
  } catch (error) {
    setDepartmentStaffMessage(error.message, true);
  }
}

async function createDepartment(event) {
  event.preventDefault();
  const form = event.currentTarget;
  try {
    await apiRequest('/api/admin/departments', {
      method: 'POST',
      body: JSON.stringify({ name: document.getElementById('newDepartmentName').value.trim() })
    });
    form.reset();
    setDepartmentStaffMessage('Department added.');
    await loadAdminDepartmentManagement();
    updateAdminDepartmentFilterOptions();
  } catch (error) {
    setDepartmentStaffMessage(error.message, true);
  }
}

async function toggleDepartmentStaff(event) {
  const button = event.target.closest('[data-staff-toggle]');
  if (!button) return;
  try {
    await apiRequest(`/api/admin/department-staff/${button.dataset.staffToggle}`, {
      method: 'PATCH',
      body: JSON.stringify({ is_active: button.dataset.active !== 'true' })
    });
    setDepartmentStaffMessage('Department staff account updated.');
    await loadAdminDepartmentManagement();
  } catch (error) {
    setDepartmentStaffMessage(error.message, true);
  }
}

function setDepartmentStaffMessage(message, isError = false) {
  const element = document.getElementById('departmentStaffMessage');
  if (!element) return;
  element.textContent = t(message);
  element.classList.toggle('error', isError);
}

function updateAdminDepartmentFilterOptions() {
  const departmentFilter = document.getElementById('adminDepartmentFilter');
  if (!departmentFilter) return;

  const selectedDepartment = departmentFilter.value;
  const departments = new Map();
  [...PREDEFINED_ADMIN_DEPARTMENTS, ...adminManagedDepartments.map(item => item.name), ...adminComplaintItems.map(item => item.department || '')]
    .map(department => String(department).trim())
    .filter(Boolean)
    .forEach(department => {
      const key = department.toLocaleLowerCase();
      if (!departments.has(key)) departments.set(key, department);
    });

  const sortedDepartments = [...departments.values()].sort((first, second) => first.localeCompare(second));
  departmentFilter.replaceChildren(new Option(t('All Departments'), ''));
  sortedDepartments.forEach(department => {
    departmentFilter.add(new Option(t(department), department));
  });
  departmentFilter.value = [...departmentFilter.options].some(option => option.value === selectedDepartment)
    ? selectedDepartment
    : '';
}

function setAdminDepartmentAssignment(value) {
  const departmentSelect = document.getElementById('adminDepartment');
  const department = value || 'Administrator Review Queue';
  adminManagedDepartments.forEach(item => {
    if (![...departmentSelect.options].some(option => option.value === item.name)) {
      departmentSelect.add(new Option(t(item.name), item.name));
    }
  });
  if (![...departmentSelect.options].some(option => option.value === department)) {
    departmentSelect.add(new Option(t(department), department));
  }
  [...departmentSelect.options].forEach(option => {
    option.textContent = t(option.value);
  });
  departmentSelect.value = department;
}

function renderAdminComplaints() {
  const query = document.getElementById('adminSearch')?.value.trim().toLocaleLowerCase() || '';
  const status = document.getElementById('adminStatusFilter')?.value || '';
  const priority = document.getElementById('adminPriorityFilter')?.value || '';
  const department = document.getElementById('adminDepartmentFilter')?.value.trim().toLocaleLowerCase() || '';
  const filtered = adminComplaintItems.filter((item) => {
    const searchable = `${item.id} ${item.title} ${item.location || ''} ${item.department || ''}`.toLocaleLowerCase();
    return (!query || searchable.includes(query))
      && (!status || item.status === status)
      && (!priority || item.priority === priority)
      && (!department || String(item.department || '').trim().toLocaleLowerCase() === department);
  });

  const rows = document.getElementById('adminComplaintRows');
  const count = document.getElementById('adminQueueCount');
  if (count) count.textContent = t('{{count}} of {{total}} complaints', { count: filtered.length, total: adminComplaintItems.length });
  rows.innerHTML = filtered.map(item => `
      <tr>
        <td>${item.id}</td>
        <td><strong>${escapeHtml(item.title)}</strong></td>
        <td>${escapeHtml(t(item.category || '—'))}</td>
        <td><span class="badge ${item.priority === 'High' || item.priority === 'Critical' ? 'escalated' : 'progress'}">${escapeHtml(t(item.priority || '—'))}</span></td>
        <td><span class="badge ${item.status.toLowerCase().replace(/\s+/g, '-')}">${escapeHtml(t(item.status))}</span></td>
        <td>${escapeHtml(t(item.department || '—'))}</td>
        <td>${formatDate(item.deadline)}</td>
        <td><button class="view" data-admin-view="${item.id}">${escapeHtml(t('View'))}</button></td>
      </tr>
    `).join('') || `<tr><td colspan="8">${escapeHtml(t('No complaints match these filters.'))}</td></tr>`;

  rows.querySelectorAll('[data-admin-view]').forEach((button) => {
    if (button.dataset.detailHandlerBound) return;
    button.dataset.detailHandlerBound = 'true';
    button.addEventListener('click', () => openAdminComplaint(button.dataset.adminView));
  });
}

async function openAdminComplaint(complaintId) {
  const token = localStorage.getItem('resolve_token');
  try {
    const response = await fetch(window.resolveApiUrl(`/api/complaints/${complaintId}`), {
      headers: { Authorization: `Bearer ${token}` }
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Unable to load complaint details.');

    const complaint = result.complaint;
    const modal = document.getElementById('adminDetailModal');
    modal.dataset.complaintId = complaint.id;
    modal.dataset.status = complaint.status || '';
    modal.dataset.department = complaint.department || '—';
    modal.dataset.priority = complaint.priority || '—';
    modal.querySelector('[data-detail-title]').textContent = complaint.title;
    modal.querySelector('[data-detail-description]').textContent = complaint.description;
    modal.querySelector('[data-detail-id]').textContent = complaint.id;
    modal.querySelector('[data-detail-status]').textContent = t(complaint.status);
    modal.querySelector('[data-detail-department]').textContent = t(complaint.department || '—');
    modal.querySelector('[data-detail-priority]').textContent = t(complaint.priority || '—');
    configureEvidenceLink(modal, complaint);
    document.getElementById('adminStatus').value = complaint.status || 'Pending';
    setAdminDepartmentAssignment(complaint.department);
    document.getElementById('adminAssignedOfficer').value = complaint.assigned_officer || '';
    document.getElementById('adminPriority').value = complaint.priority || 'Medium';
    document.getElementById('adminResolution').value = complaint.resolution || '';
    modal.classList.add('show');
  } catch (error) {
    alert(t(error.message));
  }
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}
