# Prompt for a CAD / visualisation AI

Copy everything below the line into the other AI, and attach the zip.

---

## Your role

You are a mechanical design engineer producing the physical design for a
wearable research device called **Ember**. The electronics, firmware and
data pipeline all work (attached). What does not exist is the enclosure,
the mounting method, or any visual explanation of how it goes together.
That is what I need from you.

I am an engineering student building this for a weekend hackathon. It must
be printable on a standard FDM printer (0.4 mm nozzle, PLA or PETG,
220 × 220 × 250 mm bed) and assemblable with hand tools, M2/M3 hardware and
hot-glue-level skill. Elegance matters less than something that survives a
stranger wearing it while doing burpees.

## Form factor — this is settled, design to it

**One unit, mounted on a chest strap.**

A commercial heart-rate sensor (Polar H10 class) is worn around the ribcage
on an elastic strap. That strap and its sealed pod are **bought, not
designed** — the pod sits at the centre of the sternum and broadcasts heart
rate over Bluetooth.

**Your job is the second body on that same strap:** the unit I build, also
against the chest, carrying all the other electronics. One strap, two pods.

Do not design an armband, a wristband, or anything on the forearm. Do not
redesign the Polar pod.

## What the device does, so the form follows it

Ember estimates **core body temperature** — the deep internal temperature
that defines heat stroke — without any invasive sensor. Core temperature
normally requires a swallowed telemetry pill or a rectal probe, neither of
which works on a roofer in July.

It infers core temperature from **heart rate over time**. Heart rate rises
as the body heats, so sustained elevation is evidence of a rising core. But
heart rate also rises from caffeine, anxiety, dehydration and illness — so
three more sensors decide **whether to believe the estimate**:

- **skin temperature** at the sternum
- **microclimate temperature and humidity** — the air trapped between the
  device and clothing
- **motion** — is the heart rate high from work, or high while sitting
  perfectly still (which means it is probably not heat)?

From skin temperature and microclimate humidity the firmware computes
**evaporative headroom**: the water-vapour pressure gradient driving sweat
evaporation. When it approaches zero, sweat cannot evaporate and the body
has lost its main cooling route. That is the actual mechanism of heat
strain, measured directly.

When the signals disagree, the screen shows **"CANNOT ESTIMATE"** and the
reason instead of a confident-looking number. That behaviour is the point
of the project, and the industrial design should read as an honest
instrument, not a consumer gadget.

## Who wears it

- Adults doing physical work in heat — construction, firefighting, sport,
  warehouse work.
- Worn continuously for 30 minutes to a full shift.
- 20–45 °C, **heavy sweating**, dust, repeated impacts, pulled on and off
  by the wearer.
- Worn against the skin of the chest, typically **under a t-shirt**, with
  the strap around the ribcage below the pectorals.

## Components to house — verify before committing

Typical module dimensions. Leave clearance; I will measure the real parts
with callipers and adjust.

| Component | Typical (mm) | Placement requirement |
|---|---|---|
| ESP32-S3 DevKitC-1 | 63 × 25.5 × 8 PCB, ~13 with headers | **USB-C must stay reachable with the case closed** |
| SSD1306 OLED 0.96" I²C | 27 × 27 × 4; active area 21.7 × 10.8 | faces **outward**, away from the body |
| MAX30205 skin temperature | ~25 × 15 × 3 | **flush with the back face, sprung against the sternum** |
| SHT40 microclimate T + RH | ~25 × 18 × 5 | **vented to the gap between the unit and clothing** |
| MPU-6050 IMU | 21 × 16 × 3 | rigid inside, must not rattle |
| LiPo 1000 mAh pouch (603450) | 50 × 34 × 6 | soft pouch; never compressed or pierced |
| TP4056 charger | 26 × 17 × 4 | charge port accessible |
| Piezo buzzer | 12 dia × 9 | needs a sound port |

Interconnect is four-wire I²C (SDA, SCL, 3V3, GND) daisy-chained between
boards, plus battery leads. Assume JST-PH connectors and 26 AWG silicone
wire.

## Hard constraints — these come from physics, not preference

Design around these first; getting any of them wrong breaks the project.

1. **The skin sensor must make flat, continuous, lightly sprung contact
   with the sternum.** An air gap makes it read somewhere between the
   person and the device. It needs compliant backing — foam or a printed
   leaf spring — so contact survives chest movement and breathing, and it
   must be **thermally decoupled from the enclosure**, because the ESP32
   self-heats and that heat must not conduct into the sensor.

