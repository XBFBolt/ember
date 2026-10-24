/**
 * datastore.js — in-memory only, zero persistence.
 *
 * All biometric data lives here and dies when the page closes.
 * No localStorage, no IndexedDB, no cookies, no server writes.
 *
 * Single source of truth for all three views.
 * Views subscribe with datastore.subscribe(callback).
 */

import { STATE, FLAG } from './frame.js';

// ─── thresholds (mirror firmware) ────────────────────────────────────────────
export const THRESHOLDS = {
  WATCH_C:          38.0,
  ACT_NOW_C:        38.5,
  EVAP_CRITICAL:    0.8,   // kPa — sweat cannot evaporate
  EVAP_AMPLE:       2.5,   // kPa — plenty of cooling capacity
  CT_MIN:           35.0,
  CT_MAX:           41.5,
};

/** Format a temperature for UI text, e.g. fmtC(38.5) → "38.5°". */
export function fmtC(n) { return `${Number(n).toFixed(1)}°`; }

/** Round to the 0.1° shown on screen, so the label always matches the number. */
export function round1(n) { return Math.round(n * 10) / 10; }

// ─── status enum ─────────────────────────────────────────────────────────────
export const STATUS = {
  OK:         'OK',
  WATCH:      'Watch',
  ACT_NOW:    'Act Now',
  REFUSE:     'Cannot Estimate',
};

/** Status for an estimate, compared at display precision (37.97 shows "38.0" → Watch). */
export function statusForCt(ct) {
  const r = round1(ct);
  if (r >= THRESHOLDS.ACT_NOW_C) return STATUS.ACT_NOW;
  if (r >= THRESHOLDS.WATCH_C)   return STATUS.WATCH;
  return STATUS.OK;
}

// ─── firmware state → app status ─────────────────────────────────────────────
/**
 * Paused comes from a blank number (the device blanks it on REFUSE), never from
 * a flag alone. A number at or above Watch is always shown: the v2.1 device
 * never refuses there, and the guard covers anything that still does.
 */
function _statusFor(fwState, core) {
  if (core === null) return STATUS.REFUSE;
  if (fwState === STATE.REFUSE && round1(core) < THRESHOLDS.WATCH_C) return STATUS.REFUSE;
  return statusForCt(core);
}

// "Starting…" vs "Pulse signal lost": both arrive as a blank number with the
// stale-heart-rate flag (the device blanks the number until the filter's first
// minute step after boot or a baseline, or after 2 minutes without a pulse).
// The live heart-rate byte tells them apart: a pulse means a reading is on its
// way, none means it is lost. The firmware accepts a minute with up to 30 bad
// seconds, so a pulse counts as present for PULSE_HOLD_MS after the last one
// (no flicker), which still shows a real loss within seconds.
// With two doubts the device stays paused after the pulse is back, so that
// isn't "on its way" either (same doubt count as stateFromFlags()).
const PULSE_HOLD_MS = 10_000;
let _lastPulseMs = null;

function _netDoubts(flags) {
  let d = 0;
  if (flags & FLAG.MOTIONLESS_TACHY) d++;
  if (flags & FLAG.NO_THERMAL_LOAD)  d++;
  if (flags & FLAG.COOL_SKIN)        d++;
  if (flags & FLAG.EVAP_FAILING)     d--;
  return d;
}

function _isStarting(core, flags, t) {
  return core === null && (flags & FLAG.STALE_HR) !== 0 && _netDoubts(flags) < 2 &&
    _lastPulseMs !== null && t - _lastPulseMs <= PULSE_HOLD_MS;
}

// ─── per-minute history ──────────────────────────────────────────────────────
// One point per minute of data time (mean of that minute's rows), 2 hours kept.
// Enough for the 30-min chart and the 10-min trend at any row rate.
const HISTORY_MINUTES = 120;
const MIN_MS = 60_000;
const BUCKET_FIELDS = ['ctEst', 'ctLo', 'ctHi', 'hr', 'skinC'];

function _pushHistory(hist, row) {
  const minute = Math.floor(row.t / MIN_MS);
  let b = hist[hist.length - 1];
  if (!b || b.minute !== minute) {
    b = { minute, t: 0, nT: 0, status: row.status };
    BUCKET_FIELDS.forEach(f => { b[f] = null; b['n_' + f] = 0; });
    hist.push(b);
    while (hist.length > HISTORY_MINUTES) hist.shift();
  }
  // Running means; missing values are skipped, not counted as zero.
  b.nT++; b.t += (row.t - b.t) / b.nT;
  BUCKET_FIELDS.forEach(f => {
    const v = row[f];
    if (v === null || v === undefined || !isFinite(v)) return;
    const n = ++b['n_' + f];
    b[f] = n === 1 ? v : b[f] + (v - b[f]) / n;
  });
  b.status = row.status;
}

