"""
The learned correction Ember ships (firmware 2.3+).

ECTemp maps heart rate to core temperature with one curve for everyone and
lags a fast rise. This adds a small linear correction to its estimate,
learned from PROSPIE against a rectal reference:

    estimate = ECTemp + clamp(b0 + w . features, +/- CORR_MAX_C)

The features are computed once a minute, exactly as the firmware does
(ember_core.h, struct Correction), from things the device already has:

    ct          the filter's estimate this minute
    ct_d10      its change over the last 10 minutes
    hr5         mean heart rate of the last 5 minutes (carried over gaps)
    hr5_d10     its change over the last 10 minutes
    hr_rest     hr5 minus the wearer's resting heart rate (BASELINE)

Before 10 minutes of history exist, the "10 minutes ago" value is the
oldest one available. With no resting heart rate (no BASELINE yet) or no
heart rate ever, the correction is OFF: the device shows the filter's
estimate with the uncorrected table, which is what shipped before.

The 90% range keeps its guarantee because the correction is wrapped in the
same stratified conformal calibration, fitted on people the correction
model never trained on (see loso()).

evaluate.py uses loso() for every published number; export_firmware_table.py
uses fit() and the out-of-fold predictions for the shipped tables.
learned_correction.py is the experiment that chose this model.
"""

from collections import deque

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

from conformal import DEFAULT_LEVELS, StratifiedConformal
from ectemp import CT_CLAMP

FEATURES = ("ct", "ct_d10", "hr5", "hr5_d10", "hr_rest")
LAG_MIN = 10          # "change over 10 minutes"
HR_WIN_MIN = 5        # heart-rate smoothing window, minutes
RIDGE_ALPHA = 10.0    # on standardised features; fixed in advance, not tuned
# Safety rail: the correction never moves the estimate by more than this.
# Out-of-fold corrections on PROSPIE stay well inside it (see the export
# report); it exists for inputs the training data never saw.
CORR_MAX_C = 1.0
INNER_FOLDS = 5


# ------------------------------------------------------------- features

def trial_features(hr, ct, rest_hr):
    """
    One trial, one row per minute. hr: minute heart rate (NaN = no reading,
    the filter coasted). ct: the filter's estimate after that minute's step.
    rest_hr: resting heart rate (NaN = no baseline).

    Returns (X, active): X is (n, 5) in FEATURES order, active is a bool
    array - where False, the correction is off for that minute.
    """
    hr = np.asarray(hr, float)
    ct = np.asarray(ct, float)
    n = len(hr)
    X = np.full((n, len(FEATURES)), np.nan)
    win = deque(maxlen=HR_WIN_MIN)
    ct_hist, hr5_hist = [], []
    hr5 = np.nan
    for t in range(n):
        win.append(hr[t])
        vals = [v for v in win if np.isfinite(v)]
        if vals:
            hr5 = float(np.mean(vals))
        # else: carried over from the last minute that had one
        ct_hist.append(ct[t])
        ct_old = ct_hist[max(0, len(ct_hist) - 1 - LAG_MIN)]
        X[t, 0] = ct[t]
        X[t, 1] = ct[t] - ct_old
        if np.isfinite(hr5):
            hr5_hist.append(hr5)
            X[t, 2] = hr5
            X[t, 3] = hr5 - hr5_hist[max(0, len(hr5_hist) - 1 - LAG_MIN)]
            X[t, 4] = hr5 - rest_hr
    active = np.isfinite(X).all(axis=1)
    return X, active


def add_features(df, ct_col="pred"):
    """
    df: output of evaluate.predict_all (every minute of every trial, sorted,
    filter estimate in ct_col). Adds the feature columns and corr_active.
    Resting HR is the median of the first 10 minutes, the same value the
    filter's starting point already uses (the device: BASELINE).
    """
    df = df.copy()
    cols = {f: np.full(len(df), np.nan) for f in FEATURES}
    active = np.zeros(len(df), bool)
    for _, pos in df.groupby(["subject", "condition"], sort=False).indices.items():
        g = df.iloc[pos]
        rest = g.loc[g["minute"] < g["minute"].min() + 10, "hr"].median()
        X, a = trial_features(g["hr"].to_numpy(), g[ct_col].to_numpy(), rest)
        for j, f in enumerate(FEATURES):
            cols[f][pos] = X[:, j]
        active[pos] = a
    for f in FEATURES:
        df[f] = cols[f]
    df["corr_active"] = active
    return df


