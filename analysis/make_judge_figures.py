"""
Create six figures for the judges' presentation:

  1. Coverage bars: Kalman vs Conformal (the headline result)
  2. Estimate vs true over one trial with the ± band
  3. Alert timing: where Watch and Act now stood when true core reached 38.5 °C
  4. Error (RMSE): filter alone vs Ember 2.3, on PROSPIE and the HTT external test,
     and per person
  5. The 90 % range: promised vs delivered at every level, and how wide it is
  6. Early warning: the estimate around the minute true core reached 38.5 °C,
     and how many minutes ahead Watch and Act now were on

Large fonts, readable on a projector. Every number in a title or label is
computed from the data, never typed in.

Run (after evaluate.py --prefix ember_chest; external_test.py is optional
and adds the HTT bars to figure 4 and the HTT point to figure 5):
    python3 make_judge_figures.py

Writes judges_*.png here and to ../figures/.
"""

import sys
import os
import json
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


def load_external():
    """HTT external test summary (external_test.py), or None if it wasn't run."""
    path = os.path.join(HERE, "external_htt_results.json")
    if not os.path.exists(path):
        print("external_htt_results.json not found: figures 4 and 5 show PROSPIE only")
        return None
    with open(path) as fh:
        return json.load(fh)


def _rmse(err):
    return float(np.sqrt(np.mean(np.square(err))))


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
        glo, ghi = gaussian_interval(sub["kalman_pred"], sub["var"], 0.90)
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

    fig.text(0.5, -0.1, "PROSPIE V3, 37 people, chest heart rate, leave-one-subject-out. "
             "Ember = filter + learned correction (firmware 2.3)",
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
    if "kalman_pred" in trial and not np.allclose(trial["kalman_pred"], pred):
        ax.plot(t, trial["kalman_pred"].values, "--", color=GREY, linewidth=2,
                label="Filter alone (before the learned correction)", zorder=8)
    ax.plot(t, pred, "-", color=ACC, linewidth=2.5,
            label="Ember estimate", zorder=9)

    ax.axhline(WATCH_C, color=WARN, linestyle="--", linewidth=2, alpha=0.8,
               label=f"Watch ({WATCH_C}°C)")
    ax.axhline(ACT_NOW_C, color=ACT, linestyle="--", linewidth=2, alpha=0.8,
               label=f"Act now ({ACT_NOW_C}°C)")

    ax.set_xlabel("Time (minutes)", fontsize=16, fontweight="bold")
    ax.set_ylabel("Core temperature (°C)", fontsize=16, fontweight="bold")
    ax.set_title(f"One trial: the ± held {inside:.0%} of the time",
                 fontsize=17, fontweight="bold", pad=15)
    ax.legend(fontsize=12, loc="upper left", framealpha=0.95)
    ax.grid(alpha=0.3)
    ax.tick_params(labelsize=13)
    fig.text(0.5, -0.02, f"PROSPIE participant {sid}, condition {cond}; "
             "subject held out of the calibration", ha="center", fontsize=11, color=GREY)

    fig.tight_layout()
    _save(fig, f"{prefix}_trial_interval.png")


def figure_3_alert_timing(res, prefix="judges"):
    """Where each alert stood when true core first reached 38.5 °C.
    Grey bars: the filter alone (firmware 2.2), for comparison."""
    t = alert_timing(res)
    n = len(t)
    have_before = "kalman_pred" in res and not np.allclose(res["kalman_pred"], res["pred"])
    tb = alert_timing(res.assign(pred=res["kalman_pred"])) if have_before else None

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
        x = np.arange(len(cats))
        w = 0.4 if have_before else 0.8
        if have_before:
            before = np.bincount([bucket(v) for v in tb[f"{key}_lag"]], minlength=len(cats))
            bb = ax.bar(x - w / 2, before, w, color="white", edgecolor=GREY, linewidth=1.5,
                        hatch="//", label="Filter alone (2.2)")
            for b, c in zip(bb, before):
                ax.text(b.get_x() + b.get_width() / 2, c + 0.6, f"{c}",
                        ha="center", va="bottom", fontsize=12, color=GREY)
        bars = ax.bar(x + (w / 2 if have_before else 0), counts, w, color=colors, alpha=0.9,
                      edgecolor=INK, linewidth=0.5, label="Ember 2.3" if have_before else None)
        for b, c in zip(bars, counts):
            ax.text(b.get_x() + b.get_width() / 2, c + 0.6, f"{c}",
                    ha="center", va="bottom", fontsize=15, fontweight="bold", color=INK)
        ax.set_xticks(x)
        ax.set_xticklabels(cats, fontsize=13)
        was = f" (was {before[0]})" if have_before else ""
        ax.set_title(f"{name} (estimate ≥ {th}°C): on in time {counts[0]}/{n}{was}",
                     fontsize=16, fontweight="bold")
        if have_before:
            ax.legend(fontsize=11, loc="upper center", frameon=False)
        ax.grid(axis="y", alpha=0.3)
        ax.tick_params(axis="y", labelsize=12)
    axes[0].set_ylabel("Number of trials", fontsize=14, fontweight="bold")
    axes[0].set_ylim(0, max(axes[0].get_ylim()[1], axes[1].get_ylim()[1]) * 1.12)

    fig.suptitle(f"When true core first reached {ACT_NOW_C}°C ({n} trials): "
                 "Watch carries the safety load",
                 fontsize=18, fontweight="bold", y=1.02)
    fig.tight_layout()
    _save(fig, f"{prefix}_lag.png")


def figure_4_error(res, ext, prefix="judges"):
    """Error (RMSE): filter alone vs Ember 2.3, overall and for each person."""
    err_b = res["kalman_pred"] - res["core_c"]
    err_a = res["pred"] - res["core_c"]
    rmse_b, rmse_a = _rmse(err_b), _rmse(err_a)
    n_people = res["subject"].nunique()

    groups = [(f"PROSPIE\n{n_people} people, each held out", rmse_b, rmse_a)]
    if ext:
        groups.append((f"HTT (external test)\n{ext['ember']['n_subjects']} new people, "
                       "never trained on",
                       ext["filter_alone"]["rmse"], ext["ember"]["rmse"]))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6.4),
                                   gridspec_kw={"width_ratios": [1, 1.5]})

    # Left: overall RMSE per dataset
    x = np.arange(len(groups))
    w = 0.36
    bb = ax1.bar(x - w / 2, [g[1] for g in groups], w, color="white", edgecolor=GREY,
                 linewidth=1.5, hatch="//", label="Filter alone (2.2)")
    ab = ax1.bar(x + w / 2, [g[2] for g in groups], w, color=ACC, alpha=0.9,
                 edgecolor=INK, linewidth=0.5, label="Ember 2.3 (learned correction)")
    for bars, color, weight, size in ((bb, GREY, "normal", 13), (ab, INK, "bold", 15)):
        for b in bars:
            ax1.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.008,
                     f"{b.get_height():.3f}", ha="center", va="bottom",
                     fontsize=size, fontweight=weight, color=color)
    ax1.set_xticks(x)
    ax1.set_xticklabels([g[0] for g in groups], fontsize=12)
    ax1.set_ylabel("Error (RMSE, °C)", fontsize=15, fontweight="bold")
    ax1.set_ylim(0, max(g[1] for g in groups) * 1.3)
    ax1.set_title("Typical size of a miss", fontsize=16, fontweight="bold")
    ax1.legend(fontsize=11, loc="upper left", frameon=False)
    ax1.grid(axis="y", alpha=0.3)
    ax1.tick_params(axis="y", labelsize=12)

    # Right: one pair of dots per PROSPIE person, sorted by the filter's error
    per_b = (err_b ** 2).groupby(res["subject"]).mean() ** 0.5
    per_a = (err_a ** 2).groupby(res["subject"]).mean() ** 0.5
    order = per_b.sort_values(ascending=False).index
    pb, pa = per_b[order].to_numpy(), per_a[order].to_numpy()
    better = pa < pb
    xi = np.arange(len(order))
    ax2.vlines(xi, np.minimum(pa, pb), np.maximum(pa, pb), color=GREY, linewidth=1.5, alpha=0.6)
    ax2.scatter(xi, pb, s=55, facecolors="white", edgecolors=GREY, linewidths=1.5,
                zorder=3, label="Filter alone (2.2)")
    ax2.scatter(xi[better], pa[better], s=65, color=ACC, zorder=4,
                label="Ember 2.3: better")
    ax2.scatter(xi[~better], pa[~better], s=65, color=WARN, marker="D", zorder=4,
                label="Ember 2.3: worse")
    ax2.set_xticks([])
    ax2.set_xlabel("PROSPIE participants, sorted by the filter's error",
                   fontsize=14, fontweight="bold")
    ax2.set_ylabel("Error for that person (RMSE, °C)", fontsize=15, fontweight="bold")
    ax2.set_ylim(0, max(pb.max(), pa.max()) * 1.12)
    ax2.set_title(f"Better for {int(better.sum())} of {len(order)} people",
                  fontsize=16, fontweight="bold")
    ax2.legend(fontsize=11, loc="upper right", frameon=False)
    ax2.grid(axis="y", alpha=0.3)
    ax2.tick_params(axis="y", labelsize=12)

    fig.suptitle(f"Error (RMSE): {rmse_b:.3f} → {rmse_a:.3f} °C with the learned correction  •  "
                 f"bias {err_b.mean():+.3f} → {err_a.mean():+.3f} °C",
                 fontsize=18, fontweight="bold", y=1.02)
    fig.text(0.5, -0.04, "Reference core: rectal (PROSPIE), ingestible pill (HTT). "
             "PROSPIE is leave-one-subject-out; the correction was chosen among seven "
             "variants on it, so that gain is slightly optimistic.\nHTT applies the "
             "shipped firmware tables unchanged.", ha="center", fontsize=11, color=GREY)
    fig.tight_layout()
    _save(fig, f"{prefix}_rmse.png")


