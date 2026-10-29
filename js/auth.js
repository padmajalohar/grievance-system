document.addEventListener('DOMContentLoaded', () => {
  const register = document.getElementById('registerForm');
  const login = document.getElementById('loginForm');
  const loginRole = document.getElementById('loginRole');
  const citizenSignupPrompt = document.getElementById('citizenSignupPrompt');
  const departmentAccountNotice = document.getElementById('departmentAccountNotice');

  const updateSignupPrompt = () => {
    const departmentSelected = loginRole?.value === 'department_staff';
    if (citizenSignupPrompt) citizenSignupPrompt.hidden = departmentSelected;
    if (departmentAccountNotice) departmentAccountNotice.hidden = !departmentSelected;
  };
  loginRole?.addEventListener('change', updateSignupPrompt);
  updateSignupPrompt();

  const error = (id, message) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = t(message);
    el.hidden = false;
  };

  register?.addEventListener('submit', async (event) => {
    event.preventDefault();

    const payload = {
      name: document.getElementById('registerName').value.trim(),
      email: document.getElementById('registerEmail').value.trim().toLowerCase(),
      password: document.getElementById('registerPassword').value,
      role: 'citizen',
    };

    try {
      const data = await apiRequest('/api/register', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      localStorage.setItem('resolve_user', JSON.stringify(data.user));
      localStorage.setItem('resolve_token', data.token);
      location.href = 'my-grievances.html';
    } catch (err) {
      error('registerError', err.message);
    }
  });

  login?.addEventListener('submit', async (event) => {
    event.preventDefault();

    const email = document.getElementById('loginEmail').value.trim().toLowerCase();
    const password = document.getElementById('loginPassword').value;
    const role = loginRole?.value || 'citizen';

    try {
      const data = await apiRequest('/api/login', {
        method: 'POST',
        body: JSON.stringify({ email, password, role }),
      });
      localStorage.setItem('resolve_user', JSON.stringify(data.user));
      localStorage.setItem('resolve_token', data.token);
      location.href = data.user.role === 'admin'
        ? 'admin.html'
        : data.user.role === 'department_staff'
          ? 'department.html'
          : 'my-grievances.html';
    } catch (err) {
      error('loginError', err.message);
    }
  });
});
