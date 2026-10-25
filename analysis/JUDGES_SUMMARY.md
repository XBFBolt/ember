# Ember: Results for Judges

**Analysis**: leave-one-subject-out (LOSO) on PROSPIE V3. Each person is scored by a model and calibration fitted on everyone else.
**Data**: 37 participants with chest heart-rate data (Equivital ECG or Polar strap), 128 trials, 14,041 scored minutes against a rectal reference.
**Estimator (firmware 2.3)**: the published ECTemp filter plus a small learned correction (`analysis/correction.py`), wrapped in 6-strata conformal calibration. The same coefficients and tables the firmware and webapp use (`firmware/ember/conformal_table.h`).

---

## 1. Coverage: Kalman vs conformal

The Kalman filter carries its own variance, and reading it as a 90% range is the obvious thing to do. We measured how often that range contains the true value.

| Method | Promised | Measured coverage | Mean width |
|---|---|---|---|
| Kalman posterior (uncalibrated) | 90% | **34.3%** | 0.34 °C |
| Ember conformal (calibrated) | 90% | **89.2%** | 0.99 °C |

**Headline**: the Kalman "90%" range held 34% of the time. Ember's held 89%.

A range that promises 90% and delivers a third of that is worse than no range, because people act on it.

---

## 2. The learned correction: filter alone vs Ember 2.3

ECTemp uses one heart-rate curve for everyone and lags a fast rise. Ember adds a linear correction learned from PROSPIE. Its inputs are things the device already has: the filter's estimate and its 10-minute change, the 5-minute heart rate and its 10-minute change, and heart rate above the wearer's own resting rate (from BASELINE). The correction is capped at ±1.0 °C and is off until a baseline is captured; the device then shows the filter alone with the older, wider table.

| | Filter alone (2.2) | Ember 2.3 |
|---|---|---|
| Error (RMSE) | 0.41 °C | **0.32 °C** |
| Bias | −0.14 °C | −0.01 °C |
| 90% coverage | 89.7% | 89.2% |
| Mean ± | 0.67 °C | **0.49 °C** |
| Coverage at true ≥ 38.5 °C | 67% | 71% |
| Watch already on at true 38.5 °C (of 73) | 47 | **65** |
| Watch never fired | 5 | **0** |
| Act now never fired | 34 | **27** |
| Act now false alarms (of 55 trials that stayed under 38.5) | 13 | 13 |

- **Better for 31 of 37 people.** RMSE change −0.09 °C, 95% CI over people [−0.13, −0.05]. The largest loss for one person was +0.24 °C.
- **Not just a bias shift.** A constant offset alone also cuts misses but raises Act now false alarms from 13 to 22 (`learned_correction_results.txt`).
- **Cost**: specificity at 38.0 °C drops from 0.90 to 0.84, so Watch comes on more often when true core is just under 38.0.
- **Caveat**: the model was chosen among seven variants on this data, so these gains are slightly optimistic. On a second dataset it was never fitted to (HTT, section 7), it still lowered error for 54 of 65 people.

---

## 3. Coverage by true temperature

| True core | Minutes | Kalman | Ember |
|---|---|---|---|
| Under 37.5 °C | 3,949 | 36% | 89% |
| 37.5–38.0 °C | 4,435 | 40% | 96% |
| 38.0–38.5 °C (Watch) | 3,783 | 31% | 91% |
| 38.5 °C and up (Act now) | 1,874 | 24% | **71%** |

The Kalman range is worst where it matters most. Ember's range is calibrated overall but drops to 71% (67% before the correction) when true core is 38.5 °C or higher. The calibration is fitted by *estimated* temperature, and when core is high the estimate still lags and reads low, so the truth escapes the top of the range. This is the main limitation and we state it.

---

## 4. Alert timing: where were the alerts when true core reached 38.5 °C?

73 trials reached a true core of 38.5 °C. At the first minute it did:

| | Watch (estimate ≥ 38.0) | Act now (estimate ≥ 38.5) |
|---|---|---|
| Already on | **65 / 73 (89%)**, on for a median 12 min (IQR 5–19) | 17 / 73 (23%), on for a median 4 min |
| Came on later | 8, median 8 min late, worst 41 | 29, median 15 min late, worst 62 |
| Never came on | **0 / 73** | **27 / 73 (37%)** |

- In **27 / 73 trials (37%)** Watch came on and Act now never did.
- Neither alert stayed silent in any trial (5 / 73 before the correction).

**What this means**: Watch at 38.0 °C carries the safety load. It is on before true core reaches 38.5 in nearly nine trials out of ten, while Act now is late or silent in three out of four. A single 38.5 °C alarm would have missed over a third of these trials. The lag is smaller than before, but it is real.

---

## 5. Men vs women

| | Participants | Minutes | Bias | RMSE | 90% coverage |
|---|---|---|---|---|---|
| Women | 15 | 5,574 | +0.03 °C | 0.31 °C | 90% |
| Men | 20 | 7,963 | −0.03 °C | 0.33 °C | 88% |

**Bias difference (men − women)**: −0.06 °C, 95% CI [−0.16, +0.05] (bootstrap over participants, 5,000 resamples). The interval includes zero, so we found no clear difference; it is narrower than before the correction (±0.2 °C then), but it cannot rule out a small one.

**RMSE difference**: +0.02 °C, 95% CI [−0.05, +0.07].

**Why bias, not RMSE**: a systematic offset between groups moves bias a lot and RMSE barely at all, because RMSE is dominated by within-person error. When we tested the pipeline on a simulated group offset, bias caught it and RMSE missed it. An audit on RMSE alone would call a biased model fair.

