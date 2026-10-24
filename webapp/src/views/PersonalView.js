/**
 * PersonalView.js — wearer's view (the live demo).
 *
 * Uses the design-export markup and render approach, wired to live
 * datastore data. Status thresholds come from THRESHOLDS in datastore.js.
 * All times (elapsed, breaks, water) run on the data clock (snapshot.now),
 * so the demo simulation and a real device behave the same way.
 */

import {
  subscribe, startBreak, endBreak, recordDrink, STATUS, THRESHOLDS, fmtC, round1,
} from '../lib/datastore.js';
import {
  trendRate, formatTrend, forecastRange, formatRange, recommendedAction,
  CONF_EDGES, CONF_HALF, CONF_SYNTHETIC, CONF_MEASURED_COV,
} from '../lib/estimator.js';
import { toast } from '../lib/toast.js';

// ─── wearer + placeholder schedule ───────────────────────────────────────────
// Placeholder until taken from a published heat-index table (see TODO Phase 2).
const WEARER_NAME = 'Maya Chen';
const SCHEDULE = {
  workMin:        20,   // 20 on …
  breakMin:        5,   // … 5 off
  actBreakMin:    15,   // Act now: rest at least 15 min
  waterEveryMin:  15,   // 250 ml every 15 min
  waterMl:       250,
  watchWaterMin:   5,   // Watch: drink now, then again within 5 min
};
const SETUP_MIN = 5;            // baseline capture: sit still for 5 min
const FORECAST_MIN_DATA = 5;    // minutes of data before forecasting
const CHART_WINDOW_MIN = 30;
const MIN = 60_000;

const LABELS = {
  [STATUS.OK]:      'OK',
  [STATUS.WATCH]:   'Watch',
  [STATUS.ACT_NOW]: 'Act now',
  [STATUS.REFUSE]:  'Paused',
};

const STATUS_KEY = {
  [STATUS.OK]:      'ok',
  [STATUS.WATCH]:   'watch',
  [STATUS.ACT_NOW]: 'act',
  [STATUS.REFUSE]:  'paused',
};

// ─── mount ────────────────────────────────────────────────────────────────────
export function mount(container) {
  container.innerHTML = _template();
  const root = container.querySelector('.personal');
  const dialog = container.querySelector('#how-sure');
  let last = null;   // latest snapshot, so clicks act on state, not button text

  const onClick = e => {
    if (e.target.closest('[data-action="primary"]')) {
      if (!last) return;
      if (_isSetup(last.latest)) {
        toast('Baseline capture starts from the device. Coming with the hookup.');
      } else if (last.onBreak) {
        endBreak();
      } else {
        startBreak(last.latest.status === STATUS.ACT_NOW ? SCHEDULE.actBreakMin : SCHEDULE.breakMin);
      }
      return;
    }
    if (e.target.closest('[data-action="drank"]')) {
      recordDrink();
      toast(`Logged. Next ${SCHEDULE.waterMl} ml in ${SCHEDULE.waterEveryMin} min.`);
      return;
    }
    if (e.target.closest('[data-action="how-sure"]')) {
      e.preventDefault();
      if (dialog.showModal) dialog.showModal(); else dialog.setAttribute('open', '');
      return;
    }
    if (e.target.closest('[data-action="close-dialog"]')) {
      dialog.close ? dialog.close() : dialog.removeAttribute('open');
    }
  };
  root.addEventListener('click', onClick);

  const unsub = subscribe(data => { last = data; _render(root, data); });
  return () => {
    unsub();
    root.removeEventListener('click', onClick);
    if (dialog.open && dialog.close) dialog.close();
  };
}

function _isSetup(latest) {
  // Setup only while the temperature itself says OK: never hide Watch / Act now / Paused.
  return latest.flags !== null && (latest.flags & 0x20) !== 0 && latest.status === STATUS.OK;
}