// ─── event log ───────────────────────────────────────────────────────────────
// Events surfaced to the supervisor — no biometrics, type + time only.
export const EVENT_TYPE = {
  OVERHEATING_ALERT:  'Overheating Alert',
  REST_BREAK_TAKEN:   'Rest Break Taken',
  DEVICE_OFFLINE:     'Device Offline',
  BREAK_ENDED:        'Break Ended',
  CHECKED_IN_OK:      'Checked In — OK',
};

// ─── state ───────────────────────────────────────────────────────────────────
function _emptyLatest() {
  return {
    timestampMs:  null,  // arrival time (data clock)
    seq:          null,
    hr:           null,  // fused bpm
    hrQuality:    null,  // HRQ.* (0 none, 1 single, 2 both agree, 3 disagree)
    hrA:          null,
    hrB:          null,
    ctEst:        null,  // °C, null when the device withholds it
    half:         null,  // calibrated ± °C, null when missing (never made up)
    ctLo:         null,  // ctEst − half
    ctHi:         null,  // ctEst + half
    skinC:        null,
    microC:       null,
    microRh:      null,
    evapKpa:      null,  // kept for the record; never shown (no kPa on screen)
    activity:     null,  // g
    fwState:      null,  // STATE.* (0 OK, 1 CAUTION, 2 REFUSE)
    flags:        null,  // 16-bit
    reasonFlag:   0,     // first set flag in REASON_ORDER
    baselineRunning: false,
    status:       STATUS.REFUSE,
    confidence:   'normal',
    starting:     false, // blank number, stale-HR flag, but a pulse (see PULSE_HOLD_MS): a reading is on its way
  };
}

function _emptySession() {
  return {
    startMs:         null,  // first frame
    startCt:         null,  // first number (after the last baseline), so "since start" never drifts
    workStartMs:     null,  // first number after setup: break/water schedule and forecast start here
    baselineStartMs: null,  // first frame of the running baseline (the frame has no progress field)
    baselineFailed:  false, // the last baseline ended with no-baseline still set
    haveNumber:      false, // a number has arrived since the start or the last baseline taken
  };
}

const _state = {
  latest:  _emptyLatest(),

  // Per-minute history for trend, forecast and chart (oldest first)
  history: [],

  session: _emptySession(),

  // Weather (Open-Meteo, refreshed every 5 min)
  weather: {
    tempC:        null,
    humidity:     null,
    heatIndex:    null,
    fetchedAt:    null,
  },

  // Safety events (supervisor view only, no biometrics)
  events: [],       // { id, type, ts, resolved, resolvedTs }
  nextEventId: 1,

  // Connection: which source feeds the store, and its link state
  source:       'none',  // 'none' | 'demo' | 'ble' | 'serial'
  link:         'off',   // 'off' | 'connecting' | 'connected' | 'reconnecting' | 'stalled'

  onBreak:      false,
  breakStartMs: null,
  breakTargetMin: 5,
  lastBreakEndMs: null,  // end of the last break (work period restarts here)
  lastDrinkMs:  null,
};

let _prevBaselineRunning = false;

/** Forget everything about the current wearer session (keeps weather). */
function _resetSession() {
  _state.latest  = _emptyLatest();
  _state.history = [];
  _state.session = _emptySession();
  _state.events  = [];
  _state.onBreak = false;
  _state.breakStartMs   = null;
  _state.lastBreakEndMs = null;
  _state.lastDrinkMs    = null;
  _prevBaselineRunning  = false;
  _lastPulseMs   = null;
  _lastEventType = null;
  _lastEventTs   = 0;
}

// ─── subscribers ─────────────────────────────────────────────────────────────
const _subscribers = new Set();

function _notify() {
  for (const cb of _subscribers) {
    try { cb(snapshot()); } catch (e) { console.error('datastore subscriber error', e); }
  }
}

export function subscribe(cb) {
  _subscribers.add(cb);
  cb(snapshot()); // immediate initial value
  return () => _subscribers.delete(cb);
}

