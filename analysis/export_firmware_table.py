"""
Export the fitted conformal intervals as a C header for the ESP32.

This closes the loop. The number on your device's display stops being
"1.96 times the square root of the Kalman variance" — a quantity that
published coverage tests show means almost nothing — and becomes an
interval that was calibrated against real rectal temperatures from real
people, and whose coverage you measured.

It also gives the device a refusal rule: if the calibrated interval at the
current estimate is wider than REFUSE_ABOVE_C, show "cannot estimate"
instead of a number.

    python3 export_firmware_table.py --synthetic
    python3 export_firmware_table.py --data "Prospie dataset_open access V3.xlsx"

Writes conformal_table.h. Include it from the firmware.
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


def build(df, n_strata=6, level=0.90, refuse_above=1.5):
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


def write_header(path, edges, halves, level, cov, n_subj, n_samp,
                 refuse_above, source):
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
    A(f"#define REFUSE_ABOVE_C    {refuse_above:.2f}f  "
      "// half-width above which the device declines to show a number")
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
    A("// True when the device should refuse rather than display a number.")
    A("static inline bool conformal_should_refuse(float ct_est) {")
    A("  return conformal_half_width(ct_est) > REFUSE_ABOVE_C;")
    A("}")
    A("")
    A("#endif // CONFORMAL_TABLE_H")

    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--level", type=float, default=0.90)
    ap.add_argument("--strata", type=int, default=6)
    ap.add_argument("--refuse-above", type=float, default=1.5,
                    help="half-width in C above which the device refuses")
    ap.add_argument("--out", default="conformal_table.h")
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
        df, n_strata=args.strata, level=args.level,
        refuse_above=args.refuse_above)

    text = write_header(args.out, edges, halves, args.level, cov,
                        res.subject.nunique(), len(res), args.refuse_above,
                        source)
    print(text)
    print(f"\nwrote {args.out}")

    n_refuse = int(np.mean(
        [h > args.refuse_above for h in
         sc.half_width(res["pred"].to_numpy(), args.level)]) * 100)
    print(f"\nAt REFUSE_ABOVE_C = {args.refuse_above:.2f}, the device would "
          f"decline on about {n_refuse}% of samples.")
    print("Tune that with the risk-coverage curve from evaluate.py, and be "
          "ready to\ndefend the operating point you chose.")


if __name__ == "__main__":
    main()
