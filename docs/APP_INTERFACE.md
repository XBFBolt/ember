# Ember ↔ app: the Bluetooth contract

Everything the app needs. The device does all the estimation; the app only
decodes one 20-byte frame a second and shows it honestly.

The reference implementation is `decode()` in `tools/ember_ble.py`. It is
tested against the firmware's encoder byte for byte (`--selftest`). The
webapp's port is `decodeFrame()` in `webapp/src/lib/frame.js`, tested on the
same frames and against `ember_core.h` (`node --test tests/test_frame.mjs`).

This is the contract for **firmware 2.2 and 2.3** (hardware v5: one pulse
sensor, two skin thermistors, one air thermistor outside the strap, IMU; no
SHT40). The byte layout is unchanged from 2.1; the bytes that carried
humidity, evaporative headroom and the two per-sensor heart rates are now
reserved.

**2.3**: the core estimate in the frame includes the learned correction once
a baseline is captured, and the ± is from the matching (narrower) table.
Before the baseline both are the filter's own, exactly as in 2.2. The app
decodes and shows them the same way either way; it never recomputes them.

## Connection

| | |
|---|---|
| Advertised name | `Ember` |
| Service | `e3b10001-5a2f-4c8e-9b7d-656d62657200` |
| Live frame | `e3b10002-5a2f-4c8e-9b7d-656d62657200` — read + notify, 20 bytes, 1 Hz |
| Command | `e3b10003-5a2f-4c8e-9b7d-656d62657200` — write, ASCII text |

One central at a time. If the app cannot find the device, something else
(nRF Connect, the laptop script) is probably connected to it.

20 bytes fits the default BLE MTU, so nothing needs negotiating.

## The frame (little-endian)

