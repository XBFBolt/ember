"""
Export the fitted conformal intervals as a C header for the ESP32.

This closes the loop. The ± in the app stops being "1.96 times the square
root of the Kalman variance" — a quantity that published coverage tests
show means almost nothing — and becomes an interval that was calibrated
against real rectal temperatures from real people, and whose coverage you
measured.

The table only gives the width of the range. It is not a refusal rule:
since firmware 2.1 the device declines to show a number only on signal
doubts (stateFromFlags in ember_core.h), never because the range is wide.

    python3 export_firmware_table.py --synthetic
    python3 export_firmware_table.py --data "Prospie dataset_open access V3.xlsx" \
        --out ../firmware/ember/conformal_table.h \
        --js-out ../webapp/src/lib/conformal_table.js

Writes conformal_table.h (include it from the firmware) and, with --js-out,
the same table for the webapp.
"""

import argparse
import os
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conformal import StratifiedConformal, coverage
import load_data
import evaluate


def build(df, n_strata=6, level=0.90):
    pred = evaluate.predict_all(df)
    pred = pred[pred["core_c"].notna()]   # fit only where there is a reference

    # Fit the shipped table on everything, but report coverage from the
    # leave-one-subject-out run, because that is the honest number and it
    # is the one you are allowed to print next to the device.
    res = evaluate.loso(pred, n_strata=n_strata)
    cov = coverage(res["core_c"], res[f"c_lo_{level}"], res[f"c_hi_{level}"])

    sc = StratifiedConformal(n_strata=n_strata, levels=(level,)).fit(
        pred["pred"].to_numpy(), pred["core_c"].to_numpy())

    edges = [e for e in sc.edges_ if np.isfinite(e)]
    halves = [w[level] for w in sc.widths_]
    return sc, edges, halves, cov, res


def write_header(path, edges, halves, level, cov, n_subj, n_samp, source):
    lines = []
    A = lines.append
    A("/*")
    A(" * conformal_table.h - calibrated prediction intervals for Ember")
    A(" *")
    A(" * GENERATED FILE. Do not edit by hand; rerun export_firmware_table.py.")
    A(f" * generated      {date.today().isoformat()}")
    A(f" * source data    {source}")
    A(f" * calibration    {n_subj} subjects, {n_samp} samples")
    A(f" * nominal level  {level:.0%}")
    A(f" * MEASURED coverage under leave-one-subject-out: {cov:.1%}")
    A(" *")
    A(" * The half-widths below are quantiles of the absolute error measured")
    A(" * against a rectal reference, binned by predicted temperature. They")
    A(" * are NOT derived from the Kalman posterior variance, which published")
    A(" * coverage tests show is badly miscalibrated for this model.")
    A(" */")
    A("")
    A("#ifndef CONFORMAL_TABLE_H")
    A("#define CONFORMAL_TABLE_H")
    A("")
    A(f"#define CONF_LEVEL        {level:.2f}f")
    A(f"#define CONF_MEASURED_COV {cov:.4f}f")
    A(f"#define CONF_N_STRATA     {len(halves)}")
    A("")
    A("// Upper edge of each stratum, in predicted degrees C.")
    A("static const float CONF_EDGES[CONF_N_STRATA - 1] = {")
    A("  " + ", ".join(f"{e:.4f}f" for e in edges))
    A("};")
    A("")
    A("// Interval half-width for each stratum, in degrees C.")
    A("static const float CONF_HALF[CONF_N_STRATA] = {")
    A("  " + ", ".join(f"{h:.4f}f" for h in halves))
    A("};")
    A("")
    A("// Half-width of the calibrated interval at this estimate.")
    A("static inline float conformal_half_width(float ct_est) {")
    A("  int i = 0;")
    A("  while (i < CONF_N_STRATA - 1 && ct_est >= CONF_EDGES[i]) i++;")
    A("  return CONF_HALF[i];")
    A("}")
    A("")
    A("#endif // CONFORMAL_TABLE_H")

    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return "\n".join(lines)


