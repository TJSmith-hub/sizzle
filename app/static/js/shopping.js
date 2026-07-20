// Shopping list: tick items off and remember checked state per list in localStorage.
(function () {
  const list = document.getElementById('shopping-list');
  if (!list) return;

  const storeKey = 'shopping:' + (list.dataset.key || 'default');
  let checked = {};
  try {
    checked = JSON.parse(localStorage.getItem(storeKey) || '{}');
  } catch (e) {
    checked = {};
  }

  const items = Array.from(list.querySelectorAll('.check-item'));
  items.forEach((li, idx) => {
    const box = li.querySelector('.tick');
    const name = (li.querySelector('.iname')?.textContent || '') + '#' + idx;
    if (checked[name]) {
      box.checked = true;
      li.classList.add('checked');
    }
    box.addEventListener('change', () => {
      li.classList.toggle('checked', box.checked);
      checked[name] = box.checked;
      localStorage.setItem(storeKey, JSON.stringify(checked));
    });
  });
})();
