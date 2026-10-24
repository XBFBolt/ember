/*
 * ember_core.h - everything in Ember that is arithmetic, not hardware.
 *
 * Pure C++. No Arduino, no ESP-IDF. That is deliberate: every function in
 * this file is compiled and unit-tested on a laptop against synthetic
 * signals (tests/test_core.cpp) before it ever runs on the board. If a
 * number on the app is wrong, it is wrong here first, and here is where
 * it can be caught without a soldering iron.
 *
 * Contents
 *   1. ECTemp           the published core-temperature Kalman filter
 *   2. Thermistor       NTC resistance -> temperature, calibration, skin and air
 *   3. Periodicity      autocorrelation heart rate / cadence estimator
 *   4. Heart rate       one pulse sensor -> a heart rate, or none
 *   5. Confounds        flags and the OK / CAUTION / REFUSE decision
 *   6. Packet           the 20-byte BLE frame the app decodes
 *   7. Correction       the learned correction on top of ECTemp (2.3)
 *
 * Hardware v5 (firmware 2.2): one pulse sensor, two skin thermistors, one
 * air thermistor outside the strap, IMU. No SHT40, so no humidity.
 */

#ifndef EMBER_CORE_H
#define EMBER_CORE_H

#include <math.h>
#include <stdint.h>
#include <string.h>

#include "conformal_table.h"   // GENERATED: conformal tables + correction coefficients

namespace ember {

// =================================================================== 1
// ECTemp. Buller et al. 2013. Constants per USARIEM TR T17-08 and US
// patent application 2014/0180027 A1. DO NOT retype from a paper - one
// 2024 peer-reviewed paper prints an equation that peaks at 731 bpm.
// These match analysis/ectemp.py exactly, and the unit test checks that.

static const float B2 = -4.5714f;
static const float B1 = 384.4286f;
static const float B0 = -7887.1f;
static const float GAMMA_SQ_PER_MIN = 0.000484f;   // (0.022)^2
static const float SIGMA_SQ = 356.4544f;           // (18.88)^2 bpm^2
static const float CT_MIN = 35.0f, CT_MAX = 41.5f;

inline float hrFromCt(float c) { return B2 * c * c + B1 * c + B0; }
inline float dhrDct(float c)   { return 2.0f * B2 * c + B1; }

inline float ctFromHr(float hr) {
  float a = B2, b = B1, c = B0 - hr;
  float disc = b * b - 4.0f * a * c;
  if (disc < 0.0f) return NAN;
  return (-b + sqrtf(disc)) / (2.0f * a);
}

/*
 * One step per MINUTE, fed the mean heart rate of that minute.
 *
 * That is the cadence the model was published at and the cadence the
 * conformal table was calibrated at. Version 1 of this firmware stepped
 * every 5 seconds, which makes the filter over-confident relative to the
 * calibration - the interval on screen would have been describing a
 * different filter from the one running. Do not shorten the step.
 */
struct ECTemp {
  float ct = 37.1f;
  float v  = 0.0f;

  void update(float hr) {
    float ctPred = ct;
    float vPred  = v + GAMMA_SQ_PER_MIN;
    float slope  = dhrDct(ctPred);
    float denom  = slope * slope * vPred + SIGMA_SQ;
    float k      = (denom != 0.0f) ? (vPred * slope) / denom : 0.0f;
    ct = ctPred + k * (hr - hrFromCt(ctPred));
    v  = fmaxf(0.0f, (1.0f - k * slope) * vPred);
  }

  // No trustworthy heart rate this minute: predict only. The estimate
  // holds still and the variance grows - which is correct. Skipping the
  // step entirely, which is the common mistake, silently claims the
  // device knew something it did not.
  void coast() { v += GAMMA_SQ_PER_MIN; }

  float clamped() const { return fminf(fmaxf(ct, CT_MIN), CT_MAX); }

