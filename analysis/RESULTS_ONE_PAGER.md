# Ember Results: One Page for Slides

All numbers: PROSPIE V3, 37 people, chest heart rate, leave-one-subject-out, 14,041 minutes against a rectal reference.

---

## The problem

The Kalman filter behind this algorithm comes with its own variance, and it is natural to show it as a "90%" range. We measured how often that range actually contains the true core temperature.

## The result

| | Promised | Measured |
|---|---|---|
| Kalman "90%" range | 90% | **34%** |
| Ember calibrated range | 90% | **90%** (89.7%) |

Ember replaces the Kalman variance with stratified split conformal intervals, fitted on other people and tested on someone new.

---

## Where it is weakest

| True core | Kalman | Ember |
|---|---|---|
| Under 37.5 °C | 36% | 98% |
| 37.5–38.0 °C | 40% | 95% |
| 38.0–38.5 °C | 31% | 86% |
| 38.5 °C and up | **24%** | **67%** |

At 38.5 °C and up, Ember's range holds about two times in three, not nine in ten. The estimate lags a fast rise and reads low. We say so.

---

## How late is the alarm?

73 trials reached a true core of 38.5 °C. At that minute:

- **Watch (38.0 °C) was already on in 47 (64%)**, for a median of 13 minutes. 21 came on later (median 14 min late). 5 never did.
- **Act now (38.5 °C) was on in 18 (25%).** 21 came on later (median 41 min late). **34 (47%) never fired.**
- Watch was the only alert in 29 trials (40%). Neither fired in 5 (7%).

**Implication**: Watch is the safety threshold. A single 38.5 °C alarm would have stayed silent in nearly half of these trials.

---

## Fairness: men vs women

| | People | Bias | RMSE |
|---|---|---|---|
| Women | 15 | −0.09 °C | 0.42 °C |
| Men | 20 | −0.18 °C | 0.40 °C |

**Difference (men − women)**: −0.10 °C, 95% CI [−0.26, +0.09]. No clear difference, but the interval cannot rule out a small one.

Published validations of this algorithm are mostly male; one 251-subject study had 36 women and no sex analysis. We found no published sex-stratified analysis to compare against.

---

## Limits

- Calibrated on chest ECG heart rate. It carries over to any sensor that reads heart rate correctly; the demo uses low-cost pulse sensors, a product would use validated ones.
- When heart rate was missing in most minutes, the range held only about 75%.
- Coverage drops to 67% at true core ≥ 38.5 °C; Act now never fired in 47% of trials that got there.
- Not a medical device.

---

## What makes this a contribution

1. **Honest accuracy**: leave-one-subject-out on open data.
2. **Uncertainty that keeps its promise**: 90% means 90% overall, and we show where it falls short.
3. **Lag measured, not hidden**: the two-tier alert design follows from it.
4. **Sex-stratified check**: one we could not find published for this algorithm.
5. **Refusal mode**: the device says "can't estimate" when its signals disagree, except at 38.0 °C and up, where it always shows the number.

---

**Figures**: `figures/judges_coverage.png`, `figures/judges_trial_interval.png`, `figures/judges_lag.png`
**Full results**: `analysis/JUDGES_SUMMARY.md`, `analysis/judges_results.txt`, `analysis/judges_results.json`
