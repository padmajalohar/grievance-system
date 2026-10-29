const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function loginAs(role) {
  const listeners = {};
  const values = {
    loginEmail: { value: ' Staff@Example.Test ' },
    loginPassword: { value: 'an-existing-password' },
    loginRole: {
      value: role,
      addEventListener(name, callback) {
        listeners[`role:${name}`] = callback;
      }
    },
    loginError: { textContent: '', hidden: true }
  };
  values.citizenSignupPrompt = { hidden: false };
  values.departmentAccountNotice = { hidden: true };
  const form = {
    addEventListener(name, callback) {
      listeners[`login:${name}`] = callback;
    }
  };
  values.loginForm = form;
  const document = {
    addEventListener(name, callback) {
      listeners[`document:${name}`] = callback;
    },
    getElementById(id) { return values[id] || null; }
  };
  const store = new Map();
  const requests = [];
  const context = vm.createContext({
    document,
    localStorage: {
      getItem: key => store.get(key) || null,
      setItem: (key, value) => store.set(key, value)
    },
    location: { href: '' },
    URL,
    FormData,
    fetch: async url => {
      requests.push(String(url));
      return {
        ok: true,
        headers: { get: () => 'application/json' },
        json: async () => ({
          token: 'test-session-token',
          user: { id: 21, name: 'Existing Staff', role, department: 'Water Supply Department' }
        })
      };
    },
    t: value => value,
    console
  });
  context.window = context;
  context.window.location.origin = 'http://192.168.1.40:5001';
  vm.runInContext(fs.readFileSync('js/main.js', 'utf8'), context);
  vm.runInContext(fs.readFileSync('js/auth.js', 'utf8'), context);
  listeners['document:DOMContentLoaded']();
  assert.equal(values.citizenSignupPrompt.hidden, role === 'department_staff');
  assert.equal(values.departmentAccountNotice.hidden, role !== 'department_staff');
  if (role === 'citizen') {
    values.loginRole.value = 'department_staff';
    listeners['role:change']();
    assert.equal(values.citizenSignupPrompt.hidden, true);
    assert.equal(values.departmentAccountNotice.hidden, false);
    values.loginRole.value = 'citizen';
    listeners['role:change']();
    assert.equal(values.citizenSignupPrompt.hidden, false);
    assert.equal(values.departmentAccountNotice.hidden, true);
  }
  listeners['login:submit']({ preventDefault() {} });
  await new Promise(resolve => setImmediate(resolve));
  return { context, store, requests };
}

(async () => {
  const staff = await loginAs('department_staff');
  assert.equal(staff.context.location.href, 'department.html');
  assert.equal(JSON.parse(staff.store.get('resolve_user')).department, 'Water Supply Department');
  assert.equal(staff.store.get('resolve_token'), 'test-session-token');
  assert.deepEqual(staff.requests, ['http://192.168.1.40:5001/api/login']);

  const admin = await loginAs('admin');
  assert.equal(admin.context.location.href, 'admin.html');

  const citizen = await loginAs('citizen');
  assert.equal(citizen.context.location.href, 'my-grievances.html');

  console.log('PASS: role-based redirects, session storage, and same-origin login API for staff, admin, and citizen.');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
