I'm continuing work on **Ember**, my team's project for the DS+X hackathon at Boston University (Oct 24–25, 2026, Health Hack track, also entered in Hackachusetts). Please pick up from here.

## What Ember is

A chest-strap device that estimates core body temperature from heart rate, and is honest about its uncertainty. A Polar H10 strap sends heart rate over Bluetooth to an ESP32-S3 pod (skin temp, under-shirt humidity, motion sensor, OLED). The firmware runs the published US Army ECTemp Kalman filter, shows a calibrated 90% range (conformal intervals, not the Kalman variance), and refuses to show a number when the sensors disagree. It streams CSV over USB serial to a laptop web app.

## Where the files are

My computer is linked; the project is at `/Users/dillon/Hackathon/ember/`:

- `TODO.md`: the working list, in three phases: **1. Interface → 2. Data → 3. Hookup.** We're in Phase 1. Ticked items are done.
- `webapp/`: the app being fixed. Plain ES modules, no build step. Open `index.html` over a local server (modules don't load from `file://`). Key files: `src/lib/datastore.js` (state, thresholds, `fmtC()`), `src/lib/serial.js` (Web Serial + demo simulation), `src/lib/estimator.js`, `src/views/PersonalView.js`, `CoachView.js`, `SupervisorView.js`, `src/styles/main.css`.
- `design-export/`: the reference HTML/CSS/JS for the final design.
- `firmware/ember_firmware.ino`, `firmware/conformal_table.h`, `analysis/` (Python), `docs/`: Phase 2, don't touch yet.

Read `TODO.md` first, then the webapp files you need.

## Decisions already made (don't reopen)

- **Thresholds:** Watch at estimate ≥ 38.0°C, Act now at ≥ 38.5°C. All UI text reads them from `THRESHOLDS` via `fmtC()`. No hardcoded threshold numbers in UI text.
- **Statuses:** OK, Watch, Act now, Paused (no number). Tags: "Low confidence" (firmware state not OK) and "No baseline yet" (flag 0x20). Never Paused at 38.0°C or above; show the number with Low confidence instead.
- **Paused messages (plain words):** flag 0x08 → "Heart rate signal lost. Check the strap is wet and snug."; flag 0x01 → "Your heart rate is up, but your body doesn't look like it's heating up."; otherwise → "Your sensors disagree right now."
- **Wording:** talk about heating up, never about sweat or evaporation. Don't show kPa anywhere.
- **Forecast:** a range ("about 10–25 min"), never a countdown like "4m 35s". Trend as a rate ("↑ 0.3° / 10 min").
- **Coach and Supervisor views are static examples**, labelled "Example team" / "Example crew". The Personal view is the live demo. Optional later: one live Supervisor event when the wearer hits Act now.
- **Design:** Inter font; ink #0B1B2B; OK light blue #EAF2FB / #0B5CAD; Watch solid amber #FFB020; Act now solid red #B42318; Paused slate #3A4B5C. Status block at the top of the phone screen, then the "Your plan" card (action, forecast, next break, water, buttons), then the 30-minute chart.
- **Break/water schedule** placeholders: 20 min on / 5 off, 250 ml every 15 min (to be replaced with a cited OSHA/NIOSH table later).

## Done so far (Oct 23)

- Thresholds switched to 38.0 / 38.5 and pulled from `THRESHOLDS` everywhere; range bar marks and labels positioned from CSS variables. Verified by temporarily setting Act now to 39.0: everything moved.
- Simulation climbs 36.8 → 38.7 by step 20, cools to 38.0 by step 30, then holds (no jump back). It always reports full confidence so Act now shows cleanly.
- Confidence goes low whenever the firmware state isn't OK.
- Coach sample statuses are derived from thresholds (3 Act now / 2 Watch / 6 OK / 1 Cannot estimate) and the text matches.
- Fixed a missing closing brace in `serial.js` that had made the app load blank.

## Next: Phase 1 "Personal view: bugs" in TODO.md, starting with

1. **"Start my break" stops working after switching views.** `_initButtons` in `PersonalView.js` adds a click listener to the shared `#view-container` on every mount and never removes it, so after Coach → Personal it starts and ends the break in one click. Also, it decides start/end by reading the button text; use `onBreak` from the datastore instead.
2. Forecast (`projectForward` only looks 5 min ahead, so it says "not expected this session" right before hitting Act now).
3. Trend uses 30 s of data; "since start" and the 30-min chart only cover 10 min / 3 min because history is 120 points at 5 s.
4. Fake ± fallback of 0.35 when missing; simulated ± is too narrow (should be 0.6–0.9 per `conformal_table.h`).
5. Then "Personal view: doesn't match the design", connection banner, Coach/Supervisor layout, and `?view=` in the URL, as listed in TODO.md.

## How I'd like you to work

- Make the changes directly in my webapp folder: copy files into your workspace, edit, test, write back. Check file modification times first, since I sometimes edit in Kiro in between.
- Test in a headless browser (serve the folder locally, phone width 390 px and desktop 1280 px, watch the simulation run). Syntax-check every module after editing.
- Tick items off in `TODO.md` as they're done.
- Keep replies short: what changed, what you checked, anything I need to decide.
- Phase 1 only. Don't touch the firmware, the analysis, or serial-connection logic until I say we're on Phase 2/3.
