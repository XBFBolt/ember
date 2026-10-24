# Bill of materials

US retail, October 2026. Prices are planning figures; part numbers are the
stable thing.

**Order the MAX30205 first** — it ships from Tindie and is the slowest item.
Everything else is Amazon next-day or Adafruit in 2–3 days.

---

## Heart rate — the primary signal

| Qty | Item | ~$ | Why this one |
|---|---|---|---|
| **2** | Polar H10 chest strap | 90 ea | The device published validation studies use as their *reference standard*. Our calibration came from data collected with chest-strap ECG, so matching that class of device is what keeps the calibration valid. That is a sentence you can say on stage. |
| | *or* Polar H9 | 60 ea | Same strap and electrodes, simpler electronics. The value pick. |
| | *or* COOSPO H808S | 28 ea | Works fine. Standard Heart Rate Service, which is all the firmware needs. |

**Buy two.** The strongest demo is two people — one working, one sitting as
a control — and the ESP32 can hold both Bluetooth connections at once.
Without a control subject your chart is just a line going up.

Also buy **spare CR2032 cells**. A weak cell causes intermittent dropouts
that look exactly like a firmware bug.

---

## The confound detector

This is what separates Ember from a reimplementation. Each sensor rules out
a different reason a heart rate might be high without heat being involved.

| Qty | Item | ~$ | Rules out |
|---|---|---|---|
| 1 | **MAX30205** body-temp breakout (ProtoCentral, Tindie) | 9 | Skin temperature, ±0.1 °C. High heart rate with cool skin in a cool room is not a heat story. |
| 1 | **Adafruit SHT40** temp + humidity, STEMMA QT | 8 | **Microclimate** — the air between the unit and your shirt. With skin temperature it gives *evaporative headroom*, the vapour-pressure gradient driving sweat evaporation. When that hits zero, cooling has failed. That is the mechanism of heat strain, measured directly. |
| 1 | **MPU-6050** IMU module | 6 | **The coffee detector.** High heart rate while sitting perfectly still is the signature of a non-thermal driver. Cheapest part, does the most work. |

**Substitutes if something is out of stock:**
- MAX30205 → **TMP117** (Adafruit, ±0.1 °C, easier to get). A DS18B20 works
  but is only ±0.5 °C and its probe is a cylinder, which makes poor flat
  contact with skin.
- SHT40 → **AHT20** ($4) or **BME280** ($8). Both fine.
  **A DS18B20 does not measure humidity** — it is temperature only.
- MPU-6050 → LSM6DSO, or any I²C accelerometer.

---

## The armband

| Qty | Item | ~$ | Notes |
|---|---|---|---|
| 1 | ESP32-S3 DevKitC-1 (N16R8) | 15 | BLE central, plenty of flash, good ADC. |
| 1 | SSD1306 OLED 128×64 I²C, 0.96" | 6 | Address is usually 0x3C, occasionally 0x3D. |
| 1 | LiPo 1000 mAh pouch (603450) | 8 | 50 × 34 × 6 mm. |
| 1 | TP4056 charger module **with protection** | 3 | Get the protected version, not the bare one. |
| 1 | Piezo buzzer, passive | 1 | Driven with `tone()`. |

---

## Build materials

| Item | ~$ |
|---|---|
| Perfboard, JST-PH connector kit, Dupont jumpers | 8 |
| 26 AWG silicone hook-up wire, heat-shrink | 4 |
| Kinesiology or medical tape (skin sensor) | 5 |
| PLA/PETG filament, elastic strap, hook-and-loop | 6 |
| M2 and M3 screws, heat-set inserts | 5 |

---

## Totals

| Configuration | Cost |
|---|---|
| Full build, 2× Polar H10 | **~$235** |
| Full build, 2× Polar H9 | **~$175** |
| Full build, 2× COOSPO | **~$110** |
| Single strap, budget sensors (DS18B20 + AHT20) | **~$78** |

If you cut, cut in this order: second strap last, **IMU never**. The IMU is
$6 and it answers the hardest question the project faces.

---

## Optional: $10 that turns a bad idea into a result

Buy one **MAX30102** optical pulse sensor. Do **not** use it as your heart
rate input — optical sensing fails exactly when someone is moving and
sweating, which is your entire demo, and feeding noisy heart rate into the
estimator would invalidate the calibration.

Use it as a deliberate experiment instead. Record the same bout twice, once
with the chest strap and once optically, and show how the estimate and its
interval degrade as input quality degrades — and the device noticing. That
is completely on-thesis and costs ten dollars and one extra recording.

The firmware already includes cadence-lock detection for this: motion
artifact appears at step frequency, so a reported heart rate near
60 × steps-per-second is an artifact, not a pulse.

---

## I²C bus — four devices, two pins, no conflicts

```
SSD1306   0x3C        SHT40      0x44
MAX30205  0x48        MPU-6050   0x68
```

All share `SDA = GPIO8`, `SCL = GPIO9`. Send `SCAN` over serial after
wiring; if all four addresses appear, the electrical build is done.

---

## Form factor and placement

**Everything lives in one unit on the chest strap**, beside the bought
heart-rate pod. Not an armband.

**The skin sensor sits flush with the back face**, sprung against the
sternum with compliant backing so contact survives breathing and movement,
and thermally decoupled from the enclosure so the ESP32's heat does not
conduct into it. Chest is a validated skin-temperature site — PROSPIE has a
chest skin-temp column, so the sensor site matches the calibration site.

**The microclimate sensor vents to the gap between the unit and your
shirt.** Not sealed inside the box (it would read the ESP32), not against
skin (it would read you). This is the subtlest mechanical requirement in
the build.
