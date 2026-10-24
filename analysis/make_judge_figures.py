"""
Create three figures for the judges' presentation:

  1. Coverage bars: Kalman vs Conformal (the headline result)
  2. Estimate vs true over one trial with the ± band
  3. Alert timing: where Watch and Act now stood when true core reached 38.5 °C

Large fonts, readable on a projector. Every number in a title or label is
computed from the data, never typed in.

Run (after evaluate.py --prefix ember_chest):
    python3 make_judge_figures.py

Writes judges_*.png here and to ../figures/.
"""

import sys
import os
import shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from conformal import gaussian_interval, coverage
from judges_results import alert_timing, WATCH_C, ACT_NOW_C

FIG_DIR = os.path.join(HERE, "..", "figures")

# Colors
INK = "#1f2430"
ACC = "#2f6f8f"      # accent blue
WARN = "#b4531c"     # warning orange
ACT = "#c73e1d"      # act-now red
OK = "#2d7a4f"       # green for conformal
GREY = "#6b7280"


def load_results():
    pred_file = os.path.join(HERE, "ember_chest_predictions.csv")
    if not os.path.exists(pred_file):
        sys.exit("ember_chest_predictions.csv not found. Run "
                 "evaluate.py --data <xlsx> --prefix ember_chest first.")
    return pd.read_csv(pred_file).dropna(subset=["core_c"])


def _save(fig, name):
    path = os.path.join(HERE, name)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    os.makedirs(FIG_DIR, exist_ok=True)
    shutil.copy(path, os.path.join(FIG_DIR, name))
    plt.close(fig)
    print(f"Wrote {name} (and figures/{name})")


def figure_1_coverage_bars(res, prefix="judges"):
    """Coverage comparison: Kalman vs Conformal across temperature bands."""
    fig, ax = plt.subplots(figsize=(11, 6.5))

    bands = [
        (0, 37.5, "Normal\n<37.5°C"),
        (37.5, 38.0, "Warm\n37.5–38°C"),
        (38.0, 38.5, "Watch\n38–38.5°C"),
        (38.5, 99, "Act now\n≥38.5°C"),
        (None, None, "Overall"),
    ]

    kalman_covs, conformal_covs, labels = [], [], []
    for lo, hi, label in bands:
        sub = res if lo is None else res[(res["core_c"] >= lo) & (res["core_c"] < hi)]
        if len(sub) == 0:
            continue
        glo, ghi = gaussian_interval(sub["pred"], sub["var"], 0.90)
        kalman_covs.append(coverage(sub["core_c"], glo, ghi))
        conformal_covs.append(coverage(sub["core_c"], sub["c_lo_0.9"], sub["c_hi_0.9"]))
        labels.append(f"{label}\nn={len(sub):,}")

    x = np.arange(len(labels))
    width = 0.36

    kb = ax.bar(x - width/2, kalman_covs, width, label="Kalman \"90%\" (uncalibrated)",
                color=WARN, alpha=0.9, edgecolor=INK, linewidth=0.5)
    cb = ax.bar(x + width/2, conformal_covs, width, label="Ember conformal 90% (calibrated)",
                color=OK, alpha=0.9, edgecolor=INK, linewidth=0.5)
    ax.axhline(0.90, color=INK, linestyle="--", linewidth=2, label="Promised 90%", zorder=0)

    # White box behind each label so the 90% line never runs through a number
    for bars, color in ((kb, WARN), (cb, OK)):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.015,
                    f"{b.get_height():.0%}", ha="center", va="bottom",
                    fontsize=13, fontweight="bold", color=color, zorder=5,
                    bbox=dict(facecolor="white", edgecolor="none", pad=1.5))

    ax.set_ylabel("How often the true value was inside", fontsize=15, fontweight="bold")
    ax.set_xlabel("True core temperature", fontsize=15, fontweight="bold")
    ax.set_title(f"Kalman's \"90%\" range covered {kalman_covs[-1]:.0%}  •  "
                 f"Ember's covered {conformal_covs[-1]:.0%}",
                 fontsize=18, fontweight="bold", pad=16)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=12)
    ax.set_ylim(0, 1.12)
    ax.set_yticks([0, 0.25, 0.50, 0.75, 0.90, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "90%", "100%"], fontsize=13)
    ax.legend(fontsize=12, loc="upper center", bbox_to_anchor=(0.5, -0.2),
              ncol=3, frameon=False)
    ax.grid(axis="y", alpha=0.3, zorder=0)

    fig.text(0.5, -0.1, "PROSPIE V3, 37 people, chest heart rate, leave-one-subject-out",
             ha="center", fontsize=11, color=GREY)
    fig.tight_layout()
    _save(fig, f"{prefix}_coverage.png")