def figure_5_range(res, ext, prefix="judges"):
    """The 90 % range: promised vs delivered at every level, and its width."""
    levels = (0.50, 0.80, 0.90, 0.95)
    kal, emb = [], []
    for lev in levels:
        glo, ghi = gaussian_interval(res["kalman_pred"], res["var"], lev)
        kal.append(coverage(res["core_c"], glo, ghi))
        emb.append(coverage(res["core_c"], res[f"c_lo_{lev}"], res[f"c_hi_{lev}"]))
    worst_gap = max(abs(e - lev) for e, lev in zip(emb, levels))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6.6),
                                   gridspec_kw={"width_ratios": [1, 1.25]})

    # Left: calibration curve. On the diagonal = delivers what it promises.
    ax1.plot([0.4, 1.0], [0.4, 1.0], "--", color=INK, linewidth=1.5,
             label="Perfect: delivers what it promises")
    ax1.axvline(0.90, color=GREY, linestyle=":", linewidth=1.5)
    ax1.text(0.893, 0.03, "the device\nshows 90%", fontsize=11, color=GREY, va="bottom",
             ha="right")
    ax1.plot(levels, kal, "o-", color=WARN, linewidth=2.5, markersize=9,
             label="Kalman (uncalibrated)")
    ax1.plot(levels, emb, "o-", color=OK, linewidth=2.5, markersize=9,
             label="Ember conformal")
    for lev, k, e in zip(levels, kal, emb):
        ax1.text(lev - 0.012, e + 0.035, f"{e:.0%}", ha="center", fontsize=12,
                 fontweight="bold", color=OK)
        ax1.text(lev, k - 0.065, f"{k:.0%}", ha="center", fontsize=12,
                 fontweight="bold", color=WARN)
    if ext:
        ax1.plot([0.90], [ext["ember"]["coverage_90"]], "D", markersize=10,
                 markerfacecolor="white", markeredgecolor=OK, markeredgewidth=2,
                 label=f"Ember on {ext['ember']['n_subjects']} new people (HTT): "
                       f"{ext['ember']['coverage_90']:.0%}")
    ticks = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    ax1.set_xlim(0.4, 1.0)
    ax1.set_ylim(0, 1.05)
    ax1.set_xticks(ticks)
    ax1.set_xticklabels([f"{v:.0%}" for v in ticks], fontsize=12)
    ax1.set_yticks([0, 0.25, 0.5, 0.75, 0.9, 1.0])
    ax1.set_yticklabels(["0%", "25%", "50%", "75%", "90%", "100%"], fontsize=12)
    ax1.set_xlabel("Promised: the range's stated level", fontsize=14, fontweight="bold")
    ax1.set_ylabel("Delivered: true core inside the range", fontsize=14, fontweight="bold")
    ax1.set_title(f"Ember within {worst_gap * 100:.0f} point{'s' if round(worst_gap * 100) != 1 else ''}"
                  " of its promise at every level", fontsize=15, fontweight="bold")
    ax1.legend(fontsize=11, loc="upper left", frameon=False)
    ax1.grid(alpha=0.3)

    # Right: the 90 % range as the wearer would see it, drawn around the estimate
    glo, ghi = gaussian_interval(res["kalman_pred"], res["var"], 0.90)
    rows = [
        ("Kalman \"90%\"", float(np.mean(ghi - glo) / 2),
         coverage(res["core_c"], glo, ghi), WARN, None),
        ("Filter alone (2.2)", float(np.mean(res["c_hi_raw_0.9"] - res["c_lo_raw_0.9"]) / 2),
         coverage(res["core_c"], res["c_lo_raw_0.9"], res["c_hi_raw_0.9"]), GREY, "//"),
        ("Ember 2.3", float(res["hw90"].mean()),
         coverage(res["core_c"], res["c_lo_0.9"], res["c_hi_0.9"]), OK, None),
    ]
    y = np.arange(len(rows))[::-1]
    for yi, (name, half, cov, color, hatch) in zip(y, rows):
        ax2.barh(yi, 2 * half, left=-half, height=0.5,
                 color="white" if hatch else color, alpha=1 if hatch else 0.85,
                 edgecolor=color if hatch else INK, hatch=hatch, linewidth=1.5 if hatch else 0.5)
        ax2.plot([0, 0], [yi - 0.32, yi + 0.32], color=INK, linewidth=3)
        ax2.text(half + 0.03, yi, f"±{half:.2f} °C", va="center", fontsize=14,
                 fontweight="bold", color=INK)
        ax2.text(1.58, yi, f"held {cov:.0%}", va="center", ha="right", fontsize=16,
                 fontweight="bold", color=color if color != GREY else INK)
    ax2.set_yticks(y)
    ax2.set_yticklabels([r[0] for r in rows], fontsize=14)
    ax2.set_xlim(-0.8, 1.62)
    ax2.set_xticks([-0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75])
    ax2.set_ylim(-0.6, len(rows) - 0.4)
    ax2.axvline(0, color=INK, linewidth=0.8, alpha=0.3)
    ax2.set_xlabel("°C around the estimate (black tick), average over all minutes",
                   fontsize=13, fontweight="bold")
    narrower = 1 - rows[2][1] / rows[1][1]
    ax2.set_title(f"How wide it is: the correction cut Ember's by {narrower:.0%}",
                  fontsize=15, fontweight="bold")
    ax2.grid(axis="x", alpha=0.3)
    ax2.tick_params(axis="x", labelsize=12)

    fig.suptitle("Ember's range: promised vs delivered", fontsize=18,
                 fontweight="bold", y=1.02)
    fig.text(0.5, -0.03, f"PROSPIE V3, {res['subject'].nunique()} people, "
             f"{len(res):,} minutes, leave-one-subject-out. The Kalman range is the "
             "filter's own variance; it is never shown to the wearer.",
             ha="center", fontsize=11, color=GREY)
    fig.tight_layout()
    _save(fig, f"{prefix}_range.png")