**Context**: published validations of this algorithm are mostly male. One 251-subject study had 36 women and ran no sex analysis. We found no published sex-stratified analysis to compare against.

---

## 6. Rising vs steady (optional)

| Phase | Minutes | Kalman | Ember |
|---|---|---|---|
| Rising (true core up ≥ 0.2 °C in 5 min) | 1,253 | 31% | 86% |
| Steady (change under 0.1 °C in 5 min) | 6,416 | 33% | 90% |

Rising coverage is still a little under 90%, consistent with the remaining lag in section 4.

---

## 7. Other limits worth stating

- **Pulse sensors.** The filter and the correction only see heart rate, so the chest calibration carries over to any sensor that reports heart rate correctly. In PROSPIE, finger pulse-sensor trials scored about the same as chest trials from the same conditions (bias −0.12 vs −0.11 °C, coverage 85% vs 80%). The demo uses a low-cost pulse sensor; a product would use a validated heart-rate sensor.
- **Missing heart rate.** In the conditions where heart rate was missing in about 80% of minutes, the range held 80–85%, against 89% overall. Gaps in heart rate cost coverage, so the device must keep dropouts rare and widen the ± while it is coasting.
- **One training dataset.** All 37 people come from one lab, walking on a treadmill in a heat chamber. Running, lifting, outdoor work or older wearers may differ.
- **External test (HTT).** The shipped 2.3 calibration, read straight from `conformal_table.h` with nothing refitted, on 65 new people (32 women, 33 men; 2 h walking in heat and thermoneutral; ingestible-pill core; DOI 10.17632/g5sb382smp.1, CC BY 4.0). The 90% range covered **82.0%** (95% CI over people [77.5, 86.3]) against 89.2% on PROSPIE; the Kalman "90%" range covered 26.7%. RMSE 0.40 °C (filter alone 0.49), better for 54 of 65 people; coverage at true ≥ 38.5 °C 90%. The extra misses are over-reads late in long steady walks, where heart rate keeps drifting up while core levels off: too high 12.2% vs 3.9%, too low (the dangerous side) 5.8% vs 6.9%. Cost: Act now false alarms in 25 of 82 calm trials (PROSPIE 13 of 55). Part of the gap is the reference (pill vs rectal). Full output: `analysis/external_htt_results.txt`.
- **Resting heart rate** comes from the first 10 minutes of each trial here, and from the 5-minute BASELINE on the device.
- **Accuracy overall**: RMSE 0.32 °C, bias −0.01 °C, R² 0.67. Detecting true core ≥ 38.0 °C: sensitivity 75.2%, specificity 84.2%.
- Not a medical device.

---

## Key takeaways

1. The Kalman "90%" range covered **34%**. Ember's calibrated range covered **89%**.
2. The learned correction cut error from 0.41 to **0.32 °C** and the ± from 0.67 to **0.49 °C** on average, better for 31 of 37 people, with no increase in Act now false alarms.
3. When true core reached 38.5 °C, **Watch was already on in 89%** of trials (was 64%); **Act now never fired in 37%** (was 47%).
4. At true core ≥ 38.5 °C, Ember's coverage is **71%**, not 90%, because the estimate still lags. Watch is the safety threshold, not an extra.
5. No clear difference between men and women (bias −0.06 °C, CI [−0.16, +0.05]).
6. On 65 new people from a second dataset, with nothing refitted, the range covered **82%** (Kalman 27%). The extra misses are over-reads, not under-reads.

---

## Figures (`figures/`)

1. `judges_coverage.png`: Kalman vs conformal coverage by true temperature band
2. `judges_trial_interval.png`: one held-out trial, Ember vs the filter alone vs true core, with the ± band
3. `judges_lag.png`: where Watch and Act now stood when true core reached 38.5 °C, filter alone vs Ember 2.3
4. `judges_rmse.png`: error (RMSE), filter alone vs Ember 2.3 on PROSPIE and the HTT external test, and per person
5. `judges_range.png`: the range promised vs delivered at 50/80/90/95 %, and how wide the 90 % range is
6. `judges_early_warning.png`: trials lined up on the minute true core reached 38.5 °C, and how many minutes ahead Watch and Act now were on

---

## Data provenance

- **Dataset**: PROSPIE V3, Loughborough University, CC BY-NC 4.0 (DOI 10.17028/rd.lboro.26076577)
- **Participants**: 40 in the dataset; 37 have chest heart-rate data and are analysed. Participants 17 and 18 have conflicting sex codes, so the men vs women comparison uses 35 (15 women, 20 men).
- **Conditions**: 9 heat-stress protocols, one row per minute
- **Reference**: rectal temperature
- **Heart rate**: chest only (Equivital ECG, Polar strap); finger PPG excluded
- **Validation**: leave-one-subject-out, nested. No test participant's data is in the correction model or the calibration that scores them.

---

**Generated**: 2026-10-24
**Scripts**: `analysis/evaluate.py --prefix ember_chest`, `analysis/judges_results.py`, `analysis/external_test.py`, `analysis/make_judge_figures.py`, `analysis/export_firmware_table.py`
**Output**: `analysis/results_chest.txt`, `analysis/judges_results.txt`, `analysis/judges_results.json`, `analysis/external_htt_results.txt`
**Filter alone (2.2) numbers**: `python3 evaluate.py --no-correction`, or section 7 of `judges_results.txt`
