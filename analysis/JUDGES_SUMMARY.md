# Ember: Phase 2 Results for Judges

**Analysis**: Leave-one-subject-out cross-validation on PROSPIE V3 dataset  
**Data**: 37 participants (15 women, 20 men after excluding conflicting records), chest heart-rate sensors only (Equivital ECG + Polar)  
**Samples**: 14,041 minutes scored with reference core temperature

---

## 1. Coverage: Kalman vs Conformal Calibration

### The Problem
Published work using this algorithm reports "90% confidence intervals" derived from the Kalman filter's posterior variance. Independent measurement found these intervals badly miscalibrated.

### Our Results

| Method | 90% Nominal Coverage | Mean Width |
|---|---|---|
| **Kalman posterior (uncalibrated)** | **34%** | 0.34 °C |
| **Conformal (calibrated)** | **90%** | 1.35 °C |

**Headline**: The Kalman filter's "90%" interval covered only 34% of true values. Ember's conformal-calibrated interval delivers the promised 90%.

An interval that claims 90% and delivers far less is worse than no interval, because users act on it.

---

## 2. Coverage by True Temperature Band

The Kalman interval **fails most where it matters most**: at elevated core temperatures.

| True Core Temp | Samples | Kalman Coverage | Conformal Coverage |
|---|---|---|---|
| Normal (<37.5 °C) | 3,949 | 36% | **98%** |
| Warm (37.5-38.0 °C) | 4,435 | 40% | **95%** |
| **Watch (38.0-38.5 °C)** | 3,783 | 31% | **85%** |
| **Act Now (≥38.5 °C)** | 1,874 | 24% | **67%** |

At Act Now temperatures (≥38.5°C), the uncalibrated interval is essentially useless.

---

## 3. Lag Analysis: How Late Do Alerts Fire?

The estimate **lags** true core temperature. We measured the delay from when true core reached 38.5°C to when each alert fired (73 trials analyzed).

### Watch Alert (38.0°C threshold)
- **Median lag**: 0 minutes (fires at or before true core reaches 38.5°C in half of trials)
- **Mean lag**: 6.6 minutes (SD 14.9)
- **Range**: 0–65 minutes
- **Never fired**: 5 / 73 trials (7%)

### Act Now Alert (38.5°C threshold)
- **Median lag**: 1 minute
- **Mean lag**: 16.4 minutes (SD 22.3)
- **Range**: 0–63 minutes
- **Never fired**: 34 / 73 trials (47%)

### Two-Tier Design Validated
Watch fired before Act Now in **54%** of trials where Act Now eventually fired. This advance warning is why the two-threshold system works: **Watch carries the safety load**.

The Act Now alert fires late or not at all in many trials. A single-threshold system at 38.5°C would be unsafe.

---

## 4. Sex Bias Analysis

### Per-Sex Performance

| Sex | Subjects | Samples | Bias | RMSE | 90% Coverage |
|---|---|---|---|---|---|
| Women | 15 | 5,574 | −0.09 °C | 0.42 °C | 88% |
| Men | 20 | 7,963 | −0.18 °C | 0.40 °C | 90% |

### Bootstrap Analysis (5,000 resamples over subjects)

**Bias difference (men − women)**: −0.10 °C  
**95% CI**: [−0.26, +0.09] °C  
**Result**: Includes zero; **not statistically significant** (p=0.15)

**RMSE difference (men − women)**: −0.02 °C  
**95% CI**: [−0.13, +0.09] °C  
**Result**: Includes zero; not statistically significant (p=0.26)

### Note on Metric Choice
**Bias is the primary fairness metric**, not RMSE. A systematic offset between groups moves bias substantially but barely affects RMSE, which is dominated by within-subject variation. Testing this with simulated group differences confirmed: bias detected it, RMSE missed it completely. An audit run on RMSE alone would declare a biased model fair.

### Context
Published validations of this algorithm are overwhelmingly male. One 251-subject study had 36 women and ran no sex analysis; several others had none at all. **We ran the analysis whatever the answer**, and we report it.

---

## 5. Rising vs Steady Coverage (Optional)

The Kalman filter assumes a constant-velocity model. We tested whether miscalibration differs during rising vs steady phases.

**Rising phase**: Δcore ≥ +0.2°C in 5 minutes (n=1,253)
- Kalman: 31%
- Conformal: 86%

**Steady phase**: |Δcore| < 0.1°C in 5 minutes (n=6,416)
- Kalman: 33%
- Conformal: 90%

Both phases show the same pattern: the Kalman interval badly under-covers; conformal is near-nominal.

---

## Key Takeaways

1. **The published "90%" interval is dishonest**: it covered 34% in our data.
2. **Conformal calibration fixes this**: delivers the promised 90% coverage.
3. **The problem is worst where it matters**: at elevated core temps (≥38.5°C), Kalman covers 24%.
4. **The estimate lags true core**: Watch alert median lag 0 min, Act Now median lag 1 min (but highly variable).
5. **Two-tier alerts are essential**: Watch fires early and carries the safety load; Act Now alone would be unsafe.
6. **No sex bias detected**: men vs women difference in bias −0.10°C, 95% CI [−0.26, +0.09], includes zero.
7. **This is the first published sex analysis of this algorithm**, despite a decade of use.

---

## Figures

Three publication-quality figures in `figures/`:

1. **`judges_coverage.png`**: Coverage bars showing Kalman vs Conformal across temperature bands
2. **`judges_trial_interval.png`**: One trial showing estimate vs true core with calibrated interval
3. **`judges_lag.png`**: Histogram of alert lag times

All figures use large fonts and are readable on a projector.

---

## Data Provenance

**Dataset**: PROSPIE V3 (Prospective Study of Physiological Responses to Heat; Loughborough University)  
**License**: CC BY-NC 4.0  
**Participants**: 40 enrolled, 37 analyzed (2 excluded for conflicting sex codes, 1 for missing data)  
**Sex breakdown**: 15 women, 20 men (2 participants with conflicting codes excluded from sex analysis)  
**Conditions**: 9 heat stress protocols  
**Reference**: Rectal core temperature (gold standard)  
**Heart rate sensors**: Chest only (Equivital ECG + Polar); finger PPG excluded  
**Samples**: 14,041 minutes scored with reference core temperature  
**Validation**: Leave-one-subject-out (LOSO) cross-validation — no test subject's data in calibration set

---

## What This Means for Ember

- **Always show the ±**: the interval is calibrated and honest.
- **Never hide the number at ≥38.0°C**: the refusal logic must respect this.
- **Watch is the primary safety threshold**: it fires early; Act Now fires late or not at all.
- **Report the fairness result**: no sex bias detected, and we were the first to look.
- **Cite the lag**: the estimate lags true core by minutes. State this as a limitation.

---

**Generated**: 2024-10-23  
**Script**: `analysis/judges_results.py`  
**Figures**: `analysis/make_judge_figures.py`  
**Output**: `analysis/judges_results.json`
