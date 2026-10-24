"""
Export the calibration Ember ships: the learned correction's coefficients
and the conformal tables, as a C header for the ESP32 and an ES module for
the webapp. Also writes golden test vectors so the firmware's arithmetic is
checked against this file, number for number (tests/test_core.cpp).

This closes the loop. The ± in the app stops being "1.96 times the square
root of the Kalman variance" — a quantity that published coverage tests
show means almost nothing — and becomes an interval that was calibrated
against real rectal temperatures from real people, and whose coverage you
measured.

Two tables (firmware 2.3+):
  CONF_*      for the corrected estimate (correction on: baseline captured
              and a heart rate seen). Fitted on leave-one-subject-out
              corrected estimates, so it reflects people the model did
              not train on.
  CONF_RAW_*  for the filter's own estimate (correction off: no baseline
              yet). The same table firmware 2.2 shipped.

The tables only give the width of the range. They are not a refusal rule:
the device declines to show a number only on signal doubts
(stateFromFlags in ember_core.h), never because the range is wide.

    python3 export_firmware_table.py --data "Prospie dataset_open access V3.xlsx" \
        --out ../firmware/ember/conformal_table.h \
        --js-out ../webapp/src/lib/conformal_table.js \
        --vectors-out ../tests/correction_vectors.h
"""

import argparse
import os
import sys
from datetime import date

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conformal import StratifiedConformal, coverage, gaussian_interval
from ectemp import init_from_resting_hr, run_series
import correction as corr
import evaluate
import load_data

HOT_C = 38.5


def build(df, n_strata=6, level=0.90):
    pred = corr.add_features(evaluate.predict_all(df))
    scored = pred[pred["core_c"].notna()]

    # Honest numbers: the nested leave-one-subject-out run evaluate.py uses.
    res = corr.loso(pred, n_strata=n_strata, levels=(level,))
    lo, hi = res[f"c_lo_{level}"].to_numpy(), res[f"c_hi_{level}"].to_numpy()
    hot = (res["core_c"] >= HOT_C).to_numpy()
    glo, ghi = gaussian_interval(res["kalman_pred"], res["var"], level)
    stats = {
        "cov": coverage(res["core_c"], lo, hi),
        "cov_hot": coverage(res["core_c"][hot], lo[hot], hi[hot]),
        "cov_raw": coverage(res["core_c"], res["c_lo_raw_0.9"].to_numpy(),
                            res["c_hi_raw_0.9"].to_numpy()),
        "cov_kalman": coverage(res["core_c"], glo, ghi),
        "n_subj": int(res["subject"].nunique()),
        "n_samp": int(len(res)),
        "active_share": float(res["corr_active"].mean()),
    }

    # Uncorrected table: fitted on every scored filter estimate (as in 2.2).
    sc_raw = StratifiedConformal(n_strata=n_strata, levels=(level,)).fit(
        scored["pred"].to_numpy(), scored["core_c"].to_numpy())

    # The shipped correction: fitted on every active minute.
    act = scored[scored["corr_active"]]
    model = corr.fit(act[list(corr.FEATURES)].to_numpy(),
                     (act["core_c"] - act["pred"]).to_numpy())

    # Corrected table: fitted on each subject's estimate from the model that
    # did not see them (the LOSO run above).
    ra = res[res["corr_active"]]
    sc_cor = StratifiedConformal(n_strata=n_strata, levels=(level,)).fit(
        ra["pred"].to_numpy(), ra["core_c"].to_numpy())

    X = act[list(corr.FEATURES)].to_numpy()
    raw_corr = model["intercept"] + X @ model["coef"]
    stats["corr_p01"], stats["corr_p99"] = (float(np.percentile(raw_corr, 1)),
                                            float(np.percentile(raw_corr, 99)))
    stats["corr_clamped"] = float(np.mean(np.abs(raw_corr) > corr.CORR_MAX_C))

    tables = {
        "cor": ([e for e in sc_cor.edges_ if np.isfinite(e)], [w[level] for w in sc_cor.widths_]),
        "raw": ([e for e in sc_raw.edges_ if np.isfinite(e)], [w[level] for w in sc_raw.widths_]),
    }
    return model, tables, stats


def _half(edges, halves, x):
    i = 0
    while i < len(halves) - 1 and x >= edges[i]:
        i += 1
    return halves[i]


