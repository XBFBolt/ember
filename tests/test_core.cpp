// Host unit tests for ember_core.h.
//
//   g++ -std=c++17 -O2 -Wall -Wextra -I../firmware/ember test_core.cpp -o test_core && ./test_core
//
// Every function the device uses to turn voltages into a decision is
// exercised here against signals where the right answer is known.

#include "ember_core.h"
#include "conformal_table.h"
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <random>
#include <vector>

using namespace ember;

static int fails = 0, passes = 0;
#define CHECK(cond, ...) do { if (cond) { passes++; } else { fails++; \
  printf("  FAIL %s:%d  ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

// ---------------------------------------------------------- synthetic PPG
// A pulse: sharp systolic peak plus a smaller, later dicrotic wave, with
// beat-to-beat variability, breathing wander and white noise - then
// pushed through the same prefilter the firmware uses.
static std::vector<float> synthPpg(float hrBpm, float seconds, float noise,
                                   float artHz, float artAmp, unsigned seed,
                                   float breath = 200.f) {
  const float fs = 100.0f;
  std::mt19937 rng(seed);
  std::normal_distribution<float> n01(0.f, 1.f);
  int n = (int)(seconds * fs);
  std::vector<float> raw(n, 0.f);
  float t = 0.f;
  std::vector<float> beats;
  while (t < seconds + 2) {
    beats.push_back(t);
    float ibi = 60.f / hrBpm * (1.f + 0.03f * n01(rng));
    t += ibi;
  }
  for (int i = 0; i < n; i++) {
    float ti = i / fs, v = 0.f;
    for (float b : beats) {
      float d = ti - b;
      if (d < -0.5f || d > 1.0f) continue;
      v += 120.f * expf(-d * d / (2 * 0.045f * 0.045f));
      float d2 = d - 0.28f;
      v += 45.f * expf(-d2 * d2 / (2 * 0.07f * 0.07f));
    }
    v += breath * sinf(2 * (float)M_PI * 0.25f * ti);          // breathing
    v += artAmp * sinf(2 * (float)M_PI * artHz * ti);          // motion
    v += noise * n01(rng);
    raw[i] = 2048.f + v;
  }
  Prefilter pf(PPG_HP_A, PPG_LP_A);
  std::vector<float> out(n);
  for (int i = 0; i < n; i++) out[i] = pf.step(raw[i]);
  return out;
}

static Periodicity lastWindow(const std::vector<float> &x, float fs, float seconds,
                              float fMin, float fMax) {
  int n = (int)(fs * seconds);
  return periodicity(x.data() + (x.size() - n), n, fs, fMin, fMax);
}

int main() {
  printf("ember_core tests\n");

  // ------------------------------------------------------------ ECTemp
  CHECK(coefficientsSane(), "coefficient self-check");
  {
    const float HR[] = {72,74,80,95,110,122,130,136,140,143,145,147,NAN,NAN,148,150,151,152,120,100,90};
    const float CT[] = {36.777387f,36.778164f,36.780475f,36.787332f,36.800433f,36.820165f,36.845800f,36.876798f,36.912228f,36.951403f,36.993487f,37.038185f,37.038185f,37.038185f,37.092381f,37.147623f,37.202880f,37.257994f,37.284056f,37.291848f,37.290400f};
    const float V[]  = {0.00048248f,0.00096043f,0.00143098f,0.00189142f,0.00233937f,0.00277283f,0.00319026f,0.00359056f,0.00397307f,0.00433753f,0.00468401f,0.00501285f,0.00549685f,0.00598085f,0.00622796f,0.00646225f,0.00668485f,0.00689677f,0.00709895f,0.00728890f,0.00746519f};
    ECTemp f; f.initFromRestingHr(68.0f);
    CHECK(fabsf(f.ct - 36.777126f) < 1e-4f, "CT0 from resting HR: %f", f.ct);
    float worst = 0;
    for (int i = 0; i < 21; i++) {
      if (isnan(HR[i])) f.coast(); else f.update(HR[i]);
      worst = fmaxf(worst, fabsf(f.clamped() - CT[i]));
      CHECK(fabsf(f.v - V[i]) < 2e-6f, "variance step %d: %f vs %f", i, f.v, V[i]);
    }
    CHECK(worst < 2e-4f, "firmware filter matches analysis/ectemp.py (worst %.6f C)", worst);
    printf("  ECTemp matches the Python reference, worst error %.6f C\n", worst);
  }

  // -------------------------------------------------------- thermistor
  {
    NtcParams p;
    for (float t : {20.f, 25.f, 33.f, 37.f, 40.f}) {
      float r = ntcRFromTemp(t, p);
      float v = p.vExcMv * r / (p.rFixed + r);
      float back = ntcTempC(v, 1.0f, p);
      CHECK(fabsf(back - t) < 0.01f, "NTC round trip %.1f -> %.3f", t, back);
    }
    CHECK(fabsf(ntcRFromTemp(25.f, p) - 10000.f) < 1.f, "R25");

    // A +5 % thermistor (the datasheet worst case) on the same bench.
    float trueT = 23.0f, skinT = 33.5f;
    auto vFor = [&](float t, float scale) {
      float r = ntcRFromTemp(t, p) * scale;
      return p.vExcMv * r / (p.rFixed + r);
    };
    float rawErr = ntcTempC(vFor(skinT, 1.05f), 1.0f, p) - skinT;
    // One-point CAL at room temperature against a known reference:
    float rMeas = ntcResistance(vFor(trueT, 1.05f), p);
    float k = rMeas / ntcRFromTemp(trueT, p);
    float corrErr = ntcTempC(vFor(skinT, 1.05f), k, p) - skinT;
    CHECK(fabsf(rawErr) > 1.0f, "uncalibrated +5%% bead is >1 C off (%.2f)", rawErr);
    CHECK(fabsf(corrErr) < 0.02f, "one-point CAL at 23 C fixes it at 33.5 C (%.3f)", corrErr);
    printf("  +5%% thermistor: %.2f C error raw, %.3f C after one-point CAL\n", rawErr, corrErr);

    CHECK(isnan(ntcTempC(0.0f, 1.0f, p)), "shorted thermistor reads NAN");
    CHECK(isnan(ntcTempC(3299.0f, 1.0f, p)), "open thermistor reads NAN");
    CHECK(isnan(ntcTempC(3100.0f, 1.0f, p)), "open thermistor at the ADC ceiling reads NAN");
    CHECK(!isnan(ntcTempC(2025.0f, 1.0f, p)), "15 C still reads");

    // A divider built upside down (3V3 -> thermistor -> node -> 10k -> GND).
    auto vTop = [&](float t) {
      float r = ntcRFromTemp(t, p);
      return p.vExcMv * p.rFixed / (r + p.rFixed);
    };
    for (float t : {15.f, 21.f, 25.f, 33.f, 40.f}) {
      float back = ntcTempC(ntcNodeMv(vTop(t), true, p), 1.0f, p);
      CHECK(fabsf(back - t) < 0.01f, "upside-down divider round trip %.1f -> %.3f", t, back);
    }
    CHECK(ntcTempC(vTop(21.f), 1.0f, p) > 28.0f,
          "upside-down divider read the standard way: 21 C shows as ~29 C");
    CHECK(ntcTempC(ntcNodeMv(vTop(45.f), true, p), 1.0f, p) >
          ntcTempC(ntcNodeMv(vTop(25.f), true, p), 1.0f, p), "upside-down: heat reads warmer");
    CHECK(ntcNodeMv(1800.0f, false, p) == 1800.0f, "standard divider passes through");
    CHECK(isnan(ntcNodeMv(NAN, true, p)), "no reading stays NAN");
    CHECK(isnan(ntcTempC(ntcNodeMv(0.0f, true, p), 1.0f, p)), "upside-down open thermistor reads NAN");
    CHECK(isnan(ntcTempC(ntcNodeMv(3100.0f, true, p), 1.0f, p)),
          "upside-down shorted thermistor (ADC ceiling) reads NAN, not hot");
  }

  // ---------------------------------------- CAL with no reference sensor
  {
    NtcParams p;
    auto vFor = [&](float t, float scale) {
      float r = ntcRFromTemp(t, p) * scale;
      return p.vExcMv * r / (p.rFixed + r);
    };
    const float room = 23.0f, skinT = 33.5f;
    const float scale[3] = {1.05f, 0.96f, 1.02f};       // within the +/-5 % tolerance
    float mv[3], k[3] = {1, 1, 1}, ref = NAN;
    bool none[3] = {false, false, false};
    for (int i = 0; i < 3; i++) mv[i] = vFor(room, scale[i]);

    float rawSpread = 0;
    for (int i = 0; i < 3; i++) for (int j = 0; j < 3; j++)
      rawSpread = fmaxf(rawSpread, ntcTempC(vFor(skinT, scale[i]), 1.0f, p) - ntcTempC(vFor(skinT, scale[j]), 1.0f, p));
    CHECK(ntcCalibrate(mv, 3, none, k, p, &ref) == CAL_OK, "three beads at one room temperature: CAL ok");
    float lo = 1e9f, hi = -1e9f, worst = 0;
    for (int i = 0; i < 3; i++) {
      float t = ntcTempC(vFor(skinT, scale[i]), k[i], p);
      lo = fminf(lo, t); hi = fmaxf(hi, t); worst = fmaxf(worst, fabsf(t - skinT));
    }
    printf("  shared CAL: beads %.2f C apart raw, %.3f C after; worst absolute error %.2f C\n",
           rawSpread, hi - lo, worst);
    CHECK(rawSpread > 1.5f, "the beads disagree out of the box (%.2f C)", rawSpread);
    CHECK(hi - lo < 0.02f, "after CAL they agree at skin temperature (%.3f C)", hi - lo);
    CHECK(worst < 0.6f, "absolute error is the averaged tolerance, %.2f C", worst);
    CHECK(fabsf(ref - room) < 0.6f, "shared reference %.2f C near the true %.1f", ref, room);

    // A board calibrated against the SHT40 under v2.1: A and B keep their
    // scales, and the air bead is calibrated against them.
    float kk[3] = {scale[0], scale[1], 1.0f};
    bool keepSkin[3] = {true, true, false};
    CHECK(ntcCalibrate(mv, 3, keepSkin, kk, p, &ref) == CAL_OK, "keep A/B, calibrate C: ok");
    CHECK(kk[0] == scale[0] && kk[1] == scale[1], "kept beads untouched");
    CHECK(fabsf(ref - room) < 0.01f, "reference is the kept beads' %.2f C", ref);
    CHECK(fabsf(ntcTempC(vFor(skinT, scale[2]), kk[2], p) - skinT) < 0.02f,
          "air bead now as accurate as the kept skin beads");

    // One bead in a hand: refused, nothing written.
    float mvHand[3] = {mv[0], mv[1], vFor(30.0f, scale[2])};
    float k2[3] = {1, 1, 1};
    CHECK(ntcCalibrate(mvHand, 3, none, k2, p, &ref) == CAL_BEADS_APART && k2[2] == 1.0f,
          "beads at different temperatures -> refused, scales unchanged");
    // A bead unplugged.
    float mvOpen[3] = {mv[0], 3200.0f, mv[2]};
    CHECK(ntcCalibrate(mvOpen, 3, none, k2, p, &ref) == CAL_OPEN_OR_SHORT, "open bead -> refused");
    // Every divider built with 4.7k instead of 10k: the beads agree, on ~8 C.
    NtcParams wrong = p; wrong.rFixed = 4700.0f;
    float mvWrong[3];
    for (int i = 0; i < 3; i++) {
      float r = ntcRFromTemp(room, p) * scale[i];
      mvWrong[i] = p.vExcMv * r / (wrong.rFixed + r);
    }
    CHECK(ntcCalibrate(mvWrong, 3, none, k2, p, &ref) == CAL_NOT_ROOM && k2[0] == 1.0f,
          "all fixed resistors wrong -> 'not room temperature' (%.1f C), unchanged", ref);
  }

  // -------------------------------------------------------- air bead
  {
    CHECK(airTemp(22.4f) == 22.4f && airTemp(-5.0f) == -5.0f && airTemp(45.0f) == 45.0f, "air in range");
    CHECK(isnan(airTemp(NAN)) && isnan(airTemp(-20.0f)) && isnan(airTemp(60.0f)), "air out of range -> none");
  }

  // -------------------------------------------------------- skin fusion
  {
    SkinResult s = fuseSkin(33.2f, 33.6f);
    CHECK(s.q == SKIN_AGREED && fabsf(s.tC - 33.4f) < 1e-4f, "skin agree");
    s = fuseSkin(33.2f, 30.0f);
    CHECK(s.q == SKIN_DISAGREE && fabsf(s.tC - 33.2f) < 1e-4f, "skin disagree takes the warmer");
    s = fuseSkin(33.2f, 24.0f);
    CHECK(s.q == SKIN_SINGLE && fabsf(s.tC - 33.2f) < 1e-4f, "bead off skin -> single");
    s = fuseSkin(NAN, 22.0f);
    CHECK(s.q == SKIN_NONE && isnan(s.tC), "no skin");
  }

  // ------------------------------------------------- heart rate by ACF
  {
    printf("  heart rate from synthetic PPG (8 s window), still subject:\n");
    for (float hr : {45.f, 60.f, 75.f, 100.f, 130.f, 170.f, 195.f}) {
      auto x = synthPpg(hr, 20, 15.f, 0, 0, (unsigned)hr, 40.f);
      Periodicity p = lastWindow(x, 100.f, 8.f, HR_MIN / 60.f, HR_MAX / 60.f);
      float est = 60.f * p.freqHz;
      printf("    true %5.1f  est %6.1f  sqi %.2f\n", hr, est, p.sqi);
      CHECK(fabsf(est - hr) <= 2.5f, "HR %.0f estimated %.1f", hr, est);
      CHECK(p.sqi >= 0.6f, "clean pulse SQI %.2f", p.sqi);
    }

    // The property that matters: across a grid of heart rates, noise
    // levels and heavy breathing, the channel is either RIGHT or it
    // REJECTS itself. Rejected is fine - the filter coasts through it.
    // Confidently wrong is the failure mode.
    {
      int tot = 0, acc = 0, wrong = 0;
      for (float hr = 45; hr <= 190; hr += 5)
        for (float noise : {15.f, 60.f})
          for (float br : {0.f, 200.f})
            for (unsigned sd = 0; sd < 6; sd++) {
              auto x = synthPpg(hr, 18, noise, 0, 0,
                                sd * 977 + (unsigned)(hr * 3) + (unsigned)noise, br);
              Periodicity p = lastWindow(x, 100.f, 8.f, HR_MIN / 60.f, HR_MAX / 60.f);
              Channel c = judgeChannel(p, false);
              tot++;
              if (!isnan(c.hr)) { acc++; if (fabsf(c.hr - hr) > 5.f) wrong++; }
            }
      printf("    grid of %d windows: %d accepted (%.0f%%), %d confidently wrong\n",
             tot, acc, 100.0 * acc / tot, wrong);
      CHECK(wrong == 0, "no confidently wrong heart rates (%d)", wrong);
      CHECK(acc > tot * 0.7, "accepts most windows (%d/%d)", acc, tot);
    }

    // Noise only: the SQI must say so.
    {
      std::mt19937 rng(7); std::normal_distribution<float> n01(0, 1);
      Prefilter pf(PPG_HP_A, PPG_LP_A);
      std::vector<float> x(2000);
      for (auto &v : x) v = pf.step(2048 + 40 * n01(rng));
      Periodicity p = lastWindow(x, 100.f, 8.f, HR_MIN / 60.f, HR_MAX / 60.f);
      Channel c = judgeChannel(p, false);
      printf("    noise only: sqi %.2f -> %s\n", p.sqi, isnan(c.hr) ? "rejected" : "ACCEPTED");
      CHECK(isnan(c.hr), "noise-only channel rejected (sqi %.2f)", p.sqi);
    }

    // Buried pulse, heavy noise: still found, with a lower SQI.
    {
      auto x = synthPpg(88, 20, 60.f, 0, 0, 3);
      Periodicity p = lastWindow(x, 100.f, 8.f, HR_MIN / 60.f, HR_MAX / 60.f);
      printf("    noisy 88 bpm: est %.1f sqi %.2f\n", 60 * p.freqHz, p.sqi);
      CHECK(fabsf(60 * p.freqHz - 88) < 3 || p.sqi < PPG_SQI_MIN,
            "noisy pulse either right or rejected, never confidently wrong");
    }
  }

  // ------------------------------------- motion artifact and cadence lock
  {
    // Running: true heart 110 bpm, chest bouncing at 2.7 steps/s, and the
    // bounce is three times bigger than the pulse in the optical signal.
    float stepHz = 2.7f;
    auto ppg = synthPpg(110, 20, 15.f, stepHz, 300.f, 11);
    Periodicity p = lastWindow(ppg, 100.f, 8.f, HR_MIN / 60.f, HR_MAX / 60.f);

    // Accelerometer at 50 Hz, the same bounce.
    Prefilter pa(ACC_HP_A, ACC_LP_A);
    std::mt19937 rng(5); std::normal_distribution<float> n01(0, 1);
    std::vector<float> acc(1000);
    for (int i = 0; i < 1000; i++) {
      float t = i / 50.f;
      acc[i] = pa.step(1.0f + 0.35f * fabsf(sinf((float)M_PI * stepHz * t)) + 0.02f * n01(rng));
    }
    Periodicity cad = lastWindow(acc, 50.f, 8.f, 0.8f, 3.5f);
    printf("  running: optical says %.1f bpm (sqi %.2f), cadence %.2f Hz = %.1f /min (sqi %.2f)\n",
           60 * p.freqHz, p.sqi, cad.freqHz, 60 * cad.freqHz, cad.sqi);
    CHECK(fabsf(cad.freqHz - stepHz) < 0.1f, "cadence found: %.2f Hz", cad.freqHz);
    CHECK(fabsf(60 * p.freqHz - 60 * stepHz) < 4.f, "optical channel locked onto the bounce");

    // A minute ago the heart rate was 110: the channel JUMPED to cadence.
    Channel c = judgeChannel(p, false);
    CHECK(!isnan(c.hr), "the bounce passes the channel's own quality checks (sqi %.2f)", c.sqi);
    cadenceCheck(c, cad.freqHz, true, 110.f);
    CHECK(c.cadenceLocked && isnan(c.hr), "jump to cadence (110 last minute) is rejected");
    CHECK(heartRateOf(c).q == HRQ_NONE && isnan(heartRateOf(c).hr), "rejected -> no heart rate this second");

    // No last minute to compare with: bounce and heart look the same. Reject.
    c = judgeChannel(p, false);
    cadenceCheck(c, cad.freqHz, true, NAN);
    CHECK(c.cadenceLocked && isnan(c.hr), "at cadence with no previous minute -> rejected");

    // Not moving: the check does not apply.
    c = judgeChannel(p, false);
    cadenceCheck(c, cad.freqHz, false, 110.f);
    CHECK(!c.cadenceLocked && !isnan(c.hr), "not moving -> no cadence check");

    // No cadence found: nothing to compare with, the check stands down.
    c = judgeChannel(p, false);
    cadenceCheck(c, NAN, true, 110.f);
    CHECK(!c.cadenceLocked && !isnan(c.hr), "no step rate -> no cadence check");
  }

  // ----------------------------- hard running: the heart IS at cadence
  {
    // 162 steps/min, and the heart has climbed to 162 as well, with a
    // little bounce on top. v2.0 threw this away for matching cadence.
    float stepHz = 2.7f;
    auto ppg = synthPpg(162, 20, 15.f, stepHz, 60.f, 21);
    Channel a = judgeChannel(lastWindow(ppg, 100.f, 8.f, HR_MIN / 60.f, HR_MAX / 60.f), false);
    printf("  hard running, heart at cadence: %.1f  cadence %.1f /min\n", a.hr, 60 * stepHz);
    CHECK(fabsf(a.hr - 60 * stepHz) <= CADENCE_LOCK_BPM, "the channel sits on the cadence (%.1f)", a.hr);
    Channel a2 = a;
    cadenceCheck(a, stepHz, true, 158.f);
    HeartRate h = heartRateOf(a);
    CHECK(!a.cadenceLocked, "real running HR at cadence, no jump -> kept");
    CHECK(h.q == HRQ_OK && fabsf(h.hr - 162.f) < 4.f, "heart rate %.1f", h.hr);

    // The same reading after a minute at 120: a 40 bpm jump is what a
    // bounce looks like, so it is rejected.
    cadenceCheck(a2, stepHz, true, 120.f);
    CHECK(heartRateOf(a2).q == HRQ_NONE, "same reading after a 40 bpm jump -> rejected");

    // The edge of the jump window, exactly.
    Channel x = { 160, .9f, false };
    cadenceCheck(x, stepHz, true, 160.f - CADENCE_JUMP_BPM);
    CHECK(!isnan(x.hr), "15 bpm from last minute -> kept");
    x = { 160, .9f, false };
    cadenceCheck(x, stepHz, true, 160.f - CADENCE_JUMP_BPM - 1.f);
    CHECK(isnan(x.hr) && x.cadenceLocked, "16 bpm from last minute -> rejected");

    // A channel NOT at cadence is never touched, whatever last minute was.
    x = { 120, .9f, false };
    cadenceCheck(x, stepHz, true, NAN);
    CHECK(x.hr == 120 && !x.cadenceLocked, "off-cadence channel untouched");
  }

  // ------------- one lost minute must not leave the cadence check stuck
  {
    // Heart and steps both at 162. One minute of the firmware's loop:
    // noisySeconds of junk first, then clean seconds at the heart rate.
    // Returns the minute's mean HR, or NAN if the minute was lost.
    auto minute = [](HrReference &ref, int noisySeconds) {
      double sum = 0; int n = 0;
      for (int s = 0; s < 60; s++) {
        Channel c = { NAN, .2f, false };
        if (s >= noisySeconds) c = { 162.f, .9f, false };
        cadenceCheck(c, 2.7f, true, ref.hr);
        HeartRate h = heartRateOf(c);
        if (!isnan(h.hr)) { sum += h.hr; n++; }
      }
      float mean = n >= MIN_GOOD_SEC_PER_MINUTE ? (float)(sum / n) : NAN;
      ref.endMinute(mean);
      return mean;
    };

    HrReference ref;
    ref.endMinute(158.f);                          // climbing into the run
    CHECK(!isnan(minute(ref, 0)), "minute 1 on cadence, no jump -> kept");
    CHECK(isnan(minute(ref, 40)), "minute 2: 40 s of noise -> lost");
    CHECK(!isnan(minute(ref, 0)), "minute 3 recovers: the last good minute is remembered");
    CHECK(!isnan(minute(ref, 0)), "minute 4 still fine");

    // What v2.1 did before the fix: no memory, so after the lost minute
    // every second at cadence is rejected and the device stays stuck.
    HrReference noMemory;
    noMemory.endMinute(162.f);
    noMemory.endMinute(NAN); noMemory.hr = NAN;    // forget immediately, as before
    CHECK(isnan(minute(noMemory, 0)) && isnan(minute(noMemory, 0)),
          "without the memory a clean minute at cadence is lost, and the next");

    // Remembered through HR_REF_KEEP_MIN lost minutes, then forgotten.
    HrReference r;
    r.endMinute(150.f);
    for (int i = 0; i < HR_REF_KEEP_MIN; i++) r.endMinute(NAN);
    CHECK(r.hr == 150.f, "reference survives %d lost minutes", HR_REF_KEEP_MIN);
    r.endMinute(NAN);
    CHECK(isnan(r.hr), "and is forgotten after %d", HR_REF_KEEP_MIN + 1);
    r.endMinute(NAN);
    CHECK(isnan(r.hr) && r.lostMinutes == HR_REF_KEEP_MIN + 1, "stays forgotten, counter stops");
    r.endMinute(140.f);
    CHECK(r.hr == 140.f && r.lostMinutes == 0, "a good minute resets it");
  }

  // ------------------------------------------------- one-sensor heart rate
  {
    Channel good = {100, .9f, false}, none = {NAN, .2f, false};
    CHECK(heartRateOf(good).q == HRQ_OK && heartRateOf(good).hr == 100.f, "good channel -> HR, quality OK");
    CHECK(heartRateOf(none).q == HRQ_NONE && isnan(heartRateOf(none).hr), "rejected channel -> none");
  }

  // -------------------------------------------------- states and flags
  {
    Inputs base{};
    base.ctEst = 37.6f;
    base.hr = 120; base.cadenceLockSeen = false;
    base.coastMinutes = 0; base.everUpdated = true;
    base.skinC = 34.5f; base.skinQ = SKIN_AGREED;
    base.haveAir = true; base.haveImu = true; base.activityG = 0.2f; base.secSinceMoving = 0;
    base.baselineValid = true;
    base.baselineRunning = false; base.restHr = 65; base.calibrated = true;
    base.lowBatt = false;
    auto stateOf = [](const Inputs &i) { return stateFromFlags(confoundFlags(i), i.ctEst); };

    Inputs in = base;
    CHECK(stateOf(in) == STATE_OK, "working in heat, one good pulse sensor -> OK");

    // An hour at a desk in a cool room, heart rate up from coffee, skin cool.
    Inputs desk = base;
    desk.activityG = 0.01f; desk.secSinceMoving = 3600; desk.skinC = 30.5f;
    uint16_t f = confoundFlags(desk);
    CHECK((f & F_MOTIONLESS_TACHY) && (f & F_COOL_SKIN), "coffee at a desk, cool skin: two doubts");
    CHECK(stateOf(desk) == STATE_REFUSE, "coffee at a desk, cool skin -> REFUSE (%s)", flagReason(f));

    // The same desk with skin at 32: one doubt. (v2.1 also had "no thermal
    // load" from dry air here, which took it to REFUSE; that needed humidity.)
    in = desk; in.skinC = 32.0f;
    CHECK(stateOf(in) == STATE_CAUTION, "coffee at a desk, skin 32 C: one doubt -> CAUTION");

    in = base; in.activityG = 0.01f; in.secSinceMoving = 3600;
    CHECK(stateOf(in) == STATE_CAUTION, "still for an hour but hot skin -> CAUTION");

    in = base; in.coastMinutes = 2;
    CHECK(stateOf(in) == STATE_REFUSE, "2 min without HR -> REFUSE");
    in = base; in.everUpdated = false;
    CHECK(stateOf(in) == STATE_REFUSE, "never updated -> REFUSE");
    CHECK(coastInflation(0) == 0 && coastInflation(4) > 0.07f && coastInflation(4) < 0.075f,
          "coast inflation after 4 min = %.3f C", coastInflation(4));

    // ------------------- never REFUSE at or above Watch (38.0 C)
    in = base; in.coastMinutes = 3;
    for (float ct : {38.0f, 38.4f, 39.2f}) {
      in.ctEst = ct;
      CHECK(stateOf(in) == STATE_CAUTION, "3 min without HR at %.1f -> CAUTION, not REFUSE", ct);
    }
    in.ctEst = 37.99f;
    CHECK(stateOf(in) == STATE_REFUSE, "3 min without HR at 37.99 -> still REFUSE");
    in.ctEst = NAN;
    CHECK(stateOf(in) == STATE_REFUSE, "3 min without HR, no estimate -> REFUSE");

    // Two doubts never refuse at Watch. (Up there the stillness doubt does
    // not fire, so check the rule on the flags directly.)
    CHECK(stateFromFlags(F_MOTIONLESS_TACHY | F_COOL_SKIN, 38.3f) == STATE_CAUTION,
          "two doubts at 38.3 -> CAUTION, not REFUSE");
    CHECK(stateFromFlags(F_MOTIONLESS_TACHY | F_COOL_SKIN, 37.9f) == STATE_REFUSE,
          "the same two doubts at 37.9 -> REFUSE");
    in = base; in.ctEst = 38.3f; in.skinC = 30.5f;          // cold wind on the chest
    CHECK(stateOf(in) == STATE_CAUTION && (confoundFlags(in) & F_COOL_SKIN), "cool skin at 38.3 -> CAUTION");

    in = base; in.ctEst = 38.2f; in.coastMinutes = 2;
    f = confoundFlags(in);
    CHECK(strcmp(flagReason(f), "no trustworthy heart rate") == 0,
          "CAUTION at 38.2 still says why (%s)", flagReason(f));
    CHECK(showsNumber(STATE_CAUTION, true) && showsNumber(STATE_OK, true), "number shown on OK and CAUTION");
    CHECK(!showsNumber(STATE_REFUSE, true) && !showsNumber(STATE_OK, false),
          "number withheld on REFUSE or before the first update");

    // BASELINE would reset to <= 37.6 and hide the number: not at Watch.
    CHECK(baselineAllowed(37.2f, false) && baselineAllowed(37.9f, true), "BASELINE allowed below 38.0");
    CHECK(!baselineAllowed(38.0f, true) && !baselineAllowed(38.3f, true), "BASELINE ignored at 38.0 and above");
    CHECK(baselineAllowed(38.3f, false), "before any update the estimate is only a starting guess: allowed");
    {
      ECTemp f; f.initFromRestingHr(200.0f);   // even a silly resting HR
      CHECK(f.ct <= 37.6f, "a baseline can only restart at 37.6 or below (%.2f)", f.ct);
    }

    // ------------------- grace period for "high HR while still"
    // Recovery: work stopped, the heart is still at 120, skin warm.
    Inputs rec = base; rec.activityG = 0.01f;
    for (int s : {0, 60, 300, TACHY_GRACE_SEC - 1}) {
      rec.secSinceMoving = s;
      CHECK(!(confoundFlags(rec) & F_MOTIONLESS_TACHY), "%d s after moving: no TACHY", s);
    }
    rec.secSinceMoving = TACHY_GRACE_SEC;
    CHECK(confoundFlags(rec) & F_MOTIONLESS_TACHY, "10 min after moving: TACHY can fire");
    rec.ctEst = 38.0f; rec.secSinceMoving = 3600;
    CHECK(!(confoundFlags(rec) & F_MOTIONLESS_TACHY), "at 38.0, still for an hour: no TACHY");
    in = base; in.activityG = 0.01f; in.secSinceMoving = 1000000;
    CHECK(confoundFlags(in) & F_MOTIONLESS_TACHY, "never moved since boot: TACHY can fire");

    // No motion sensor: activity reads 0 all through a workout, which looks
    // exactly like sitting still. The stillness check must stand down.
    in = base; in.haveImu = false; in.activityG = 0.0f; in.secSinceMoving = 1000000; in.hr = 150;
    CHECK(!(confoundFlags(in) & F_MOTIONLESS_TACHY), "no IMU: no TACHY, whatever the heart rate");
    CHECK(stateOf(in) == STATE_OK, "no IMU, working hard in heat -> OK");

    Inputs cool = desk; cool.secSinceMoving = 300;   // recovering with cool skin
    f = confoundFlags(cool);
    CHECK(!(f & F_MOTIONLESS_TACHY) && stateOf(cool) == STATE_CAUTION,
          "5 min into recovery, cool skin: one doubt -> CAUTION, not REFUSE");
    cool.secSinceMoving = 3600; cool.ctEst = 38.1f;
    f = confoundFlags(cool);
    CHECK(!(f & F_MOTIONLESS_TACHY) && stateOf(cool) == STATE_CAUTION,
          "still for an hour at 38.1: no TACHY -> CAUTION");

    // ------------------- reserved bits: 0x0010 (v2.0), and v2.1's humidity
    // and two-sensor flags
    {
      const uint16_t RESERVED = F_RESERVED_0002 | F_RESERVED_0010 | F_RESERVED_0080 |
                                F_RESERVED_0100 | F_RESERVED_0200;
      uint16_t seen = 0;
      for (const Inputs &c0 : {base, desk, rec, cool})
        for (int m : {0, 1, 2, 10, 60})
          for (float ct : {35.0f, 37.0f, 37.9f, 38.0f, 38.5f, 41.5f})
            for (bool air : {true, false})
              for (float hr : {NAN, 70.f, 160.f}) {
                Inputs c = c0; c.coastMinutes = m; c.ctEst = ct; c.haveAir = air; c.hr = hr;
                c.cadenceLockSeen = m == 1; c.skinQ = m == 2 ? SKIN_DISAGREE : SKIN_SINGLE;
                c.calibrated = m != 10; c.lowBatt = m == 60;
                seen |= confoundFlags(c);
              }
      CHECK(!(seen & RESERVED), "reserved bits are never set (saw 0x%04X)", seen & RESERVED);
      CHECK(flagReason(RESERVED)[0] == '\0', "reserved bits have no reason text");
      in = base; in.ctEst = 38.5f; in.coastMinutes = 60;
      CHECK(stateOf(in) == STATE_CAUTION && fabsf(coastInflation(60) - 0.280f) < 0.002f,
            "an hour of coasting at 38.5: +/- grows to %.2f, number kept",
            conformal_half_width(38.5f) + coastInflation(60));
    }

    // ------------------- auxiliary sensors are info only
    in = base; in.calibrated = false;
    CHECK(stateOf(in) == STATE_OK, "uncalibrated thermistors -> OK");

    // Uncalibrated beads reading low in a cool room: no skin doubt.
    in = base; in.calibrated = false; in.skinC = 30.0f;
    f = confoundFlags(in);
    CHECK(!(f & F_COOL_SKIN) && stateOf(in) == STATE_OK,
          "uncalibrated, skin reads 30 C: no skin doubt -> OK");
    in.calibrated = true;
    f = confoundFlags(in);
    CHECK((f & F_COOL_SKIN) && stateOf(in) == STATE_CAUTION,
          "the same once calibrated: the skin doubt -> CAUTION");
    // The cost: coffee at a desk on an uncalibrated unit is one doubt, not two.
    in = desk; in.calibrated = false;
    f = confoundFlags(in);
    CHECK((f & F_MOTIONLESS_TACHY) && !(f & F_COOL_SKIN) && stateOf(in) == STATE_CAUTION,
          "coffee at a desk, uncalibrated -> CAUTION only (run CAL before the demo)");
    in = base; in.haveAir = false;
    f = confoundFlags(in);
    CHECK((f & F_NO_AIR) && stateOf(in) == STATE_OK, "no air thermistor -> OK, NO_AIR set");
    in = base; in.skinQ = SKIN_DISAGREE;
    CHECK(stateOf(in) == STATE_OK, "skin beads disagree -> OK");
    in = base; in.skinQ = SKIN_SINGLE;
    CHECK(stateOf(in) == STATE_OK, "one skin bead off -> OK");
    in = base; in.lowBatt = true;
    CHECK(stateOf(in) == STATE_OK, "low battery -> OK");
    in = base; in.calibrated = false; in.haveAir = false;
    in.skinQ = SKIN_DISAGREE; in.lowBatt = true;
    CHECK(stateOf(in) == STATE_OK, "every info-only flag at once -> still OK");
    in.baselineValid = false;
    f = confoundFlags(in);
    CHECK(stateOf(in) == STATE_CAUTION && strcmp(flagReason(f), "no baseline yet") == 0,
          "CAUTION reason is the real one, not an info-only flag (%s)", flagReason(f));

    in = base; in.cadenceLockSeen = true;
    CHECK(stateOf(in) == STATE_CAUTION, "cadence lock seen -> CAUTION");
    in = base; in.baselineValid = false;
    CHECK(stateOf(in) == STATE_CAUTION, "no baseline -> CAUTION");
    in = base; in.baselineRunning = true;
    CHECK(stateOf(in) == STATE_CAUTION, "baseline running -> CAUTION");
  }

  // ------------------------- the frame at Watch, while coasting
  {
    // The strap slipped at 38.3: three minutes without a heart rate.
    Inputs in{};
    in.ctEst = 38.3f; in.hr = NAN; in.coastMinutes = 3; in.everUpdated = true;
    in.skinC = 35.0f; in.skinQ = SKIN_AGREED; in.haveAir = true;
    in.haveImu = true; in.activityG = 0.2f; in.secSinceMoving = 0; in.baselineValid = true; in.restHr = 65;
    in.calibrated = true;
    uint16_t f = confoundFlags(in);
    State st = stateFromFlags(f, in.ctEst);
    float conf = conformal_half_width(in.ctEst);
    float half = conf + coastInflation(in.coastMinutes);   // as ember.ino computes it
    bool show = showsNumber(st, in.everUpdated);
    Frame fr{};
    fr.ctC = show ? in.ctEst : NAN; fr.halfC = show ? half : NAN; fr.state = st; fr.flags = f;
    fr.hr = NAN; fr.hrQ = HRQ_NONE; fr.skinC = fr.airC = NAN;
    fr.activityG = NAN; fr.battPct = 255;
    uint8_t b[PACKET_LEN];
    encodeFrame(fr, b);
    CHECK(st == STATE_CAUTION && (f & F_STALE_HR), "stale HR at 38.3 -> CAUTION");
    CHECK((int16_t)(b[2] | b[3] << 8) == 3830, "frame carries the number (38.30)");
    CHECK(b[4] != 255 && b[4] > (uint8_t)roundf(conf * 50.f),
          "frame carries the +/-, inflated: %.2f vs %.2f calibrated", b[4] / 50.f, conf);
    CHECK((b[5] & 0x0F) == STATE_CAUTION && (b[6] | b[7] << 8) == f, "state and flags in the frame");

    in.ctEst = 37.8f;
    st = stateFromFlags(confoundFlags(in), in.ctEst);
    CHECK(st == STATE_REFUSE && !showsNumber(st, true), "the same at 37.8 -> REFUSE, number withheld");
  }

  // ------------------------------------------------------------ frame
  {
    Frame fr{};
    fr.seq = 513; fr.ctC = 37.84f; fr.halfC = 0.62f; fr.state = STATE_CAUTION;
    fr.baselineRunning = false; fr.logging = true; fr.flags = F_SKIN_SINGLE | F_NO_BASELINE;
    fr.hr = 131.4f; fr.hrQ = HRQ_OK; fr.skinC = 34.12f; fr.airC = 22.5f;
    fr.battPct = 81; fr.activityG = 0.21f;
    uint8_t b[PACKET_LEN];
    encodeFrame(fr, b);
    CHECK((b[0] | b[1] << 8) == 513, "seq");
    CHECK((int16_t)(b[2] | b[3] << 8) == 3784, "ct centi");
    CHECK(b[4] == 31, "half 0.62 -> 31 x 0.02");
    CHECK(b[5] == (1 | 0x20), "state byte");
    CHECK((b[6] | b[7] << 8) == (F_SKIN_SINGLE | F_NO_BASELINE), "flags");
    CHECK(b[8] == 131 && b[9] == 1, "hr");
    CHECK((int16_t)(b[10] | b[11] << 8) == 3412, "skin");
    CHECK((int16_t)(b[12] | b[13] << 8) == 2250, "air 22.5");
    CHECK(b[14] == 255 && b[15] == 0x80, "reserved bytes 14-15 sent as 'not available'");
    CHECK(b[16] == 81 && b[17] == 105, "battery, activity");
    CHECK(b[18] == 0 && b[19] == 0, "reserved bytes 18-19 sent as 'not available'");
    fr.ctC = NAN; fr.halfC = NAN; fr.airC = NAN;
    encodeFrame(fr, b);
    CHECK((int16_t)(b[2] | b[3] << 8) == INT16_MIN && b[4] == 255 &&
          (int16_t)(b[12] | b[13] << 8) == INT16_MIN, "NAN sentinels");
  }

  // ---------------------------------------------------------- battery
  {
    CHECK(lipoPercent(4.2f) == 100 && lipoPercent(3.3f) == 0, "battery ends");
    int prev = -1; bool mono = true;
    for (float v = 3.3f; v <= 4.2f; v += 0.01f) { int p = lipoPercent(v); if (p < prev) mono = false; prev = p; }
    CHECK(mono, "battery percent monotone");
  }

  printf("\n%d passed, %d failed\n", passes, fails);
  return fails ? 1 : 0;
}
