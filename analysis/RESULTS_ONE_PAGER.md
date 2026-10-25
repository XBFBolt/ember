# Ember Results: One Page for Slides

All numbers: PROSPIE V3, 37 people, chest heart rate, leave-one-subject-out, 14,041 minutes against a rectal reference. Ember = the published ECTemp filter + a learned correction (firmware 2.3).

---

## The problem

The Kalman filter behind this algorithm comes with its own variance, and it is natural to show it as a "90%" range. We measured how often that range actually contains the true core temperature.

## The result

| | Promised | Measured |
|---|---|---|
| Kalman "90%" range | 90% | **34%** |
| Ember calibrated range | 90% | **89%** (89.2%) |

Ember replaces the Kalman variance with stratified split conformal intervals, fitted on other people and tested on someone new.

---

## A small learned correction makes it sharper

A linear model, learned from the same data and tested on people it never saw, adjusts the filter using heart rate compared with the wearer's own resting rate.

| | Filter alone | Ember |
|---|---|---|
| Error (RMSE) | 0.41 °C | **0.32 °C** |
| Average ± | 0.67 °C | **0.49 °C** |
| Watch on in time, true core reaching 38.5 °C | 47 / 73 | **65 / 73** |
| Act now never fired | 34 / 73 | **27 / 73** |
| Act now false alarms | 13 / 55 | 13 / 55 |

Better for 31 of 37 people (error change −0.09 °C, 95% CI [−0.13, −0.05]). Off until the wearer's baseline is captured.

---

## Where it is weakest

| True core | Kalman | Ember |
|---|---|---|
| Under 37.5 °C | 36% | 89% |
| 37.5–38.0 °C | 40% | 96% |
| 38.0–38.5 °C | 31% | 91% |
| 38.5 °C and up | **24%** | **71%** |

At 38.5 °C and up, Ember's range holds about seven times in ten, not nine. The estimate still lags a fast rise and reads low. We say so.

---

## How late is the alarm?

73 trials reached a true core of 38.5 °C. At that minute:

- **Watch (38.0 °C) was already on in 65 (89%)**, for a median of 12 minutes. 8 came on later (median 8 min late). None stayed off.
- **Act now (38.5 °C) was on in 17 (23%).** 29 came on later (median 15 min late). **27 (37%) never fired.**

**Implication**: Watch is the safety threshold. A single 38.5 °C alarm would have stayed silent in over a third of these trials.

---

## Fairness: men vs women

| | People | Bias | RMSE |
|---|---|---|---|
| Women | 15 | +0.03 °C | 0.31 °C |
| Men | 20 | −0.03 °C | 0.33 °C |

**Difference (men − women)**: −0.06 °C, 95% CI [−0.16, +0.05]. No clear difference, but the interval cannot rule out a small one.

Published validations of this algorithm are mostly male; one 251-subject study had 36 women and no sex analysis. We found no published sex-stratified analysis to compare against.

---

## Limits

- Trained on one dataset, one lab, treadmill walking in a heat chamber. The correction was chosen among seven variants on this data, so its gains are slightly optimistic.
- On a second dataset never used for fitting (HTT, 65 people, ingestible pill), the 90% range covered 82%, not 89% (Kalman 27%). The extra misses are over-reads late in long walks, so the cost is false alarms (Act now in 25 of 82 calm trials), not missed heat.
- Calibrated on chest ECG heart rate. It carries over to any sensor that reads heart rate correctly; the demo uses a low-cost pulse sensor, a product would use a validated one.
- Coverage drops to 71% at true core ≥ 38.5 °C; Act now never fired in 37% of trials that got there.
- Watch comes on a little more often just under 38.0 °C than before the correction (specificity 0.84, was 0.90).
- Not a medical device.

---

## What makes this a contribution

1. **Honest accuracy**: leave-one-subject-out on open data.
2. **Uncertainty that keeps its promise**: 90% means about 90% overall, and we show where it falls short.
3. **A learned correction that can't break the promise**: whatever it does, the range is recalibrated on people it never saw.
4. **Lag measured, not hidden**: the two-tier alert design follows from it.
5. **Sex-stratified check**: one we could not find published for this algorithm.
6. **Refusal mode**: the device says "can't estimate" when its signals disagree, except at 38.0 °C and up, where it always shows the number.

---

**Figures**: `figures/judges_coverage.png`, `figures/judges_trial_interval.png`, `figures/judges_lag.png`, `figures/judges_rmse.png`, `figures/judges_range.png`, `figures/judges_early_warning.png`
**Full results**: `analysis/JUDGES_SUMMARY.md`, `analysis/judges_results.txt`, `analysis/judges_results.json`
