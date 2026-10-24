/**
 * sim.js — demo simulation. Builds v2 frames, encodes them to the 20 bytes the
 * device sends and decodes them with the same decodeFrame(), so the demo and
 * the device share one code path from the bytes onwards.
 *
 * Time runs 7.5× fast: one frame every 4 s of wall clock, 30 s of data time.
 * The session follows the device:
 *   boot      1 min   no number yet (stale heart rate)       → "Starting"
 *   no base   ≤2 min  number, no baseline; waits for BASELINE, then starts it itself
 *   baseline  5 min   baseline running (state bit 4)        → "Setting up"
 *   restart   1 min   filter restarted, number withheld     → "Starting"
 *   work              36.8 → 38.7 → 38.0 °C, then holds; one minute with the pulse on the step rate
 */

import { encodeFrame, decodeFrame, STATE, FLAG, HRQ } from './frame.js';
import { conformalHalfWidth, conformalHalfWidthRaw } from './conformal_table.js';
import { THRESHOLDS } from './datastore.js';

const SIM_TICK_MS = 4_000;    // wall clock per frame
const SIM_MS_PER_TICK = 30_000; // data time per frame

const BOOT_TICKS     = 2;
const NOBASE_TICKS   = 4;     // auto-start the baseline after this, so the demo runs hands-free
const BASELINE_TICKS = 10;    // 5 min, as on the device
const RESTART_TICKS  = 2;

// Work trajectory: one entry per tick (30 s). HR follows the exercise arc.
const WORK_HR = [
  65, 67, 70, 74, 79, 85, 91, 97, 103, 109,
  114, 118, 122, 125, 127, 129, 130, 131, 132, 132,
  131, 130, 128, 126, 124, 122, 120, 118, 117, 116,
];
const CADENCE_STEPS = [8, 9];   // one minute with the pulse on the step rate → Low confidence

// 36.8 at step 0 → 38.7 at step 20, then cools to 38.0 by step 29 and holds.
function _workCore(i) {
  if (i <= 20) return 36.8 + (i / 20) * (38.7 - 36.8);
  return 38.7 + ((i - 20) / 9) * (38.0 - 38.7);
}

let _timer   = null;
let _onFrame = null;
let _epoch   = 0;    // data-clock start (wall ms)
let _ticks   = 0;    // frames since start (data clock)
let _seq     = 0;
let _phase   = 'boot';
let _inPhase = 0;    // ticks in the current phase
let _step    = 0;    // work trajectory index
let _lastCore = null;

const _jit = (amp) => (Math.random() - 0.5) * amp;

/** Start the demo. onFrame(frame, t) gets each decoded frame and its data time. */
export function startSimulation(onFrame) {
  stopSimulation();
  _onFrame = onFrame;
  _epoch = Date.now();
  _ticks = 0; _seq = 0; _step = 0; _lastCore = null;
  _go('boot');
  _timer = setInterval(_tick, SIM_TICK_MS);
  _tick();
}

export function stopSimulation() {
  if (_timer) { clearInterval(_timer); _timer = null; }
  _onFrame = null;
}

export const simRunning = () => _timer !== null;

/** Commands the demo understands. BASELINE follows the device's rule: not at or above Watch. */
export function simCommand(text) {
  const cmd = String(text).trim().toUpperCase();
  if (cmd !== 'BASELINE') return;
  if (_phase === 'baseline' || _phase === 'restart') return;
  if (_lastCore !== null && _lastCore >= THRESHOLDS.WATCH_C) return;   // ignored, as on the device
  _step = 0;
  _go('baseline');
}

function _go(phase) { _phase = phase; _inPhase = 0; }

function _tick() {
  if (!_onFrame) return;
  const f = _frame();
  _lastCore = f.core;
  const t = _epoch + _ticks * SIM_MS_PER_TICK;
  _onFrame(decodeFrame(encodeFrame(f)), t);
  _ticks++;
  _inPhase++;
  if (_phase === 'work') _step = Math.min(_step + 1, WORK_HR.length - 1);   // holds at the end
  else if (_phase === 'boot'     && _inPhase >= BOOT_TICKS)     _go('nobase');
  else if (_phase === 'nobase'   && _inPhase >= NOBASE_TICKS)   _go('baseline');
  else if (_phase === 'baseline' && _inPhase >= BASELINE_TICKS) _go('restart');
  else if (_phase === 'restart'  && _inPhase >= RESTART_TICKS)  _go('work');
}

function _frame() {
  const resting = _phase !== 'work';
  const hr = resting ? 64 + _jit(3) : WORK_HR[_step] + _jit(3);
  const core = resting ? 36.8 + _jit(0.04) : _workCore(_step) + _jit(0.04);
  const i = resting ? 0 : _step;

  const f = {
    seq:      _seq++ & 0xffff,
    core,
    // As on the device: the learned correction (and its narrower table) is
    // on only once the baseline is captured; before that, the filter alone.
    half:     _phase === 'work' ? conformalHalfWidth(core) : conformalHalfWidthRaw(core),
    state:    STATE.OK,
    baselineRunning: false,
    logging:  false,
    flags:    0,
    hr,
    hrQuality: HRQ.OK,
    // Skin sits 1.5–2.0 °C below core and drifts a little further during effort
    skin:     core - (1.5 + Math.min(i * 0.02, 0.5)) + _jit(0.2),
    // Air beside the strap: a warm room, warmed a little by the body during effort
    airC:     27.0 + i * 0.04 + _jit(0.2),
    battery:  null,                                   // power bank: always "on USB"
    activity: resting ? 0.01 + Math.random() * 0.01 : 0.22 + _jit(0.08),
  };

  switch (_phase) {
    case 'boot':       // first minute after power-on: the filter hasn't stepped yet
      Object.assign(f, { core: null, half: null, state: STATE.REFUSE, flags: FLAG.STALE_HR | FLAG.NO_BASELINE });
      break;
    case 'nobase':
      Object.assign(f, { state: STATE.CAUTION, flags: FLAG.NO_BASELINE });
      break;
    case 'baseline':
      Object.assign(f, { state: STATE.CAUTION, baselineRunning: true, flags: FLAG.NO_BASELINE | FLAG.BASELINE_RUNNING });
      break;
    case 'restart':    // baseline done: filter restarted, number withheld until its next step
      Object.assign(f, { core: null, half: null, state: STATE.REFUSE, flags: FLAG.STALE_HR });
      break;
    default:           // work
      if (CADENCE_STEPS.includes(_step)) {
        // The device drops a pulse that jumps to the step rate: no heart rate that second
        Object.assign(f, { state: STATE.CAUTION, flags: FLAG.CADENCE_LOCK, hr: null, hrQuality: HRQ.NONE });
      }
  }
  return f;
}
