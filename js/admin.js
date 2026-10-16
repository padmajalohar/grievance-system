let adminComplaintItems = [];

document.addEventListener('DOMContentLoaded', async () => {
  const token = localStorage.getItem('resolve_token');
  if (!token) {
    location.href = 'login.html';
    return;
  }

  const user = JSON.parse(localStorage.getItem('resolve_user') || '{}');
  if (user.role !== 'admin') {
    location.href = 'dashboard.html';
    return;
  }

  document.querySelectorAll('[data-user-name]').forEach((element) => {
    element.textContent = user.name || 'Admin';
  });
  document.querySelectorAll('[data-user-initial]').forEach((element) => {
    element.textContent = (user.name || 'A')[0].toUpperCase();
  });

  await loadAdminDashboard();

  document.getElementById('adminSearch')?.addEventListener('input', renderAdminComplaints);
  ['adminStatusFilter', 'adminPriorityFilter'].forEach((id) => {
    document.getElementById(id)?.addEventListener('change', renderAdminComplaints);
  });

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
      const response = await fetch(`http://localhost:5001/api/admin/complaints/${currentId}`, {
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
      alert('Complaint updated successfully.');
      document.getElementById('adminDetailModal').classList.remove('show');
      await loadAdminDashboard();
    } catch (error) {
      alert(error.message);
    }
  });
});

async function loadAdminDashboard() {
  const token = localStorage.getItem('resolve_token');
  try {
    const dashboardResponse = await fetch('http://localhost:5001/api/admin/dashboard', {
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

    const complaintsResponse = await fetch('http://localhost:5001/api/admin/complaints', {
      headers: { Authorization: `Bearer ${token}` }
    });
    const complaintsData = await complaintsResponse.json();
    if (!complaintsResponse.ok) {
      throw new Error(complaintsData.error || 'Unable to load complaint list.');
    }

    adminComplaintItems = complaintsData.complaints || [];
    renderAdminComplaints();

    document.querySelectorAll('[data-admin-view]').forEach((button) => {
      button.addEventListener('click', async () => {
        const complaintId = button.getAttribute('data-admin-view');
        const detailResponse = await fetch(`http://localhost:5001/api/complaints/${complaintId}`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        const detailData = await detailResponse.json();
        if (!detailResponse.ok) {
          alert(detailData.error || 'Unable to load complaint details.');
          return;
        }

        const complaint = detailData.complaint;
        const modal = document.getElementById('adminDetailModal');
        modal.dataset.complaintId = complaint.id;
        modal.querySelector('[data-detail-title]').textContent = complaint.title;
        modal.querySelector('[data-detail-description]').textContent = complaint.description;
        modal.querySelector('[data-detail-id]').textContent = complaint.id;
        modal.querySelector('[data-detail-status]').textContent = complaint.status;
        modal.querySelector('[data-detail-department]').textContent = complaint.department || '—';
        modal.querySelector('[data-detail-priority]').textContent = complaint.priority || '—';
        document.getElementById('adminStatus').value = complaint.status || 'Pending';
        document.getElementById('adminDepartment').value = complaint.department || 'Administrator Review Queue';
        document.getElementById('adminPriority').value = complaint.priority || 'Medium';
        document.getElementById('adminResolution').value = complaint.resolution || '';
        modal.classList.add('show');
      });
    });
  } catch (error) {
    alert(error.message);
  }
}

function renderAdminComplaints() {
  const query = document.getElementById('adminSearch')?.value.trim().toLocaleLowerCase() || '';
  const status = document.getElementById('adminStatusFilter')?.value || '';
  const priority = document.getElementById('adminPriorityFilter')?.value || '';
  const filtered = adminComplaintItems.filter((item) => {
    const searchable = `${item.id} ${item.title} ${item.location || ''} ${item.department || ''}`.toLocaleLowerCase();
    return (!query || searchable.includes(query))
      && (!status || item.status === status)
      && (!priority || item.priority === priority);
  });

  const rows = document.getElementById('adminComplaintRows');
  const count = document.getElementById('adminQueueCount');
  if (count) count.textContent = `${filtered.length} of ${adminComplaintItems.length} complaints`;
  rows.innerHTML = filtered.map(item => `
      <tr>
        <td>${item.id}</td>
        <td><strong>${escapeHtml(item.title)}</strong></td>
        <td>${escapeHtml(item.category || '—')}</td>
        <td><span class="badge ${item.priority === 'High' || item.priority === 'Critical' ? 'escalated' : 'progress'}">${escapeHtml(item.priority || '—')}</span></td>
        <td><span class="badge ${item.status.toLowerCase().replace(/\s+/g, '-')}">${escapeHtml(item.status)}</span></td>
        <td>${escapeHtml(item.department || '—')}</td>
        <td>${formatDate(item.deadline)}</td>
        <td><button class="view" data-admin-view="${item.id}">View</button></td>
      </tr>
    `).join('') || '<tr><td colspan="8">No complaints match these filters.</td></tr>';

  rows.querySelectorAll('[data-admin-view]').forEach((button) => {
    button.addEventListener('click', () => openAdminComplaint(button.dataset.adminView));
  });
}

async function openAdminComplaint(complaintId) {
  const token = localStorage.getItem('resolve_token');
  try {
    const response = await fetch(`http://localhost:5001/api/complaints/${complaintId}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Unable to load complaint details.');

    const complaint = result.complaint;
    const modal = document.getElementById('adminDetailModal');
    modal.dataset.complaintId = complaint.id;
    modal.querySelector('[data-detail-title]').textContent = complaint.title;
    modal.querySelector('[data-detail-description]').textContent = complaint.description;
    modal.querySelector('[data-detail-id]').textContent = complaint.id;
    modal.querySelector('[data-detail-status]').textContent = complaint.status;
    modal.querySelector('[data-detail-department]').textContent = complaint.department || '—';
    modal.querySelector('[data-detail-priority]').textContent = complaint.priority || '—';
    configureEvidenceLink(modal, complaint);
    document.getElementById('adminStatus').value = complaint.status || 'Pending';
    document.getElementById('adminDepartment').value = complaint.department || 'Administrator Review Queue';
    document.getElementById('adminAssignedOfficer').value = complaint.assigned_officer || '';
    document.getElementById('adminPriority').value = complaint.priority || 'Medium';
    document.getElementById('adminResolution').value = complaint.resolution || '';
    modal.classList.add('show');
  } catch (error) {
    alert(error.message);
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
