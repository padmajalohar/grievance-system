const rewardEscape = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' })[character]);

function loadRewardsAssets() {
  if (!document.querySelector('link[data-rewards-style]')) {
    const stylesheet = document.createElement('link');
    stylesheet.rel = 'stylesheet';
    stylesheet.href = 'css/rewards.css?v=1';
    stylesheet.dataset.rewardsStyle = 'true';
    document.head.appendChild(stylesheet);
  }
}

async function initCivicRewardsCitizen() {
  loadRewardsAssets();
  const main = document.querySelector('main');
  if (!main || document.getElementById('civicRewardsPanel')) return;
  const panel = document.createElement('section');
  panel.id = 'civicRewardsPanel';
  panel.className = 'panel civic-rewards';
  panel.setAttribute('aria-labelledby', 'rewardsHeading');
  panel.innerHTML = `
    <div class="panel-head"><h2 id="rewardsHeading">Civic Impact Rewards</h2><span class="reward-muted">Non-monetary community recognition</span></div>
    <div class="reward-summary">
      <div class="reward-metric"><span>Available CivicPoints</span><strong id="rewardsPoints">0</strong></div>
      <div class="reward-metric"><span>Verified contributions</span><strong id="rewardsVerified">0</strong></div>
      <div class="reward-metric"><span>Verified resolutions</span><strong id="rewardsResolved">0</strong></div>
    </div>
    <div class="reward-lists">
      <section><h3 class="reward-section-title">Achievements</h3><div id="rewardsBadges" class="reward-card-list"></div><div id="rewardsProgress"></div></section>
      <section><h3 class="reward-section-title">Points history</h3><div id="rewardTransactions"></div></section>
    </div>
    <p id="rewardsExplanation" class="reward-muted"></p>
    <p><button class="view" type="button" id="rewardLeaderboardButton" hidden>Community leaderboard</button></p>
    <div id="rewardLeaderboard" hidden></div>
    <div id="citizenRewardsFeedback" class="reward-feedback" role="status"></div>`;
  const heading = main.querySelector('.heading');
  if (heading) heading.insertAdjacentElement('afterend', panel);
  else main.prepend(panel);

  const modal = document.getElementById('detailModal');
  if (modal && !document.getElementById('citizenUpdateForm')) {
    const form = document.createElement('form');
    form.id = 'citizenUpdateForm';
    form.hidden = true;
    form.innerHTML = '<h3 class="reward-section-title">Add useful new information</h3><label>Update<textarea name="details" minlength="20" maxlength="2000" required placeholder="Add new facts that may help resolve the issue."></textarea></label><button class="btn" type="submit">Submit update for review</button><p id="citizenUpdateMessage" class="reward-feedback" role="status"></p>';
    (modal.querySelector('.history') || modal.querySelector('.modal')).appendChild(form);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const complaintId = form.dataset.complaintId;
      const details = form.elements.details.value.trim();
      const message = document.getElementById('citizenUpdateMessage');
      try {
        await apiRequest(`/api/complaints/${encodeURIComponent(complaintId)}/updates`, { method: 'POST', body: JSON.stringify({ details }) });
        form.reset();
        message.textContent = 'Update sent to an administrator for verification. Points are awarded only if it is verified.';
      } catch (error) {
        message.textContent = error.message;
      }
    });
    const observer = new MutationObserver(() => {
      const id = modal.querySelector('[data-detail="id"]')?.textContent || '';
      const status = modal.querySelector('[data-detail="status"]')?.textContent || '';
      if (!id || id === '—') return;
      form.dataset.complaintId = id;
      form.hidden = ['Resolved', 'Rejected'].includes(status);
      document.getElementById('citizenUpdateMessage').textContent = '';
    });
    observer.observe(modal, { subtree: true, childList: true, characterData: true, attributes: true });
  }

  document.getElementById('rewardLeaderboardButton').addEventListener('click', async () => {
    const output = document.getElementById('rewardLeaderboard');
    try {
      const data = await apiRequest('/api/citizen/leaderboard');
      output.hidden = false;
      output.innerHTML = data.leaderboard.map((entry, index) => `<p class="reward-history-row"><span>${index + 1}. ${rewardEscape(entry.display_name)} · ${entry.verified_contributions} verified contributions</span><strong>${entry.verified_resolutions} verified resolutions</strong></p>`).join('') || '<p class="reward-muted">No verified contributions yet.</p>';
    } catch (error) {
      output.hidden = false;
      output.textContent = error.message;
    }
  });
  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-civic-certificate]');
    if (!button) return;
    try {
      const response = await fetch(`http://localhost:5001/api/citizen/rewards/certificates/${encodeURIComponent(button.dataset.civicCertificate)}`, { headers: { Authorization: `Bearer ${localStorage.getItem('resolve_token')}` } });
      if (!response.ok) throw new Error((await response.json()).error || 'Certificate unavailable.');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = `${button.dataset.civicCertificate}-civic-impact-certificate.html`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (error) {
      document.getElementById('citizenRewardsFeedback').textContent = error.message;
    }
  });
  await refreshCivicRewards();
}

