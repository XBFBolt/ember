"""
External test: does Ember's calibration hold on people it never saw?

Everything Ember ships was fitted on PROSPIE (Loughborough, rectal core,
chest heart rate). This applies that calibration, UNCHANGED, to a second
dataset from another lab: the heat tolerance test (HTT) study, 65 adults
walking two hours in the heat and in a thermoneutral room, with an
ingestible-pill core reference (load_htt.py).

Nothing is refitted. The correction coefficients and both conformal tables
are read from firmware/ember/conformal_table.h, the file the device is
built from, so these numbers describe the shipped device's maths (2.3).

Each trial runs the way the device would:
  - BASELINE = the wearer's resting heart rate, measured at rest before the
    trial (HTT has no seated rest at the start; walking begins at minute 0).
    It sets the filter's starting point and the correction's hr_rest.
  - ECTemp steps once a minute on the minute heart rate; it coasts through
    missing minutes.
  - The correction and the corrected table apply once the correction is
    active; before that, the filter alone with the uncorrected table.

    python3 external_test.py | tee external_htt_results.txt
"""

import json
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import correction as corr
from conformal import coverage, gaussian_interval
from ectemp import init_from_resting_hr, run_series
from evaluate import bootstrap_group_diff
from judges_results import ACT_NOW_C, TEMP_BANDS, alert_timing, _scorecard
from load_htt import load_htt

HEADER = os.path.join(HERE, "..", "firmware", "ember", "conformal_table.h")
LEVEL = 0.90
N_BOOT = 2000


# --------------------------------------------- the shipped calibration

def _floats(text, name):
    m = re.search(rf"{name}\s*(?:\[[^\]]*\])?\s*=\s*\{{([^}}]*)\}}", text)
    if not m:
        sys.exit(f"{name} not found in {HEADER}")
    return [float(v.strip().rstrip("f")) for v in m.group(1).split(",") if v.strip()]


def _scalar(text, name, define=False):
    pat = rf"#define\s+{name}\s+([-0-9.e]+)f?" if define else rf"{name}\s*=\s*([-0-9.e]+)f?;"
    m = re.search(pat, text)
    if not m:
        sys.exit(f"{name} not found in {HEADER}")
    return float(m.group(1))


class Table:
    """A shipped conformal table: half-width by stratum of the estimate."""

    def __init__(self, edges, halves):
        self.edges, self.halves = np.asarray(edges), np.asarray(halves)

    def half(self, est):
        # Same lookup as conformal_half_width() in the header.
        return self.halves[np.searchsorted(self.edges, np.asarray(est, float), side="right")]


def load_shipped(path=HEADER):
    text = open(path).read()
    for name, want in (("CORR_LAG_MIN", corr.LAG_MIN), ("CORR_HR_WIN_MIN", corr.HR_WIN_MIN),
                       ("CORR_MAX_C", corr.CORR_MAX_C)):
        got = _scalar(text, name, define=True)
        if got != want:
            sys.exit(f"{name} is {got} in the header but {want} in correction.py")
    model = {"intercept": _scalar(text, "CORR_INTERCEPT"),
             "coef": np.asarray(_floats(text, "CORR_COEF"))}
    source = re.search(r"source data\s+(.*)", text).group(1).strip()
    return (model, Table(_floats(text, "CONF_EDGES"), _floats(text, "CONF_HALF")),
            Table(_floats(text, "CONF_RAW_EDGES"), _floats(text, "CONF_RAW_HALF")), source)


# ------------------------------------------------------------- predict

def predict(df, model, cor, raw):
    """Run every trial as the device would. Returns scored rows only."""
    out = []
    for _, g in df.groupby(["subject", "condition"], sort=False):
        g = g.sort_values("minute").copy()
        rest = float(g["rest_hr"].iloc[0])
        ct0 = init_from_resting_hr(rest) if np.isfinite(rest) else 37.1
        ct, var = run_series(g["hr"].to_numpy(), ct_init=ct0, step_seconds=60.0)
        X, active = corr.trial_features(g["hr"].to_numpy(), ct, rest)
        est = corr.apply(model, ct, X, active)
        h_raw = raw.half(ct)
        h = np.where(active, cor.half(est), h_raw)
        g["kalman_pred"], g["var"], g["pred"], g["corr_active"] = ct, var, est, active
        g["c_lo_0.9"], g["c_hi_0.9"] = est - h, est + h
        g["c_lo_raw_0.9"], g["c_hi_raw_0.9"] = ct - h_raw, ct + h_raw
        out.append(g)
    res = pd.concat(out, ignore_index=True)
    return res[res["core_c"].notna()].reset_index(drop=True)


