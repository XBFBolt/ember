/**
 * device.js — which source feeds the datastore: the demo, Bluetooth or USB.
 *
 * One source at a time. Switching starts a fresh session in the datastore.
 * The only thing the app ever sends back is a command (BASELINE), routed to
 * whichever source is active.
 *
 * A device that stays connected but stops sending (firmware stuck, power bank
 * off before the link times out) goes to 'stalled' after a few seconds, so
 * the last number is never left on screen as if it were live.
 */

import { ingestFrame, setSource, setLink } from './datastore.js';
import { bleAvailable, connectBle, disconnectBle, sendBleCommand } from './ble.js';
import { serialAvailable, connectSerial, disconnectSerial, sendSerialCommand } from './serial.js';
import { startSimulation, stopSimulation, simRunning, simCommand } from './sim.js';

const STALL_MS = 5_000;   // the device sends 1 frame a second: 5 missed in a row

let _active = 'none';     // 'none' | 'demo' | 'ble' | 'serial'
let _link   = 'off';      // mirror of the datastore's link state
let _lastFrameMs = 0;     // wall clock of the last device frame
let _watchdog = null;
let _fallback = false;    // restart the demo if this first connect fails

export { bleAvailable, serialAvailable };
export const activeSource = () => _active;

function _setLink(link) {
  _link = link;
  setLink(link);
}

/** Make `source` the active one, stopping whatever ran before. */
function _take(source) {
  if (_active === source) return;
  const prev = _active;
  _active = source;          // first, so the old source's 'off' callback is ignored
  if (prev === 'demo')   stopSimulation();
  if (prev === 'ble')    disconnectBle();
  if (prev === 'serial') disconnectSerial({ quiet: true });
  setSource(source);
}

function _callbacks(source) {
  _startWatchdog();
  let everUp = false;       // this connect attempt reached 'connected' at least once
  return {
    onFrame: f => {
      if (_active !== source) return;
      _lastFrameMs = Date.now();
      if (_link === 'stalled') _setLink('connected');
      ingestFrame(f);
    },
    onLink: link => {
      // The demo keeps running until a device is actually picked in the chooser.
      if (link === 'connecting' && _active !== source) {
        _fallback = _active === 'demo' && simRunning();
        _take(source);
      }
      if (_active !== source) return;
      if (link === 'connected') {
        everUp = true;
        _fallback = false;
        _lastFrameMs = Date.now();   // first frame due within a second
      }
      _setLink(link);
      // A first connect that failed (device off, out of range): back to the demo,
      // so the screen isn't left empty. The caller shows why in a toast.
      if (link === 'off' && !everUp && _fallback) {
        _fallback = false;
        startDemo();
      }
    },
  };
}

// Runs only while a device is the source
function _startWatchdog() {
  if (_watchdog) return;
  _watchdog = setInterval(() => {
    const device = _active === 'ble' || _active === 'serial';
    if (device && _link === 'connected' && Date.now() - _lastFrameMs > STALL_MS) _setLink('stalled');
  }, 1000);
}

function _stopWatchdog() {
  if (_watchdog) { clearInterval(_watchdog); _watchdog = null; }
}

/** Start the demo, or restart it after Stop demo (a fresh session: its clock starts over). */
export function startDemo() {
  _stopWatchdog();
  if (_active === 'demo' && simRunning()) return;
  if (_active === 'demo') setSource('demo', { fresh: true });
  else _take('demo');
  _setLink('connected');
  startSimulation((f, t) => { if (_active === 'demo') ingestFrame(f, t); });
}

/** Bluetooth (the worn demo). Call from a click. Rejects on cancel or failure. */
export function connectBluetooth() {
  return connectBle(_callbacks('ble'));
}

/** USB serial (bench). Call from a click. Rejects on cancel or failure. */
export function connectUsb() {
  return connectSerial(_callbacks('serial'));
}

export async function disconnect() {
  _fallback = false;        // a deliberate Disconnect stays disconnected
  _stopWatchdog();
  if (_active === 'ble')    disconnectBle();
  if (_active === 'serial') await disconnectSerial();
  if (_active === 'demo')   { stopSimulation(); _setLink('off'); }
}

/** Send a command (BASELINE, …) to the active source. */
export async function sendCommand(text) {
  if (_active === 'ble')    return sendBleCommand(text);
  if (_active === 'serial') return sendSerialCommand(text);
  if (_active === 'demo')   return simCommand(text);
  throw new Error('EMB.R is not connected.');
}
