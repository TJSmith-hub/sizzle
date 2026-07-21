// Cooking timers. Steps on the detail page expose tappable durations (see
// scale.js); tapping one calls SizzleTimers.start(seconds, label) and a timer
// appears in a fixed bar at the bottom of the screen.
//
// Mobile browsers throttle or freeze setInterval when the tab is backgrounded
// or the screen locks, so a naive countdown drifts. We instead store each
// timer's target end time (wall clock) and recompute the remaining time on
// every tick and whenever the page becomes visible again — the display is
// always correct the instant you look at it. State is persisted to
// localStorage (per recipe) so a refresh or accidental navigation doesn't lose
// a running timer.
window.SizzleTimers = (function () {
  const root = document.querySelector('.recipe-detail');
  const storeKey = 'timers:' + ((root && root.dataset.recipeId) || 'x');

  // timer: {id, label, duration, endAt, remaining, state: 'running'|'paused'|'done'}
  // endAt is meaningful while running; remaining (seconds) is authoritative
  // while paused. `alarmed` guards against re-firing the alert every tick.
  let timers = load();
  let seq = timers.reduce((m, t) => Math.max(m, t.id), 0);
  let bar = null;
  let audioCtx = null;

  function load() {
    try {
      const raw = JSON.parse(localStorage.getItem(storeKey) || '[]');
      if (!Array.isArray(raw)) return [];
      return raw.map((t) => ({
        id: t.id, label: t.label || '', duration: t.duration || 0,
        endAt: t.endAt || 0, remaining: t.remaining || 0,
        state: t.state === 'paused' || t.state === 'done' ? t.state : 'running',
        alarmed: t.state === 'done',
      }));
    } catch (e) {
      return [];
    }
  }

  function save() {
    try {
      localStorage.setItem(storeKey, JSON.stringify(timers.map((t) => ({
        id: t.id, label: t.label, duration: t.duration,
        endAt: t.endAt, remaining: t.remaining, state: t.state,
      }))));
    } catch (e) { /* private mode / quota — timers still work in-memory */ }
  }

  function now() { return Date.now(); }

  function secondsLeft(t) {
    if (t.state === 'paused') return Math.max(0, Math.round(t.remaining));
    return Math.max(0, Math.round((t.endAt - now()) / 1000));
  }

  function fmt(secs) {
    const s = Math.max(0, secs);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    const pad = (n) => String(n).padStart(2, '0');
    return h ? h + ':' + pad(m) + ':' + pad(sec) : m + ':' + pad(sec);
  }

  // --- alerting (best-effort; layered so it degrades gracefully) ---
  function beep() {
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      if (!audioCtx) audioCtx = new Ctx();
      if (audioCtx.state === 'suspended') audioCtx.resume();
      const t0 = audioCtx.currentTime;
      // three short rising pulses
      [0, 0.5, 1.0].forEach((offset, i) => {
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'sine';
        osc.frequency.value = 880 + i * 220;
        gain.gain.setValueAtTime(0.0001, t0 + offset);
        gain.gain.exponentialRampToValueAtTime(0.4, t0 + offset + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + offset + 0.35);
        osc.connect(gain).connect(audioCtx.destination);
        osc.start(t0 + offset);
        osc.stop(t0 + offset + 0.4);
      });
    } catch (e) { /* audio unavailable */ }
  }

  function notify(label) {
    try {
      if (navigator.vibrate) navigator.vibrate([200, 100, 200, 100, 200]);
    } catch (e) { /* no vibration */ }
    try {
      if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('⏱ Timer done', { body: label || 'Time is up', tag: 'sizzle-timer' });
      }
    } catch (e) { /* notifications unavailable */ }
  }

  function fire(t) {
    beep();
    notify(t.label);
  }

  // --- rendering ---
  function ensureBar() {
    if (bar) return bar;
    bar = document.createElement('div');
    bar.id = 'timer-bar';
    bar.setAttribute('role', 'region');
    bar.setAttribute('aria-label', 'Cooking timers');
    document.body.appendChild(bar);
    return bar;
  }

  function ctrlBtn(text, title, onClick) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn btn-round timer-ctrl';
    b.textContent = text;
    b.title = title;
    b.setAttribute('aria-label', title);
    b.addEventListener('click', onClick);
    return b;
  }

  function render() {
    ensureBar();
    document.body.classList.toggle('timers-active', timers.length > 0);
    bar.style.display = timers.length ? 'flex' : 'none';
    bar.innerHTML = '';
    timers.forEach((t) => {
      const row = document.createElement('div');
      row.className = 'timer-row' + (t.state === 'done' ? ' is-done' : '')
        + (t.state === 'paused' ? ' is-paused' : '');

      const time = document.createElement('span');
      time.className = 'timer-time';
      time.textContent = t.state === 'done' ? "Time's up" : fmt(secondsLeft(t));

      const label = document.createElement('span');
      label.className = 'timer-label';
      label.textContent = t.label || '';

      const controls = document.createElement('div');
      controls.className = 'timer-controls';
      if (t.state === 'done') {
        controls.appendChild(ctrlBtn('↻', 'Restart timer', () => restart(t.id)));
      } else if (t.state === 'paused') {
        controls.appendChild(ctrlBtn('▶', 'Resume', () => resume(t.id)));
        controls.appendChild(ctrlBtn('+1', 'Add one minute', () => addMinute(t.id)));
      } else {
        controls.appendChild(ctrlBtn('⏸', 'Pause', () => pause(t.id)));
        controls.appendChild(ctrlBtn('+1', 'Add one minute', () => addMinute(t.id)));
      }
      controls.appendChild(ctrlBtn('✕', 'Dismiss timer', () => dismiss(t.id)));

      const main = document.createElement('div');
      main.className = 'timer-main';
      main.appendChild(time);
      if (t.label) main.appendChild(label);

      row.appendChild(main);
      row.appendChild(controls);
      bar.appendChild(row);
    });
  }

  function tick() {
    let changed = false;
    timers.forEach((t) => {
      if (t.state === 'running' && secondsLeft(t) <= 0 && !t.alarmed) {
        t.state = 'done';
        t.alarmed = true;
        changed = true;
        fire(t);
      }
    });
    if (changed) save();
    render();
  }

  // --- actions ---
  function find(id) { return timers.find((t) => t.id === id); }

  function start(seconds, label) {
    seconds = Math.round(seconds);
    if (!seconds || seconds <= 0) return;
    requestNotifyPermission();
    // A user gesture reached us — unlock audio so the alarm can sound later.
    try {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (Ctx && !audioCtx) audioCtx = new Ctx();
      if (audioCtx && audioCtx.state === 'suspended') audioCtx.resume();
    } catch (e) { /* ignore */ }

    seq += 1;
    timers.push({
      id: seq, label: label || '', duration: seconds,
      endAt: now() + seconds * 1000, remaining: seconds,
      state: 'running', alarmed: false,
    });
    save();
    render();
  }

  function pause(id) {
    const t = find(id);
    if (!t || t.state !== 'running') return;
    t.remaining = secondsLeft(t);
    t.state = 'paused';
    save(); render();
  }

  function resume(id) {
    const t = find(id);
    if (!t || t.state !== 'paused') return;
    t.endAt = now() + t.remaining * 1000;
    t.state = 'running';
    save(); render();
  }

  function addMinute(id) {
    const t = find(id);
    if (!t) return;
    if (t.state === 'paused') t.remaining += 60;
    else t.endAt += 60000;
    save(); render();
  }

  function restart(id) {
    const t = find(id);
    if (!t) return;
    t.endAt = now() + t.duration * 1000;
    t.remaining = t.duration;
    t.state = 'running';
    t.alarmed = false;
    save(); render();
  }

  function dismiss(id) {
    timers = timers.filter((t) => t.id !== id);
    save(); render();
  }

  function requestNotifyPermission() {
    try {
      if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
      }
    } catch (e) { /* ignore */ }
  }

  // Timers frozen while backgrounded may already be overdue — catch up on return.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') tick();
  });

  // Re-attach the bar if a re-render wiped the body (defensive; detail page
  // doesn't do full re-renders, but keeps the bar resilient).
  setInterval(tick, 500);
  render();

  return { start };
})();
