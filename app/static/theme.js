/* Runs before first paint so the saved theme never flashes. Default: dark. */
(function () {
  var t = 'dark';
  try { if (localStorage.getItem('opspilot_theme') === 'light') t = 'light'; } catch (e) { /* storage blocked */ }
  document.documentElement.setAttribute('data-theme', t);
})();
