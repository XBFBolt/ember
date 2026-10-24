/**
 * datastore.js — in-memory only, zero persistence.
 *
 * All biometric data lives here and dies when the page closes.
 * No localStorage, no IndexedDB, no cookies, no server writes.
 *
 * Single source of truth for all three views.
 * Views subscribe with datastore.subscribe(callback).
 */

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

// ─── firmware state codes (match serial CSV) ─────────────────────────────────
const FW_STATE = { OK: 0, CAUTION: 1, REFUSE: 2 };

function fwStateToStatus(fwState, ctEst) {
  const valid = isFinite(ctEst);
  // Never Paused at or above Watch: show the number (tagged Low confidence) instead.
  if (fwState === FW_STATE.REFUSE && !(valid && round1(ctEst) >= THRESHOLDS.WATCH_C)) return STATUS.REFUSE;
  if (!valid) return STATUS.REFUSE;
  return statusForCt(ctEst);
}

function fwStateToConfidence(fwState, flags) {
  if (fwState !== FW_STATE.OK || (flags & 0x20) !== 0) return 'low';
  return 'normal';
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
  STRAP_OFFLINE:      'Strap Offline',
  BREAK_ENDED:        'Break Ended',
  CHECKED_IN_OK:      'Checked In — OK',
};

// ─── state ───────────────────────────────────────────────────────────────────
const _state = {
  // Latest reading
  latest: {
    timestampMs:  null,
    hr:           null,  // bpm
    ctEst:        null,  // °C
    ctLo:         null,  // °C lower bound
    ctHi:         null,  // °C upper bound
    skinC:        null,  // °C
    microC:       null,  // °C
    microRh:      null,  // %
    evapKpa:      null,  // kPa
    actRms:       null,
    stepHz:       null,
    fwState:      null,  // 0/1/2
    flags:        null,  // hex byte
    status:       STATUS.REFUSE,
    confidence:   'normal',
  },

  // Per-minute history for trend, forecast and chart (oldest first)
  history: [],

  // Session: first valid reading, kept separately so "since start" never drifts
  session: { startMs: null, startCt: null, setupStartMs: null, workStartMs: null },

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

  // Demo / connection state
  connected:    false,  // serial or sim
  simulating:   false,
  onBreak:      false,
  breakStartMs: null,
  breakTargetMin: 5,
  lastBreakEndMs: null,  // end of the last break (work period restarts here)
  lastDrinkMs:  null,
};

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
    history:    _state.history.map(b => ({ t: b.t, ctEst: b.ctEst, ctLo: b.ctLo, ctHi: b.ctHi, hr: b.hr, skinC: b.skinC, status: b.status })),
    session:    { ..._state.session },
    weather:    { ..._state.weather },
    events:     _state.events.map(e => ({ ...e })),
    connected:  _state.connected,
    simulating: _state.simulating,
    onBreak:    _state.onBreak,
    breakStartMs: _state.breakStartMs,
    breakTargetMin: _state.breakTargetMin,
    lastBreakEndMs: _state.lastBreakEndMs,
    lastDrinkMs:  _state.lastDrinkMs,
    now:        dataNow(),
  };
}

// ─── ingest a parsed CSV row from the firmware ───────────────────────────────
/**
 * row = {
 *   ms, hr, ct_est, ct_lo, ct_hi, kalman_half,
 *   skin_c, micro_c, micro_rh, evap_kpa,
 *   act_rms, step_hz, state, flags
 * }
 */
// Tracks the wall-clock time of the first ingest so we can compute
// simulated elapsed time from the firmware's ms field.
let _simEpochWall = null;
let _simEpochMs   = null;

export function ingestRow(row) {
  const ctEst   = parseFloat(row.ct_est);
  const fwState = parseInt(row.state, 10);
  const flags   = parseInt(row.flags, 16) || 0;

  // Never REFUSE when ctEst >= WATCH_C — fwStateToStatus keeps the number (low confidence)
  const status = fwStateToStatus(fwState, ctEst);

  const confidence = fwStateToConfidence(fwState, flags);

  const rowMs = parseFloat(row.ms) || 0;
  if (_simEpochWall === null) {
    _simEpochWall = Date.now();
    _simEpochMs   = rowMs;
  }
  // Reconstruct a wall-clock-aligned timestamp using sim time offsets
  const timestampMs = _simEpochWall + (rowMs - _simEpochMs);

  _state.latest = {
    timestampMs,
    hr:          parseFloat(row.hr)        || null,
    ctEst:       isFinite(ctEst) ? ctEst   : null,
    ctLo:        parseFloat(row.ct_lo)     || null,
    ctHi:        parseFloat(row.ct_hi)     || null,
    skinC:       parseFloat(row.skin_c)    || null,
    microC:      parseFloat(row.micro_c)   || null,
    microRh:     parseFloat(row.micro_rh)  || null,
    evapKpa:     parseFloat(row.evap_kpa)  || null,
    actRms:      parseFloat(row.act_rms)   || null,
    stepHz:      parseFloat(row.step_hz)   || null,
    fwState,
    flags:       parseInt(row.flags, 16)   || 0,
    status,
    confidence,
  };

  _pushHistory(_state.history, {
    t:      timestampMs,
    ctEst:  _state.latest.ctEst,
    ctLo:   _state.latest.ctLo,
    ctHi:   _state.latest.ctHi,
    hr:     _state.latest.hr,
    skinC:  _state.latest.skinC,
    status,
  });

  const sess = _state.session;
  if (sess.startMs === null) sess.startMs = timestampMs;
  if (sess.startCt === null && _state.latest.ctEst !== null) sess.startCt = _state.latest.ctEst;
  // Setup countdown runs from the first row that carries the no-baseline flag
  if (flags & 0x20) { if (sess.setupStartMs === null) sess.setupStartMs = timestampMs; }
  else {
    sess.setupStartMs = null;
    // Work (break/water schedule, forecast warm-up) starts with the first row after setup
    if (sess.workStartMs === null) sess.workStartMs = timestampMs;
  }

  // Auto-generate safety events
  if (status === STATUS.ACT_NOW) _maybeRaiseEvent(EVENT_TYPE.OVERHEATING_ALERT);
  if (!_state.connected) _state.connected = true;

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
 * "Now" on the data clock: the latest row's timestamp. On the device this tracks
 * the wall clock; in the demo it runs at simulation speed, so break, water and
 * elapsed times all move together.
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

/** Mark strap as offline */
export function markStrapOffline() {
  _maybeRaiseEvent(EVENT_TYPE.STRAP_OFFLINE);
  _state.connected = false;
  _notify();
}

// ─── connection state ─────────────────────────────────────────────────────────
export function setConnected(v) {
  _state.connected = v;
  if (!v) markStrapOffline();
  _notify();
}

export function setSimulating(v) {
  _state.simulating = v;
  _notify();
}
