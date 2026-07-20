// Recipe detail: live serving-scaling + metric/imperial unit toggle.
// The conversion/rounding/formatting logic here mirrors app/services/units.py
// so that on-screen scaling and the server-generated shopping list agree.
(function () {
  const root = document.querySelector('.recipe-detail');
  const dataEl = document.getElementById('recipe-data');
  if (!root || !dataEl) return;

  const data = JSON.parse(dataEl.textContent);

  // --- units mirror (see units.py) ---
  const UNIT_TYPE = {
    tsp: 'volume', tbsp: 'volume', cup: 'volume', fl_oz: 'volume', ml: 'volume', l: 'volume',
    g: 'weight', kg: 'weight', oz: 'weight', lb: 'weight',
  };
  const TO_BASE = {
    tsp: 4.92892, tbsp: 14.7868, fl_oz: 29.5735, cup: 236.588, ml: 1, l: 1000,
    g: 1, kg: 1000, oz: 28.3495, lb: 453.592,
  };
  const LABELS = { tsp: 'tsp', tbsp: 'tbsp', cup: 'cup', fl_oz: 'fl oz', ml: 'ml', l: 'l', g: 'g', kg: 'kg', oz: 'oz', lb: 'lb' };
  const FRACTION_UNITS = new Set(['tsp', 'tbsp', 'cup']);

  function mtype(u) { return u == null ? 'count' : (UNIT_TYPE[u] || 'count'); }

  function toSystem(qty, unit, system) {
    const t = mtype(unit);
    if (t === 'count' || unit == null) return [qty, unit];
    const metric = system === 'metric';
    if (t === 'volume') {
      const ml = qty * TO_BASE[unit];
      if (metric) return ml >= 1000 ? [ml / 1000, 'l'] : [ml, 'ml'];
      for (const u of ['cup', 'fl_oz', 'tbsp', 'tsp']) {
        const v = ml / TO_BASE[u];
        if (v >= 1) return [v, u];
      }
      return [ml / TO_BASE.tsp, 'tsp'];
    }
    // weight
    const g = qty * TO_BASE[unit];
    if (metric) return g >= 1000 ? [g / 1000, 'kg'] : [g, 'g'];
    const oz = g / TO_BASE.oz;
    return oz >= 16 ? [oz / 16, 'lb'] : [oz, 'oz'];
  }

  function roundCooking(qty, unit) {
    if (qty == null) return qty;
    const t = mtype(unit);
    if (FRACTION_UNITS.has(unit) || t === 'count') return Math.round(qty * 4) / 4;
    if (unit === 'ml' || unit === 'g') return qty >= 100 ? Math.round(qty / 5) * 5 : Math.round(qty);
    return Math.round(qty * 10) / 10;
  }

  const DENOMS = [2, 3, 4, 8];
  function formatQuantity(qty) {
    if (qty == null) return '';
    if (qty < 0) return '-' + formatQuantity(-qty);
    let whole = Math.floor(qty);
    const frac = qty - whole;
    if (frac < 1e-6) return String(whole);
    let best = null, bestErr = 1e9;
    for (const d of DENOMS) {
      const num = Math.round(frac * d);
      if (num === 0) continue;
      const err = Math.abs(num / d - frac);
      if (err < bestErr - 1e-9) { bestErr = err; best = [num, d]; }
    }
    if (!best || bestErr > 0.06) {
      return (Math.round(qty * 100) / 100).toString();
    }
    let [num, d] = best;
    if (num >= d) { whole += Math.floor(num / d); num = num % d; if (num === 0) return String(whole); }
    const fs = num + '/' + d;
    return whole ? whole + ' ' + fs : fs;
  }

  const TEMP_RE = /(-?\d{2,3})\s*(?:°|degrees?\s*)?\s*([CF])\b/gi;
  function convertTemps(text, system) {
    const target = system === 'metric' ? 'C' : 'F';
    return text.replace(TEMP_RE, (m, val, unit) => {
      const src = unit.toUpperCase();
      const v = parseFloat(val);
      if (src === target) return m;
      if (src === 'F') { const c = ((v - 32) * 5) / 9; return (Math.round(c / 5) * 5) + '°C'; }
      const f = (v * 9) / 5 + 32;
      return (Math.round(f / 5) * 5) + '°F';
    });
  }

  // --- state ---
  const baseServings = data.servings && data.servings > 0 ? data.servings : null;
  const servInput = document.getElementById('servings-input');
  const ingWrap = document.getElementById('ingredients');
  const stepsWrap = document.getElementById('instructions');
  const storeKey = 'units:' + (root.dataset.recipeId || '');

  let system = localStorage.getItem(storeKey) || root.dataset.defaultSystem || 'metric';

  function currentServings() {
    const v = parseFloat(servInput.value);
    return isNaN(v) || v <= 0 ? (baseServings || 1) : v;
  }

  function scaleOne(qty) {
    if (!baseServings) return qty; // no base -> cannot scale, show as-is
    return qty * (currentServings() / baseServings);
  }

  function renderIngredientText(ing) {
    if (!ing.parsed || ing.quantity == null) {
      return { amount: '', unit: '', name: ing.raw_text, prep: '', note: 'as written' };
    }
    let qty = scaleOne(ing.quantity);
    let [q, u] = toSystem(qty, ing.unit, system);
    q = roundCooking(q, u);
    let amount = formatQuantity(q);
    if (ing.quantity_max != null) {
      let [qm, um] = toSystem(scaleOne(ing.quantity_max), ing.unit, system);
      qm = roundCooking(qm, um);
      amount += '–' + formatQuantity(qm);
      u = um;
    }
    return { amount, unit: LABELS[u] || '', name: ing.name || ing.raw_text, prep: ing.note || '', note: '' };
  }

  function render() {
    // ingredients
    ingWrap.innerHTML = '';
    data.groups.forEach((g) => {
      const box = document.createElement('div');
      box.className = 'ingredient-group';
      if (g.title) {
        const h = document.createElement('h3');
        h.textContent = g.title;
        box.appendChild(h);
      }
      const ul = document.createElement('ul');
      ul.className = 'ingredient-list';
      g.ingredients.forEach((ing) => {
        const li = document.createElement('li');
        const r = renderIngredientText(ing);
        if (r.amount) {
          const a = document.createElement('span');
          a.className = 'amount';
          a.textContent = (r.amount + ' ' + r.unit).trim() + ' ';
          li.appendChild(a);
        }
        li.appendChild(document.createTextNode(r.name));
        if (r.prep) {
          const p = document.createElement('span');
          p.className = 'prep';
          p.textContent = ', ' + r.prep;
          li.appendChild(p);
        }
        if (r.note) {
          const n = document.createElement('span');
          n.className = 'note';
          n.textContent = '(' + r.note + ')';
          li.appendChild(n);
        }
        ul.appendChild(li);
      });
      box.appendChild(ul);
      ingWrap.appendChild(box);
    });

    // instructions (with temperature conversion)
    stepsWrap.innerHTML = '';
    (data.instructions || []).forEach((step) => {
      const li = document.createElement('li');
      li.textContent = convertTemps(step, system);
      stepsWrap.appendChild(li);
    });

    // toggle button state
    document.querySelectorAll('.toggle-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.system === system);
    });
  }

  // --- events ---
  if (servInput) {
    servInput.addEventListener('input', render);
    document.getElementById('serv-plus')?.addEventListener('click', () => {
      servInput.value = Math.max(1, (parseFloat(servInput.value) || 0) + 1);
      render();
    });
    document.getElementById('serv-minus')?.addEventListener('click', () => {
      servInput.value = Math.max(1, (parseFloat(servInput.value) || 2) - 1);
      render();
    });
  }
  document.querySelectorAll('.toggle-btn').forEach((b) => {
    b.addEventListener('click', () => {
      system = b.dataset.system;
      localStorage.setItem(storeKey, system);
      render();
    });
  });

  render();
})();
