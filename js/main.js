document.addEventListener('DOMContentLoaded', async () => {
  const user = JSON.parse(localStorage.getItem('resolve_user') || 'null');
  const token = localStorage.getItem('resolve_token');
  const page = document.body.dataset.page;

  if (page === 'dashboard') {
    location.replace('my-grievances.html');
    return;
  }

  if (['submit', 'grievances', 'admin', 'department'].includes(page)) {
    if (!user || !token) {
      location.href = 'login.html';
      return;
    }
    if (page === 'admin' && user.role !== 'admin') {
      location.href = user.role === 'department_staff' ? 'department.html' : 'my-grievances.html';
      return;
    }
    if (page === 'department' && user.role !== 'department_staff') {
      location.href = user.role === 'admin' ? 'admin.html' : 'my-grievances.html';
      return;
    }
    if (['submit', 'grievances'].includes(page) && user.role !== 'citizen') {
      location.href = user.role === 'admin' ? 'admin.html' : 'department.html';
      return;
    }
  }

  document.querySelectorAll('[data-user-name]').forEach((element) => {
    element.textContent = user?.name || 'Citizen';
  });

  document.querySelectorAll('[data-user-initial]').forEach((element) => {
    element.textContent = (user?.name || 'D')[0].toUpperCase();
  });

  document.querySelectorAll('[data-logout]').forEach((button) => {
    button.addEventListener('click', async () => {
      try {
        await window.apiRequest('/api/logout', { method: 'POST' });
      } catch (error) {
        alert(t(error.message));
      }
      localStorage.removeItem('resolve_token');
      localStorage.removeItem('resolve_user');
      location.href = 'index.html';
    });
  });

  document.addEventListener('click', async (event) => {
    const link = event.target.closest('[data-evidence-download]');
    if (!link) return;
    event.preventDefault();

    try {
      const response = await fetch(window.resolveApiUrl(`/api/complaints/${encodeURIComponent(link.dataset.complaintId)}/evidence`), {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.error || 'Unable to download evidence.');
      }
      const objectUrl = URL.createObjectURL(await response.blob());
      const download = document.createElement('a');
      download.href = objectUrl;
      download.download = link.dataset.filename || 'evidence';
      document.body.appendChild(download);
      download.click();
      download.remove();
      setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
    } catch (error) {
      alert(t(error.message));
    }
  });

  document.querySelector('[data-close]')?.addEventListener('click', () => {
    const modal = document.getElementById('detailModal');
    if (modal) modal.classList.remove('show');
  });

  document.getElementById('detailModal')?.addEventListener('click', (event) => {
    if (event.target.id === 'detailModal') event.target.classList.remove('show');
  });

  if (page === 'admin') {
    const adminName = user?.name || 'Administrator';
    document.querySelectorAll('[data-user-name]').forEach((element) => {
      element.textContent = adminName;
    });
  }

  if (page === 'admin' || page === 'grievances') {
    const rewardsScript = document.createElement('script');
    rewardsScript.src = 'js/rewards.js?v=2';
    rewardsScript.onload = () => {
      if (page === 'admin') window.initAdminCivicRewards?.();
      if (page === 'grievances') window.initCivicRewardsCitizen?.();
    };
    document.body.appendChild(rewardsScript);
  }
});

function configureEvidenceLink(modal, complaint) {
  const link = modal.querySelector('[data-evidence-download]');
  if (!link) return;
  link.hidden = !complaint.evidence;
  link.dataset.complaintId = complaint.id;
  link.dataset.filename = String(complaint.evidence || '').split(/[\\/]/).pop().replace(/^[a-f0-9]{32}_/i, '');
}

window.resolveApiUrl = function resolveApiUrl(path) {
  const apiBase = window.location.origin && window.location.origin !== 'null'
    ? window.location.origin
    : 'http://localhost:5001';
  return new URL(path, apiBase);
};

window.apiRequest = async function apiRequest(path, options = {}) {
  const token = localStorage.getItem('resolve_token');
  const headers = { ...(options.headers || {}) };

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(window.resolveApiUrl(path), {
    ...options,
    headers,
  });

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : await response.text();

  if (!response.ok) {
    const error = new Error(typeof payload === 'object' ? (payload.error || 'Request failed.') : payload || 'Request failed.');
    error.payload = payload;
    error.status = response.status;
    throw error;
  }

  return payload;
};

function formatDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  const locale = window.ResolveAIi18n?.localeTags?.[localStorage.getItem('resolve_language')] || 'en-IN';
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(locale, { day: '2-digit', month: 'short', year: 'numeric' });
}

function isBreached(item) {
  if (!item || !item.deadline || item.status === 'Resolved' || item.status === 'Rejected') return false;
  return new Date(item.deadline).getTime() < Date.now();
}

function safe(value) {
  const div = document.createElement('div');
  div.textContent = value || '';
  return div.innerHTML;
}

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function getGrievances() {
  return JSON.parse(localStorage.getItem('resolve_grievances') || '[]');
}

function saveGrievances(value) {
  localStorage.setItem('resolve_grievances', JSON.stringify(value));
}
