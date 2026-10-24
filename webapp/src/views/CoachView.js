/**
 * CoachView.js — sports coach view (static demo).
 *
 * Renders once with hardcoded data to sell the vision.
 * No datastore subscription — only PersonalView is live.
 */

import { THRESHOLDS, fmtC } from '../lib/datastore.js';
import { forecastRange, formatRange } from '../lib/estimator.js';
import { toast } from '../lib/toast.js';

const W = fmtC(THRESHOLDS.WATCH_C);
const A = fmtC(THRESHOLDS.ACT_NOW_C);

const LABELS = { ok: 'OK', watch: 'Watch', act: 'Act now', paused: 'Cannot estimate' };

function _ctToStatus(name, ct) {
  if (name === 'S. Kim') return 'paused';
  if (ct === null || ct === undefined) return 'paused';
  if (ct >= THRESHOLDS.ACT_NOW_C) return 'act';
  if (ct >= THRESHOLDS.WATCH_C)   return 'watch';
  return 'ok';
}

const _PLAYERS_RAW = [
  { name: 'J. Okafor', num: 22, ct: 38.8, half: 0.92, trend: '↑ 0.4° / 10 min', note: 'Rest 15+ min' },
  { name: 'T. Brooks', num: 54, ct: 38.6, half: 0.92, trend: '↑ 0.3° / 10 min', note: 'Rest 15+ min' },
  { name: 'S. Kim',    num: 31, ct: null, half: null,  trend: 'High HR, no motion', note: 'Check in person' },
  { name: 'M. Alvarez',num: 7,  ct: 38.6, half: 0.92, trend: '↑ 0.3° / 10 min', note: 'Rest 15+ min' },
  { name: 'E. Vega',   num: 60, ct: 38.1, half: 0.70, trend: '↑ 0.4° / 10 min', rate: 0.4 },
  { name: 'D. Price',  num: 88, ct: 38.0, half: 0.68, trend: '↑ 0.2° / 10 min', rate: 0.2 },
  { name: 'A. Nwosu',  num: 12, ct: 37.8, half: 0.68, trend: '→ steady',          note: 'Break with team' },
  { name: 'R. Patel',  num: 3,  ct: 37.7, half: 0.62, trend: '↓ falling',         note: 'Break with team' },
  { name: 'C. Moreau', num: 45, ct: 37.6, half: 0.62, trend: '→ steady',          note: 'Break with team' },
  { name: 'L. Grant',  num: 19, ct: 37.5, half: 0.62, trend: '→ steady',          note: 'Break with team' },
  { name: 'B. Walsh',  num: 9,  ct: 37.4, half: 0.62, trend: '→ steady',          note: 'Break with team' },
  { name: 'H. Osei',   num: 24, ct: 37.2, half: 0.59, trend: '→ steady',          note: 'Seated control', control: true },
];

// Watch notes use the same forecast range as the Personal view.
function _note(p, status) {
  if (p.note) return p.note;
  const r = forecastRange(p.ct, p.rate);
  return r ? `${A} ${formatRange(r)}` : 'Break with team';
}

const PLAYERS = _PLAYERS_RAW.map(p => {
  const status = _ctToStatus(p.name, p.ct);
  return { ...p, status, note: _note(p, status) };
});
const WATCH_NAMES = PLAYERS.filter(p => p.status === 'watch').map(p => p.name);

const LOG = [
  { time: '4:44 PM', text: 'S. Kim: cannot estimate (high heart rate while still)' },
  { time: '4:42 PM', text: 'J. Okafor reached Act now (38.8 ± 0.9°C, rising)' },
  { time: '4:40 PM', text: 'M. Alvarez reached Act now (38.6 ± 0.9°C, rising)' },
  { time: '4:38 PM', text: 'T. Brooks reached Act now (38.6 ± 0.9°C)' },
  { time: '4:20 PM', text: 'Team water break, 5 min' },
  { time: '4:05 PM', text: 'Practice started · 12 baselines captured' },
];

const RISK_ORDER = { act: 0, paused: 1, watch: 2, ok: 3 };

const BUTTON_TOASTS = {
  'call-break': 'Break called for the team.',
  'keep':       'Keeping the schedule. Next break in 6 min.',
  'done':       'Marked done.',
};

export function mount(container) {
  container.innerHTML = _render();
  const root = container.querySelector('.page');
  // No subscription — static. Buttons only acknowledge the click.
  const onClick = e => {
    const btn = e.target.closest('[data-demo]');
    if (!btn) return;
    toast(BUTTON_TOASTS[btn.dataset.demo]);
    if (btn.dataset.demo === 'done') { btn.disabled = true; btn.textContent = 'Done'; }
  };
  root.addEventListener('click', onClick);
  return () => root.removeEventListener('click', onClick);
}

