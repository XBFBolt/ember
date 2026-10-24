# Build plan

Twelve steps. The ones marked **GATE** are hard stops — do not move past
them, because everything after assumes they passed.

Rough total: **10–12 hours** including prints, spread across two days.
The data track (E-01, E-09, E-10) needs no hardware and can run in
parallel from the start.

---

### E-01 · Run the analysis before you own anything · 20 min

```bash
cd analysis
pip install -r requirements.txt
python3 ectemp.py
python3 conformal.py
python3 evaluate.py --synthetic
```

Expect: the coefficient self-check passes, and the coverage table shows the
conformal intervals tracking their nominal levels (≈0.50 / 0.80 / 0.90 /
0.95) while the Kalman intervals sit far below.

This step exists because published coefficients get transcribed wrongly — a
2024 peer-reviewed paper prints a core-temperature equation whose peak is
over 700 bpm. One arithmetic check catches it; a display never will.

**Do this on the train. It is the whole pipeline, proven, before you spend
a dollar.**

---

### E-02 · Verify the strap before anything else · 15 min

Install **nRF Connect** on a phone (free). Wet the two ribbed contact pads
on the underside of the strap, put it on, scan.

You should see the strap advertising the **Heart Rate service** and
streaming live values. That confirms it works, confirms it speaks the
standard protocol, and lets you watch the raw bytes your parsing code will
handle.

Three things that waste afternoons:
- **A strap holds one Bluetooth connection.** If a phone app is connected,
  your ESP32 will not find it. Close the app and forget the device.
- **Dry electrodes produce nothing** and look exactly like dead hardware.
- **A weak CR2032 causes intermittent dropouts** that look like a bug.

---

### E-03 · Toolchain · 20 min

Arduino IDE → Boards Manager → **esp32 by Espressif (3.x)**.

Library Manager, exactly these:
- NimBLE-Arduino (h2zero)
- Adafruit SSD1306, Adafruit GFX
- Adafruit SHT4x
- Adafruit MPU6050, Adafruit Unified Sensor

Board: **ESP32S3 Dev Module**. Set **USB CDC On Boot: Enabled** or you get
no serial output and will conclude the board is dead.

---

### E-04 · GATE · Breadboard the I²C bus · 1 h

Wire all four I²C devices on a breadboard. Everything shares `SDA = GPIO8`,
`SCL = GPIO9`, 3V3 and GND. Use a single star ground point, not a chain.

Flash `firmware/ember_firmware.ino`, open serial at 115200, send `SCAN`.

**All four addresses must appear: 0x3C, 0x44, 0x48, 0x68.** If one is
missing, fix it now — finding a cold joint later inside a sealed enclosure
costs hours.

---

### E-05 · GATE · End to end on a person, untethered · 45 min

Strap on and wet, board on battery, OLED showing a number that tracks a
real heart. Send `BASELINE` and sit still for five minutes.

Expect in order: coefficient check PASS, I²C scan with four devices,
`connected to Polar H10 ...`, then the baseline summary printing *this
wearer's* resting heart rate and the CT0 derived from it.

Do not start on the enclosure until this works.

---

### E-06 · Sensor placement · 1 h

This step is mostly physics, not assembly, and it decides whether the
confound detector means anything.

- **Skin sensor:** flush with the back face, sprung against the sternum
  with a few mm of foam behind it so contact survives breathing. Thermally
  decoupled from the enclosure.
- **Microclimate sensor:** vented to the gap between the unit and your
  shirt. **Not sealed inside the box** (it would read the self-heating
  ESP32) and **not against skin** (it would read you).
- **IMU:** rigid inside the enclosure. Orientation barely matters — we use
  the magnitude — but it must not rattle.

Sanity checks: hold the skin sensor and watch it climb to ~33 °C and
settle. Put the unit on under a shirt and watch `evap_kpa` fall as the
microclimate humidifies — that is the headroom closing, and it is the
single most interesting number the device produces.

---

