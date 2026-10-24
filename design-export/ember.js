/* =========================================================
   Ember views: rendering + view switching.
   No framework. Sample data at the bottom shows the shapes
   each render function expects; swap it for live data.
   ========================================================= */

(function () {
  'use strict';

  // ------------------------------------------------ status rules
  // Firmware states (from ember_firmware.ino): 0 OK, 1 CAUTION, 2 REFUSE.
  // Flags: 0x20 = no baseline yet.
  const ALERT_C = 38.5; // Act now  (matches CT_ALERT_C in firmware)
  const WATCH_C = 38.0; // Watch

  /** Turn one firmware CSV row into a UI status key. */
  function statusFromRow(row) {
    if (row.state === 2) return 'paused';
    if (row.flags & 0x20) return 'baseline';
    if (row.ct_est >= ALERT_C) return 'act';
    if (row.ct_est >= WATCH_C) return 'watch';
    return 'ok';
  }

  /** Parse one line of the firmware's START log into an object.
   *  Columns: ms,hr,ct_est,ct_lo,ct_hi,kalman_half,skin_c,micro_c,
   *           micro_rh,evap_kpa,act_rms,step_hz,state,flags */
  function parseCsvLine(line) {
    const c = line.trim().split(',');
    if (c.length < 14 || isNaN(Number(c[0]))) return null;
    return {
      ms: +c[0], hr: +c[1], ct_est: +c[2], ct_lo: +c[3], ct_hi: +c[4],
      kalman_half: +c[5], skin_c: +c[6], micro_c: +c[7], micro_rh: +c[8],
      evap_kpa: +c[9], act_rms: +c[10], step_hz: +c[11],
      state: +c[12], flags: parseInt(c[13], 16)
    };
  }

  const LABELS = { baseline: 'Setting up', ok: 'OK', watch: 'Watch', act: 'Act now', paused: 'Paused' };
  const STATUS_CLASSES = ['status--baseline', 'status--ok', 'status--watch', 'status--act', 'status--paused'];

  function setStatusClass(el, key) {
    STATUS_CLASSES.forEach((c) => el.classList.remove(c));
    el.classList.add('status--' + key);
  }

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  }

  // ------------------------------------------------ personal view
  /** state: see SAMPLE_PERSONAL below for the full shape. */
  function renderPersonal(state) {
    const root = document.getElementById('view-personal');
    if (!root) return;
    setStatusClass(root, state.status);

    const set = (field, value) => {
      root.querySelectorAll('[data-field="' + field + '"]').forEach((el) => { el.textContent = value ?? ''; });
    };

    set('label', LABELS[state.status]);
    const tag = root.querySelector('[data-field="tag"]');
    tag.hidden = !state.tag;
    tag.textContent = state.tag || '';

    const paused = state.status === 'paused';
    root.querySelector('[data-when="number"]').hidden = paused;
    root.querySelector('[data-when="paused"]').hidden = !paused;

    if (!paused) {
      set('temp', state.ct.toFixed(1));
      set('half', state.half.toFixed(1));
      set('lo', (state.ct - state.half).toFixed(1));
      set('hi', (state.ct + state.half).toFixed(1));
      const range = root.querySelector('[data-field="range"]');
      range.style.setProperty('--lo', Math.max(36, state.ct - state.half));
      range.style.setProperty('--hi', Math.min(40, state.ct + state.half));
      range.style.setProperty('--est', state.ct);
    }

    ['name', 'elapsed', 'trend', 'rise', 'reason', 'action', 'forecast', 'forecastNote',
      'breakWhen', 'breakDetail', 'water', 'waterDetail', 'btn', 'hr', 'motion', 'skinNow']
      .forEach((f) => { if (f in state) set(f, state[f]); });

    root.querySelector('[data-field="breakWhen"]').classList.toggle('is-urgent', !!state.breakUrgent);
    root.querySelector('[data-field="water"]').classList.toggle('is-urgent', !!state.waterUrgent);

    if (state.chart) drawChart(root, state.chart);
  }

  /** chart: { core: [°C...], lo: [...], hi: [...], skin: [...] }, oldest first, over the last 30 min.
   *  Core and skin each get their own fixed scale (core 36.5–39.8, skin 31–36) so the
   *  direction of each line is honest and they share one small chart. */
  function drawChart(root, chart) {
    const W = 310, H = 86;
    const scale = (lo, hi) => (v) => {
      const t = Math.min(1, Math.max(0, (v - lo) / (hi - lo)));
      return (H - 4) - t * (H - 8);
    };
    const yCore = scale(36.5, 39.8), ySkin = scale(31, 36);
    const x = (i, n) => (n < 2 ? 0 : (i / (n - 1)) * W);
    const pts = (arr, y) => arr.map((v, i) => x(i, arr.length).toFixed(1) + ',' + y(v).toFixed(1)).join(' ');
    const band = chart.hi.map((v, i) => x(i, chart.hi.length).toFixed(1) + ',' + yCore(v).toFixed(1))
      .concat(chart.lo.map((v, i) => x(i, chart.lo.length).toFixed(1) + ',' + yCore(v).toFixed(1)).reverse()).join(' ');
    root.querySelector('[data-field="chartBand"]').setAttribute('points', band);
    root.querySelector('[data-field="chartCore"]').setAttribute('points', pts(chart.core, yCore));
    root.querySelector('[data-field="chartSkin"]').setAttribute('points', pts(chart.skin, ySkin));
  }

  // ------------------------------------------------ coach view
  const RISK_ORDER = { act: 0, paused: 1, watch: 2, ok: 3, baseline: 4 };

  function renderCoach(data) {
    const counts = { act: 0, watch: 0, ok: 0, paused: 0 };
    data.players.forEach((p) => { if (p.status in counts) counts[p.status]++; });

    document.getElementById('coach-tiles').innerHTML = [
      tile('act', 'Act now', counts.act, 'Estimate at or over 38.5°C'),
      tile('watch', 'Watch', counts.watch, 'Estimate 38.0°C or higher'),
      tile('ok', 'OK', counts.ok, 'Estimate under 38.0°C'),
      tile('paused', 'Cannot estimate', counts.paused, 'Signals disagree · check in person')
    ].join('');

    const sorted = data.players.slice().sort((a, b) => (RISK_ORDER[a.status] - RISK_ORDER[b.status]) || ((b.ct || 0) - (a.ct || 0)));
    document.getElementById('coach-players').innerHTML = sorted.map(playerCard).join('');

    document.getElementById('coach-log').innerHTML = data.log
      .map((l) => '<li><time>' + esc(l.time) + '</time><span>' + esc(l.text) + '</span></li>').join('');
  }

  function tile(status, label, num, note) {
    return '<div class="tile status--' + status + '"><span class="label">' + esc(label) + '</span>' +
      '<span class="tile__num">' + esc(num) + '</span><span class="tile__note">' + esc(note) + '</span></div>';
  }

  function playerCard(p) {
    const temp = p.status === 'paused'
      ? '<div class="player__none">No number shown</div>'
      : '<div class="player__temp"><strong>' + p.ct.toFixed(1) + '</strong><span>± ' + p.half.toFixed(1) + '°C</span></div>';
    return '<article class="player status--' + p.status + '">' +
      '<div class="strip">' + esc(p.status === 'paused' ? 'Cannot estimate' : LABELS[p.status]) + '</div>' +
      '<div class="player__body">' +
        '<div class="player__name"><span>' + esc(p.name) + ' <small>#' + esc(p.num) + '</small></span>' +
          (p.control ? '<span class="tag">Control</span>' : '') + '</div>' +
        temp +
        '<div class="player__foot"><span>' + esc(p.trend) + '</span><span>' + esc(p.note) + '</span></div>' +
      '</div></article>';
  }

  // ------------------------------------------------ supervisor view
  function renderSupervisor(data) {
    const open = data.events.filter((e) => e.open).length;
    const resolved = data.events.length - open;
    document.getElementById('sup-tiles').innerHTML = [
      tile(open ? 'act' : 'ok', 'Open events', open, 'Need a check-in'),
      '<div class="tile tile--plain"><span class="label">Resolved today</span><span class="tile__num">' + resolved +
        '</span><span class="tile__note">Breaks taken, signals restored</span></div>',
      '<div class="tile tile--plain"><span class="label">Crew on shift</span><span class="tile__num">' + data.crew.length +
        '</span><span class="tile__note">All straps connected</span></div>'
    ].join('');

    document.getElementById('sup-events').innerHTML = data.events.map((e, i) =>
      '<article class="event status--' + (e.open ? 'act' : 'ok') + '">' +
        '<div class="strip">' + (e.open ? 'Open · check in now' : 'Resolved') + '</div>' +
        '<div class="event__body">' +
          '<div class="event__title"><time>' + esc(e.time) + '</time><strong>' + esc(e.type) + ' · ' + esc(e.who) + '</strong></div>' +
          '<p>' + esc(e.detail) + '</p>' +
          (e.open
            ? '<div class="btn-row"><button type="button" class="btn btn--primary" style="height:44px;font-size:14px" data-ack="' + i + '">I checked in, worker is OK</button>' +
              '<button type="button" class="btn btn--outline">Call worker</button></div>'
            : '<div class="event__resolved">' + esc(e.resolved) + '</div>') +
        '</div></article>').join('');

    document.getElementById('sup-crew').innerHTML = data.crew.map((c) =>
      '<li><span><strong>' + esc(c.name) + '</strong><small>' + esc(c.role) + '</small></span>' +
      '<span class="pill ' + (c.status ? 'status--' + c.status : 'pill--none') + '">' + esc(c.label) + '</span></li>').join('');

    document.querySelectorAll('[data-ack]').forEach((btn) => btn.addEventListener('click', () => {
      const e = data.events[+btn.dataset.ack];
      e.open = false;
      e.resolved = 'You checked in. Worker confirmed OK.';
      data.crew.forEach((c) => { if (c.name === e.who) { c.status = 'ok'; c.label = 'Checked in'; } });
      renderSupervisor(data);
    }));
  }

  // ------------------------------------------------ view switching
  function showView(view) {
    document.querySelectorAll('[data-view]').forEach((el) => { el.hidden = el.dataset.view !== view; });
    document.querySelectorAll('[data-view-link]').forEach((a) => {
      if (a.dataset.viewLink === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
  }

  document.querySelectorAll('[data-view-link]').forEach((a) => a.addEventListener('click', (ev) => {
    ev.preventDefault();
    const view = a.dataset.viewLink;
    const url = new URL(location.href);
    url.searchParams.set('view', view);
    history.replaceState(null, '', url);
    showView(view);
  }));

  // ------------------------------------------------ sample data
  const ramp = (a, b, n) => Array.from({ length: n }, (_, i) => a + (b - a) * (i / (n - 1)));

  const SAMPLE_PERSONAL = {
    baseline: {
      status: 'baseline', tag: 'No baseline yet', ct: 37.1, half: 0.6, trend: '—', rise: '—',
      action: 'Sit still for 5 minutes so Ember can learn your resting heart rate.',
      forecast: '3:12 left in setup', forecastNote: 'Forecasts start once Ember knows your baseline.',
      breakWhen: 'After setup', breakDetail: 'Plan built from your pace', water: 'Drink before you start', waterDetail: 'About 500 ml',
      btn: 'Skip (less accurate)', hr: '66', motion: 'still', skinNow: '34.1',
      chart: { core: ramp(37.1, 37.1, 10), lo: ramp(36.5, 36.5, 10), hi: ramp(37.7, 37.7, 10), skin: ramp(34.1, 34.1, 10) }
    },
    ok: {
      status: 'ok', ct: 37.6, half: 0.6, trend: '→ Steady', rise: '+0.5°',
      action: 'Keep going. You are on a safe pace.',
      forecast: 'Not expected to reach 38.5° this session', forecastNote: 'At your current pace, with today’s heat.',
      breakWhen: 'In 14 min', breakDetail: '5 min in shade · 20 on, 5 off', water: 'In 6 min', waterDetail: '250 ml every 15 min',
      btn: 'Got it', hr: '128', motion: 'moving', skinNow: '34.0',
      chart: { core: ramp(37.2, 37.6, 30), lo: ramp(36.6, 37.0, 30), hi: ramp(37.8, 38.2, 30), skin: ramp(34.0, 34.0, 30) }
    },
    watch: {
      status: 'watch', ct: 38.1, half: 0.7, trend: '↑ 0.3° / 10 min', rise: '+1.0°',
      action: 'You are heating up. Take your break now, not in 10 minutes.',
      forecast: 'Could reach 38.5° in about 10–25 min', forecastNote: 'If you keep this pace. A break now resets the clock.',
      breakWhen: 'Now', breakUrgent: true, breakDetail: '5 min in shade', water: 'Now', waterUrgent: true, waterDetail: '250 ml · last drink 22 min ago',
      btn: 'Start my break', hr: '152', motion: 'moving', skinNow: '33.8',
      chart: { core: ramp(37.2, 38.1, 30), lo: ramp(36.6, 37.4, 30), hi: ramp(37.8, 38.8, 30), skin: [33.6, 33.4, 33.3, 33.3, 33.4, 33.5, 33.6, 33.7, 33.8, 33.8] }
    },
    act: {
      status: 'act', ct: 38.7, half: 0.9, trend: '↑ 0.4° / 10 min', rise: '+1.6°',
      action: 'You are too hot. Stop now and tell your coach.',
      forecast: 'Over 38.5° and still rising', forecastNote: 'Rest until Ember shows Watch or OK, at least 15 min.',
      breakWhen: 'Stop now', breakUrgent: true, breakDetail: 'Shade or AC · 15+ min', water: 'Now', waterUrgent: true, waterDetail: '500 ml, in sips',
      btn: 'I am stopping', hr: '171', motion: 'moving', skinNow: '35.4',
      chart: { core: ramp(37.4, 38.7, 30), lo: ramp(36.8, 37.8, 30), hi: ramp(38.0, 39.6, 30), skin: [33.6, 33.4, 33.5, 33.8, 34.2, 34.6, 35.0, 35.4] }
    },
    paused: {
      status: 'paused', reason: 'High heart rate while sitting still',
      action: 'Sit for a few minutes. Coffee or stairs can do this, and it will clear.',
      forecast: 'Forecast paused', forecastNote: 'Feeling dizzy or sick? Stop and tell someone.',
      breakWhen: 'As planned', breakDetail: '20 on, 5 off', water: 'In 4 min', waterDetail: '250 ml every 15 min',
      btn: 'Okay', hr: '104', motion: 'still', skinNow: '33.9',
      chart: { core: ramp(37.3, 37.3, 10), lo: ramp(36.7, 36.7, 10), hi: ramp(37.9, 37.9, 10), skin: ramp(33.9, 33.9, 10) }
    }
  };

  const SAMPLE_COACH = {
    players: [
      { name: 'J. Okafor', num: 22, status: 'act', ct: 38.8, half: 0.92, trend: '↑ 0.4° / 10 min', note: 'Rest 15+ min' },
      { name: 'T. Brooks', num: 54, status: 'act', ct: 38.6, half: 0.92, trend: '↑ 0.3° / 10 min', note: 'Rest 15+ min' },
      { name: 'S. Kim', num: 31, status: 'paused', trend: 'High HR, no motion', note: 'Check in person' },
      { name: 'M. Alvarez', num: 7, status: 'watch', ct: 38.2, half: 0.70, trend: '↑ 0.3° / 10 min', note: '38.5° in ~10–20 min' },
      { name: 'E. Vega', num: 60, status: 'watch', ct: 38.1, half: 0.70, trend: '↑ 0.4° / 10 min', note: '38.5° in ~10–20 min' },
      { name: 'D. Price', num: 88, status: 'watch', ct: 38.0, half: 0.68, trend: '↑ 0.2° / 10 min', note: '38.5° in ~15–30 min' },
      { name: 'A. Nwosu', num: 12, status: 'ok', ct: 37.8, half: 0.68, trend: '→ steady', note: 'Break with team' },
      { name: 'R. Patel', num: 3, status: 'ok', ct: 37.7, half: 0.62, trend: '↓ falling', note: 'Break with team' },
      { name: 'C. Moreau', num: 45, status: 'ok', ct: 37.6, half: 0.62, trend: '→ steady', note: 'Break with team' },
      { name: 'L. Grant', num: 19, status: 'ok', ct: 37.5, half: 0.62, trend: '→ steady', note: 'Break with team' },
      { name: 'B. Walsh', num: 9, status: 'ok', ct: 37.4, half: 0.62, trend: '→ steady', note: 'Break with team' },
      { name: 'H. Osei', num: 24, status: 'ok', ct: 37.2, half: 0.59, trend: '→ steady', note: 'Seated control', control: true }
    ],
    log: [
      { time: '4:44 PM', text: 'S. Kim: cannot estimate (high heart rate while still)' },
      { time: '4:42 PM', text: 'J. Okafor reached Act now (38.8 ± 0.9°C, rising)' },
      { time: '4:38 PM', text: 'T. Brooks reached Act now (38.6 ± 0.9°C)' },
      { time: '4:20 PM', text: 'Team water break, 5 min' },
      { time: '4:05 PM', text: 'Practice started · 12 baselines captured' }
    ]
  };

  const SAMPLE_SUPERVISOR = {
    events: [
      { time: '11:18 AM', type: 'Overheating alert', who: 'D. Reyes', open: true,
        detail: 'Estimated core temp passed 38.5°C and was still rising. D. Reyes was told on their phone to stop and rest in the shade.' },
      { time: '10:42 AM', type: 'Overheating alert', who: 'K. Lin', open: false,
        detail: 'Worker took a 10-minute rest break after their phone warned them.', resolved: 'Back to work 10:55 AM.' },
      { time: '9:30 AM', type: 'Estimate unavailable', who: 'P. Mendes', open: false,
        detail: 'Heart rate signal lost for 12 minutes, so Ember could not estimate and no alerts could fire for this worker.', resolved: 'Reconnected 9:44 AM.' }
    ],
    crew: [
      { name: 'D. Reyes', role: 'Ironworker', status: 'act', label: 'Alert open' },
      { name: 'K. Lin', role: 'Laborer', status: 'ok', label: 'Break taken' },
      { name: 'P. Mendes', role: 'Operator', status: 'ok', label: 'Reconnected' },
      { name: 'A. Costa', role: 'Carpenter', label: 'No events' },
      { name: 'J. Baptiste', role: 'Laborer', label: 'No events' },
      { name: 'M. Silva', role: 'Electrician', label: 'No events' },
      { name: 'T. Nguyen', role: 'Carpenter', label: 'No events' },
      { name: 'R. Doyle', role: 'Foreman', label: 'No events' }
    ]
  };

  // ------------------------------------------------ boot
  const params = new URLSearchParams(location.search);
  const view = ['personal', 'coach', 'supervisor'].includes(params.get('view')) ? params.get('view') : 'personal';
  const demoStatus = params.get('status') in SAMPLE_PERSONAL ? params.get('status') : 'watch';

  renderPersonal(Object.assign({ name: 'Maya Chen', elapsed: '42 min' }, SAMPLE_PERSONAL[demoStatus]));
  renderCoach(SAMPLE_COACH);
  renderSupervisor(SAMPLE_SUPERVISOR);
  showView(view);

  // Expose for your own code (live data, Web Serial, replay).
  window.Ember = { renderPersonal, renderCoach, renderSupervisor, statusFromRow, parseCsvLine, showView, SAMPLE_PERSONAL };
})();
