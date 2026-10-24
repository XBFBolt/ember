"""
Calibrated uncertainty for core temperature estimation.

THE PROBLEM THIS SOLVES
-----------------------
A Kalman filter hands you a posterior variance, and it is extremely
tempting to put 1.96*sqrt(v) on the display and call it a 95% interval.
Published work that actually measured the coverage of ECTemp's variance
found it badly miscalibrated - intervals that should contain the truth 90%
of the time contained it a small fraction of that.

An interval that claims 90% and delivers far less is worse than no
interval, because a user acts on it.

THE FIX
-------
Split conformal prediction. Hold out a calibration set, measure the actual
distribution of |error|, and take the quantile. The resulting interval has
a finite-sample coverage guarantee under exchangeability, with no
assumption that the errors are Gaussian - which they are emphatically not
here.

Two refinements that matter for this problem:

  STRATIFICATION. Error grows with temperature: the model is worst exactly
  where it matters. One global quantile therefore over-covers at rest and
  under-covers in the danger zone. Calibrating within strata of predicted
  temperature fixes that, and is the idea behind the SCOPE method in the
  published conformal work on this problem.

  SUBJECT-WISE SPLITTING. The calibration subjects must be different people
  from the test subjects. Calibrating on the same subject you evaluate on
  leaks, and at least one published result does exactly that.

    python3 conformal.py     # self-test on synthetic data
"""

import numpy as np

DEFAULT_LEVELS = (0.50, 0.80, 0.90, 0.95)


# ------------------------------------------------------- global conformal

