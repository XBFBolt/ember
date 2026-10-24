# Ember: Phase 2 Results for Judges

**Analysis**: leave-one-subject-out (LOSO) on PROSPIE V3. Each person is scored by a calibration fitted on everyone else.
**Data**: 37 participants with chest heart-rate data (Equivital ECG or Polar strap), 128 trials, 14,041 scored minutes against a rectal reference.
**Calibration**: 6 conformal strata, the same table the firmware and webapp use (`firmware/ember/conformal_table.h`).

---

## 1. Coverage: Kalman vs conformal

The Kalman filter carries its own variance, and reading it as a 90% range is the obvious thing to do. We measured how often that range contains the true value.

| Method | Promised | Measured coverage | Mean width |
|---|---|---|---|
| Kalman posterior (uncalibrated) | 90% | **34.3%** | 0.34 °C |
| Ember conformal (calibrated) | 90% | **89.7%** | 1.34 °C |

**Headline**: the Kalman "90%" range held 34% of the time. Ember's held 90% (89.7%).

A range that promises 90% and delivers a third of that is worse than no range, because people act on it.

---

## 2. Coverage by true temperature

| True core | Minutes | Kalman | Conformal |
|---|---|---|---|
| Under 37.5 °C | 3,949 | 36% | 98% |
| 37.5–38.0 °C | 4,435 | 40% | 95% |
| 38.0–38.5 °C (Watch) | 3,783 | 31% | 86% |
| 38.5 °C and up (Act now) | 1,874 | 24% | **67%** |

The Kalman range is worst where it matters most. Ember's range is well calibrated overall but drops to 67% when true core is 38.5 °C or higher. The calibration is fitted by *predicted* temperature, and when core is high the estimate lags and reads low, so the truth escapes the top of the range. This is the main limitation and we state it.

---

## 3. Alert timing: where were the alerts when true core reached 38.5 °C?

73 trials reached a true core of 38.5 °C. At the first minute it did:

| | Watch (estimate ≥ 38.0) | Act now (estimate ≥ 38.5) |
|---|---|---|
| Already on | **47 / 73 (64%)**, on for a median 13 min (IQR 6–21) | 18 / 73 (25%), on for a median 8 min |
| Came on later | 21, median 14 min late, worst 65 | 21, median 41 min late, worst 63 |
| Never came on | 5 / 73 (7%) | **34 / 73 (47%)** |

- In **29 / 73 trials (40%)** Watch came on and Act now never did.
- In **5 / 73 trials (7%)** neither alert ever came on.

**What this means**: Watch at 38.0 °C carries the safety load. It is usually on before true core reaches 38.5, while Act now is late or silent in three trials out of four. A single 38.5 °C alarm would have missed nearly half of these trials. This is lag, and it is real.

---

## 4. Men vs women

| | Participants | Minutes | Bias | RMSE | 90% coverage |
|---|---|---|---|---|---|
| Women | 15 | 5,574 | −0.09 °C | 0.42 °C | 88% |
| Men | 20 | 7,963 | −0.18 °C | 0.40 °C | 90% |

**Bias difference (men − women)**: −0.10 °C, 95% CI [−0.26, +0.09] (bootstrap over participants, 5,000 resamples). The interval includes zero, so we found no clear difference, but it is about ±0.2 °C wide and cannot rule out a small one.

**RMSE difference**: −0.02 °C, 95% CI [−0.13, +0.09].

**Why bias, not RMSE**: a systematic offset between groups moves bias a lot and RMSE barely at all, because RMSE is dominated by within-person error. When we tested the pipeline on a simulated group offset, bias caught it and RMSE missed it. An audit on RMSE alone would call a biased model fair.

**Context**: published validations of this algorithm are mostly male. One 251-subject study had 36 women and ran no sex analysis. We found no published sex-stratified analysis to compare against.

---

## 5. Rising vs steady (optional)

| Phase | Minutes | Kalman | Conformal |
|---|---|---|---|
| Rising (true core up ≥ 0.2 °C in 5 min) | 1,253 | 31% | 85% (84.9%) |
| Steady (change under 0.1 °C in 5 min) | 6,416 | 33% | 91% |

Rising coverage is just under 85%, consistent with the lag in section 3. In a quick test, giving rising minutes their own ± did not help; a range that reaches further above the estimate than below helped a little. Neither is shipped.

---

## 6. Other limits worth stating

- **Pulse sensors.** The filter only sees the heart-rate number, so the chest calibration carries over to any sensor that reports heart rate correctly. In PROSPIE, finger pulse-sensor trials scored about the same as chest trials from the same conditions (bias −0.41 vs −0.36 °C, coverage 74% vs 78%). The demo uses low-cost pulse sensors; a product would use validated heart-rate sensors.
- **Missing heart rate.** In the conditions where heart rate was missing in about 80% of minutes, the range held only 74–78%, against 90% overall. Gaps in heart rate cost coverage, so the device must keep dropouts rare and widen the ± while it is coasting.
- **Accuracy overall**: RMSE 0.41 °C, bias −0.14 °C, R² 0.47. Detecting true core ≥ 38.0 °C: sensitivity 60.6%, specificity 89.5%.
- Not a medical device.

---

## Key takeaways

1. The Kalman "90%" range covered **34%**. Ember's calibrated range covered **90%** (89.7%).
2. At true core ≥ 38.5 °C, Ember's coverage drops to **67%** because the estimate lags.
3. When true core reached 38.5 °C, **Watch was already on in 64%** of trials; **Act now never fired in 47%**.
4. Watch is the safety threshold, not an extra. In 40% of trials it was the only alert.
5. No clear difference between men and women (bias −0.10 °C, CI [−0.26, +0.09]), and no published sex-stratified analysis to compare with.

---

## Figures (`figures/`)

1. `judges_coverage.png`: Kalman vs conformal coverage by true temperature band
2. `judges_trial_interval.png`: one held-out trial, estimate vs true core with the ± band
3. `judges_lag.png`: where Watch and Act now stood when true core reached 38.5 °C

---

## Data provenance

- **Dataset**: PROSPIE V3, Loughborough University, CC BY-NC 4.0 (DOI 10.17028/rd.lboro.26076577)
- **Participants**: 40 in the dataset; 37 have chest heart-rate data and are analysed. Participants 17 and 18 have conflicting sex codes, so the men vs women comparison uses 35 (15 women, 20 men).
- **Conditions**: 9 heat-stress protocols, one row per minute
- **Reference**: rectal temperature
- **Heart rate**: chest only (Equivital ECG, Polar strap); finger PPG excluded
- **Validation**: leave-one-subject-out; no test participant's data is in its calibration

---

**Generated**: 2026-10-24
**Scripts**: `analysis/evaluate.py --prefix ember_chest`, `analysis/judges_results.py`, `analysis/make_judge_figures.py`
**Output**: `analysis/results_chest.txt`, `analysis/judges_results.txt`, `analysis/judges_results.json`
