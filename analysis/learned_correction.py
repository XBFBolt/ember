"""
Can a learned model reduce ECTemp's lag without breaking the calibrated range?

The shipped estimate lags a fast rise: at true core >= 38.5 C the 90% range
holds only ~67% of the time, and Act now never fired in 34 of 73 trials that
got there (judges_results.txt). This script tests fixes for that lag under
exactly the protocol the judge numbers use, so the comparison is like for like.

Variants
--------
  A  shipped       ECTemp as in the firmware (published GAMMA_SQ),
                   CT0 from the first 10 minutes' heart rate
  A2 offset        A + a constant shift learned on the training subjects
                   (ablation: how much of any gain is just removing bias?)
  B  tuned gamma   ECTemp with the process noise chosen on the training
                   subjects only (smallest RMSE). B2/B1/B0 untouched.
  C  ridge, HR     A + a linear model of A's error, from heart-rate features
                   only (what the device already computes)
  C2 ridge, +amb   C + ambient temperature / humidity
  D  ridge, all    C2 + chest skin temperature and work/rest
  E  trees, all    same features as D, gradient-boosted trees (ceiling check:
                   does a flexible model buy anything over a linear one?)

Every variant is wrapped in the same 6-strata conformal calibration as
conformal_table.h, so a 90% range still has to mean 90%.

Protocol (no held-out subject ever touches its own model or calibration)
--------
  outer   leave one subject out
  inner   for C-E, GroupKFold over the remaining subjects gives out-of-fold
          corrected predictions; the conformal table is fitted on those, so
          the calibration reflects people the model did not train on
  final   model refit on all training subjects, applied to the held-out one

Every feature is causal (uses only the current and earlier minutes) and has
a v2 device counterpart: heart rate (pulse sensors), resting HR (BASELINE),
chest skin (thermistors), ambient T/RH (SHT40), work/rest (IMU). Deliberately
left out: sex (fairness), minutes since start and condition (they would teach
the model the PROSPIE protocol, not physiology).

Caveat to state with any result: seven variants are compared on the same
data, so the best one's numbers are slightly optimistic.

This is the EXPERIMENT that chose variant C. The shipped model is
correction.py: the same idea with features defined exactly as the firmware
computes them, no imputation, and the correction off without a baseline.
Its numbers are in judges_results.txt (section 7) and differ slightly.

Run:
    python3 learned_correction.py --data "Prospie dataset_open access V3.xlsx" \
        | tee learned_correction_results.txt
"""

import argparse
import json
import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import load_data
from conformal import StratifiedConformal, coverage
from ectemp import CT_CLAMP, GAMMA_SQ, init_from_resting_hr, run_series, self_check
from evaluate import basic_metrics, detection_metrics, parse_hr_types
from judges_results import ACT_NOW_C, TEMP_BANDS, WATCH_C, alert_timing

N_STRATA = 6          # same as export_firmware_table.py / conformal_table.h
LEVEL = 0.90
INNER_FOLDS = 5
GAMMA_MULTS = (1, 2, 4, 8, 16, 32)
N_BOOT = 5000         # same resamples and seed as judges_results.py
BOOT_SEED = 42

EXTRA_COLS = {
    "skin_chest": "SkinTemp chest",
    "amb_t": "Environmental temperature (chamber or cooling area outside chamber) Temp",
    "amb_rh": "Environmental temperature (chamber or cooling area outside chamber) Humidity",
    "workrest": "Activity workrest",   # 1 = work (treadmill), 2 = rest
}

# HR-only: everything the device already computes (filter output, its own
# heart rate history, the BASELINE resting HR). No new sensor dependencies.
HR_FEATS = ["pred", "pred_rate10", "hr5", "hr_rate10", "hr_above_rest"]
AMB_FEATS = HR_FEATS + ["amb_t", "amb_rh"]
ALL_FEATS = AMB_FEATS + ["skin_chest", "skin_rate10", "working"]


# ------------------------------------------------------------- filtering

