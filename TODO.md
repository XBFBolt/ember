# Ember TODO

**Hardware is now v5** (`wiring_v5.html`): one chest pulse sensor, two skin thermistors, one air thermistor outside the strap, IMU, ESP32-S3, power bank, **Bluetooth to the app**. The SHT40 and the second pulse sensor are gone (firmware 2.2, Phase 3b). No Polar, no OLED, no buzzer, no USB-serial in the worn demo.

Order: 1. Interface (done) → 2. Data → 3. Firmware v2 fixes → 4. Hookup → 5. Demo safety net → 6. Ethics and story → 7. Freeze and present.
**Software** = Dillon. **Hardware** = team.

## What "done" looks like on Sunday

- A judge watches a teammate wear Ember through rest → hard work → recovery, live on the projector (laptop, Chrome, Bluetooth). The number rises, Watch and Act now fire, and the ± is shown the whole time.
- When the sensors can't be trusted, the screen says so and why. It never hides the number at 38.0°C or above.
- One slide of real results from 37 people: Kalman's "90%" range covered 34% vs Ember's 89%; the learned correction (error 0.41 → 0.32 °C, Watch on in time 47 → 65 of 73); how late the alarm fires; men vs women.
- If anything fails on stage, replay a recorded real session in the same app, one click away.
- Clear limits: calibrated on chest heart-rate data, not pulse sensors; not a medical device.

---

## Phase 1 · Interface

### Decisions (made Oct 23)

- [x] **Thresholds: Watch 38.0°C, Act now 38.5°C**, everywhere. 38.5 is the firmware alert (`CT_ALERT_C`) and the ACGIH work limit; 38.0 is the evaluation's "elevated" cutoff and the WHO limit. Watch carries the safety load because the estimate lags.
  - [x] Change `datastore.js:13-14` to 38.0 / 38.5.
  - [x] Range bar labels back to "Watch 38°" / "Act 38.5°" (the marks are already at those positions).
  - [x] Replace every hardcoded "38.2" / "37.5" in Personal, Coach, Supervisor and forecast text.
  - [x] Change the simulation so it climbs past 38.5 (to about 38.7) and back, instead of lowering the thresholds to fit it.
- [x] **Paused vs Low confidence.**
  - Paused (no number): heart rate signal lost, or two or more sensor doubts.
  - Low confidence (number shown, tagged): one doubt, or no baseline yet.
  - Never Paused at 38.0°C or above; show the number with Low confidence instead.
  - Paused reasons, plain words only: "Heart rate signal lost. Check the strap is wet and snug." / "Your heart rate is up, but your body doesn't look like it's heating up." / "Your sensors disagree right now."
- [x] **Coach and Supervisor stay static.** Personal is the live demo. Static data must be consistent with the thresholds and clearly labelled as an example.

### Personal view: bugs

- [x] **"Start my break" stops working after switching views.** `_initButtons` adds a click listener to the shared `#view-container` on every mount and never removes it. Go Coach → Personal and press the button: two listeners fire, starting and ending the break at once. Attach to the view's own root, or remove the listener on unmount.
- [x] **The simulation loops every 2 minutes with a cliff.** At the end of the 30 steps it jumps from 38.4°C back to 36.8°C: status flips Act now → OK, the chart drops vertically, "since start" resets oddly, and an active break continues. Hold at the end, cool down gradually, or reset everything (history, elapsed, break) together.
- [x] **Forecast is wrong.** At 37.6°C and rising it says "Not expected to reach 38.2° this session", then reaches Act now about 7 minutes later. `projectForward` only looks 5 minutes ahead. Replace with a range from the last 10 minutes' trend ("about 10–25 min"), capped at 30 min, shown only when rising.
- [x] **Forecast format** is a countdown like "4m 35s". Use the agreed range wording.
- [x] **Trend uses 30 seconds of data** (last 6 points) and shows words only ("↑ Rising"). Use 10 minutes and show the rate ("↑ 0.3° / 10 min").
- [x] **"Since start" is really "since 10 minutes ago"**, and the "Last 30 min" chart shows about 3 minutes, because history holds 120 points at 5 s. Keep longer, per-minute history and store the starting value separately.
- [x] **± is made up when missing** (`PersonalView.js:71` falls back to 0.35). Show "—" instead.
- [x] **Simulated ± is too narrow** (0.3–0.4). Use the calibrated widths (0.6–0.9) so the demo shows what the real device will.
- [x] **Chart legend spacing**: "Skin 35.4 °C" has a gap. In `main.css`, change `.legend span` to `.legend > span`.
- [x] **Empty chart for the first minute.** Show "Collecting data…" until there are a few points.

### Personal view: doesn't match the design

