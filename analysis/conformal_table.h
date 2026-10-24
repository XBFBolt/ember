/*
 * conformal_table.h - calibrated prediction intervals for Ember
 *
 * GENERATED FILE. Do not edit by hand; rerun export_firmware_table.py.
 * generated      2026-10-23
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

#ifndef CONFORMAL_TABLE_H
#define CONFORMAL_TABLE_H

#define CONF_LEVEL        0.90f
#define CONF_MEASURED_COV 0.8967f
#define CONF_N_STRATA     6
#define REFUSE_ABOVE_C    1.50f  // half-width above which the device declines to show a number

// Upper edge of each stratum, in predicted degrees C.
static const float CONF_EDGES[CONF_N_STRATA - 1] = {
  37.1090f, 37.4371f, 37.6990f, 37.9584f, 38.2786f
};

// Interval half-width for each stratum, in degrees C.
static const float CONF_HALF[CONF_N_STRATA] = {
  0.6845f, 0.6023f, 0.7733f, 0.6710f, 0.6013f, 0.6373f
};

// Half-width of the calibrated interval at this estimate.
static inline float conformal_half_width(float ct_est) {
  int i = 0;
  while (i < CONF_N_STRATA - 1 && ct_est >= CONF_EDGES[i]) i++;
  return CONF_HALF[i];
}

// True when the device should refuse rather than display a number.
static inline bool conformal_should_refuse(float ct_est) {
  return conformal_half_width(ct_est) > REFUSE_ABOVE_C;
}

#endif // CONFORMAL_TABLE_H