def _header_comment(A, kind, level, stats, source):
    A("/*")
    A(f" * conformal_table.{kind} - calibrated prediction intervals and the")
    A(" * learned correction for Ember (firmware 2.3+)")
    A(" *")
    A(" * GENERATED FILE. Do not edit by hand; rerun export_firmware_table.py.")
    A(f" * generated      {date.today().isoformat()}")
    A(f" * source data    {source}")
    A(f" * calibration    {stats['n_subj']} subjects, {stats['n_samp']} samples")
    A(f" * nominal level  {level:.0%}")
    A(" * MEASURED coverage under leave-one-subject-out:")
    A(f" *   shipped (corrected where possible)  {stats['cov']:.1%}")
    A(f" *   at true core >= {HOT_C}              {stats['cov_hot']:.1%}")
    A(f" *   uncorrected filter, CONF_RAW table  {stats['cov_raw']:.1%}")
    A(f" *   Kalman posterior \"90%\" (not shown)  {stats['cov_kalman']:.1%}")
    A(" *")
    A(" * The half-widths are quantiles of the absolute error measured against")
    A(" * a rectal reference, binned by estimated temperature. They are NOT")
    A(" * derived from the Kalman posterior variance, which published coverage")
    A(" * tests show is badly miscalibrated for this model.")
    A(" *")
    A(" * Correction: estimate = filter + clamp(CORR_INTERCEPT + CORR_COEF . x,")
    A(" * +/- CORR_MAX_C), x = (ct, ct_d10, hr5, hr5_d10, hr_rest), computed")
    A(" * once a minute as in analysis/correction.py. Off (CONF_RAW table) until")
    A(" * a baseline is captured and a heart rate has been seen.")
    A(" */")
    A("")


def _f(x):
    s = f"{x:.8g}"
    if not any(c in s for c in ".en"):   # "1f" is not a C float literal; "1.0f" is
        s += ".0"
    return s + "f"


def write_header(path, model, tables, level, stats, source):
    lines = []
    A = lines.append
    _header_comment(A, "h", level, stats, source)
    (ce, ch), (re_, rh) = tables["cor"], tables["raw"]
    A("#ifndef CONFORMAL_TABLE_H")
    A("#define CONFORMAL_TABLE_H")
    A("")
    A(f"#define CONF_LEVEL            {level:.2f}f")
    A(f"#define CONF_MEASURED_COV     {stats['cov']:.4f}f")
    A(f"#define CONF_RAW_MEASURED_COV {stats['cov_raw']:.4f}f")
    A(f"#define CONF_N_STRATA         {len(ch)}")
    A(f"#define CONF_RAW_N_STRATA     {len(rh)}")
    A("")
    A("// Corrected estimate: upper edge of each stratum, degrees C.")
    A("static const float CONF_EDGES[CONF_N_STRATA - 1] = {")
    A("  " + ", ".join(f"{e:.4f}f" for e in ce))
    A("};")
    A("// Corrected estimate: half-width of each stratum, degrees C.")
    A("static const float CONF_HALF[CONF_N_STRATA] = {")
    A("  " + ", ".join(f"{h:.4f}f" for h in ch))
    A("};")
    A("")
    A("// Filter alone (no baseline yet): upper edge of each stratum, degrees C.")
    A("static const float CONF_RAW_EDGES[CONF_RAW_N_STRATA - 1] = {")
    A("  " + ", ".join(f"{e:.4f}f" for e in re_))
    A("};")
    A("// Filter alone: half-width of each stratum, degrees C.")
    A("static const float CONF_RAW_HALF[CONF_RAW_N_STRATA] = {")
    A("  " + ", ".join(f"{h:.4f}f" for h in rh))
    A("};")
    A("")
    A("// Half-width of the calibrated interval for a corrected estimate.")
    A("static inline float conformal_half_width(float ct_est) {")
    A("  int i = 0;")
    A("  while (i < CONF_N_STRATA - 1 && ct_est >= CONF_EDGES[i]) i++;")
    A("  return CONF_HALF[i];")
    A("}")
    A("")
    A("// Half-width of the calibrated interval for the filter's own estimate.")
    A("static inline float conformal_half_width_raw(float ct_est) {")
    A("  int i = 0;")
    A("  while (i < CONF_RAW_N_STRATA - 1 && ct_est >= CONF_RAW_EDGES[i]) i++;")
    A("  return CONF_RAW_HALF[i];")
    A("}")
    A("")
    A("// Learned correction. Features, in order: ct, ct_d10, hr5, hr5_d10, hr_rest")
    A(f"#define CORR_N_FEATURES {len(corr.FEATURES)}")
    A(f"#define CORR_LAG_MIN    {corr.LAG_MIN}")
    A(f"#define CORR_HR_WIN_MIN {corr.HR_WIN_MIN}")
    A(f"#define CORR_MAX_C      {_f(corr.CORR_MAX_C)}")
    A(f"static const float CORR_INTERCEPT = {_f(model['intercept'])};")
    A("static const float CORR_COEF[CORR_N_FEATURES] = {")
    A("  " + ", ".join(_f(c) for c in model["coef"]))
    A("};")
    A("")
    A("#endif // CONFORMAL_TABLE_H")
    text = "\n".join(lines) + "\n"
    with open(path, "w") as fh:
        fh.write(text)
    return text