// ─── render ───────────────────────────────────────────────────────────────────
function _render(root, data) {
  const { latest, history, session, onBreak, breakStartMs, breakTargetMin, now } = data;
  const { status, ctEst, ctLo, ctHi, hr, skinC, flags, confidence } = latest;

  const setup  = _isSetup(latest);
  const paused = status === STATUS.REFUSE;
  const statusKey = setup ? 'baseline' : (STATUS_KEY[status] ?? 'paused');

  ['ok', 'watch', 'act', 'paused', 'baseline'].forEach(k => root.classList.remove('status--' + k));
  root.classList.add('status--' + statusKey);

  // ── hero ──
  _set(root, 'name', WEARER_NAME);
  _set(root, 'mode', data.simulating ? 'Demo' : 'Live');
  const elapsedMin = session.startMs !== null ? Math.max(0, (now - session.startMs) / MIN) : null;
  const workMin    = session.workStartMs !== null ? Math.max(0, (now - session.workStartMs) / MIN) : null;
  _set(root, 'elapsed', elapsedMin === null ? '—' : `${Math.floor(elapsedMin)} min`);
  _set(root, 'label', LABELS[status] ?? 'Paused');

  const tag = root.querySelector('[data-field="tag"]');
  const noBaseline = flags !== null && (flags & 0x20) !== 0;
  if (noBaseline)              { tag.textContent = 'No baseline yet'; tag.hidden = false; }
  else if (confidence === 'low' && !paused) { tag.textContent = 'Low confidence'; tag.hidden = false; }
  else                         { tag.hidden = true; }

  root.querySelector('[data-when="number"]').hidden = paused;
  root.querySelector('[data-when="paused"]').hidden = !paused;

  const trend  = trendRate(history, now);          // 10-min rate, shown on screen
  const recent = trendRate(history, now, 4, 2);    // last few minutes: still rising?
  if (!paused && ctEst !== null) {
    const shown = round1(ctEst);
    _set(root, 'temp', shown.toFixed(1));

    const range = root.querySelector('[data-field="range"]');
    const haveRange = Number.isFinite(ctLo) && Number.isFinite(ctHi);
    if (haveRange) {
      _set(root, 'half', ((ctHi - ctLo) / 2).toFixed(1));
      _set(root, 'lo',   round1(ctLo).toFixed(1));
      _set(root, 'hi',   round1(ctHi).toFixed(1));
      range.style.setProperty('--lo', Math.max(36, ctLo));
      range.style.setProperty('--hi', Math.min(40, ctHi));
    } else {
      // No made-up ±: say we don't have it
      _set(root, 'half', '—'); _set(root, 'lo', '—'); _set(root, 'hi', '—');
    }
    root.querySelector('.range__band').hidden = !haveRange;
    range.style.setProperty('--est', Math.min(40, Math.max(36, ctEst)));

    _set(root, 'trend', formatTrend(trend));
    _set(root, 'rise', session.startCt !== null
      ? _signed(round1(ctEst) - round1(session.startCt)) + '°' : '—');
  }
  _set(root, 'reason', _pauseReason(latest));

  // ── plan ──
  _set(root, 'planTitle', setup ? 'Setting up' : 'Your plan');
  _set(root, 'action', setup
    ? `Sit still for ${SETUP_MIN} minutes so Ember can learn your resting heart rate.`
    : recommendedAction(status));

  _renderForecast(root, { status, setup, paused, ctEst, trend, recent, workMin, session, now });
  _renderBreak(root, data, { status, setup, paused, onBreak, breakStartMs, breakTargetMin, now });
  _renderWater(root, data, { status, setup, now });

  _set(root, 'btn',
    setup                       ? 'Capture baseline' :
    onBreak                     ? 'End my break' :
    status === STATUS.ACT_NOW   ? 'I am stopping' :
                                  'Start my break');

  // ── weather (real only; hidden when it didn't load) ──
  const w = data.weather;
  const weatherEl = root.querySelector('[data-field="weather"]');
  if (w && Number.isFinite(w.tempC) && Number.isFinite(w.humidity)) {
    weatherEl.textContent = `Here now: air ${Math.round(w.tempC)}°C · humidity ${Math.round(w.humidity)}%`;
    weatherEl.hidden = false;
  } else {
    weatherEl.hidden = true;
  }

  // ── vitals + chart ──
  _set(root, 'hr',      hr      ? `${Math.round(hr)}` : '—');
  _set(root, 'motion',  latest.actRms != null ? (latest.actRms > 0.35 ? 'moving' : 'still') : '—');
  _set(root, 'skinNow', skinC   ? skinC.toFixed(1) : '—');
  _drawChart(root, history, now);
}

