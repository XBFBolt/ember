"""
Ember - chest-worn prototype enclosure, v4 (power-bank build).  Simple.

Three printed parts: a tub with a curved back, a flat lid, and a loose
pod that holds the power bank on the same strap.

WHAT THE CASE HOUSES, BOTTOM TO TOP
  floor          6.0 mm at the ends, 2.5 mm under the deepest part of the scoop
  under-deck     4.5 mm: only wires, the hot glue around the thermistor beads,
                 and trimmed pins. No battery any more.
  protoboard     70 x 50 x 1.6 on four posts, shifted 1.5 mm toward the USB end
  DevKitC-1      soldered straight into the protoboard (2.5 mm header spacer),
                 USB end facing -X, J1 header on the inner (+Y) side
  outside        2 x pulse sensor and the SHT40, on leads through the +Y slot
  in the floor   2 x thermistor bead, through the windows in the end pads
  power          a USB cable from the power bank into the notch at -X

THE POD
  An open-top tray for the power bank with 3 mm of air on every side and
  walls only ~70 % of the bank's height. Nothing about it is a press fit:
  the bank drops in, a hook-and-loop band around tray and bank keeps it
  there, and it lifts straight out to charge. It threads onto the chest
  strap with the same loops as the case and is worn at the side, under the
  arm, close to the case's USB end.

WHY v4 EXISTS
  The LiPo and charger are gone, so the battery deck drops from 7.5 to 4.5 mm
  and the case gets 3 mm thinner (23.5 mm). Everything that hung off the
  deck height - USB notch, cable slot, lid clearance - follows from the
  parameters below.

PRINTING - a correction to v3's notes
  The curved back is a shallow concave surface. Printed back-down, its middle
  starts 3.5 mm above the bed at a slope of about 10 degrees, which no printer
  bridges cleanly. Use supports touching the build plate only; they fill a
  3.5 mm sliver and pull off. The lid and the pod need no supports.

HUMAN-CENTRED DECISIONS
  - concave body-side face (R150) bridges the sternum; the flat end pads bear
  - thermistor windows are in those pads, the only part that touches skin
  - strap loops outside the box at body level: each strap end threads up
    through a loop from the skin side and folds back, so the pull stays at
    skin level and the case cannot tip
  - vents low on one wall, cable slot on the other with a drip loop, nothing
    else faces up; drains at cavity-floor level
  - USB-C reachable with the lid on
  - the heavy part (the bank) rides at the side, not on the breastbone

Run:  python3 ember_enclosure.py
"""

import cadquery as cq
from cadquery import exporters

# ----------------------------------------------------------------- params
WALL        = 2.5
LID         = 2.5

BOARD_X     = 70.0     # your protoboard
BOARD_Y     = 50.0
BOARD_T     = 1.6
BOARD_SHIFT_X = -1.5   # toward the USB end, for USB plug reach

CAV_X       = 76.0
CAV_Y       = 64.0

CHEST_R     = 150.0
SCOOP_D     = 3.5
FLOOR_MIN   = 2.5
FLOOR       = SCOOP_D + FLOOR_MIN            # 6.0

CORNER_R    = 6.0

# lid screws, in the long walls (the corners belong to the protoboard)
BOSS_D      = 7.0
BOSS_PILOT  = 2.6      # M3 self-tapping
BOSS_X      = 22.0
BOSS_Y      = 30.5
LID_HOLE    = 3.4
LID_LIP     = 1.2      # locating ring that drops into the cavity
LIP_RING    = 2.0      # ring wall thickness - hollow, so it clears the DevKitC
FIT         = 0.3

# deck posts: the protoboard screws onto these
DECK_H      = 4.5      # room under the board for wires, glue blobs, trimmed pins
DECK_D      = 6.0
DECK_PILOT  = 2.6      # M3; set 1.8 if your board's holes only pass M2
DECK_SPAN_X = 64.0     # MEASURE: centre-to-centre of your board's corner holes
DECK_SPAN_Y = 44.0

# DevKitC-1 on the protoboard
DEV_L       = 62.74    # board length (Espressif drawing)
DEV_W       = 25.40
DEV_Y       = -10.16   # its centreline: J3 on the outer hole row, J1 on the 9th
DEV_PIN22_X = -29.21   # J1-22 / J3-22 sit in the protoboard's -X end column
DEV_USB_MARGIN = 4.7   # MEASURE: J1-22 pin centre to the USB-end board edge
SPACER      = 2.5      # male-header plastic between protoboard and DevKitC
DEV_TOP     = 3.2      # tallest part on the DevKitC (the WROOM module)
USB_PORT_DY = 5.5      # the two USB-C ports, either side of the centreline (approx)
HEADROOM    = 1.6      # air between the DevKitC's tallest part and the lid

