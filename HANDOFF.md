# Ember handoff

I'm Dillon, continuing work on **Ember** for the DS+X hackathon at Boston University (Oct 24–25, 2026, Health Hack track, also entered in Hackachusetts). This is the starting point for an assistant picking the work up. Kiro loads the project instructions on its own; anyone else should read them first.

## Read first

1. `/Users/dillon/Hackathon/.kiro/steering/ember.md`: what Ember v2 is, the hardware, the Bluetooth contract, every UI decision, the rules, and the commands that check a change. It is the one place decisions live; don't reopen them.
2. `TODO.md`: the phases, what's done, what's next.
3. For Phase 4: `docs/APP_INTERFACE.md` and `decode()` in `tools/ember_ble.py`.

## Where we are (Oct 24, afternoon)

- **Done:** Phase 1 (interface), Phase 2 (data and judge results), Phase 3 (firmware v2.1 fixes). All firmware unit tests and the decoder self-test pass. The sketch type-checks on a laptop.
- **Firmware compiles for the ESP32-S3** (esp32 core 3.3.12 via the Arduino IDE's `arduino-cli`, both USB settings, no warnings), but hasn't run on a board yet.
- **Still open from Phase 3:** the team doesn't have the updated folder.
- **Next:** Phase 4, the Web Bluetooth hookup (`webapp/src/lib/ble.js`, the decoder ported from `ember_ble.py`, `datastore.ingestFrame`, the Personal view's v2 states). Then Phase 5, replay.

## Phase 4 notes not yet in TODO.md

From the Phase 3 review:

- Decide Paused from the state byte or a blank number, never from flag 0x08. From 38.0 °C up, a lost pulse arrives as CAUTION with a held number and a widening ±, and needs its own wording ("Pulse signal lost. Showing the last estimate; the range is widening.").
- "Starting…" and "signal lost" both arrive as flag 0x08. Tell them apart with the live heart-rate byte: a heart rate means starting, none means lost. A timer after connecting would hide a real loss after a reconnect.
- A failed baseline has no signal of its own: the baseline bit drops and 0x20 stays set. Say so ("Baseline didn't take. Check the sensors and try again.").
- Before anyone records a session: `ember_ble.py --csv` should also save the raw 20 bytes per row (so replay uses the same decoder), flush every row, and reconnect after a drop.

## How I'd like you to work

- Edit the repo directly. Check file modification times before editing: I sometimes edit in Kiro, or in another session, in between.
- After every change, run the checks listed in the steering file (firmware tests, sketch type-check, `--selftest`, `node --check`, the app in a browser at 390 px and 1280 px).
- Firmware changes go in `ember_core.h` with a unit test. Don't touch `docs/BOM.md`.
- Tick items off in `TODO.md` as they're done.
- Keep replies short: what changed, what you checked, anything I need to decide.
