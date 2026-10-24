/**
 * frame.js — the 20-byte Bluetooth frame (docs/APP_INTERFACE.md).
 *
 * decodeFrame() is a port of decode() in tools/ember_ble.py, and encodeFrame()
 * of encodeFrame() in firmware/ember/ember_core.h (the demo simulation uses it,
 * so the demo and the device share one decoder). Flag bits, reason order and
 * reason text must stay identical to ember_core.h; tests/test_frame.mjs checks.
 *
 * Pure module: no DOM, no imports, so node can test it.
 */

export const UUID = {
  SVC:  'e3b10001-5a2f-4c8e-9b7d-656d62657200',
  LIVE: 'e3b10002-5a2f-4c8e-9b7d-656d62657200',
  CMD:  'e3b10003-5a2f-4c8e-9b7d-656d62657200',
};
export const BLE_NAME = 'Ember';
export const FRAME_LEN = 20;

/** Low nibble of the state byte. */
export const STATE = { OK: 0, CAUTION: 1, REFUSE: 2 };
const STATE_BASELINE = 0x10;
const STATE_LOGGING  = 0x20;

/** Heart-rate quality, byte 9. */
export const HRQ = { NONE: 0, SINGLE: 1, AGREED: 2, DISAGREE: 3 };

export const FLAG = {
  MOTIONLESS_TACHY: 0x0001,
  NO_THERMAL_LOAD:  0x0002,
  COOL_SKIN:        0x0004,
  STALE_HR:         0x0008,
  RESERVED_0010:    0x0010,   // was WIDE_INTERVAL in 2.0. Never set, never reuse
  NO_BASELINE:      0x0020,
  CADENCE_LOCK:     0x0040,
  EVAP_FAILING:     0x0080,
  PPG_DISAGREE:     0x0100,
  PPG_SINGLE:       0x0200,
  SKIN_DISAGREE:    0x0400,
  SKIN_SINGLE:      0x0800,
  NO_MICRO:         0x1000,
  LOW_BATT:         0x2000,
  NOT_CALIBRATED:   0x4000,
  BASELINE_RUNNING: 0x8000,
};

/** Firmware reason text (flagReason() in ember_core.h). Not wearer wording. */
export const FLAG_TEXT = {
  [FLAG.STALE_HR]:         'no trustworthy heart rate',
  [FLAG.MOTIONLESS_TACHY]: 'high HR while still',
  [FLAG.NO_THERMAL_LOAD]:  'no thermal load',
  [FLAG.COOL_SKIN]:        'skin not warm',
  [FLAG.PPG_DISAGREE]:     'pulse sensors disagree',
  [FLAG.CADENCE_LOCK]:     'pulse matches step cadence',
  [FLAG.PPG_SINGLE]:       'one pulse sensor only',
  [FLAG.BASELINE_RUNNING]: 'baseline in progress',
  [FLAG.NO_BASELINE]:      'no baseline yet',
  [FLAG.SKIN_DISAGREE]:    'skin sensors disagree',
  [FLAG.NOT_CALIBRATED]:   'thermistors not calibrated',
  [FLAG.NO_MICRO]:         'no microclimate sensor',
};

/** One reason per state: the first set flag in this order (flagReason()). */
export const REASON_ORDER = [
  FLAG.STALE_HR, FLAG.MOTIONLESS_TACHY, FLAG.NO_THERMAL_LOAD, FLAG.COOL_SKIN,
  FLAG.PPG_DISAGREE, FLAG.CADENCE_LOCK, FLAG.PPG_SINGLE,
  FLAG.BASELINE_RUNNING, FLAG.NO_BASELINE,
  FLAG.SKIN_DISAGREE, FLAG.NOT_CALIBRATED, FLAG.NO_MICRO,
];

/** The flag that gives the reason, or 0 when none applies. */
export function reasonFlag(flags) {
  return REASON_ORDER.find(f => flags & f) ?? 0;
}

