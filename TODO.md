# Ember TODO

**Hardware is now v2** (`ember_v2` package): two chest pulse sensors, two skin thermistors, SHT40 outside the case, IMU, ESP32-S3, power bank, **Bluetooth to the app**. No Polar, no OLED, no buzzer, no USB-serial in the worn demo.

Order: 1. Interface (done) → 2. Data → 3. Firmware v2 fixes → 4. Hookup → 5. Demo safety net → 6. Ethics and story → 7. Freeze and present.
**Software** = Dillon. **Hardware** = team, following the v2 build guide (P0–P9).

## What "done" looks like on Sunday

- A judge watches a teammate wear Ember through rest → hard work → recovery, live on the projector (laptop, Chrome, Bluetooth). The number rises, Watch and Act now fire, and the ± is shown the whole time.
- When the sensors can't be trusted, the screen says so and why. It never hides the number at 38.0°C or above.
- One slide of real results from 37 people: Kalman's "90%" range covered 34% vs Ember's 90%; how late the alarm fires; men vs women.
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

- [x] Rerun `evaluate.py` (chest only, the default) and save the output to `analysis/results_chest.txt`. Also run `--hr-types all` for comparison.
- [x] Rerun `export_firmware_table.py` writing to `firmware/ember/conformal_table.h`, and write the same table to `webapp/src/lib/conformal_table.js` (webapp imports it; set `CONF_SYNTHETIC` false).
- [x] Results for judges, LOSO only:
  - [x] coverage of the 90% range: Kalman vs conformal (headline: 33% vs 89%)
  - [x] coverage by true temperature band (<37.5, 37.5–38, 38–38.5, ≥38.5)
  - [x] lag at the limits: minutes from true core reaching 38.5 to Watch (38.0) and Act now (38.5) firing; how often Watch fired first
  - [x] men vs women: bias difference with bootstrap CI
  - [x] optional: rising vs steady coverage
- [x] Three figures (`figures/`): coverage bars (Kalman vs conformal), estimate vs true over one trial with the ± band, lag histogram. Large fonts, readable on a projector.
- [x] Put the real headline numbers on the webapp "How sure is Ember?" sheet; remove the synthetic note.
- [ ] Optional: read the spreadsheet's red (interpolated) cells with openpyxl and report how many scored minutes were interpolated.

## Phase 3 · Firmware v2 fixes (tonight, before the team flashes)

Copy `ember_v2/` into this repo (`firmware/ember/`, `tests/`, `tools/`, `cad/`, `docs/APP_INTERFACE.md`, guide). Retire `firmware/ember_firmware.ino`. Every fix goes in `ember_core.h` with a unit test; all tests must pass.

- [ ] **Never REFUSE at ≥ 38.0°C.** `stateFromFlags` takes the estimate; from 38.0 up the worst state is CAUTION, and the frame still carries the number and ± (inflated while coasting).
- [ ] **Cadence check rejects real running heart rate.** At 160–180 steps/min the pulse genuinely matches cadence (the test suite's own example: HR 162.6 vs cadence 162). Only reject a channel when its heart rate jumped to cadence (vs the last minute's fused HR) or disagrees with the other channel, not just because the two match.
- [ ] **Grace period for "high HR while still":** skip `F_MOTIONLESS_TACHY` for 10 min after the last activity, and whenever the estimate is ≥ 38.0.
- [ ] Remove the width-based refusal (`F_WIDE_INTERVAL`); keep bit 0x0010 reserved.
- [ ] Recheck which flags make CAUTION. Uncalibrated thermistors or a missing SHT40 shouldn't put the heart-rate estimate in Low confidence forever; make them info-only.
- [ ] Rebuild and run `tests/` and `tools/ember_ble.py --selftest`. Send the team the updated folder.

## Phase 4 · Hookup: webapp ↔ device over Bluetooth (tonight, Sat)

The device sends one 20-byte frame a second over BLE (`docs/APP_INTERFACE.md`). Chrome on the laptop connects with Web Bluetooth; no app store.

