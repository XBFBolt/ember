/**
 * SupervisorView.js — workplace supervisor view (static demo).
 *
 * Renders once with hardcoded data to sell the vision.
 * No datastore subscription — only PersonalView is live.
 */

import { THRESHOLDS, fmtC } from '../lib/datastore.js';
import { toast } from '../lib/toast.js';

const EVENTS = [
  {
    time: '11:18 AM', type: 'Overheating alert', who: 'D. Reyes', open: true,
    detail: `Estimated core temp passed ${fmtC(THRESHOLDS.ACT_NOW_C)}C and was still rising. D. Reyes was told on their phone to stop and rest in the shade.`,
  },
  {
    time: '10:42 AM', type: 'Overheating alert', who: 'K. Lin', open: false,
    detail: 'Worker took a 10-minute rest break after their phone warned them.',
    resolved: 'Back to work 10:55 AM.',
  },
  {
    time: '9:30 AM', type: 'Estimate unavailable', who: 'P. Mendes', open: false,
    detail: 'Heart rate signal lost for 12 minutes, so EMB.R could not estimate and no alerts could fire for this worker.',
    resolved: 'Reconnected 9:44 AM.',
  },
];

const CREW = [
  { name: 'D. Reyes',    role: 'Ironworker',  status: 'act', label: 'Alert open' },
  { name: 'K. Lin',      role: 'Laborer',     status: 'ok',  label: 'Break taken' },
  { name: 'P. Mendes',   role: 'Operator',    status: 'ok',  label: 'Reconnected' },
  { name: 'A. Costa',    role: 'Carpenter',   status: null,  label: 'No events' },
  { name: 'J. Baptiste', role: 'Laborer',     status: null,  label: 'No events' },
  { name: 'M. Silva',    role: 'Electrician', status: null,  label: 'No events' },
  { name: 'T. Nguyen',   role: 'Carpenter',   status: null,  label: 'No events' },
  { name: 'R. Doyle',    role: 'Foreman',     status: null,  label: 'No events' },
];

export function mount(container) {
  container.innerHTML = _render();
  // One delegated listener on the container, removed on unmount.
  // Re-rendering replaces the markup but keeps this listener.
  const onClick = e => {
    const ack = e.target.closest('[data-ack]');
    if (ack) {
      const idx = parseInt(ack.dataset.ack, 10);
      EVENTS[idx].open     = false;
      EVENTS[idx].resolved = 'You checked in. Worker confirmed OK.';
      const who = CREW.find(c => c.name === EVENTS[idx].who);
      if (who) { who.status = 'ok'; who.label = 'Checked in'; }
      container.innerHTML = _render();
      return;
    }
    const call = e.target.closest('[data-call]');
    if (call) toast(`Calling ${call.dataset.call}…`);
  };
  container.addEventListener('click', onClick);
  return () => container.removeEventListener('click', onClick);
}

function _render() {
  const open     = EVENTS.filter(e => e.open).length;
  const resolved = EVENTS.filter(e => !e.open).length;

  const tiles = [
    open > 0
      ? `<div class="tile status--act"><span class="label">Open events</span><span class="tile__num">${open}</span><span class="tile__note">Need a check-in</span></div>`
      : `<div class="tile status--ok"><span class="label">Open events</span><span class="tile__num">0</span><span class="tile__note">All clear</span></div>`,
    `<div class="tile tile--plain"><span class="label">Resolved today</span><span class="tile__num">${resolved}</span><span class="tile__note">Breaks taken, signals restored</span></div>`,
    `<div class="tile tile--plain"><span class="label">Crew on shift</span><span class="tile__num">${CREW.length}</span><span class="tile__note">All straps connected</span></div>`,
  ].join('');

  const eventCards = EVENTS.map((e, i) => {
    const statusKey = e.open ? 'act' : 'ok';
    return `<article class="event status--${statusKey}">
      <div class="strip">${e.open ? 'Open · check in now' : 'Resolved'}</div>
      <div class="event__body">
        <div class="event__title">
          <time>${_esc(e.time)}</time>
          <strong>${_esc(e.type)} · ${_esc(e.who)}</strong>
        </div>
        <p>${_esc(e.detail)}</p>
        ${e.open
          ? `<div class="btn-row">
               <button type="button" class="btn btn--primary" style="height:44px;font-size:14px" data-ack="${i}">I checked in, worker is OK</button>
               <button type="button" class="btn btn--outline" data-call="${_esc(e.who)}">Call worker</button>
             </div>`
          : `<div class="event__resolved">${_esc(e.resolved)}</div>`
        }
      </div>
    </article>`;
  }).join('');

  const crewItems = CREW.map(c => {
    const pillClass = c.status ? `pill status--${c.status}` : 'pill pill--none';
    return `<li>
      <span><strong>${_esc(c.name)}</strong><small>${_esc(c.role)}</small></span>
      <span class="${pillClass}">${_esc(c.label)}</span>
    </li>`;
  }).join('');

  return /* html */`
<div class="page page--supervisor">
  <div class="page__head">
    <div>
      <p class="page__sub">Example crew · Seaport site · Crew B · Shift 7:00 AM to 3:30 PM</p>
      <h1>Heat safety events</h1>
    </div>
    <div class="chips">
      <span class="chip">Air 30°C</span>
      <span class="chip chip--watch">Heat index 34°C · High</span>
    </div>
  </div>

  <section class="card notice">
    <div class="notice__icon">
      <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/></svg>
    </div>
    <div>
      <h2>You see safety events only</h2>
      <p>Temperatures, heart rate and forecasts stay private to each worker. You're told when someone needs help, not how their body is doing minute to minute.</p>
    </div>
  </section>

  <div class="tiles">${tiles}</div>

  <div class="split">
    <section class="split__main" aria-labelledby="events-title">
      <h2 id="events-title" style="font-size:17px">Events</h2>
      <div style="display:flex;flex-direction:column;gap:12px">${eventCards}</div>
    </section>

    <aside class="split__side">
      <section class="card card--dark breakplan" aria-labelledby="cbp-title">
        <div class="breakplan__head">
          <h2 id="cbp-title">Crew break plan</h2>
          <span>45 on, 15 off</span>
        </div>
        <div class="breakplan__big"><strong>11:45</strong><span>next crew break · in 12 min</span></div>
        <p>Set from today's heat index. Water and shade for everyone, about 500 ml per hour each. EMB.R suggests the schedule; you can change it.</p>
      </section>

      <section class="card" aria-labelledby="crew-title">
        <h2 id="crew-title" style="margin-bottom:6px">Crew</h2>
        <ul class="plain crew">${crewItems}</ul>
      </section>

      <section class="card whosees" aria-labelledby="ws-title">
        <h2 id="ws-title">Who sees what</h2>
        <div class="shared">
          <span class="label">Shared with you</span>
          <ul class="plain">
            <li><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0B5CAD" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"/></svg>Overheating alerts</li>
            <li><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0B5CAD" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"/></svg>Rest breaks taken</li>
            <li><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#0B5CAD" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12l5 5L20 7"/></svg>Estimate unavailable</li>
          </ul>
        </div>
        <div class="private">
          <span class="label">Only the worker sees</span>
          <ul class="plain">
            <li><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>Core temp estimate and range</li>
            <li><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>Heart rate and skin temp</li>
            <li><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>Motion and other sensor readings</li>
            <li><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>Full history and location</li>
          </ul>
        </div>
      </section>
    </aside>
  </div>
</div>`;
}

function _esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch])
  );
}
