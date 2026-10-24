# Ember: dataset research and integration brief

Research checked 24 October 2026. This is a research and implementation plan; no model was trained or deployed, and the original project files were not changed.

**Recommended starting set:** retain PROSPIE for chest temperature and clothing microclimate; add the 65-person hot/thermoneutral exercise dataset for HR-to-core-temperature evaluation; add PAMAP2 for activity context. Use the CORE validation and Lôbo cooling datasets as separate challenge sets. WESAD can support an exploratory nonthermal stress-context model, subject to its non-commercial terms and Ember's available signals.

## What Ember actually needs

The supplied project uses Polar H10 heart rate, MAX30205 chest skin temperature, SHT40 under-shirt temperature and relative humidity, and MPU6050 motion. Its core estimate currently comes from an HR-based ECTemp filter, with a conformal interval lookup and heuristic flags. It does not measure core temperature directly.

Three distinct data tasks should remain separate:

| Task | Required evidence | Appropriate output |
|---|---|---|
| Estimate core temperature | Synchronized HR and independently measured core temperature; skin/microclimate when available | Estimated temperature and tested uncertainty |
| Interpret sensing context | Motion/activity labels, sensor quality, nonthermal stress examples, clothing and environment | Activity, missing-signal and out-of-distribution indicators |
| Understand the person and setting | Exertion/comfort reports, feedback on alerts, work/rest context and environmental exposure | Useful explanations and interaction design |

Temperature fields are not interchangeable. Preserve reference site and device: rectal, ingestible, skin, ambient, sensor-internal and model-estimated temperature must be separate variables. Humidity under clothing is different from outdoor humidity.

## Ranked sources

### 1. Hot versus thermoneutral exercise — best new core-model dataset

