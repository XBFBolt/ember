#!/usr/bin/env python3
"""
ember_ble.py - talk to Ember over Bluetooth from a laptop.

Two jobs:
  1. Prove the BLE link works before anyone has written a line of the app.
  2. Be the reference decoder: the app team copies decode() and is done.

    pip install bleak
    python3 ember_ble.py                    # live readout
    python3 ember_ble.py --csv bout.csv     # and log every frame
    python3 ember_ble.py --send BASELINE    # send a command, then watch
    python3 ember_ble.py --selftest         # check the decoder, no hardware

Frame layout is in docs/APP_INTERFACE.md and must match encodeFrame() in
firmware/ember/ember_core.h.
"""

import argparse
import asyncio
import csv
import struct
import sys
import time

UUID_SVC = "e3b10001-5a2f-4c8e-9b7d-656d62657200"
UUID_LIVE = "e3b10002-5a2f-4c8e-9b7d-656d62657200"
UUID_CMD = "e3b10003-5a2f-4c8e-9b7d-656d62657200"

STATES = {0: "OK", 1: "CAUTION", 2: "REFUSE"}
HRQ = {0: "none", 1: "ok"}               # 2 and 3 were v2.1's two-sensor states

FLAGS = [
    (0x0001, "MOTIONLESS_TACHY", "high HR while still"),
    (0x0002, "RESERVED_0002", ""),          # was NO_THERMAL_LOAD (v2.1, needed humidity)
    (0x0004, "COOL_SKIN", "skin not warm"),
    (0x0008, "STALE_HR", "no trustworthy heart rate"),
    (0x0010, "RESERVED_0010", ""),          # was WIDE_INTERVAL in v2.0
    (0x0020, "NO_BASELINE", "no baseline yet"),
    (0x0040, "CADENCE_LOCK", "pulse matches step cadence"),
    (0x0080, "RESERVED_0080", ""),          # was EVAP_FAILING (v2.1, needed humidity)
    (0x0100, "RESERVED_0100", ""),          # was PPG_DISAGREE (v2.1, two pulse sensors)
    (0x0200, "RESERVED_0200", ""),          # was PPG_SINGLE (v2.1, two pulse sensors)
    (0x0400, "SKIN_DISAGREE", "skin sensors disagree"),
    (0x0800, "SKIN_SINGLE", "one skin sensor off skin"),
    (0x1000, "NO_AIR", "no air temperature sensor"),
    (0x2000, "LOW_BATT", "battery low"),
    (0x4000, "NOT_CALIBRATED", "thermistors not calibrated"),
    (0x8000, "BASELINE_RUNNING", "baseline in progress"),
]

# Reasons in the order the firmware ranks them (flagReason in ember_core.h):
# flags that can cause REFUSE or CAUTION first, info-only flags last.
# --selftest checks this against the header when it can find it.
REASON_ORDER = [0x0008, 0x0001, 0x0004, 0x0040, 0x8000, 0x0020, 0x0400, 0x4000, 0x1000]


def decode(b: bytes) -> dict:
    """20-byte little-endian frame -> dict. None means 'not available'.
    Bytes 14, 15, 18 and 19 are reserved (v2.1's humidity, headroom and
    per-sensor heart rates) and ignored."""
    if len(b) < 20:
        raise ValueError(f"frame is {len(b)} bytes, expected 20")
    seq, ct_c, half, st, flags, hr, hrq, skin_c, air_c, _r14, _r15, batt, act, _r18, _r19 = \
        struct.unpack("<HhBBHBBhhBbBBBB", b[:20])

    def c(v):  return None if v == -32768 else v / 100.0
    def u(v, scale, none):  return None if v == none else v / scale

    reason = next((dict((f, d) for f, _, d in FLAGS)[f] for f in REASON_ORDER if flags & f), "")
    return {
        "seq": seq,
        "core_c": c(ct_c),                       # None whenever the device refuses
        "half_c": u(half, 50.0, 255),
        "state": STATES.get(st & 0x0F, "?"),
        "baseline_running": bool(st & 0x10),
        "logging": bool(st & 0x20),
        "flags": flags,
        "flag_names": [n for f, n, _ in FLAGS if flags & f],
        "reason": reason,
        "hr": None if hr == 0 else hr,
        "hr_quality": HRQ.get(hrq, "?"),
        "skin_c": c(skin_c),
        "air_c": c(air_c),                       # air thermistor, outside the strap
        "battery_pct": None if batt == 255 else batt,      # None = on USB power
        "activity_g": u(act, 500.0, 255),
    }


def fmt(d: dict) -> str:
    def f(v, spec, none="--"):
        return none if v is None else format(v, spec)
    if d["state"] == "REFUSE" or d["core_c"] is None:
        core = f"CANNOT ESTIMATE ({d['reason']})"
    else:
        core = f"{d['core_c']:.2f} +/- {d['half_c']:.2f} C"
        if d["state"] == "CAUTION":
            core += f"  ?  ({d['reason']})"
    return (f"#{d['seq']:5d}  {core:44s} | HR {f(d['hr'], '3d')} {d['hr_quality']:4s}"
            f" | skin {f(d['skin_c'], '.2f')} | air {f(d['air_c'], '.1f')} C"
            f" | act {f(d['activity_g'], '.2f')} g | batt {f(d['battery_pct'], 'd', 'USB')}")


