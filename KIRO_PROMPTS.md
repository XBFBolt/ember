# Kiro prompts

Phase 2 is next. Phase 1 is done and kept at the bottom for reference.

---

# Phase 2 · Data (firmware + analysis)

Paste one at a time, in order. Check each before moving on.
Start every session with: **"Read TODO.md. We're doing Phase 2: firmware, analysis and docs. Don't change the webapp unless the prompt says so, and don't touch the serial-connection logic in `serial.js` or the firmware's `START`/CSV handshake. That's Phase 3."**

Decisions that still apply: Watch at 38.0°C, Act now at 38.5°C. Never show "can't estimate" at 38.0 or above. Talk about heating up, never sweat. No accuracy claims from synthetic data.

## A. Real data (do this first; you do step 1 by hand)

1. *(By hand)* Download PROSPIE from DOI `10.17028/rd.lboro.26076577` and put `Prospie dataset_open access V3.xlsx` in `analysis/`. Then `pip install -r analysis/requirements.txt`.
2. In `analysis/`, run `python3 evaluate.py --data "Prospie dataset_open access V3.xlsx" --no-plot` and show me the full output. Then check the printed column mapping and tell me, for each of `subject`, `sex`, `condition`, `minute`, `hr`, `core_c`, which spreadsheet column it picked and whether that's right. `core_c` must be rectal or gastrointestinal temperature, never skin or ambient. If anything is wrong, fix the patterns in `load_data.py` instead of renaming columns in the spreadsheet.
3. In `load_data.py`, after cleaning, print the median spacing between consecutive `minute` values within a trial. `evaluate.py` runs the filter with `step_seconds=60.0`, so the data must be one row per minute. If the spacing isn't 1 minute, stop and tell me; don't resample silently.
4. Run `python3 export_firmware_table.py --data "Prospie dataset_open access V3.xlsx" --out ../firmware/conformal_table.h`. Show me the new `CONF_EDGES`, `CONF_HALF` and measured coverage next to the old (synthetic) values. Make sure the header's "source data" line no longer says SYNTHETIC.

## B. Analysis additions (`evaluate.py`)

5. Add a "coverage by temperature band" table to `report()`: for the conformal 90% interval and the Kalman 90% interval, report coverage and sample count in bands of TRUE core temp: under 37.5, 37.5–38.0, 38.0–38.5, 38.5 and up. Use LOSO results only. Flag any band under 85% coverage or with fewer than 50 samples.
6. Add a "lag at the limits" table. For every trial where true core reaches 38.5°C, report how many minutes later the estimate reaches 38.0 (Watch) and 38.5 (Act now), or "never". Print the median, the worst case, and how many trials Watch fired before true core hit 38.5. This is the honest answer to "how late is the alarm?"
7. Split LOSO coverage by phase: rising (true core up more than 0.05°C over the previous 5 minutes) vs steady or falling. Print the 90% coverage for each. Don't change the calibration yet; just report it. If rising coverage is under 85%, tell me and propose (don't implement) stratifying by rising/steady as well as by predicted temperature.

## C. Firmware (`firmware/ember_firmware.ino`)

8. Run the Kalman filter once per minute, like the calibration does. Keep the 5 s loop for sensors, display, flags and CSV. Every 60 s, call `filterUpdate()` with the mean HR over the last 60 s and use `GAMMA_SQ_PER_MIN` directly as the process noise. If there was no HR that minute, add `GAMMA_SQ_PER_MIN` to `vv` instead. Increase the HR buffer from 64 to 128 entries so 60 s at ~1 Hz fits. Between updates, CSV and display keep showing the last estimate.
9. When the baseline sets the starting estimate (`captureBaseline`), clamp `ctFromHr(restHr)` to 36.4–37.6, exactly like `init_from_resting_hr()` in `analysis/ectemp.py`.
10. Remove the width-based refusal: delete the `F_WIDE_INTERVAL` check in `confoundFlags`, drop it from `stateFromFlags` and `flagReason`, and remove the "refuse when half-width" line from `printId()`. Keep the bit value 0x10 reserved (comment it) so old CSVs still parse. Leave `REFUSE_ABOVE_C` in the generated header, unused.
11. In `stateFromFlags`, pass in the estimate and never return `STATE_REFUSE` when it is 38.0°C or above; return `STATE_CAUTION` instead. This includes stale HR: the number stays on screen with a "?" and the reason.
12. "High HR while still" (`F_MOTIONLESS_TACHY`): track `lastActiveMs` (any 5 s step with `actRms > 0.35`). Skip this flag for 10 minutes after the last activity, and whenever the estimate is 38.0 or above. Someone who just stopped running has a high heart rate while still, and that is heat, not caffeine.
13. Buzzer: beep for Act now (estimate ≥ 38.5) in OK **or** CAUTION state. Right now it only beeps in OK, so a CAUTION at 38.6 is silent. Beep once on entering Act now, then at most once every 60 s while it lasts. Limit the low-cooling chirp (`F_EVAP_FAILING`) to once every 5 minutes. Make the "HOT" box on the OLED follow the same rule.
14. Compile it (Arduino IDE or `arduino-cli compile`) and fix every warning you introduced. Then list every change you made against prompts 8–13 so I can check them.