def filter_alone(res):
    """What firmware 2.2 (or 2.3 before BASELINE) would show."""
    return res.assign(pred=res["kalman_pred"], **{"c_lo_0.9": res["c_lo_raw_0.9"],
                                                  "c_hi_0.9": res["c_hi_raw_0.9"]})


# ------------------------------------------------------------- metrics

def cov90(r):
    return coverage(r["core_c"], r["c_lo_0.9"].to_numpy(), r["c_hi_0.9"].to_numpy())


def boot_ci(res, fn, n_boot=N_BOOT, seed=0):
    """95% interval over PEOPLE (resampling minutes would fake precision)."""
    rng = np.random.default_rng(seed)
    groups = {s: g for s, g in res.groupby("subject")}
    ids = np.array(list(groups))
    vals = []
    for _ in range(n_boot):
        pick = rng.choice(ids, len(ids), replace=True)
        vals.append(fn(pd.concat([groups[s] for s in pick], ignore_index=True)))
    return [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]


def rmse(r):
    return float(np.sqrt(np.mean((r["pred"] - r["core_c"]) ** 2)))


def scorecard(r):
    s = _scorecard(r)
    glo, ghi = gaussian_interval(r["kalman_pred"], r["var"], LEVEL)
    s["kalman_coverage"] = coverage(r["core_c"], glo, ghi)
    s["n_subjects"], s["n_minutes"] = int(r["subject"].nunique()), int(len(r))
    s["n_trials"] = int(r.groupby(["subject", "condition"]).ngroups)
    return s


def by_band(r):
    rows = []
    for lo, hi, label in TEMP_BANDS:
        m = (r["core_c"] >= lo) & (r["core_c"] < hi)
        if m.sum():
            rows.append({"band": label, "n": int(m.sum()), "coverage": cov90(r[m]),
                         "bias": float((r["pred"] - r["core_c"])[m].mean())})
    return rows


def trial_end_after_danger(r):
    """Minutes of data left after true core first reached 38.5, per trial."""
    left = []
    for _, g in r.groupby(["subject", "condition"]):
        hot = g[g["core_c"] >= ACT_NOW_C]
        if len(hot):
            left.append(float(g["minute"].max() - hot["minute"].iloc[0]))
    return left


# --------------------------------------------------------------- report

ROWS = [("error (RMSE, °C)", "rmse", "{:.3f}"), ("bias (°C)", "bias", "{:+.3f}"),
        ("90% coverage", "coverage_90", "{:.1%}"), ("mean ± (°C)", "mean_half", "{:.2f}"),
        (f"coverage at true ≥{ACT_NOW_C}", "coverage_hot", "{:.1%}"),
        ("Kalman \"90%\" coverage", "kalman_coverage", "{:.1%}"),
        (f"Watch on at true {ACT_NOW_C}", "watch_on", "{:d}"),
        ("Watch never fired", "watch_never", "{:d}"),
        (f"Act now on at true {ACT_NOW_C}", "act_on", "{:d}"),
        ("Act now never fired", "act_never", "{:d}"),
        ("Act now false alarm trials", "act_false_trials", "{:d}")]


def table(cols):
    """cols: [(title, scorecard)]"""
    print(f"\n  {'':32s}" + "".join(f"{t:>15s}" for t, _ in cols))
    for label, k, fmt in ROWS:
        cells = []
        for _, s in cols:
            v = s.get(k) if s else None
            cells.append("—" if v is None or (isinstance(v, float) and not np.isfinite(v))
                         else fmt.format(v))
        print(f"  {label:32s}" + "".join(f"{c:>15s}" for c in cells))
    tail = [f"{t}: {s['danger_trials']} reached {ACT_NOW_C}, {s['calm_trials']} did not"
            for t, s in cols if s]
    print("\n  Alert rows count trials. " + "; ".join(tail) + ".")


def section(title):
    print("\n" + "=" * 72 + f"\n {title}\n" + "=" * 72)