function _renderForecast(root, { status, setup, paused, ctEst, trend, recent, workMin, session, now }) {
  // Forecast only while rising over 10 min AND over the last few minutes,
  // so a peak that has turned over isn't reported as still climbing.
  const stillRising = !!recent && recent.ratePer10 >= 0.05;
  const A = fmtC(THRESHOLDS.ACT_NOW_C);
  let main, note;
  if (setup) {
    const left = session.setupStartMs !== null
      ? Math.max(1, Math.ceil(SETUP_MIN - (now - session.setupStartMs) / MIN)) : SETUP_MIN;
    main = `About ${left} min left in setup`;
    note = 'Forecasts start once Ember knows your baseline.';
  } else if (paused) {
    main = 'Forecast paused';
    note = 'Forecasts restart when the sensors agree again.';
  } else if (status === STATUS.ACT_NOW) {
    main = stillRising ? `Over ${A} and still rising` : `Over ${A}`;
    note = `Rest until Ember shows Watch or OK, at least ${SCHEDULE.actBreakMin} min.`;
  } else if (workMin === null || workMin < FORECAST_MIN_DATA || !trend) {
    main = `Forecast starts after ${FORECAST_MIN_DATA} minutes`;
    note = 'Ember needs a few minutes of your pace first.';
  } else {
    const r = stillRising ? forecastRange(ctEst, trend.ratePer10) : null;
    if (r) {
      main = `Could reach ${A} ${formatRange(r)}`;
      note = 'If you keep this pace. A break now resets the clock.';
    } else {
      main = `Not expected to reach ${A} in the next 30 min`;
      note = 'At your current pace, with today\'s heat.';
    }
  }
  _set(root, 'forecast', main);
  _set(root, 'forecastNote', note);
}

function _renderBreak(root, data, { status, setup, onBreak, breakStartMs, breakTargetMin, now }) {
  let label = 'Next break', value, detail, urgent = false;
  if (onBreak) {
    const done = Math.max(0, Math.floor((now - breakStartMs) / MIN));
    const left = breakTargetMin - done;
    label  = 'On break';
    value  = `${done} min`;
    detail = left > 0 ? `of ${breakTargetMin} · ${left} min left` : `${breakTargetMin} min done · end when ready`;
  } else if (setup) {
    value = 'After setup'; detail = 'Plan built from your pace';
  } else if (status === STATUS.ACT_NOW) {
    value = 'Stop now'; detail = `Shade or AC · ${SCHEDULE.actBreakMin}+ min`; urgent = true;
  } else if (status === STATUS.WATCH) {
    value = 'Now'; detail = `${SCHEDULE.breakMin} min in shade`; urgent = true;
  } else {
    const from = data.lastBreakEndMs ?? data.session.workStartMs ?? data.session.startMs ?? now;
    const mins = Math.ceil(SCHEDULE.workMin - (now - from) / MIN);
    value  = mins <= 0 ? 'Now' : `In ${mins} min`;
    urgent = mins <= 0;
    detail = `${SCHEDULE.breakMin} min in shade · ${SCHEDULE.workMin} on, ${SCHEDULE.breakMin} off`;
  }
  _set(root, 'breakLabel', label);
  _set(root, 'breakWhen', value);
  _set(root, 'breakDetail', detail);
  root.querySelector('[data-field="breakWhen"]').classList.toggle('is-urgent', urgent);
}