async function refreshCivicRewards() {
  try {
    const data = await apiRequest('/api/citizen/rewards');
    document.getElementById('rewardsPoints').textContent = data.summary.available_points;
    document.getElementById('rewardsVerified').textContent = data.summary.verified_contributions;
    document.getElementById('rewardsResolved').textContent = data.summary.verified_resolutions;
    document.getElementById('rewardsExplanation').textContent = data.explanation;
    const badges = document.getElementById('rewardsBadges');
    badges.innerHTML = data.badges.map((badge) => `<article class="reward-badge"><strong>${rewardEscape(badge.name)}</strong><div class="reward-muted">${rewardEscape(badge.description)} Awarded ${rewardEscape(formatDate(badge.awarded_at))}.</div><button type="button" class="view" data-civic-certificate="${rewardEscape(badge.badge_key)}">Download milestone certificate</button></article>`).join('') || '<p class="reward-muted">No badges earned yet. Verified contributions unlock milestones.</p>';
    const progress = document.getElementById('rewardsProgress');
    progress.innerHTML = data.next_badge ? `<h4>${rewardEscape(data.next_badge.name)} · ${data.next_badge.progress} of ${data.next_badge.target}</h4><div class="reward-progress" role="progressbar" aria-valuemin="0" aria-valuemax="${data.next_badge.target}" aria-valuenow="${data.next_badge.progress}"><span style="width:${Math.min(100, data.next_badge.progress / data.next_badge.target * 100)}%"></span></div>` : '<p class="reward-muted">All configured contribution milestones achieved.</p>';
    const transactions = document.getElementById('rewardTransactions');
    transactions.innerHTML = data.transactions.map((transaction) => `<div class="reward-history-row"><span>${rewardEscape(transaction.reason)}<br><small>${rewardEscape(transaction.complaint_id || transaction.transaction_id)} · ${rewardEscape(formatDate(transaction.created_at))}</small></span><strong>${transaction.points > 0 ? '+' : ''}${transaction.points}</strong></div>`).join('') || '<p class="reward-muted">No reward transactions yet.</p>';
    document.getElementById('rewardLeaderboardButton').hidden = !data.leaderboard_enabled;
  } catch (error) {
    const feedback = document.getElementById('citizenRewardsFeedback');
    if (feedback) feedback.textContent = error.message;
  }
}