## D. Filters agree (Python vs firmware vs webapp)

15. Move `hrFromCt`, `dhrDct`, `ctFromHr`, `filterUpdate` and their constants from the `.ino` into `firmware/ectemp_core.h` as plain C (no Arduino calls, state passed by pointer). The `.ino` includes it and behaves the same.
16. Write `analysis/test_agreement.py`. It builds a fixed 90-minute HR series (rest 70 → ramp to 165 → hold → recover to 110, one value per minute, plus two missing minutes). It runs it through (a) `ectemp.run_series(step_seconds=60)`, (b) a tiny C program compiled with `cc` that includes `../firmware/ectemp_core.h`, and (c) `webapp/src/lib/estimator.js` via `node`. It fails if any minute differs by more than 0.01°C, and prints the worst difference. For (c), you may add an exported `runSeries(hrList, ct0, stepSeconds)` to `estimator.js` that uses the existing `filterStep` with a step-size parameter; don't change anything else in the webapp.
17. Run the test and show me the output. If it fails, find which implementation is wrong against Buller et al. 2013 (the constants in `ectemp.py`'s self-check) rather than tweaking tolerances.

## E. Carry the real calibration into the webapp

18. Make `export_firmware_table.py` also write `webapp/src/lib/conformal_table.js` with `CONF_EDGES`, `CONF_HALF`, `CONF_LEVEL`, `CONF_MEASURED_COV` and `CONF_SYNTHETIC` (true only with `--synthetic`). In `webapp/src/lib/estimator.js`, replace the hand-copied `CONF_EDGES` / `CONF_HALF` / `CONF_SYNTHETIC` with a re-export from that file. Rerun the export with the real data.
19. Open the webapp's "How sure is Ember?" sheet and check that the table shows the real widths and that the yellow "synthetic placeholder" note is gone. If the measured coverage is real now, add one sentence: "Tested on 16 people, the true value was inside the range X% of the time." Use the printed number and don't round up.

## F. Docs

20. `README.md`: the "26%" claim and "its coverage has been verified" come from synthetic data unless step A changed them. Replace them with the numbers from the real-data run, saying what they were measured on ("PROSPIE, 16 participants, leave-one-subject-out"). If you don't have real numbers yet, label them "synthetic test, not a result". Do the same in `docs/SCIENCE.md` (around line 84) and in the comments at the top of `ember_firmware.ino`.
21. `docs/SCIENCE.md` line 16: soften "skin temperature **falls**" to say skin temperature often stays flat or falls while core climbs, so it can't stand in for core. No bold, no absolute.
22. Search the repo for accuracy claims ("accurate", "verified", "validated", "proven", RMSE numbers, percentages) and list each with file and line. For each, say whether real data supports it now. Don't edit them; I'll decide.
23. Break schedule: I'll pick the source (e.g. US Army TB MED 507 work/rest and water table, or NIOSH 2016-106) and tell you the row. Then put the cited work/rest and water numbers in a `docs/SCHEDULE.md` with the citation. Only after that, update `SCHEDULE` at the top of `webapp/src/views/PersonalView.js` and the "20 on, 5 off" / "45 on, 15 off" text in Coach and Supervisor to match. Don't invent a schedule or a citation.

## Check prompts (use after each section)

- "Show me the diff for this section and confirm nothing in `webapp/` changed except what the prompt allowed."
- "Run `python3 ectemp.py`, `python3 conformal.py` and `python3 test_agreement.py` and show the output."
- "In the firmware, list every code path that can return STATE_REFUSE, and confirm none can fire with an estimate of 38.0 or above."
- "List every place the buzzer can sound and the most often each can repeat."
- "Search the repo for 'SYNTHETIC' and 'synthetic' and tell me which of those are still true."

---

# Phase 1 · Interface (done Oct 23, kept for reference)

Paste one at a time, in order. After each, run the app and check before moving on.
Start every session with: **"Read TODO.md. We're only doing Phase 1, interface. Don't touch serial.js, the firmware or the analysis folder."**

---

## 1. Thresholds (do this first)

1. In `webapp/src/lib/datastore.js`, set WATCH_C to 38.0 and ACT_NOW_C to 38.5. Remove the comment claiming they mirror the firmware and say they match CT_ALERT_C in the firmware instead.
2. Search the whole webapp for the strings "37.5" and "38.2" and replace them with values read from THRESHOLDS, so no threshold is hardcoded anywhere. List every file you changed.
3. In PersonalView's range bar, change the labels to "Watch 38°" and "Act 38.5°" and build them from THRESHOLDS. Make the mark positions in CSS come from the same values using the `--min`/`--max` scale, not fixed 50% / 62.5%.
4. In `serial.js` simulation only, change the trajectory so core temp rises from 36.8 to about 38.7 and then cools back to 37.5 over the 30 steps, with no jump at the end. Don't change anything else in serial.js.

## 2. Paused vs Low confidence

5. In `datastore.js`, add a `confidence` field to `latest`: 'low' when firmware state is 1 (CAUTION) or flag 0x20 is set, otherwise 'normal'. Never set status to REFUSE when ctEst ≥ 38.0; use the normal status with confidence 'low' instead.
6. In PersonalView, show the hero tag "Low confidence" when confidence is 'low', and "No baseline yet" when flag 0x20 is set. Hide it otherwise.
7. Replace `_pauseReason` in PersonalView with three plain messages: flag 0x08 → "Heart rate signal lost. Check the strap is wet and snug."; flag 0x01 → "Your heart rate is up, but your body doesn't look like it's heating up."; otherwise → "Your sensors disagree right now." Use the same text for the paused paragraph.
8. Remove every mention of sweat or evaporation from the UI text: the "Sweat not cooling" tag, the pause reason, and the line in `estimator.js` `recommendedAction`. Don't remove evapKpa from the data.

## 3. Break button bug

9. In PersonalView `_initButtons`, the click listener is added to the shared container on every mount and never removed, so it fires twice after switching views. Attach it to the view's own `.personal` root, or return a cleanup that removes it in the unmount function.
10. Don't decide break start/end by reading the button's text. Read `onBreak` from the latest datastore snapshot instead.

## 4. Forecast

11. Replace the forecast in PersonalView. Keep one sample per minute of ctEst, fit a straight line to the last 10 minutes, and if the slope is positive compute minutes until ACT_NOW_C. Show it as a range ("about 10–25 min") using ±40% of the estimate, rounded to 5 minutes, capped at 30 min.
12. If the slope isn't positive, show "Not expected to reach 38.5° at this pace". If there's less than 5 minutes of data, show "Forecast starts after 5 minutes". Remove `projectForward` and `formatCountdown` from the forecast path.

## 5. Trend, history and chart

13. In `datastore.js`, keep a second history of one point per minute (the mean of that minute's rows) for at least 60 minutes, alongside the existing 5 s ring buffer. Also store the first valid ctEst of the session as `sessionStartCt`.
14. In PersonalView, compute "since start" from `sessionStartCt`, and draw the "Last 30 min" chart from the per-minute history.
15. Replace `trendDirection` with a rate: change in ctEst over the last 10 minutes of per-minute history, shown as "↑ 0.3° / 10 min", "↓ 0.2° / 10 min" or "→ Steady" if under 0.1.
16. When the chart has fewer than 3 points, hide the lines and show "Collecting data…" in the chart area.
17. In `main.css`, change `.legend span` to `.legend > span` so the nested value span doesn't get a flex gap.

## 6. Honest ±

18. In PersonalView, if ctLo or ctHi is missing, show "—" for the ± and the likely range, and hide the range band. Don't fall back to 0.35.
19. In the simulation only, set the half-width from the estimate using the bands in `firmware/conformal_table.h` (0.59 below 37.27 up to 0.92 above 38.58), instead of a fixed 0.35.

## 7. Plan card copy

20. Update `recommendedAction` text: OK → "Keep going. You are on a safe pace."; Watch → "You are heating up. Take your break now, not in 10 minutes."; Act now → "You are too hot. Stop now and tell your coach."; Paused → "Sit for a few minutes. If you feel dizzy or sick, stop and tell someone."
21. In Act now, make the Break card show "Stop now" with "Shade or AC · 15+ min", and Water "Now" with "500 ml, in sips". It must not say "5 min in shade".
22. While on a break, label the break card "On break", show "2 min of 5" style progress, and change the primary button to "End my break".

## 8. Water and schedule

23. Make "I drank" record the time in the datastore and show "last drink X min ago" under the Water card. Reset the water countdown when pressed.
24. Replace the 8 on / 5 off and every-4-min water rules with constants at the top of PersonalView: 20 min on, 5 min off, 250 ml every 15 min. Drive them from session elapsed time, not simulation step count.

## 9. Small Personal fixes

25. Show a wearer name from a constant at the top of PersonalView (default "Maya Chen") instead of "You".
26. When `simulating` is true, the live pill should read "Demo · 8 min" instead of "Live · 8 min".
27. Change the footer to "Heart rate and history stay on your device. Not a medical device."
28. Make "How sure is Ember?" open a simple panel explaining the ± in two sentences, with a placeholder for the coverage table image `figures/ember_results.png`.

## 10. Connection banner

29. Shrink the connection banner into a small chip in the top bar showing a dot and "Demo" / "Connected" / "Not connected". Clicking it opens a small menu with Connect / Disconnect.
30. Make Disconnect actually call `disconnectSerial()`; only call `connectSerial()` when not connected.

## 11. Coach view (static)

31. In CoachView, recount the tiles from PLAYERS using THRESHOLDS so the counts always match the cards. Assign each player's status from their ct with the same rule as the datastore, except S. Kim stays 'paused'.
32. Replace "12 straps live" with "Example team · 12 players", and keep the rest of the header.
33. On screens under 600 px: show the tiles as a 2×2 grid, the player cards two per row, and move the Break plan card above the players.
34. Make "Call break now", "Keep schedule" and "Mark done" show a short toast ("Break called for the team") instead of doing nothing.
35. Change the Watch player notes to the range format: "38.5° in about 10–20 min".

## 12. Supervisor view (static)

36. In SupervisorView, change the page subtitle to start with "Example crew ·".
37. On screens under 600 px, put the three summary tiles in one row with smaller numbers.
38. Make "Call worker" show a toast ("Calling D. Reyes…"). Make sure "11:45" and "in 12 min" are consistent with each other.
39. Remove the duplicated click wiring: `mount` and `_rewire` contain the same code. Use one function.

## 13. Whole app

40. In `webapp/index.html`, read `?view=` on load to choose the view, and update the URL with `history.replaceState` when a tab is clicked, so reloading keeps the view and the projector can open `?view=coach`.
41. In PersonalView only, show the real weather from the datastore if it loaded, otherwise hide the weather line. Leave the Coach and Supervisor chips static.

## 14. Optional, if time is left

42. When the live wearer enters Act now, add one event for them at the top of the Supervisor events list using the datastore's events, with no temperature in the text. Keep the static events below it.

---

## Check prompts (use after each section)

- "Run through the simulation in Personal view and list anything that contradicts THRESHOLDS or the TODO decisions."
- "Search the webapp for any hardcoded temperature number in UI text and list them."
- "Show me every place a click listener is added and confirm each is removed on unmount."
- "Describe what Personal view shows in each state: OK, Watch, Act now, Paused, Low confidence, Setting up, On break."