- [x] **Remove the sweat wording**: the "Sweat not cooling" tag, the "Sweat is not cooling you" pause reason (`PersonalView.js:52, 253`) and the action text (`estimator.js:125`).
- [x] **Show "Low confidence"** when the firmware state is CAUTION (1). Currently ignored, even though the simulation sends it above 38.2.
- [x] **Add the "Setting up" state** (no-baseline flag 0x20) with the 5-minute countdown and a "Capture baseline" button. The button can be inert until Phase 3.
- [x] **Watch action is too weak.** "Reduce intensity and drink water" sits next to Break "Now" and Water "Now". Use the design copy: "You are heating up. Take your break now, not in 10 minutes."
- [x] **Act now contradicts itself.** The Break card says "Now · 5 min in shade" while the forecast says rest at least 15 minutes. Show "Stop now · 15+ min in shade".
- [x] **On a break, the "Next break" card shows the elapsed time** ("2m 10s") under the wrong label. Show "On break · 2 min" and how long is left.
- [x] **Water card**: add "last drink X min ago", and make "I drank" reset it.
- [x] **Placeholder schedule** (8 on / 5 off, water every 4 min) is tied to simulation speed. Replace with the real schedule once chosen, and drive it from real elapsed time.
- [x] **Name shows "You"**. Use the wearer's name.
- [x] **"Live · 0 min" while simulated.** Say "Demo" when simulating.
- [x] **"How sure is Ember?" goes nowhere.** Link it to a short screen with the coverage table.
- [x] **Footer says "on this phone"**, but in the demo the data is on the laptop. Reword.

### Connection banner

- [x] **Takes about 60 px above the status block on a phone** and wraps. Make it a small chip in the top bar, or move it to the bottom.
- [x] **"Disconnect" calls connect** (`index.html:102`). Toggle based on state.

### Coach view (static)

- [x] Fix the sample data to match 38.0 / 38.5: Alvarez 38.2 stays Watch; Nwosu, Patel, Moreau, Grant (37.5–37.8) stay OK; Okafor and Brooks stay Act now. Recheck tile counts and "Do this now" text.
- [x] **Label it as an example**: replace "12 straps live" with "Example team · 12 players", so judges don't think it's faked live data.
- [x] **Phone layout**: 2×2 tiles, two cards per row, Break plan above the players on small screens.
- [x] Buttons ("Call break now", "Keep schedule", "Mark done"): either remove them or give a small visible response (a toast) so a judge's click isn't met with nothing.
- [x] Same forecast wording as Personal ("about 10–20 min").

### Supervisor view (static)

- [x] Label it as an example ("Example crew").
- [x] **Phone layout**: put the 3 tiles in one row, or make them smaller.
- [x] "Call worker": remove, or show a toast.
- [x] Hardcoded times ("11:45", "in 12 min") are fine for a static example; just make them consistent with each other.
- [ ] Optional, only if time is left: when the live wearer hits Act now, add one event for them at the top of the list. It's the only way to show the privacy flow end to end (phone sees the number, supervisor sees only the alert).

### Whole app

- [x] **The view isn't in the URL.** Reloading always returns to Personal, and you can't open Coach on the projector and Personal on the phone. Support `?view=coach` (as in `design-export`).
- [x] Personal view: show the real weather if it loaded, otherwise hide the chip. Coach and Supervisor keep their static chips.

---

## Phase 2 · Data (tonight, Sat morning)

The data is PROSPIE V3 (Loughborough, CC BY-NC 4.0): 40 participants, 9 heat conditions, one row per minute, rectal core temperature. Loader checked Oct 23: correct columns, 9999 = missing, minutes kept contiguous, chest heart-rate sensors only (Equivital ECG + Polar; finger PPG excluded), participants 17 and 18 have conflicting sex codes so they're excluded from the by-sex analysis.

Reviewed Oct 24: evaluation now uses 6 strata, the same as the shipped table, so every judge number describes the calibration the device runs. All outputs regenerated.

- [x] Rerun `evaluate.py` (chest only, the default) with `--prefix ember_chest`, output in `analysis/results_chest.txt`. Also `--hr-types all --prefix ember_all` → `results_all_hr_types.txt`.
- [x] `export_firmware_table.py --out ../firmware/ember/conformal_table.h --js-out ../webapp/src/lib/conformal_table.js` writes both tables from one run (`CONF_SYNTHETIC` false). (Path updated in Phase 3; the table moved into the v2 firmware folder.)
- [x] Results for judges, LOSO only (`judges_results.py` → `judges_results.txt`, `JUDGES_SUMMARY.md`, `RESULTS_ONE_PAGER.md`):
  - [x] coverage of the 90% range: Kalman vs conformal (headline: 34% vs 90%; exact 34.3% vs 89.7%)
  - [x] coverage by true temperature band (<37.5, 37.5–38, 38–38.5, ≥38.5): 98 / 95 / 86 / 67%
  - [x] lag at the limits: when true core first hit 38.5, Watch was already on in 47/73 trials, Act now in 18/73; Act now never fired in 34/73; Watch was the only alert in 29/73, neither fired in 5/73
  - [x] men vs women: bias difference with bootstrap CI
  - [x] optional: rising vs steady coverage
