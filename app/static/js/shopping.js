// Shopping list: tick items off without a full page reload, and toggle the
// inline edit form for a row. Checked state is persisted server-side (see
// routers/shopping.py toggle_item), not in localStorage -- the list is now a
// shared, durable record rather than a per-browser view.
(function () {
  const list = document.getElementById('shopping-list');
  if (!list) return;

  list.querySelectorAll('.check-item').forEach((li) => {
    const id = li.dataset.itemId;
    const box = li.querySelector('.tick');

    box.addEventListener('change', () => {
      li.classList.toggle('checked', box.checked);
      fetch(`/shopping-list/items/${id}/toggle`, { method: 'POST' }).catch(() => {
        // Network hiccup: reload so the checkbox reflects the real state.
        window.location.reload();
      });
    });

    const editBtn = li.querySelector('.edit-toggle');
    const cancelBtn = li.querySelector('.edit-cancel');
    editBtn?.addEventListener('click', () => li.classList.add('editing'));
    cancelBtn?.addEventListener('click', () => li.classList.remove('editing'));
  });
})();
