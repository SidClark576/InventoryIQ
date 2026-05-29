function requireAuth() {
  if (!sessionStorage.getItem('userEmail')) window.location.href = 'login.html';
}

function escHTML(s) {
  if (!s) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function initNav(activePageId) {
  const email = sessionStorage.getItem('userEmail') || '';
  const el = document.getElementById('nav-email');
  if (el) el.textContent = email;

  document.querySelectorAll('[data-page]').forEach(function (a) {
    const active = a.dataset.page === activePageId;
    a.classList.toggle('text-[#005ab4]', active);
    a.classList.toggle('bg-[#e8f0fe]', active);
    a.classList.toggle('border-[#005ab4]', active);
    a.classList.toggle('font-bold', active);
    a.classList.toggle('text-gray-500', !active);
    a.classList.toggle('border-transparent', !active);
    a.classList.toggle('font-medium', !active);
  });
}

async function handleLogout() {
  const token = sessionStorage.getItem('sessionToken') || '';
  if (token) {
    try {
      await fetch(`${CONFIG.AUTH_ENDPOINT}/logout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-Token': token }
      });
    } catch (_) {
      // Network error on logout is non-fatal — always clear local session
    }
  }
  sessionStorage.clear();
  window.location.href = 'login.html';
}

function showPremiumToast(title, message, type = 'success') {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `premium-toast toast-${type}`;
  
  let iconName = 'check_circle';
  if (type === 'error') iconName = 'error';
  if (type === 'warning') iconName = 'warning';

  toast.innerHTML = `
    <span class="material-symbols-outlined toast-icon">${iconName}</span>
    <div class="toast-content">
      <div class="toast-title">${escHTML(title)}</div>
      <div class="toast-message">${escHTML(message)}</div>
    </div>
  `;

  container.appendChild(toast);

  // Trigger animation
  requestAnimationFrame(() => {
    toast.classList.add('show');
  });

  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => {
      toast.remove();
      if (container.childNodes.length === 0) container.remove();
    }, 400); // Wait for transition out
  }, 4000);
}
