// Host tests for the webapp's data path (no browser needed):
//  - frame.js: the same frames as `tools/ember_ble.py --selftest`, the firmware
//    encoder's byte-exact frame from tests/test_core.cpp, and the flag bits,
//    reason order and text against flagReason() in ember_core.h
//  - serial.js: the 24-column bench CSV, including REFUSE withholding the number
//  - datastore.js: Paused vs Starting, no gap-filling, never hidden at 38.0+
//
//   node --test tests/test_frame.mjs          (from ember/)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import {
  decodeFrame, encodeFrame, reasonFlag, FLAG, FLAG_TEXT, REASON_ORDER, STATE, HRQ, FRAME_LEN,
} from '../webapp/src/lib/frame.js';

const close = (a, b, msg) => assert.ok(Math.abs(a - b) < 1e-9, `${msg}: ${a} vs ${b}`);

// The frame tests/test_core.cpp encodes and ember_ble.py decodes.
const FW_BYTES = Uint8Array.from([0x01, 0x02, 0xC8, 0x0E, 31, 0x21, 0x20, 0x02, 131, 1,
  0x54, 0x0D, 0x4E, 0x0C, 127, 27, 81, 105, 131, 0]);

test('decodes the self-test frame', () => {
  const d = decodeFrame(new DataView(FW_BYTES.buffer));
  assert.equal(d.seq, 513);
  close(d.core, 37.84, 'core');
  close(d.half, 0.62, 'half');
  assert.equal(d.state, STATE.CAUTION);
  assert.equal(d.logging, true);
  assert.equal(d.baselineRunning, false);
  assert.equal(d.flags, FLAG.NO_BASELINE | FLAG.PPG_SINGLE);
  assert.equal(d.hr, 131);
  assert.equal(d.hrQuality, HRQ.SINGLE);
  close(d.skin, 34.12, 'skin');
  close(d.microC, 31.50, 'micro');
  assert.equal(d.microRh, 63.5);
  close(d.evapKpa, 1.35, 'evap');
  assert.equal(d.battery, 81);
  close(d.activity, 0.21, 'activity');
  assert.equal(d.hrA, 131);
  assert.equal(d.hrB, null);
  assert.equal(d.reasonFlag, FLAG.PPG_SINGLE);
  assert.equal(d.reason, 'one pulse sensor only');
});

test('REFUSE frame: core and ± arrive blank', () => {
  const e = decodeFrame(Uint8Array.from([0, 0, 0x00, 0x80, 255, 2, 0x08, 0, 0, 0,
    0x00, 0x80, 0x00, 0x80, 255, 0x80, 255, 255, 0, 0]));
  assert.equal(e.core, null);
  assert.equal(e.half, null);
  assert.equal(e.evapKpa, null);
  assert.equal(e.state, STATE.REFUSE);
  assert.equal(e.reason, 'no trustworthy heart rate');
  assert.equal(e.battery, null);
  assert.equal(e.hr, null);
  assert.equal(e.skin, null);
  assert.equal(e.microRh, null);
  assert.equal(e.activity, null);
});

test('at 38.0 and up a stale heart rate is CAUTION with the number', () => {
  const w = decodeFrame(Uint8Array.from([5, 0, 0xF6, 0x0E, 35, 0x01, 0x08, 0x00, 0, 0,
    0x00, 0x80, 0x00, 0x80, 255, 0x80, 255, 255, 0, 0]));
  assert.equal(w.state, STATE.CAUTION);
  close(w.core, 38.30, 'core');
  close(w.half, 0.70, 'half');
  assert.equal(w.reason, 'no trustworthy heart rate');
});

test('an info-only flag never masks the reason', () => {
  const b = new Uint8Array(FRAME_LEN);
  b[5] = STATE.CAUTION;
  new DataView(b.buffer).setUint16(6, FLAG.NO_BASELINE | FLAG.NOT_CALIBRATED | FLAG.NO_MICRO, true);
  assert.equal(decodeFrame(b).reason, 'no baseline yet');
  assert.equal(reasonFlag(0), 0);
  assert.equal(reasonFlag(FLAG.EVAP_FAILING | FLAG.RESERVED_0010), 0);
});

