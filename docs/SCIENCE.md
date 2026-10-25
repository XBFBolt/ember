# The science behind Ember

Why Ember exists, what it adds to the published method, and where it falls
short. Full numbers are in `analysis/JUDGES_SUMMARY.md`.

---

## The problem

Heat stroke is defined by **core body temperature**: deep internal
temperature, not how hot someone feels or how warm their skin is. The only
accurate field measurements are an ingestible telemetry pill or a rectal
probe.

A skin thermometer is not a substitute. During hard work, skin temperature
can stay flat or even fall while the core climbs, depending on clothing,
airflow and conditions. It does not track the number that matters.

## The standard workaround

Heart rate rises as the core heats, because the body pumps blood to the
skin to shed heat. Buller et al. (2013) fitted that relationship and wrapped
it in an extended Kalman filter (ECTemp): roughly 78 bpm ≈ 37.0 °C,
120 bpm ≈ 38.0 °C, 152 bpm ≈ 39.0 °C.

A single reading tells you nothing: a heart rate of 150 can mean heat, or
stairs, or coffee. The filter accumulates evidence over time and leans on
the fact that core temperature changes slowly. One spike barely moves the
estimate; twenty minutes of sustained elevation walks it up.

Commercial heat-safety wearables use this approach today.

---

## What the literature says

### 1. It is less accurate than advertised

A 2026 systematic review screened 12,535 records, included 38 studies, and
**re-implemented 14 models under a common protocol**: parameters refit on
training folds, three-fold trial-based cross-validation, causal processing,
rectal reference.

| | Self-reported | Dataset 1 | Dataset 2 |
|---|---|---|---|
| RMSE | 0.30 °C | 0.4108 | **0.6563** |
| MAE | — | 0.2943 | 0.4746 |
| R² | 0.71 | 0.4686 | **−0.4010** |

A negative R² means the model did **worse than always predicting the mean
core temperature**. The authors conclude that no single approach
consistently outperformed the others across settings.

> Zhao, Li & Bergmann, *Building and Environment* 297 (2026)

### 2. It fails where it matters

Detecting core temperature ≥ 38.0 °C in that same benchmark:

| | Dataset 1 | Dataset 2 |
|---|---|---|
| Sensitivity | 0.7117 | **0.3328** |
| Specificity | 0.9171 | 0.8549 |

Two of every three high readings were missed on the second dataset.

A separate validation in **101 elite athletes** (49 men, 52 women) found a
bias of 0.15 °C and limits of agreement of ±0.45 °C overall, with
**sensitivity falling to 50–0 % above 39.0 °C**. The method is least
reliable when someone is in danger.

> de Korte et al., *Frontiers in Sports and Active Living* 4 (2022)

### 3. Its confidence interval is not a confidence interval

A Kalman filter produces a posterior variance, and it is tempting to show
it as a 90 % or 95 % range. Published coverage testing found ECTemp's
variance-based intervals covering a small fraction of their nominal rate;
the authors report a **12-fold improvement** in probabilistic accuracy from
replacing them with conformal intervals.

> Strickland et al., *Communications Engineering* (2025). Their code is not
> public.

We ran the same test on open data:

| | Promised | PROSPIE (37 people, LOSO) | HTT (65 new people) |
|---|---|---|---|
| Kalman posterior range | 90 % | **34.3 %** | **26.7 %** |
| Ember conformal range | 90 % | **89.2 %** | **82.0 %** |

A range that promises 90 % and delivers a third of that is worse than no
range, because people act on it.

---

## What Ember adds

**1. An open reference implementation.** We found no public implementation
of ECTemp in any language; benchmarking groups re-implement it from the
papers. `analysis/ectemp.py` is cited and checks its own coefficients, and
the firmware (`ember_core.h`) refuses to boot if its copy disagrees.

**2. A calibrated range.** Stratified split conformal prediction: measure
the real error distribution on people the model has not seen, and take the
quantile. No Gaussian assumption, and the errors are not Gaussian. The
table is stratified by estimated temperature, because the error grows with
it: one global quantile over-covers at rest and under-covers near the
limits. The device looks the ± up in `conformal_table.h`.

**3. A small learned correction.** ECTemp uses one heart-rate curve for
everyone and lags a fast rise. A linear correction on features the device
already has (the filter's estimate and its 10-minute change, the 5-minute
heart rate and its 10-minute change, heart rate above the wearer's own
resting rate) cuts PROSPIE error from 0.41 to 0.32 °C and the average ±
from 0.67 to 0.49 °C. It is capped at ±1.0 °C, off until a resting baseline
is captured, and the range is recalibrated around it on held-out people,
so it cannot break the coverage promise.

