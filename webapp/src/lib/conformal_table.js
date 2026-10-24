/*
 * conformal_table.js - calibrated prediction intervals for Ember
 *
 * GENERATED FILE. Do not edit by hand; rerun export_firmware_table.py.
 * generated      2026-10-24
 * source data    Prospie dataset_open access V3.xlsx (HR: Equivital chest ECG, Polar chest strap)
 * calibration    37 subjects, 14041 samples
 * nominal level  90%
 * MEASURED coverage under leave-one-subject-out: 89.7%
 *
 * The half-widths below are quantiles of the absolute error measured
 * against a rectal reference, binned by predicted temperature. They
 * are NOT derived from the Kalman posterior variance, which published
 * coverage tests show is badly miscalibrated for this model.
 */

export const CONF_SYNTHETIC = false;

export const CONF_LEVEL = 0.90;
export const CONF_MEASURED_COV = 0.8967;
export const CONF_N_STRATA = 6;

// Upper edge of each stratum, in predicted degrees C.
export const CONF_EDGES = [
  37.1090, 37.4371, 37.6990, 37.9584, 38.2786
];

// Interval half-width for each stratum, in degrees C.
export const CONF_HALF = [
  0.6845, 0.6023, 0.7733, 0.6710, 0.6013, 0.6373
];

/**
 * Half-width of the calibrated interval at this estimate.
 * @param {number} ct_est - Estimated core temperature in degrees C
 * @returns {number} Half-width in degrees C
 */
export function conformalHalfWidth(ct_est) {
  let i = 0;
  while (i < CONF_N_STRATA - 1 && ct_est >= CONF_EDGES[i]) {
    i++;
  }
  return CONF_HALF[i];
}