# the case's internal height follows from the stack, nothing hand-tuned
CAV_Z = DECK_H + BOARD_T + SPACER + 1.6 + DEV_TOP + HEADROOM

# ------------------------------------------------------------- power bank
BANK_L      = 88.9     # MEASURE: 3.5 in
BANK_W      = 38.1     #          1.5 in
BANK_T      = 25.4     #          1.0 in
POD_CLEAR   = 3.0      # air on every side, in plan. Loose on purpose.
POD_MIN_AIR = 2.5      # the rule the check enforces: never less air than this
POD_WALL    = 2.5
POD_FLOOR   = 2.5
POD_WALL_H  = 18.0     # wall height above the floor: ~70 % of the bank
POD_CORNER  = 6.0
POD_CABLE_W = 30.0     # open-topped notch at +X for the USB plug and cable
POD_CABLE_Z = 4.0      # notch bottom, above the pod floor
POD_THUMB_W = 26.0     # notch at -X to get a thumb under the bank
POD_THUMB_D = 10.0
POD_BAND_W  = 30.0     # notches in the long walls that locate the keeper band
POD_BAND_D  = 2.0
POD_DRAIN_D = 4.0
BANK_EDGE_R = 2.0      # power banks have rounded vertical edges; used in the check

# strap loops
LOOP_OUT    = 14.0
LOOP_W      = 32.0
LOOP_T      = 5.0
SLOT_X      = 4.0
SLOT_Y      = 28.0
SLOT_OFF    = 7.5

# USB opening: an open-topped notch in the -X wall plus a matching notch in
# the lid edge, wide enough for both ports and any cable's overmould.
USB_W       = 24.0
LID_USB_D   = 8.0   

VENT_N      = 5
VENT_L      = 11.0
VENT_W      = 1.8
VENT_PITCH  = 4.5
VENT_Z      = 6.0

CABLE_W     = 18.0     # +Y wall, ABOVE the deck, level with the protoboard top
CABLE_H     = 5.0

SKIN_D      = 4.0      # thermistor windows, in the flat end pads
SKIN_X      = (-35.0, 35.0)

DRAIN_D     = 2.5
DRAIN_Z     = 1.5
DRAIN_X     = (-33.0, 33.0)

# derived
OUT_X = CAV_X + 2 * WALL
OUT_Y = CAV_Y + 2 * WALL
OUT_Z = FLOOR + CAV_Z

Z_BOARD_BOT = FLOOR + DECK_H
Z_BOARD_TOP = Z_BOARD_BOT + BOARD_T
Z_DEV_PCB   = Z_BOARD_TOP + SPACER
Z_DEV_TOP   = Z_DEV_PCB + 1.6 + DEV_TOP
Z_USB       = Z_DEV_PCB + 1.6 + 1.6          # USB-C receptacle centre
USB_Z0      = Z_BOARD_TOP + 1.0              # bottom of the USB notch
CABLE_ZC    = Z_BOARD_TOP + 0.5 + CABLE_H / 2

DEV_X0 = DEV_PIN22_X + BOARD_SHIFT_X - DEV_USB_MARGIN   # USB-end edge
DEV_XC = DEV_X0 + DEV_L / 2

BOSS_PTS = [(x, y) for x in (-BOSS_X, BOSS_X) for y in (-BOSS_Y, BOSS_Y)]
DECK_PTS = [(x + BOARD_SHIFT_X, y)
            for x in (-DECK_SPAN_X / 2, DECK_SPAN_X / 2)
            for y in (-DECK_SPAN_Y / 2, DECK_SPAN_Y / 2)]


# ---------------------------------------------------------------- helpers

def rounded_box(x, y, z, r):
    return cq.Workplane("XY").rect(x, y).extrude(z).edges("|Z").fillet(r)


def box(x, y, z, cx, cy, z0):
    return cq.Workplane("XY").box(x, y, z, centered=(True, True, False)).translate((cx, cy, z0))


def post(x, y, z0, d, h, pilot, depth):
    p = cq.Workplane("XY").circle(d / 2).extrude(h).translate((x, y, z0))
    hole = (cq.Workplane("XY").circle(pilot / 2).extrude(depth + 1)
            .translate((x, y, z0 + h - depth)))
    return p, hole


