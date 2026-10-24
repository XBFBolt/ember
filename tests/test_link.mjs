// Link-layer tests for the webapp against a fake Web Bluetooth device
// (no browser, no board): connect, frames, BASELINE, drop and auto-reconnect,
// Disconnect, a failed first connect falling back to the demo.
// Takes about 5 s (real retry timers).
//
//   node --test tests/test_link.mjs          (from ember/)

import { test } from 'node:test';
import assert from 'node:assert/strict';

// ─── fake navigator.bluetooth ────────────────────────────────────────────────
const written = [];
let connectCalls = 0;
let failConnects = 0;     // the next N gatt.connect() calls reject
let lastOpts = null;

class FakeChar extends EventTarget {
  async startNotifications() { return this; }
  async writeValueWithResponse(d) { written.push(new TextDecoder().decode(d)); }
  emit(bytes) { this.value = new DataView(bytes.buffer); this.dispatchEvent(new Event('characteristicvaluechanged')); }
}
const live = new FakeChar();
const cmd = new FakeChar();
const device = new EventTarget();
device.gatt = {
  connected: false,
  async connect() {
    connectCalls++;
    if (failConnects > 0) { failConnects--; throw new Error('out of range'); }
    this.connected = true;
    return this;
  },
  async getPrimaryService() {
    return { getCharacteristic: async c => (c.startsWith('e3b10002') ? live : cmd) };
  },
  disconnect() {
    if (!this.connected) return;
    this.connected = false;
    queueMicrotask(() => device.dispatchEvent(new Event('gattserverdisconnected')));
  },
};
/** The radio drops: no disconnect() call from the app. */
function drop() {
  device.gatt.connected = false;
  device.dispatchEvent(new Event('gattserverdisconnected'));
}
Object.defineProperty(globalThis, 'navigator', {
  configurable: true,
  value: { bluetooth: { requestDevice: async opts => { lastOpts = opts; return device; } } },
});

const ds  = await import('../webapp/src/lib/datastore.js');
const dev = await import('../webapp/src/lib/device.js');
const { encodeFrame, STATE, FLAG, HRQ, UUID, BLE_NAME } = await import('../webapp/src/lib/frame.js');
const { stopSimulation } = await import('../webapp/src/lib/sim.js');

const sleep = ms => new Promise(r => setTimeout(r, ms));
const frame = (core, extra = {}) => encodeFrame({
  core, half: core === null ? null : 0.68, state: STATE.OK, flags: 0, hr: 120, hrQuality: HRQ.OK, ...extra,
});

test('Bluetooth: connect, frames, command, drop, reconnect, disconnect', async () => {
  dev.startDemo();
  assert.equal(ds.snapshot().source, 'demo');

  await dev.connectBluetooth();
  assert.deepEqual(lastOpts.filters, [{ name: BLE_NAME }, { services: [UUID.SVC] }]);
  assert.deepEqual(lastOpts.optionalServices, [UUID.SVC]);
  let s = ds.snapshot();
  assert.equal(s.source, 'ble');
  assert.equal(s.link, 'connected');
  assert.equal(s.history.length, 0, 'demo history cleared on switch');
  assert.equal(s.events.length, 0, 'no spurious offline event');

  live.emit(frame(37.4));
  live.emit(frame(37.5));
  assert.ok(Math.abs(ds.snapshot().latest.ctEst - 37.5) < 1e-9, 'frames reach the datastore');

  await dev.sendCommand('BASELINE');
  assert.equal(written.at(-1), 'BASELINE');

  // The radio drops; the first retry fails, the second succeeds
  failConnects = 1;
  const before = connectCalls;
  drop();
  s = ds.snapshot();
  assert.equal(s.link, 'reconnecting');
  assert.ok(s.history.length > 0, 'history kept through the drop');
  assert.equal(s.events[0]?.type, ds.EVENT_TYPE.DEVICE_OFFLINE);
  await assert.rejects(dev.sendCommand('BASELINE'), 'commands fail while disconnected');
  await sleep(1200);
  assert.equal(ds.snapshot().link, 'reconnecting');
  assert.equal(connectCalls, before + 1, 'first retry after ~1 s');
  await sleep(2200);
  assert.equal(ds.snapshot().link, 'connected', 'second retry after ~2 s');
  assert.equal(ds.snapshot().latest.ctEst, null, 'no stale number shown as live after reconnect');

  let n = 0;
  const unsub = ds.subscribe(() => n++);
  n = 0;
  live.emit(frame(null, { state: STATE.REFUSE, flags: FLAG.STALE_HR, hr: null }));
  unsub();
  assert.equal(n, 1, 'one update per frame after reconnect (no duplicate listeners)');
  assert.equal(ds.snapshot().latest.ctEst, null);
  assert.equal(ds.snapshot().latest.status, ds.STATUS.REFUSE);

  // Disconnect: off, and no more reconnect attempts
  const calls = connectCalls;
  await dev.disconnect();
  await sleep(1500);
  assert.equal(ds.snapshot().link, 'off');
  assert.equal(connectCalls, calls);
});

test('a failed first connect goes back to the demo', async () => {
  dev.startDemo();
  assert.equal(ds.snapshot().source, 'demo');
  failConnects = 1;
  await assert.rejects(dev.connectBluetooth(), /out of range/);
  const s = ds.snapshot();
  assert.equal(s.source, 'demo');
  assert.equal(s.link, 'connected');
  stopSimulation();
});