def write_js(path, model, tables, level, stats, source, synthetic):
    """Same tables as write_header, as an ES module for the webapp."""
    lines = []
    A = lines.append
    _header_comment(A, "js", level, stats, source)
    (ce, ch), (re_, rh) = tables["cor"], tables["raw"]
    A(f"export const CONF_SYNTHETIC = {'true' if synthetic else 'false'};")
    A("")
    A(f"export const CONF_LEVEL = {level:.2f};")
    A(f"export const CONF_MEASURED_COV = {stats['cov']:.4f};")
    A(f"/** Coverage when true core was {HOT_C} °C or more. */")
    A(f"export const CONF_MEASURED_COV_HOT = {stats['cov_hot']:.4f};")
    A(f"export const CONF_RAW_MEASURED_COV = {stats['cov_raw']:.4f};")
    A("/** What the Kalman filter's own \"90%\" range actually covered. Never displayed as a range. */")
    A(f"export const KALMAN_MEASURED_COV = {stats['cov_kalman']:.4f};")
    A(f"export const CONF_N_STRATA = {len(ch)};")
    A("")
    A("// Corrected estimate: upper edge of each stratum, degrees C.")
    A("export const CONF_EDGES = [")
    A("  " + ", ".join(f"{e:.4f}" for e in ce))
    A("];")
    A("// Corrected estimate: half-width of each stratum, degrees C.")
    A("export const CONF_HALF = [")
    A("  " + ", ".join(f"{h:.4f}" for h in ch))
    A("];")
    A("")
    A("// Filter alone (no baseline yet).")
    A("export const CONF_RAW_EDGES = [")
    A("  " + ", ".join(f"{e:.4f}" for e in re_))
    A("];")
    A("export const CONF_RAW_HALF = [")
    A("  " + ", ".join(f"{h:.4f}" for h in rh))
    A("];")
    A("")
    A("function _half(edges, halves, ct) {")
    A("  let i = 0;")
    A("  while (i < halves.length - 1 && ct >= edges[i]) i++;")
    A("  return halves[i];")
    A("}")
    A("")
    A("/** Half-width for a corrected estimate (baseline captured). */")
    A("export function conformalHalfWidth(ct_est) {")
    A("  return _half(CONF_EDGES, CONF_HALF, ct_est);")
    A("}")
    A("")
    A("/** Half-width for the filter's own estimate (no baseline yet). */")
    A("export function conformalHalfWidthRaw(ct_est) {")
    A("  return _half(CONF_RAW_EDGES, CONF_RAW_HALF, ct_est);")
    A("}")
    A("")
    A("// Learned correction (applied on the device; listed here for the app's")
    A("// \"How sure is Ember?\" sheet). Features: ct, ct_d10, hr5, hr5_d10, hr_rest.")
    A(f"export const CORR_INTERCEPT = {model['intercept']:.8g};")
    A("export const CORR_COEF = [" + ", ".join(f"{c:.8g}" for c in model["coef"]) + "];")
    A(f"export const CORR_MAX_C = {corr.CORR_MAX_C};")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")


# ------------------------------------------------------- golden vectors

def _vector_cases():
    """Synthetic minute-by-minute heart rates covering every branch."""
    nan = float("nan")
    ramp = list(np.linspace(68, 158, 35)) + [158.0] * 10 + list(np.linspace(150, 95, 20))
    ramp[12] = ramp[13] = ramp[14] = nan          # three coasted minutes mid-climb
    return [
        ("work", 62.0, ramp),                                  # full session
        ("short", 70.0, [75.0, 76.0, nan, 78.0, 80.0, 84.0]),  # under 10 minutes of history
        ("no_baseline", nan, [80.0, 95.0, 110.0, 120.0, 125.0]),  # correction off
        ("late_hr", 58.0, [nan, nan, nan, 90.0, 100.0, 110.0, 115.0]),  # no hr5 at first
    ]