async function initAdminCivicRewards() {
  loadRewardsAssets();
  const main = document.querySelector('main');
  if (!main || document.getElementById('adminCivicRewards')) return;
  const panel = document.createElement('section');
  panel.id = 'adminCivicRewards';
  panel.className = 'panel civic-rewards';
  panel.innerHTML = `
    <div class="panel-head"><h2>Civic Impact Rewards Management</h2><span class="reward-muted">Verification is separate from complaint priority and routing.</span></div>
    <div id="adminRewardStats" class="reward-admin-grid"></div>
    <h3 class="reward-section-title">Contribution verification queue</h3><div id="adminRewardComplaints" class="reward-card-list"></div>
    <h3 class="reward-section-title">Citizen update verification</h3><div id="adminRewardUpdates" class="reward-card-list"></div>
    <h3 class="reward-section-title">Reward policy</h3><div id="adminRewardRules" class="reward-config-grid"></div><h4>Badge thresholds</h4><div id="adminRewardBadges" class="reward-config-grid"></div><label class="reward-check"><input id="adminLeaderboardEnabled" type="checkbox"> Enable pseudonymous community leaderboard</label><button id="saveRewardConfig" class="btn" type="button">Save reward policy</button>
    <h3 class="reward-section-title">Manual adjustment</h3><div class="reward-config-grid"><label>Citizen ID<input id="rewardAdjustmentCitizen" type="number" min="1"></label><label>Points (+/-)<input id="rewardAdjustmentPoints" type="number" min="-1000" max="1000"></label><label>Related complaint ID (optional)<input id="rewardAdjustmentComplaint"></label><label>Reason<input id="rewardAdjustmentReason" minlength="8" maxlength="500"></label></div><button id="submitRewardAdjustment" class="btn" type="button">Record adjustment</button>
    <h3 class="reward-section-title">Auditable reward transactions</h3><div id="adminRewardLedger" class="reward-card-list"></div><p id="adminRewardsFeedback" class="reward-feedback" role="status"></p>`;
  const queue = main.querySelector('#adminComplaintRows')?.closest('section');
  if (queue) queue.insertAdjacentElement('afterend', panel);
  else main.appendChild(panel);

  panel.addEventListener('click', async (event) => {
    const complaintButton = event.target.closest('[data-reward-complaint-decision]');
    const updateButton = event.target.closest('[data-reward-update-decision]');
    const reverseButton = event.target.closest('[data-reward-reverse]');
    const feedback = document.getElementById('adminRewardsFeedback');
    try {
      if (complaintButton) {
        const card = complaintButton.closest('[data-complaint-review]');
        await apiRequest(`/api/admin/rewards/complaints/${encodeURIComponent(card.dataset.complaintReview)}/decision`, { method: 'POST', body: JSON.stringify({ eligible: card.querySelector('[name="eligible"]').checked, evidence_approved: card.querySelector('[name="evidence_approved"]').checked, resolution_verified: card.querySelector('[name="resolution_verified"]').checked, social_impact_verified: card.querySelector('[name="social_impact_verified"]').checked, reason: card.querySelector('[name="reason"]').value.trim() }) });
        feedback.textContent = 'Contribution review saved. CivicPoints were recorded only for approved events.';
        await refreshAdminCivicRewards();
      } else if (updateButton) {
        const card = updateButton.closest('[data-update-review]');
        await apiRequest(`/api/admin/rewards/updates/${card.dataset.updateReview}/decision`, { method: 'POST', body: JSON.stringify({ verified: updateButton.dataset.verified === 'true', reason: card.querySelector('[name="update_reason"]').value.trim() }) });
        feedback.textContent = 'Citizen update review saved.';
        await refreshAdminCivicRewards();
      } else if (reverseButton) {
        const reason = window.prompt('Reason for reversing this transaction (at least 8 characters):');
        if (!reason) return;
        await apiRequest(`/api/admin/rewards/transactions/${encodeURIComponent(reverseButton.dataset.rewardReverse)}/reverse`, { method: 'POST', body: JSON.stringify({ reason }) });
        feedback.textContent = 'Reversal recorded as a new transaction.';
        await refreshAdminCivicRewards();
      }
    } catch (error) {
      feedback.textContent = error.message;
    }
  });
  document.getElementById('saveRewardConfig').addEventListener('click', async () => {
    const feedback = document.getElementById('adminRewardsFeedback');
    try {
      const rules = {};
      document.querySelectorAll('[data-reward-rule]').forEach((field) => {
        const key = field.dataset.rewardRule;
        rules[key] = { points: Number(field.value), enabled: document.querySelector(`[data-reward-rule-enabled="${key}"]`).checked };
      });
      const badges = {};
      document.querySelectorAll('[data-badge-threshold]').forEach((field) => { badges[field.dataset.badgeThreshold] = Number(field.value); });
      await apiRequest('/api/admin/rewards/config', { method: 'PATCH', body: JSON.stringify({ rules, badges, leaderboard_enabled: document.getElementById('adminLeaderboardEnabled').checked }) });
      feedback.textContent = 'Reward policy saved.';
      await refreshAdminCivicRewards();
    } catch (error) {
      feedback.textContent = error.message;
    }
  });
  document.getElementById('submitRewardAdjustment').addEventListener('click', async () => {
    const feedback = document.getElementById('adminRewardsFeedback');
    try {
      const adjustmentButton = document.getElementById('submitRewardAdjustment');
      adjustmentButton.dataset.idempotencyKey ||= crypto.randomUUID();
      await apiRequest('/api/admin/rewards/adjustments', { method: 'POST', body: JSON.stringify({ citizen_id: Number(document.getElementById('rewardAdjustmentCitizen').value), points: Number(document.getElementById('rewardAdjustmentPoints').value), complaint_id: document.getElementById('rewardAdjustmentComplaint').value.trim(), reason: document.getElementById('rewardAdjustmentReason').value.trim(), idempotency_key: adjustmentButton.dataset.idempotencyKey }) });
      delete adjustmentButton.dataset.idempotencyKey;
      feedback.textContent = 'Manual adjustment recorded in the reward ledger.';
      await refreshAdminCivicRewards();
    } catch (error) {
      feedback.textContent = error.message;
    }
  });
  await refreshAdminCivicRewards();
}