- [ ] `src/lib/ble.js`: `connectBle()` (requestDevice name "Ember", service `e3b10001-…`), notifications on `…0002`, `sendCommand(text)` on `…0003`, auto-reconnect, disconnect handling.
- [ ] `decodeFrame(DataView)`, ported from `tools/ember_ble.py`; unit-test it against the self-test frames.
- [ ] `datastore.ingestFrame(f)`: timestamp on arrival (seq only counts while connected); a blank core on REFUSE means Paused; single ± (lo/hi = core ± half); flags are 16-bit; state bit 4 = baseline running.
- [ ] Personal view for v2:
  - [ ] Paused message for 0x08: "Pulse signal lost. Press the sensors flat against your skin."
  - [ ] "Setting up" countdown driven by the baseline-running bit (300 s), with "Start baseline" sending `BASELINE`
  - [ ] "Starting…" for the first minute after connect or baseline (no number yet), not "signal lost"
  - [ ] show the CAUTION reason next to "Low confidence" (e.g. "one pulse sensor only")
  - [ ] 0x80: a calm "Your body is struggling to cool down" line, no sweat wording
  - [ ] hide battery; optional "2 pulse sensors agree" from heart-rate quality
- [ ] Connection chip: Bluetooth first; USB serial kept for the bench (parse the new 24-column CSV: `ct_lo`, `ct_hi`, `state`, `flags` 0x%04X, "nan").
- [ ] Simulation emits v2 frames through the same decoder, so the demo and the device share one code path. Stop it when a device connects.
- [ ] On the real device: same minute shows the same core, ±, state and reason in the app and in `ember_ble.py`.

## Phase 5 · Demo safety net (Sat)

- [ ] **Replay mode:** record frames to a file (`ember_ble.py --csv`) and play them back in the webapp at 1× or 10×. Button in the connection menu.
- [ ] Record 2–3 real sessions with the team: 5 min baseline, 12 min hard work, 10 min recovery. Keep the best one in `demo/`.
- [ ] Bluetooth drop: the app shows "Disconnected · reconnecting", keeps history, resumes.
- [ ] Load test: leave the app connected 30 min; no slowdown, no memory growth.
- [ ] Coach view (optional): show the live wearer as one player card; the rest stay static examples.
- [ ] Supervisor view (optional): live wearer's Act now appears as one event (no temperature shown).

## Phase 6 · Ethics, transparency, story (Sat evening)

- [ ] "About this data" panel: PROSPIE citation and licence, 37 people, chest heart rate, leave-one-subject-out, what the ± means.
- [ ] Limits stated in the app and slides: calibrated on chest heart rate, not pulse sensors; estimate lags true core (give the measured lag); not a medical device.
- [ ] Privacy: data stays on the device and laptop, nothing uploaded; supervisor sees alerts only. Check the webapp sends nothing anywhere except the optional weather lookup.
- [ ] Fairness: show the men vs women result honestly, whatever it is.
- [ ] Docs: README, HANDOFF, BOM, BUILD_PLAN describe v2; remove synthetic claims ("26%", "16 participants", "coverage verified"); soften SCIENCE.md "skin falls".
- [ ] Break schedule: pick a cited source (TB MED 507 or NIOSH 2016-106) or label 20/5 and 250 ml as placeholders on screen.

## Phase 7 · Freeze and present (Sun morning)

- [ ] Code freeze mid-morning; only demo-breaking bugs after.
- [ ] Slides (≤ 8): problem → why current estimates overclaim (34% vs 90%) → Ember → live demo → results → fairness and privacy → limits → ask.
- [ ] Backup video of the full demo; the replay file loaded and tested on the presenting laptop.
- [ ] Rehearse twice, once with someone new; time it.
- [ ] Presenting laptop: Chrome, Bluetooth on, webapp served locally, browser zoom set for the projector, notifications off.

## Hardware checkpoints the software depends on

- [ ] Fri night: v2 compiles and flashes (P0); phone or laptop sees "Ember" frames.
- [ ] Sat midday: breadboard gate passed (P2); both pulse sensors AGREED on fingertips.
- [ ] Sat afternoon: worn test passed (P7); baseline succeeds; first app connection (P8).
- [ ] Sat evening: demo session recorded for replay.

## Cut list (if behind, cut from the top)

Rising vs steady analysis → interpolated-cell count → live Coach/Supervisor → "2 sensors agree" display → break-schedule citation (label as placeholder). Never cut: Phase 3 safety fixes, Bluetooth hookup, replay mode, the results slide.