- [x] Three figures (`figures/`, written by `make_judge_figures.py`): coverage bars (Kalman vs conformal), estimate vs true over one trial with the ± band, alert timing (already on / late / never). Large fonts, readable on a projector.
- [x] Oct 25: three more from the same script: `judges_rmse.png` (RMSE 0.405 → 0.318, HTT 0.490 → 0.395, better for 31/37 people), `judges_range.png` (promised vs delivered at 50/80/90/95 %; ± 0.17 Kalman / 0.67 filter alone / 0.49 Ember), `judges_early_warning.png` (trials lined up on true 38.5; Watch on in time 65/73, median 12 min ahead, 40/73 at least 10 min). The first three are unchanged.
- [x] Put the real headline numbers on the webapp "How sure is Ember?" sheet; remove the synthetic note.
- [ ] Optional: read the spreadsheet's red (interpolated) cells with openpyxl and report how many scored minutes were interpolated.

### Possible improvements (not scheduled)

The range under-covers when core rises fast (84.9%) and at true core ≥ 38.5 (67%), because the estimate lags and reads low.
- **Tried, doesn't help:** a separate ± while the estimate is rising. Rising coverage stayed at about 85% or dropped to 80%. The estimate isn't rising fast at the moments the truth is.
- **Helps a little:** a lopsided range, since misses are almost always on the high side: about 0.3° below the estimate and 0.85° above, instead of ± 0.7. Rising coverage 85.6%, coverage at ≥ 38.5 went from 67% to 73%, and the range is narrower overall. Cost: the device sends a low and a high instead of one ± (firmware, BLE frame, app).
- **The real fix is the lag itself**, in the filter, not the range. Out of scope for the hackathon.
- **The lag, partly fixed: learned correction (Oct 24).** Experiment: `analysis/learned_correction.py` → `learned_correction_results.txt` (7 variants). Shipped in Phase 2b below.

## Phase 2b · Learned correction (Oct 24, done in software)

A linear correction on top of ECTemp, from heart-rate features the device already has (filter estimate and its 10-min change, 5-min HR and its 10-min change, HR above BASELINE resting HR). Capped at ±1.0 °C. Off until BASELINE succeeds: then the device shows the filter alone with the 2.2 table.

- [x] `analysis/correction.py`: features defined exactly as the firmware computes them; nested LOSO (model and calibration never see the test person).
- [x] `export_firmware_table.py` writes coefficients + both tables (`CONF_*` corrected, `CONF_RAW_*` filter alone) to `firmware/ember/conformal_table.h` and `webapp/src/lib/conformal_table.js`, plus golden vectors `tests/correction_vectors.h`.
- [x] Firmware **2.3.0**: `struct Correction` in `ember_core.h`, stepped once a minute after the filter, reset on BASELINE; every decision (state, Watch rule, BASELINE allowed) uses the shown estimate. `STATUS` prints filter vs correction. Tests: 191 pass, including C == Python on the golden vectors. Sketch type-checks against the host stubs.
- [x] Webapp: demo uses the corrected ± after baseline, the 2.2 ± before; Coach ± from the table; "How sure" sheet explains the correction, all numbers from the generated table. Node tests 21/21.
- [x] Judge numbers regenerated (`evaluate.py`, `judges_results.py` section 7, figures with "filter alone" for comparison), `JUDGES_SUMMARY.md`, `RESULTS_ONE_PAGER.md`. Headline: Kalman 34% vs Ember **89%**; RMSE 0.41 → **0.32**; ± 0.67 → **0.49**; Watch on in time 47 → **65**/73; Act now never 34 → **27**; false Act now 13 → 13; better for 31/37 people; men vs women −0.06 [−0.16, +0.05].
- [ ] **Team reflashes 2.3.0.** `ID` shows "learned correction: off until BASELINE"; after BASELINE, `STATUS` shows "learned correction +x.xx C".
- [ ] On the device: run BASELINE, then check the ± in the app drops from ~0.6–0.8 to ~0.4–0.6.
- [ ] Re-record the replay session on 2.3 (old recordings carry 2.2 numbers).
- [ ] Optional: train on PROSPIE, test on the firefighter dataset (DOI 10.17632/7ghxcsd9sz.1) to answer "does it hold in general?".
- [x] Oct 25: external test on a second dataset instead (the firefighter set only has session-summary HR). HTT, DOI 10.17632/g5sb382smp.1, CC BY 4.0: 65 people (32 F, 33 M), 2 h walking in heat and thermoneutral, ingestible-pill core, HR every minute. `analysis/load_htt.py` (adapter; pill-artifact rules fixed before any model run), `analysis/external_test.py` → `external_htt_results.txt` / `.json`. Applies the shipped 2.3 calibration read straight from `conformal_table.h` (checked against the golden vectors), nothing refitted.
  - 90 % range covered **82.0 %** [77.5, 86.3 over people] vs 89.2 % on PROSPIE; Kalman "90 %" covered 26.7 % (34.3 % on PROSPIE). RMSE 0.40 (filter alone 0.49); correction better for 54/65 people. Coverage at true ≥ 38.5: 90.0 %.
  - The extra misses are over-reads (12.2 % too high vs 3.9 %), late in 2 h steady walks: HR keeps drifting up while core levels off. Under-reads, the dangerous side, 5.8 % vs 6.9 %. Cost: Act now false alarms in 25/82 calm trials (PROSPIE 13/55).
  - Pooling PROSPIE + HTT (plan step 3) is not done; it would change the shipped table.