2. **The microclimate sensor must sample the air between the device and
   clothing — not the inside of the sealed box, and not the skin.** It
   needs a vent path to that gap. This is the subtlest requirement in the
   build: the sensor must see freely exchanging microclimate air while
   staying out of the enclosure's own warm interior and off the skin
   surface. If it ends up measuring the ESP32 or the body, the evaporative
   headroom calculation becomes meaningless.

3. **The back face must match chest curvature.** A flat rigid brick against
   the sternum is painful within ten minutes and will bounce during
   exercise. Assume a gentle convex chest; a slight concave back face, or a
   compliant interface layer, or both.

4. **Low profile and low mass.** Anything that stands proud of the chest
   bounces, chafes under a shirt, and shifts the skin sensor off contact.
   Minimise thickness over everything except where the battery demands it.

5. **Sweat.** The torso is the worst place on the body for sweat. Not
   waterproof, but: no upward-facing openings, drainage paths at the lowest
   point, electronics raised off any surface where sweat can pool, and the
   microclimate vent designed so it admits vapour but sheds liquid.

6. **USB-C reachable with the device fully assembled and worn.** I reflash
   dozens of times during the build and at least once at the judging table.

7. **Battery swappable without a soldering iron**, and never compressed,
   folded or pierced by a screw boss.

8. **Strain relief on every wire at every board.** A jumper backing out of
   a header is the classic demo failure.

## Design questions I want you to actually answer, not skip

**How does it attach to the Polar strap?** The Polar pod uses two snap
studs on a ~25–30 mm wide elastic band. Options include matching studs, a
slide-on keeper the strap threads through, or a clamshell clip over the
band. Pick one, justify it, and make it **one-handed** — the wearer puts
this on themselves.

**Where on the strap, relative to the Polar pod?** The pod occupies the
sternum centre. Your unit goes beside it. Which side, how far, and does the
asymmetric mass matter when someone runs?

**One body or two?** Everything could sit in one enclosure, or the battery
could go in a third small pod on the opposite side of the strap to balance
the mass and halve the thickness of the main body. Argue for one.

**How is the screen read?** It faces outward, so it is readable by an
observer or by the wearer looking down when the strap is exposed, and not
at all under a shirt. Consider the viewing angle looking down at one's own
chest — the display may want to be tilted upward rather than lying flat
against the body. The wearer also gets a buzzer, and the device streams to
a laptop, so the screen is not the only channel.

## Deliverables

1. **A system diagram** — all components, which bus each sits on, power
   flow, and which sensor faces skin, microclimate, or outward. For my
   teammates and for a slide.

2. **A wear diagram** — a figure of a person showing the strap around the
   ribcage, the Polar pod, your unit beside it, where the skin sensor
   contacts, and where the microclimate vent opens. Label distances.

3. **The enclosure, as parametric CAD.** **OpenSCAD source is my first
   preference** — it is text, I can edit the dimensions myself, and it
   diffs in git. FreeCAD Python or CadQuery are acceptable. Include:
   - main housing with component pockets, screw bosses, display window
   - lid
   - the curved back face with the skin-sensor aperture and its compliant
     mount
   - the microclimate vent geometry
   - the strap attachment feature
   - battery pod, if you argue for two bodies
   - **every dimension as a named variable at the top of the file**

4. **An exploded assembly view** showing assembly order.

5. **Printing and assembly notes** — orientation per part, where supports
   are needed, layer height, infill, and the hardware list with screw sizes
   and lengths.

6. **A short list of your design decisions and why**, especially for the
   four questions above, the microclimate vent, and the skin-sensor
   compliance.

## Output preferences

- OpenSCAD as a complete, runnable file I can paste and render, not
  fragments.
- Diagrams as SVG, or clearly enough described that I can redraw them.
- Millimetres throughout.
- State assumptions explicitly where I have not given a dimension.
- If something I have asked for is mechanically unwise, say so and propose
  the alternative rather than quietly designing around it.

## What not to do

- Do not design the chest strap or the Polar pod. Both are bought.
- Do not design an armband or wrist unit. This is chest-mounted.
- Do not seal the microclimate sensor inside the enclosure, however neat
  that looks, and do not press it against skin.
- Do not require a resin printer, CNC, or injection moulding.
- Do not make it look like a consumer fitness tracker. It is a research
  instrument that admits when it does not know, and it should read that
  way.

## Context in the attached zip

- `README.md` — overview and how the pieces fit
- `docs/BOM.md` — exact parts list with suppliers
- `docs/BUILD_PLAN.md` — the assembly order I am working to
- `docs/SCIENCE.md` — why the device behaves the way it does
- `firmware/ember_firmware.ino` — the running firmware. **Pin assignments,
  I²C addresses, the display layout and the evaporative-headroom
  calculation are all in here and are authoritative.**
- `analysis/` — the Python that generates the calibration the device uses
