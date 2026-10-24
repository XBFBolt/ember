"""
Ember - the evaluation that makes this project a contribution rather than a
reimplementation.

Four results, all producible in one evening on openly licensed data:

  1. HONEST ACCURACY. Run ECTemp under leave-one-subject-out and report what
     it actually achieves, next to what its original paper reported. The one
     independent standardized benchmark of this literature found the gap is
     large and in one dataset the model scored a NEGATIVE R-squared - worse
     than predicting the mean.

  2. CALIBRATED UNCERTAINTY. Measure the real coverage of the Kalman
     posterior variance, then replace it with stratified split conformal
     intervals and measure again. Published work found the Kalman interval
     badly under-covers; conformal gives intervals that hold.

  3. SEX-STRATIFIED PERFORMANCE. The literature on this algorithm is
     overwhelmingly male. PROSPIE is sex-balanced. Report accuracy and
     coverage separately for men and women with bootstrap intervals on the
     difference. Whatever the answer, nobody has published it.

  4. A REFUSAL MODE. Because accuracy collapses in exactly the regime that
     matters, the device should decline to answer when its own interval is
     too wide. The risk-coverage curve is how you pick that threshold.

Run:
    python3 evaluate.py --synthetic
    python3 evaluate.py --data "Prospie dataset_open access V3.xlsx"
"""

import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ectemp import run_series, init_from_resting_hr, self_check
from conformal import (StratifiedConformal, coverage_table, risk_coverage,
                       gaussian_interval, coverage, DEFAULT_LEVELS)
import load_data

ELEVATED_C = 38.0


# ----------------------------------------------------------------- metrics

def basic_metrics(y_true, y_pred):
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    m = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[m], y_pred[m]
    err = y_pred - y_true
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    return {
        "n": int(y_true.size),
        "rmse": float(np.sqrt(np.mean(err ** 2))),
        "mae": float(np.mean(np.abs(err))),
        "bias": float(np.mean(err)),
        "sd": float(np.std(err, ddof=1)) if y_true.size > 1 else float("nan"),
        "r2": 1.0 - ss_res / ss_tot if ss_tot > 1e-9 else float("nan"),
        "loa_lo": float(np.mean(err) - 1.96 * np.std(err, ddof=1)),
        "loa_hi": float(np.mean(err) + 1.96 * np.std(err, ddof=1)),
    }


def detection_metrics(y_true, y_pred, thresh=ELEVATED_C):
    yt = np.asarray(y_true, float) >= thresh
    yp = np.asarray(y_pred, float) >= thresh
    tp = int(np.sum(yt & yp)); fn = int(np.sum(yt & ~yp))
    tn = int(np.sum(~yt & ~yp)); fp = int(np.sum(~yt & yp))
    sens = tp / (tp + fn) if (tp + fn) else float("nan")
    spec = tn / (tn + fp) if (tn + fp) else float("nan")
    return {"sensitivity": sens, "specificity": spec,
            "prevalence": float(np.mean(yt)),
            "tp": tp, "fn": fn, "tn": tn, "fp": fp}


# ------------------------------------------------------------------- core

def predict_all(df, personalise_ct0=True):
    """
    Run ECTemp over every (subject, condition) trial.
    Adds columns: pred, var.
    """
    out = []
    for (sid, cond), g in df.groupby(["subject", "condition"], sort=False):
        g = g.sort_values("minute")
        if personalise_ct0:
            # Use the subject's own early resting HR rather than assuming
            # 37.1 C for everyone. Cheap and defensible individualisation.
            # First 10 minutes (seated rest); HR may be sparse or missing there.
            rest = g.loc[g["minute"] < g["minute"].min() + 10, "hr"].median()
            ct0 = init_from_resting_hr(rest) if np.isfinite(rest) else 37.1
        else:
            ct0 = 37.1
        pred, var = run_series(g["hr"].to_numpy(), ct_init=ct0,
                               step_seconds=60.0)
        gg = g.copy()
        gg["pred"] = pred
        gg["var"] = var
        gg["ct0"] = ct0
        out.append(gg)
    return pd.concat(out, ignore_index=True)


