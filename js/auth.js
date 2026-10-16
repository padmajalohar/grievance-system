document.addEventListener('DOMContentLoaded', () => {
  const register = document.getElementById('registerForm');
  const login = document.getElementById('loginForm');

  const error = (id, message) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
  };

  register?.addEventListener('submit', async (event) => {
    event.preventDefault();

    const payload = {
      name: document.getElementById('registerName').value.trim(),
      email: document.getElementById('registerEmail').value.trim().toLowerCase(),
      password: document.getElementById('registerPassword').value,
    };

    try {
      const response = await fetch('http://localhost:5001/api/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Unable to register.');
      }
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
    const role = document.getElementById('loginRole')?.value || 'citizen';

    try {
      const response = await fetch('http://localhost:5001/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, role }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || 'Unable to sign in.');
      }
      localStorage.setItem('resolve_user', JSON.stringify(data.user));
      localStorage.setItem('resolve_token', data.token);
      location.href = role === 'admin' ? 'admin.html' : 'my-grievances.html';
    } catch (err) {
      error('loginError', err.message);
    }
  });
});