test('baseline-running bit and short frames', () => {
  const b = new Uint8Array(FRAME_LEN);
  b[5] = STATE.CAUTION | 0x10;
  const d = decodeFrame(b.buffer);
  assert.equal(d.baselineRunning, true);
  assert.equal(d.logging, false);
  assert.equal(d.state, STATE.CAUTION);
  assert.throws(() => decodeFrame(new Uint8Array(19)), RangeError);
});

test('encoder matches the firmware byte for byte', () => {
  const f = {
    seq: 513, core: 37.84, half: 0.62, state: STATE.CAUTION, baselineRunning: false, logging: true,
    flags: FLAG.PPG_SINGLE | FLAG.NO_BASELINE, hr: 131.4, hrQuality: HRQ.SINGLE, skin: 34.12,
    microC: 31.5, microRh: 63.5, evapKpa: 1.37, battery: 81, activity: 0.21, hrA: 131.4, hrB: null,
  };
  assert.deepEqual(Array.from(encodeFrame(f)), Array.from(FW_BYTES));

  const blank = encodeFrame({ ...f, core: NaN, half: null, evapKpa: undefined });
  const v = new DataView(blank.buffer);
  assert.equal(v.getInt16(2, true), -32768);
  assert.equal(blank[4], 255);
  assert.equal(blank[15], 0x80);
});

test('encode → decode round trip', () => {
  const f = {
    seq: 65535, core: 38.71, half: 0.86, state: STATE.CAUTION, baselineRunning: true, logging: false,
    flags: FLAG.BASELINE_RUNNING | FLAG.NO_BASELINE | FLAG.EVAP_FAILING, hr: 162, hrQuality: HRQ.AGREED,
    skin: 35.5, microC: 33.25, microRh: 91, evapKpa: -0.4, battery: null, activity: 0.5, hrA: 161, hrB: 163,
  };
  const d = decodeFrame(encodeFrame(f));
  for (const k of ['seq', 'state', 'baselineRunning', 'logging', 'flags', 'hr', 'hrQuality', 'microRh', 'battery', 'activity', 'hrA', 'hrB']) {
    assert.equal(d[k], f[k], k);
  }
  for (const k of ['core', 'half', 'skin', 'microC', 'evapKpa']) close(d[k], f[k], k);
  assert.equal(d.reason, 'baseline in progress');
});

test('flags, reason order and reason text match ember_core.h', () => {
  const src = readFileSync(fileURLToPath(new URL('../firmware/ember/ember_core.h', import.meta.url)), 'utf8');
  const bits = Object.fromEntries([...src.matchAll(/\b(F_\w+)\s*=\s*(0x[0-9A-Fa-f]+)/g)].map(m => [m[1], parseInt(m[2], 16)]));
  for (const [name, bit] of Object.entries(FLAG)) assert.equal(bits['F_' + name], bit, `F_${name}`);

  let body = src.slice(src.indexOf('inline const char *flagReason'));
  body = body.slice(0, body.indexOf('\n}'));
  const fw = [...body.matchAll(/if \(f & (F_\w+)\)\s+return "([^"]*)"/g)].map(m => [bits[m[1]], m[2]]);
  assert.ok(fw.length > 0, 'found flagReason');
  assert.deepEqual(fw.map(([b]) => b), REASON_ORDER, 'REASON_ORDER differs from flagReason');
  for (const [bit, text] of fw) assert.equal(FLAG_TEXT[bit], text, `0x${bit.toString(16)}`);
});

// ─── USB bench path: the 24-column CSV becomes the same frame shape ─────────

const { csvLineToFrame } = await import('../webapp/src/lib/serial.js');

test('CSV row → frame (firmware printf format)', () => {
  const f = csvLineToFrame('123456,131.2,0.81,nan,0.10,131.2,1,1.62,0.210,34.10,nan,34.10,2,' +
    '31.50,63.5,1.370,0.00,37.840,37.220,38.460,0.900,1,1,0x0220');
  close(f.core, 37.84, 'core');
  close(f.half, 0.62, 'half (from ct_lo/ct_hi, never kalman_half)');
  assert.equal(f.state, STATE.CAUTION);
  assert.equal(f.flags, FLAG.PPG_SINGLE | FLAG.NO_BASELINE);
  assert.equal(f.reason, 'one pulse sensor only');
  assert.equal(f.hr, 131.2);
  assert.equal(f.hrQuality, HRQ.SINGLE);
  assert.equal(f.hrB, null);
  close(f.skin, 34.10, 'skin');
  close(f.activity, 0.21, 'activity');
  assert.equal(f.baselineRunning, false);
  assert.equal(f.battery, null);
});

