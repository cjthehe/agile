async function login() {
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  const messageBox = document.getElementById('message');

  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    const data = await response.json();

    if (!response.ok) {
      messageBox.textContent = data.message || 'Login failed';
      return;
    }

    localStorage.setItem('session_id', data.session_id);
    window.location.href = '/home';
  } catch (error) {
    messageBox.textContent = 'Login failed';
  }
}

async function registerUser() {
  const name = document.getElementById('registerName').value;
  const email = document.getElementById('registerEmail').value;
  const password = document.getElementById('registerPassword').value;
  const confirmPassword = document.getElementById('registerConfirmPassword').value;
  const messageBox = document.getElementById('registerMessage');

  try {
    const response = await fetch('/api/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password, confirmPassword })
    });

    const data = await response.json();

    if (!response.ok) {
      messageBox.textContent = data.message || 'Registration failed';
      messageBox.className = 'text-danger mt-3 text-center';
      return;
    }

    messageBox.textContent = `Registration successful. Welcome, ${data.user.name}!`;
    messageBox.className = 'text-success mt-3 text-center';
    document.getElementById('registerForm').reset();
  } catch (error) {
    messageBox.textContent = 'Registration failed';
    messageBox.className = 'text-danger mt-3 text-center';
  }
}

function updateAuthButtons() {
  const sessionId = localStorage.getItem('session_id');
  const loginLink = document.getElementById('loginLink');
  const logoutButton = document.getElementById('logoutButton');

  if (!loginLink || !logoutButton) {
    return;
  }

  if (sessionId) {
    loginLink.classList.add('d-none');
    logoutButton.classList.remove('d-none');
  } else {
    loginLink.classList.remove('d-none');
    logoutButton.classList.add('d-none');
  }
}

async function login() {
  const email = document.getElementById('email').value;
  const password = document.getElementById('password').value;
  const messageBox = document.getElementById('message');

  try {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });

    const data = await response.json();

    if (!response.ok) {
      messageBox.textContent = data.message || 'Login failed';
      return;
    }

    localStorage.setItem('session_id', data.session_id);
    window.location.href = '/home';
  } catch (error) {
    messageBox.textContent = 'Login failed';
  }
}

window.addEventListener('DOMContentLoaded', () => {
  updateAuthButtons();
  const logoutButton = document.getElementById('logoutButton');

  if (logoutButton) {
    logoutButton.addEventListener('click', async () => {
      const sessionId = localStorage.getItem('session_id');

      if (!sessionId) {
        window.location.href = '/login';
        return;
      }

      try {
        await fetch('/api/logout', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId })
        });
      } finally {
        localStorage.removeItem('session_id');
        updateAuthButtons();
        window.location.href = '/login';
      }
    });
  }
});