  void initFromRestingHr(float hrRest) {
    float c = ctFromHr(hrRest);
    if (isnan(c)) c = 37.1f;
    ct = fminf(fmaxf(c, 36.4f), 37.6f);
    v  = 0.0f;
  }
};

// Catches a transcription error in the coefficients. Returns true if sane.
inline bool coefficientsSane() {
  struct { float ct, lo, hi; } t[] = {
    {36.5f, 40, 75}, {37.0f, 65, 95}, {38.0f, 105, 135}, {39.0f, 135, 170}
  };
  for (auto &c : t) {
    float hr = hrFromCt(c.ct);
    if (hr < c.lo || hr > c.hi) return false;
  }
  return (-B1 / (2.0f * B2)) > 41.0f;     // the parabola must peak above 41 C
}

// =================================================================== 2
// Thermistor: Vishay NTCLE100E3103JB0.
//   R25 = 10 k, tolerance +/-5 % (the "J")   B25/85 = 3977 K +/-0.75 %
//   dissipation factor 7 mW/K
//
// Wiring: 3V3 -- 10 k fixed -- node -- NTC -- GND. Node goes to an ADC pin.
//
// Self-heating at skin temperature is about 0.26 mW / 7 mW/K = 0.04 C, so
// the divider is simply tied to 3V3; pulsing it would buy nothing.
//
// The +/-5 % on R25 is the problem worth solving: out of the box two
// thermistors can disagree by over 2 C. A resistance error is a constant
// error in 1/T, which over the 20-40 C range is almost exactly a constant
// temperature offset - so one calibration point fixes it. calScale is that
// correction, stored on the board. With no reference sensor on the v5
// hardware, CAL makes the beads agree with each other (ntcCalibrate).

struct NtcParams {
  float r25    = 10000.0f;
  float beta   = 3977.0f;
  float rFixed = 10000.0f;
  float vExcMv = 3300.0f;
};

// The ESP32-S3 ADC tops out near 3.1 V, so an open thermistor (node pulled
// to 3.3 V) reads ~3100 mV, not 3300. Anything above 3000 mV is > 100 k,
// colder than -13 C: treat it as disconnected rather than as a reading.
static const float NTC_SHORT_MV = 50.0f, NTC_OPEN_MV = 3000.0f;

inline float ntcResistance(float vNodeMv, const NtcParams &p) {
  if (isnan(vNodeMv) || vNodeMv <= NTC_SHORT_MV || vNodeMv >= NTC_OPEN_MV) return NAN;
  return p.rFixed * vNodeMv / (p.vExcMv - vNodeMv);
}

/*
 * A divider built upside down: 3V3 -> thermistor -> node -> fixed resistor
 * -> GND. Heat then RAISES the node voltage, and the maths above reads it as
 * cold. This returns the voltage the standard divider would show for the same
 * thermistor resistance (Vexc - V, exact), so everything downstream - ntcTempC,
 * CAL, the open/short checks - works unchanged.
 *
 * Open and short keep their meaning. An open thermistor on top leaves the node
 * at 0 V, which mirrors to the open end. A shorted one pulls the node to 3V3,
 * but the ADC stops near 3.1 V, so at or above NTC_OPEN_MV (about 85 C on a
 * standard divider) it is reported as shorted rather than mirrored to ~200 mV
 * and read as a hot bead.
 */
inline float ntcNodeMv(float measuredMv, bool thermistorOnTop, const NtcParams &p) {
  if (!thermistorOnTop || isnan(measuredMv)) return measuredMv;
  if (measuredMv >= NTC_OPEN_MV) return 0.0f;
  return p.vExcMv - measuredMv;
}

inline float ntcTempFromR(float r, const NtcParams &p) {
  if (isnan(r) || r <= 0.0f) return NAN;
  float invT = 1.0f / 298.15f + logf(r / p.r25) / p.beta;
  return 1.0f / invT - 273.15f;
}

inline float ntcRFromTemp(float tC, const NtcParams &p) {
  return p.r25 * expf(p.beta * (1.0f / (tC + 273.15f) - 1.0f / 298.15f));
}

// calScale = R_measured / R_true, found by CAL. 1.0 means uncalibrated.
inline float ntcTempC(float vNodeMv, float calScale, const NtcParams &p) {
  float r = ntcResistance(vNodeMv, p);
  if (isnan(r)) return NAN;
  return ntcTempFromR(r / calScale, p);
}

/*
 * CAL with no reference sensor.
 *
 * v2.1 calibrated the skin beads against the SHT40. The v5 hardware has no
 * SHT40, so CAL puts every bead at one temperature (device unpowered at room
 * temperature, the air bead lying beside it) and makes them agree. Each
 * bead's error is a resistance scale, so the shared reference is the
 * geometric mean of their resistances. That removes the bead-to-bead spread
 * and averages the tolerances: three +/-5 % beads leave about +/-0.6 C of
 * absolute error, against +/-1.1 C for one bead out of the box.
 *
 * keep[i]: bead i already has a trusted scale in k[i] (the skin beads of a
 * board calibrated against the SHT40 under v2.1). Kept beads are not
 * changed and set the reference on their own; the others are calibrated
 * against them.
 *
 * mv: each bead's averaged node voltage. k: in/out scales, written only on
 * CAL_OK. refC: out, the reference temperature.
 */
enum CalStatus : uint8_t { CAL_OK = 0, CAL_OPEN_OR_SHORT, CAL_BEADS_APART, CAL_NOT_ROOM };

static const int   NTC_BEADS = 3;              // skin A, skin B, air C
static const float CAL_DRIFT_C = 0.3f;         // max change of one bead over the 30 s CAL
// Two +/-5 % beads at one temperature read at most ~2.2 C apart. Further
// apart, they are not at the same temperature (one in a hand, on skin) or a
// divider is miswired.
static const float CAL_MAX_APART_C = 2.5f;
// The reference must look like a room. Outside this, the beads are not at
// room temperature or every fixed resistor is wrong - which agreement alone
// cannot catch (a 4.7k in place of each 10k reads about 8 C).
static const float CAL_ROOM_LO = 12.0f, CAL_ROOM_HI = 35.0f;

inline CalStatus ntcCalibrate(const float mv[], int n, const bool keep[], float k[],
                              const NtcParams &p, float *refC) {
  float r[NTC_BEADS], t[NTC_BEADS];
  if (n < 1 || n > NTC_BEADS) return CAL_OPEN_OR_SHORT;
  float tLo = 1e9f, tHi = -1e9f;
  int nKeep = 0;
  for (int i = 0; i < n; i++) {
    r[i] = ntcResistance(mv[i], p);
    if (isnan(r[i])) return CAL_OPEN_OR_SHORT;
    t[i] = ntcTempFromR(r[i] / (keep[i] ? k[i] : 1.0f), p);
    tLo = fminf(tLo, t[i]); tHi = fmaxf(tHi, t[i]);
    if (keep[i]) nKeep++;
  }
  if (tHi - tLo > CAL_MAX_APART_C) return CAL_BEADS_APART;

  float rRef, ref;
  if (nKeep > 0) {
    double s = 0;
    for (int i = 0; i < n; i++) if (keep[i]) s += t[i];
    ref = (float)(s / nKeep);
    rRef = ntcRFromTemp(ref, p);
  } else {
    double s = 0;
    for (int i = 0; i < n; i++) s += log(r[i]);
    rRef = (float)exp(s / n);
    ref = ntcTempFromR(rRef, p);
  }
  *refC = ref;
  if (ref < CAL_ROOM_LO || ref > CAL_ROOM_HI) return CAL_NOT_ROOM;
  for (int i = 0; i < n; i++) if (!keep[i]) k[i] = r[i] / rRef;
  return CAL_OK;
}

// Two beads, one skin temperature - or an honest statement that there
// isn't one.
enum SkinQuality : uint8_t { SKIN_NONE = 0, SKIN_SINGLE = 1, SKIN_AGREED = 2, SKIN_DISAGREE = 3 };

struct SkinResult { float tC; SkinQuality q; };

static const float SKIN_LO = 28.0f;    // below this a bead is not on skin
static const float SKIN_HI = 41.0f;
static const float SKIN_AGREE_C = 1.0f;

inline SkinResult fuseSkin(float a, float b) {
  bool okA = !isnan(a) && a >= SKIN_LO && a <= SKIN_HI;
  bool okB = !isnan(b) && b >= SKIN_LO && b <= SKIN_HI;
  if (okA && okB) {
    if (fabsf(a - b) <= SKIN_AGREE_C) return { 0.5f * (a + b), SKIN_AGREED };
    // Disagreeing beads: a bead losing contact drifts toward the air,
    // which is cooler than skin in almost every condition this device is
    // for. So the warmer one is the better guess - but it is flagged.
    return { fmaxf(a, b), SKIN_DISAGREE };
  }
  if (okA) return { a, SKIN_SINGLE };
  if (okB) return { b, SKIN_SINGLE };
  return { NAN, SKIN_NONE };
}

// The air bead (C) hangs outside the strap, in the air near the body. It is
// shown to the wearer and feeds no decision. Outside this range it is
// unplugged or broken (the open-circuit cut-off is near -13 C).
static const float AIR_LO = -10.0f, AIR_HI = 55.0f;

inline float airTemp(float tC) {
  return (!isnan(tC) && tC >= AIR_LO && tC <= AIR_HI) ? tC : NAN;
}

// =================================================================== 3
// Periodicity by normalised autocorrelation.
//
// Used twice: heart rate from the pulse sensor, and step cadence from the
// accelerometer. Autocorrelation rather than beat-by-beat peak picking for
// two reasons:
//   - it is robust to waveform shape and polarity, which vary between
//     pulse-sensor clones and between finger and chest
//   - the height of the autocorrelation peak is a SIGNAL QUALITY INDEX for
//     free: near 1 for a clean periodic pulse, near 0 for noise. That is
//     the number the device uses to decide whether to believe a channel.

struct Prefilter {
  // Two first-order high-passes IN CASCADE (12 dB/octave below the
  // corner), then a one-pole low-pass for the top end.
  //
  // Cascade matters. The obvious shortcut - subtract a twice-smoothed
  // baseline - is only a FIRST-order high-pass, and on the chest it lets
  // breathing through almost untouched. Breathing is a big, slow wave in
  // a chest PPG; leave it in and it swamps the autocorrelation at every
  // heart-rate lag. The unit test caught exactly that.
  float aHp, aLp;
  float b1 = NAN, b2 = 0.0f, lp = 0.0f;
  Prefilter(float hpAlpha, float lpAlpha) : aHp(hpAlpha), aLp(lpAlpha) {}
  float step(float x) {
    if (isnan(b1)) { b1 = x; b2 = 0.0f; }
    b1 += aHp * (x - b1);
    float h1 = x - b1;
    b2 += aHp * (h1 - b2);
    float h2 = h1 - b2;
    lp += aLp * (h2 - lp);
    return lp;
  }
};

// Corner frequencies, as one-pole alphas: a = 2*pi*fc/fs.
//   PPG, 100 Hz: high-pass 0.6 Hz (below 40 bpm), low-pass ~5 Hz
//   accel, 50 Hz: high-pass 0.5 Hz, low-pass ~6 Hz
static const float PPG_FS = 100.0f, ACC_FS = 50.0f;
static const float PPG_HP_A = 0.0377f, PPG_LP_A = 0.30f;
static const float ACC_HP_A = 0.0628f, ACC_LP_A = 0.55f;

struct Periodicity {
  float freqHz;     // NAN if no usable period
  float sqi;        // 0..1, height of the normalised autocorrelation peak
  float stdDev;     // amplitude of the windowed signal
};

/*
 * x: n samples at fs Hz, oldest first, already prefiltered (~zero mean).
 * Searches periods between 1/fMax and 1/fMin seconds.
 */
inline Periodicity periodicity(const float *x, int n, float fs, float fMin, float fMax) {
  Periodicity out = { NAN, 0.0f, 0.0f };
  int lMin = (int)floorf(fs / fMax);
  int lMax = (int)ceilf(fs / fMin);
  if (lMin < 2) lMin = 2;
  if (lMax > n / 2) lMax = n / 2;
  if (lMax - lMin < 4) return out;

  double mean = 0;
  for (int i = 0; i < n; i++) mean += x[i];
  mean /= n;
  double ss = 0;
  for (int i = 0; i < n; i++) { double d = x[i] - mean; ss += d * d; }
  out.stdDev = (float)sqrt(ss / n);
  if (out.stdDev < 1e-6f) return out;

  // r[L] for L in [lMin-1, lMax+1] so the peak search has neighbours.
  static float r[512];
  int base = lMin - 1;
  int count = (lMax + 1) - base + 1;
  if (count > 512) return out;
  for (int k = 0; k < count; k++) {
    int L = base + k;
    double sxy = 0, sxx = 0, syy = 0;
    for (int i = 0; i + L < n; i++) {
      double a = x[i] - mean, b = x[i + L] - mean;
      sxy += a * b; sxx += a * a; syy += b * b;
    }
    r[k] = (sxx > 0 && syy > 0) ? (float)(sxy / sqrt(sxx * syy)) : 0.0f;
  }

  // A periodic signal repeats at P, 2P, 3P... and all of those lags score
  // almost equally well, so "the highest peak" is a coin toss between the
  // true period and its multiples (the unit test caught it reporting a
  // 162/min bounce as 54/min). The true period is the SHORTEST lag that
  // scores nearly as well as the best one.
  float peakR = -2.0f;
  for (int k = 1; k < count - 1; k++)
    if (r[k] >= r[k - 1] && r[k] >= r[k + 1] && r[k] > peakR) peakR = r[k];
  if (peakR <= 0.0f) return out;
  int best = -1; float bestR = 0.0f;
  for (int k = 1; k < count - 1; k++) {
    if (r[k] >= r[k - 1] && r[k] >= r[k + 1] && r[k] >= 0.85f * peakR) {
      best = k; bestR = r[k]; break;
    }
  }
  if (best < 0) return out;

  // Parabolic interpolation for a sub-sample period.
  float y0 = r[best - 1], y1 = r[best], y2 = r[best + 1];
  float den = y0 - 2.0f * y1 + y2;
  float delta = (fabsf(den) > 1e-9f) ? 0.5f * (y0 - y2) / den : 0.0f;
  if (delta > 0.5f) delta = 0.5f;
  if (delta < -0.5f) delta = -0.5f;
  float lag = (float)(base + best) + delta;

  out.freqHz = fs / lag;
  out.sqi = bestR;
  return out;
}

// =================================================================== 4
// Heart rate: one pulse sensor.
//
// v2.1 had two pulse sensors and believed a heart rate only when they
// agreed. The v5 hardware has one, so nothing cross-checks it: a heart rate
// is believed on its own signal quality (the autocorrelation peak, at least
// PPG_SQI_MIN) and on the cadence check below. When either fails, there is
// no heart rate that second, and a minute short of good seconds makes the
// Kalman filter coast.

static const float PPG_SQI_MIN   = 0.50f;
static const float HR_MIN = 40.0f, HR_MAX = 200.0f;
static const float CADENCE_LOCK_BPM = 5.0f;
// A pulse sitting on the step cadence is believed only if it is within
// this of the last minute's heart rate. In steady running the heart drifts
// a few bpm a minute; an optical sensor that locks onto the bounce jumps by
// tens of bpm from one second to the next.
static const float CADENCE_JUMP_BPM = 15.0f;

// A minute needs this many good seconds to update the filter (otherwise it
// coasts) and to become the cadence check's reference.
static const int MIN_GOOD_SEC_PER_MINUTE = 30;
// How many lost minutes in a row the reference survives. Without this
// memory, one lost minute while the heart sits on the step rate leaves
// nothing to compare against, every later second at that rate is
// rejected, and the device stays stuck until the wearer changes pace.
static const int HR_REF_KEEP_MIN = 3;

/*
 * The heart rate the cadence check compares against: the mean heart rate
 * of the last GOOD minute, remembered through up to HR_REF_KEEP_MIN lost
 * minutes, then forgotten (NAN).
 */
struct HrReference {
  float hr = NAN;
  int lostMinutes = 0;
  // Call once per minute: the minute's mean HR, or NAN if it was lost.
  void endMinute(float minuteMean) {
    if (!isnan(minuteMean)) { hr = minuteMean; lostMinutes = 0; return; }
    if (!isnan(hr) && ++lostMinutes > HR_REF_KEEP_MIN) hr = NAN;
  }
};

// Frame byte 9. Values 2 (both sensors agree) and 3 (they disagree) were
// v2.1's two-sensor states; 2.2 never sends them.
enum HrQuality : uint8_t { HRQ_NONE = 0, HRQ_OK = 1 };

struct Channel {
  float hr;          // NAN if not usable
  float sqi;
  bool  cadenceLocked;
};

// The channel's own verdict: saturation, signal quality, plausible range.
// The cadence check needs the motion sensor, so it is a separate step.
inline Channel judgeChannel(const Periodicity &p, bool saturated) {
  Channel c = { NAN, p.sqi, false };
  if (saturated || isnan(p.freqHz) || p.sqi < PPG_SQI_MIN) return c;
  float hr = 60.0f * p.freqHz;
  if (hr < HR_MIN || hr > HR_MAX) return c;
  c.hr = hr;
  return c;
}

/*
 * Cadence check.
 *
 * Motion artifact lands at step frequency, so a "pulse" at 60 x steps-per-
 * second may be the sensor bouncing. It may also be the heart: at 160-180
 * steps/min a runner's pulse genuinely sits there. Matching cadence alone
 * is therefore not enough to reject it. A pulse at cadence is rejected when
 * it jumped there: more than CADENCE_JUMP_BPM from the last minute's heart
 * rate, or there is no last minute to compare against.
 *
 * With one sensor this is the only motion defence (v2.1 also rejected a
 * channel that disagreed with the other one). A heart rate that climbs
 * steadily onto the step rate and a bounce that does the same look alike,
 * so pick demo work whose step rate is far from the heart rate.
 *
 * prevHr: HrReference::hr - the last good minute's heart rate, NAN if
 * there has been no good minute recently.
 */
inline void cadenceCheck(Channel &c, float stepHz, bool moving, float prevHr) {
  if (!moving || isnan(stepHz) || isnan(c.hr)) return;
  if (fabsf(c.hr - 60.0f * stepHz) > CADENCE_LOCK_BPM) return;     // not at cadence
  bool jumped = isnan(prevHr) || fabsf(c.hr - prevHr) > CADENCE_JUMP_BPM;
  if (jumped) { c.hr = NAN; c.cadenceLocked = true; }
}

struct HeartRate { float hr; HrQuality q; };

inline HeartRate heartRateOf(const Channel &c) {
  if (isnan(c.hr)) return { NAN, HRQ_NONE };
  return { c.hr, HRQ_OK };
}

// =================================================================== 5
// Confounds. The estimator cannot tell WHY a heart rate is high. These
// ask whether the rest of the body agrees that heat is the explanation.

enum State : uint8_t { STATE_OK = 0, STATE_CAUTION = 1, STATE_REFUSE = 2 };

// Reserved bits are never set. 0x0002 and 0x0080 needed the SHT40's
// humidity; they stay free for an air-temperature version once its
// thresholds are tested. 0x0010, 0x0100 and 0x0200: do not reuse.
enum Flag : uint16_t {
  F_MOTIONLESS_TACHY = 0x0001,  // high HR while still: caffeine, anxiety, illness
  F_RESERVED_0002    = 0x0002,  // was NO_THERMAL_LOAD (v2.1, needed humidity)
  F_COOL_SKIN        = 0x0004,
  F_STALE_HR         = 0x0008,  // no trustworthy heart rate for 2+ minutes
  F_RESERVED_0010    = 0x0010,  // was WIDE_INTERVAL in v2.0
  F_NO_BASELINE      = 0x0020,
  F_CADENCE_LOCK     = 0x0040,  // the pulse was rejected as motion artifact
  F_RESERVED_0080    = 0x0080,  // was EVAP_FAILING (v2.1, needed humidity)
  F_RESERVED_0100    = 0x0100,  // was PPG_DISAGREE (v2.1, two pulse sensors)
  F_RESERVED_0200    = 0x0200,  // was PPG_SINGLE   (v2.1, two pulse sensors)
  F_SKIN_DISAGREE    = 0x0400,  // the two skin thermistors disagree      (info only)
  F_SKIN_SINGLE      = 0x0800,  // one skin thermistor off skin           (info only)
  F_NO_AIR           = 0x1000,  // air thermistor not reading             (info only)
  F_LOW_BATT         = 0x2000,  //                                        (info only)
  F_NOT_CALIBRATED   = 0x4000,  // skin thermistors never calibrated      (info only)
  F_BASELINE_RUNNING = 0x8000,
};

// Flags that, on their own, make the state CAUTION. They all cast doubt on
// the heart rate the estimate is built from, or on its starting point.
//
// The info-only flags (skin, air, calibration, battery) describe the
// AUXILIARY sensors. Those feed the confound checks or the display, not the
// estimate, so they never lower confidence in the number by themselves -
// otherwise an uncalibrated bead would hold the display in Low confidence
// for the whole session.
static const uint16_t CAUTION_FLAGS = F_NO_BASELINE | F_BASELINE_RUNNING | F_CADENCE_LOCK;

static const float ACT_STILL_G       = 0.035f; // below: essentially motionless
static const float ACT_MOVING_G      = 0.05f;  // above: cadence check applies

// The app's Watch threshold. At or above it the device never withholds the
// number: the estimate lags true core, so a wearer this warm is the one
// who most needs to see it. The worst state up here is CAUTION.
static const float CT_WATCH_C = 38.0f;

// Heart rate stays high for minutes after work stops: that is the body
// shedding heat, not caffeine. "High HR while still" waits this long after
// the wearer was last moving.
static const int TACHY_GRACE_SEC = 600;

struct Inputs {
  float ctEst;             // current core estimate (clamped), NAN if none
  float hr;                // this second's heart rate, NAN if none
  bool  cadenceLockSeen;   // the pulse was rejected for cadence this second
  int   coastMinutes;      // consecutive minutes without a filter update
  bool  everUpdated;
  float skinC;  SkinQuality skinQ;
  bool  haveAir;           // the air thermistor is reading
  bool  haveImu;           // motion sensor found at boot
  float activityG;         // smoothed (reads 0 with no motion sensor)
  int   secSinceMoving;    // seconds since activityG was last >= ACT_MOVING_G
  bool  baselineValid;
  bool  baselineRunning;
  float restHr;
  bool  calibrated;
  bool  lowBatt;
};

inline uint16_t confoundFlags(const Inputs &in) {
  uint16_t f = 0;
  if (!in.everUpdated || in.coastMinutes >= 2) f |= F_STALE_HR;
  if (!in.baselineValid) f |= F_NO_BASELINE;
  if (in.baselineRunning) f |= F_BASELINE_RUNNING;
  if (in.cadenceLockSeen) f |= F_CADENCE_LOCK;
  if (in.skinQ == SKIN_DISAGREE) f |= F_SKIN_DISAGREE;
  if (in.skinQ == SKIN_SINGLE)   f |= F_SKIN_SINGLE;
  if (!in.haveAir) f |= F_NO_AIR;
  if (!in.calibrated) f |= F_NOT_CALIBRATED;
  if (in.lowBatt) f |= F_LOW_BATT;

  // Not in the grace period after moving, and not at or above Watch: up
  // there, wrongly blaming caffeine is the dangerous mistake. Not without a
  // motion sensor either: activity then reads 0, and a whole workout would
  // look like sitting still. (No flag bit is free to report the missing
  // IMU; ID and SCAN show it on the serial port.)
  bool inGrace = in.secSinceMoving < TACHY_GRACE_SEC;
  bool hot = in.ctEst >= CT_WATCH_C;              // false for NAN
  if (in.haveImu && in.baselineValid && !isnan(in.hr) &&
      in.hr > in.restHr + 25.0f && in.activityG < ACT_STILL_G &&
      !inGrace && !hot)
    f |= F_MOTIONLESS_TACHY;

  // The skin doubt needs calibrated beads. Out of the box a +/-5 % bead can
  // read more than 1 C low, which in a cool room raises the doubt against a
  // good estimate. Until CAL, skin raises no doubt.
  if (in.calibrated && !isnan(in.skinC) && in.skinC < 31.0f) f |= F_COOL_SKIN;
  return f;
}

/*
 * ctEst: the estimate the frame will carry (NAN if none). Below Watch the
 * device refuses on a stale heart rate or two doubts. At or above Watch it
 * never refuses: the worst state is CAUTION, and the frame keeps the
 * number and the +/- (inflated while coasting, see coastInflation).
 *
 * There are two doubts (v2.1 had three, plus a humidity signal that
 * cancelled one), so refusing on doubts takes both: a high heart rate
 * while still AND cool skin.
 */
inline State stateFromFlags(uint16_t f, float ctEst) {
  int doubts = 0;
  if (f & F_MOTIONLESS_TACHY) doubts++;
  if (f & F_COOL_SKIN)        doubts++;

  State s = STATE_OK;
  if ((f & F_STALE_HR) || doubts >= 2)          s = STATE_REFUSE;
  else if (doubts == 1 || (f & CAUTION_FLAGS))  s = STATE_CAUTION;

  if (s == STATE_REFUSE && ctEst >= CT_WATCH_C) s = STATE_CAUTION;
  return s;
}

// Whether the frame carries the number and +/-. The device withholds them
// itself on REFUSE, so the app has no stale value to fall back on.
inline bool showsNumber(State st, bool everUpdated) {
  return everUpdated && st != STATE_REFUSE;
}

// BASELINE restarts the filter from a resting value (37.6 C at most) and
// withholds the number until the next update. At or above Watch that would
// hide a hot wearer's number, so the device refuses to start or finish a
// baseline there. Checked when the command arrives and again at the end.
inline bool baselineAllowed(float ctEst, bool everUpdated) {
  return !(everUpdated && ctEst >= CT_WATCH_C);
}

// The reason to show beside the state. Flags that can cause REFUSE or
// CAUTION come first, so an info-only flag never masks the real reason.
inline const char *flagReason(uint16_t f) {
  if (f & F_STALE_HR)         return "no trustworthy heart rate";
  if (f & F_MOTIONLESS_TACHY) return "high HR while still";
  if (f & F_COOL_SKIN)        return "skin not warm";
  if (f & F_CADENCE_LOCK)     return "pulse matches step cadence";
  if (f & F_BASELINE_RUNNING) return "baseline in progress";
  if (f & F_NO_BASELINE)      return "no baseline yet";
  if (f & F_SKIN_DISAGREE)    return "skin sensors disagree";
  if (f & F_NOT_CALIBRATED)   return "thermistors not calibrated";
  if (f & F_NO_AIR)           return "no air temperature sensor";
  return "";
}

// While coasting, the true uncertainty grows by the model's own process
// noise. Add it to the calibrated half-width (90 % -> 1.645 sigma).
inline float coastInflation(int coastMinutes) {
  if (coastMinutes <= 0) return 0.0f;
  return 1.645f * sqrtf(coastMinutes * GAMMA_SQ_PER_MIN);
}

// LiPo open-circuit-ish voltage to percent, light load.
inline uint8_t lipoPercent(float v) {
  static const float V[] = {3.30f, 3.60f, 3.70f, 3.75f, 3.80f, 3.85f, 3.95f, 4.05f, 4.15f, 4.20f};
  static const float P[] = {0,     5,     12,    25,    40,    55,    70,    85,    95,    100};
  if (isnan(v) || v <= V[0]) return 0;
  for (int i = 1; i < 10; i++) {
    if (v <= V[i]) return (uint8_t)(P[i-1] + (P[i] - P[i-1]) * (v - V[i-1]) / (V[i] - V[i-1]) + 0.5f);
  }
  return 100;
}

// =================================================================== 6
// The BLE frame. 20 bytes, little-endian - fits the default BLE MTU, so
// the app works without negotiating anything. Layout is documented in
// docs/APP_INTERFACE.md and decoded by tools/ember_ble.py.
//
// The layout is v2.1's. Bytes 14, 15, 18 and 19 carried humidity,
// evaporative headroom and the two per-sensor heart rates; they are
// reserved now and always sent as their "not available" values.

static const int PACKET_LEN = 20;

struct Frame {
  uint16_t seq;
  float ctC, halfC;          // NAN when refusing / unknown
  State state;
  bool baselineRunning, logging;
  uint16_t flags;
  float hr; HrQuality hrQ;
  float skinC, airC;
  uint8_t battPct;           // 255 = no battery (USB power)
  float activityG;
};

inline int16_t centi(float v) {
  if (isnan(v)) return INT16_MIN;
  float c = roundf(v * 100.0f);
  if (c > 32767.0f) c = 32767.0f;
  if (c < -32767.0f) c = -32767.0f;
  return (int16_t)c;
}
inline uint8_t u8(float v, float scale, uint8_t none) {
  if (isnan(v)) return none;
  float s = roundf(v * scale);
  if (s < 0) s = 0;
  if (s > 254) s = 254;
  return (uint8_t)s;
}
inline void put16(uint8_t *b, int o, uint16_t v) { b[o] = v & 0xFF; b[o + 1] = v >> 8; }

inline void encodeFrame(const Frame &f, uint8_t out[PACKET_LEN]) {
  put16(out, 0, f.seq);
  put16(out, 2, (uint16_t)centi(f.ctC));
  out[4] = u8(f.halfC, 50.0f, 255);                       // 0.02 C units
  out[5] = (uint8_t)f.state | (f.baselineRunning ? 0x10 : 0) | (f.logging ? 0x20 : 0);
  put16(out, 6, f.flags);
  out[8] = u8(f.hr, 1.0f, 0);
  out[9] = (uint8_t)f.hrQ;
  put16(out, 10, (uint16_t)centi(f.skinC));
  put16(out, 12, (uint16_t)centi(f.airC));
  out[14] = 255;                                          // reserved (was humidity)
  out[15] = 0x80;                                         // reserved (was headroom), -128
  out[16] = f.battPct;
  out[17] = u8(f.activityG, 500.0f, 255);                 // 2 milli-g units
  out[18] = 0;                                            // reserved (was HR sensor A)
  out[19] = 0;                                            // reserved (was HR sensor B)
}

// =================================================================== 7
// Learned correction (firmware 2.3).
//
// ECTemp uses one heart-rate curve for everyone and lags a fast rise. A
// small linear model, fitted on PROSPIE against a rectal reference, adds a
// correction to its estimate:
//
//   estimate = filter + clamp(CORR_INTERCEPT + CORR_COEF . x, +/- CORR_MAX_C)
//   x = (ct, ct_d10, hr5, hr5_d10, hr_rest)
//
//   ct       the filter's estimate this minute
//   ct_d10   its change over the last 10 minutes (oldest kept, if fewer)
//   hr5      mean of the last 5 minutes' heart rates, carried over gaps
//   hr5_d10  its change over the last 10 minutes (oldest kept, if fewer)
//   hr_rest  hr5 minus the resting heart rate from BASELINE
//
// Mirrors analysis/correction.py minute for minute; the golden vectors in
// tests/correction_vectors.h check that. The coefficients and both tables
// are GENERATED into conformal_table.h - never edit them by hand.
//
// OFF until a baseline is captured and a heart rate has been seen. Off,
// the device shows the filter's own estimate with the CONF_RAW table:
// exactly what firmware 2.2 shipped.

struct Lagged {
  static const int N = CORR_LAG_MIN + 1;
  float v[N];
  int n = 0, head = 0;
  void reset() { n = 0; head = 0; }
  void push(float x) { v[head] = x; head = (head + 1) % N; if (n < N) n++; }
  // The value CORR_LAG_MIN pushes ago, or the oldest kept if fewer.
  float lagged() const {
    int k = n - 1;
    if (k > CORR_LAG_MIN) k = CORR_LAG_MIN;
    return v[(head - 1 - k + 2 * N) % N];
  }
};

struct Correction {
  float hrWin[CORR_HR_WIN_MIN];
  int hrWinN = 0, hrWinHead = 0;
  float hr5 = NAN;
  Lagged ctHist, hr5Hist;
  float corr = 0.0f;
  bool on = false;