function _renderWater(root, data, { status, setup, now }) {
  const since = data.lastDrinkMs !== null ? (now - data.lastDrinkMs) / MIN : null;
  const lastText = since === null ? null
    : since < 1 ? 'last drink just now' : `last drink ${Math.floor(since)} min ago`;
  let value, detail, urgent = false;
  if (setup) {
    value = 'Drink before you start'; detail = 'About 500 ml';
  } else if (status === STATUS.ACT_NOW) {
    value = 'Now'; detail = '500 ml, in sips'; urgent = true;
    if (lastText) detail += ` · ${lastText}`;
  } else {
    const every = status === STATUS.WATCH ? SCHEDULE.watchWaterMin : SCHEDULE.waterEveryMin;
    const from  = data.lastDrinkMs ?? (status === STATUS.WATCH ? null : (data.session.workStartMs ?? data.session.startMs));
    const mins  = from === null ? 0 : Math.ceil(every - (now - from) / MIN);
    value  = mins <= 0 ? 'Now' : `In ${mins} min`;
    urgent = mins <= 0;
    detail = lastText ? `${SCHEDULE.waterMl} ml · ${lastText}`
      : status === STATUS.WATCH ? `${SCHEDULE.waterMl} ml · no drink logged yet`
      : `${SCHEDULE.waterMl} ml every ${SCHEDULE.waterEveryMin} min`;
  }
  _set(root, 'water', value);
  _set(root, 'waterDetail', detail);
  root.querySelector('[data-field="water"]').classList.toggle('is-urgent', urgent);
}

// ─── SVG chart (pure, no Chart.js) ───────────────────────────────────────────
// Fixed 30-minute window ending now; one point per minute.
function _drawChart(root, history, now) {
  const W = 310, H = 86;
  const pts = history.filter(h => h.t >= now - CHART_WINDOW_MIN * MIN);
  const collecting = pts.filter(h => h.ctEst != null).length < 3;
  root.querySelector('[data-field="chartEmpty"]').hidden = !collecting;
  root.querySelector('[data-field="chartSvg"]').style.visibility = collecting ? 'hidden' : '';
  if (collecting) return;

  // Single shared scale covering both core and skin, so skin plots below core.
  const SCALE_LO = 33.0, SCALE_HI = 40.0;
  const y = v => {
    const t = Math.min(1, Math.max(0, (v - SCALE_LO) / (SCALE_HI - SCALE_LO)));
    return ((H - 4) - t * (H - 8)).toFixed(1);
  };
  const x = t => (W - ((now - t) / (CHART_WINDOW_MIN * MIN)) * W).toFixed(1);
  const line = key => pts.filter(h => h[key] != null).map(h => `${x(h.t)},${y(h[key])}`).join(' ');

  const hi = pts.filter(h => h.ctHi != null).map(h => `${x(h.t)},${y(h.ctHi)}`);
  const lo = pts.filter(h => h.ctLo != null).map(h => `${x(h.t)},${y(h.ctLo)}`).reverse();

  root.querySelector('[data-field="chartBand"]').setAttribute('points', [...hi, ...lo].join(' '));
  root.querySelector('[data-field="chartCore"]').setAttribute('points', line('ctEst'));
  root.querySelector('[data-field="chartSkin"]').setAttribute('points', line('skinC'));
}

// ─── helpers ──────────────────────────────────────────────────────────────────
function _set(root, field, value) {
  root.querySelectorAll(`[data-field="${field}"]`).forEach(el => {
    el.textContent = value ?? '';
  });
}

