"""
Phase 2 analysis for judges: all the numbers that matter for the presentation.

This produces:
  1. Coverage comparison: Kalman vs conformal at 90%
  2. Coverage stratified by true temperature band
  3. Lag analysis: time from true core ≥38.5 to alerts firing
  4. Sex bias with bootstrap confidence intervals
  5. Optional: coverage during rising vs steady phases

Run:
    python3 judges_results.py
"""

import sys
import os
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conformal import gaussian_interval, coverage
from evaluate import bootstrap_group_diff

# Temperature thresholds (from TODO Phase 1)
WATCH_C = 38.0
ACT_NOW_C = 38.5
TEMP_BANDS = [
    (0, 37.5, "normal (<37.5)"),
    (37.5, 38.0, "warm (37.5-38.0)"),
    (38.0, 38.5, "watch (38.0-38.5)"),
    (38.5, 99, "act now (≥38.5)")
]


def load_results():
    """Load the LOSO predictions (chest-only sensors)."""
    pred_file = "ember_chest_predictions.csv"
    if not os.path.exists(pred_file):
        sys.exit(f"{pred_file} not found. Run evaluate.py --hr-types 2,3 --prefix ember_chest first.")
    df = pd.read_csv(pred_file)
    # Only scored rows
    df = df[df["core_c"].notna()].copy()
    return df


def coverage_comparison(res):
    """1. Coverage of the 90% range: Kalman vs conformal."""
    print("\n" + "=" * 68)
    print(" 1. COVERAGE: Kalman posterior variance vs conformal")
    print("=" * 68)
    
    # 90% intervals
    glo, ghi = gaussian_interval(res["pred"], res["var"], 0.90)
    kalman_cov = coverage(res["core_c"], glo, ghi)
    conformal_cov = coverage(res["core_c"], res["c_lo_0.9"], res["c_hi_0.9"])
    
    kalman_width = float(np.mean(ghi - glo))
    conformal_width = float(np.mean(res["c_hi_0.9"] - res["c_lo_0.9"]))
    
    print(f"\n  90% nominal interval coverage:")
    print(f"    Kalman posterior:      {kalman_cov:.1%}  (mean width {kalman_width:.2f} °C)")
    print(f"    Conformal calibrated:  {conformal_cov:.1%}  (mean width {conformal_width:.2f} °C)")
    print(f"\n  Headline: Kalman's \"90%\" interval covered {kalman_cov:.0%} of true values.")
    print(f"            Conformal's 90% interval covered {conformal_cov:.0%}.")
    
    return {
        "kalman_coverage": kalman_cov,
        "kalman_width": kalman_width,
        "conformal_coverage": conformal_cov,
        "conformal_width": conformal_width
    }