| Byte | Type | Field | Scale | "Not available" |
|---|---|---|---|---|
| 0–1 | uint16 | sequence | +1 per frame, wraps | — |
| 2–3 | int16 | core temperature | °C × 100 | `-32768` |
| 4 | uint8 | interval half-width (±) | °C × 50 (0.02 °C steps) | `255` |
| 5 | uint8 | state | low nibble: 0 OK, 1 CAUTION, 2 REFUSE · bit 4: baseline running · bit 5: logging | — |
| 6–7 | uint16 | flags | bit field, below | — |
| 8 | uint8 | heart rate | bpm | `0` |
| 9 | uint8 | heart-rate quality | 0 none, 1 ok (2 and 3 were 2.1's two-sensor states; never sent) | — |
| 10–11 | int16 | skin temperature | °C × 100 | `-32768` |
| 12–13 | int16 | air temperature (thermistor C, outside the strap) | °C × 100 | `-32768` |
| 14 | uint8 | *reserved* (was humidity) | — | always `255` |
| 15 | int8 | *reserved* (was evaporative headroom) | — | always `-128` |
| 16 | uint8 | battery | % | `255` = running on USB (the power-bank build always sends 255) |
| 17 | uint8 | activity | g × 500 (2 mg steps, saturates at 0.508 g) | `255` |
| 18 | uint8 | *reserved* (was heart rate, sensor A) | — | always `0` |
| 19 | uint8 | *reserved* (was heart rate, sensor B) | — | always `0` |

The air temperature is the air near the body, for display. It feeds no
decision.

**When the state is REFUSE, bytes 2–4 arrive as "not available" on
purpose.** The device withholds the number; the app must not fill the gap
with the last good value.

**From 38.0 °C up the device never refuses** (firmware 2.1+). The worst
state there is CAUTION, and the frame always carries the number and ±.
If the heart rate is lost up there, the number holds, the ± widens a
little each minute, and the reason is "no trustworthy heart rate".

## Flags

What causes what:

- **REFUSE** (below 38.0 °C only): `STALE_HR`, or both doubts:
  `MOTIONLESS_TACHY` and `COOL_SKIN`. The skin doubt is only raised once
  the thermistors are calibrated (`CAL`); while `NOT_CALIBRATED` is set it
  never appears.
- **CAUTION**: one doubt, or any of `NO_BASELINE`, `BASELINE_RUNNING`,
  `CADENCE_LOCK`.
- **Info only**, never change the state: `SKIN_DISAGREE`, `SKIN_SINGLE`,
  `NO_AIR`, `LOW_BATT`, `NOT_CALIBRATED`.
- **Reserved**, never set: `0x0002` and `0x0080` (2.1's humidity-based
  "no thermal load" and "struggling to cool down"), `0x0010`, `0x0100`,
  `0x0200`.

| Bit | Name | What to tell the user |
|---|---|---|
| `0x0001` | MOTIONLESS_TACHY | high heart rate while still (not set within 10 min of moving, or at 38.0 °C and above) |
| `0x0002` | *reserved* | was NO_THERMAL_LOAD in 2.1 (needed humidity); never set from 2.2 |
| `0x0004` | COOL_SKIN | skin not warm |
| `0x0008` | STALE_HR | no trustworthy heart rate |
| `0x0010` | *reserved* | was WIDE_INTERVAL in 2.0; never set from 2.1. Ignore it |
| `0x0020` | NO_BASELINE | no baseline yet |
| `0x0040` | CADENCE_LOCK | the pulse jumped to the step cadence and was dropped |
| `0x0080` | *reserved* | was EVAP_FAILING in 2.1 (needed humidity); never set from 2.2 |
| `0x0100` | *reserved* | was PPG_DISAGREE in 2.1 (two pulse sensors); never set, never reuse |
| `0x0200` | *reserved* | was PPG_SINGLE in 2.1 (two pulse sensors); never set, never reuse |
| `0x0400` | SKIN_DISAGREE | the two skin sensors disagree (info only) |
| `0x0800` | SKIN_SINGLE | one skin sensor is off the skin (info only) |
| `0x1000` | NO_AIR | air thermistor not reading (info only; was NO_MICRO, the SHT40, in 2.1) |
| `0x2000` | LOW_BATT | battery low (info only) |
| `0x4000` | NOT_CALIBRATED | skin thermistors not calibrated (info only) |
| `0x8000` | BASELINE_RUNNING | baseline in progress |

To show one reason, take the first set flag in this order (the same order
the firmware uses, info-only flags last): `0x0008, 0x0001, 0x0004, 0x0040,
0x8000, 0x0020, 0x0400, 0x4000, 0x1000`.

## Commands

Write the ASCII text to the command characteristic. Same commands as the
serial port: `BASELINE`, `START`, `STOP`, `CAL`, `STATUS`, `ID`.
(Their text replies go to the serial port; the app sees their effect in the
state byte and flags.)

## Three rules for the display

1. **REFUSE** → show *Cannot estimate* and the reason. No number.
2. **CAUTION** → show the number, with the reason beside it.
3. **Always show the ± next to the number.** Never compute or show a Kalman
   variance: on PROSPIE (37 people, leave-one-subject-out) the published
   filter's own "90 %" range covered 34 % of the time. The ± in the frame
   is the calibrated one.

## Web Bluetooth (Chrome, no app store)

```js
const SVC = "e3b10001-5a2f-4c8e-9b7d-656d62657200";
const LIVE = "e3b10002-5a2f-4c8e-9b7d-656d62657200";
const CMD = "e3b10003-5a2f-4c8e-9b7d-656d62657200";

const dev = await navigator.bluetooth.requestDevice({ filters: [{ name: "Ember" }], optionalServices: [SVC] });
const svc = await (await dev.gatt.connect()).getPrimaryService(SVC);
const live = await svc.getCharacteristic(LIVE);
live.addEventListener("characteristicvaluechanged", e => show(decode(e.target.value)));
await live.startNotifications();

function decode(v) {                       // v: DataView, 20 bytes
  const i16 = o => { const x = v.getInt16(o, true); return x === -32768 ? null : x / 100; };
  const u8 = (o, s, none) => { const x = v.getUint8(o); return x === none ? null : x / s; };
  const st = v.getUint8(5);
  return {
    seq: v.getUint16(0, true), core: i16(2), half: u8(4, 50, 255),
    state: ["OK", "CAUTION", "REFUSE"][st & 0x0f], baseline: !!(st & 0x10), logging: !!(st & 0x20),
    flags: v.getUint16(6, true), hr: u8(8, 1, 0), hrQuality: v.getUint8(9),
    skin: i16(10), airC: i16(12),            // bytes 14, 15, 18, 19 reserved
    battery: u8(16, 1, 255), activity: u8(17, 500, 255),
  };
}

// send a command
await (await svc.getCharacteristic(CMD)).writeValue(new TextEncoder().encode("BASELINE"));
```
