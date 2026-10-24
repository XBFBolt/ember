# Ember enclosure v4 (power-bank build)

Three printed parts, all parametric in `ember_enclosure.py`.

    case      81 x 69 x 23.5 mm (109 mm including the strap loops)
    lid       flat, notched for USB
    pod       99.9 x 49.1 x 20.5 mm (128 mm with strap loops)
              pocket 94.9 x 44.1 mm for a 88.9 x 38.1 x 25.4 mm bank

## What changed from v3

- **No battery inside.** The deck under the protoboard drops from 7.5 to
  4.5 mm (room for wires, trimmed pins and the glue around the beads), and
  the case is 3 mm thinner. The internal height is now derived from the
  stack instead of typed in.
- **The pod.** An open-top tray with 3 mm of air on every side and walls
  about 70 % of the bank's height. Nothing is a press fit: the bank drops in,
  a hook-and-loop band through the two wall notches holds it, and it lifts
  out to charge. Cable notch at one end, thumb notch at the other, four
  drains, the same strap loops as the case.
- **Printing correction.** The body needs supports touching the build plate
  under its curved back. Earlier notes said it didn't; the scoop is a shallow
  overhang (about 10 degrees) that no printer bridges cleanly.

## The checks

`python3 ember_enclosure.py` prints two checks before exporting:

- **fit check** - board, DevKitC, IMU and the glue blobs against the case
  and each other, the USB cable path to either port, and at least 4 mm under
  the board.
- **pod check** - the bank against the pod, at least 2.5 mm of air all round
  (a fixed rule, not derived from the clearance you set), and at least 3 mm
  of bank above the walls for the band.

Both were negative-tested: too little pod clearance, walls too tall, a deck
too low and a lid notch too small each make them fail.

## Measure before printing

| Parameter | Default | What it is |
|---|---|---|
| `DECK_SPAN_X`, `DECK_SPAN_Y` | 64, 44 | protoboard corner holes, centre to centre |
| `DEV_USB_MARGIN` | 4.7 | J1 pin 22 centre to the DevKitC's USB-end edge |
| `BANK_L`, `BANK_W`, `BANK_T` | 88.9, 38.1, 25.4 | the power bank |

## Print

| Part | On the bed | Supports |
|---|---|---|
| Body | curved back | touching build plate only |
| Lid | flat top | none |
| Pod | floor | none |

0.2 mm layers, 3 walls, 25 % infill, PETG or PLA.

## Hardware

4 x M3 x 10 self-tapping (lid), 3 x M3 x 6 (protoboard: the DevKitC's USB
end covers the fourth hole, and that corner rests on its post).
