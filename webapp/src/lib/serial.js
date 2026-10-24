/**
 * serial.js — USB serial link to the device, for the bench (Chrome, Web Serial).
 *
 * Sends START and reads the firmware's 19-column CSV at 1 Hz. Each row becomes
 * the same frame shape decodeFrame() returns, so the rest of the app can't
 * tell USB from Bluetooth. The worn demo uses Bluetooth (ble.js).
 *
 * Unlike the Bluetooth frame, the CSV always carries ct_est, so a REFUSE row
 * is blanked here, the same way the device blanks the frame.
 */

import { STATE, FLAG, HRQ, reasonFlag, FLAG_TEXT } from './frame.js';

const BAUD = 115200;
export const CSV_HEADER = 'ms,hr,sqi,hr_q,step_hz,act_g,skinA,skinB,skin,skin_q,air_c,vbat,' +
  'ct_est,ct_lo,ct_hi,kalman_half,filter_step,state,flags';
const FIELDS = CSV_HEADER.split(',');

const START_RETRY_MS = 3_000;   // resend START if no header yet (the board may reset when the port opens)
const START_TRIES    = 3;

let _port    = null;
let _reader  = null;
let _pipe    = null;
let _active  = false;
let _headerSeen = false;
let _startTimer = null;
let _onFrame = () => {};
let _onLink  = () => {};

export function serialAvailable() {
  return typeof navigator !== 'undefined' && 'serial' in navigator;
}

// ─── CSV → frame ─────────────────────────────────────────────────────────────

/** "nan", "" or garbage → null. */
function _num(s) {
  if (s === undefined || s === null) return null;
  const x = parseFloat(s);
  return Number.isFinite(x) ? x : null;
}

/**
 * One CSV line (after the header) → frame object, or null if it isn't a data row.
 * kalman_half is ignored: it is the uncalibrated interval and is never shown.
 */
export function csvLineToFrame(line) {
  const vals = line.trim().split(',');
  if (vals.length !== FIELDS.length) return null;
  const r = {};
  FIELDS.forEach((k, i) => { r[k] = vals[i]; });

  const state = (parseInt(r.state, 10) || 0) & 0x0f;
  const flags = (parseInt(r.flags, 16) || 0) & 0xffff;
  const refuse = state === STATE.REFUSE;
  const core = refuse ? null : _num(r.ct_est);
  const lo = _num(r.ct_lo), hi = _num(r.ct_hi);
  const half = core !== null && lo !== null && hi !== null ? (hi - lo) / 2 : null;
  const hr = _num(r.hr);
  const rf = reasonFlag(flags);

  return {
    seq:             null,
    core,
    half,
    state,
    baselineRunning: (flags & FLAG.BASELINE_RUNNING) !== 0,
    logging:         true,
    flags,
    reasonFlag:      rf,
    reason:          rf ? FLAG_TEXT[rf] : '',
    hr:              hr === 0 ? null : hr,
    hrQuality:       parseInt(r.hr_q, 10) || HRQ.NONE,
    skin:            _num(r.skin),
    airC:            _num(r.air_c),
    battery:         null,          // the power-bank build has no battery
    activity:        _num(r.act_g),
  };
}

// ─── connect ─────────────────────────────────────────────────────────────────

/**
 * Open the port chooser and start reading. Must be called from a click.
 * Same callbacks as connectBle(). Rejects if the user cancels.
 */
export async function connectSerial({ onFrame, onLink }) {
  if (!serialAvailable()) throw new Error('USB serial needs Chrome on a laptop.');
  const port = await navigator.serial.requestPort();
  await disconnectSerial({ quiet: true });
  _onFrame = onFrame;
  _onLink  = onLink;
  _onLink('connecting');
  try {
    await port.open({ baudRate: BAUD });
    _port = port;
    _active = true;
    _headerSeen = false;
    _readLoop().catch(err => console.warn('Serial read loop:', err.message));
    await sendSerialCommand('START');
  } catch (err) {
    await disconnectSerial({ quiet: true });
    _onLink('off');
    throw err;
  }
  _scheduleStartRetry(1);
  _onLink('connected');   // only once the port is open and START is written
}

/** Close everything. Each step on its own: after an unplug some of them fail. */
export async function disconnectSerial({ quiet = false } = {}) {
  _active = false;
  if (_startTimer) { clearTimeout(_startTimer); _startTimer = null; }
  const reader = _reader, pipe = _pipe, port = _port;
  _reader = null; _pipe = null; _port = null;
  if (reader) { try { await reader.cancel(); } catch (_) { /* stream already errored */ } }
  if (pipe)   await pipe;                    // never rejects (caught where it's created)
  if (port)   { try { await port.close(); } catch (_) { /* already gone */ } }
  if (!quiet) _onLink('off');
}

function _scheduleStartRetry(tries) {
  if (tries >= START_TRIES) return;
  _startTimer = setTimeout(() => {
    _startTimer = null;
    if (!_active || _headerSeen) return;
    sendSerialCommand('START').catch(() => {});
    _scheduleStartRetry(tries + 1);
  }, START_RETRY_MS);
}

export async function sendSerialCommand(text) {
  if (!_port?.writable) throw new Error('EMB.R is not connected over USB.');
  const writer = _port.writable.getWriter();
  try { await writer.write(new TextEncoder().encode(text + '\n')); }
  finally { writer.releaseLock(); }
}

// ─── read loop ───────────────────────────────────────────────────────────────

async function _readLoop() {
  const decoder = new TextDecoderStream();
  // Caught here so an unplug (the pipe aborts) is never an unhandled rejection
  _pipe = _port.readable.pipeTo(decoder.writable).catch(() => {});
  const reader = _reader = decoder.readable.getReader();

  let buf = '';
  try {
    while (_active) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += value;
      const lines = buf.split('\n');
      buf = lines.pop();                    // incomplete last line stays in the buffer
      for (const line of lines) {
        const s = line.trim();
        if (!s || s.startsWith('#')) continue;
        if (s === CSV_HEADER) { _headerSeen = true; continue; }
        if (!_headerSeen) continue;
        const f = csvLineToFrame(s);
        if (f) _onFrame(f);
      }
    }
  } catch (err) {
    if (_active) console.warn('Serial read error:', err.message);
  }
  if (_active && _reader === reader) {      // unplugged, not a user disconnect
    await disconnectSerial();
  }
}