def main():
    model, cor, raw, source = load_shipped()
    print("=" * 72)
    print(" EMBER EXTERNAL TEST: PROSPIE calibration on the HTT dataset")
    print("=" * 72)
    print(f"\n Calibration: firmware/ember/conformal_table.h, unchanged")
    print(f"   ({source})")
    print(" Test data:   HTT, DOI 10.17632/g5sb382smp.1, CC BY 4.0, never used to fit\n")

    df = load_htt()
    res = predict(df, model, cor, raw)
    ref = json.load(open(os.path.join(HERE, "judges_results.json")))["correction"]
    ref_s = dict(ref["ember"], kalman_coverage=json.load(open(
        os.path.join(HERE, "judges_results.json")))["coverage_comparison"]["kalman_coverage"])

    out = {"calibration_source": source, "test_data": "HTT data set.xlsx (DOI 10.17632/g5sb382smp.1)"}

    section("1. HEADLINE: Ember 2.3 on 65 new people, next to PROSPIE")
    ember, alone = scorecard(res), scorecard(filter_alone(res))
    table([("PROSPIE LOSO", ref_s), ("HTT filter", alone), ("HTT Ember 2.3", ember)])
    ci_cov = boot_ci(res, cov90)
    ci_rmse = boot_ci(res, rmse)
    ci_bias = boot_ci(res, lambda r: float((r["pred"] - r["core_c"]).mean()))
    print(f"\n  HTT, Ember 2.3, 95% intervals over people: coverage "
          f"[{ci_cov[0]:.1%}, {ci_cov[1]:.1%}], RMSE [{ci_rmse[0]:.3f}, {ci_rmse[1]:.3f}], "
          f"bias [{ci_bias[0]:+.3f}, {ci_bias[1]:+.3f}]")
    print(f"  {ember['n_subjects']} people, {ember['n_trials']} trials, {ember['n_minutes']} "
          f"scored minutes; correction on for {res['corr_active'].mean():.1%} of them")
    out.update(ember=ember, filter_alone=alone, prospie_reference=ref_s,
               ci={"coverage_90": ci_cov, "rmse": ci_rmse, "bias": ci_bias})

    pe = (res["pred"] - res["core_c"]) ** 2
    pk = (res["kalman_pred"] - res["core_c"]) ** 2
    better = int((pe.groupby(res["subject"]).mean() < pk.groupby(res["subject"]).mean()).sum())
    print(f"  The correction lowered RMSE for {better} of {res['subject'].nunique()} people.")
    out["people_improved"] = better

    section("2. COVERAGE BY TRUE TEMPERATURE")
    print(f"\n  {'band':>20s} {'minutes':>8s} {'coverage':>9s} {'bias':>8s}")
    bands = by_band(res)
    for b in bands:
        print(f"  {b['band']:>20s} {b['n']:>8d} {b['coverage']:>9.1%} {b['bias']:>+8.3f}")
    out["by_band"] = bands

    section("3. HEAT vs THERMONEUTRAL")
    cols = []
    for cond in ("heat", "neutral"):
        r = res[res["condition"] == cond]
        s = scorecard(r)
        s["coverage_ci"] = boot_ci(r, cov90)
        cols.append((cond, s))
        out[f"condition_{cond}"] = s
    table(cols)
    for t, s in cols:
        print(f"  {t}: coverage 95% CI over people [{s['coverage_ci'][0]:.1%}, {s['coverage_ci'][1]:.1%}]")

    section("4. WOMEN vs MEN")
    cols = [(sx, scorecard(res[res["sex"] == sx])) for sx in ("F", "M")]
    table(cols)
    for key in ("bias", "rmse"):
        d = bootstrap_group_diff(res, key=key, by="sex", n_boot=N_BOOT)
        if d:
            a, b = d["groups"]
            print(f"  {key} {b} - {a}: {d['point']:+.3f} °C, 95% CI "
                  f"[{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}]")
            out[f"sex_{key}_diff"] = d
    out["by_sex"] = dict(cols)

    section("5. WHERE THE MISSES ARE")
    pros = pd.read_csv(os.path.join(HERE, "ember_chest_predictions.csv"))
    pros = pros[pros["core_c"].notna()]

    def split(r):
        return (float((r["core_c"] < r["c_lo_0.9"]).mean()),
                float((r["core_c"] > r["c_hi_0.9"]).mean()))
    h_hi, h_lo = split(res)
    p_hi, p_lo = split(pros)
    print(f"\n  {'':34s} {'PROSPIE LOSO':>13s} {'HTT':>8s}")
    print(f"  {'estimate too high (true below)':34s} {p_hi:>13.1%} {h_hi:>8.1%}")
    print(f"  {'estimate too low (true above)':34s} {p_lo:>13.1%} {h_lo:>8.1%}")
    print("  Too low is the dangerous direction: the wearer is hotter than the range says.")
    out["miss_direction"] = {"htt": {"too_high": h_hi, "too_low": h_lo},
                             "prospie": {"too_high": p_hi, "too_low": p_lo}}

    print(f"\n  By time into the trial (HTT):")
    print(f"  {'minutes':>10s} {'n':>6s} {'coverage':>9s} {'bias':>8s} {'too high':>9s} {'too low':>8s}")
    tb = pd.cut(res["minute"], [0, 10, 30, 60, 90, 121], right=False)
    rows = []
    for b, g in res.groupby(tb, observed=True):
        hi, lo = split(g)
        rows.append({"minutes": str(b), "n": int(len(g)), "coverage": cov90(g),
                     "bias": float((g["pred"] - g["core_c"]).mean()), "too_high": hi, "too_low": lo})
        print(f"  {str(b):>10s} {len(g):>6d} {cov90(g):>9.1%} {rows[-1]['bias']:>+8.3f} "
              f"{hi:>9.1%} {lo:>8.1%}")
    out["by_time"] = rows

    full = res.groupby(["subject", "condition"])["minute"].transform("max") >= 115
    drift = (res[full].groupby(["condition", tb[full]], observed=True)
             .agg(hr=("hr", "median"), core=("core_c", "median"), est=("pred", "median")))
    print(f"\n  Trials that ran the full two hours (medians):")
    print(f"  {'':8s} {'minutes':>10s} {'HR':>6s} {'true core':>10s} {'Ember':>7s}")
    for (cond, b), r in drift.iterrows():
        print(f"  {cond:8s} {str(b):>10s} {r['hr']:>6.0f} {r['core']:>10.2f} {r['est']:>7.2f}")
    print("  Late in a long steady walk, heart rate keeps rising while core levels off")
    print("  (cardiovascular drift). ECTemp reads the rising heart rate as rising core,")
    print("  so Ember over-reads: more false alarms, not more misses.")

    section("6. ALERT TIMING CAVEAT: these trials stop early")
    left = trial_end_after_danger(res)
    left_p = trial_end_after_danger(pros)
    t = alert_timing(res)
    never = t[t["act_lag"].isna()]
    print(f"\n  The HTT protocol stopped a trial at core 39.0 °C or HR 180 bpm. After true")
    print(f"  core first reached {ACT_NOW_C} °C, HTT trials had a median of {np.median(left):.0f} min "
          f"of data left (IQR {np.percentile(left, 25):.0f}-{np.percentile(left, 75):.0f});")
    print(f"  PROSPIE trials had {np.median(left_p):.0f} min (IQR {np.percentile(left_p, 25):.0f}-"
          f"{np.percentile(left_p, 75):.0f}). \"Act now never fired\" means \"not before")
    print(f"  the trial ended\", so the two datasets' alert counts are not directly comparable.")
    print(f"  Of the {len(never)} HTT trials where Act now never fired, "
          f"{int((never['watch_lag'].notna()).sum())} had Watch on by the end.")
    out["minutes_left_after_danger"] = {"htt_median": float(np.median(left)),
                                        "prospie_median": float(np.median(left_p))}

    section("7. SENSITIVITY: is it the cleaning or the reference?")
    cols = [("all trials", ember)]
    tp = res[res["temp_method"] == "TP"]
    cols.append(("pill (TP) only", scorecard(tp)))
    raw_df = load_htt(clean_dips=False, verbose=False)
    nodip = predict(raw_df, model, cor, raw)
    cols.append(("no dip rule", scorecard(nodip)))
    table(cols)
    out["sensitivity"] = {k: v for k, v in cols[1:]}

    section("8. WHAT THIS DOES AND DOES NOT SHOW")
    print("""
  - Same maths as the device (header coefficients and tables), run on
    people, a lab and a core sensor it was never fitted to.
  - Reference differs: ingestible pill here, rectal in PROSPIE. Pill and
    rectal disagree by a few tenths during exercise, so part of any
    coverage loss is the reference, not Ember.
  - The HR sensor in the HTT treadmill trials is not stated; PROSPIE's
    was a chest ECG or Polar strap. Ember's own pulse sensor is neither.
  - One protocol (steady walking): it tests the step from "chamber
    conditions" to "walking for two hours", not every kind of work.
  - Cleaning rules (load_htt.py) were fixed before this script was run.""")

    with open(os.path.join(HERE, "external_htt_results.json"), "w") as fh:
        json.dump(out, fh, indent=2, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    print("\n  wrote external_htt_results.json")


if __name__ == "__main__":
    main()