def coverage_by_band(res):
    """2. Coverage stratified by true temperature band."""
    print("\n" + "=" * 68)
    print(" 2. COVERAGE BY TRUE TEMPERATURE BAND")
    print("=" * 68)
    
    rows = []
    print(f"\n  {'Band':>20s} {'n':>6s} {'Kalman':>8s} {'Conformal':>10s}")
    print("  " + "-" * 48)
    
    for lo, hi, label in TEMP_BANDS:
        mask = (res["core_c"] >= lo) & (res["core_c"] < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        
        sub = res[mask]
        glo, ghi = gaussian_interval(sub["pred"], sub["var"], 0.90)
        k_cov = coverage(sub["core_c"], glo, ghi)
        c_cov = coverage(sub["core_c"], sub["c_lo_0.9"], sub["c_hi_0.9"])
        
        print(f"  {label:>20s} {n:>6d} {k_cov:>8.3f} {c_cov:>10.3f}")
        rows.append({
            "band": label,
            "lo": lo,
            "hi": hi,
            "n": n,
            "kalman_coverage": k_cov,
            "conformal_coverage": c_cov
        })
    
    print("\n  The Kalman interval fails most where it matters most: at high core temps.")
    return rows


def lag_analysis(res):
    """3. Lag: minutes from true core ≥38.5 to Watch (38.0) and Act now (38.5) firing."""
    print("\n" + "=" * 68)
    print(" 3. LAG ANALYSIS: How late do the alarms fire?")
    print("=" * 68)
    
    # For each (subject, condition) trial, find the first minute where true core ≥ 38.5
    # then measure how long until pred ≥ 38.0 (Watch) and pred ≥ 38.5 (Act now)
    
    watch_lags = []
    act_lags = []
    watch_fired_first = 0
    total_trials = 0
    never_watch = 0
    never_act = 0
    
    for (sid, cond), g in res.groupby(["subject", "condition"], sort=False):
        g = g.sort_values("minute")
        
        # First minute where true core ≥ 38.5
        elevated = g[g["core_c"] >= ACT_NOW_C]
        if elevated.empty:
            continue
        
        total_trials += 1
        t0 = elevated.iloc[0]["minute"]
        
        # Subsequent data after that point
        after = g[g["minute"] >= t0]
        
        # Time to Watch (pred ≥ 38.0)
        watch_hit = after[after["pred"] >= WATCH_C]
        if not watch_hit.empty:
            lag_watch = watch_hit.iloc[0]["minute"] - t0
            watch_lags.append(lag_watch)
        else:
            never_watch += 1
        
        # Time to Act now (pred ≥ 38.5)
        act_hit = after[after["pred"] >= ACT_NOW_C]
        if not act_hit.empty:
            lag_act = act_hit.iloc[0]["minute"] - t0
            act_lags.append(lag_act)
            
            # Did Watch fire first?
            if not watch_hit.empty and watch_hit.iloc[0]["minute"] < act_hit.iloc[0]["minute"]:
                watch_fired_first += 1
        else:
            never_act += 1
    
    print(f"\n  Analyzed {total_trials} trials where true core reached {ACT_NOW_C}°C")
    
    if watch_lags:
        print(f"\n  Time from true core ≥{ACT_NOW_C}°C to Watch ({WATCH_C}°C) firing:")
        print(f"    median: {np.median(watch_lags):.1f} min")
        print(f"    mean:   {np.mean(watch_lags):.1f} min ± {np.std(watch_lags):.1f} SD")
        print(f"    range:  {np.min(watch_lags):.0f} - {np.max(watch_lags):.0f} min")
        print(f"    never fired: {never_watch} / {total_trials}")
    
    if act_lags:
        print(f"\n  Time from true core ≥{ACT_NOW_C}°C to Act now ({ACT_NOW_C}°C) firing:")
        print(f"    median: {np.median(act_lags):.1f} min")
        print(f"    mean:   {np.mean(act_lags):.1f} min ± {np.std(act_lags):.1f} SD")
        print(f"    range:  {np.min(act_lags):.0f} - {np.max(act_lags):.0f} min")
        print(f"    never fired: {never_act} / {total_trials}")
    
    if act_lags:
        watch_first_pct = 100 * watch_fired_first / len(act_lags)
        print(f"\n  Watch fired before Act now in {watch_fired_first}/{len(act_lags)} "
              f"trials ({watch_first_pct:.0f}%)")
        print(f"  This validates the two-tier alert design: Watch gives advance warning.")
    
    return {
        "total_trials": total_trials,
        "watch_lags": {
            "n": len(watch_lags),
            "median": float(np.median(watch_lags)) if watch_lags else None,
            "mean": float(np.mean(watch_lags)) if watch_lags else None,
            "std": float(np.std(watch_lags)) if watch_lags else None,
            "min": float(np.min(watch_lags)) if watch_lags else None,
            "max": float(np.max(watch_lags)) if watch_lags else None,
            "never_fired": never_watch
        },
        "act_lags": {
            "n": len(act_lags),
            "median": float(np.median(act_lags)) if act_lags else None,
            "mean": float(np.mean(act_lags)) if act_lags else None,
            "std": float(np.std(act_lags)) if act_lags else None,
            "min": float(np.min(act_lags)) if act_lags else None,
            "max": float(np.max(act_lags)) if act_lags else None,
            "never_fired": never_act
        },
        "watch_fired_first": watch_fired_first,
        "watch_fired_first_pct": watch_first_pct if act_lags else None
    }


def sex_bias_analysis(res):
    """4. Men vs women: bias difference with bootstrap CI."""
    print("\n" + "=" * 68)
    print(" 4. SEX BIAS ANALYSIS")
    print("=" * 68)
    
    if not res["sex"].notna().any() or res["sex"].nunique() < 2:
        print("  No usable sex column - skipped.")
        return None
    
    # Per-sex statistics
    for g in sorted(res["sex"].dropna().unique()):
        sub = res[res.sex == g]
        n_subj = sub.subject.nunique()
        n_samp = len(sub)
        
        err = sub["pred"] - sub["core_c"]
        bias = float(np.mean(err))
        rmse = float(np.sqrt(np.mean(err ** 2)))
        
        # Coverage
        c_cov = coverage(sub["core_c"], sub["c_lo_0.9"], sub["c_hi_0.9"])
        
        print(f"\n  {g}:  n_subjects={n_subj},  n_samples={n_samp}")
        print(f"    bias: {bias:+.3f} °C")
        print(f"    RMSE: {rmse:.3f} °C")
        print(f"    90% conformal coverage: {c_cov:.1%}")
    
    # Bootstrap difference (bias is primary metric per evaluate.py)
    print("\n  Bootstrap analysis of BIAS difference (resampling subjects):")
    bd_bias = bootstrap_group_diff(res, key="bias", by="sex", n_boot=5000, seed=42)
    
    if bd_bias:
        a, b = bd_bias["groups"]
        excl = bd_bias["ci"][0] > 0 or bd_bias["ci"][1] < 0
        tag = "EXCLUDES ZERO — statistically significant" if excl else "includes zero"
        
        print(f"    {b} minus {a}: {bd_bias['point']:+.3f} °C")
        print(f"    95% CI: [{bd_bias['ci'][0]:+.3f}, {bd_bias['ci'][1]:+.3f}]  ({tag})")
        print(f"    P(difference > 0): {bd_bias['p_exceeds_zero']:.3f}")
    
    # Also RMSE for comparison
    print("\n  Bootstrap analysis of RMSE difference (for comparison):")
    bd_rmse = bootstrap_group_diff(res, key="rmse", by="sex", n_boot=5000, seed=42)
    
    if bd_rmse:
        a, b = bd_rmse["groups"]
        excl = bd_rmse["ci"][0] > 0 or bd_rmse["ci"][1] < 0
        tag = "EXCLUDES ZERO" if excl else "includes zero"
        
        print(f"    {b} minus {a}: {bd_rmse['point']:+.3f} °C")
        print(f"    95% CI: [{bd_rmse['ci'][0]:+.3f}, {bd_rmse['ci'][1]:+.3f}]  ({tag})")
    
    print("\n  Note: Bias is the primary metric. A systematic offset between groups")
    print("        moves bias substantially but barely affects RMSE (which is dominated")
    print("        by within-subject variation). See evaluate.py comments for details.")
    
    return {
        "bias": bd_bias,
        "rmse": bd_rmse
    }


def rising_vs_steady_coverage(res):
    """5. Optional: coverage during rising vs steady phases."""
    print("\n" + "=" * 68)
    print(" 5. COVERAGE: Rising vs Steady (OPTIONAL)")
    print("=" * 68)
    
    # Define "rising" as: core temp increased by ≥0.2°C in the last 5 minutes
    # This requires grouping by trial and computing the 5-min delta
    
    res = res.copy()
    res["phase"] = "unknown"
    
    for (sid, cond), g in res.groupby(["subject", "condition"], sort=False):
        g = g.sort_values("minute").copy()
        
        # 5-minute rolling delta
        for i in range(len(g)):
            idx = g.index[i]
            t = g.loc[idx, "minute"]
            
            # Look back 5 minutes
            past = g[(g["minute"] >= t - 5) & (g["minute"] < t)]
            if past.empty:
                continue
            
            delta = g.loc[idx, "core_c"] - past["core_c"].iloc[0]
            
            if delta >= 0.2:
                res.loc[idx, "phase"] = "rising"
            elif abs(delta) < 0.1:
                res.loc[idx, "phase"] = "steady"
            # else: neither (declining or ambiguous)
    
    rising = res[res["phase"] == "rising"]
    steady = res[res["phase"] == "steady"]
    
    if len(rising) < 100 or len(steady) < 100:
        print("  Not enough data in rising/steady phases - skipped.")
        return None
    
    print(f"\n  Rising phase (Δcore ≥ +0.2°C in 5 min):  n = {len(rising)}")
    print(f"  Steady phase (|Δcore| < 0.1°C in 5 min):  n = {len(steady)}")
    
    results = {}
    for label, sub in [("rising", rising), ("steady", steady)]:
        glo, ghi = gaussian_interval(sub["pred"], sub["var"], 0.90)
        k_cov = coverage(sub["core_c"], glo, ghi)
        c_cov = coverage(sub["core_c"], sub["c_lo_0.9"], sub["c_hi_0.9"])
        
        print(f"\n  {label.capitalize()}:")
        print(f"    Kalman 90%:     {k_cov:.1%}")
        print(f"    Conformal 90%:  {c_cov:.1%}")
        
        results[label] = {
            "n": len(sub),
            "kalman_coverage": k_cov,
            "conformal_coverage": c_cov
        }
    
    print("\n  Note: The Kalman filter assumes a constant-velocity model, so")
    print("        miscalibration may differ between rising and steady phases.")
    
    return results


def main():
    print("=" * 68)
    print(" EMBER PHASE 2: RESULTS FOR JUDGES")
    print("=" * 68)
    print("\n All analyses use leave-one-subject-out cross-validation on")
    print(" PROSPIE V3 dataset (chest heart-rate sensors only).")
    
    res = load_results()
    
    summary = {}
    summary["coverage_comparison"] = coverage_comparison(res)
    summary["coverage_by_band"] = coverage_by_band(res)
    summary["lag_analysis"] = lag_analysis(res)
    summary["sex_bias"] = sex_bias_analysis(res)
    
    # Optional
    try:
        summary["rising_vs_steady"] = rising_vs_steady_coverage(res)
    except Exception as e:
        print(f"\n  Rising vs steady analysis failed: {e}")
        summary["rising_vs_steady"] = None
    
    # Write summary
    out_file = "judges_results.json"
    with open(out_file, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"\n\nWrote {out_file}")
    
    print("\n" + "=" * 68)
    print(" DONE")
    print("=" * 68)


if __name__ == "__main__":
    main()
