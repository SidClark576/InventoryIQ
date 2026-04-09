function requireAuth() {
  if (!sessionStorage.getItem('userEmail')) window.location.href = 'login.html';
}

function initNav(activePageId) {
  const email = sessionStorage.getItem('userEmail') || '';
  const el = document.getElementById('nav-email');
  if (el) el.textContent = email;

  document.querySelectorAll('[data-page]').forEach(function(a) {
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

function handleLogout() {
  sessionStorage.clear();
  window.location.href = 'login.html';
}