## Phase 3 · Firmware v2 fixes (tonight, before the team flashes)

Copy `ember_v2/` into this repo (`firmware/ember/`, `tests/`, `tools/`, `cad/`, `docs/APP_INTERFACE.md`, guide). Retire `firmware/ember_firmware.ino`. Every fix goes in `ember_core.h` with a unit test; all tests must pass.

Done Oct 24: v2 copied in, `firmware/ember_firmware.ino` deleted, and the real Phase 2 table moved to `firmware/ember/conformal_table.h` (the v2 package shipped a synthetic one; names match). Firmware is now **v2.1** so `ID` shows whether the team flashed the fixed build.

- [x] **Never REFUSE at ≥ 38.0°C.** `stateFromFlags(flags, ctEst)`; from 38.0 (`CT_WATCH_C`) up the worst state is CAUTION, and the frame still carries the number and ± (inflated while coasting).
- [x] **Cadence check rejects real running heart rate.** At 160–180 steps/min the pulse genuinely matches cadence (the test suite's own example: HR 162.6 vs cadence 162). Only reject a channel when its heart rate jumped to cadence (vs the last minute's fused HR) or disagrees with the other channel, not just because the two match.
  - New `cadenceCheck()` runs on both channels before fusion. Jump = more than 15 bpm from the last good minute. With no recent good minute it still rejects, since bounce and heart look the same then.
  - [x] Fixed (review): one lost minute with the heart on the step rate left no reference, so every later second was rejected and the app went Paused mid-workout. `HrReference` now remembers the last good minute through up to 3 lost minutes. Unit test reproduces the stuck case.
  - **Hardware note:** an ECG chest strap (Polar H10 class) would remove this whole problem. It reads the heart's electrical signal, so the bounce can't fake a beat, and it matches the chest-ECG data the calibration came from. The v2 BOM is fixed for the hackathon, so this is software for now; worth it for any next version.
- [x] **Grace period for "high HR while still":** skip `F_MOTIONLESS_TACHY` for 10 min after the last activity, and whenever the estimate is ≥ 38.0.
  - "Activity" = smoothed activity ≥ `ACT_MOVING_G` (0.05 g), the same threshold the cadence check uses.
