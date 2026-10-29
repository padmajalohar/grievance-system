document.addEventListener('DOMContentLoaded', async () => {
  document.addEventListener('resolveai:languagechange', () => {
    if (document.body.dataset.page === 'grievances') {
      loadGrievanceList();
      const modal = document.getElementById('detailModal');
      if (modal?.classList.contains('show') && activeGrievanceDetail) {
        renderGrievanceDetails(modal, activeGrievanceDetail);
      }
    }
    if (document.body.dataset.page === 'submit') {
      updateClassificationLabels(lastUnsupportedLanguageClassification);
    }
  });

  if (document.body.dataset.page === 'dashboard') {
    await loadDashboard();
  }
  if (document.body.dataset.page === 'grievances') {
    await loadGrievanceList();
  }
  if (document.body.dataset.page === 'submit') {
    initSubmitForm();
  }
});

let activeGrievanceDetail = null;
let lastUnsupportedLanguageClassification = false;

async function loadDashboard() {
  try {
    const response = await apiRequest('/api/citizen/complaints');
    const items = response.complaints || [];
    const count = { total: items.length, pending: 0, progress: 0, resolved: 0, escalated: 0 };

    items.forEach((item) => {
      if (item.status === 'Pending') count.pending += 1;
      else if (item.status === 'In Progress') count.progress += 1;
      else if (item.status === 'Resolved') count.resolved += 1;
      else if (item.status === 'Escalated') count.escalated += 1;
    });

    Object.entries(count).forEach(([key, value]) => {
      const element = document.querySelector(`[data-stat="${key}"]`);
      if (element) element.textContent = value;
    });

    const recentActivity = document.getElementById('recentActivity');
    if (!recentActivity) return;
    recentActivity.innerHTML = items.slice().reverse().slice(0, 3).map((item) => `
      <div class="activity">
        <span class="icon">${item.status === 'Resolved' ? '✓' : '↗'}</span>
        <div>
          <strong>${escapeHtml(item.title)}</strong>
          <small>${escapeHtml(item.id)} · ${escapeHtml(item.status)} · ${formatDate(item.created_at)}</small>
        </div>
      </div>
    `).join('') || `<p class="muted">${escapeHtml(t('No complaints yet.'))}</p>`;

    const latest = items.find((item) => item.status !== 'Resolved') || items[0];
    if (latest) {
      document.getElementById('deadlineTitle').textContent = latest.title;
      document.getElementById('deadlineId').textContent = latest.id;
      document.getElementById('deadlineDate').textContent = formatDate(latest.deadline);
    }
  } catch (error) {
    alert(t(error.message));
  }
}

async function loadGrievanceList() {
  try {
    const response = await apiRequest('/api/citizen/complaints');
    const items = response.complaints || [];
    const grievanceRows = document.getElementById('grievanceRows');

    grievanceRows.innerHTML = items.slice().reverse().map((item) => {
      const status = isBreached(item) ? 'Escalated' : item.status;
      return `
        <tr>
          <td>${escapeHtml(item.id)}</td>
          <td><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.location)}</span></td>
          <td>${escapeHtml(t(item.category || '—'))}</td>
          <td><span class="badge ${item.priority === 'High' || item.priority === 'Critical' ? 'escalated' : 'progress'}">${escapeHtml(t(item.priority || '—'))}</span></td>
          <td><span class="badge ${status.toLowerCase().replace(/\s+/g, '-')}">${escapeHtml(t(status))}</span></td>
          <td>${escapeHtml(t(item.department || '—'))}</td>
          <td>${formatDate(item.deadline)}</td>
          <td><button class="view" data-index="${item.id}">${escapeHtml(t('View'))}</button></td>
        </tr>
      `;
    }).join('') || `<tr><td colspan="8">${escapeHtml(t('No complaints found.'))}</td></tr>`;

    grievanceRows.querySelectorAll('[data-index]').forEach((button) => {
      button.addEventListener('click', async () => {
        const complaintId = button.getAttribute('data-index');
        const data = await apiRequest(`/api/complaints/${complaintId}`);
        const item = data.complaint;
        const modal = document.getElementById('detailModal');
        if (!modal) return;
        activeGrievanceDetail = item;
        renderGrievanceDetails(modal, item);
        window.configureCivicUpdateForm?.(modal, item);
        modal.classList.add('show');
      });
    });
  } catch (error) {
    alert(t(error.message));
  }
}