// ─── public read ─────────────────────────────────────────────────────────────
export function snapshot() {
  return {
    latest:     { ..._state.latest },
    history:    _state.history.map(b => ({ minute: b.minute, t: b.t, ctEst: b.ctEst, ctLo: b.ctLo, ctHi: b.ctHi, hr: b.hr, skinC: b.skinC, status: b.status })),
    session:    { ..._state.session },
    weather:    { ..._state.weather },
    events:     _state.events.map(e => ({ ...e })),
    source:     _state.source,
    link:       _state.link,
    connected:  _state.link === 'connected',
    simulating: _state.source === 'demo',
    onBreak:    _state.onBreak,
    breakStartMs: _state.breakStartMs,
    breakTargetMin: _state.breakTargetMin,
    lastBreakEndMs: _state.lastBreakEndMs,
    lastDrinkMs:  _state.lastDrinkMs,
    now:        dataNow(),
  };
}

// ─── ingest one frame ────────────────────────────────────────────────────────
const _num = x => (x === null || x === undefined || !Number.isFinite(x)) ? null : x;

/**
 * f: a decoded frame (decodeFrame in frame.js; the USB bench path and the demo
 * build the same shape). t: arrival time in ms. The device's seq only counts
 * while connected, so frames are timestamped on arrival; the demo passes its
 * own faster clock.
 */
export function ingestFrame(f, t = Date.now()) {
  const flags   = f.flags ?? 0;
  const fwState = f.state ?? STATE.OK;
  const core    = _num(f.core);
  // A blank number stays blank: never filled with an older value.
  const half    = core === null ? null : _num(f.half);
  const running = !!f.baselineRunning || (flags & FLAG.BASELINE_RUNNING) !== 0;
  const status  = _statusFor(fwState, core);
  const hr      = _num(f.hr);

  // ── session bookkeeping ──
  const sess = _state.session;
  if (sess.startMs === null) sess.startMs = t;
  if (running && !_prevBaselineRunning) {
    // Baseline started: setup countdown from here, work clock restarts after it
    sess.baselineStartMs = t;
    sess.baselineFailed = false;
    sess.workStartMs = null;
  }
  if (!running && _prevBaselineRunning) {
    sess.baselineStartMs = null;
    if (flags & FLAG.NO_BASELINE) {
      // No signal of its own: the bit drops and no-baseline stays set.
      // (Too few good heart-rate seconds, or the estimate reached Watch.)
      sess.baselineFailed = true;
    } else {
      // Taken: the device restarted the filter, so "since start" restarts too
      sess.startCt = null;
      sess.haveNumber = false;
    }
  }
  if (!(flags & FLAG.NO_BASELINE)) sess.baselineFailed = false;
  _prevBaselineRunning = running;

  if (hr !== null) _lastPulseMs = t;
  const starting = _isStarting(core, flags, t);
  if (core !== null) sess.haveNumber = true;

  _state.latest = {
    timestampMs: t,
    seq:         f.seq ?? null,
    hr,
    hrQuality:   f.hrQuality ?? null,
    hrA:         _num(f.hrA),
    hrB:         _num(f.hrB),
    ctEst:       core,
    half,
    ctLo:        half === null ? null : core - half,
    ctHi:        half === null ? null : core + half,
    skinC:       _num(f.skin),
    microC:      _num(f.microC),
    microRh:     _num(f.microRh),
    evapKpa:     _num(f.evapKpa),
    activity:    _num(f.activity),
    fwState,
    flags,
    reasonFlag:  f.reasonFlag ?? 0,
    baselineRunning: running,
    status,
    confidence:  fwState === STATE.OK ? 'normal' : 'low',
    starting,
  };

  _pushHistory(_state.history, {
    t,
    ctEst:  core,
    ctLo:   _state.latest.ctLo,
    ctHi:   _state.latest.ctHi,
    hr,
    skinC:  _state.latest.skinC,
    status,
  });

  if (core !== null) {
    if (sess.startCt === null) sess.startCt = core;
    // Work (break/water schedule, forecast warm-up) starts with the first number after setup
    const inSetup = (flags & (FLAG.NO_BASELINE | FLAG.BASELINE_RUNNING)) !== 0;
    if (!inSetup && sess.workStartMs === null) sess.workStartMs = t;
  }

  // Auto-generate safety events
  if (status === STATUS.ACT_NOW) _maybeRaiseEvent(EVENT_TYPE.OVERHEATING_ALERT);

  _notify();
}