def fit_global(residuals, levels=DEFAULT_LEVELS):
    """
    residuals: |y_true - y_pred| on the calibration set.
    Returns {level: half_width}. Uses the finite-sample corrected quantile
    index, which is what gives the coverage guarantee.
    """
    r = np.asarray(residuals, dtype=float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < 20:
        raise ValueError(f"only {n} calibration points; need at least 20")
    out = {}
    for a in levels:
        # ceil((n+1) * level) / n quantile
        q_idx = min(1.0, np.ceil((n + 1) * a) / n)
        out[a] = float(np.quantile(r, q_idx, method="higher"))
    return out


# -------------------------------------------- stratified conformal (SCOPE)

class StratifiedConformal:
    """
    Calibrate separately within bins of PREDICTED core temperature, so the
    interval widens where the model is genuinely worse instead of averaging
    that away.
    """

    def __init__(self, n_strata=5, levels=DEFAULT_LEVELS, min_per_stratum=20):
        self.n_strata = int(n_strata)
        self.levels = tuple(levels)
        self.min_per_stratum = int(min_per_stratum)
        self.edges_ = None
        self.widths_ = None      # list of {level: half_width}, per stratum
        self.global_ = None      # fallback

    def fit(self, y_pred, y_true):
        y_pred = np.asarray(y_pred, float)
        y_true = np.asarray(y_true, float)
        m = np.isfinite(y_pred) & np.isfinite(y_true)
        y_pred, y_true = y_pred[m], y_true[m]
        resid = np.abs(y_true - y_pred)

        self.global_ = fit_global(resid, self.levels)

        # Equal-count strata on the predicted value.
        qs = np.linspace(0, 1, self.n_strata + 1)
        edges = np.quantile(y_pred, qs)
        edges[0], edges[-1] = -np.inf, np.inf
        edges = np.unique(edges)
        self.edges_ = edges

        self.widths_ = []
        for i in range(len(edges) - 1):
            sel = (y_pred >= edges[i]) & (y_pred < edges[i + 1])
            if sel.sum() >= self.min_per_stratum:
                self.widths_.append(fit_global(resid[sel], self.levels))
            else:
                # Not enough data in this bin: fall back rather than invent
                # a narrow interval from six points.
                self.widths_.append(dict(self.global_))
        return self

    def _stratum(self, y_pred):
        return np.clip(np.searchsorted(self.edges_, y_pred, side="right") - 1,
                       0, len(self.widths_) - 1)

    def interval(self, y_pred, level=0.90):
        """Return (lower, upper) arrays for the given nominal level."""
        y_pred = np.asarray(y_pred, float)
        idx = self._stratum(y_pred)
        half = np.array([self.widths_[i][level] for i in idx])
        return y_pred - half, y_pred + half

    def half_width(self, y_pred, level=0.90):
        y_pred = np.asarray(y_pred, float)
        idx = self._stratum(y_pred)
        return np.array([self.widths_[i][level] for i in idx])


# ------------------------------------------------------------- evaluation

def coverage(y_true, lo, hi):
    y_true = np.asarray(y_true, float)
    m = np.isfinite(y_true) & np.isfinite(lo) & np.isfinite(hi)
    if m.sum() == 0:
        return float("nan")
    return float(np.mean((y_true[m] >= lo[m]) & (y_true[m] <= hi[m])))


def gaussian_interval(y_pred, variance, level=0.90):
    """
    The naive interval you get from the Kalman posterior variance. Included
    so you can measure how far off it is, which is a result in itself.
    """
    from scipy.stats import norm
    z = norm.ppf(0.5 + level / 2.0)
    half = z * np.sqrt(np.maximum(np.asarray(variance, float), 0.0))
    y_pred = np.asarray(y_pred, float)
    return y_pred - half, y_pred + half


def coverage_table(y_true, y_pred, variance, conformal, levels=DEFAULT_LEVELS):
    """
    The central table of the whole project: nominal level versus what each
    method actually delivers.
    """
    rows = []
    for a in levels:
        glo, ghi = gaussian_interval(y_pred, variance, a)
        clo, chi = conformal.interval(y_pred, a)
        rows.append({
            "nominal": a,
            "kalman_coverage": coverage(y_true, glo, ghi),
            "kalman_width": float(np.nanmean(ghi - glo)),
            "conformal_coverage": coverage(y_true, clo, chi),
            "conformal_width": float(np.nanmean(chi - clo)),
        })
    return rows


# ------------------------------------------------- selective prediction

def risk_coverage(y_true, y_pred, half_width, n_points=40):
    """
    The refusal curve. Sort predictions by how uncertain the model says they
    are, then ask: if we only answer on the most confident X% of samples,
    what is the error on those?

    A device that refuses is a device you can trust. This curve is how you
    choose the threshold, and it is a far better slide than a single RMSE.
    """
    y_true = np.asarray(y_true, float)
    y_pred = np.asarray(y_pred, float)
    hw = np.asarray(half_width, float)
    m = np.isfinite(y_true) & np.isfinite(y_pred) & np.isfinite(hw)
    y_true, y_pred, hw = y_true[m], y_pred[m], hw[m]

    order = np.argsort(hw)
    err = np.abs(y_true - y_pred)[order]
    n = err.size
    out = []
    for frac in np.linspace(1.0, 0.1, n_points):
        k = max(10, int(round(frac * n)))
        e = err[:k]
        out.append({
            "answered_fraction": k / n,
            "rmse": float(np.sqrt(np.mean(e ** 2))),
            "mae": float(np.mean(e)),
            "threshold": float(hw[order][k - 1]),
        })
    return out


# ------------------------------------------------------------- self-test

def _self_test():
    print("Conformal calibration self-test")
    print("=" * 58)
    rng = np.random.default_rng(0)
    n = 4000

    # Heteroscedastic, heavy-tailed errors - like the real thing, and
    # exactly the case where a Gaussian variance fails.
    y_pred = rng.uniform(36.5, 39.5, n)
    scale = 0.12 + 0.55 * np.clip(y_pred - 37.0, 0, None) / 2.5
    err = rng.standard_t(df=3, size=n) * scale
    y_true = y_pred + err
    claimed_var = np.full(n, 0.05 ** 2)      # an over-confident filter

    cut = n // 2
    cal_p, cal_t = y_pred[:cut], y_true[:cut]
    te_p, te_t = y_pred[cut:], y_true[cut:]
    te_v = claimed_var[cut:]

    sc = StratifiedConformal(n_strata=5).fit(cal_p, cal_t)

    print(f"\n{'nominal':>8} | {'kalman':>8} {'width':>7} | "
          f"{'conformal':>10} {'width':>7}")
    print("-" * 52)
    rows = coverage_table(te_t, te_p, te_v, sc)
    for r in rows:
        print(f"{r['nominal']:>8.2f} | {r['kalman_coverage']:>8.3f} "
              f"{r['kalman_width']:>7.3f} | {r['conformal_coverage']:>10.3f} "
              f"{r['conformal_width']:>7.3f}")

    for r in rows:
        assert abs(r["conformal_coverage"] - r["nominal"]) < 0.05, \
            f"conformal coverage off at {r['nominal']}"
    assert rows[-1]["kalman_coverage"] < 0.60, \
        "the over-confident baseline should badly under-cover"
    print("\n  conformal tracks its nominal level; the Gaussian interval "
          "does not.")

    rc = risk_coverage(te_t, te_p, sc.half_width(te_p, 0.90))
    full, tenth = rc[0], rc[-1]
    print(f"\n  answering 100% of samples : RMSE {full['rmse']:.3f}")
    print(f"  answering  {tenth['answered_fraction']*100:.0f}% of samples : "
          f"RMSE {tenth['rmse']:.3f}")
    assert tenth["rmse"] < full["rmse"], "refusing should improve error"
    print("\n  PASS")


if __name__ == "__main__":
    _self_test()