test('CSV REFUSE row: the number is withheld, as the device does over Bluetooth', () => {
  const f = csvLineToFrame('1,nan,0,nan,0,nan,0,0.00,0.010,33.00,33.00,33.00,0,' +
    '28.00,40.0,2.900,0.00,37.100,36.480,37.720,0.900,0,2,0x8028');
  assert.equal(f.state, STATE.REFUSE);
  assert.equal(f.core, null);
  assert.equal(f.half, null);
  assert.equal(f.hr, null);
  assert.equal(f.baselineRunning, true);
  assert.equal(f.reason, 'no trustworthy heart rate');
  assert.equal(csvLineToFrame('ms,hrA,sqiA'), null);
});

// ─── datastore: Paused, Starting, and no gap-filling ─────────────────────────

const ds = await import('../webapp/src/lib/datastore.js');

test('a blank number stays blank; a pulse means a reading is on its way', () => {
  ds.setSource('test-a');
  const t0 = 1_000_000;
  // Boot: stale heart rate, no number yet, pulse present → Starting
  ds.ingestFrame({ core: null, half: null, state: STATE.REFUSE, flags: FLAG.STALE_HR | FLAG.NO_BASELINE, hr: 70 }, t0);
  let l = ds.snapshot().latest;
  assert.equal(l.status, ds.STATUS.REFUSE);
  assert.equal(l.starting, true);
  assert.equal(ds.snapshot().session.haveNumber, false);
  // First number
  ds.ingestFrame({ core: 37.2, half: 0.6, state: STATE.CAUTION, flags: FLAG.NO_BASELINE, hr: 70 }, t0 + 60_000);
  l = ds.snapshot().latest;
  close(l.ctLo, 36.6, 'lo'); close(l.ctHi, 37.8, 'hi');
  assert.equal(l.confidence, 'low');
  // Pulse lost mid-session: Paused, nothing carried over
  ds.ingestFrame({ core: null, half: null, state: STATE.REFUSE, flags: FLAG.STALE_HR, hr: null }, t0 + 120_000);
  l = ds.snapshot().latest;
  assert.equal(l.ctEst, null);
  assert.equal(l.half, null);
  assert.equal(l.ctLo, null);
  assert.equal(l.status, ds.STATUS.REFUSE);
  assert.equal(l.starting, false);
  assert.equal(ds.snapshot().session.haveNumber, true);   // so a returning pulse reads as Paused, not Starting
});

test('no pulse is "lost" straight away, even right after connecting (no timer)', () => {
  ds.setSource('test-b');
  ds.ingestFrame({ core: null, state: STATE.REFUSE, flags: FLAG.STALE_HR, hr: null }, 2_000_000);
  assert.equal(ds.snapshot().latest.starting, false);
  // Two doubts with a pulse is a real refusal, not Starting
  ds.ingestFrame({ core: null, state: STATE.REFUSE, flags: FLAG.MOTIONLESS_TACHY | FLAG.COOL_SKIN, hr: 110 }, 2_001_000);
  assert.equal(ds.snapshot().latest.starting, false);
});

test('a failed baseline: the bit drops and no-baseline stays set', () => {
  ds.setSource('test-e');
  const t0 = 5_000_000;
  ds.ingestFrame({ core: 37.0, half: 0.6, state: STATE.CAUTION, flags: FLAG.NO_BASELINE, hr: 64 }, t0);
  ds.ingestFrame({ core: 37.0, half: 0.6, state: STATE.CAUTION, baselineRunning: true,
    flags: FLAG.NO_BASELINE | FLAG.BASELINE_RUNNING, hr: 64 }, t0 + 1000);
  ds.ingestFrame({ core: 37.0, half: 0.6, state: STATE.CAUTION, flags: FLAG.NO_BASELINE, hr: null }, t0 + 301_000);
  const s = ds.snapshot().session;
  assert.equal(s.baselineFailed, true);
  assert.equal(s.startCt, 37.0, 'filter not restarted, so "since start" keeps its start');
  // Retrying clears it
  ds.ingestFrame({ core: 37.0, half: 0.6, state: STATE.CAUTION, baselineRunning: true,
    flags: FLAG.NO_BASELINE | FLAG.BASELINE_RUNNING, hr: 64 }, t0 + 310_000);
  assert.equal(ds.snapshot().session.baselineFailed, false);
});