**4. A device that refuses.** Given a sensitivity of 0.33 in the regime
that matters, a better point estimate is not enough. Skin temperature and
motion check whether a high heart rate has a thermal explanation: a racing
heart while sitting still with cool skin is not heat. When the pulse is lost,
or both doubts fire, the app shows *Paused* with the reason instead of a
number. From 38.0 °C up it never refuses: it shows the number with *Low
confidence*.

**5. A sex-stratified check.** Published validations of this algorithm are
mostly male; the largest had 36 women of 251 and ran no sex analysis. On
PROSPIE (15 women, 20 men with consistent sex codes) the bias difference,
men minus women, was −0.06 °C (95 % CI −0.16 to +0.05). On HTT (32 women,
33 men) it was +0.12 °C (95 % CI −0.00 to +0.24). Neither interval excludes
zero, and neither rules out a small difference.

---

## Two methodological points

**Audit on bias, not RMSE.** In a positive control, we injected a simulated
+7 bpm offset into one group. Bias caught it, with a bootstrap interval
excluding zero. RMSE barely moved, because it is dominated by
within-person error. A fairness audit run on RMSE alone would call a biased
model fair.

**Calibrate on different people than you test on.** The conformal
calibration set must contain no one from the test set. Ember's evaluation
is nested leave-one-subject-out: no test participant's data is in the
correction model or the calibration that scores them.

---

## Data

Core temperature ground truth needs a pill or a probe, so public data is
scarce. The systematic review above benchmarked on two datasets.

- **PROSPIE V3** (Loughborough University), DOI `10.17028/rd.lboro.26076577`,
  CC BY-NC 4.0. 40 participants, 9 heat-stress protocols, one row per
  minute, rectal reference. Ember uses the 37 with chest heart rate
  (Equivital ECG or Polar strap). This is the training and calibration set.
- **HTT** (hot vs thermoneutral exercise), DOI `10.17632/g5sb382smp.1`,
  CC BY 4.0. 65 participants (32 women, 33 men), 2 h of walking in heat and
  thermoneutral conditions, ingestible-pill core, heart rate every minute.
  Used only as an external test; nothing is fitted on it.
- **Not used:** the firefighter heat-stress set (DOI `10.17632/7ghxcsd9sz.1`)
  has session-summary heart rate only. The Radboud athlete set (101 people,
  sex-balanced) is available on request. PhysioNet, WESAD and PPG-DaLiA have
  skin temperature only, which is not core temperature.

---

## Limits

- **No ground truth at the event.** Ingestible pills are not hackathon
  equipment. We validated the implementation and the calibration against
  published measurements; we did not validate physiology on our hardware.
- **The estimate lags.** At true core ≥ 38.5 °C the range held 71 %, not
  90 %, on PROSPIE, and Act now never fired in 27 of 73 trials that got
  there. Watch at 38.0 °C was already on in 65 of 73. Watch carries the
  safety load.
- **Long steady work over-reads.** On HTT, late in two-hour walks, heart rate
  kept drifting up while core levelled off. Ember read high: more false
  alarms, not more misses.
- **Calibrated on chest heart rate.** The demo uses a low-cost analog pulse
  sensor, and nothing cross-checks it. A product would use a validated
  heart-rate sensor such as an ECG strap.
- **Not an alarm.** This cannot tell an individual they are about to have
  heat stroke. It is a trend and triage signal.
- **Beta blockers lower heart rate**, so the estimate would read low in
  someone taking them. That is a miss in the dangerous direction, and the
  doubt checks do not catch it.
- **Licences.** PROSPIE is CC BY-NC, which blocks commercial use. ECTemp is
  patented (US 10,702,165 B2).

---

## Sources

- Zhao, Li & Bergmann, "Data-driven estimation of core body temperature
  during physical activity under heat exposure: a systematic review and
  benchmark", *Building and Environment* 297 (2026).
- de Korte et al., "A heart rate based algorithm to estimate core
  temperature responses in elite athletes exercising in the heat",
  *Frontiers in Sports and Active Living* 4:882254 (2022).
- Strickland et al., "Degrees of uncertainty: conformal deep learning for
  non-invasive core body temperature prediction in extreme environments",
  *Communications Engineering* (2025).
- Buller et al., "Estimation of human core temperature from sequential
  heart rate observations", *Physiological Measurement* 34:781–798 (2013).
- USARIEM Technical Report T17-08 (Looney et al. 2017) and US patent
  application 2014/0180027 A1: the filter constants, which agree.
