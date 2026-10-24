# Ember

**An honest core-temperature estimator.**

Core body temperature is what defines heat stroke, and it cannot be measured
in the field without a swallowed pill or a rectal probe. The standard
workaround is to infer it from heart rate using a published Kalman filter.
Products ship this today.

The problem is that the published algorithm is considerably less reliable
than anyone using it believes, and the confidence number it displays is
close to meaningless. Ember is the version that tells the truth about that.

**Three things no shipping product does:**

1. **The interval is calibrated, not invented.** The ± on the screen is
   derived from measured errors against real rectal temperatures, and its
   coverage has been verified. The Kalman filter's own posterior variance —
   which is what everyone else displays — covered **26%** of the time when
   claiming 90% in our testing.
2. **It refuses.** When the signals disagree or the estimate falls outside
   the calibrated range, it shows `CANNOT ESTIMATE` and the reason.
3. **It checks the heart rate against the body.** Heart rate alone cannot
   tell heat from caffeine. Skin temperature and motion decide whether a
   high heart rate has a thermal explanation: a racing heart while sitting
   still with cool skin is not heat, and the device says so instead of
   showing a number. A third thermistor reads the air outside the strap.

---

## Start here, in this order

**1. Run the analysis tonight. No hardware, no downloads, ~2 minutes.**

```bash
cd analysis
pip install -r requirements.txt
python3 ectemp.py            # coefficient self-check
python3 conformal.py         # calibration self-test
python3 evaluate.py --synthetic
```

If `evaluate.py` prints its four result blocks and the coverage table shows
conformal tracking its nominal levels while the Kalman interval does not,
your environment is correct and everything downstream is hardware.

**2. Read `docs/SCIENCE.md`.** It is short and it is why this project is not
a reimplementation. Everyone on the team should read it before the event.

**3. Order parts from `docs/BOM.md`.** The MAX30205 ships slowest — order it
first. Buy **two** chest straps; the best demo needs a control subject.

**4. Build from `docs/BUILD_PLAN.md`.** Twelve numbered steps with gates.

**5. Get the real data and recalibrate.** PROSPIE, DOI
`10.17028/rd.lboro.26076577` — free, immediate download, 16 participants,
8 men and 8 women.

```bash
python3 evaluate.py --data "Prospie dataset_open access V3.xlsx"
python3 export_firmware_table.py --data "Prospie dataset_open access V3.xlsx"
```

That second command writes `conformal_table.h`. Copy it into `firmware/`
and reflash. The number on the display is now backed by real measurements.

---

## What is in this folder

```
README.md                      you are here
CAD_PROMPT.md                  paste into a CAD AI, with this zip attached

docs/
  BOM.md                       what to buy, with suppliers and why each part
  BUILD_PLAN.md                step-by-step assembly, 12 steps with gates
  SCIENCE.md                   the findings this project is built on

firmware/
  ember_firmware.ino           ESP32-S3: BLE heart rate, 3 sensors on I2C,
                               Kalman filter, confound detector, refusal mode
  conformal_table.h            GENERATED. Currently from synthetic data.
                               Regenerate from PROSPIE before you believe it.

analysis/
  ectemp.py                    reference Buller/USARIEM filter + self-check
  conformal.py                 stratified conformal intervals + coverage
  load_data.py                 PROSPIE loader + synthetic generator
  evaluate.py                  leave-one-subject-out, the four results
  export_firmware_table.py     writes conformal_table.h
  requirements.txt

figures/
  ember_results.png            the four-panel result figure
  ember_by_sex.png             per-subject accuracy by sex
```

---

## How the pieces connect

One elastic strap around the ribcage, two pods on it: the bought heart-rate
sensor, and the unit you build.

```
  Polar pod ──Bluetooth──┐          (bought, sealed, sternum centre)
                         ▼
  skin temp ──┐    ┌──────────────┐
  microclim ──┼I2C─►│   ESP32-S3   │──► OLED  (estimate + interval,
  motion   ───┘    │              │           or CANNOT ESTIMATE)
                   │  Kalman +    │──► buzzer
                   │  confound    │──► serial CSV log
                   │  detector    │
                   └──────▲───────┘
                            │
                   conformal_table.h
                            ▲
                            │  generated offline, once
                     ┌──────┴───────┐
                     │  PROSPIE     │  16 people, rectal reference
                     │  + Python    │  → measured error quantiles
                     └──────────────┘
```

The device itself runs no machine learning. It runs about ten lines of
arithmetic and a twelve-entry lookup table. **What makes it defensible is
not the hardware — it is that the number on the screen was calibrated
against sixteen real people and we can show the coverage.**

---

## Division of labour, if you are three people

- **Hardware:** BOM, wiring, I²C bring-up, enclosure, strap. Owns steps
  E-02 to E-06 in the build plan.
- **Firmware:** flashing, BLE strap pairing, confound thresholds, display.
  Owns E-04 to E-08.
- **Data:** PROSPIE download, the evaluation, the figures, the calibration
  table. Can start tonight and needs no hardware at all until E-09.

The data person is not blocked by anything. Start them now.

---

## The pitch, in four sentences

> Heat stroke is defined by core temperature, which cannot be measured in
> the field without swallowing a pill. The algorithm everyone uses instead
> was independently re-evaluated last year and scored a **negative R²** on
> one of two benchmark datasets, missing two thirds of dangerous readings —
> and the confidence interval it displays covers a quarter of what it
> claims.
>
> We built the honest version: a calibrated interval we measured, a refusal
> mode for the regime where the model is known to fail, three sensors that
> vote on whether a high heart rate is even thermal, and the first
> sex-stratified validation of the algorithm, on the only sex-balanced open
> dataset that exists.
>
> It runs on a thirty-dollar board. Here is the coverage table.

---

## Not a medical device

Bench demonstrator. Consenting adults only. We have no ground truth at the
event — ingestible pills are not hackathon equipment — so we validated the
*implementation* and the *calibration* against someone else's published
measurements, and nothing here is clinically validated. Say that out loud
before anyone asks; it makes you more credible, not less.

**Licences to know:** PROSPIE is CC BY-**NC** and blocks commercial use. The
Oxford-NIL reference repositories carry no licence file, which means all
rights reserved — read and cite, do not copy. The ECTemp method is patented
(US 10,702,165 B2), which is irrelevant for a hackathon and decisive for a
company.