  // A new filter start (BASELINE succeeded): forget the history.
  void reset() {
    hrWinN = 0; hrWinHead = 0; hr5 = NAN;
    ctHist.reset(); hr5Hist.reset();
    corr = 0.0f; on = false;
  }

  // Once a minute, after the filter's step. minuteHr: that minute's mean
  // heart rate, NAN if the filter coasted. ct: the filter's clamped
  // estimate. restHr: NAN without a baseline.
  void step(float minuteHr, float ct, float restHr) {
    hrWin[hrWinHead] = minuteHr;
    hrWinHead = (hrWinHead + 1) % CORR_HR_WIN_MIN;
    if (hrWinN < CORR_HR_WIN_MIN) hrWinN++;
    float s = 0.0f; int k = 0;
    for (int i = 0; i < hrWinN; i++) if (!isnan(hrWin[i])) { s += hrWin[i]; k++; }
    if (k > 0) hr5 = s / k;                   // otherwise carried over

    ctHist.push(ct);
    on = false; corr = 0.0f;
    if (isnan(hr5)) return;
    hr5Hist.push(hr5);
    if (isnan(restHr)) return;

    float x[CORR_N_FEATURES] = {
      ct, ct - ctHist.lagged(), hr5, hr5 - hr5Hist.lagged(), hr5 - restHr
    };
    float c = CORR_INTERCEPT;
    for (int i = 0; i < CORR_N_FEATURES; i++) c += CORR_COEF[i] * x[i];
    corr = fminf(fmaxf(c, -CORR_MAX_C), CORR_MAX_C);
    on = true;
  }

  // The estimate to show, from the filter's clamped estimate.
  float estimate(float ct) const {
    return on ? fminf(fmaxf(ct + corr, CT_MIN), CT_MAX) : ct;
  }
};

// The +/- for the estimate on screen: the table that matches how it was
// made, widened while coasting.
inline float calibratedHalf(float est, bool corrected, int coastMinutes) {
  return (corrected ? conformal_half_width(est) : conformal_half_width_raw(est))
         + coastInflation(coastMinutes);
}

} // namespace ember

#endif // EMBER_CORE_H
