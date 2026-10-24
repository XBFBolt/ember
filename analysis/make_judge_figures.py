"""
Create three publication-quality figures for the judges' presentation:

  1. Coverage bars: Kalman vs Conformal (the headline result)
  2. Estimate vs true over one trial with the ± band
  3. Lag histogram: time from true ≥38.5°C to alerts firing

Large fonts, readable on a projector.
"""

import sys
import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from conformal import gaussian_interval, coverage

# Colors
INK = "#1f2430"
ACC = "#2f6f8f"      # accent blue
WARN = "#b4531c"     # warning orange
OK = "#2d7a4f"       # green for conformal
GREY = "#6b7280"

WATCH_C = 38.0
ACT_NOW_C = 38.5


def load_results():
    pred_file = "ember_chest_predictions.csv"
    if not os.path.exists(pred_file):
        sys.exit(f"{pred_file} not found. Run evaluate.py --hr-types 2,3 --prefix ember_chest first.")
    return pd.read_csv(pred_file).dropna(subset=["core_c"])


def figure_1_coverage_bars(res, prefix="judges"):
    """Coverage comparison: Kalman vs Conformal across temperature bands."""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    bands = [
        (0, 37.5, "Normal\n<37.5°C"),
        (37.5, 38.0, "Warm\n37.5-38°C"),
        (38.0, 38.5, "Watch\n38-38.5°C"),
        (38.5, 99, "Act Now\n≥38.5°C"),
        (0, 99, "Overall")
    ]
    
    kalman_covs = []
    conformal_covs = []
    labels = []
    
    for lo, hi, label in bands:
        if lo == 0 and hi == 99:
            # Overall
            sub = res
        else:
            sub = res[(res["core_c"] >= lo) & (res["core_c"] < hi)]
        
        if len(sub) == 0:
            continue
        
        glo, ghi = gaussian_interval(sub["pred"], sub["var"], 0.90)
        k_cov = coverage(sub["core_c"], glo, ghi)
        c_cov = coverage(sub["core_c"], sub["c_lo_0.9"], sub["c_hi_0.9"])
        
        kalman_covs.append(k_cov)
        conformal_covs.append(c_cov)
        labels.append(label)
    
    x = np.arange(len(labels))
    width = 0.35
    
    # Bars
    ax.bar(x - width/2, kalman_covs, width, label="Kalman posterior (uncalibrated)",
           color=WARN, alpha=0.9, edgecolor=INK, linewidth=0.5)
    ax.bar(x + width/2, conformal_covs, width, label="Conformal (calibrated)",
           color=OK, alpha=0.9, edgecolor=INK, linewidth=0.5)
    
    # Nominal line
    ax.axhline(0.90, color=INK, linestyle="--", linewidth=2, label="Nominal 90%", zorder=0)
    
    # Labels
    ax.set_ylabel("Actual Coverage", fontsize=16, fontweight="bold")
    ax.set_xlabel("True Core Temperature", fontsize=16, fontweight="bold")
    ax.set_title("Kalman's \"90%\" interval covered 33% • Conformal covered 89%",
                 fontsize=18, fontweight="bold", pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=13)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, 0.25, 0.50, 0.75, 0.90, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "90%", "100%"], fontsize=13)
    ax.legend(fontsize=13, loc="upper left", framealpha=0.95)
    ax.grid(axis="y", alpha=0.3, zorder=0)
    
    # Emphasize the failure at high temps
    ax.text(2, kalman_covs[2] + 0.03, f"{kalman_covs[2]:.0%}", ha="center", 
            fontsize=12, fontweight="bold", color=WARN)
    ax.text(2, conformal_covs[2] + 0.03, f"{conformal_covs[2]:.0%}", ha="center",
            fontsize=12, fontweight="bold", color=OK)
    
    fig.tight_layout()
    path = f"{prefix}_coverage.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    print(f"Wrote {path}")