def run_filter(df, gamma_sq):
    """ECTemp over every trial; same CT0 rule as evaluate.predict_all."""
    out = np.full(len(df), np.nan)
    for _, pos in df.groupby(["subject", "condition"], sort=False).indices.items():
        g = df.iloc[pos]
        rest = g.loc[g["minute"] < g["minute"].min() + 10, "hr"].median()
        ct0 = init_from_resting_hr(rest) if np.isfinite(rest) else 37.1
        pred, _ = run_series(g["hr"].to_numpy(), ct_init=ct0,
                             step_seconds=60.0, gamma_sq=gamma_sq)
        out[pos] = pred
    return out


def add_features(df):
    """Causal per-minute features. df must be sorted by trial, then minute."""
    df = df.copy()
    keys = [df["subject"], df["condition"]]
    by = lambda col: df.groupby(keys, sort=False)[col]

    first_min = by("minute").transform("min")
    df["rest_hr"] = (df["hr"].where(df["minute"] < first_min + 10)
                     .groupby(keys, sort=False).transform("median"))
    # 5-minute mean of observed HR, carried forward over gaps of up to 10 min
    # (conditions 1-3 only have HR every 5 minutes).
    df["hr5"] = by("hr").transform(
        lambda s: s.rolling(5, min_periods=1).mean().ffill(limit=10))
    df["hr_rate10"] = df["hr5"] - by("hr5").shift(10)
    df["hr_above_rest"] = df["hr5"] - df["rest_hr"]
    df["pred_rate10"] = df["pred"] - by("pred").shift(10)
    df["skin_chest"] = by("skin_chest").transform(lambda s: s.ffill(limit=5))
    df["skin_rate10"] = df["skin_chest"] - by("skin_chest").shift(10)
    df["working"] = (df["workrest"] == 1).astype(float)
    return df


# ------------------------------------------------------------------ LOSO

def _frame(te, est, lo, hi):
    keep = ["subject", "condition", "minute", "sex", "core_c"]
    out = te[keep].copy()
    out["pred"] = est
    out["lo"] = lo
    out["hi"] = hi
    return out


def loso_fixed(scored, pred_col):
    """A filter with no fitted parameters: calibrate on the other subjects."""
    pieces = []
    for held in sorted(scored.subject.unique()):
        tr = scored[scored.subject != held]
        te = scored[scored.subject == held]
        sc = StratifiedConformal(n_strata=N_STRATA, levels=(LEVEL,)).fit(
            tr[pred_col].to_numpy(), tr["core_c"].to_numpy())
        p = te[pred_col].to_numpy()
        lo, hi = sc.interval(p, LEVEL)
        pieces.append(_frame(te, p, lo, hi))
    return pd.concat(pieces, ignore_index=True)


def loso_tuned_gamma(scored, gamma_cols):
    """Pick the process noise by RMSE on the training subjects, per fold."""
    pieces, chosen = [], []
    for held in sorted(scored.subject.unique()):
        tr = scored[scored.subject != held]
        te = scored[scored.subject == held]
        rmse = {m: np.sqrt(np.mean((tr[c] - tr["core_c"]) ** 2))
                for m, c in gamma_cols.items()}
        m = min(rmse, key=rmse.get)
        chosen.append(m)
        col = gamma_cols[m]
        sc = StratifiedConformal(n_strata=N_STRATA, levels=(LEVEL,)).fit(
            tr[col].to_numpy(), tr["core_c"].to_numpy())
        p = te[col].to_numpy()
        lo, hi = sc.interval(p, LEVEL)
        pieces.append(_frame(te, p, lo, hi))
    return pd.concat(pieces, ignore_index=True), chosen


def make_offset():
    return DummyRegressor(strategy="mean")


def make_ridge():
    return make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                         StandardScaler(), Ridge(alpha=10.0))


def make_trees():
    return HistGradientBoostingRegressor(
        max_depth=3, learning_rate=0.05, max_iter=300, min_samples_leaf=100,
        l2_regularization=1.0, early_stopping=False, random_state=0)


