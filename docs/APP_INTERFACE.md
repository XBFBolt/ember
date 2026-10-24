# Ember ↔ app: the Bluetooth contract

Everything the app needs. The device does all the estimation; the app only
decodes one 20-byte frame a second and shows it honestly.

The reference implementation is `decode()` in `tools/ember_ble.py`. It is
tested against the firmware's encoder byte for byte (`--selftest`).

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
| 8 | uint8 | heart rate (fused) | bpm | `0` |
| 9 | uint8 | heart-rate quality | 0 none, 1 single sensor, 2 both agree, 3 sensors disagree | — |
| 10–11 | int16 | skin temperature | °C × 100 | `-32768` |
| 12–13 | int16 | microclimate temperature | °C × 100 | `-32768` |
| 14 | uint8 | microclimate humidity | % × 2 (0.5 % steps) | `255` |
| 15 | int8 | evaporative headroom | kPa × 20 (0.05 kPa steps) | `-128` |
| 16 | uint8 | battery | % | `255` = running on USB (the power-bank build always sends 255) |
| 17 | uint8 | activity | g × 500 (2 mg steps, saturates at 0.508 g) | `255` |
| 18 | uint8 | heart rate, sensor A | bpm | `0` |
| 19 | uint8 | heart rate, sensor B | bpm | `0` |

**When the state is REFUSE, bytes 2–4 arrive as "not available" on
purpose.** The device withholds the number; the app must not fill the gap
with the last good value.

**From 38.0 °C up the device never refuses** (firmware 2.1+). The worst
state there is CAUTION, and the frame always carries the number and ±.
If the heart rate is lost up there, the number holds, the ± widens a
little each minute, and the reason is "no trustworthy heart rate".

## Flags

What causes what:

- **REFUSE** (below 38.0 °C only): `STALE_HR`, or two or more doubts among
  `MOTIONLESS_TACHY`, `NO_THERMAL_LOAD`, `COOL_SKIN` (`EVAP_FAILING`
  cancels one doubt). The two skin doubts are only raised once the
  thermistors are calibrated (`CAL`); while `NOT_CALIBRATED` is set they
  never appear.
- **CAUTION**: one doubt, or any of `NO_BASELINE`, `BASELINE_RUNNING`,
  `PPG_SINGLE`, `PPG_DISAGREE`, `CADENCE_LOCK`.
- **Info only**, never change the state: `SKIN_DISAGREE`, `SKIN_SINGLE`,
  `NO_MICRO`, `LOW_BATT`, `NOT_CALIBRATED`.

| Bit | Name | What to tell the user |
|---|---|---|
| `0x0001` | MOTIONLESS_TACHY | high heart rate while still (not set within 10 min of moving, or at 38.0 °C and above) |
| `0x0002` | NO_THERMAL_LOAD | no thermal load |
| `0x0004` | COOL_SKIN | skin not warm |
| `0x0008` | STALE_HR | no trustworthy heart rate |
| `0x0010` | *reserved* | was WIDE_INTERVAL in 2.0; never set from 2.1. Ignore it |
| `0x0020` | NO_BASELINE | no baseline yet |
| `0x0040` | CADENCE_LOCK | a pulse sensor jumped to the step cadence, or matched it while disagreeing with the other sensor, and was dropped |
| `0x0080` | EVAP_FAILING | sweat cannot evaporate — a danger signal, not a doubt |
| `0x0100` | PPG_DISAGREE | the two pulse sensors disagree |
| `0x0200` | PPG_SINGLE | only one pulse sensor usable |
| `0x0400` | SKIN_DISAGREE | the two skin sensors disagree (info only) |
| `0x0800` | SKIN_SINGLE | one skin sensor is off the skin (info only) |
| `0x1000` | NO_MICRO | microclimate sensor missing (info only) |
| `0x2000` | LOW_BATT | battery low (info only) |
| `0x4000` | NOT_CALIBRATED | skin sensors not calibrated (info only) |
| `0x8000` | BASELINE_RUNNING | baseline in progress |

To show one reason, take the first set flag in this order (the same order
the firmware uses, info-only flags last): `0x0008, 0x0001, 0x0002, 0x0004,
0x0100, 0x0040, 0x0200, 0x8000, 0x0020, 0x0400, 0x4000, 0x1000`.

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

`EVAP_FAILING` deserves its own alert regardless of state: it means the air
against the skin is close to saturated and sweating has stopped cooling.

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
    skin: i16(10), microC: i16(12), microRh: u8(14, 2, 255),
    evap: v.getInt8(15) === -128 ? null : v.getInt8(15) / 20,
    battery: u8(16, 1, 255), activity: u8(17, 500, 255), hrA: u8(18, 1, 0), hrB: u8(19, 1, 0),
  };
}

// send a command
await (await svc.getCharacteristic(CMD)).writeValue(new TextEncoder().encode("BASELINE"));
```
