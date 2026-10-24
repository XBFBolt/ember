/**
 * serial.js — Web Serial API bridge to the Ember device.
 *
 * Reads the CSV stream produced by the firmware when `START` is sent.
 * CSV header: ms,hr,ct_est,ct_lo,ct_hi,kalman_half,skin_c,micro_c,
 *             micro_rh,evap_kpa,act_rms,step_hz,state,flags
 *
 * Falls back to simulation mode if Web Serial is unavailable
 * (Firefox, Safari, or no device connected).
 */

import { ingestRow, setConnected, setSimulating, markStrapOffline } from './datastore.js';
import { confHalf } from './estimator.js';

const BAUD = 115200;
const CSV_HEADER = 'ms,hr,ct_est,ct_lo,ct_hi,kalman_half,skin_c,micro_c,micro_rh,evap_kpa,act_rms,step_hz,state,flags';
const FIELDS = CSV_HEADER.split(',');

let _port   = null;
let _reader = null;
let _active = false;

// ─── connect ─────────────────────────────────────────────────────────────────
export async function connectSerial() {
  if (!('serial' in navigator)) {
    console.warn('Web Serial not available — starting simulation');
    startSimulation();
    return false;
  }

  try {
    _port = await navigator.serial.requestPort();
    await _port.open({ baudRate: BAUD });
    setConnected(true);
    setSimulating(false);
    _active = true;
    _readLoop();
    _sendStart();
    return true;
  } catch (err) {
    console.warn('Serial connect failed:', err.message);
    startSimulation();
    return false;
  }
}

export async function disconnectSerial() {
  _active = false;
  try {
    if (_reader) { await _reader.cancel(); _reader = null; }
    if (_port)   { await _port.close();    _port   = null; }
  } catch (_) { /* ignore */ }
  setConnected(false);
}

async function _sendStart() {
  if (!_port?.writable) return;
  const writer = _port.writable.getWriter();
  await writer.write(new TextEncoder().encode('START\n'));
  writer.releaseLock();
}

// ─── read loop ───────────────────────────────────────────────────────────────
async function _readLoop() {
  const decoder = new TextDecoderStream();
  _port.readable.pipeTo(decoder.writable);
  _reader = decoder.readable.getReader();

  let buf = '';
  let headerSeen = false;

  try {
    while (_active) {
      const { value, done } = await _reader.read();
      if (done) break;
      buf += value;
      const lines = buf.split('\n');
      buf = lines.pop(); // incomplete last line stays in buffer

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        if (trimmed === CSV_HEADER) { headerSeen = true; continue; }
        if (!headerSeen) continue;
        _parseLine(trimmed);
      }
    }
  } catch (err) {
    if (_active) {
      console.warn('Serial read error:', err.message);
      markStrapOffline();
    }
  }
}

function _parseLine(line) {
  const vals = line.split(',');
  if (vals.length !== FIELDS.length) return;
  const row = {};
  FIELDS.forEach((f, i) => { row[f] = vals[i]; });
  ingestRow(row);
}

// ─── simulation mode ──────────────────────────────────────────────────────────
/**
 * Demo simulation: compresses a realistic 15-minute exercise bout into
 * ~2 minutes of wall-clock time (30 steps × 4 s = 120 s).
 *
 * Each tick advances simulated time by 30 s so the elapsed counter and
 * chart feel like a full 15-minute session even though it runs fast.
 *
 * Skin temp is always below core temp (~1–2 °C lower) and on a shared
 * scale so the chart separation is visually clear.
 */
let _simTimer  = null;
let _simStep   = 0;   // trajectory index, holds at the last step
let _simTicks  = 0;   // ticks since start, keeps counting so the clock never stops

// Simulated ms offset per step: 30 s of "exercise time" per tick
const SIM_MS_PER_STEP = 30_000;
// Wall-clock tick interval
const SIM_TICK_MS = 4_000;
// Setup phase first: 10 ticks = 5 simulated minutes (~40 s on the clock),
// sitting still with the no-baseline flag (0x20) set, then the climb starts.
const SIM_SETUP_TICKS = 10;

export function startSimulation() {
  if (_simTimer) return;
  setSimulating(true);
  setConnected(true);
  _simStep = 0;
  _simTicks = 0;
  _simTimer = setInterval(_simTick, SIM_TICK_MS);
  _simTick(); // immediate first tick
}