def loso_correction(scored, feats, make_model):
    """Shipped filter + learned correction of its error, nested LOSO."""
    pieces = []
    for held in sorted(scored.subject.unique()):
        tr = scored[scored.subject != held]
        te = scored[scored.subject == held]
        X, y = tr[feats], (tr["core_c"] - tr["pred"]).to_numpy()

        oof = np.empty(len(tr))
        for a, b in GroupKFold(n_splits=INNER_FOLDS).split(X, y, tr["subject"]):
            oof[b] = make_model().fit(X.iloc[a], y[a]).predict(X.iloc[b])
        cal_pred = np.clip(tr["pred"].to_numpy() + oof, *CT_CLAMP)
        sc = StratifiedConformal(n_strata=N_STRATA, levels=(LEVEL,)).fit(
            cal_pred, tr["core_c"].to_numpy())

        model = make_model().fit(X, y)
        p = np.clip(te["pred"].to_numpy() + model.predict(te[feats]), *CT_CLAMP)
        lo, hi = sc.interval(p, LEVEL)
        pieces.append(_frame(te, p, lo, hi))
    return pd.concat(pieces, ignore_index=True)


# --------------------------------------------------------------- metrics

def sex_bias_ci(res):
    """
    Bootstrap over subjects of the pooled bias difference (M minus F).
    Same resampling sequence as evaluate.bootstrap_group_diff, computed from
    per-subject sums so it runs in a second instead of minutes.
    """
    r = res.dropna(subset=["sex"])
    if r["sex"].nunique() != 2:
        return None
    err = r["pred"] - r["core_c"]
    s_sum = err.groupby(r["subject"]).sum()
    s_n = err.groupby(r["subject"]).size()
    a, b = sorted(r["sex"].unique())
    subs = {g: r[r["sex"] == g].subject.unique() for g in (a, b)}

    def bias(ids):
        return s_sum[ids].sum() / s_n[ids].sum()

    rng = np.random.default_rng(BOOT_SEED)
    diffs = np.empty(N_BOOT)
    for i in range(N_BOOT):
        pick = [rng.choice(subs[g], size=len(subs[g]), replace=True) for g in (a, b)]
        diffs[i] = bias(pick[1]) - bias(pick[0])
    return {"groups": [a, b],
            "point": float(bias(subs[b]) - bias(subs[a])),
            "ci": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]}


def summarise(res):
    m = basic_metrics(res["core_c"], res["pred"])
    det = detection_metrics(res["core_c"], res["pred"], WATCH_C)
    out = {
        "rmse": m["rmse"], "bias": m["bias"], "mae": m["mae"],
        "coverage_90": coverage(res["core_c"], res["lo"].to_numpy(), res["hi"].to_numpy()),
        "mean_width": float(np.mean(res["hi"] - res["lo"])),
        "sens_38": det["sensitivity"], "spec_38": det["specificity"],
    }

    for lo, hi, label in TEMP_BANDS:
        s = res[(res["core_c"] >= lo) & (res["core_c"] < hi)]
        out[f"cov_{label}"] = coverage(s["core_c"], s["lo"].to_numpy(), s["hi"].to_numpy())

    # Rising: true core up >= 0.2 C versus 5 minutes earlier (as judges_results)
    d5 = res["core_c"] - res.groupby(["subject", "condition"])["core_c"].shift(5)
    rising = res[d5 >= 0.2]
    out["cov_rising"] = coverage(rising["core_c"], rising["lo"].to_numpy(), rising["hi"].to_numpy())

    t = alert_timing(res)
    n = len(t)
    out["danger_trials"] = n
    for key in ("watch", "act"):
        lag = t[f"{key}_lag"]
        out[f"{key}_on"] = int(t[f"{key}_on"].sum())
        out[f"{key}_never"] = int(lag.isna().sum())
        late = lag[lag > 0]
        out[f"{key}_late_median"] = float(late.median()) if len(late) else 0.0

    # False alarms: trials whose true core never reached 38.5 but Act now fired
    per = res.groupby(["subject", "condition"]).agg(tmax=("core_c", "max"),
                                                    emax=("pred", "max"))
    calm = per[per["tmax"] < ACT_NOW_C]
    out["calm_trials"] = int(len(calm))
    out["act_false_trials"] = int((calm["emax"] >= ACT_NOW_C).sum())
    # Watch on while true core is under 37.5
    cool = res[res["core_c"] < 37.5]
    out["watch_false_min"] = float(np.mean(cool["pred"] >= WATCH_C)) if len(cool) else float("nan")

    out["sex_bias"] = sex_bias_ci(res)
    return out


