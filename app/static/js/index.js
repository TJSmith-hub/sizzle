// Recipe list: track selection count and enable the "Make shopping list" button.
(function () {
  const checks = Array.from(document.querySelectorAll('.recipe-check'));
  const countEl = document.getElementById('selected-count');
  const btn = document.getElementById('make-list-btn');
  if (!checks.length || !btn) return;

  function update() {
    const n = checks.filter((c) => c.checked).length;
    if (countEl) countEl.textContent = String(n);
    btn.disabled = n === 0;
  }

  checks.forEach((c) => c.addEventListener('change', update));
  update();
})();