function _render() {
  const counts = { act: 0, watch: 0, ok: 0, paused: 0 };
  PLAYERS.forEach(p => { if (p.status in counts) counts[p.status]++; });

  const sorted = [...PLAYERS].sort((a, b) =>
    (RISK_ORDER[a.status] ?? 4) - (RISK_ORDER[b.status] ?? 4)
  );

  const tiles = [
    _tile('act',    'Act now',         counts.act,    `Estimate at or over ${A}C`),
    _tile('watch',  'Watch',           counts.watch,  `Estimate ${W}C or higher`),
    _tile('ok',     'OK',              counts.ok,     `Estimate under ${W}C`),
    _tile('paused', 'Cannot estimate', counts.paused, 'Signals disagree · check in person'),
  ].join('');

  const playerCards = sorted.map(_playerCard).join('');

  const logItems = LOG.map(l =>
    `<li><time>${_esc(l.time)}</time><span>${_esc(l.text)}</span></li>`
  ).join('');

  return /* html */`
<div class="page page--coach">
  <div class="page__head">
    <div>
      <p class="page__sub">Preseason practice · Field 2 · started 4:05 PM · Example team · 12 players</p>
      <h1>Team heat status</h1>
    </div>
    <div class="chips">
      <span class="chip">Air 31°C · Humidity 68%</span>
      <span class="chip chip--watch">Heat index 36°C · High</span>
    </div>
  </div>

  <div class="tiles">${tiles}</div>

  <div class="split">
    <section class="split__main" aria-labelledby="players-title">
      <div class="section-head">
        <h2 id="players-title">Players</h2>
        <span>Sorted by risk · ± is the measured 90% range · updates every 5 s</span>
      </div>
      <div class="players">${playerCards}</div>
    </section>

    <aside class="split__side">
      <section class="card card--dark breakplan" aria-labelledby="bp-title">
        <div class="breakplan__head">
          <h2 id="bp-title">Break plan</h2>
          <span>20 min on, 5 off</span>
        </div>
        <div class="breakplan__big">
          <strong>6 min</strong>
          <span>to next team water break</span>
        </div>
        <p>Bring it forward: ${_list(WATCH_NAMES)} could reach ${A} in the next 30 min. Each player gets 250 ml. Okafor, Brooks and Alvarez stay out until Ember shows Watch or OK.</p>
        <div class="btn-row">
          <button type="button" class="btn btn--amber" data-demo="call-break">Call break now</button>
          <button type="button" class="btn btn--ghost-dark" data-demo="keep">Keep schedule</button>
        </div>
      </section>

      <section class="card todo" aria-labelledby="todo-title">
        <h2 id="todo-title">Do this now</h2>
        <div class="todo__item">
          <span class="badge status--act">Act now</span>
          <p>Pull J. Okafor (#22), T. Brooks (#54), and M. Alvarez (#7) to the cooling tent. All three are over ${A}C and still heating up.</p>
          <button type="button" class="btn btn--outline" style="align-self:flex-start" data-demo="done">Mark done</button>
        </div>
        <div class="todo__item">
          <span class="badge status--watch">Next 5 min</span>
          <p>${_count(WATCH_NAMES.length)} over ${W}C and heating up. Call the water break early. Check on S. Kim in person: Ember can't tell if their high heart rate is heat.</p>
        </div>
        <div class="todo__item">
          <span class="badge status--ok">Rest of practice</span>
          <p>Heat index stays high until about 6 PM. Keep 20 on, 5 off and 250 ml per break.</p>
        </div>
      </section>

      <section class="card" aria-labelledby="log-title">
        <h2 id="log-title" style="margin-bottom:10px">Today</h2>
        <ul class="log">${logItems}</ul>
      </section>

      <p class="fineprint">Athletes opted in to share status and core temp range. Heart rate and history stay on each athlete's phone. A triage signal, not an alarm or a medical device: it supports your judgment, it doesn't replace it.</p>
    </aside>
  </div>
</div>`;
}

function _tile(status, label, num, note) {
  return `<div class="tile status--${status}">
    <span class="label">${_esc(label)}</span>
    <span class="tile__num">${num}</span>
    <span class="tile__note">${_esc(note)}</span>
  </div>`;
}

function _playerCard(p) {
  const tempHtml = p.status === 'paused' || p.ct === null
    ? `<div class="player__none">No number shown</div>`
    : `<div class="player__temp"><strong>${p.ct.toFixed(1)}</strong><span>± ${(p.half ?? 0).toFixed(1)}°C</span></div>`;
  const controlTag = p.control ? `<span class="tag">Control</span>` : '';

  return `<article class="player status--${p.status}">
    <div class="strip">${_esc(LABELS[p.status] ?? p.status)}</div>
    <div class="player__body">
      <div class="player__name">
        <span>${_esc(p.name)} <small>#${p.num}</small></span>
        ${controlTag}
      </div>
      ${tempHtml}
      <div class="player__foot">
        <span>${_esc(p.trend)}</span>
        <span>${_esc(p.note)}</span>
      </div>
    </div>
  </article>`;
}

function _list(names) {
  if (names.length <= 1) return names.join('');
  return names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1];
}

function _count(n) {
  const words = ['No players are', 'One player is', 'Two players are', 'Three players are', 'Four players are'];
  return words[n] ?? `${n} players are`;
}

function _esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch])
  );
}