function renderGrievanceDetails(modal, item) {
  modal.querySelector('[data-detail="title"]').textContent = item.title;
  modal.querySelector('[data-detail="description"]').textContent = `${item.description}\n\n${t('AI category:')} ${t(item.prediction?.predicted_category || item.category)}\n${t('Priority:')} ${t(item.prediction?.predicted_priority || item.priority)}\n${t('Department:')} ${t(item.department)}`;
  modal.querySelector('[data-detail="id"]').textContent = item.id;
  modal.querySelector('[data-detail="status"]').textContent = t(isBreached(item) ? 'Escalated' : item.status);
  modal.querySelector('[data-detail="department"]').textContent = t(item.department || '—');
  modal.querySelector('[data-detail="deadline"]').textContent = formatDate(item.deadline);
  configureEvidenceLink(modal, item);
  const historyContainer = modal.querySelector('[data-detail-history]');
  if (historyContainer) {
    historyContainer.innerHTML = (item.history || []).map((entry) => `
      <article class="history-entry">
        <div><strong>${escapeHtml(t(entry.action))}</strong><time>${escapeHtml(formatDate(entry.created_at))}</time></div>
        <p>${escapeHtml(entry.details)}</p>
      </article>
    `).join('') || `<p class="muted">${escapeHtml(t('No updates yet.'))}</p>`;
  }
}

function initSubmitForm() {
  const form = document.getElementById('grievanceForm');
  const evidence = document.getElementById('evidence');
  if (!form || !evidence) return;

  evidence.addEventListener('change', () => {
    const fileName = evidence.files[0]?.name || t('Optional evidence: image or document');
    document.getElementById('fileName').textContent = fileName;
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const payload = {
      title: document.getElementById('title').value.trim(),
      description: document.getElementById('description').value.trim(),
      category: document.getElementById('category').value,
      location: document.getElementById('location').value.trim(),
    };

    if (!payload.title || !payload.description || !payload.location) {
      alert(t('Please fill in the title, description, and location.'));
      return;
    }

    try {
      const submissionError = document.getElementById('submissionError');
      if (submissionError) submissionError.hidden = true;
      const formData = new FormData();
      Object.entries(payload).forEach(([key, value]) => formData.append(key, value));
      if (evidence.files[0]) formData.append('evidence', evidence.files[0]);
      const result = await apiRequest('/api/complaints', {
        method: 'POST',
        body: formData,
      });

      document.getElementById('confirmation').classList.remove('hidden');
      document.getElementById('analysisResult').classList.remove('hidden');
      document.getElementById('generatedId').textContent = result.complaint.id;
      lastUnsupportedLanguageClassification = result.prediction.model_version === 'unsupported_language_fallback';
      updateClassificationLabels(lastUnsupportedLanguageClassification);
      document.getElementById('predictedCategory').textContent = t(result.prediction.predicted_category);
      document.getElementById('predictedPriority').textContent = t(result.prediction.predicted_priority);
      document.getElementById('confidence').textContent = `${result.prediction.confidence}%`;
      document.getElementById('predictedDepartment').textContent = t(result.prediction.recommended_department);
      form.reset();
      document.getElementById('fileName').textContent = t('Optional evidence: image or document');
    } catch (error) {
      const submissionError = document.getElementById('submissionError');
      if (submissionError) {
        submissionError.textContent = t(error.message);
        submissionError.hidden = false;
      } else {
        alert(t(error.message));
      }
    }
  });
}

function updateClassificationLabels(unsupported) {
  const categoryLabel = document.getElementById('categoryResultLabel');
  const priorityLabel = document.getElementById('priorityResultLabel');
  const notice = document.getElementById('classificationNotice');
  if (categoryLabel) categoryLabel.textContent = t(unsupported ? 'Category awaiting human review' : 'Predicted category');
  if (priorityLabel) priorityLabel.textContent = t(unsupported ? 'Priority pending human assessment' : 'Predicted priority');
  if (notice) {
    notice.textContent = t('This language is not supported by the complaint classifier. No category or priority prediction was made; this complaint is queued for human review.');
    notice.hidden = !unsupported;
  }
}
