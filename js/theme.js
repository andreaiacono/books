// js/theme.js — Theme toggle (loaded as plain script, not a module)
(function () {
  const root = document.documentElement;

  function syncMeta() {
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = root.dataset.theme === 'light' ? '#faf8f5' : '#0f0e0d';
  }

  function syncButton() {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    btn.textContent = root.dataset.theme === 'light' ? '☾' : '☀';
    btn.setAttribute('aria-label', root.dataset.theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode');
  }

  function setTheme(t) {
    root.dataset.theme = t;
    localStorage.setItem('theme', t);
    syncButton();
    syncMeta();
  }

  const btn = document.getElementById('theme-toggle');
  if (btn) btn.addEventListener('click', () => setTheme(root.dataset.theme === 'light' ? 'dark' : 'light'));

  syncButton();
  syncMeta();
})();