[Dataset, DOI 10.17632/g5sb382smp.1](https://data.mendeley.com/datasets/g5sb382smp/1) · [Study methods](https://pmc.ncbi.nlm.nih.gov/articles/PMC10464765/)

**Access:** downloadable XLSX, inspected. **License:** CC BY 4.0.

The study includes 65 people, 32 women and 33 men, walking in hot and thermoneutral conditions. The workbook contains participant-level temperature and HR rows against minutes 0–120, plus demographics, fitness, resting HR and session information. Early termination and missing entries mean not every trace is complete.

**Use:** additional HR/core training and subject-disjoint evaluation; compare performance across heat exposure and fitness. Keep both conditions for each person in the same split.

**Adapter:** unpivot the two treadmill sheets; pair each participant's temperature and HR rows; retain `Temp. Method` and missingness. The paper describes ingestible sensing, while the workbook contains TP, RP and blank method codes: confirm their meanings before combining references. Ambient temperature values appear Fahrenheit-scale; resolve units before conversion. No chest-skin, clothing-microclimate or IMU streams were established.

### 2. CORE wearable validation — additional measured-reference benchmark

[Dataset, DOI 10.6084/m9.figshare.29120024.v1](https://figshare.com/articles/dataset/Validity_of_the_CORE_Wearable_Sensor_During_Constant-load_Cycling_Exercise_in_the_Heat_xlsx/29120024) · [Study](https://pubmed.ncbi.nlm.nih.gov/40876129/)

**Access:** XLSX inspected. **License:** CC BY 4.0.

Twenty-four adults, 13 men and 11 women, cycled for 60 minutes in heat. Separate workbook blocks contain rectal reference temperature, CORE estimates, reference and CORE skin temperatures, HR, workload, perceived exertion, environment and participant information.

**Use:** test bias and transfer across people and sensor methods. The rectal column is the reference target; the commercial CORE estimate is a comparator.

**Limitation:** HR is populated in selected blocks, typically about 20 time bins per participant, rather than throughout the hour. It cannot directly replay a continuously driven HR filter without handling these gaps. Evaluate matched windows or an explicitly documented missing-data protocol. Unpivot by subject ID and time label, which mixes interval strings and numeric values. Local fat thickness is useful for research bias analysis, not a required user onboarding input.

### 3. PAMAP2 — activity context for the chest IMU

[UCI dataset, DOI 10.24432/C5NW2H](https://archive.ics.uci.edu/dataset/231/pamap2+physical+activity+monitoring)

**Access:** public DAT/ZIP files; documentation checked, full archive not downloaded. **License:** CC BY 4.0.

Nine participants performed labeled activities with chest, wrist and ankle IMUs plus an HR monitor. IMUs sampled at 100 Hz; HR is approximately 9 Hz.

**Use:** develop a chest-only work/rest or activity classifier for MPU6050 features. Restrict training inputs to sensors Ember actually has; using ankle/wrist channels would inflate expected performance.

**Adapter:** preserve timestamps and NaNs; resample chest acceleration to Ember's processing rate with anti-aliasing. Check units, gravity treatment, orientation and sensor placement using actual Ember recordings. PAMAP2's IMU temperature is not a measured core-temperature target and should not be assumed to be skin temperature.

### 4. Lôbo cooling study — challenging cooling/recovery and inclusion test

[Dataset, DOI 10.6084/m9.figshare.25939744.v1](https://figshare.com/articles/dataset/J_Therm_Biol_-_L_bo_et_al_2024_-_Raw_data/25939744)

**Access:** XLSX inspected. **License:** CC BY 4.0.

Nine male wheelchair rugby athletes with tetraplegia completed control, cooling-vest and water-spray trials. The workbook separates core temperature, HR, chest/other skin temperatures, comfort, sensation and exertion, with exercise and recovery sections.

**Use:** a distinct population and cooling challenge set; do not pool indiscriminately into a general-adult model. Resolve the core reference method from study documentation before quantitative evaluation. Exclude mean/SD columns from participant records and preserve phase boundaries and each variable's sampling times.

**Human-centered implication:** the study found improved thermal perception without a corresponding reduction in exercise hyperthermia. Feeling cooler and measuring cooler chest skin cannot be treated as proof of safe core temperature. Collect subjective feedback as a separate signal.

### 5. WESAD — exploratory nonthermal stress context

[UCI description](https://archive.ics.uci.edu/dataset/465/wesad+wearable+stress+and+affect+detection) · [Original download and terms](https://ubi29.informatik.uni-siegen.de/usi/data_wesad.html)

**Access:** public download; documentation and original terms checked, full recordings not downloaded. **Terms:** scientific, non-commercial use with credit; do not assume unrestricted commercial reuse.

Fifteen participants have synchronized chest/wrist physiological signals and neutral, stress and amusement labels, with self-reports.

**Use:** investigate HR elevations under nonthermal stress and test context-classification ideas. There is no independent core-temperature target for Ember calibration. These labels do not establish that a stressed person cannot simultaneously overheat.

**Feature constraint:** Ember's current BLE parser extracts HR, not RR intervals, HRV or raw ECG. Begin with a comparable HR/temperature/motion subset. A model trained on ECG-derived HRV, EDA or respiration needs additional acquisition support; those are not currently available inputs. Avoid displaying a categorical explanation such as “just stress.”

### 6. NASA POWER — outdoor exposure context

[Hourly API documentation](https://power.larc.nasa.gov/docs/services/api/temporal/hourly/) · [NASA POWER overview](https://power.larc.nasa.gov/global-community-summit/reports/power-2022-global-community-summit-summary-report.pdf)

**Access:** public meteorological/solar data service with JSON/CSV output; documentation checked, no data extract made. Follow NASA/source-product acknowledgment requirements.

**Use:** historical session context and environmental scenario coverage. Temperature, humidity and wind can help describe outdoor exposure. Request UTC explicitly and keep spatial resolution, source and data age.

Hourly gridded outdoor data cannot replace SHT40 under-shirt measurements, indoor conditions or immediate personal heat exposure. It is not a core-temperature label, a direct WBGT measurement or a guaranteed real-time alert feed. Location sharing should be optional where the product permits.

## Existing sources that need a more careful role

**PROSPIE remains the best match to Ember's complete temperature/microclimate feature set.** [Repository and license](https://doi.org/10.17028/rd.lboro.26076577.v1).

The inspected workbook has `Key`, `Conditions ` and `Data` sheets. It contains HR, rectal temperature, chest and insulated skin temperatures, front/back clothing temperature/RH, workload and perception fields. License: **CC BY-NC 4.0**.

My preliminary workbook count found **40 participant IDs**, not the 16 described in the project comments. There are 11,893 rows with numeric HR in 30–230 bpm and rectal temperature in 34–42 °C. This is only a screening count, not the final eligible cohort or a validation result.

Use the `Data` sheet, combine its two header rows and convert Excel time objects. The key defines `9999` as missing; red-font measurements can be interpolated using adjacent observations. Preserve those quality flags and avoid treating interpolated targets as independent measured truth. Decide exclusions before evaluation. The current generic loader defaults to the first sheet and retains only six columns, so it does not provide a reliable multimodal import.

**Firefighter dataset: useful context, not yet a continuous HR/core validation set.** [Repository](https://data.mendeley.com/datasets/7ghxcsd9sz/1). CC BY 4.0; 21 male firefighters in the described study.

The landing page describes continuous physiological recordings and multiple CSV files. The downloadable version I inspected instead exposes an XLSX with core-temperature trajectories and summary tables. HR appears as mean/max summaries; the skin/microclimate sheet contains summary statistics. I did not verify synchronized individual HR/skin/RH streams. Request those streams and a data dictionary before treating this as an external multimodal test. Do not broadcast a session-average HR across the core-temperature curve.

## Additional leads, with unresolved suitability

| Dataset | Potential use | What still needs verification |
|---|---|---|
| [Earbud core estimation, Zenodo 19835255](https://zenodo.org/records/19835255) | Independent wearable-method comparison in varied indoor temperatures | Repository metadata reports CC BY 4.0, but workbook download was blocked in this session. Confirm reference site, participants, HR and transferable inputs; Ember has no earbud temperature sensor. |
| [PPE thermophysiology/Fiala/PHS validation, Zenodo 19383727](https://zenodo.org/records/19383727) | Mechanistic context for protective clothing, rectal-temperature and sweat predictions | Landing page describes measured and predicted values in separate workbooks. License and full schema were not verified. Keep simulated predictions separate from measured labels; HR availability is unconfirmed. |

## Integration into the supplied stack

**First, build dataset-specific adapters.** Preserve the old six-column interface for the existing evaluator, but also write a richer canonical table. Suggested fields:

```text
dataset_id, dataset_version, participant_id, session_id, condition,
elapsed_s, timestamp_utc, reference_method, reference_device,
core_ref_c, hr_bpm, skin_chest_c, skin_insulated_c,
micro_temp_c, micro_rh_pct, ambient_temp_c, ambient_rh_pct,
activity_label, act_rms, step_hz,
thermal_sensation, thermal_comfort, perceived_exertion,
sensor_site, quality_flag, is_interpolated, missingness
```

Not every dataset contains every field. Leave unavailable values missing and retain provenance; never construct a false synchronized record by joining different people's measurements across datasets. Store raw IMU streams separately from derived features. Keep device-specific estimates, such as CORE, in clearly named comparator columns.

**Second, establish the real-data baseline.** Run the fixed ECTemp estimator on correctly aligned HR/core sessions. Account for missing observations and actual elapsed time. The offline evaluator currently assumes 60-second steps, while firmware operates on a different cadence. Match temporal behavior before exporting calibration. A five-second display refresh is not evidence of five-second label resolution.

**Third, test modest ML extensions.** My recommendation is a small residual regressor that learns the error of the baseline using available past/current HR trends, skin and microclimate features, with an HR-only fallback when those channels are absent. Compare a regularized linear model and a small tree model before considering larger sequence models. Train an activity classifier separately with chest-only PAMAP2 inputs. Public datasets cannot establish reliable automatic rejection of stress, caffeine or poor contact without appropriate labels.

**Fourth, evaluate and recalibrate.** Split by participant before generating windows; all sessions for one person stay together. Learned model fitting, uncertainty calibration and final testing must use distinct participants, with an outer held-out dataset where possible. Do not tune against the external test set. Preserve reference-method differences and report performance by dataset, reference method, temperature range and relevant participant groups. Use participant-level confidence intervals rather than treating correlated time samples as independent people.

Report temperature error and bias, interval coverage and width, missing-signal behavior, and the burden of proposed alerts. A small average error does not establish reliable detection at high temperatures. Conformal calibration on one population does not automatically guarantee coverage under a new clothing, sensing or population distribution.

**Fifth, export only evaluated behavior.** `firmware/conformal_table.h` explicitly identifies the shipped intervals as **synthetic calibration**. Its reported coverage describes the generator, not human performance. Replace that artifact only after a documented real-data evaluation. A new regression model also needs an actual inference implementation; changing a conformal lookup table does not deploy the regressor.

## Sensing and human-centered validation that public data cannot replace

Public recordings can improve models and reveal failure modes. They cannot calibrate the physical MAX30205/SHT40 assembly, PCB heat leakage, contact pressure or response lag in Ember's enclosure. Compare the assembled sensors with suitable reference instruments and record the exact contact/vent geometry. Collect ordinary wear sessions to check stable contact, motion, clothing effects and timestamps; controlled core-temperature validation requires an appropriate research setup.

Keep Ember's vapor-pressure calculation labeled as an **evaporative-potential proxy**. It is not a measured sweat rate or proof that the wearer is dissipating enough heat.

The human-centered follow-up dataset should include optional exertion/thermal-comfort check-ins, activity and clothing context, sensor discomfort, alert understanding and whether an alert was useful or disruptive. Evaluate donning, movement and readability with different body shapes and users. Retain uncertainty in the interface and avoid treating silence or a normal estimate as a guarantee of safety. This interaction research is distinct from physiological ground-truth collection.

## Practical hackathon order

1. Implement and inspect the hot/thermoneutral and PROSPIE adapters; keep raw-source attribution, versions and exclusions.
2. Demonstrate an offline real-data baseline with participant-disjoint evaluation and clearly distinguish it from live unvalidated estimates.
3. Add chest-based work/rest classification and a small, testable residual-model experiment if time permits.
4. Show separate CORE-window and cooling/recovery challenge results; keep the firefighter data in the context/retrieval backlog until aligned streams are available.
5. Use feedback from wearing the physical prototype to improve contact, comfort and alert presentation.

The strongest defensible story is a wearable that combines physiology with activity and microclimate context, measures its uncertainty, and makes its limits visible. The additional datasets enable testing that story; they do not by themselves establish a clinically validated heat-illness detector.
