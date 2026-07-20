// Review / edit screen: button-based editor for ingredient groups + steps.
// Reorganize with move up/down and a "move to group" dropdown (no drag-and-drop,
// works on touch). On submit, the whole structure is serialized into one JSON
// field so the server can persist it in a single validated payload.
(function () {
  const form = document.getElementById('review-form');
  const dataEl = document.getElementById('recipe-data');
  if (!form || !dataEl) return;

  const UNITS = ['', 'tsp', 'tbsp', 'cup', 'fl_oz', 'ml', 'l', 'g', 'kg', 'oz', 'lb'];

  const data = JSON.parse(dataEl.textContent);
  // Working state (deep-ish copy).
  let groups = (data.groups || []).map((g) => ({
    title: g.title || '',
    ingredients: (g.ingredients || []).map((i) => ({
      raw_text: i.raw_text || '',
      quantity: i.quantity,
      quantity_max: i.quantity_max,
      unit: i.unit || '',
      name: i.name || '',
      parsed: !!i.parsed,
    })),
  }));
  if (!groups.length) groups = [{ title: '', ingredients: [] }];
  let steps = (data.instructions || []).slice();

  const groupsEl = document.getElementById('groups');
  const stepsEl = document.getElementById('steps');

  function el(tag, attrs, children) {
    const n = document.createElement(tag);
    if (attrs) Object.entries(attrs).forEach(([k, v]) => {
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else n.setAttribute(k, v);
    });
    (children || []).forEach((c) => n.appendChild(c));
    return n;
  }

  function num(v) {
    if (v === '' || v == null) return null;
    const n = parseFloat(v);
    return isNaN(n) ? null : n;
  }

  function groupLabel(g, idx) {
    return 'Group ' + (idx + 1) + (g.title ? ': ' + g.title : ' (unnamed)');
  }

  function renderGroups() {
    groupsEl.innerHTML = '';
    groups.forEach((g, gi) => {
      // --- group header ---
      const titleInput = el('input', { type: 'text', placeholder: 'Group name (leave blank for none)' });
      titleInput.value = g.title;
      titleInput.addEventListener('input', () => { g.title = titleInput.value; });

      const up = el('button', { type: 'button', class: 'btn btn-xs', text: '↑', title: 'Move group up' });
      up.disabled = gi === 0;
      up.addEventListener('click', () => { swap(groups, gi, gi - 1); renderGroups(); });

      const down = el('button', { type: 'button', class: 'btn btn-xs', text: '↓', title: 'Move group down' });
      down.disabled = gi === groups.length - 1;
      down.addEventListener('click', () => { swap(groups, gi, gi + 1); renderGroups(); });

      const del = el('button', { type: 'button', class: 'btn btn-xs btn-danger', text: '✕', title: 'Delete group' });
      del.addEventListener('click', () => {
        if (g.ingredients.length && !confirm('Delete this group and its ' + g.ingredients.length + ' ingredient(s)?')) return;
        groups.splice(gi, 1);
        if (!groups.length) groups.push({ title: '', ingredients: [] });
        renderGroups();
      });

      const head = el('div', { class: 'group-head' }, [
        titleInput,
        el('div', { class: 'group-controls' }, [up, down, del]),
      ]);

      // --- ingredient rows ---
      const rows = el('div', { class: 'ing-rows' });
      g.ingredients.forEach((ing, ii) => rows.appendChild(renderRow(g, gi, ing, ii)));

      // --- group footer ---
      const addIng = el('button', { type: 'button', class: 'btn btn-xs', text: '+ Add ingredient' });
      addIng.addEventListener('click', () => {
        g.ingredients.push({ raw_text: '', quantity: null, quantity_max: null, unit: '', name: '', parsed: false });
        renderGroups();
      });
      const foot = el('div', { class: 'group-foot' }, [addIng]);

      groupsEl.appendChild(el('div', { class: 'group' }, [head, rows, foot]));
    });
  }

  function renderRow(group, gi, ing, ii) {
    const qty = el('input', { type: 'text', class: 'qty-in', placeholder: 'qty' });
    qty.value = ing.quantity != null ? ing.quantity : '';
    qty.addEventListener('input', () => {
      ing.quantity = num(qty.value);
      ing.parsed = ing.quantity != null;
      row.classList.toggle('is-unparsed', !ing.parsed);
      flag.textContent = ing.parsed ? '' : 'Unparsed — shown as raw text, not scaled';
    });

    const unit = el('select', {});
    UNITS.forEach((u) => {
      const o = el('option', { value: u, text: u === '' ? '(count)' : u });
      if (u === (ing.unit || '')) o.selected = true;
      unit.appendChild(o);
    });
    unit.addEventListener('change', () => { ing.unit = unit.value; });

    const name = el('input', { type: 'text', placeholder: 'ingredient name' });
    name.value = ing.name || '';
    name.addEventListener('input', () => { ing.name = name.value; });

    // controls: up / down / move-to-group / delete
    const up = el('button', { type: 'button', class: 'btn btn-xs', text: '↑' });
    up.disabled = ii === 0;
    up.addEventListener('click', () => { swap(group.ingredients, ii, ii - 1); renderGroups(); });

    const down = el('button', { type: 'button', class: 'btn btn-xs', text: '↓' });
    down.disabled = ii === group.ingredients.length - 1;
    down.addEventListener('click', () => { swap(group.ingredients, ii, ii + 1); renderGroups(); });

    const move = el('select', { class: 'move-target', title: 'Move to group' });
    move.appendChild(el('option', { value: '', text: 'move to…' }));
    groups.forEach((gg, idx) => {
      if (idx === gi) return;
      move.appendChild(el('option', { value: String(idx), text: groupLabel(gg, idx) }));
    });
    move.addEventListener('change', () => {
      const target = parseInt(move.value, 10);
      if (isNaN(target)) return;
      group.ingredients.splice(ii, 1);
      groups[target].ingredients.push(ing);
      renderGroups();
    });

    const del = el('button', { type: 'button', class: 'btn btn-xs btn-danger', text: '✕' });
    del.addEventListener('click', () => { group.ingredients.splice(ii, 1); renderGroups(); });

    const controls = el('div', { class: 'row-controls' }, [up, down, move, del]);

    const raw = el('input', { type: 'text', class: 'raw', placeholder: 'original text' });
    raw.value = ing.raw_text || '';
    raw.addEventListener('input', () => { ing.raw_text = raw.value; });

    const flag = el('span', { class: 'flag' });
    flag.textContent = ing.parsed ? '' : (ing.raw_text ? 'Unparsed — shown as raw text, not scaled' : '');

    const row = el('div', { class: 'ing-row' + (ing.parsed ? '' : ' is-unparsed') }, [qty, unit, name, controls, raw, flag]);
    return row;
  }

  function renderSteps() {
    stepsEl.innerHTML = '';
    steps.forEach((text, si) => {
      const ta = el('textarea', { rows: '2' });
      ta.value = text;
      ta.addEventListener('input', () => { steps[si] = ta.value; });

      const up = el('button', { type: 'button', class: 'btn btn-xs', text: '↑' });
      up.disabled = si === 0;
      up.addEventListener('click', () => { swap(steps, si, si - 1); renderSteps(); });

      const down = el('button', { type: 'button', class: 'btn btn-xs', text: '↓' });
      down.disabled = si === steps.length - 1;
      down.addEventListener('click', () => { swap(steps, si, si + 1); renderSteps(); });

      const del = el('button', { type: 'button', class: 'btn btn-xs btn-danger', text: '✕' });
      del.addEventListener('click', () => { steps.splice(si, 1); renderSteps(); });

      const num = el('span', { class: 'step-num', text: String(si + 1) + '.' });
      const controls = el('div', { class: 'row-controls' }, [up, down, del]);
      stepsEl.appendChild(el('div', { class: 'step-row' }, [num, ta, controls]));
    });
  }

  function swap(arr, a, b) {
    if (b < 0 || b >= arr.length) return;
    const t = arr[a]; arr[a] = arr[b]; arr[b] = t;
  }

  // --- add buttons ---
  document.getElementById('add-group').addEventListener('click', () => {
    groups.push({ title: '', ingredients: [] });
    renderGroups();
  });
  document.getElementById('add-step').addEventListener('click', () => {
    steps.push('');
    renderSteps();
  });

  // --- serialize on submit ---
  form.addEventListener('submit', (e) => {
    const intVal = (id) => {
      const v = document.getElementById(id).value.trim();
      if (v === '') return null;
      const n = parseInt(v, 10);
      return isNaN(n) ? null : n;
    };
    const strVal = (id) => {
      const v = document.getElementById(id).value.trim();
      return v === '' ? null : v;
    };

    const payload = {
      title: document.getElementById('f-title').value.trim(),
      source_url: strVal('f-source'),
      image_url: strVal('f-image'),
      servings: intVal('f-servings'),
      prep_time: intVal('f-prep'),
      cook_time: intVal('f-cook'),
      total_time: intVal('f-total'),
      tags: document.getElementById('f-tags').value.split(',').map((s) => s.trim()).filter(Boolean),
      instructions: steps.map((s) => s.trim()).filter(Boolean),
      groups: groups
        .filter((g) => g.title.trim() || g.ingredients.length)
        .map((g) => ({
          title: g.title.trim() || null,
          ingredients: g.ingredients
            .filter((i) => (i.raw_text || i.name || '').trim())
            .map((i) => {
              const q = i.quantity;
              const parsed = q != null && !isNaN(q);
              return {
                raw_text: (i.raw_text || i.name || '').trim(),
                quantity: parsed ? q : null,
                quantity_max: i.quantity_max != null ? i.quantity_max : null,
                unit: i.unit || null,
                name: (i.name || '').trim() || null,
                parsed: parsed,
              };
            }),
        })),
    };

    if (!payload.title) {
      e.preventDefault();
      alert('Please enter a title.');
      return;
    }
    document.getElementById('payload').value = JSON.stringify(payload);
  });

  renderGroups();
  renderSteps();
})();