function _signed(n) {
  const v = Math.abs(n) < 0.05 ? 0 : n;
  return (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(1);
}

function _pauseReason(latest) {
  const flags = latest.flags ?? 0;
  if (flags & 0x08) return 'Heart rate signal lost. Check the strap is wet and snug.';
  if (flags & 0x01) return 'Your heart rate is up, but your body doesn\'t look like it\'s heating up.';
  return 'Your sensors disagree right now.';
}

function _confRows() {
  const edges = CONF_EDGES.map(e => round1(e).toFixed(1));
  return CONF_HALF.map((h, i) => {
    const band = i === 0 ? `Under ${edges[0]}°C`
      : i === CONF_HALF.length - 1 ? `${edges[i - 1]}°C and up`
      : `${edges[i - 1]}–${edges[i]}°C`;
    return `<tr><td>${band}</td><td>± ${h.toFixed(1)}°C</td></tr>`;
  }).join('');
}

// ─── template ─────────────────────────────────────────────────────────────────
function _template() {
  return /* html */`
<main class="personal status--ok" aria-label="Personal view">
  <section class="hero" aria-live="polite">
    <div class="hero__top">
      <span data-field="name">—</span>
      <span class="live"><span data-field="mode">Live</span> · <span data-field="elapsed">—</span></span>
    </div>
    <div class="hero__status">
      <span class="hero__label" data-field="label">OK</span>
      <span class="hero__tag" data-field="tag" hidden></span>
    </div>

    <div data-when="number">
      <div class="reading">
        <div class="reading__temp" data-field="temp">—</div>
        <div class="reading__unit"><span>°C</span><span>± <span data-field="half">—</span></span></div>
        <div class="reading__trend">
          <strong data-field="trend">—</strong>
          <span><span data-field="rise">—</span> since start</span>
        </div>
      </div>
      <div class="reading__caption">Estimated core temp · likely <span data-field="lo">—</span>–<span data-field="hi">—</span>°C</div>
      <div class="range" data-field="range" style="--lo: 37.3; --hi: 37.8; --est: 37.5; --watch: ${THRESHOLDS.WATCH_C}; --act: ${THRESHOLDS.ACT_NOW_C}" role="img"
           aria-label="Likely range on a scale from 36 to 40 degrees, with markers at ${fmtC(THRESHOLDS.WATCH_C)} and ${fmtC(THRESHOLDS.ACT_NOW_C)}">
        <div class="range__track"></div>
        <div class="range__band"></div>
        <div class="range__mark range__mark--watch"></div>
        <div class="range__mark range__mark--act"></div>
        <div class="range__dot"></div>
        <div class="range__labels">
          <span>36°</span>
          <span>Watch ${fmtC(THRESHOLDS.WATCH_C)}</span>
          <span>Act ${fmtC(THRESHOLDS.ACT_NOW_C)}</span>
          <span>40°</span>
        </div>
      </div>
    </div>

    <div class="paused-msg" data-when="paused" hidden>
      <h2>Can't estimate right now</h2>
      <strong data-field="reason">Your sensors disagree right now.</strong>
      <p>Ember won't show a number it can't stand behind. It will come back on its own.</p>
    </div>
  </section>

  <div class="personal__body">
    <p class="personal__weather" data-field="weather" hidden></p>
    <section class="card plan" aria-labelledby="plan-title">
      <div class="plan__head">
        <span class="label" id="plan-title" data-field="planTitle">Your plan</span>
        <span>Updated just now</span>
      </div>
      <p class="plan__action" data-field="action">—</p>
      <div class="forecast">
        <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17l6-6 4 4 8-8"/><path d="M14 7h7v7"/></svg>
        <div>
          <strong data-field="forecast">—</strong>
          <span data-field="forecastNote"></span>
        </div>
      </div>
      <div class="plan__grid">
        <div class="mini">
          <div class="mini__label">
            <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2"/><path d="M9 2h6"/></svg>
            <span data-field="breakLabel">Next break</span>
          </div>
          <div class="mini__value" data-field="breakWhen">—</div>
          <div class="mini__note" data-field="breakDetail"></div>
        </div>
        <div class="mini">
          <div class="mini__label">
            <svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/></svg>
            Water
          </div>
          <div class="mini__value" data-field="water">—</div>
          <div class="mini__note" data-field="waterDetail"></div>
        </div>
      </div>
      <div class="plan__buttons">
        <button type="button" class="btn btn--primary" data-field="btn" data-action="primary">Start my break</button>
        <button type="button" class="btn btn--secondary" data-action="drank">I drank</button>
      </div>
    </section>

    <section class="card trend-card" aria-label="Last 30 minutes">
      <div class="trend-card__head">
        <strong>Last 30 min</strong>
        <span>HR <span data-field="hr">—</span> bpm · <span data-field="motion">—</span></span>
      </div>
      <div class="chart-wrap">
      <p class="chart-empty" data-field="chartEmpty">Collecting data…</p>
      <svg data-field="chartSvg" role="img" aria-label="Core estimate and its range compared with skin temperature" viewBox="0 0 310 86" preserveAspectRatio="none">
        <polygon data-field="chartBand" fill="#0B1B2B" fill-opacity="0.08" points=""/>
        <polyline data-field="chartCore" fill="none" stroke="#0B1B2B" stroke-width="2.25" stroke-linecap="round" stroke-linejoin="round" points=""/>
        <polyline data-field="chartSkin" fill="none" stroke="#0B5CAD" stroke-width="2" stroke-dasharray="5 4" stroke-linecap="round" points=""/>
      </svg>
      </div>
      <div class="legend">
        <span><svg aria-hidden="true" width="16" height="4"><line x1="0" y1="2" x2="16" y2="2" stroke="#0B1B2B" stroke-width="2.5"/></svg>Core estimate + range</span>
        <span><svg aria-hidden="true" width="16" height="4"><line x1="0" y1="2" x2="16" y2="2" stroke="#0B5CAD" stroke-width="2" stroke-dasharray="4 3"/></svg><span>Skin <span data-field="skinNow">—</span>°C</span></span>
      </div>
    </section>

    <footer class="personal__foot">
      <span>This is an estimate, not a medical reading. Heart rate and history stay on your device.</span>
      <a href="#how-sure" data-action="how-sure">How sure is Ember?</a>
    </footer>
  </div>

  <dialog id="how-sure" class="sheet" aria-labelledby="how-sure-title">
    <div class="sheet__head">
      <h2 id="how-sure-title">How sure is Ember?</h2>
      <button type="button" class="btn btn--secondary btn-sm" data-action="close-dialog">Close</button>
    </div>
    <p>The ± is a 90% range: it is sized so your real core temperature should fall inside it about 9 times out of 10. It comes from comparing Ember's estimate with a core thermometer in 37 people, not from the filter's own guess, so it is honest about how wrong Ember can be.</p>
    <p><strong>Measured coverage</strong>: tested on 37 people it had never seen (PROSPIE V3, chest heart-rate straps, 14,041 minutes), the true value was inside Ember's range <strong>${(CONF_MEASURED_COV * 100).toFixed(1)}%</strong> of the time. The filter's own "90%" range held only <strong>34%</strong> of the time.</p>
    <p>It holds less well when you are very hot. When true core was ${fmtC(THRESHOLDS.ACT_NOW_C)} or more, the range held about 2 times in 3, because the estimate lags behind a fast rise. That is why Watch starts at ${fmtC(THRESHOLDS.WATCH_C)}.</p>
    <p>When the sensors disagree, Ember pauses the number. From ${fmtC(THRESHOLDS.WATCH_C)} up it always shows the number, marked Low confidence.</p>
    <p>The ± depends on the estimate, from ± ${Math.min(...CONF_HALF).toFixed(1)}° to ± ${Math.max(...CONF_HALF).toFixed(1)}°:</p>
    <table class="sheet__table">
      <thead><tr><th>Estimate</th><th>Range</th></tr></thead>
      <tbody>${_confRows()}</tbody>
    </table>
    ${CONF_SYNTHETIC ? '<p class="sheet__note">Placeholder: these widths come from synthetic test data. They will be replaced with the real calibration before the demo.</p>' : ''}
  </dialog>
</main>
`;
}