### E-07 · Print and assemble the enclosure · 2 h + print time

Use the CAD output (see `CAD_PROMPT.md`). Start the print before you do
E-08; it is your longest pole.

Non-negotiables regardless of design:
- **USB-C reachable with the case closed.** You will reflash at the table.
- Battery swappable without a soldering iron.
- Strain relief on every wire at the board. A jumper backing out of a
  header is the classic demo failure.
- No upward-facing openings; sweat drains out, not in.

---

### E-08 · Tune the confound thresholds · 1 h

The defaults in the firmware are reasonable starting points, not truth.
Collect four short recordings and adjust:

| Recording | What it should produce |
|---|---|
| Sitting still, calm | `STATE_OK`, low heart rate, no flags |
| Sitting still after a coffee or two flights of stairs | `F_MOTIONLESS_TACHY` → refuse or caution |
| Working hard in a warm room | `STATE_OK`, estimate climbing |
| Working hard in a cold room / outdoors in winter | `F_NO_THERMAL_LOAD` → caution |
| Warm room, under a jacket, humid | `evap_kpa` falling toward `F_EVAP_FAILING` |

Edit the thresholds in `confoundFlags()`. Write down what you chose and
why — a judge will ask, and "we tuned it on four labelled recordings" is a
good answer.

---

### E-09 · GATE · Get the real data and recalibrate · 1.5 h

Download PROSPIE: **DOI `10.17028/rd.lboro.26076577`**. Free, immediate,
no application. 16 participants, 8 men and 8 women, 1-minute rectal
temperature with heart rate and full environmental conditions.

```bash
python3 evaluate.py --data "Prospie dataset_open access V3.xlsx"
python3 export_firmware_table.py --data "Prospie dataset_open access V3.xlsx"
cp conformal_table.h ../firmware/
```

The loader does fuzzy column matching and **prints the mapping it chose**.
Check it. It refuses to map anything containing "skin", "insulated",
"ambient" or "climatic" to the core-temperature slot, but a silent mix-up
here produces a beautiful, completely meaningless result.

Reflash. The ± on the display is now backed by real measurements, and the
header records the measured coverage in a comment.

---

### E-10 · The four results · 1.5 h

From the same run you now have everything for the presentation:

1. **Honest accuracy** — leave-one-subject-out RMSE next to the published
   figure and the independent benchmark.
2. **Calibration** — the coverage table. Kalman versus conformal versus
   nominal. This is the headline.
3. **Sex stratification** — bias and coverage by group with bootstrap
   intervals over subjects. Report **bias**, not RMSE: a systematic group
   offset moves bias and barely touches RMSE, so an audit run on RMSE will
   declare a biased model fair.
4. **Refusal** — the risk–coverage curve. Pick your operating point
   deliberately and be ready to defend it.

Figures land in `ember_results.png` and `ember_by_sex.png`.

---

### E-11 · Record the real bout · 45 min

Two volunteers, two straps, 25–30 minutes: 5 min seated rest (`BASELINE`),
12 min hard work, 10 min recovery. One volunteer sits through the whole
thing as a control.

Send `START` to begin logging, `STOP` at the end. Capture the serial CSV.

The chart that wins it: the core estimate climbing while **skin temperature
on the same screen goes down**, with the control subject flat beside it.
That single picture is the argument for why an estimator is needed at all.

---

### E-12 · GATE · Freeze, rehearse, parachute · 1.5 h

No commits after this.

- Charge everything, including spare CR2032s.
- **Record a backup video** of the demo working.
- Save one good CSV you can replay if the hardware dies.
- Rehearse three times, out loud, on the actual table.
- **Rehearse once with a stranger wearing it.** Strap position, skin contact
  and electrode wetting all behave differently on someone else, and a
  stranger is who will be wearing it when it counts.

Six slides: what core temperature is and why you cannot measure it · the
published algorithm and its independent re-evaluation · the device · the
coverage table · the sex-stratified result · what clinical validation would
require.