def figure_2_trial_with_interval(res, prefix="judges"):
    """One trial: estimate vs true with conformal interval."""
    elevated_trials = []
    for (sid, cond), g in res.groupby(["subject", "condition"], sort=False):
        if g["core_c"].max() >= ACT_NOW_C:
            elevated_trials.append((sid, cond, g))

    if not elevated_trials:
        print("No trials reach Act now - skipping figure 2")
        return

    # Mid-length trial that reaches Act now (deterministic pick, not cherry-picked)
    elevated_trials.sort(key=lambda x: (len(x[2]), x[0], x[1]))
    sid, cond, trial = elevated_trials[len(elevated_trials) // 2]
    trial = trial.sort_values("minute")

    fig, ax = plt.subplots(figsize=(12, 6))

    t = trial["minute"].values
    true_core = trial["core_c"].values
    pred = trial["pred"].values
    lo90 = trial["c_lo_0.9"].values
    hi90 = trial["c_hi_0.9"].values
    inside = float(np.mean((true_core >= lo90) & (true_core <= hi90)))

    ax.fill_between(t, lo90, hi90, alpha=0.25, color=ACC, step="mid",
                    label="Ember ± (90% calibrated range)")
    ax.plot(t, true_core, "-", color=INK, linewidth=3,
            label="True core (rectal reference)", zorder=10)
    ax.plot(t, pred, "-", color=ACC, linewidth=2.5,
            label="Ember estimate", zorder=9)

    ax.axhline(WATCH_C, color=WARN, linestyle="--", linewidth=2, alpha=0.8,
               label=f"Watch ({WATCH_C}°C)")
    ax.axhline(ACT_NOW_C, color=ACT, linestyle="--", linewidth=2, alpha=0.8,
               label=f"Act now ({ACT_NOW_C}°C)")

    ax.set_xlabel("Time (minutes)", fontsize=16, fontweight="bold")
    ax.set_ylabel("Core temperature (°C)", fontsize=16, fontweight="bold")
    ax.set_title(f"One trial: the estimate lags; the ± held {inside:.0%} of the time",
                 fontsize=17, fontweight="bold", pad=15)
    ax.legend(fontsize=12, loc="upper left", framealpha=0.95)
    ax.grid(alpha=0.3)
    ax.tick_params(labelsize=13)
    fig.text(0.5, -0.02, f"PROSPIE participant {sid}, condition {cond}; "
             "subject held out of the calibration", ha="center", fontsize=11, color=GREY)

    fig.tight_layout()
    _save(fig, f"{prefix}_trial_interval.png")


def figure_3_alert_timing(res, prefix="judges"):
    """Where each alert stood when true core first reached 38.5 °C."""
    t = alert_timing(res)
    n = len(t)

    cats = ["Already on", "1–10 min\nlate", "11–30 min\nlate", "Over 30 min\nlate", "Never"]

    def bucket(lag):
        if np.isnan(lag):
            return 4
        if lag == 0:
            return 0
        if lag <= 10:
            return 1
        if lag <= 30:
            return 2
        return 3

    fig, axes = plt.subplots(1, 2, figsize=(15, 5.8), sharey=True)
    for ax, key, name, th, color in (
            (axes[0], "watch", "Watch", WATCH_C, WARN),
            (axes[1], "act", "Act now", ACT_NOW_C, ACT)):
        counts = np.bincount([bucket(v) for v in t[f"{key}_lag"]], minlength=len(cats))
        colors = [OK] + [color] * 3 + [GREY]
        bars = ax.bar(range(len(cats)), counts, color=colors, alpha=0.9,
                      edgecolor=INK, linewidth=0.5)
        for b, c in zip(bars, counts):
            ax.text(b.get_x() + b.get_width() / 2, c + 0.6, f"{c}",
                    ha="center", va="bottom", fontsize=15, fontweight="bold", color=INK)
        ax.set_xticks(range(len(cats)))
        ax.set_xticklabels(cats, fontsize=13)
        ax.set_title(f"{name} (estimate ≥ {th}°C): on in time {counts[0]}/{n}",
                     fontsize=16, fontweight="bold")
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(axis="y", labelsize=12)
    axes[0].set_ylabel("Number of trials", fontsize=14, fontweight="bold")
    axes[0].set_ylim(0, max(axes[0].get_ylim()[1], axes[1].get_ylim()[1]) * 1.12)

    fig.suptitle(f"When true core first reached {ACT_NOW_C}°C ({n} trials): "
                 "Watch carries the safety load",
                 fontsize=18, fontweight="bold", y=1.02)
    fig.tight_layout()
    _save(fig, f"{prefix}_lag.png")


def main():
    print("Creating figures for judges...")
    res = load_results()

    figure_1_coverage_bars(res)
    figure_2_trial_with_interval(res)
    figure_3_alert_timing(res)

    print("\nDone. Three figures ready for presentation.")


if __name__ == "__main__":
    main()