// ─── weather ─────────────────────────────────────────────────────────────────
export function setWeather(tempC, humidity) {
  const heatIndex = _calcHeatIndex(tempC, humidity);
  _state.weather = { tempC, humidity, heatIndex, fetchedAt: Date.now() };
  _notify();
}

// Heat index (Rothfusz equation, valid above 27 °C / 80 °F)
function _calcHeatIndex(tC, rh) {
  const tF = tC * 9 / 5 + 32;
  if (tF < 80 || rh < 40) {
    // Simple approximation below threshold
    return tC + 0.33 * (rh / 100 * 6.105 * Math.exp(17.27 * tC / (237.7 + tC))) - 4.0;
  }
  const hi =
    -42.379 +
    2.04901523   * tF +
    10.14333127  * rh -
    0.22475541   * tF * rh -
    6.83783e-3   * tF * tF -
    5.481717e-2  * rh * rh +
    1.22874e-3   * tF * tF * rh +
    8.5282e-4    * tF * rh * rh -
    1.99e-6      * tF * tF * rh * rh;
  return (hi - 32) * 5 / 9;
}

// ─── safety events ───────────────────────────────────────────────────────────
let _lastEventType = null;
let _lastEventTs   = 0;
const EVENT_DEBOUNCE_MS = 60_000; // don't re-raise the same event within 1 min

function _maybeRaiseEvent(type) {
  const now = Date.now();
  if (type === _lastEventType && now - _lastEventTs < EVENT_DEBOUNCE_MS) return;
  _lastEventType = type;
  _lastEventTs   = now;
  _raiseEvent(type);
}

function _raiseEvent(type) {
  _state.events.unshift({
    id:         _state.nextEventId++,
    type,
    ts:         Date.now(),
    resolved:   false,
    resolvedTs: null,
  });
  // Keep last 50 events
  if (_state.events.length > 50) _state.events.length = 50;
}

/** Supervisor acknowledges: "I checked in, worker is OK" */
export function resolveEvent(id) {
  const ev = _state.events.find(e => e.id === id);
  if (ev) {
    ev.resolved   = true;
    ev.resolvedTs = Date.now();
    _raiseEvent(EVENT_TYPE.CHECKED_IN_OK);
    _notify();
  }
}

/**
 * "Now" on the data clock: the latest frame's arrival time. On the device this
 * tracks the wall clock; in the demo it runs at simulation speed, so break,
 * water and elapsed times all move together.
 */
export function dataNow() {
  return _state.latest.timestampMs ?? Date.now();
}

/** Wearer starts a rest break (5 min normally, 15+ in Act now) */
export function startBreak(targetMin = 5) {
  if (_state.onBreak) return;
  _state.onBreak      = true;
  _state.breakStartMs = dataNow();
  _state.breakTargetMin = targetMin;
  _raiseEvent(EVENT_TYPE.REST_BREAK_TAKEN);
  _notify();
}

/** Wearer ends their break */
export function endBreak() {
  if (!_state.onBreak) return;
  _state.onBreak      = false;
  _state.breakStartMs = null;
  _state.lastBreakEndMs = dataNow();
  _raiseEvent(EVENT_TYPE.BREAK_ENDED);
  _notify();
}

/** Wearer pressed "I drank" */
export function recordDrink() {
  _state.lastDrinkMs = dataNow();
  _notify();
}

// ─── connection state ─────────────────────────────────────────────────────────
/**
 * Switch the source feeding the store. A different source starts a new
 * session (demo history never mixes with the device's); the same source
 * reconnecting keeps its history. `fresh` forces a new session for the same
 * source (a restarted demo: its clock starts over).
 */
export function setSource(source, { fresh = false } = {}) {
  if (fresh || source !== _state.source) {
    _resetSession();
    _state.link = 'off';   // the old source's link state doesn't carry over
  }
  _state.source = source;
  _notify();
}

/**
 * Link state of the current source: 'off' | 'connecting' | 'connected' |
 * 'reconnecting' | 'stalled' (still connected, but no frame for a few seconds).
 */
export function setLink(link) {
  const wasUp = _state.link === 'connected';
  const device = _state.source === 'ble' || _state.source === 'serial';
  _state.link = link;
  if (wasUp && link !== 'connected' && device) _maybeRaiseEvent(EVENT_TYPE.DEVICE_OFFLINE);
  // Back up after a drop: the last frame is old, so it must not show as live
  // until a fresh one arrives. History and the session are kept.
  if (!wasUp && link === 'connected' && device) _state.latest = _emptyLatest();
  _notify();
}
