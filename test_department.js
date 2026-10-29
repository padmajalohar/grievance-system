const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function element(value = '') {
  return { value, innerHTML: '', textContent: '', options: [], addEventListener() {} };
}

const elements = {
  departmentSearch: element(),
  departmentStatusFilter: element(),
  departmentPriorityFilter: element(),
  departmentComplaintRows: element(),
  departmentQueueCount: element()
};
const document = {
  addEventListener() {},
  getElementById(id) { return elements[id] || null; }
};
const context = vm.createContext({
  document,
  t: (value, values = {}) => String(value).replace(/\{\{(\w+)\}\}/g, (_match, key) => values[key] ?? `{{${key}}}`),
  escapeHtml: value => String(value || ''),
  formatDate: value => value || '—',
  console
});
const source = fs.readFileSync('js/department.js', 'utf8');
vm.runInContext(source, context);

vm.runInContext(`
  departmentComplaintItems = [
    { id: 'GRV-W1', title: 'Water outage', location: 'North Block', priority: 'High', status: 'Pending', created_at: '2026-01-01' },
    { id: 'GRV-S1', title: 'Waste pickup', location: 'South Block', priority: 'Low', status: 'Resolved', created_at: '2026-01-02' },
    { id: 'GRV-W2', title: 'Water pressure', location: 'West Block', priority: 'Medium', status: 'In Progress', created_at: '2026-01-03' }
  ];
  renderDepartmentComplaints();
`, context);
assert.match(elements.departmentComplaintRows.innerHTML, /GRV-W1/);
assert.match(elements.departmentComplaintRows.innerHTML, /GRV-S1/);
assert.match(elements.departmentComplaintRows.innerHTML, /GRV-W2/);

elements.departmentSearch.value = 'water';
vm.runInContext('renderDepartmentComplaints()', context);
assert.match(elements.departmentComplaintRows.innerHTML, /GRV-W1/);
assert.match(elements.departmentComplaintRows.innerHTML, /GRV-W2/);
assert.doesNotMatch(elements.departmentComplaintRows.innerHTML, /GRV-S1/);

elements.departmentSearch.value = '';
elements.departmentStatusFilter.value = 'Resolved';
vm.runInContext('renderDepartmentComplaints()', context);
assert.match(elements.departmentComplaintRows.innerHTML, /GRV-S1/);
assert.doesNotMatch(elements.departmentComplaintRows.innerHTML, /GRV-W1/);

elements.departmentStatusFilter.value = '';
elements.departmentPriorityFilter.value = 'High';
vm.runInContext('renderDepartmentComplaints()', context);
assert.match(elements.departmentComplaintRows.innerHTML, /GRV-W1/);
assert.doesNotMatch(elements.departmentComplaintRows.innerHTML, /GRV-W2/);

elements.departmentSearch.value = 'water';
elements.departmentStatusFilter.value = 'In Progress';
elements.departmentPriorityFilter.value = 'Medium';
vm.runInContext('renderDepartmentComplaints()', context);
assert.match(elements.departmentComplaintRows.innerHTML, /GRV-W2/);
assert.doesNotMatch(elements.departmentComplaintRows.innerHTML, /GRV-W1/);

elements.departmentPriorityFilter.value = 'Critical';
vm.runInContext('renderDepartmentComplaints()', context);
assert.match(elements.departmentComplaintRows.innerHTML, /No complaints match these filters/);
assert.equal(elements.departmentQueueCount.textContent, '0 of 3 complaints');

const statsElement = element();
elements.departmentStats = statsElement;
vm.runInContext(`
  renderDepartmentStats({
    total: 3,
    priority_counts: { Critical: 0, High: 1, Medium: 1, Low: 1 },
    status_counts: { Pending: 1, 'In Progress': 1, Resolved: 1, Rejected: 0, Escalated: 0 },
    overdue: 0
  });
`, context);
for (const label of ['Total complaints', 'Critical priority', 'High priority', 'Medium priority', 'Low priority', 'Pending', 'In Progress', 'Resolved', 'Rejected', 'Escalated']) {
  assert.ok(statsElement.innerHTML.includes(label), `dashboard stats include ${label}`);
}

console.log('PASS: department search/status/priority filters, combined filtering, empty state, and summary metrics.');
