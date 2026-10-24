"""
Reference implementation of the Buller et al. (2013) / USARIEM ECTemp
extended Kalman filter for estimating core body temperature from heart rate.

WHY THIS FILE EXISTS
--------------------
As of this writing nobody has released an open implementation of ECTemp.
USARIEM publishes a browser demo widget, not code. Every paper that
benchmarks against it has had to reimplement it, and at least one group
reports contacting USARIEM about the original and getting no reply.

So this is a small contribution in its own right: a clean, tested, cited
reference implementation.

    PATENT NOTE. The method is covered by US 2014/0180027 A1 and
    US 10,702,165 B2. That is irrelevant for coursework, a hackathon, or
    research use, and very relevant if you ever try to sell it. Any
    commercial path should route around the patented method rather than
    through it.

Parameters are from USARIEM Technical Report T17-08 (Looney et al. 2017)
and the patent application, which agree.

    python3 ectemp.py        # runs the self-check and a demo
"""

import math

import numpy as np

# ---------------------------------------------------------------- constants
# Observation model: HR = B2*CT^2 + B1*CT + B0
B2 = -4.5714
B1 = 384.4286
B0 = -7887.1

GAMMA_SQ = 0.000484      # process noise variance, (0.022)^2, per 1-min step
SIGMA_SQ = 356.4544      # measurement noise variance, (18.88)^2, bpm^2

CT_INIT_DEFAULT = 37.1
V_INIT_DEFAULT = 0.0

CT_CLAMP = (35.0, 41.5)


def hr_from_ct(ct):
    return B2 * ct * ct + B1 * ct + B0


def dhr_dct(ct):
    return 2.0 * B2 * ct + B1


def ct_from_hr(hr):
    """Inverse of the observation model, lower (physiological) root."""
    a, b, c = B2, B1, B0 - hr
    disc = b * b - 4 * a * c
    if disc < 0:
        return float("nan")
    return (-b + math.sqrt(disc)) / (2 * a)


class ECTemp:
    """
    Extended Kalman filter. Feed one heart rate per minute.

    Exposes both the point estimate and the filter's own posterior variance.
    The variance is included so you can MEASURE how badly calibrated it is -
    see conformal.py. Do not ship it to a user as a confidence interval.
    """

    def __init__(self, ct_init=CT_INIT_DEFAULT, v_init=V_INIT_DEFAULT,
                 step_seconds=60.0):
        self.ct = float(ct_init)
        self.v = float(v_init)
        self.gamma_sq = GAMMA_SQ * (step_seconds / 60.0)

    def update(self, hr):
        ct_pred = self.ct
        v_pred = self.v + self.gamma_sq
        c_t = dhr_dct(ct_pred)
        denom = c_t * c_t * v_pred + SIGMA_SQ
        k = (v_pred * c_t) / denom if denom != 0 else 0.0
        self.ct = ct_pred + k * (hr - hr_from_ct(ct_pred))
        self.v = max(0.0, (1.0 - k * c_t) * v_pred)
        return self.ct, self.v


def run_series(hr_series, ct_init=CT_INIT_DEFAULT, step_seconds=60.0):
    """
    Filter a whole heart-rate series.
    Returns (ct_estimates, posterior_variances), both 1-D arrays.
    """
    f = ECTemp(ct_init=ct_init, step_seconds=step_seconds)
    out_ct, out_v = [], []
    for hr in np.asarray(hr_series, dtype=float):
        if not np.isfinite(hr):
            # No observation: predict only, variance grows. This is the
            # correct behaviour and most implementations get it wrong by
            # simply skipping the sample.
            f.v += f.gamma_sq
        else:
            f.update(float(hr))
        out_ct.append(float(np.clip(f.ct, *CT_CLAMP)))
        out_v.append(f.v)
    return np.asarray(out_ct), np.asarray(out_v)


def init_from_resting_hr(hr_resting):
    """
    Pick CT0 from the subject's own resting heart rate instead of assuming
    37.1 C for everyone. A cheap, defensible first step toward
    individualisation, and it costs nothing.
    """
    ct = ct_from_hr(float(hr_resting))
    if not np.isfinite(ct):
        return CT_INIT_DEFAULT
    return float(np.clip(ct, 36.4, 37.6))


# ------------------------------------------------------------- self-check

def self_check(verbose=True):
    """
    Published coefficients get transcribed wrongly. A 2024 peer-reviewed
    paper prints a core-temperature observation equation whose peak is over
    700 bpm. This check takes a millisecond and catches that class of error.
    """
    ok = True
    for ct, lo, hi in [(36.5, 40, 75), (37.0, 65, 95), (38.0, 105, 135),
                       (39.0, 135, 170), (40.0, 155, 195)]:
        hr = hr_from_ct(ct)
        good = lo <= hr <= hi
        ok &= good
        if verbose:
            print(f"  [{'ok ' if good else 'BAD'}] CT {ct:.1f} -> HR {hr:6.1f} "
                  f"(expect {lo}-{hi})")
    peak = -B1 / (2 * B2)
    good = peak > 41.0
    ok &= good
    if verbose:
        print(f"  [{'ok ' if good else 'BAD'}] model peaks at CT {peak:.2f} "
              f"(must be > 41.0)")
    rt = ct_from_hr(hr_from_ct(38.0))
    good = abs(rt - 38.0) < 1e-6
    ok &= good
    if verbose:
        print(f"  [{'ok ' if good else 'BAD'}] inverse round trip -> {rt:.6f}")
    return bool(ok)


if __name__ == "__main__":
    print("ECTemp reference implementation")
    print("=" * 56)
    print("\nCoefficient self-check:")
    ok = self_check()
    print(f"\n  {'PASS' if ok else 'FAIL'}\n")

    print("Steady-state CT for a sustained heart rate:")
    for hr in (70, 100, 130, 150, 170):
        print(f"  {hr:3d} bpm -> {ct_from_hr(hr):.2f} C")

    print("\nCT0 chosen from resting HR:")
    for hr in (55, 65, 75, 85):
        print(f"  resting {hr:3d} bpm -> CT0 {init_from_resting_hr(hr):.2f} C")