# ---------------------------------------------------------------- report

ROWS = [
    ("RMSE (°C)",                    "rmse",               "{:.3f}"),
    ("bias (°C)",                    "bias",               "{:+.3f}"),
    ("90% coverage",                 "coverage_90",        "{:.1%}"),
    ("mean range width (°C)",        "mean_width",         "{:.2f}"),
    ("coverage, true <37.5",         "cov_normal (<37.5)", "{:.1%}"),
    ("coverage, true 37.5-38.0",     "cov_warm (37.5-38.0)", "{:.1%}"),
    ("coverage, true 38.0-38.5",     "cov_watch (38.0-38.5)", "{:.1%}"),
    ("coverage, true >=38.5",        "cov_act now (≥38.5)", "{:.1%}"),
    ("coverage, rising",             "cov_rising",         "{:.1%}"),
    ("sensitivity at 38.0",          "sens_38",            "{:.3f}"),
    ("specificity at 38.0",          "spec_38",            "{:.3f}"),
    ("Watch on at true 38.5",        "watch_on",           "{:d}"),
    ("Watch never fired",            "watch_never",        "{:d}"),
    ("Act now on at true 38.5",      "act_on",             "{:d}"),
    ("Act now never fired",          "act_never",          "{:d}"),
    ("Act now late, median min",     "act_late_median",    "{:.0f}"),
    ("Act now false alarm trials",   "act_false_trials",   "{:d}"),
    ("Watch on while true <37.5",    "watch_false_min",    "{:.1%}"),
]


def print_table(results):
    names = list(results)
    w = 14
    print(f"\n  {'':30s}" + "".join(f"{n:>{w}s}" for n in names))
    print("  " + "-" * (30 + w * len(names)))
    for label, key, fmt in ROWS:
        cells = []
        for n in names:
            v = results[n].get(key)
            cells.append("—" if v is None or (isinstance(v, float) and np.isnan(v))
                         else fmt.format(v))
        print(f"  {label:30s}" + "".join(f"{c:>{w}s}" for c in cells))
    print(f"  {'sex bias M-F (°C)':30s}" + "".join(
        f"{results[n]['sex_bias']['point']:>+{w}.3f}" if results[n]["sex_bias"] else f"{'—':>{w}s}"
        for n in names))
    print(f"  {'  95% CI':30s}" + "".join(
        f"{'[%+.2f,%+.2f]' % tuple(results[n]['sex_bias']['ci']):>{w}s}"
        if results[n]["sex_bias"] else f"{'—':>{w}s}" for n in names))
    any_r = next(iter(results.values()))
    print(f"\n  Alert rows count trials out of {any_r['danger_trials']} that reached "
          f"true {ACT_NOW_C}; false alarms out of {any_r['calm_trials']} that did not.")


def ridge_coefficients(scored, feats):
    """Standardised coefficients of the final ridge model, for interpretation."""
    model = make_ridge().fit(scored[feats], scored["core_c"] - scored["pred"])
    names = model[:-1].get_feature_names_out(feats)
    coef = model[-1].coef_
    order = np.argsort(-np.abs(coef))
    print("  Ridge (all subjects), standardised coefficients, largest first:")
    for i in order:
        print(f"    {names[i]:28s} {coef[i]:+.3f}")
    print(f"    {'intercept':28s} {model[-1].intercept_:+.3f}")