test('a baseline restarts "since start" and shows Starting until the next number', () => {
  ds.setSource('test-c');
  const t0 = 3_000_000;
  ds.ingestFrame({ core: 37.0, half: 0.6, state: STATE.CAUTION, flags: FLAG.NO_BASELINE, hr: 64 }, t0);
  ds.ingestFrame({ core: 37.0, half: 0.6, state: STATE.CAUTION, baselineRunning: true,
    flags: FLAG.NO_BASELINE | FLAG.BASELINE_RUNNING, hr: 64 }, t0 + 1000);
  assert.equal(ds.snapshot().session.baselineStartMs, t0 + 1000);
  ds.ingestFrame({ core: null, state: STATE.REFUSE, flags: FLAG.STALE_HR, hr: 64 }, t0 + 301_000);
  const s = ds.snapshot();
  assert.equal(s.latest.starting, true);
  assert.equal(s.session.baselineStartMs, null);
  assert.equal(s.session.startCt, null);
  ds.ingestFrame({ core: 36.9, half: 0.68, state: STATE.OK, flags: 0, hr: 64 }, t0 + 361_000);
  assert.equal(ds.snapshot().session.startCt, 36.9);
  assert.equal(ds.snapshot().session.workStartMs, t0 + 361_000);
});

test('Starting holds through a dropped second, and gives way to "lost" within seconds', () => {
  ds.setSource('test-f');
  const t0 = 6_000_000;
  const blank = (t, hr) => ds.ingestFrame({ core: null, state: STATE.REFUSE, flags: FLAG.STALE_HR, hr }, t);
  blank(t0, 66);
  blank(t0 + 1000, null);                       // firmware tolerates bad seconds
  assert.equal(ds.snapshot().latest.starting, true, 'no flicker on one bad second');
  blank(t0 + 12_000, null);
  assert.equal(ds.snapshot().latest.starting, false, 'a real loss shows within seconds');
});

test('reconnecting the same device never shows the old number as live', () => {
  ds.setSource('demo');
  ds.setLink('connected');
  ds.setSource('ble');
  assert.equal(ds.snapshot().link, 'off', 'the demo link state does not carry over');
  ds.setLink('connecting');
  assert.equal(ds.snapshot().events.length, 0, 'no spurious Device Offline on demo → device');
  ds.setLink('connected');
  ds.ingestFrame({ core: 37.4, half: 0.6, state: STATE.OK, flags: 0, hr: 120 }, 7_000_000);
  ds.setLink('reconnecting');
  assert.equal(ds.snapshot().events[0]?.type, ds.EVENT_TYPE.DEVICE_OFFLINE);
  ds.setLink('connected');
  const s = ds.snapshot();
  assert.equal(s.latest.ctEst, null, 'old number cleared until a fresh frame');
  assert.equal(s.latest.timestampMs, null);
  assert.ok(s.history.length > 0, 'history kept');
  assert.notEqual(s.session.startMs, null, 'session kept');
  ds.setSource('test-g');
});

test('at 38.0 and up the number is always shown', () => {
  ds.setSource('test-d');
  ds.ingestFrame({ core: 38.3, half: 0.7, state: STATE.CAUTION, flags: FLAG.STALE_HR, hr: null }, 4_000_000);
  const l = ds.snapshot().latest;
  assert.equal(l.status, ds.STATUS.WATCH);
  assert.equal(l.confidence, 'low');
  // Even a REFUSE that still carried a number (pre-2.1 firmware) is not hidden up here
  ds.ingestFrame({ core: 38.3, half: 0.7, state: STATE.REFUSE, flags: FLAG.STALE_HR, hr: null }, 4_001_000);
  assert.equal(ds.snapshot().latest.status, ds.STATUS.WATCH);
});
