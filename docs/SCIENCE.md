# Why this project exists

Read this before the event. It is the difference between presenting a
reimplementation and presenting a contribution.

---

## The problem

Heat stroke is defined by **core body temperature** — deep internal
temperature, not how hot someone feels or how warm their skin is. The only
accurate field measurements are an ingestible telemetry pill or a rectal
probe.

You cannot substitute a skin thermometer. During hard work, skin
temperature **falls** as sweat evaporates while the core climbs. It moves
the wrong way. Showing that on one chart is the clearest single argument
for the whole project.

## The standard workaround

Heart rate rises as the core heats, because the body pumps blood to the
skin to shed heat. Buller et al. (2013) fitted that relationship and wrapped
it in an extended Kalman filter: roughly 78 bpm ≈ 37.0 °C, 120 bpm ≈
38.0 °C, 152 bpm ≈ 39.0 °C.

A single reading tells you nothing — your heart rate is 150 because of
heat, or stairs, or coffee. The filter works by accumulating evidence over
time and leaning on the fact that core temperature is physically slow. One
spike barely moves the estimate; twenty minutes of sustained elevation
walks it up.

This algorithm is deployed. Commercial heat-safety wearables run it today.

---

## The three findings this project is built on

### 1. It is much worse than advertised

A 2026 systematic review screened 12,535 records, included 38 studies, and
**re-implemented 14 models under a common protocol** — parameters refit on
training folds, three-fold trial-based cross-validation, causal processing,
rectal reference.

| | Self-reported | Dataset 1 | Dataset 2 |
|---|---|---|---|
| RMSE | 0.30 °C | 0.4108 | **0.6563** |
| MAE | — | 0.2943 | 0.4746 |
| R² | 0.71 | 0.4686 | **−0.4010** |

A negative R² means the model performs **worse than always predicting the
mean core temperature**. The authors conclude that no single approach
consistently outperformed others across settings.

> Zhao, Li & Bergmann, *Building and Environment* 297 (2026)

### 2. It fails where it matters

Detecting core temperature ≥ 38.0 °C in that same benchmark:

| | Dataset 1 | Dataset 2 |
|---|---|---|
| Sensitivity | 0.7117 | **0.3328** |
| Specificity | 0.9171 | 0.8549 |

Two of every three dangerous readings missed on the second dataset.

A separate validation in **101 elite athletes** (49 men, 52 women) found
bias 0.15 °C and limits of agreement ±0.45 °C overall — but **sensitivity
falling to 50–0% above 39.0 °C**. The device is least reliable precisely
when someone is in danger.

> de Korte et al., *Frontiers in Sports and Active Living* 4 (2022)

### 3. The confidence interval is not a confidence interval

A Kalman filter hands you a posterior variance, and it is extremely
tempting to display 1.96·√v as a 95% interval. Published coverage testing
found ECTemp's variance-derived intervals covering a small fraction of
their nominal rate; the authors report a **12-fold improvement** in
probabilistic accuracy from replacing them with conformal intervals.

Running the test ourselves on synthetic data, a nominal **90% interval
covered 26%**. Conformal intervals fitted on the same data covered
**89.5%**.

An interval that claims 90% and delivers 26% is worse than no interval,
because a user acts on it.

> Strickland et al., *Communications Engineering* (2025). Their code is
> proprietary — which is the gap we fill.

---

## What Ember adds

**1. An open reference implementation.** Nobody has released ECTemp, in any
language. USARIEM publishes a browser demo widget, not code; every
benchmarking group reimplements it from a PDF, and one reports emailing
USARIEM and getting no reply. `analysis/ectemp.py` is clean, cited, and
self-checking.

**2. A calibrated interval.** Stratified split conformal prediction: hold
out calibration subjects, measure the real error distribution, take the
quantile. No Gaussian assumption — and the errors are emphatically not
Gaussian. Stratified by predicted temperature, because the error grows with
it, so one global quantile over-covers at rest and under-covers in the
danger zone.

**3. A device that refuses.** Given sensitivity of 0.33 in the regime that
matters, the correct engineering response is not a better point estimate.
It is a device that declines. Three sensors vote on whether a high heart
rate even has a thermal explanation; when they disagree, the screen says
`CANNOT ESTIMATE` and why.

**4. The sex-stratified validation nobody has run.** The literature is
overwhelmingly male — the largest study had 36 women of 251 and performed
no sex analysis; several others had none at all. PROSPIE is 8 men and 8
women. Whatever the answer, including no difference, it is a result the
field does not have.

---

## Two methodological points we learned by running the code

**Audit on bias, not RMSE.** We built a positive control: inject a
simulated +7 bpm group offset and see whether the analysis finds it. Bias
caught it cleanly (−0.214 °C, bootstrap CI excluding zero). **RMSE missed
it entirely** (−0.008 °C, CI spanning zero) — a modest systematic offset
barely moves an error metric dominated by within-subject variance. A
fairness audit run on RMSE would have declared the model fair.

**Calibrate on different people than you test on.** The conformal
calibration set must contain no subject from the test set. At least one
published result computes per-subject calibration on its own test data and
reports the resulting coverage as if it were held out.

---

## The data landscape

Core temperature ground truth needs a pill or a probe, so public data is
scarce — the systematic review above benchmarked on **two** datasets.

**Download now:**
- **PROSPIE**, DOI `10.17028/rd.lboro.26076577` — 16 participants, 8M/8F,
  rectal reference, 1-minute sampling, heart rate, 11 skin sites, breathing
  rate, full environment (25–40 °C, 20–50% RH, two solar conditions), two
  clothing conditions. **CC BY-NC** — fine for this, blocks commercial use.
- **Firefighter circadian heat stress**, DOI `10.17632/7ghxcsd9sz.1` — 21
  men, e-Celsius ingestible capsule at 30 s, Polar H10 beat-to-beat heart
  rate, skin and under-PPE microclimate, live-fire exposures. CC BY. Use
  for cross-dataset transfer, not the sex analysis.

**Worth an email:** the Radboud dataset — 101 athletes, 49 men and 52
women, myTemp pill at 10 s, Polar V800 heart rate at 1 Hz. "Available from
the corresponding author on reasonable request." It is the only large
sex-balanced set that exists.

**Do not bother:** PhysioNet, Kaggle, WESAD, PPG-DaLiA. They have skin
temperature only, which is not core temperature and during exercise moves
the wrong way.

---

## Honest limits, which you should volunteer

- **No ground truth at the event.** Ingestible pills are not hackathon
  equipment. We validated the implementation and the calibration against
  published measurements; we did not validate physiology.
- **Not an alarm.** This cannot tell an individual they are about to have
  heat stroke, and nothing on the market can either. It is a trend and
  triage signal — "this person's strain is climbing faster than their crew
  and faster than their own baseline."
- **Beta blockers lower heart rate**, so the estimate would read low in
  someone on them. That is a miss in the dangerous direction and the
  confound detector does not catch it.
- **PROSPIE is CC BY-NC.** The Oxford-NIL reference repos carry no licence
  file, meaning all rights reserved — read and cite, do not copy. **ECTemp
  is patented** (US 10,702,165 B2): irrelevant for a hackathon, decisive
  for a company.

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
  application 2014/0180027 A1 — the filter constants, which agree.
