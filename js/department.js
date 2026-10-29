let departmentComplaintItems = [];
let currentDepartmentComplaintId = '';

document.addEventListener('DOMContentLoaded', async () => {
  let user;
  try {
    user = JSON.parse(localStorage.getItem('resolve_user') || 'null');
  } catch (_error) {
    user = null;
  }
  if (!user || !localStorage.getItem('resolve_token') || user.role !== 'department_staff') {
    location.href = !user || !localStorage.getItem('resolve_token')
      ? 'login.html'
      : user.role === 'admin'
        ? 'admin.html'
        : 'my-grievances.html';
    return;
  }

  const search = document.getElementById('departmentSearch');
  const status = document.getElementById('departmentStatusFilter');
  const priority = document.getElementById('departmentPriorityFilter');
  search?.addEventListener('input', renderDepartmentComplaints);
  status?.addEventListener('change', renderDepartmentComplaints);
  priority?.addEventListener('change', renderDepartmentComplaints);
  document.getElementById('departmentComplaintRows')?.addEventListener('click', handleDepartmentView);
  document.getElementById('departmentUpdateForm')?.addEventListener('submit', saveDepartmentUpdate);
  const modal = document.getElementById('departmentDetailModal');
  modal?.querySelector('[data-close]')?.addEventListener('click', () => modal.classList.remove('show'));
  modal?.addEventListener('click', event => {
    if (event.target === modal) modal.classList.remove('show');
  });
  document.addEventListener('resolveai:languagechange', renderDepartmentComplaints);

  try {
    const [dashboard, complaints] = await Promise.all([
      apiRequest('/api/department/dashboard'),
      apiRequest('/api/department/complaints')
    ]);
    document.getElementById('departmentName').textContent = t(dashboard.department);
    renderDepartmentStats(dashboard.stats);
    departmentComplaintItems = complaints.complaints || [];
    renderDepartmentComplaints();
  } catch (error) {
    if (error.status === 401) {
      localStorage.removeItem('resolve_token');
      localStorage.removeItem('resolve_user');
      location.href = 'login.html';
      return;
    }
    const message = document.getElementById('departmentLoadMessage');
    if (message) {
      message.textContent = t(error.message || 'Unable to load department dashboard.');
      message.hidden = false;
    }
  }
});

function renderDepartmentStats(stats) {
  const container = document.getElementById('departmentStats');
  if (!container) return;
  const entries = [
    ['Total complaints', stats.total],
    ...Object.entries(stats.priority_counts || {}).map(([priority, count]) => [t(`${priority} priority`), count]),
    ...Object.entries(stats.status_counts || {}).map(([status, count]) => [status, count]),
    ['Overdue', stats.overdue]
  ];
  container.innerHTML = entries.map(([label, count]) => `
    <div class="stat"><p>${escapeHtml(label)} <i></i></p><strong>${Number(count) || 0}</strong></div>
  `).join('');
}

function renderDepartmentComplaints() {
  const query = document.getElementById('departmentSearch')?.value.trim().toLocaleLowerCase() || '';
  const status = document.getElementById('departmentStatusFilter')?.value || '';
  const priority = document.getElementById('departmentPriorityFilter')?.value || '';
  const filtered = departmentComplaintItems.filter(complaint => {
    const searchable = `${complaint.id} ${complaint.title} ${complaint.location || ''}`.toLocaleLowerCase();
    return (!query || searchable.includes(query))
      && (!status || complaint.status === status)
      && (!priority || complaint.priority === priority);
  });
  const rows = document.getElementById('departmentComplaintRows');
  if (!rows) return;
  rows.innerHTML = filtered.map(complaint => `
    <tr>
      <td>${escapeHtml(complaint.id)}</td>
      <td><strong>${escapeHtml(complaint.title)}</strong></td>
      <td>${escapeHtml(t(complaint.category || '—'))}</td>
      <td><span class="badge ${['High', 'Critical'].includes(complaint.priority) ? 'escalated' : 'progress'}">${escapeHtml(t(complaint.priority || '—'))}</span></td>
      <td><span class="badge ${escapeHtml(String(complaint.status || '').toLowerCase().replace(/\s+/g, '-'))}">${escapeHtml(t(complaint.status || '—'))}</span></td>
      <td>${escapeHtml(complaint.location || '—')}</td>
      <td>${escapeHtml(formatDate(complaint.created_at))}</td>
      <td><button class="view" type="button" data-department-view="${escapeHtml(complaint.id)}">${escapeHtml(t('View'))}</button></td>
    </tr>
  `).join('') || `<tr><td colspan="8">${escapeHtml(t('No complaints match these filters.'))}</td></tr>`;
  const count = document.getElementById('departmentQueueCount');
  if (count) count.textContent = t('{{count}} of {{total}} complaints', { count: filtered.length, total: departmentComplaintItems.length });
}