def loso(df, n_strata=6, seed=0):
    """
    Leave one subject out. For each held-out subject, the conformal
    calibration is fitted on the OTHER subjects only - never on the test
    subject, which is a leak that has appeared in published work.
    """
    # Score only minutes with a reference core temperature. The filter has
    # already run over every minute (predict-only where HR was missing).
    df = df[df["core_c"].notna()]
    subjects = sorted(df.subject.unique())
    if len(subjects) < 4:
        sys.exit(f"only {len(subjects)} subjects; LOSO needs more")

    pieces = []
    for held in subjects:
        te = df[df.subject == held]
        tr = df[df.subject != held]
        sc = StratifiedConformal(n_strata=n_strata).fit(
            tr["pred"].to_numpy(), tr["core_c"].to_numpy())
        t = te.copy()
        for a in DEFAULT_LEVELS:
            lo, hi = sc.interval(t["pred"].to_numpy(), a)
            t[f"c_lo_{a}"] = lo
            t[f"c_hi_{a}"] = hi
        t["hw90"] = sc.half_width(t["pred"].to_numpy(), 0.90)
        pieces.append(t)
    return pd.concat(pieces, ignore_index=True)


def bootstrap_group_diff(res, key="rmse", by="sex", n_boot=2000, seed=0):
    """
    Bootstrap over SUBJECTS (not samples) for the difference in a metric
    between groups. Resampling samples would ignore that observations within
    a subject are not independent and would give you a fake tiny interval.
    """
    rng = np.random.default_rng(seed)
    groups = [g for g in res[by].dropna().unique()]
    if len(groups) != 2:
        return None
    a, b = sorted(groups)
    subs = {g: res[res[by] == g].subject.unique() for g in (a, b)}
    if min(len(subs[a]), len(subs[b])) < 3:
        return None

    def metric(frame):
        return basic_metrics(frame["core_c"], frame["pred"])[key]

    diffs = []
    for _ in range(n_boot):
        pick = []
        for g in (a, b):
            s = rng.choice(subs[g], size=len(subs[g]), replace=True)
            pick.append(pd.concat([res[res.subject == x] for x in s]))
        diffs.append(metric(pick[1]) - metric(pick[0]))
    diffs = np.asarray(diffs)
    return {
        "groups": (a, b),
        "point": metric(res[res[by] == b]) - metric(res[res[by] == a]),
        "ci": (float(np.percentile(diffs, 2.5)),
               float(np.percentile(diffs, 97.5))),
        "p_exceeds_zero": float(np.mean(diffs > 0)),
    }


# ------------------------------------------------------------------ report

