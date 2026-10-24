/**
 * replay.js — plays a saved bench CSV (the firmware's START output, 19 columns)
 * back through the app at 1×: one row a second, looping at the end.
 *
 * Each row goes CSV → frame (csvLineToFrame, which withholds the number on
 * REFUSE, as the device does) → the 20 bytes the device sends → decodeFrame(),
 * so a replay takes the same path from the bytes onwards as Bluetooth and the demo.
 */

import { csvLineToFrame, CSV_HEADER } from './serial.js';
import { encodeFrame, decodeFrame } from './frame.js';

/** Served next to the app: webapp/demo/. */
export const REPLAY_URL = new URL('../../demo/resting_sample.csv', import.meta.url);
const TICK_MS = 1_000;

let _frames  = null;   // parsed once, then reused for restarts
let _timer   = null;
let _onFrame = null;
let _i   = 0;
let _seq = 0;

/** Firmware CSV text → frames. Comment lines (#) and anything before the header are skipped. */
export function parseReplayCsv(text) {
  const lines = text.split(/\r?\n/).map(s => s.trim());
  const h = lines.indexOf(CSV_HEADER);
  if (h < 0) throw new Error('not an EMB.R CSV (header missing)');
  const frames = lines.slice(h + 1)
    .filter(s => s && !s.startsWith('#'))
    .map(csvLineToFrame)
    .filter(Boolean);
  if (!frames.length) throw new Error('the file has no data rows');
  return frames;
}

/** Fetch and parse the replay file (cached after the first load). */
export async function loadReplay(url = REPLAY_URL) {
  if (_frames) return _frames;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`couldn't load the replay file (${res.status})`);
  _frames = parseReplayCsv(await res.text());
  return _frames;
}

/** Start playing. onFrame(frame, t) gets each decoded frame and its time (wall clock, 1×). */
export function playReplay(frames, onFrame) {
  stopReplay();
  _frames  = frames;
  _onFrame = onFrame;
  _i = 0; _seq = 0;
  _timer = setInterval(_tick, TICK_MS);
  _tick();
}

export function stopReplay() {
  if (_timer) { clearInterval(_timer); _timer = null; }
  _onFrame = null;
}

export const replayRunning = () => _timer !== null;

function _tick() {
  if (!_onFrame) return;
  const f = { ..._frames[_i], seq: _seq++ & 0xffff };
  _onFrame(decodeFrame(encodeFrame(f)), Date.now());
  _i = (_i + 1) % _frames.length;   // loop: the clock keeps running, so history carries on
}