- [x] Remove the width-based refusal (`F_WIDE_INTERVAL`); keep bit 0x0010 reserved (`F_RESERVED_0010`). The leftover `REFUSE_ABOVE_C` and "should refuse" helper are gone from `export_firmware_table.py` and both generated tables (regenerated; the numbers didn't change).
- [x] Recheck which flags make CAUTION. Uncalibrated thermistors or a missing SHT40 shouldn't put the heart-rate estimate in Low confidence forever; make them info-only.
  - Info only now: `NOT_CALIBRATED`, `NO_MICRO`, `SKIN_DISAGREE` (and `SKIN_SINGLE`, `LOW_BATT` as before). CAUTION only from doubts about the heart rate or its starting point: `NO_BASELINE`, `BASELINE_RUNNING`, `PPG_SINGLE`, `PPG_DISAGREE`, `CADENCE_LOCK`, or one confound doubt.
  - Reason order changed so an info-only flag never masks the real reason. `ember_ble.py` and `APP_INTERFACE.md` match; `--selftest` now checks the order against `ember_core.h`.
- [x] Fixed (review): **no motion sensor made exercise look like sitting still.** Activity reads 0, so "high HR while still" fired for the whole workout. The stillness check now stands down when the IMU wasn't found at boot (no free flag bit to report it; `ID` and `SCAN` show it).
- [x] Fixed (review): **BASELINE at 38.0 or above** reset the estimate to ≤ 37.6 and hid it for a minute. The firmware now ignores BASELINE at or above 38.0, and cancels a baseline that ends there. The app side is in Phase 4.
- [x] Rebuild and run `tests/` (163 pass) and `tools/ember_ble.py --selftest` (passes). Sketch type-checks against the host stubs.
- [x] **Compiled for the ESP32-S3** on Dillon's Mac: esp32 core 3.3.12 via the Arduino IDE's `arduino-cli`, board `esp32:esp32:esp32s3`, both USB settings (CDC on boot off and on). No errors, no warnings, 48–49 % flash, 14 % RAM. One fix needed: core 3.3 uses NimBLE, which adds the notify descriptor itself and deprecates `BLE2902`, so that line is now Bluedroid-only. The guide now pins core 3.3.12. Not yet run on a board: the team's P0 flash is still the real test.
  - Recompile: `"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" compile --fqbn esp32:esp32:esp32s3 --warnings all firmware/ember`
- [x] Decided (review): **skin doubts before CAL.** Uncalibrated beads can read > 1 °C low, and skin fed two doubts (< 33 °C, < 31 °C), so a cool, dry room could pause a good estimate. Both options taken:
  - Firmware: no skin doubts until `CAL` has run. Cost: on an uncalibrated unit, "coffee at a desk" is one doubt (Low confidence), not two (Cannot estimate). `EVAP_FAILING` stays on.
  - Demo: `CAL` is a required step before recording or presenting (Phase 5 and 7), so the full Cannot estimate behaviour is live on stage.
- [ ] Send the team the updated folder.

## Phase 3b · Hardware v5: one pulse sensor, an air thermistor, no SHT40 (Oct 24)

Wiring in `wiring_v5.html`, `ember_schematic_v5.png`, `ember_protoboard_v5.png`. Pulse sensor B is gone, GPIO5 now reads air thermistor C (R3, hangs outside the strap), and the SHT40 is gone, so there is no humidity. Firmware is **2.2**.

- [x] **One pulse sensor.** `cadenceCheck()` takes one channel (jump test only; the "other sensor disagrees" test is gone), `fuseHr()` became `heartRateOf()`. HR quality is 0 none / 1 ok. `PPG_SINGLE` would have held Low confidence all session on 2.1; 0x0100 and 0x0200 are now reserved, never set.
  - The loss: nothing cross-checks the heart rate. Only the signal-quality gate and the cadence jump test are left, so step-ups or cycling (step rate far from heart rate) matter more for the demo.
- [x] **No humidity.** Evaporative headroom is gone, so `NO_THERMAL_LOAD` (0x0002) and `EVAP_FAILING` (0x0080) are reserved, never set. Doubts left: high HR while still, cool skin. Cannot estimate from doubts now needs both; on stage it realistically comes only from a lost pulse.
  - The app's "Your body is struggling to cool down" line and the EVAP doubt-cancel rule are gone.
- [x] **Air thermistor** on GPIO5: frame bytes 12–13 (was microclimate °C), `NO_AIR` 0x1000 (was `NO_MICRO`) when it isn't reading. Display only. The Personal view shows "Air near you 24°C" on the weather line.
- [x] **CAL without the SHT40:** `ntcCalibrate()` makes the three beads agree at room temperature (geometric mean of resistances, about ±0.6 °C absolute). Refuses if a bead is open, the beads are > 2.5 °C apart, or they agree on something that isn't room temperature (catches every fixed resistor being wrong). A board calibrated against the SHT40 under 2.1 keeps kA/kB and only calibrates C against them. New NVS keys `kC`, `calC`.
- [x] **Frame layout unchanged;** bytes 14, 15, 18, 19 reserved and sent as "none". CSV is 19 columns: `ms,hr,sqi,hr_q,step_hz,act_g,skinA,skinB,skin,skin_q,air_c,vbat,ct_est,ct_lo,ct_hi,kalman_half,filter_step,state,flags`.
- [x] Changed together: `ember_core.h`, `ember.ino`, `test_core.cpp`, `ember_ble.py`, `APP_INTERFACE.md`, `frame.js`, `serial.js`, `sim.js` (the Low confidence minute is now a cadence lock), `datastore.js`, `PersonalView.js`, `test_frame.mjs`, `test_link.mjs`, the steering file.
  - Checks: 167 core tests, sketch type-check, `--selftest` (reason order matches), 21 node tests (new: CSV header checked against `ember.ino`, a 2.1 CSV row is rejected).
- [x] ~~Build guide for v5~~ Dropped Oct 24: `guide/` and `docs/BUILD_GUIDE.md` deleted from the repo and its history (all branches).
- [ ] On the board: `SCAN` shows only 0x68; `TEMP` shows the air bead near room temperature; `CAL` passes; `ID` says v2.2.2 and "thermistor calibration: yes".
  - [x] Oct 24: on the demo board the thermistors read colder when heated: all three dividers are built upside down (thermistor on the 3V3 side). Fixed in firmware, not rewired: **2.2.1** flipped the air bead, **2.2.2** also skin A and B. `NTC_A_ON_TOP`, `NTC_B_ON_TOP`, `NTC_C_ON_TOP` (all 1) in `ember.ino` flip them with `ntcNodeMv()` (11 new unit tests, 178 pass, compiles for the S3). Set one to 0 if that divider is ever rewired to match the diagram. Rerun `CAL` after flashing: the stored calibration was taken the old way round.
  - Upside down, skin on the chest read below 28 °C, so skin always showed NONE before this fix. Recheck that `TEMP` shows `AGREED` on skin.
- [ ] Later (after the hackathon): an air-based "no thermal load" / "struggling to cool down" using skin vs air. PROSPIE has ambient and chest-skin columns to set the thresholds; reuse bits 0x0002 / 0x0080.

## Phase 4 · Hookup: webapp ↔ device over Bluetooth (tonight, Sat)

The device sends one 20-byte frame a second over BLE (`docs/APP_INTERFACE.md`). Chrome on the laptop connects with Web Bluetooth; no app store.

- [x] `src/lib/ble.js`: `connectBle()` (requestDevice name "Ember", service `e3b10001-…`), notifications on `…0002`, `sendCommand(text)` on `…0003`, auto-reconnect, disconnect handling.
  - Reconnects by itself after a drop (1, 2, 4, 8, then every 15 s) with the same device object, so no chooser. History is kept; Disconnect stops the retries.
  - `src/lib/device.js` picks the source (demo, Bluetooth or USB) and sends `BASELINE` to whichever is active.
  - `node --test tests/test_link.mjs` (2 pass, about 5 s) runs it against a fake `navigator.bluetooth`. Frames arrive and `BASELINE` is written. A drop goes to reconnecting and recovers on the second retry. No duplicate listeners, Disconnect stops the retries, and a failed first connect goes back to the demo. **Not yet run against a real board.**
  - Second pass (review), fixed:
    - After a reconnect, the last pre-drop number no longer shows as live; it waits for a fresh frame.
    - USB unplug now always closes the port. "Connected" is reported only after `START` is written, and `START` is resent if no header arrives.
    - Starting vs Paused no longer flickers on a single bad pulse second (a 10 s hold).
    - "Pulse found again" is no longer promised when two doubts will keep it paused.
    - A failed first connect goes back to the demo.
    - No spurious "Device Offline" event when switching from the demo.
    - The hero says "Connecting" on a first connect.
    - Start baseline ignores a double click.
    - The stall watchdog only runs while a device is the source.
  - Fixed (review): **Disconnect pressed while connecting** could still end up "connected" (the in-flight connect finished afterwards), or toast an error. It now stays off, quietly. A timed-out connect is aborted instead of left pending.
  - Fixed (review): the chooser also matches on the service UUID, not only the name "Ember", since macOS can keep a board's old cached name after a reflash.
  - Added (review): **stall watchdog** in `device.js`. A device that stays connected but sends nothing for 5 s (firmware stuck, power bank off before the link times out) goes to "No data": the number is taken off screen, as when Offline, and comes back with the next frame.
- [x] `decodeFrame(DataView)`, ported from `tools/ember_ble.py`; unit-test it against the self-test frames.
  - In `src/lib/frame.js` (pure, no DOM) with `encodeFrame` for the simulation. `node --test tests/test_frame.mjs` (17 pass): the 4 self-test frames, the firmware encoder's bytes, a round trip, flag bits, reason order and text against `ember_core.h`, the CSV path, and the datastore's Paused / Starting / reconnect rules.
- [x] `datastore.ingestFrame(f)`: timestamp on arrival (seq only counts while connected); a blank core on REFUSE means Paused; single ± (lo/hi = core ± half); flags are 16-bit; state bit 4 = baseline running.
  - `ingestFrame(f, t)`: `t` defaults to arrival time; the demo passes its own faster clock. `ingestRow` is gone.
  - `setSource()` / `setLink()` replace `setConnected` / `setSimulating`. A new source starts a fresh session, so demo history never mixes with the device's. The same source reconnecting keeps its history.
- [x] Personal view for v2:
  - [x] Paused message for 0x08: "Pulse signal lost. Press the sensors flat against your skin."
  - [x] "Setting up" countdown driven by the baseline-running bit (300 s), with "Start baseline" sending `BASELINE`
    - The frame has no progress field, so the countdown runs from the first frame with the bit. After a reconnect mid-baseline it restarts (approximate by up to the time disconnected).
  - [x] Only show the baseline button during setup, never mid-session. A mid-session baseline resets the estimate and hides it for a minute (the firmware already ignores it at 38.0 or above).
    - Offered only while `NO_BASELINE` is set, no baseline is running, and the estimate is below Watch (or still Starting). Disabled ("Baseline running") while it runs.
  - [x] "Starting…" for the first minute after connect or baseline (no number yet), not "signal lost"
    - Both arrive as a blank number with `STALE_HR`. The live heart-rate byte tells them apart (no timer, so a real loss is never hidden). A pulse with no number yet since the start or the last baseline shows Starting ("Getting a first reading"). A pulse mid-session shows Paused ("Pulse found again. The number comes back within a minute."). No pulse shows Paused ("Pulse signal lost…").
    - At 38.0 and up, a lost pulse arrives as CAUTION with the number held. The reason beside Low confidence says "pulse signal lost: showing the last estimate, the range is widening".
    - A failed baseline (the bit drops while `NO_BASELINE` stays set) says "Baseline didn't take. Check the sensors are flat against your skin, sit still and try again."
  - [x] show the CAUTION reason next to "Low confidence" (e.g. "one pulse sensor only")
    - Plain-words map in `PersonalView.js` (`CAUTION_TEXT`). The firmware strings stay in `frame.js` for the tests.
  - [x] 0x80: a calm "Your body is struggling to cool down" line, no sweat wording
    - Shown under the status whenever the flag is set, with a number or Paused.
  - [x] hide battery; optional "2 pulse sensors agree" from heart-rate quality
    - Battery is never shown. The heart-rate line says "2 sensors agree", "1 sensor" or "sensors disagree".
  - Also: an "Offline" hero when the link is down ("Lost the connection to Ember. Reconnecting…"). The last number is not left on screen, and heart rate, skin and motion show "—".
- [x] Connection chip: Bluetooth first; USB serial kept for the bench (parse the new 24-column CSV: `ct_lo`, `ct_hi`, `state`, `flags` 0x%04X, "nan").
  - Menu: Connect Ember (Bluetooth), Disconnect / Stop demo, USB cable (bench), Show demo (Restart demo once stopped). Chip: Demo, Bluetooth, USB, Connecting…, Reconnecting… / No data (blinking dot), Disconnected. Cancelling a chooser is silent; other errors get a toast.
  - Fixed (review): **Stop demo, then Show demo did nothing** until a page reload (`startDemo()` returned early because the demo was still the active source). Restart now works and starts a fresh session, since the demo's clock starts over.
  - USB: `csvLineToFrame()` in `serial.js` maps a row to the frame shape, half = (ct_hi − ct_lo) / 2, and blanks the number on REFUSE as the device does. `kalman_half` is ignored.
- [x] Simulation emits v2 frames through the same decoder, so the demo and the device share one code path. Stop it when a device connects.
  - Moved to `src/lib/sim.js`; it encodes each frame to bytes, then `decodeFrame()`s them. Same timeline as the device: Starting (1 min), No baseline yet (waits for Start baseline, starts itself after 2 min), Setting up (5 min), Starting (1 min), then the work bout to 38.7 °C and back to 38.0. One minute on one pulse sensor shows Low confidence. Still 7.5× speed.
  - It stops once a device is picked in the chooser, not before, so cancelling leaves the demo running.
- [x] Fixed (review): the 30-min chart drew a straight line across minutes with no number (Paused, disconnected), filling the gap visually. Lines and the range band now break there; skin carries on if it has values.
- [ ] On the real device: the same minute shows the same core, ±, state and reason in the app and on a second reader.
  - The device takes one Bluetooth connection at a time, so the app and `ember_ble.py` can't both be connected. Instead: app over Bluetooth, with `START` on the USB serial monitor at the same time. Compare the CSV's `ct_est`, `ct_hi − ct_est`, `state` and `flags` against the app.

## Phase 5 · Demo safety net (Sat)

- [ ] **Replay mode:** record frames to a file (`ember_ble.py --csv`) and play them back in the webapp at 1× or 10×. Button in the connection menu.
  - Before anyone records: `ember_ble.py --csv` should also save the raw 20 bytes per row (hex), so replay runs through `decodeFrame()` like the device and the demo. It should also flush every row and reconnect after a drop.
  - Replay can be one more source in `device.js`, calling `ingestFrame(decodeFrame(bytes), t)` with its own clock, the same way `sim.js` does.
  - [x] Oct 24, quick version (recording skipped): "Replay sample" in the connection menu plays `webapp/demo/resting_sample.csv` (the firmware's 19-column `START` CSV) at 1×, looping, through `csvLineToFrame` → `encodeFrame` → `decodeFrame` (`src/lib/replay.js`). Chip and hero say "Replay". The sample is **generated** (60 s, resting 20-year-old man, CAL and baseline done), not a recording: swap in a real `START` capture when there is one. No 10× yet.
- [ ] Record 2–3 real sessions with the team: 5 min baseline, 12 min hard work, 10 min recovery. Keep the best one in `demo/`.
  - **Run `CAL` first.** `ID` must say "thermistor calibration: yes"; until then the skin checks are off and "Cannot estimate" can't fire on skin.
  - Pick hard work whose step rate is far from the heart rate: step-ups around 100/min, or cycling. Running puts cadence and heart rate both near 160, the case where pulse sensors are easiest to fool.
- [ ] Bluetooth drop: the app shows "Disconnected · reconnecting", keeps history, resumes.
  - The software was built in Phase 4 ("Reconnecting…" chip, Offline hero, history kept, auto-reconnect) and tested against a fake device. Tick this once a real drop has been tested: walk out of range, or unplug the power bank, then come back.
- [ ] Load test: leave the app connected 30 min; no slowdown, no memory growth.
- [ ] Coach view (optional): show the live wearer as one player card; the rest stay static examples.
- [ ] Supervisor view (optional): live wearer's Act now appears as one event (no temperature shown).

## Phase 6 · Ethics, transparency, story (Sat evening)

- [ ] "About this data" panel: PROSPIE citation and licence, 37 people, chest heart rate, leave-one-subject-out, what the ± means.
- [ ] Limits stated in the app and slides: calibrated on chest heart rate, not pulse sensors; estimate lags true core (give the measured lag); not a medical device.
- [ ] Privacy: data stays on the device and laptop, nothing uploaded; supervisor sees alerts only. Check the webapp sends nothing anywhere except the optional weather lookup and the Emergency help chat (only what the user types, to Anthropic).
- [x] **Emergency help chat** (Oct 24): a button bottom-right on every view (on Personal, the bottom-right of the phone column, and the panel opens inside it) opens a heat-illness first-aid chat with Claude (`src/lib/assistant.js`, `src/views/HelpChat.js`). The 911 call bar and five first-aid steps are static text, so they show with no key or no internet. Starter taps ("They collapsed or seem confused", …), streaming replies, "New chat" clears without a reload. No device data is sent; the key is pasted into the panel and kept in memory only. Model `claude-sonnet-5-5`, low effort, no up-front thinking; retries once without those settings on HTTP 400. Checked in headless Chrome at 1280 and 390 px against a faked API stream.
  - [ ] Paste a real key on the presenting laptop and run one conversation before going on stage: not yet tested against the real API.
  - [ ] Have someone with first-aid training read the system prompt and the static steps.
- [ ] Fairness: show the men vs women result honestly, whatever it is.
- [ ] Docs: README, BOM, BUILD_PLAN describe v2 (HANDOFF and the Kiro steering file were brought up to v2.1 on Oct 24; `BOM.md` is marked frozen in the steering file, so decide before editing it); remove synthetic claims ("26%", "16 participants", "coverage verified"); soften SCIENCE.md "skin falls".
- [ ] Break schedule: pick a cited source (TB MED 507 or NIOSH 2016-106) or label 20/5 and 250 ml as placeholders on screen.

## Phase 7 · Freeze and present (Sun morning)

- [ ] Code freeze mid-morning; only demo-breaking bugs after.
- [ ] Slides (≤ 8): problem → why current estimates overclaim (34% vs 90%) → Ember → live demo → results → fairness and privacy → limits → ask.
- [ ] Backup video of the full demo; the replay file loaded and tested on the presenting laptop.
- [ ] Rehearse twice, once with someone new; time it.
- [ ] Presenting laptop: Chrome, Bluetooth on, webapp served locally, browser zoom set for the projector, notifications off.
- [ ] Demo unit: `ID` shows firmware v2.3 and "thermistor calibration: yes". If not, run `CAL` (P6) before going on stage.

## Hardware checkpoints the software depends on

- [ ] Fri night: v2 compiles and flashes (P0); phone or laptop sees "Ember" frames.
- [ ] Sat midday: breadboard gate passed (P2); the pulse sensor gives a steady heart rate (`HR` says OK) on a fingertip.
- [ ] Sat afternoon: worn test passed (P7); baseline succeeds; first app connection (P8).
- [ ] Sat afternoon, quick sanity check: pulse-sensor heart rate vs a smartwatch or a 30 s manual count, at rest and during work. Every 4 bpm off moves the estimate about 0.1 °C.
- [ ] Sat evening: demo session recorded for replay.

## Cut list (if behind, cut from the top)

Rising vs steady analysis → interpolated-cell count → live Coach/Supervisor → break-schedule citation (label as placeholder). Never cut: Phase 3 safety fixes, Bluetooth hookup, replay mode, the results slide.