def report(res, label=""):
    print("\n" + "=" * 68)
    print(f" 1. HONEST ACCURACY  (leave-one-subject-out){'  ' + label if label else ''}")
    print("=" * 68)
    m = basic_metrics(res["core_c"], res["pred"])
    print(f"  n = {m['n']} samples, {res.subject.nunique()} subjects")
    print(f"  RMSE   {m['rmse']:.3f} C")
    print(f"  MAE    {m['mae']:.3f} C")
    print(f"  bias   {m['bias']:+.3f} C")
    print(f"  95% limits of agreement  {m['loa_lo']:+.2f} to {m['loa_hi']:+.2f} C")
    print(f"  R^2    {m['r2']:.4f}")
    print()
    print("  For reference, published figures for this algorithm:")
    print("    original paper (Buller 2013)           RMSE 0.30, R^2 0.71")
    print("    USARIEM product page                   RMSE 0.30, LoA +/-0.63")
    print("    independent standardized benchmark     RMSE 0.41 (D1), 0.66 (D2)")
    print("                                           R^2  0.47 (D1), -0.40 (D2)")
    if m["r2"] < 0:
        print("\n  Your R^2 is NEGATIVE: on this data the model is worse than")
        print("  always predicting the mean core temperature. Report that.")

    d = detection_metrics(res["core_c"], res["pred"])
    print(f"\n  Detecting core temp >= {ELEVATED_C} C "
          f"(prevalence {d['prevalence']*100:.0f}%)")
    print(f"    sensitivity {d['sensitivity']:.3f}   "
          f"specificity {d['specificity']:.3f}")
    print(f"    missed {d['fn']} of {d['tp']+d['fn']} elevated samples")
    print("  Benchmark reference: sensitivity 0.71 (D1), 0.33 (D2)")

    print("\n" + "=" * 68)
    print(" 2. IS THE UNCERTAINTY HONEST?")
    print("=" * 68)
    print(f"  {'nominal':>8} | {'Kalman':>8} {'width':>7} | "
          f"{'conformal':>9} {'width':>7}")
    print("  " + "-" * 50)
    rows = []
    for a in DEFAULT_LEVELS:
        glo, ghi = gaussian_interval(res["pred"], res["var"], a)
        kc = coverage(res["core_c"], glo, ghi)
        kw = float(np.mean(ghi - glo))
        cc = coverage(res["core_c"], res[f"c_lo_{a}"], res[f"c_hi_{a}"])
        cw = float(np.mean(res[f"c_hi_{a}"] - res[f"c_lo_{a}"]))
        rows.append({"nominal": a, "kalman_coverage": kc, "kalman_width": kw,
                     "conformal_coverage": cc, "conformal_width": cw})
        print(f"  {a:>8.2f} | {kc:>8.3f} {kw:>7.3f} | {cc:>9.3f} {cw:>7.3f}")
    print("\n  A 90% interval that covers far less than 90% of the time is")
    print("  worse than no interval, because a user acts on it.")

    print("\n" + "=" * 68)
    print(" 3. DOES IT WORK EQUALLY WELL FOR EVERYONE?")
    print("=" * 68)
    if res["sex"].notna().any() and res["sex"].nunique() == 2:
        for g, sub in res.groupby("sex"):
            mm = basic_metrics(sub["core_c"], sub["pred"])
            cv = coverage(sub["core_c"], sub["c_lo_0.9"], sub["c_hi_0.9"])
            print(f"  {g}  n_subj={sub.subject.nunique():2d}  "
                  f"RMSE {mm['rmse']:.3f}  bias {mm['bias']:+.3f}  "
                  f"R^2 {mm['r2']:+.3f}  90% coverage {cv:.3f}")
        # BIAS is the primary metric here, and that is not an arbitrary
        # choice. A systematic offset between groups moves the bias a lot
        # and the RMSE almost not at all, because RMSE is dominated by
        # within-subject error. Testing this pipeline against a simulated
        # group difference, bias detected it and RMSE missed it completely.
        # An audit run on RMSE alone would conclude the model is fair.
        for key, name in (("bias", "BIAS"), ("rmse", "RMSE")):
            # Same resamples and seed as judges_results.py, so both report one CI.
            bd = bootstrap_group_diff(res, key, n_boot=5000, seed=42)
            if not bd:
                continue
            a, b = bd["groups"]
            excl = bd["ci"][0] > 0 or bd["ci"][1] < 0
            tag = "EXCLUDES ZERO" if excl else "includes zero"
            star = " <- primary" if key == "bias" else ""
            print(f"\n  {name} difference ({b} minus {a}): {bd['point']:+.3f} C"
                  f"{star}")
            print(f"    bootstrap 95% CI over subjects "
                  f"[{bd['ci'][0]:+.3f}, {bd['ci'][1]:+.3f}]  {tag}")
        print("\n  Note on metric choice: a systematic offset between groups")
        print("  shows up in BIAS and barely moves RMSE. Audit on bias, or")
        print("  you will declare a biased model fair.")
        print("\n  Context: published validations of this algorithm are")
        print("  overwhelmingly male. One 251-subject study had 36 women and")
        print("  ran no sex analysis; several others had none at all.")
    else:
        print("  No usable sex column - skipped.")

    if "trial_hr_type" in res and res["trial_hr_type"].notna().any():
        print("\n  By heart-rate sensor (trial's main sensor):")
        for t, sub in res.groupby("trial_hr_type"):
            mm = basic_metrics(sub["core_c"], sub["pred"])
            cv = coverage(sub["core_c"], sub["c_lo_0.9"], sub["c_hi_0.9"])
            name = load_data.HR_TYPE_NAMES.get(int(t), str(t))
            print(f"    {name:20s} n_subj={sub.subject.nunique():2d}  n={mm['n']:5d}  "
                  f"RMSE {mm['rmse']:.3f}  bias {mm['bias']:+.3f}  90% coverage {cv:.3f}")

    print("\n" + "=" * 68)
    print(" 4. WHEN SHOULD THE DEVICE REFUSE TO ANSWER?")
    print("=" * 68)
    rc = risk_coverage(res["core_c"], res["pred"], res["hw90"])
    print(f"  {'answered':>9} {'RMSE':>7} {'MAE':>7}   width threshold")
    for r in rc[::8]:
        print(f"  {r['answered_fraction']*100:>8.0f}% {r['rmse']:>7.3f} "
              f"{r['mae']:>7.3f}   <= {r['threshold']:.3f} C")
    print("\n  Pick the operating point deliberately and defend it. A device")
    print("  that answers 70% of the time and is right when it does beats one")
    print("  that always answers and is sometimes badly wrong.")

    return {"overall": m, "detection": d, "coverage": rows}