def write_js(path, edges, halves, level, cov, n_subj, n_samp,
             source, synthetic):
    """Same table as write_header, as an ES module for the webapp."""
    lines = []
    A = lines.append
    A("/*")
    A(" * conformal_table.js - calibrated prediction intervals for Ember")
    A(" *")
    A(" * GENERATED FILE. Do not edit by hand; rerun export_firmware_table.py.")
    A(f" * generated      {date.today().isoformat()}")
    A(f" * source data    {source}")
    A(f" * calibration    {n_subj} subjects, {n_samp} samples")
    A(f" * nominal level  {level:.0%}")
    A(f" * MEASURED coverage under leave-one-subject-out: {cov:.1%}")
    A(" *")
    A(" * The half-widths below are quantiles of the absolute error measured")
    A(" * against a rectal reference, binned by predicted temperature. They")
    A(" * are NOT derived from the Kalman posterior variance, which published")
    A(" * coverage tests show is badly miscalibrated for this model.")
    A(" */")
    A("")
    A(f"export const CONF_SYNTHETIC = {'true' if synthetic else 'false'};")
    A("")
    A(f"export const CONF_LEVEL = {level:.2f};")
    A(f"export const CONF_MEASURED_COV = {cov:.4f};")
    A(f"export const CONF_N_STRATA = {len(halves)};")
    A("")
    A("// Upper edge of each stratum, in predicted degrees C.")
    A("export const CONF_EDGES = [")
    A("  " + ", ".join(f"{e:.4f}" for e in edges))
    A("];")
    A("")
    A("// Interval half-width for each stratum, in degrees C.")
    A("export const CONF_HALF = [")
    A("  " + ", ".join(f"{h:.4f}" for h in halves))
    A("];")
    A("")
    A("/**")
    A(" * Half-width of the calibrated interval at this estimate.")
    A(" * @param {number} ct_est - Estimated core temperature in degrees C")
    A(" * @returns {number} Half-width in degrees C")
    A(" */")
    A("export function conformalHalfWidth(ct_est) {")
    A("  let i = 0;")
    A("  while (i < CONF_N_STRATA - 1 && ct_est >= CONF_EDGES[i]) {")
    A("    i++;")
    A("  }")
    A("  return CONF_HALF[i];")
    A("}")

    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--level", type=float, default=0.90)
    ap.add_argument("--strata", type=int, default=6)
    ap.add_argument("--out", default="conformal_table.h")
    ap.add_argument("--js-out", default=None,
                    help="also write the table as an ES module for the webapp, "
                         "e.g. ../webapp/src/lib/conformal_table.js")
    ap.add_argument("--hr-types", default="2,3",
                    help="HR sensor types: 1 finger PPG, 2 Equivital chest, 3 Polar "
                         "chest; 'all' for every type (default 2,3: chest only)")
    args = ap.parse_args()

    if args.synthetic:
        print("*** SYNTHETIC calibration. Do not flash this to a device you")
        print("*** intend to believe. Regenerate from PROSPIE.\n")
        df = load_data.make_synthetic()
        source = "SYNTHETIC - not real calibration"
    elif args.data:
        hr_types = evaluate.parse_hr_types(args.hr_types)
        df = load_data.load_prospie(args.data, hr_types=hr_types)
        source = os.path.basename(args.data) + (
            "" if hr_types is None else
            f" (HR: {', '.join(load_data.HR_TYPE_NAMES[t] for t in hr_types)})")
    else:
        sys.exit("give --data or --synthetic")

    sc, edges, halves, cov, res = build(
        df, n_strata=args.strata, level=args.level)

    text = write_header(args.out, edges, halves, args.level, cov,
                        res.subject.nunique(), len(res), source)
    print(text)
    print(f"\nwrote {args.out}")

    if args.js_out:
        write_js(args.js_out, edges, halves, args.level, cov,
                 res.subject.nunique(), len(res), source,
                 synthetic=args.synthetic)
        print(f"wrote {args.js_out}")


if __name__ == "__main__":
    main()
