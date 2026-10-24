/*
 * conformal_table.h - calibrated prediction intervals and the
 * learned correction for Ember (firmware 2.3+)
 *
 * GENERATED FILE. Do not edit by hand; rerun export_firmware_table.py.
 * generated      2026-10-24
 * source data    Prospie dataset_open access V3.xlsx (HR: Equivital chest ECG, Polar chest strap)
 * calibration    37 subjects, 14041 samples
 * nominal level  90%
 * MEASURED coverage under leave-one-subject-out:
 *   shipped (corrected where possible)  89.2%
 *   at true core >= 38.5              71.2%
 *   uncorrected filter, CONF_RAW table  89.7%
 *   Kalman posterior "90%" (not shown)  34.3%
 *
 * The half-widths are quantiles of the absolute error measured against
 * a rectal reference, binned by estimated temperature. They are NOT
 * derived from the Kalman posterior variance, which published coverage
 * tests show is badly miscalibrated for this model.
 *
 * Correction: estimate = filter + clamp(CORR_INTERCEPT + CORR_COEF . x,
 * +/- CORR_MAX_C), x = (ct, ct_d10, hr5, hr5_d10, hr_rest), computed
 * once a minute as in analysis/correction.py. Off (CONF_RAW table) until
 * a baseline is captured and a heart rate has been seen.
 */

#ifndef CONFORMAL_TABLE_H
#define CONFORMAL_TABLE_H

#define CONF_LEVEL            0.90f
#define CONF_MEASURED_COV     0.8917f
#define CONF_RAW_MEASURED_COV 0.8967f
#define CONF_N_STRATA         6
#define CONF_RAW_N_STRATA     6

// Corrected estimate: upper edge of each stratum, degrees C.
static const float CONF_EDGES[CONF_N_STRATA - 1] = {
  37.2991f, 37.6630f, 37.8906f, 38.0790f, 38.3063f
};
// Corrected estimate: half-width of each stratum, degrees C.
static const float CONF_HALF[CONF_N_STRATA] = {
  0.3903f, 0.4055f, 0.4935f, 0.5220f, 0.5421f, 0.5986f
};

// Filter alone (no baseline yet): upper edge of each stratum, degrees C.
static const float CONF_RAW_EDGES[CONF_RAW_N_STRATA - 1] = {
  37.1090f, 37.4371f, 37.6990f, 37.9584f, 38.2786f
};
// Filter alone: half-width of each stratum, degrees C.
static const float CONF_RAW_HALF[CONF_RAW_N_STRATA] = {
  0.6845f, 0.6023f, 0.7733f, 0.6710f, 0.6013f, 0.6373f
};

// Half-width of the calibrated interval for a corrected estimate.
static inline float conformal_half_width(float ct_est) {
  int i = 0;
  while (i < CONF_N_STRATA - 1 && ct_est >= CONF_EDGES[i]) i++;
  return CONF_HALF[i];
}

// Half-width of the calibrated interval for the filter's own estimate.
static inline float conformal_half_width_raw(float ct_est) {
  int i = 0;
  while (i < CONF_RAW_N_STRATA - 1 && ct_est >= CONF_RAW_EDGES[i]) i++;
  return CONF_RAW_HALF[i];
}

// Learned correction. Features, in order: ct, ct_d10, hr5, hr5_d10, hr_rest
#define CORR_N_FEATURES 5
#define CORR_LAG_MIN    10
#define CORR_HR_WIN_MIN 5
#define CORR_MAX_C      1.0f
static const float CORR_INTERCEPT = 22.117185f;
static const float CORR_COEF[CORR_N_FEATURES] = {
  -0.59388485f, -0.94303399f, 4.9245101e-05f, -0.0054475906f, 0.011452299f
};

#endif // CONFORMAL_TABLE_H
