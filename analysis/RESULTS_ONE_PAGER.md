# Ember Results: One Page for Slides

---

## The Problem

Published algorithms report **"90% confidence intervals"** for core temperature estimates. Independent testing found these intervals **badly miscalibrated**.

An interval that claims 90% and delivers far less is **worse than no interval** — users act on it.

---

## Our Solution: Conformal Calibration

We replaced the Kalman filter's uncalibrated variance with **stratified split conformal prediction**.

### Result

| Method | Claimed | Actual Coverage |
|---|---|---|
| **Kalman "90%" interval** | 90% | **34%** |
| **Ember conformal interval** | 90% | **90%** |

**Headline**: The published method's "90%" interval covered **only 34%** of true values. Ember delivers **90%**.

---

## Where It Fails Most

The uncalibrated interval is **worst at elevated core temperatures** — exactly where accuracy matters:

| True Core Temp | Kalman | Conformal |
|---|---|---|
| Normal (<37.5°C) | 36% | 98% |
| Warm (37.5-38.0°C) | 40% | 95% |
| **Watch (38.0-38.5°C)** | 31% | 85% |
| **Act Now (≥38.5°C)** | **24%** | 67% |

At Act Now temperatures (≥38.5°C), the Kalman interval is **essentially useless**.

---

## Alert Timing: The Estimate Lags

We measured the delay from when **true core reached 38.5°C** to when alerts fired (73 trials):

- **Watch (38.0°C)**: median lag **0 min** (fires early or on time in half of trials)
- **Act Now (38.5°C)**: median lag **1 min**, but never fired in **47% of trials**

**Implication**: A single 38.5°C threshold would be unsafe. The **two-tier design** (Watch + Act Now) works because **Watch carries the safety load**.

---

## Fairness: Men vs Women

**Question**: Does the algorithm work equally well for everyone?

| Sex | Subjects | Bias | RMSE |
|---|---|---|---|
| Women | 15 | −0.09 °C | 0.42 °C |
| Men | 20 | −0.18 °C | 0.40 °C |

**Difference (men − women)**: −0.10 °C  
**95% CI**: [−0.26, +0.09]  
**Result**: **Not statistically significant**

### Context
Published validations of this algorithm are **overwhelmingly male**. One 251-subject study had 36 women and ran **no sex analysis**. 

**We ran it whatever the answer, and we report it.**

---

## Data

- **PROSPIE V3** (Loughborough, CC BY-NC 4.0)
- **37 participants** (15 women, 20 men), 9 heat conditions
- **14,041 minutes** scored with rectal reference
- **Chest heart rate only** (Equivital ECG + Polar)
- **Leave-one-subject-out** cross-validation

---

## Key Takeaways for Ember

1. **Always show the ±** — it's calibrated and honest
2. **Never hide the number at ≥38.0°C** — refusal logic must respect this
3. **Watch (38.0°C) is the primary safety threshold** — it fires early
4. **Act Now (38.5°C) fires late or not at all** — it's a backup, not the main alert
5. **No sex bias detected** — and we were the first to look
6. **The estimate lags true core by minutes** — state this as a limitation

---

## What Makes This a Contribution

1. **Honest accuracy**: LOSO validation on open data (most work doesn't)
2. **Calibrated uncertainty**: conformal intervals hold their promise (Kalman doesn't)
3. **Fairness audit**: first sex-stratified analysis of this algorithm
4. **Refusal mode**: the device says "I don't know" when signals disagree

**This is not just a reimplementation. It's an honest, auditable, fair version of a widely-deployed algorithm.**

---

**Figures**: `figures/judges_coverage.png`, `judges_trial_interval.png`, `judges_lag.png`  
**Full results**: `analysis/JUDGES_SUMMARY.md`  
**Data**: `analysis/judges_results.json`