# ------------------------------------------------------------------ main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="Prospie dataset_open access V3.xlsx")
    ap.add_argument("--hr-types", default="2,3")
    ap.add_argument("--out", default="learned_correction_results.json")
    args = ap.parse_args()

    if not self_check(verbose=False):
        sys.exit("ECTemp coefficient check FAILED")

    t0 = time.time()
    df = load_data.load_prospie(args.data, hr_types=parse_hr_types(args.hr_types),
                                verbose=False, extra_cols=EXTRA_COLS)

    gamma_cols = {}
    for m in GAMMA_MULTS:
        col = "pred" if m == 1 else f"pred_g{m}"
        df[col] = run_filter(df, GAMMA_SQ * m)
        gamma_cols[m] = col
    df = add_features(df)
    scored = df[df["core_c"].notna()].reset_index(drop=True)

    print("=" * 72)
    print(" EMBER: CAN A LEARNED MODEL FIX THE LAG?")
    print("=" * 72)
    print(f"\n PROSPIE V3, chest HR, leave-one-subject-out, {N_STRATA}-strata conformal")
    print(f" {scored.subject.nunique()} subjects, {len(scored)} scored minutes, "
          f"{scored.groupby(['subject', 'condition']).ngroups} trials")

    results, frames = {}, {}
    frames["A shipped"] = loso_fixed(scored, "pred")
    frames["A2 offset"] = loso_correction(scored, ["pred"], make_offset)
    frames["B gamma"], chosen = loso_tuned_gamma(scored, gamma_cols)
    frames["C ridgeHR"] = loso_correction(scored, HR_FEATS, make_ridge)
    frames["C2 +amb"] = loso_correction(scored, AMB_FEATS, make_ridge)
    frames["D ridgeAll"] = loso_correction(scored, ALL_FEATS, make_ridge)
    frames["E trees"] = loso_correction(scored, ALL_FEATS, make_trees)
    for name, fr in frames.items():
        results[name] = summarise(fr)

    print("\n" + "=" * 72)
    print(" 1. ALL VARIANTS, HELD-OUT")
    print("=" * 72)
    print_table(results)

    vals, counts = np.unique(chosen, return_counts=True)
    print("\n  B: gamma multiplier chosen per fold (by training RMSE): " +
          ", ".join(f"x{v} in {c} folds" for v, c in zip(vals, counts)))

    a = results["A shipped"]
    print("\n  Sanity check, A should match judges_results.txt: "
          f"coverage {a['coverage_90']:.1%} (89.7%), Act now never {a['act_never']} (34), "
          f"Watch on {a['watch_on']} (47)")

    print("\n" + "=" * 72)
    print(" 2. GAMMA TRADE-OFF (exploratory: each row is LOSO, but looking at")
    print("    all rows and picking one is a selection, not a held-out result)")
    print("=" * 72)
    grid = {}
    for m, col in gamma_cols.items():
        grid[f"x{m}"] = summarise(loso_fixed(scored, col))
    print(f"\n  {'gamma':>6s} {'RMSE':>7s} {'cov90':>7s} {'width':>7s} {'cov>=38.5':>10s} "
          f"{'Act on':>7s} {'Act never':>10s} {'Act false':>10s}")
    for k, r in grid.items():
        print(f"  {k:>6s} {r['rmse']:>7.3f} {r['coverage_90']:>7.1%} {r['mean_width']:>7.2f} "
              f"{r['cov_act now (≥38.5)']:>10.1%} {r['act_on']:>7d} {r['act_never']:>10d} "
              f"{r['act_false_trials']:>10d}")

    print("\n" + "=" * 72)
    print(" 3. WHAT THE LINEAR CORRECTION LEARNED")
    print("=" * 72)
    print("\n  C (HR only, the candidate for the device):")
    ridge_coefficients(scored, HR_FEATS)
    print("\n  D (all features):")
    ridge_coefficients(scored, ALL_FEATS)

    print("\n  Caveats: seven variants compared on the same data, so the best")
    print("  one's numbers are slightly optimistic. Ambient T/RH here is the")
    print("  chamber; on the device the SHT40 sits near the body. Work/rest is")
    print("  the protocol label; on the device it would come from the IMU.")
    print("  Calibrated on chest heart rate, as the shipped table is.")

    with open(args.out, "w") as fh:
        json.dump({"variants": results, "gamma_grid": grid,
                   "gamma_chosen": [int(c) for c in chosen],
                   "features_hr": HR_FEATS, "features_amb": AMB_FEATS,
                   "features_all": ALL_FEATS},
                  fh, indent=2, default=float)
    print(f"\n  wrote {args.out}  ({time.time() - t0:.0f} s)")


if __name__ == "__main__":
    main()