# ------------------------------------------------------------------- body

def make_body():
    b = rounded_box(OUT_X, OUT_Y, OUT_Z, CORNER_R)
    b = b.cut(rounded_box(CAV_X, CAV_Y, CAV_Z + 2, 3.0).translate((0, 0, FLOOR)))

    holes = []
    for (x, y) in BOSS_PTS:
        p, h = post(x, y, FLOOR, BOSS_D, CAV_Z, BOSS_PILOT, CAV_Z - 1.0)
        b = b.union(p); holes.append(h)
    for (x, y) in DECK_PTS:
        p, h = post(x, y, FLOOR, DECK_D, DECK_H, DECK_PILOT, DECK_H - 1.5)
        b = b.union(p); holes.append(h)

    for sx in (-1, 1):
        b = b.union(rounded_box(LOOP_OUT * 2, LOOP_W, LOOP_T, 3.0)
                    .translate((sx * OUT_X / 2, 0, 0)))
        holes.append(box(SLOT_X, SLOT_Y, LOOP_T + 2, sx * (OUT_X / 2 + SLOT_OFF), 0, -1))
    for h in holes:
        b = b.cut(h)

    # chest scoop
    b = b.cut(cq.Workplane("XZ").center(0, SCOOP_D - CHEST_R)
              .circle(CHEST_R).extrude(OUT_Y, both=True))

    # USB notch, -X wall, open to the top
    b = b.cut(box(WALL * 4, USB_W, OUT_Z, -OUT_X / 2, DEV_Y, USB_Z0))

    # microclimate vents, -Y wall, low
    for i in range(VENT_N):
        x = (i - (VENT_N - 1) / 2.0) * VENT_PITCH
        b = b.cut(cq.Workplane("XZ").center(x, FLOOR + VENT_Z).rect(VENT_W, VENT_L)
                  .extrude(WALL * 6, both=True).translate((0, -OUT_Y / 2, 0)))

    # sensor leads, +Y wall, level with the top of the protoboard
    b = b.cut(cq.Workplane("XZ").center(0, CABLE_ZC).rect(CABLE_W, CABLE_H)
              .extrude(WALL * 6, both=True).translate((0, OUT_Y / 2, 0)))

    # thermistor windows through the end pads
    for sx in SKIN_X:
        b = b.cut(cq.Workplane("XY").circle(SKIN_D / 2).extrude(FLOOR + 2)
                  .translate((sx, 0, -1)))

    # drains
    for sy in (-1, 1):
        for dx in DRAIN_X:
            b = b.cut(cq.Workplane("XZ").center(dx, FLOOR + DRAIN_Z).circle(DRAIN_D / 2)
                      .extrude(WALL * 6, both=True).translate((0, sy * OUT_Y / 2, 0)))
    return b


# -------------------------------------------------------------------- lid

def make_lid():
    l = rounded_box(OUT_X, OUT_Y, LID, CORNER_R)
    ring_o = rounded_box(CAV_X - 2 * FIT, CAV_Y - 2 * FIT, LID_LIP, 3.0)
    ring_i = rounded_box(CAV_X - 2 * FIT - 2 * LIP_RING, CAV_Y - 2 * FIT - 2 * LIP_RING,
                         LID_LIP + 0.2, 2.0).translate((0, 0, -0.1))
    l = l.union(ring_o.cut(ring_i).translate((0, 0, -LID_LIP)))
    for (x, y) in BOSS_PTS:
        l = l.cut(cq.Workplane("XY").circle(BOSS_D / 2 + 0.6).extrude(LID_LIP + 0.01)
                  .translate((x, y, -LID_LIP)))
        l = l.cut(cq.Workplane("XY").circle(LID_HOLE / 2).extrude(LID + LID_LIP + 2)
                  .translate((x, y, -LID_LIP - 1)))
    # USB notch in the lid edge, matching the wall
    l = l.cut(box(LID_USB_D * 2, USB_W, LID + LID_LIP + 2, -OUT_X / 2, DEV_Y, -LID_LIP - 1))
    return l


# ----------------------------------------------------------------- checks