const I16_NONE = -32768;

/**
 * 20-byte little-endian frame → object. null means "not available".
 * Accepts a DataView (Web Bluetooth), an ArrayBuffer or a Uint8Array.
 * On REFUSE the device sends core and half as null on purpose: never fill them.
 */
export function decodeFrame(src) {
  const v = src instanceof DataView ? src
    : ArrayBuffer.isView(src) ? new DataView(src.buffer, src.byteOffset, src.byteLength)
    : new DataView(src);
  if (v.byteLength < FRAME_LEN) throw new RangeError(`frame is ${v.byteLength} bytes, expected ${FRAME_LEN}`);

  const c  = o => { const x = v.getInt16(o, true); return x === I16_NONE ? null : x / 100; };
  const u  = (o, scale, none) => { const x = v.getUint8(o); return x === none ? null : x / scale; };
  const st = v.getUint8(5);
  const flags = v.getUint16(6, true);
  const evap = v.getInt8(15);
  const rf = reasonFlag(flags);

  return {
    seq:             v.getUint16(0, true),
    core:            c(2),                    // °C, null whenever the device refuses
    half:            u(4, 50, 255),           // ± °C (calibrated), null with no number
    state:           st & 0x0f,               // STATE.*
    baselineRunning: (st & STATE_BASELINE) !== 0,
    logging:         (st & STATE_LOGGING) !== 0,
    flags,
    reasonFlag:      rf,
    reason:          rf ? FLAG_TEXT[rf] : '',
    hr:              u(8, 1, 0),              // fused bpm
    hrQuality:       v.getUint8(9),           // HRQ.*
    skin:            c(10),
    microC:          c(12),
    microRh:         u(14, 2, 255),
    evapKpa:         evap === -128 ? null : evap / 20,
    battery:         u(16, 1, 255),           // null = on USB power (always, on the power-bank build)
    activity:        u(17, 500, 255),         // g
    hrA:             u(18, 1, 0),
    hrB:             u(19, 1, 0),
  };
}

// ─── encoder (mirrors ember_core.h; the simulation and tests use it) ─────────

const _none = x => x === null || x === undefined || Number.isNaN(x);
// C roundf: halves round away from zero (Math.round rounds them up).
const _roundf = x => Math.sign(x) * Math.round(Math.abs(x));

function _centi(x) {
  if (_none(x)) return I16_NONE;
  return Math.max(-32767, Math.min(32767, _roundf(x * 100)));
}
function _u8(x, scale, none) {
  if (_none(x)) return none;
  return Math.max(0, Math.min(254, _roundf(x * scale)));
}

/** Frame object (the shape decodeFrame returns) → Uint8Array(20). */
export function encodeFrame(f) {
  const b = new Uint8Array(FRAME_LEN);
  const v = new DataView(b.buffer);
  v.setUint16(0, (f.seq ?? 0) & 0xffff, true);
  v.setInt16(2, _centi(f.core), true);
  b[4] = _u8(f.half, 50, 255);
  b[5] = (f.state ?? 0) | (f.baselineRunning ? STATE_BASELINE : 0) | (f.logging ? STATE_LOGGING : 0);
  v.setUint16(6, (f.flags ?? 0) & 0xffff, true);
  b[8] = _u8(f.hr, 1, 0);
  b[9] = f.hrQuality ?? HRQ.NONE;
  v.setInt16(10, _centi(f.skin), true);
  v.setInt16(12, _centi(f.microC), true);
  b[14] = _u8(f.microRh, 2, 255);
  v.setInt8(15, _none(f.evapKpa) ? -128 : Math.max(-127, Math.min(127, _roundf(f.evapKpa * 20))));
  b[16] = _none(f.battery) ? 255 : f.battery;
  b[17] = _u8(f.activity, 500, 255);
  b[18] = _u8(f.hrA, 1, 0);
  b[19] = _u8(f.hrB, 1, 0);
  return b;
}