async function refreshAdminCivicRewards() {
  const feedback = document.getElementById('adminRewardsFeedback');
  try {
    const [statsData, pending, config, ledgerData] = await Promise.all([
      apiRequest('/api/admin/rewards/stats'),
      apiRequest('/api/admin/rewards/pending'),
      apiRequest('/api/admin/rewards/config'),
      apiRequest('/api/admin/rewards/transactions'),
    ]);
    const stats = statsData.stats;
    document.getElementById('adminRewardStats').innerHTML = Object.entries({ 'Net CivicPoints': stats.net_points_awarded, 'Verified contributions': stats.verified_contributions, 'Verified resolutions': stats.verified_resolutions, 'Awaiting review': stats.pending_complaints + stats.pending_updates, 'Citizens earning points': stats.citizens_with_points, 'Badges awarded': stats.badges_awarded }).map(([label, value]) => `<div class="reward-metric"><span>${rewardEscape(label)}</span><strong>${value}</strong></div>`).join('');
    document.getElementById('adminRewardComplaints').innerHTML = pending.complaints.map((item) => `<article class="reward-review-card" data-complaint-review="${rewardEscape(item.complaint_id)}"><header><div><strong>${rewardEscape(item.complaint_id)} · ${rewardEscape(item.title)}</strong><div class="reward-muted">${rewardEscape(item.citizen_name)} · Citizen ID ${item.user_id} · ${rewardEscape(item.location)} · ${rewardEscape(item.status)} · ${rewardEscape(item.priority)}</div></div>${item.evidence ? `<a href="#" class="link" data-evidence-download data-complaint-id="${rewardEscape(item.complaint_id)}" data-filename="${rewardEscape(String(item.evidence).split(/[\\/]/).pop().replace(/^[a-f0-9]{32}_/i, ''))}">Review evidence</a>` : '<span class="reward-muted">No evidence attached</span>'}</header>${item.potential_related_reports?.length ? `<p class="reward-muted">Potentially related reports: ${item.potential_related_reports.map(rewardEscape).join(', ')}. Independent reports remain separate; this signal is for administrator review only.</p>` : ''}<p>${rewardEscape(item.description)}</p>${item.resolution ? `<p><strong>Resolution:</strong> ${rewardEscape(item.resolution)}</p>` : ''}<div class="reward-checks"><label><input type="checkbox" name="eligible"> Verify contribution (+ configured points)</label><label><input type="checkbox" name="evidence_approved" ${item.evidence ? '' : 'disabled'}> Approve useful evidence</label><label><input type="checkbox" name="resolution_verified" ${item.status === 'Resolved' && item.resolution ? '' : 'disabled'}> Verify documented resolution</label><label><input type="checkbox" name="social_impact_verified"> Award Social Impact badge</label></div><label>Decision reason<textarea name="reason" minlength="8" required placeholder="Record why this contribution qualifies or does not qualify."></textarea></label><button type="button" class="btn" data-reward-complaint-decision>Save verification</button></article>`).join('') || '<p class="reward-muted">No new complaints are awaiting reward verification.</p>';
    document.getElementById('adminRewardUpdates').innerHTML = pending.updates.map((item) => `<article class="reward-review-card" data-update-review="${item.id}"><header><strong>${rewardEscape(item.complaint_id)} · ${rewardEscape(item.title)}</strong><span class="reward-muted">${rewardEscape(item.citizen_name)} · ${rewardEscape(formatDate(item.created_at))}</span></header><p>${rewardEscape(item.details)}</p><label>Review reason<textarea name="update_reason" minlength="8" required placeholder="Explain whether this update adds useful new information."></textarea></label><footer><button type="button" class="btn" data-reward-update-decision data-verified="true">Verify update (+ configured points)</button><button type="button" class="view" data-reward-update-decision data-verified="false">Reject update</button></footer></article>`).join('') || '<p class="reward-muted">No citizen updates are awaiting review.</p>';
    document.getElementById('adminRewardRules').innerHTML = config.rules.map((rule) => `<label>${rewardEscape(rule.rule_key.replaceAll('_', ' '))} points<input type="number" min="0" max="1000" value="${rule.points}" data-reward-rule="${rewardEscape(rule.rule_key)}"><span class="reward-check"><input type="checkbox" data-reward-rule-enabled="${rewardEscape(rule.rule_key)}" ${rule.enabled ? 'checked' : ''}> Enabled</span></label>`).join('');
    document.getElementById('adminRewardBadges').innerHTML = config.badges.filter((badge) => badge.badge_key !== 'social_impact').map((badge) => `<label>${rewardEscape(badge.name)} threshold<input type="number" min="1" max="10000" value="${badge.contribution_threshold}" data-badge-threshold="${rewardEscape(badge.badge_key)}"></label>`).join('');
    document.getElementById('adminLeaderboardEnabled').checked = config.leaderboard_enabled;
    document.getElementById('adminRewardLedger').innerHTML = ledgerData.transactions.map((transaction) => `<article class="reward-ledger-row"><header><strong>${rewardEscape(transaction.citizen_name)} · #${transaction.citizen_id} · ${transaction.points > 0 ? '+' : ''}${transaction.points} CivicPoints</strong><span class="reward-muted">${rewardEscape(transaction.event_type)} · ${rewardEscape(formatDate(transaction.created_at))}</span></header><p>${rewardEscape(transaction.reason)}</p><small>${rewardEscape(transaction.complaint_id || transaction.transaction_id)}${transaction.reversal_of ? ` · reverses transaction record ${transaction.reversal_of}` : ''}</small>${transaction.points > 0 && !transaction.reversal_of ? `<button type="button" class="view" data-reward-reverse="${rewardEscape(transaction.transaction_id)}">Reverse with reason</button>` : ''}</article>`).join('') || '<p class="reward-muted">No CivicPoints transactions recorded.</p>';
  } catch (error) {
    feedback.textContent = error.message;
  }
}

window.configureCivicUpdateForm = function configureCivicUpdateForm(modal, item) {
  const form = document.getElementById('citizenUpdateForm');
  if (!form) return;
  form.dataset.complaintId = item.id;
  form.hidden = ['Resolved', 'Rejected'].includes(item.status);
  document.getElementById('citizenUpdateMessage').textContent = '';
};

window.initCivicRewardsCitizen = initCivicRewardsCitizen;
window.initAdminCivicRewards = initAdminCivicRewards;
