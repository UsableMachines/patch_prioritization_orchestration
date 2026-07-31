/* ── Theme Toggle ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  // Theme
  const html = document.documentElement;
  const themeToggle = document.getElementById('themeToggle');
  const themeIcon = document.getElementById('themeIcon');
  const saved = localStorage.getItem('theme') || 'light';
  html.setAttribute('data-theme', saved);
  updateThemeIcon(saved);

  if (themeToggle) {
    themeToggle.addEventListener('click', function () {
      const current = html.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      html.setAttribute('data-theme', next);
      localStorage.setItem('theme', next);
      updateThemeIcon(next);
    });
  }

  function updateThemeIcon(theme) {
    if (!themeIcon) return;
    themeIcon.className = theme === 'dark' ? 'fas fa-sun' : 'fas fa-moon';
  }

  // Sidebar toggle (desktop)
  const sidebar = document.getElementById('sidebar');
  const sidebarToggle = document.getElementById('sidebarToggle');
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', function () {
      sidebar.classList.toggle('collapsed');
      localStorage.setItem('sidebar', sidebar.classList.contains('collapsed') ? 'collapsed' : 'expanded');
    });
    if (localStorage.getItem('sidebar') === 'collapsed') {
      sidebar.classList.add('collapsed');
    }
  }

  // Sidebar toggle (mobile)
  const sidebarMobile = document.getElementById('sidebarToggleMobile');
  if (sidebarMobile && sidebar) {
    sidebarMobile.addEventListener('click', function () {
      sidebar.classList.toggle('mobile-open');
    });
    // Close sidebar on nav click (mobile)
    sidebar.querySelectorAll('.nav-item').forEach(function (item) {
      item.addEventListener('click', function () {
        sidebar.classList.remove('mobile-open');
      });
    });
  }

  // Help panel
  const helpToggle = document.getElementById('helpToggle');
  const helpPanel = document.getElementById('helpPanel');
  const helpClose = document.getElementById('helpClose');
  const helpOverlay = document.getElementById('helpOverlay');

  function openHelp() {
    if (helpPanel) helpPanel.classList.add('open');
    if (helpOverlay) helpOverlay.classList.add('open');
  }
  function closeHelp() {
    if (helpPanel) helpPanel.classList.remove('open');
    if (helpOverlay) helpOverlay.classList.remove('open');
  }

  if (helpToggle) helpToggle.addEventListener('click', openHelp);
  if (helpClose) helpClose.addEventListener('click', closeHelp);
  if (helpOverlay) helpOverlay.addEventListener('click', closeHelp);

  // Auto-dismiss flash messages
  document.querySelectorAll('.alert').forEach(function (el) {
    setTimeout(function () { el.style.opacity = '0'; setTimeout(function () { el.remove(); }, 300); }, 6000);
  });
});