# ---------------------------------------------------------------- model

def fit(X, y, alpha=RIDGE_ALPHA):
    """
    Ridge regression on standardised features, returned in RAW units so the
    firmware needs no scaler: correction = intercept + coef . x
    """
    X = np.asarray(X, float)
    y = np.asarray(y, float)
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    w = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - y.mean()))
    coef = w / sd
    return {"coef": coef, "intercept": float(y.mean() - coef @ mu),
            "std_coef": w, "mean": mu, "sd": sd}


def correction(model, X):
    c = model["intercept"] + np.asarray(X, float) @ model["coef"]
    return np.clip(c, -CORR_MAX_C, CORR_MAX_C)


def apply(model, ct, X, active):
    """The shipped estimate: corrected where active, the filter's elsewhere."""
    ct = np.asarray(ct, float)
    est = ct.copy()
    if active.any():
        est[active] = np.clip(ct[active] + correction(model, X[active]), *CT_CLAMP)
    return est


# ----------------------------------------------------------------- LOSO

def _xy(frame, ct_col):
    return frame[list(FEATURES)].to_numpy(), (frame["core_c"] - frame[ct_col]).to_numpy()


def oof_estimates(train, ct_col="pred", folds=INNER_FOLDS):
    """Out-of-fold corrected estimates for active rows, grouped by subject."""
    X, y = _xy(train, ct_col)
    out = np.full(len(train), np.nan)
    k = min(folds, train["subject"].nunique())
    for a, b in GroupKFold(n_splits=k).split(X, y, train["subject"]):
        m = fit(X[a], y[a])
        out[b] = np.clip(train[ct_col].to_numpy()[b] + correction(m, X[b]), *CT_CLAMP)
    return out


def loso(df, n_strata=6, levels=DEFAULT_LEVELS, train_mask=None):
    """
    Leave one subject out, nested:
      - the correction is trained on the other subjects' active minutes
      - its conformal table is fitted on their OUT-OF-FOLD corrected
        estimates, so it measures error on people the model did not see
      - minutes where the correction is off get the uncorrected table,
        fitted on the other subjects' filter estimates (as before 2.3)

    df: add_features() output (any minutes; only scored ones are used).
    train_mask: optional boolean Series - rows allowed to TRAIN and
    CALIBRATE the correction (e.g. chest heart-rate trials only, when the
    evaluation also includes finger PPG trials). All rows are predicted.

    Returns the scored rows with kalman_pred (the filter), pred (shipped),
    c_lo_/c_hi_<level>, hw90, and c_lo_raw_0.9 / c_hi_raw_0.9 (the
    uncorrected 90% interval, for before/after comparisons).
    """
    df = df[df["core_c"].notna()].copy()
    df["kalman_pred"] = df["pred"]
    mask = (pd.Series(True, index=df.index) if train_mask is None
            else train_mask.reindex(df.index).fillna(False).astype(bool))
    pieces = []
    for held in sorted(df["subject"].unique()):
        te = df[df["subject"] == held].copy()
        tr = df[df["subject"] != held]

        raw = StratifiedConformal(n_strata=n_strata, levels=levels).fit(
            tr["kalman_pred"].to_numpy(), tr["core_c"].to_numpy())

        fit_rows = tr[tr["corr_active"] & mask.loc[tr.index]]
        oof = oof_estimates(fit_rows, "kalman_pred")
        cor = StratifiedConformal(n_strata=n_strata, levels=levels).fit(
            oof, fit_rows["core_c"].to_numpy())
        model = fit(*_xy(fit_rows, "kalman_pred"))

        act = te["corr_active"].to_numpy()
        X = te[list(FEATURES)].to_numpy()
        est = apply(model, te["kalman_pred"].to_numpy(), X, act)
        te["pred"] = est
        for lev in levels:
            lo_r, hi_r = raw.interval(te["kalman_pred"].to_numpy(), lev)
            lo_c, hi_c = cor.interval(est, lev)
            te[f"c_lo_{lev}"] = np.where(act, lo_c, lo_r)
            te[f"c_hi_{lev}"] = np.where(act, hi_c, hi_r)
            if lev == 0.90:
                te["c_lo_raw_0.9"], te["c_hi_raw_0.9"] = lo_r, hi_r
        te["hw90"] = (te["c_hi_0.9"] - te["c_lo_0.9"]) / 2
        pieces.append(te)
    return pd.concat(pieces, ignore_index=True)