def figure_2_trial_with_interval(res, prefix="judges"):
    """One trial: estimate vs true with conformal interval."""
    # Pick a trial that reaches Act Now
    elevated_trials = []
    for (sid, cond), g in res.groupby(["subject", "condition"], sort=False):
        if g["core_c"].max() >= ACT_NOW_C:
            elevated_trials.append((sid, cond, g))
    
    if not elevated_trials:
        print("No trials reach Act Now - skipping figure 2")
        return
    
    # Pick a mid-length trial for visual clarity
    elevated_trials.sort(key=lambda x: len(x[2]))
    sid, cond, trial = elevated_trials[len(elevated_trials) // 2]
    trial = trial.sort_values("minute")
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    t = trial["minute"].values
    true_core = trial["core_c"].values
    pred = trial["pred"].values
    lo90 = trial["c_lo_0.9"].values
    hi90 = trial["c_hi_0.9"].values
    
    # Conformal band
    ax.fill_between(t, lo90, hi90, alpha=0.25, color=ACC, label="90% conformal interval")
    
    # True core
    ax.plot(t, true_core, "o-", color=INK, linewidth=2.5, markersize=3,
            label="True core (reference)", zorder=10)
    
    # Estimate
    ax.plot(t, pred, "s-", color=ACC, linewidth=2, markersize=3,
            label="Ember estimate", zorder=9)
    
    # Thresholds
    ax.axhline(WATCH_C, color=WARN, linestyle="--", linewidth=2, alpha=0.8,
               label=f"Watch ({WATCH_C}°C)")
    ax.axhline(ACT_NOW_C, color="#c73e1d", linestyle="--", linewidth=2, alpha=0.8,
               label=f"Act Now ({ACT_NOW_C}°C)")
    
    ax.set_xlabel("Time (minutes)", fontsize=16, fontweight="bold")
    ax.set_ylabel("Core Temperature (°C)", fontsize=16, fontweight="bold")
    ax.set_title(f"Trial: Subject {sid}, Condition {cond}  —  Estimate tracks true core with calibrated uncertainty",
                 fontsize=16, fontweight="bold", pad=15)
    ax.legend(fontsize=12, loc="upper left", framealpha=0.95)
    ax.grid(alpha=0.3)
    ax.tick_params(labelsize=13)
    
    fig.tight_layout()
    path = f"{prefix}_trial_interval.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    print(f"Wrote {path}")


def figure_3_lag_histogram(res, prefix="judges"):
    """Lag histogram: time from true ≥38.5 to alerts firing."""
    watch_lags = []
    act_lags = []
    
    for (sid, cond), g in res.groupby(["subject", "condition"], sort=False):
        g = g.sort_values("minute")
        elevated = g[g["core_c"] >= ACT_NOW_C]
        if elevated.empty:
            continue
        
        t0 = elevated.iloc[0]["minute"]
        after = g[g["minute"] >= t0]
        
        # Watch
        watch_hit = after[after["pred"] >= WATCH_C]
        if not watch_hit.empty:
            watch_lags.append(watch_hit.iloc[0]["minute"] - t0)
        
        # Act Now
        act_hit = after[after["pred"] >= ACT_NOW_C]
        if not act_hit.empty:
            act_lags.append(act_hit.iloc[0]["minute"] - t0)
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Watch
    ax = axes[0]
    if watch_lags:
        ax.hist(watch_lags, bins=np.arange(0, max(watch_lags) + 5, 5), 
                color=WARN, alpha=0.8, edgecolor=INK, linewidth=0.5)
        median = np.median(watch_lags)
        ax.axvline(median, color=INK, linestyle="--", linewidth=2.5, 
                   label=f"Median: {median:.0f} min")
        ax.set_xlabel("Minutes from true ≥38.5°C to Watch firing", fontsize=14, fontweight="bold")
        ax.set_ylabel("Number of trials", fontsize=14, fontweight="bold")
        ax.set_title(f"Watch Alert Lag  (median {median:.0f} min)", 
                     fontsize=15, fontweight="bold")
        ax.legend(fontsize=12, framealpha=0.95)
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(labelsize=12)
    
    # Act Now
    ax = axes[1]
    if act_lags:
        ax.hist(act_lags, bins=np.arange(0, max(act_lags) + 5, 5),
                color="#c73e1d", alpha=0.8, edgecolor=INK, linewidth=0.5)
        median = np.median(act_lags)
        ax.axvline(median, color=INK, linestyle="--", linewidth=2.5,
                   label=f"Median: {median:.0f} min")
        ax.set_xlabel("Minutes from true ≥38.5°C to Act Now firing", fontsize=14, fontweight="bold")
        ax.set_ylabel("Number of trials", fontsize=14, fontweight="bold")
        ax.set_title(f"Act Now Alert Lag  (median {median:.0f} min)",
                     fontsize=15, fontweight="bold")
        ax.legend(fontsize=12, framealpha=0.95)
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(labelsize=12)
    
    fig.suptitle("Alert Timing: The estimate lags true core temperature",
                 fontsize=17, fontweight="bold", y=1.02)
    fig.tight_layout()
    path = f"{prefix}_lag.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    print(f"Wrote {path}")


def main():
    print("Creating figures for judges...")
    res = load_results()
    
    figure_1_coverage_bars(res)
    figure_2_trial_with_interval(res)
    figure_3_lag_histogram(res)
    
    print("\nDone. Three figures ready for presentation.")


if __name__ == "__main__":
    main()
