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
  // Spoon/cup measures read naturally in metric recipes too - metric mode
  // leaves them as-is rather than forcing a conversion to ml/l (mirrors units.py).
  const VOLUME_KEEP_FOR_METRIC = new Set(['tsp', 'tbsp', 'cup']);

  function mtype(u) { return u == null ? 'count' : (UNIT_TYPE[u] || 'count'); }

  // Convert within a measurement type (mirrors units.convert). Returns null for
  // cross-type conversions; count<->count passes the quantity through.
  function convert(qty, from, to) {
    if (from === to) return qty;
    if (mtype(from) !== mtype(to)) return null;
    if (from == null || to == null) return qty;
    return (qty * TO_BASE[from]) / TO_BASE[to];
  }

  function toSystem(qty, unit, system) {
    const t = mtype(unit);
    if (t === 'count' || unit == null) return [qty, unit];
    const metric = system === 'metric';
    if (t === 'volume') {
      if (metric && VOLUME_KEEP_FOR_METRIC.has(unit)) return [qty, unit];
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

  // ml equivalent of a cup quantity, rounded UP to the nearest 10 ml. Shown
  // alongside cups as a metric hint (mirrors units.cup_to_ml).
  function cupToMl(cups) { return Math.ceil((cups * TO_BASE.cup) / 10) * 10; }

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

  // --- durations -> tappable timer chips ---
  // One component of a duration ("20 minutes", "1 hr", "20-25 mins"). A range
  // takes the upper bound (group 2). Deliberately conservative: no bare h/m/s
  // single letters, so we don't turn stray numbers into timers.
  const DURATION_RE = /(\d+(?:\.\d+)?)(?:\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?))?\s*(hours?|hrs?|hr|minutes?|mins?|min|seconds?|secs?|sec)\b/gi;

  function unitSeconds(unit) {
    const u = unit.toLowerCase();
    if (u[0] === 'h') return 3600;
    if (u[0] === 'm') return 60;
    return 1;
  }

  // Find duration spans in `text`, merging adjacent components ("1 hour 30
  // minutes") into a single chip. Returns [{start, end, seconds}].
  function findDurations(text) {
    const comps = [];
    let m;
    DURATION_RE.lastIndex = 0;
    while ((m = DURATION_RE.exec(text)) !== null) {
      const value = m[2] != null ? parseFloat(m[2]) : parseFloat(m[1]);
      comps.push({ start: m.index, end: m.index + m[0].length, seconds: Math.round(value * unitSeconds(m[3])) });
    }
    const merged = [];
    comps.forEach((c) => {
      const last = merged[merged.length - 1];
      // Merge only if the gap is whitespace or a joining "and".
      if (last && /^\s*(?:and\s*)?$/i.test(text.slice(last.end, c.start))) {
        last.end = c.end;
        last.seconds += c.seconds;
      } else {
        merged.push({ ...c });
      }
    });
    return merged;
  }

  // Append `text` to `li`, rendering any durations as timer buttons.
  function appendStepText(li, text, contextLabel) {
    const spans = findDurations(text);
    if (!spans.length) { li.appendChild(document.createTextNode(text)); return; }
    let idx = 0;
    spans.forEach((s) => {
      if (s.start > idx) li.appendChild(document.createTextNode(text.slice(idx, s.start)));
      const label = text.slice(s.start, s.end);
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'timer-chip';
      btn.textContent = '⏱ ' + label;
      btn.title = 'Start a ' + label + ' timer';
      btn.addEventListener('click', () => {
        if (window.SizzleTimers) window.SizzleTimers.start(s.seconds, contextLabel || label);
      });
      li.appendChild(btn);
      idx = s.end;
    });
    if (idx < text.length) li.appendChild(document.createTextNode(text.slice(idx)));
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
      return { amount: '', unit: '', mlHint: '', name: ing.raw_text, prep: '', note: 'as written' };
    }
    let q, u, qm = null, amount;
    if (ing.quantity_max != null) {
      // Pick the display unit from the max end (its larger magnitude decides any
      // promotion, e.g. ml->l), then express the low end in that same unit so
      // the range reads consistently (mirrors shopping_list._to_display).
      [qm, u] = toSystem(scaleOne(ing.quantity_max), ing.unit, system);
      q = roundCooking(convert(scaleOne(ing.quantity), ing.unit, u), u);
      qm = roundCooking(qm, u);
      amount = formatQuantity(q) + '–' + formatQuantity(qm);
    } else {
      [q, u] = toSystem(scaleOne(ing.quantity), ing.unit, system);
      q = roundCooking(q, u);
      amount = formatQuantity(q);
    }
    // Show a ml equivalent alongside cups (mirrors DisplayItem.display_ml_hint).
    let mlHint = '';
    if (u === 'cup') {
      mlHint = '(' + cupToMl(q) + (qm != null ? '–' + cupToMl(qm) : '') + ' ml)';
    }
    return { amount, unit: LABELS[u] || '', mlHint, name: ing.name || ing.raw_text, prep: ing.note || '', note: '' };
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
          a.textContent = (r.amount + ' ' + r.unit + (r.mlHint ? ' ' + r.mlHint : '')).trim() + ' ';
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

    // instructions (grouped by heading, with temperature conversion). Each
    // heading starts a fresh <ol>, but step numbers run continuously across the
    // whole recipe (the <ol> `start` carries the count on) so a recipe of
    // single-step sections doesn't render "1." over and over.
    stepsWrap.innerHTML = '';
    let currentOl = null;
    let stepCount = 0;
    (data.instructions || []).forEach((raw) => {
      const item = typeof raw === 'string' ? { type: 'step', text: raw } : raw;
      if (item.type === 'heading') {
        const h = document.createElement('h3');
        h.className = 'instruction-group-heading';
        h.textContent = convertTemps(item.text, system);
        stepsWrap.appendChild(h);
        currentOl = null;
        return;
      }
      if (!currentOl) {
        currentOl = document.createElement('ol');
        currentOl.start = stepCount + 1;
        stepsWrap.appendChild(currentOl);
      }
      const li = document.createElement('li');
      appendStepText(li, convertTemps(item.text, system), 'Step ' + (stepCount + 1));
      currentOl.appendChild(li);
      stepCount += 1;
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