def _warning_minutes(t, key):
    """Minutes the alert had been on when true core reached 38.5 (negative = came on
    that many minutes late, -inf = never came on)."""
    w = np.where(t[f"{key}_on"], t[f"{key}_lead"], -t[f"{key}_lag"])
    return np.where(np.isnan(w), -np.inf, w)


def figure_6_early_warning(res, prefix="judges"):
    """Early warning before true core reaches 38.5 °C."""
    t = alert_timing(res)
    n = len(t)
    tb = alert_timing(res.assign(pred=res["kalman_pred"]))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6.6),
                                   gridspec_kw={"width_ratios": [1.1, 1]})

    # Left: every trial lined up on the minute true core first reached 38.5
    m = res.merge(t[["subject", "condition", "t_danger"]], on=["subject", "condition"])
    m["rel"] = m["minute"] - m["t_danger"]
    m = m[(m["rel"] >= -40) & (m["rel"] <= 15)]
    g = m.groupby("rel")
    keep = g.size() >= n / 2           # only minutes most trials reach
    med = g[["core_c", "pred", "kalman_pred"]].median()[keep]
    q25, q75 = g["pred"].quantile(0.25)[keep], g["pred"].quantile(0.75)[keep]
    rel = med.index.to_numpy()

    ax1.fill_between(rel, q25, q75, color=ACC, alpha=0.18, linewidth=0,
                     label="Ember, middle half of trials")
    ax1.plot(rel, med["core_c"], color=INK, linewidth=3, label="True core (rectal)", zorder=5)
    ax1.plot(rel, med["kalman_pred"], "--", color=GREY, linewidth=2, label="Filter alone (2.2)")
    ax1.plot(rel, med["pred"], color=ACC, linewidth=2.5, label="Ember 2.3", zorder=4)
    ax1.axhline(WATCH_C, color=WARN, linestyle="--", linewidth=2, alpha=0.8)
    ax1.axhline(ACT_NOW_C, color=ACT, linestyle="--", linewidth=2, alpha=0.8)
    ax1.text(rel[0] + 0.5, WATCH_C + 0.02, f"Watch {WATCH_C}°C", color=WARN, fontsize=12,
             fontweight="bold")
    ax1.text(rel[0] + 0.5, ACT_NOW_C - 0.02, f"Act now {ACT_NOW_C}°C", color=ACT, fontsize=12,
             fontweight="bold", va="top")
    ax1.axvline(0, color=INK, linewidth=1.2, alpha=0.5)
    e0, c0 = float(med.loc[0.0, "pred"]), float(med.loc[0.0, "core_c"])
    ax1.plot([0], [e0], "o", color=ACC, markersize=10, zorder=6)
    where = ("above Watch, below Act now" if WATCH_C <= e0 < ACT_NOW_C
             else "below Watch" if e0 < WATCH_C else "above Act now")
    ax1.annotate(f"At that minute Ember read {e0:.2f} °C\n(median; true core {c0:.2f} °C):\n{where}",
                 xy=(0, e0), xytext=(-12, float(q25.min()) + 0.1), va="bottom",
                 fontsize=12, color=INK, arrowprops=dict(arrowstyle="->", color=INK),
                 bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=2), zorder=7)
    ax1.set_xlabel(f"Minutes from true core first reaching {ACT_NOW_C}°C",
                   fontsize=14, fontweight="bold")
    ax1.set_ylabel("Core temperature (°C, median of trials)", fontsize=14, fontweight="bold")
    ax1.set_title(f"{n} trials lined up on the danger minute", fontsize=16, fontweight="bold")
    ax1.legend(fontsize=11, loc="upper left", frameon=False)
    ax1.grid(alpha=0.3)
    ax1.tick_params(labelsize=12)

    # Right: share of trials already warned at least x minutes ahead
    xs = np.arange(-30, 46)
    ax2.axvspan(xs[0], 0, color=GREY, alpha=0.08)
    ax2.text(-15, 1.02, "late", ha="center", fontsize=12, color=GREY, fontweight="bold")
    ax2.text(22, 1.02, "warned ahead", ha="center", fontsize=12, color=GREY, fontweight="bold")
    for key, name, th, color in (("watch", "Watch", WATCH_C, WARN), ("act", "Act now", ACT_NOW_C, ACT)):
        w, wb = _warning_minutes(t, key), _warning_minutes(tb, key)
        ax2.plot(xs, [np.mean(wb >= x) for x in xs], "--", color=color, linewidth=1.8,
                 alpha=0.55, drawstyle="steps-pre", label=f"{name} ≥ {th}°C, filter alone (2.2)")
        ax2.plot(xs, [np.mean(w >= x) for x in xs], color=color, linewidth=3,
                 drawstyle="steps-pre", label=f"{name} ≥ {th}°C, Ember 2.3")
        on0 = int(np.sum(w >= 0))
        ax2.plot([0], [on0 / n], "o", color=color, markersize=9, zorder=5)
        never = int(np.sum(np.isinf(w)))
        txt = f"{on0}/{n} on in time" + (f"\nnever fired: {never}/{n}" if never else "")
        ax2.annotate(txt, xy=(0, on0 / n), xytext=(-28, on0 / n - (0.17 if key == "act" else 0.28)),
                     fontsize=12, fontweight="bold", color=color,
                     arrowprops=dict(arrowstyle="->", color=color))
        if key == "watch":
            k10 = int(np.sum(w >= 10))
            ax2.plot([10], [k10 / n], "o", color=color, markersize=9, zorder=5)
            ax2.annotate(f"{k10}/{n} at least\n10 min ahead", xy=(10, k10 / n),
                         xytext=(16, k10 / n + 0.06), fontsize=12, fontweight="bold",
                         color=color, arrowprops=dict(arrowstyle="->", color=color))
    ax2.axvline(0, color=INK, linewidth=1.2, alpha=0.5)
    ax2.set_xlim(xs[0], xs[-1])
    ax2.set_ylim(0, 1.08)
    ax2.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax2.set_yticklabels(["0%", "25%", "50%", "75%", "100%"], fontsize=12)
    ax2.set_xlabel(f"Minutes of warning before true core hit {ACT_NOW_C}°C",
                   fontsize=14, fontweight="bold")
    ax2.set_ylabel("Trials warned at least this early", fontsize=14, fontweight="bold")
    ax2.set_title("How far ahead each alert was on", fontsize=16, fontweight="bold")
    ax2.legend(fontsize=10.5, loc="upper right", bbox_to_anchor=(1, 0.93), frameon=False)
    ax2.grid(alpha=0.3)
    ax2.tick_params(axis="x", labelsize=12)

    w = _warning_minutes(t, "watch")
    lead = float(np.median(w[w >= 0]))
    fig.suptitle(f"Early warning: Watch was on before true core reached {ACT_NOW_C}°C "
                 f"in {int(np.sum(w >= 0))} of {n} trials, a median {lead:.0f} min ahead",
                 fontsize=18, fontweight="bold", y=1.02)
    fig.text(0.5, -0.03, f"PROSPIE V3, {n} held-out trials where rectal core reached "
             f"{ACT_NOW_C}°C. Warning = how long the alert had been on without a break at "
             "that minute; negative = it came on late.", ha="center", fontsize=11, color=GREY)
    fig.tight_layout()
    _save(fig, f"{prefix}_early_warning.png")


def main():
    print("Creating figures for judges...")
    res = load_results()
    ext = load_external()

    figure_1_coverage_bars(res)
    figure_2_trial_with_interval(res)
    figure_3_alert_timing(res)
    figure_4_error(res, ext)
    figure_5_range(res, ext)
    figure_6_early_warning(res)

    print("\nDone. Six figures ready for presentation.")


if __name__ == "__main__":
    main()
