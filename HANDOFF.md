# Ember handoff

I'm Dillon, continuing work on **Ember** for the DS+X hackathon at Boston University (Oct 24–25, 2026, Health Hack track, also entered in Hackachusetts). This is the starting point for an assistant picking the work up. Kiro loads the project instructions on its own; anyone else should read them first.

## Read first

1. `/Users/dillon/Hackathon/.kiro/steering/ember.md`: what Ember v2 is, the hardware, the Bluetooth contract, every UI decision, the rules, and the commands that check a change. It is the one place decisions live; don't reopen them.
2. `TODO.md`: the phases, what's done, what's next.
3. The Bluetooth contract: `docs/APP_INTERFACE.md`. Its two decoders, `decode()` in `tools/ember_ble.py` and `decodeFrame()` in `webapp/src/lib/frame.js`, must stay identical.

## Where we are (Oct 24, afternoon)

- **Done:** Phase 1 (interface), Phase 2 (data and judge results), Phase 3 (firmware v2.1 fixes). All firmware unit tests and the decoder self-test pass. The sketch type-checks on a laptop.
- **Firmware compiles for the ESP32-S3** (esp32 core 3.3.12 via the Arduino IDE's `arduino-cli`, both USB settings, no warnings), but hasn't run on a board yet.
- **Still open from Phase 3:** the team doesn't have the updated folder.
- **Phase 4 (Web Bluetooth hookup) is done in software:**
  - `frame.js` holds the decoder and encoder. `ble.js` does connect and auto-reconnect. `device.js` picks the source. The demo (`sim.js`) emits real frames through the same decoder. `datastore.ingestFrame` takes them, and the Personal view has the v2 states.
  - The Phase 3 review notes are all in, plus a second review pass. `node --test tests/test_frame.mjs tests/test_link.mjs` passes; the link test uses a fake Bluetooth device.
  - Not yet run against a real board. That check is the last Phase 4 item in TODO.
- **Next:** Phase 5, replay. Its first sub-item (raw bytes in `ember_ble.py --csv`) comes before anyone records.

## How I'd like you to work

- Edit the repo directly. Check file modification times before editing: I sometimes edit in Kiro, or in another session, in between.
- After every change, run the checks listed in the steering file (firmware tests, sketch type-check, `--selftest`, `node --check`, the app in a browser at 390 px and 1280 px).
- Firmware changes go in `ember_core.h` with a unit test. Don't touch `docs/BOM.md`.
- Tick items off in `TODO.md` as they're done.
- Keep replies short: what changed, what you checked, anything I need to decide.