def self_check(body, lid):
    """Do the parts fit, and can a USB cable reach the port?"""
    solid = body.val()
    lid_on = lid.translate((0, 0, OUT_Z)).val()
    imu_x0 = DEV_PIN22_X + BOARD_SHIFT_X + 2 * 2.54 - 1.3   # header starts at column 2
    parts = {
        "protoboard":   (BOARD_X, BOARD_Y, BOARD_T, BOARD_SHIFT_X, 0, Z_BOARD_BOT),
        "DevKitC-1":    (DEV_L, DEV_W, Z_DEV_TOP - Z_BOARD_TOP, DEV_XC, DEV_Y, Z_BOARD_TOP),
        "IMU GY-521":   (20.3, 15.6, 5.1, imu_x0 + 10.15, 15.1, Z_BOARD_TOP),
        # hot glue that seats each bead, as it really ends up: a blob up to
        # 3 mm tall filling the corner between window and end wall
        "glue, bead B": (6.0, 10.0, 3.0, SKIN_X[0], 0, FLOOR),
        "glue, bead A": (6.0, 10.0, 3.0, SKIN_X[1], 0, FLOOR),
    }
    ok = True
    print("  fit check:")
    envs = {}
    for name, (x, y, z, cx, cy, z0) in parts.items():
        env = box(x, y, z, cx, cy, z0).val()
        envs[name] = env
        clash = solid.intersect(env).Volume() + lid_on.intersect(env).Volume()
        bad = clash > 1e-6
        ok &= not bad
        print(f"    {name:<13} {x:>5.1f} x {y:>5.1f} x {z:>4.1f}   "
              + (f"CLASH with case {clash:.0f} mm^3" if bad else "clear of case"))

    # ...and with each other: the battery under the deck, the IMU beside
    # the DevKitC. (The first version of this check only compared parts to
    # the printed solid, and a deliberately-too-low deck passed it.)
    names = list(envs)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            v = envs[names[i]].intersect(envs[names[j]]).Volume()
            if v > 1e-6:
                ok = False
                print(f"    *** {names[i]} overlaps {names[j]} by {v:.0f} mm^3")

    # USB: a cable overmould (12.5 x 7.5) must travel from 10 mm outside the
    # case all the way to the receptacle face, for either port.
    reach = (-OUT_X / 2) - DEV_X0
    x_out = -OUT_X / 2 - 10.0
    x_in = DEV_X0 - 0.01
    for name, dy in (("USB port 1", -USB_PORT_DY), ("USB port 2", USB_PORT_DY)):
        plug = box(x_in - x_out, 12.5, 7.5, (x_in + x_out) / 2,
                   DEV_Y + dy, Z_USB - 3.75).val()
        clash = solid.intersect(plug).Volume() + lid_on.intersect(plug).Volume()
        bad = clash > 1e-6
        ok &= not bad
        print(f"    {name:<13} cable path to the receptacle       "
              + (f"BLOCKED {clash:.0f} mm^3" if bad else "clear"))
    print(f"    receptacle face {abs(reach):.1f} mm inside the outer wall"
          f" (a USB-C plug shell is ~6.6 mm long)")
    wall_gap = DEV_X0 - (-CAV_X / 2)
    if wall_gap < 0.3:
        ok = False
        print(f"    *** DevKitC USB end hits the wall ({wall_gap:.1f} mm) - reduce BOARD_SHIFT_X")
    if DECK_H < 4.0:
        ok = False
        print(f"    *** only {DECK_H:.1f} mm under the board - wires and glue need 4")
    print("    " + ("all parts fit" if ok else "*** SOMETHING DOES NOT FIT ***"))
    return ok


# -------------------------------------------------------------------- pod

POD_IN_L = BANK_L + 2 * POD_CLEAR
POD_IN_W = BANK_W + 2 * POD_CLEAR
POD_L = POD_IN_L + 2 * POD_WALL
POD_W = POD_IN_W + 2 * POD_WALL
POD_H = POD_FLOOR + POD_WALL_H