export function stopSimulation() {
  if (_simTimer) { clearInterval(_simTimer); _simTimer = null; }
  setSimulating(false);
}

// 30-step trajectory: warm-up → heat stress peak → partial recovery → hold
// HR profile matches the exercise arc
const SIM_HR_PROFILE = [
  65, 67, 70, 74, 79, 85, 91, 97, 103, 109,
  114, 118, 122, 125, 127, 129, 130, 131, 132, 132,
  131, 130, 128, 126, 124, 122, 120, 118, 117, 116,
];

// Core temp waypoints: rises from 36.8 to ~38.7 by step 20,
// then cools to ~38.0 by step 30.
function _simCtEst(i) {
  if (i <= 20) {
    // Linear rise: 36.8 at step 0 → 38.7 at step 20
    return 36.8 + (i / 20) * (38.7 - 36.8);
  } else {
    // Linear cool: 38.7 at step 20 → 38.0 at step 30
    return 38.7 + ((i - 20) / 10) * (38.0 - 38.7);
  }
}

function _simSetupTick() {
  // Resting and still: flat core, resting HR, almost no motion
  const ctEst = 36.8 + (Math.random() - 0.5) * 0.04;
  const half  = confHalf(ctEst);
  ingestRow({
    ms:          _simTicks * SIM_MS_PER_STEP,
    hr:          (64 + (Math.random() - 0.5) * 3).toFixed(1),
    ct_est:      ctEst.toFixed(3),
    ct_lo:       (ctEst - half).toFixed(3),
    ct_hi:       (ctEst + half).toFixed(3),
    kalman_half: '0.80',
    skin_c:      (35.3 + (Math.random() - 0.5) * 0.2).toFixed(2),
    micro_c:     (30.0 + (Math.random() - 0.5) * 0.3).toFixed(2),
    micro_rh:    (55 + (Math.random() - 0.5) * 3).toFixed(1),
    evap_kpa:    '2.800',
    act_rms:     (0.08 + Math.random() * 0.04).toFixed(3),
    step_hz:     '0.00',
    state:       0,
    flags:       '0x20',   // no baseline yet → "Setting up"
  });
  _simTicks++;
}

function _simTick() {
  if (_simTicks < SIM_SETUP_TICKS) { _simSetupTick(); return; }

  // Clamp to last step — hold rather than loop
  const i = Math.min(_simStep, SIM_HR_PROFILE.length - 1);

  const hr      = SIM_HR_PROFILE[i] + (Math.random() - 0.5) * 3;

  const ctEst   = _simCtEst(i) + (Math.random() - 0.5) * 0.04;
  const half    = confHalf(ctEst);  // calibrated widths, as the device sends

  // Skin temp: always 1.5–2.0 °C below core, with slight divergence during effort
  // (skin cools slightly via sweating while core keeps rising)
  const skinOffset = 1.5 + Math.min(i * 0.02, 0.5);
  const skinC   = ctEst - skinOffset + (Math.random() - 0.5) * 0.2;

  const microC  = 30.0 + i * 0.06 + (Math.random() - 0.5) * 0.3;
  const microRh = Math.min(95, 55 + i * 1.2 + (Math.random() - 0.5) * 3);
  const evapKpa = Math.max(0.1, 2.8 - i * 0.08 + (Math.random() - 0.5) * 0.1);
  const actRms  = 0.6 + (Math.random() - 0.5) * 0.2;

  // Use simulated ms so elapsed time shows "15 min" arc, not 2 min
  ingestRow({
    ms:          _simTicks * SIM_MS_PER_STEP,
    hr:          hr.toFixed(1),
    ct_est:      ctEst.toFixed(3),
    ct_lo:       (ctEst - half).toFixed(3),
    ct_hi:       (ctEst + half).toFixed(3),
    kalman_half: '0.80',
    skin_c:      skinC.toFixed(2),
    micro_c:     microC.toFixed(2),
    micro_rh:    microRh.toFixed(1),
    evap_kpa:    evapKpa.toFixed(3),
    act_rms:     actRms.toFixed(3),
    step_hz:     '1.85',
    state:       0,  // demo: always confident, so Act now shows cleanly
    flags:       evapKpa < 0.8 ? '0x80' : '0x00',
  });

  _simStep = Math.min(_simStep + 1, SIM_HR_PROFILE.length - 1);
  _simTicks++;
}
