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

/** Heart-rate quality, byte 9. (2 and 3 were 2.1's two-sensor states; 2.2 never sends them.) */
export const HRQ = { NONE: 0, OK: 1 };

/** Reserved bits are never set (firmware 2.2). Never reuse 0x0010, 0x0100, 0x0200. */
export const FLAG = {
  MOTIONLESS_TACHY: 0x0001,
  RESERVED_0002:    0x0002,   // was NO_THERMAL_LOAD (2.1, needed humidity)
  COOL_SKIN:        0x0004,
  STALE_HR:         0x0008,
  RESERVED_0010:    0x0010,   // was WIDE_INTERVAL in 2.0
  NO_BASELINE:      0x0020,
  CADENCE_LOCK:     0x0040,
  RESERVED_0080:    0x0080,   // was EVAP_FAILING (2.1, needed humidity)
  RESERVED_0100:    0x0100,   // was PPG_DISAGREE (2.1, two pulse sensors)
  RESERVED_0200:    0x0200,   // was PPG_SINGLE (2.1, two pulse sensors)
  SKIN_DISAGREE:    0x0400,
  SKIN_SINGLE:      0x0800,
  NO_AIR:           0x1000,
  LOW_BATT:         0x2000,
  NOT_CALIBRATED:   0x4000,
  BASELINE_RUNNING: 0x8000,
};

/** Firmware reason text (flagReason() in ember_core.h). Not wearer wording. */
export const FLAG_TEXT = {
  [FLAG.STALE_HR]:         'no trustworthy heart rate',
  [FLAG.MOTIONLESS_TACHY]: 'high HR while still',
  [FLAG.COOL_SKIN]:        'skin not warm',
  [FLAG.CADENCE_LOCK]:     'pulse matches step cadence',
  [FLAG.BASELINE_RUNNING]: 'baseline in progress',
  [FLAG.NO_BASELINE]:      'no baseline yet',
  [FLAG.SKIN_DISAGREE]:    'skin sensors disagree',
  [FLAG.NOT_CALIBRATED]:   'thermistors not calibrated',
  [FLAG.NO_AIR]:           'no air temperature sensor',
};

/** One reason per state: the first set flag in this order (flagReason()). */
export const REASON_ORDER = [
  FLAG.STALE_HR, FLAG.MOTIONLESS_TACHY, FLAG.COOL_SKIN, FLAG.CADENCE_LOCK,
  FLAG.BASELINE_RUNNING, FLAG.NO_BASELINE,
  FLAG.SKIN_DISAGREE, FLAG.NOT_CALIBRATED, FLAG.NO_AIR,
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
 * Bytes 14, 15, 18 and 19 are reserved (2.1's humidity, headroom and
 * per-sensor heart rates) and ignored.
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
    hr:              u(8, 1, 0),              // bpm
    hrQuality:       v.getUint8(9),           // HRQ.*
    skin:            c(10),
    airC:            c(12),                   // air thermistor, outside the strap
    battery:         u(16, 1, 255),           // null = on USB power (always, on the power-bank build)
    activity:        u(17, 500, 255),         // g
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
  v.setInt16(12, _centi(f.airC), true);
  b[14] = 255;                    // reserved (was humidity)
  v.setInt8(15, -128);            // reserved (was evaporative headroom)
  b[16] = _none(f.battery) ? 255 : f.battery;
  b[17] = _u8(f.activity, 500, 255);
  b[18] = 0;                      // reserved (was HR sensor A)
  b[19] = 0;                      // reserved (was HR sensor B)
  return b;
}