def make_pod():
    p = rounded_box(POD_L, POD_W, POD_H, POD_CORNER)
    p = p.cut(rounded_box(POD_IN_L, POD_IN_W, POD_H, 1.0).translate((0, 0, POD_FLOOR)))
    # strap loops at both ends, floor level. Unlike the case, the pod floor
    # is thinner than the loop, so the loop must start at the end wall and
    # go outward only - a centred loop would put a 5 mm step inside the
    # pocket. (The pod check caught exactly that.)
    holes = []
    for sx in (-1, 1):
        tab_len = LOOP_OUT + POD_WALL
        p = p.union(rounded_box(tab_len, LOOP_W, LOOP_T, 3.0)
                    .translate((sx * (POD_L / 2 - POD_WALL + tab_len / 2), 0, 0)))
        holes.append(box(SLOT_X, SLOT_Y, LOOP_T + 2, sx * (POD_L / 2 + SLOT_OFF), 0, -1))
    for h in holes:
        p = p.cut(h)
    # cable notch (+X) and thumb notch (-X), both open to the top
    p = p.cut(box(POD_WALL * 4, POD_CABLE_W, POD_H, POD_L / 2, 0, POD_FLOOR + POD_CABLE_Z))
    p = p.cut(box(POD_WALL * 4, POD_THUMB_W, POD_THUMB_D + 1, -POD_L / 2, 0, POD_H - POD_THUMB_D))
    # keeper-band notches on the long walls' top edges
    for sy in (-1, 1):
        p = p.cut(box(POD_BAND_W, POD_WALL * 4, POD_BAND_D + 1, 0, sy * POD_W / 2, POD_H - POD_BAND_D))
    # drains
    for x in (-POD_IN_L / 4, POD_IN_L / 4):
        for y in (-POD_IN_W / 4, POD_IN_W / 4):
            p = p.cut(cq.Workplane("XY").circle(POD_DRAIN_D / 2).extrude(POD_FLOOR + 2)
                      .translate((x, y, -1)))
    return p


def pod_check(pod):
    """The bank must drop in with POD_CLEAR of air all round - never a press fit."""
    solid = pod.val()
    ok = True
    print("  pod check:")
    bank = rounded_box(BANK_L, BANK_W, BANK_T, BANK_EDGE_R).translate((0, 0, POD_FLOOR + 0.01)).val()
    v = solid.intersect(bank).Volume()
    print(f"    bank {BANK_L:.1f} x {BANK_W:.1f} x {BANK_T:.1f}     "
          + ("clear" if v < 1e-6 else f"CLASH {v:.0f} mm^3"))
    ok &= v < 1e-6
    margin = POD_MIN_AIR
    ring = (rounded_box(BANK_L + 2 * margin, BANK_W + 2 * margin, BANK_T, BANK_EDGE_R + margin)
            .translate((0, 0, POD_FLOOR + 0.01)).val())
    v2 = solid.intersect(ring).Volume()
    print(f"    at least {margin:.1f} mm of air all round   "
          + ("yes" if v2 < 1e-6 else f"NO ({v2:.0f} mm^3 tight)"))
    ok &= v2 < 1e-6
    stick = BANK_T - POD_WALL_H
    print(f"    bank stands {stick:.1f} mm above the walls, for the keeper band")
    if stick < 3.0:
        ok = False
        print("    *** walls too tall: the band can't hold the bank down")
    print("    " + ("pod OK" if ok else "*** POD PROBLEM ***"))
    return ok


# ------------------------------------------------------------------- main

if __name__ == "__main__":
    import os, sys
    out = os.path.dirname(os.path.abspath(__file__))
    body, lid, pod = make_body(), make_lid(), make_pod()
    good = self_check(body, lid)
    good &= pod_check(pod)
    print()
    for name, obj in (("ember_body", body), ("ember_lid", lid), ("ember_pod", pod)):
        exporters.export(obj, os.path.join(out, name + ".step"))
        exporters.export(obj, os.path.join(out, name + ".stl"))
        print(f"  wrote {name}.step and {name}.stl")
    asm = body.union(lid.translate((0, 0, OUT_Z + 14)))
    exporters.export(asm, os.path.join(out, "ember_assembly.step"))
    exporters.export(asm, os.path.join(out, "ember_assembly.stl"))
    print("  wrote ember_assembly.step  (lid shown lifted)")

    print(f"\n  case footprint    : {OUT_X:.1f} x {OUT_Y:.1f} mm (109 with strap loops)")
    print(f"  overall thickness : {OUT_Z + LID:.1f} mm")
    print(f"  protoboard        : z {Z_BOARD_BOT:.1f}-{Z_BOARD_TOP:.1f}")
    print(f"  DevKitC top       : z {Z_DEV_TOP:.1f}   lid underside z {OUT_Z:.1f}")
    print(f"  USB port centre   : z {Z_USB:.1f}, y {DEV_Y:.1f}")
    print(f"  floor under scoop : {FLOOR_MIN:.1f} mm")
    print(f"  pod               : {POD_L:.1f} x {POD_W:.1f} x {POD_H:.1f} mm "
          f"({POD_L + 2 * LOOP_OUT:.0f} with strap loops), pocket {POD_IN_L:.1f} x {POD_IN_W:.1f}")
    sys.exit(0 if good else 1)