def write_vectors(path, model, tables):
    """tests/correction_vectors.h: what the firmware must reproduce."""
    (ce, ch), (re_, rh) = tables["cor"], tables["raw"]
    L = ["// GENERATED by analysis/export_firmware_table.py - do not edit.",
         "// Each case: per-minute heart rate (NAN = coasted minute), the resting",
         "// heart rate (NAN = no baseline), and what analysis/correction.py says",
         "// the device must show each minute: estimate, half-width, correction on.",
         "#pragma once", "#include <math.h>", ""]
    names = []
    for name, rest, hr in _vector_cases():
        hr = np.asarray(hr, float)
        ct0 = init_from_resting_hr(rest) if np.isfinite(rest) else 37.1
        ct, _ = run_series(hr, ct_init=ct0)
        X, active = corr.trial_features(hr, ct, rest)
        est = corr.apply(model, ct, X, active)
        half = [(_half(ce, ch, e) if a else _half(re_, rh, e)) for e, a in zip(est, active)]
        fl = lambda a: ", ".join("NAN" if not np.isfinite(v) else f"{v:.6f}f" for v in a)
        L.append(f"static const float V_{name}_hr[]   = {{ {fl(hr)} }};")
        L.append(f"static const float V_{name}_est[]  = {{ {fl(est)} }};")
        L.append(f"static const float V_{name}_half[] = {{ {fl(half)} }};")
        L.append(f"static const bool  V_{name}_on[]   = {{ "
                 + ", ".join('true' if a else 'false' for a in active) + " };")
        L.append("")
        names.append((name, rest, len(hr)))
    L.append("struct CorrVector { const char *name; float restHr; int n;")
    L.append("  const float *hr, *est, *half; const bool *on; };")
    L.append("static const CorrVector CORR_VECTORS[] = {")
    for name, rest, n in names:
        r = "NAN" if not np.isfinite(rest) else f"{rest:.1f}f"
        L.append(f"  {{ \"{name}\", {r}, {n}, V_{name}_hr, V_{name}_est, V_{name}_half, V_{name}_on }},")
    L.append("};")
    L.append(f"static const int N_CORR_VECTORS = {len(names)};")
    with open(path, "w") as fh:
        fh.write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="Prospie dataset_open access V3.xlsx")
    ap.add_argument("--level", type=float, default=0.90)
    ap.add_argument("--strata", type=int, default=6)
    ap.add_argument("--out", default="conformal_table.h")
    ap.add_argument("--js-out", default=None,
                    help="also write the tables as an ES module for the webapp, "
                         "e.g. ../webapp/src/lib/conformal_table.js")
    ap.add_argument("--vectors-out", default=None,
                    help="also write golden vectors for tests/test_core.cpp, "
                         "e.g. ../tests/correction_vectors.h")
    ap.add_argument("--hr-types", default="2,3",
                    help="HR sensor types: 1 finger PPG, 2 Equivital chest, 3 Polar "
                         "chest; 'all' for every type (default 2,3: chest only)")
    args = ap.parse_args()

    hr_types = evaluate.parse_hr_types(args.hr_types)
    df = load_data.load_prospie(args.data, hr_types=hr_types)
    source = os.path.basename(args.data) + (
        "" if hr_types is None else
        f" (HR: {', '.join(load_data.HR_TYPE_NAMES[t] for t in hr_types)})")

    model, tables, stats = build(df, n_strata=args.strata, level=args.level)

    print(write_header(args.out, model, tables, args.level, stats, source))
    print(f"wrote {args.out}")
    if args.js_out:
        write_js(args.js_out, model, tables, args.level, stats, source, synthetic=False)
        print(f"wrote {args.js_out}")
    if args.vectors_out:
        write_vectors(args.vectors_out, model, tables)
        print(f"wrote {args.vectors_out}")

    print(f"\ncorrection active on {stats['active_share']:.1%} of scored minutes")
    print(f"raw correction, 1st-99th percentile: {stats['corr_p01']:+.2f} to "
          f"{stats['corr_p99']:+.2f} C; clamped at +/-{corr.CORR_MAX_C} on "
          f"{stats['corr_clamped']:.2%} of minutes")
    print("standardised coefficients: " + ", ".join(
        f"{f} {w:+.3f}" for f, w in zip(corr.FEATURES, model["std_coef"])))


if __name__ == "__main__":
    main()