# ------------------------------------------------------------------- plots

def make_figures(res, prefix="ember"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    INK, ACC, WARN = "#1f2430", "#2f6f8f", "#b4531c"

    fig, axes = plt.subplots(2, 2, figsize=(12.5, 9))

    # (a) Bland-Altman
    ax = axes[0, 0]
    mean_v = (res["pred"] + res["core_c"]) / 2
    diff = res["pred"] - res["core_c"]
    ax.scatter(mean_v, diff, s=3, alpha=0.18, color=ACC, edgecolors="none")
    b, s = diff.mean(), diff.std(ddof=1)
    for y, ls, lab in [(b, "-", f"bias {b:+.2f}"),
                       (b + 1.96 * s, "--", f"+1.96 SD {b+1.96*s:+.2f}"),
                       (b - 1.96 * s, "--", f"-1.96 SD {b-1.96*s:+.2f}")]:
        ax.axhline(y, ls=ls, color=WARN, lw=1.2)
        ax.text(ax.get_xlim()[1], y, f" {lab}", va="center", fontsize=8,
                color=WARN)
    ax.set_xlabel("mean of estimate and reference (°C)")
    ax.set_ylabel("estimate − reference (°C)")
    ax.set_title("Bland–Altman, leave-one-subject-out", fontsize=11)
    ax.grid(alpha=0.15)

    # (b) coverage
    ax = axes[0, 1]
    noms = list(DEFAULT_LEVELS)
    kcov, ccov = [], []
    for a in noms:
        glo, ghi = gaussian_interval(res["pred"], res["var"], a)
        kcov.append(coverage(res["core_c"], glo, ghi))
        ccov.append(coverage(res["core_c"], res[f"c_lo_{a}"], res[f"c_hi_{a}"]))
    x = np.arange(len(noms))
    ax.bar(x - 0.2, kcov, 0.4, color=WARN, label="Kalman posterior variance")
    ax.bar(x + 0.2, ccov, 0.4, color=ACC, label="stratified conformal")
    ax.plot(x, noms, "k--o", lw=1.4, ms=5, label="nominal (what is claimed)")
    ax.set_xticks(x); ax.set_xticklabels([f"{a:.0%}" for a in noms])
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("claimed confidence level")
    ax.set_ylabel("actual coverage")
    ax.set_title("Does the interval mean what it says?", fontsize=11)
    ax.legend(fontsize=8); ax.grid(axis="y", alpha=0.15)

    # (c) error vs true temperature - where it fails
    ax = axes[1, 0]
    bins = np.arange(36.5, 40.1, 0.25)
    idx = np.digitize(res["core_c"], bins)
    cx, cy, cn = [], [], []
    for i in range(1, len(bins)):
        sel = idx == i
        if sel.sum() > 30:
            cx.append((bins[i-1] + bins[i]) / 2)
            cy.append(float(np.sqrt(np.mean(
                (res["pred"][sel] - res["core_c"][sel]) ** 2))))
            cn.append(int(sel.sum()))
    ax.plot(cx, cy, "-o", color=WARN, lw=1.8, ms=5)
    ax.axvline(ELEVATED_C, color=INK, ls=":", lw=1.2)
    ax.text(ELEVATED_C, ax.get_ylim()[1] * 0.95, " clinical threshold",
            fontsize=8, color=INK, va="top")
    ax.set_xlabel("true core temperature (°C)")
    ax.set_ylabel("RMSE in bin (°C)")
    ax.set_title("The error grows where it matters most", fontsize=11)
    ax.grid(alpha=0.15)

    # (d) risk-coverage
    ax = axes[1, 1]
    rc = risk_coverage(res["core_c"], res["pred"], res["hw90"])
    fr = [r["answered_fraction"] * 100 for r in rc]
    rm = [r["rmse"] for r in rc]
    ax.plot(fr, rm, "-", color=ACC, lw=2)
    ax.set_xlabel("percentage of samples the device answers on")
    ax.set_ylabel("RMSE on answered samples (°C)")
    ax.set_title("Refusing to answer buys accuracy", fontsize=11)
    ax.grid(alpha=0.15)
    ax.invert_xaxis()

    fig.suptitle("Ember: an honest core-temperature estimator", fontsize=13.5)
    fig.tight_layout()
    path = f"{prefix}_results.png"
    fig.savefig(path, dpi=150)
    print(f"\nwrote {path}")

    if res["sex"].notna().any() and res["sex"].nunique() == 2:
        fig2, ax = plt.subplots(figsize=(6.6, 4.4))
        order = sorted(res["sex"].dropna().unique())
        for i, g in enumerate(order):
            sub = res[res.sex == g]
            per = [basic_metrics(s["core_c"], s["pred"])["rmse"]
                   for _, s in sub.groupby("subject")]
            jit = np.random.default_rng(i).normal(0, 0.05, len(per))
            ax.scatter(np.full(len(per), i) + jit, per, s=48, alpha=0.75,
                       color=[ACC, WARN][i % 2], edgecolors="none")
            ax.hlines(np.median(per), i - 0.22, i + 0.22, color=INK, lw=2.2)
        ax.set_xticks(range(len(order))); ax.set_xticklabels(order)
        ax.set_ylabel("per-subject RMSE (°C)")
        ax.set_title("Accuracy by sex — one point per participant", fontsize=11)
        ax.grid(axis="y", alpha=0.15)
        fig2.tight_layout()
        fig2.savefig(f"{prefix}_by_sex.png", dpi=150)
        print(f"wrote {prefix}_by_sex.png")


# -------------------------------------------------------------------- main

def parse_hr_types(text):
    if text is None or str(text).strip().lower() == "all":
        return None
    return tuple(int(x) for x in str(text).split(",") if x.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="path to the PROSPIE .xlsx")
    ap.add_argument("--sheet", default="Data")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--no-personalise", action="store_true",
                    help="use a fixed CT0 of 37.1 for everyone")
    # 6 matches export_firmware_table.py, so the numbers reported here describe
    # the table the device and webapp actually use.
    ap.add_argument("--strata", type=int, default=6)
    # Default matches the default --hr-types (chest), so a plain run never
    # overwrites the all-sensor comparison (run that with --prefix ember_all).
    ap.add_argument("--prefix", default="ember_chest")
    ap.add_argument("--no-plot", action="store_true")
    ap.add_argument("--hr-types", default="2,3",
                    help="HR sensor types to use: 1 finger PPG, 2 Equivital chest, "
                         "3 Polar chest; 'all' keeps every type (default 2,3: chest only)")
    args = ap.parse_args()

    print("Ember evaluation")
    print("=" * 68)
    print("\nECTemp coefficient self-check:")
    if not self_check():
        sys.exit("coefficient check FAILED - do not trust anything below")
    print("  PASS\n")

    if args.synthetic:
        print("*** SYNTHETIC DATA. Every number below is a property of the")
        print("*** generator, not of human physiology. Use it to check the")
        print("*** pipeline runs, then download PROSPIE and run it again.\n")
        df = load_data.make_synthetic()
    elif args.data:
        try:
            sheet = int(args.sheet)
        except (TypeError, ValueError):
            sheet = args.sheet
        df = load_data.load_prospie(args.data, sheet=sheet,
                                    hr_types=parse_hr_types(args.hr_types))
    else:
        sys.exit("give --data <xlsx> or --synthetic")

    pred = predict_all(df, personalise_ct0=not args.no_personalise)
    res = loso(pred, n_strata=args.strata)
    summary = report(res, label="(synthetic)" if args.synthetic else "")

    if not args.no_plot:
        make_figures(res, prefix=args.prefix)

    res.to_csv(f"{args.prefix}_predictions.csv", index=False)
    with open(f"{args.prefix}_summary.json", "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"wrote {args.prefix}_predictions.csv and {args.prefix}_summary.json")


if __name__ == "__main__":
    main()
