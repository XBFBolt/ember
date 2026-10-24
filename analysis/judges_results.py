"""
Phase 2 analysis for judges: all the numbers that matter for the presentation.

This produces:
  1. Coverage comparison: Kalman vs conformal at 90%
  2. Coverage stratified by true temperature band
  3. Alert timing: where Watch and Act now stood when true core reached 38.5
  4. Sex bias with bootstrap confidence intervals
  5. Optional: coverage during rising vs steady phases
  6. Pulse sensors: the chest table applied to PROSPIE's finger-PPG trials

Input is the leave-one-subject-out output of evaluate.py (chest heart-rate
sensors, 6 conformal strata: the same calibration as conformal_table.h).

Run:
    python3 evaluate.py --data "Prospie dataset_open access V3.xlsx" --prefix ember_chest
    python3 evaluate.py --data "Prospie dataset_open access V3.xlsx" --hr-types all --prefix ember_all
    python3 judges_results.py | tee judges_results.txt
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
        sys.exit(f"{pred_file} not found. Run evaluate.py --data <xlsx> --prefix ember_chest first.")
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
    print(f"\n  Headline: Kalman's \"90%\" interval covered {kalman_cov:.1%} of true values.")
    print(f"            Conformal's 90% interval covered {conformal_cov:.1%}.")

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

        flag = "  <- under 85%" if c_cov < 0.85 else ""
        flag += "  <- under 50 samples" if n < 50 else ""
        print(f"  {label:>20s} {n:>6d} {k_cov:>8.3f} {c_cov:>10.3f}{flag}")
        rows.append({
            "band": label,
            "lo": lo,
            "hi": hi,
            "n": n,
            "kalman_coverage": k_cov,
            "conformal_coverage": c_cov
        })

    print("\n  The Kalman interval fails most where it matters most: at high core temps.")
    print("  Conformal is calibrated by PREDICTED temperature, so coverage conditional")
    print("  on TRUE temperature is not guaranteed; it drops at >=38.5 because the")
    print("  estimate lags and reads low when core is high.")
    return rows


def alert_timing(res):
    """
    One record per trial where true core reaches ACT_NOW_C.

    For each alert (Watch = estimate >= 38.0, Act now = estimate >= 38.5),
    measured at t_danger, the first minute true core is >= 38.5:
      on       - alert already on at t_danger
      lag      - minutes after t_danger until the alert is on
                 (0 if already on, NaN if it never came on)
      lead     - if on, how many minutes the current uninterrupted run of the
                 alert had been on before t_danger (0 = came on that minute)
      first    - first minute the alert was on anywhere in the trial, relative
                 to t_danger (negative = before). Secondary: an early crossing
                 that switched off again before t_danger counts here.
    """
    recs = []
    for (sid, cond), g in res.groupby(["subject", "condition"], sort=False):
        g = g.sort_values("minute")
        elevated = g[g["core_c"] >= ACT_NOW_C]
        if elevated.empty:
            continue
        t_danger = float(elevated["minute"].iloc[0])
        rec = {"subject": sid, "condition": cond, "t_danger": t_danger}
        for key, th in (("watch", WATCH_C), ("act", ACT_NOW_C)):
            on_rows = g[g["pred"] >= th]
            after = on_rows[on_rows["minute"] >= t_danger]
            lag = float(after["minute"].iloc[0] - t_danger) if len(after) else np.nan
            on = lag == 0
            lead = np.nan
            if on:
                before = g[g["minute"] <= t_danger].iloc[::-1]
                off = before[before["pred"] < th]
                start = (before["minute"].iloc[-1] if off.empty
                         else g[g["minute"] > off["minute"].iloc[0]]["minute"].iloc[0])
                lead = float(t_danger - start)
            first = float(on_rows["minute"].iloc[0] - t_danger) if len(on_rows) else np.nan
            rec.update({f"{key}_on": on, f"{key}_lag": lag,
                        f"{key}_lead": lead, f"{key}_first": first})
        recs.append(rec)
    return pd.DataFrame(recs)


def _describe(x):
    x = pd.Series(x).dropna()
    if x.empty:
        return None
    return {"n": int(len(x)), "median": float(x.median()),
            "q25": float(x.quantile(0.25)), "q75": float(x.quantile(0.75)),
            "max": float(x.max())}


def lag_analysis(res):
    """3. Alert timing at the limit: true core reaching 38.5 °C."""
    print("\n" + "=" * 68)
    print(f" 3. ALERT TIMING: when true core first reached {ACT_NOW_C}°C")
    print("=" * 68)

    t = alert_timing(res)
    n = len(t)
    print(f"\n  {n} trials where true core reached {ACT_NOW_C}°C")

    out = {"total_trials": n}
    for key, name, th in (("watch", "Watch", WATCH_C), ("act", "Act now", ACT_NOW_C)):
        on = int(t[f"{key}_on"].sum())
        before = int((t[f"{key}_lead"] > 0).sum())
        lag = t[f"{key}_lag"]
        late = lag[lag > 0]
        never = int(lag.isna().sum())
        lead = t[f"{key}_lead"].dropna()
        first = t[f"{key}_first"].dropna()

        print(f"\n  {name} (estimate >= {th}°C):")
        print(f"    already on at that minute:  {on} / {n} ({on/n:.0%})"
              f"   [on beforehand: {before}]")
        if on:
            print(f"      had been on for: median {lead.median():.0f} min "
                  f"(IQR {lead.quantile(.25):.0f}-{lead.quantile(.75):.0f})")
        if len(late):
            print(f"    came on later:              {len(late)} / {n}, "
                  f"median {late.median():.0f} min late, worst {late.max():.0f} min")
        else:
            print(f"    came on later:              0 / {n}")
        print(f"    never came on:              {never} / {n} ({never/n:.0%})")
        print(f"    lag (0 if already on):      median {lag.median():.0f} min, "
              f"worst {lag.max():.0f} min (among {lag.notna().sum()} that fired)")
        print(f"    [secondary] first on anywhere in trial: median {first.median():+.0f} min "
              f"relative to true {ACT_NOW_C}")

        out[key] = {
            "on_at_danger": on,
            "on_before_danger": before,
            "lead_when_on": _describe(lead),
            "late_count": int(len(late)),
            "late": _describe(late),
            "never": never,
            "lag": _describe(lag),
            "first_anywhere": _describe(first),
        }

    watch_only = int((t["watch_lag"].notna() & t["act_lag"].isna()).sum())
    neither = int(t["watch_lag"].isna().sum())
    print(f"\n  Watch came on but Act now never did: {watch_only} / {n} ({watch_only/n:.0%})")
    print(f"  Neither alert ever came on:          {neither} / {n} ({neither/n:.0%})")
    print("\n  Watch carries the safety load: it is already on in most trials when")
    print("  true core reaches 38.5, while Act now is usually late or never fires.")

    out["watch_only"] = watch_only
    out["neither"] = neither
    return out


def sex_bias_analysis(res):
    """4. Men vs women: bias difference with bootstrap CI."""
    print("\n" + "=" * 68)
    print(" 4. SEX BIAS ANALYSIS")
    print("=" * 68)

    if not res["sex"].notna().any() or res["sex"].nunique() < 2:
        print("  No usable sex column - skipped.")
        return None

    per_sex = {}
    for g in sorted(res["sex"].dropna().unique()):
        sub = res[res.sex == g]
        n_subj = sub.subject.nunique()
        n_samp = len(sub)

        err = sub["pred"] - sub["core_c"]
        bias = float(np.mean(err))
        rmse = float(np.sqrt(np.mean(err ** 2)))
        c_cov = coverage(sub["core_c"], sub["c_lo_0.9"], sub["c_hi_0.9"])

        print(f"\n  {g}:  n_subjects={n_subj},  n_samples={n_samp}")
        print(f"    bias: {bias:+.3f} °C")
        print(f"    RMSE: {rmse:.3f} °C")
        print(f"    90% conformal coverage: {c_cov:.1%}")
        per_sex[g] = {"n_subjects": int(n_subj), "n_samples": int(n_samp),
                      "bias": bias, "rmse": rmse, "coverage_90": c_cov}

    # Bootstrap difference (bias is primary metric per evaluate.py)
    print("\n  Bootstrap analysis of BIAS difference (5000 resamples of subjects):")
    bd_bias = bootstrap_group_diff(res, key="bias", by="sex", n_boot=5000, seed=42)

    if bd_bias:
        a, b = bd_bias["groups"]
        excl = bd_bias["ci"][0] > 0 or bd_bias["ci"][1] < 0
        tag = "EXCLUDES ZERO — statistically significant" if excl else "includes zero"

        print(f"    {b} minus {a}: {bd_bias['point']:+.3f} °C")
        print(f"    95% CI: [{bd_bias['ci'][0]:+.3f}, {bd_bias['ci'][1]:+.3f}]  ({tag})")
        print(f"    P(difference > 0): {bd_bias['p_exceeds_zero']:.3f}")

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
        "per_sex": per_sex,
        "bias": bd_bias,
        "rmse": bd_rmse
    }


def rising_vs_steady_coverage(res):
    """5. Optional: coverage during rising vs steady phases."""
    print("\n" + "=" * 68)
    print(" 5. COVERAGE: Rising vs Steady (OPTIONAL)")
    print("=" * 68)

    # "Rising": true core up >= 0.2 °C versus 5 minutes earlier.
    # "Steady": change under 0.1 °C either way. Everything else is left out.
    res = res.copy()
    res["phase"] = "unknown"

    for (sid, cond), g in res.groupby(["subject", "condition"], sort=False):
        g = g.sort_values("minute").copy()

        for i in range(len(g)):
            idx = g.index[i]
            t = g.loc[idx, "minute"]

            past = g[(g["minute"] >= t - 5) & (g["minute"] < t)]
            if past.empty:
                continue

            delta = g.loc[idx, "core_c"] - past["core_c"].iloc[0]

            if delta >= 0.2:
                res.loc[idx, "phase"] = "rising"
            elif abs(delta) < 0.1:
                res.loc[idx, "phase"] = "steady"

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

    if results["rising"]["conformal_coverage"] < 0.85:
        print("\n  Rising coverage is under 85%: consider stratifying the calibration")
        print("  by rising/steady as well as by predicted temperature.")

    return results


def pulse_sensor_check(n_strata=6, level=0.90):
    """
    6. Ember v2 measures heart rate with optical pulse sensors (PPG); the
    shipped table is calibrated on chest ECG/strap heart rate. The filter only
    sees heart rate, so the question is whether sensor type changes the error.
    PROSPIE's finger-PPG trials are compared with chest trials from the same
    conditions, all leave-one-subject-out.
    """
    from conformal import StratifiedConformal

    print("\n" + "=" * 68)
    print(" 6. PULSE SENSORS: does the chest calibration hold for optical HR?")
    print("=" * 68)

    path = "ember_all_predictions.csv"
    if not os.path.exists(path):
        print(f"  {path} not found. Run evaluate.py --hr-types all --prefix ember_all.")
        return None
    a = pd.read_csv(path).dropna(subset=["core_c"])
    chest = a[a["trial_hr_type"].isin([2, 3])]
    ppg = a[a["trial_hr_type"] == 1]
    if ppg.empty:
        print("  No finger-PPG trials - skipped.")
        return None

    def loso_on(test, train_pool):
        inside, half = [], []
        for s in test["subject"].unique():
            tr = train_pool[train_pool["subject"] != s]
            sc = StratifiedConformal(n_strata=n_strata, levels=(level,)).fit(
                tr["pred"].to_numpy(), tr["core_c"].to_numpy())
            te = test[test["subject"] == s]
            lo, hi = sc.interval(te["pred"].to_numpy(), level)
            inside.append(((te["core_c"] >= lo) & (te["core_c"] <= hi)).to_numpy())
            half.append((hi - lo) / 2)
        return float(np.concatenate(inside).mean()), float(np.concatenate(half).mean())

    def row(label, g, cov):
        e = g["pred"] - g["core_c"]
        print(f"  {label:34s} {g.groupby(['subject', 'condition']).ngroups:>3d} trials  "
              f"bias {e.mean():+.2f}  coverage {cov:.1%}  HR missing {g['hr'].isna().mean():.0%}")
        return {"trials": int(g.groupby(["subject", "condition"]).ngroups),
                "minutes": int(len(g)), "bias": float(e.mean()), "coverage": cov,
                "hr_missing": float(g["hr"].isna().mean())}

    # Finger PPG only appears in some conditions. Compare it with chest trials
    # from the SAME conditions, or the sensor gets blamed for the protocol.
    ppg_conds = sorted(int(c) for c in ppg["condition"].unique())
    chest_same = chest[chest["condition"].isin(ppg_conds)]

    ppg_cov, ppg_half = loso_on(ppg, chest)
    same_cov, _ = loso_on(chest_same, chest)
    ppg_own_cov, ppg_own_half = loso_on(ppg, ppg)

    print(f"\n  Finger PPG appears only in conditions {ppg_conds}. "
          f"Chest table, leave-one-subject-out:")
    out = {"conditions": [int(c) for c in ppg_conds]}
    out["ppg"] = row("finger pulse trials", ppg, ppg_cov)
    out["chest_same_conditions"] = row("chest trials, same conditions", chest_same, same_cov)
    out["ppg"]["mean_half"] = ppg_half
    out["ppg_own_table"] = {"coverage": ppg_own_cov, "mean_half": ppg_own_half}

    print("\n  Most of the gap is the conditions (heart rate missing in most")
    print("  minutes in both groups), not the sensor. Same conditions, pulse vs")
    print(f"  chest differ by {out['ppg']['bias'] - out['chest_same_conditions']['bias']:+.2f} °C "
          f"bias and {100 * (out['ppg']['coverage'] - out['chest_same_conditions']['coverage']):+.1f} "
          "points of coverage.")
    print("  The filter only sees heart rate: if Ember's pulse sensors report the")
    print("  same heart rate as a chest strap, the chest calibration applies.")
    return out


def main():
    print("=" * 68)
    print(" EMBER PHASE 2: RESULTS FOR JUDGES")
    print("=" * 68)
    print("\n All analyses use leave-one-subject-out cross-validation on")
    print(" PROSPIE V3 (chest heart-rate sensors only, 6 conformal strata,")
    print(" the same calibration as firmware/conformal_table.h).")

    res = load_results()
    print(f"\n {res.subject.nunique()} subjects, {len(res)} scored minutes, "
          f"{res.groupby(['subject', 'condition']).ngroups} trials")

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

    summary["pulse_sensor_check"] = pulse_sensor_check()

    out_file = "judges_results.json"
    with open(out_file, "w") as fh:
        json.dump(summary, fh, indent=2)
    print(f"\n\nWrote {out_file}")

    print("\n" + "=" * 68)
    print(" DONE")
    print("=" * 68)


if __name__ == "__main__":
    main()
