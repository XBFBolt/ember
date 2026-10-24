/*
 * conformal_table.js - calibrated prediction intervals and the
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

export const CONF_SYNTHETIC = false;

export const CONF_LEVEL = 0.90;
export const CONF_MEASURED_COV = 0.8917;
/** Coverage when true core was 38.5 °C or more. */
export const CONF_MEASURED_COV_HOT = 0.7124;
export const CONF_RAW_MEASURED_COV = 0.8967;
/** What the Kalman filter's own "90%" range actually covered. Never displayed as a range. */
export const KALMAN_MEASURED_COV = 0.3433;
export const CONF_N_STRATA = 6;

// Corrected estimate: upper edge of each stratum, degrees C.
export const CONF_EDGES = [
  37.2991, 37.6630, 37.8906, 38.0790, 38.3063
];
// Corrected estimate: half-width of each stratum, degrees C.
export const CONF_HALF = [
  0.3903, 0.4055, 0.4935, 0.5220, 0.5421, 0.5986
];

// Filter alone (no baseline yet).
export const CONF_RAW_EDGES = [
  37.1090, 37.4371, 37.6990, 37.9584, 38.2786
];
export const CONF_RAW_HALF = [
  0.6845, 0.6023, 0.7733, 0.6710, 0.6013, 0.6373
];

function _half(edges, halves, ct) {
  let i = 0;
  while (i < halves.length - 1 && ct >= edges[i]) i++;
  return halves[i];
}

/** Half-width for a corrected estimate (baseline captured). */
export function conformalHalfWidth(ct_est) {
  return _half(CONF_EDGES, CONF_HALF, ct_est);
}

/** Half-width for the filter's own estimate (no baseline yet). */
export function conformalHalfWidthRaw(ct_est) {
  return _half(CONF_RAW_EDGES, CONF_RAW_HALF, ct_est);
}

// Learned correction (applied on the device; listed here for the app's
// "How sure is Ember?" sheet). Features: ct, ct_d10, hr5, hr5_d10, hr_rest.
export const CORR_INTERCEPT = 22.117185;
export const CORR_COEF = [-0.59388485, -0.94303399, 4.9245101e-05, -0.0054475906, 0.011452299];
export const CORR_MAX_C = 1.0;
