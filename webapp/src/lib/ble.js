/**
 * ble.js — Web Bluetooth link to the Ember device (Chrome only).
 *
 * Connects to the device named "Ember", subscribes to the 1 Hz live frame and
 * writes ASCII commands. On an unexpected drop it reconnects by itself with
 * backoff, reusing the same device object so no chooser pops up. After a page
 * reload Chrome needs a new click in the chooser.
 *
 * Contract: docs/APP_INTERFACE.md. Decoding: frame.js.
 */

import { UUID, BLE_NAME, decodeFrame } from './frame.js';

const RETRY_MS = [1000, 2000, 4000, 8000, 15000];   // then every 15 s
const CONNECT_TIMEOUT_MS = 10_000;

let _device  = null;
let _live    = null;   // live-frame characteristic
let _cmd     = null;   // command characteristic
let _wanted  = false;  // user wants to stay connected (false after Disconnect)
let _timer   = null;
let _attempt = 0;
let _onFrame = () => {};
let _onLink  = () => {};

export function bleAvailable() {
  return typeof navigator !== 'undefined' && 'bluetooth' in navigator;
}

/**
 * Open the device chooser and connect. Must be called from a click.
 * onFrame(frame) gets every decoded frame; onLink(state) gets
 * 'connecting' | 'connected' | 'reconnecting' | 'off'.
 * Rejects if the user cancels the chooser or the first connect fails.
 */
export async function connectBle({ onFrame, onLink }) {
  if (!bleAvailable()) throw new Error('Bluetooth needs Chrome on a laptop or Android.');
  const device = await navigator.bluetooth.requestDevice({
    // Either matches: macOS can keep showing a board's old cached name after a
    // reflash, but the service UUID is always in the advertisement.
    filters: [{ name: BLE_NAME }, { services: [UUID.SVC] }],
    optionalServices: [UUID.SVC],
  });
  _stopRetry();
  if (_device && _device !== device) {
    _device.removeEventListener('gattserverdisconnected', _onDisconnected);
    if (_device.gatt.connected) _device.gatt.disconnect();
  }
  _device  = device;
  _onFrame = onFrame;
  _onLink  = onLink;
  _wanted  = true;
  _attempt = 0;
  _device.addEventListener('gattserverdisconnected', _onDisconnected);
  _onLink('connecting');
  try {
    await _open();
  } catch (err) {
    if (!_wanted) return;        // Disconnect pressed while connecting: not an error
    _wanted = false;
    _close();
    _onLink('off');
    throw err;
  }
}

/** User-initiated disconnect: no reconnecting afterwards. */
export function disconnectBle() {
  _wanted = false;
  _stopRetry();
  _close();
  _onLink('off');
}

/** Write an ASCII command (BASELINE, START, STOP, CAL, STATUS, ID). */
export async function sendBleCommand(text) {
  if (!_cmd || !_device?.gatt.connected) throw new Error('EMB.R is not connected.');
  const data = new TextEncoder().encode(text);
  if (_cmd.writeValueWithResponse) await _cmd.writeValueWithResponse(data);
  else await _cmd.writeValue(data);
}

// ─── internals ───────────────────────────────────────────────────────────────

async function _open() {
  const server = await _withTimeout(_device.gatt.connect(), CONNECT_TIMEOUT_MS, 'EMB.R did not answer.');
  const svc    = await server.getPrimaryService(UUID.SVC);
  const live   = await svc.getCharacteristic(UUID.LIVE);
  const cmd    = await svc.getCharacteristic(UUID.CMD);
  if (!_wanted) { _close(); return; }    // Disconnect pressed meanwhile: don't come back up
  if (_live) _live.removeEventListener('characteristicvaluechanged', _onValue);
  _live = live;
  _cmd  = cmd;
  _live.addEventListener('characteristicvaluechanged', _onValue);
  await _live.startNotifications();
  if (!_wanted) { _close(); return; }
  _attempt = 0;
  _onLink('connected');
}

function _close() {
  if (_live) _live.removeEventListener('characteristicvaluechanged', _onValue);
  _live = null;
  _cmd  = null;
  // Unconditional: disconnect() also aborts a connect() still pending (e.g. one
  // that timed out), so it can't finish later behind our back.
  try { _device?.gatt.disconnect(); } catch (_) { /* already gone */ }
}

function _onValue(e) {
  let f;
  try { f = decodeFrame(e.target.value); }
  catch (err) { console.warn('Ember: bad frame', err.message); return; }
  _onFrame(f);
}

function _onDisconnected() {
  _cmd = null;
  if (!_wanted) return;          // disconnectBle() already reported 'off'
  _onLink('reconnecting');
  if (!_timer) _scheduleRetry(); // a failed retry may have scheduled one already
}

function _scheduleRetry() {
  _stopRetry();
  const delay = RETRY_MS[Math.min(_attempt, RETRY_MS.length - 1)];
  _attempt++;
  _timer = setTimeout(async () => {
    _timer = null;
    if (!_wanted) return;
    try {
      await _open();
    } catch (err) {
      console.warn('Ember: reconnect failed:', err.message);
      if (!_wanted) return;
      _close();
      _onLink('reconnecting');
      if (!_timer) _scheduleRetry();
    }
  }, delay);
}

function _stopRetry() {
  if (_timer) { clearTimeout(_timer); _timer = null; }
}

function _withTimeout(promise, ms, message) {
  let t;
  return Promise.race([
    promise.finally(() => clearTimeout(t)),
    new Promise((_, reject) => { t = setTimeout(() => reject(new Error(message)), ms); }),
  ]);
}