async function handleDepartmentView(event) {
  const button = event.target.closest('[data-department-view]');
  if (!button) return;
  try {
    const result = await apiRequest(`/api/department/complaints/${encodeURIComponent(button.dataset.departmentView)}`);
    const complaint = result.complaint;
    currentDepartmentComplaintId = complaint.id;
    document.querySelectorAll('[data-department-detail]').forEach(element => {
      const key = element.dataset.departmentDetail;
      element.textContent = key === 'description' || key === 'title'
        ? complaint[key] || ''
        : key === 'status' || key === 'priority' || key === 'category' || key === 'department'
          ? t(complaint[key] || '—')
          : complaint[key] || '—';
    });
    configureEvidenceLink(document.getElementById('departmentDetailModal'), complaint);
    const status = document.getElementById('departmentStatus');
    if (![...status.options].some(option => option.value === complaint.status)) {
      status.add(new Option(t(complaint.status), complaint.status));
    }
    status.value = complaint.status === 'Pending' || complaint.status === 'Escalated' ? 'In Progress' : complaint.status;
    const isRejected = complaint.status === 'Rejected';
    status.disabled = complaint.status === 'Resolved' || isRejected;
    document.getElementById('departmentResolution').value = complaint.resolution || '';
    document.getElementById('departmentResolution').disabled = isRejected;
    document.querySelector('#departmentUpdateForm button[type="submit"]').disabled = isRejected;
    document.getElementById('departmentUpdateMessage').textContent = '';
    const history = document.querySelector('[data-department-history]');
    history.innerHTML = (complaint.history || []).map(item => `
      <p><strong>${escapeHtml(t(item.action))}</strong> · ${escapeHtml(formatDate(item.created_at))}<br>${escapeHtml(item.details || '')}</p>
    `).join('') || `<p>${escapeHtml(t('No updates yet.'))}</p>`;
    document.getElementById('departmentDetailModal').classList.add('show');
  } catch (error) {
    alert(t(error.message));
  }
}

async function saveDepartmentUpdate(event) {
  event.preventDefault();
  if (!currentDepartmentComplaintId) return;
  const message = document.getElementById('departmentUpdateMessage');
  try {
    const result = await apiRequest(`/api/department/complaints/${encodeURIComponent(currentDepartmentComplaintId)}`, {
      method: 'PATCH',
      body: JSON.stringify({
        status: document.getElementById('departmentStatus').value,
        resolution: document.getElementById('departmentResolution').value.trim()
      })
    });
    const index = departmentComplaintItems.findIndex(item => item.id === result.complaint.id);
    if (index >= 0) departmentComplaintItems[index] = result.complaint;
    message.textContent = t('Complaint updated successfully.');
    renderDepartmentComplaints();
    try {
      const dashboard = await apiRequest('/api/department/dashboard');
      renderDepartmentStats(dashboard.stats);
    } catch (refreshError) {
      message.textContent = t('Complaint updated successfully.') + ` ${t(refreshError.message)}`;
    }
  } catch (error) {
    message.textContent = t(error.message);
  }
}