async def run(args):
    from bleak import BleakClient, BleakScanner

    print("scanning for Ember ...")
    dev = await BleakScanner.find_device_by_filter(
        lambda d, ad: (d.name or "").startswith("Ember") or
        UUID_SVC in [s.lower() for s in (ad.service_uuids or [])],
        timeout=15.0)
    if dev is None:
        sys.exit("not found. Is it powered? Is another phone/app already connected to it?")
    print(f"found {dev.name} {dev.address}, connecting ...")

    writer = None
    if args.csv:
        fh = open(args.csv, "w", newline="")
        writer = csv.writer(fh)
        writer.writerow(["t"] + list(decode(bytes(20)).keys()))

    def on_frame(_, data: bytearray):
        d = decode(bytes(data))
        print(fmt(d))
        if writer:
            writer.writerow([f"{time.time():.3f}"] + list(d.values()))

    async with BleakClient(dev) as client:
        print("connected.")
        if args.send:
            await client.write_gatt_char(UUID_CMD, args.send.encode(), response=True)
            print(f"sent {args.send}")
        await client.start_notify(UUID_LIVE, on_frame)
        try:
            while client.is_connected:
                await asyncio.sleep(1.0)
        except KeyboardInterrupt:
            pass


def selftest():
    # The same frame tests/test_core.cpp encodes and checks byte by byte.
    b = bytes([0x01, 0x02, 0xC8, 0x0E, 31, 0x21, 0x20, 0x08, 131, 1,
               0x54, 0x0D, 0xCA, 0x08, 255, 0x80, 81, 105, 0, 0])
    d = decode(b)
    assert d["seq"] == 513, d
    assert abs(d["core_c"] - 37.84) < 1e-9
    assert abs(d["half_c"] - 0.62) < 1e-9
    assert d["state"] == "CAUTION" and d["logging"] and not d["baseline_running"]
    assert set(d["flag_names"]) == {"NO_BASELINE", "SKIN_SINGLE"}
    assert d["hr"] == 131 and d["hr_quality"] == "ok"
    assert abs(d["skin_c"] - 34.12) < 1e-9 and abs(d["air_c"] - 22.50) < 1e-9
    assert d["battery_pct"] == 81 and abs(d["activity_g"] - 0.21) < 1e-9
    assert d["reason"] == "no baseline yet"
    nan = bytes([0, 0, 0x00, 0x80, 255, 2, 0x08, 0, 0, 0, 0x00, 0x80, 0x00, 0x80, 255, 0x80, 255, 255, 0, 0])
    e = decode(nan)
    assert e["core_c"] is None and e["half_c"] is None and e["air_c"] is None
    assert e["hr"] is None and e["hr_quality"] == "none"
    assert e["state"] == "REFUSE" and e["reason"] == "no trustworthy heart rate"
    assert e["battery_pct"] is None
    # v2.1: at or above 38.0 the device sends CAUTION with the number, even
    # with a stale heart rate. 38.30 +/- 0.70, flags STALE_HR.
    w = decode(bytes([5, 0, 0xF6, 0x0E, 35, 0x01, 0x08, 0x00, 0, 0,
                      0x00, 0x80, 0x00, 0x80, 255, 0x80, 255, 255, 0, 0]))
    assert w["state"] == "CAUTION" and abs(w["core_c"] - 38.30) < 1e-9 and abs(w["half_c"] - 0.70) < 1e-9
    assert w["reason"] == "no trustworthy heart rate"
    # An info-only flag never masks the reason for CAUTION.
    i = decode(bytes([0] * 5 + [0x01] + list((0x0020 | 0x4000 | 0x1000).to_bytes(2, "little")) + [0] * 12))
    assert i["reason"] == "no baseline yet", i["reason"]
    # Reserved bits never give a reason.
    r = decode(bytes([0] * 6 + list((0x0002 | 0x0010 | 0x0080 | 0x0100 | 0x0200).to_bytes(2, "little")) + [0] * 12))
    assert r["reason"] == "", r["reason"]
    _check_against_firmware()
    print(fmt(d))
    print(fmt(e))
    print(fmt(w))
    print("decoder self-test passed")


def _check_against_firmware():
    """REASON_ORDER and reason text must match flagReason() in ember_core.h."""
    import os
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "..", "firmware", "ember", "ember_core.h")
    if not os.path.exists(path):
        print("(ember_core.h not found next to this tool: skipped the firmware cross-check)")
        return
    src = open(path).read()
    bits = {n: int(v, 16) for n, v in re.findall(r"\b(F_\w+)\s*=\s*(0x[0-9A-Fa-f]+)", src)}
    body = src[src.index("inline const char *flagReason"):]
    body = body[:body.index("\n}")]
    fw = [(bits[n], text) for n, text in re.findall(r"if \(f & (F_\w+)\)\s+return \"([^\"]*)\"", body)]
    desc = {f: d for f, _, d in FLAGS}
    assert [f for f, _ in fw] == REASON_ORDER, f"REASON_ORDER differs from flagReason: {fw}"
    for f, text in fw:
        assert desc[f] == text, f"flag 0x{f:04X}: decoder says {desc[f]!r}, firmware says {text!r}"
    print(f"reason order matches ember_core.h ({len(fw)} reasons)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", help="log every frame to this file")
    ap.add_argument("--send", help="command to send first, e.g. BASELINE, START, CAL")
    ap.add_argument("--selftest", action="store_true", help="check the decoder, no hardware")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    else:
        asyncio.run(run(a))
