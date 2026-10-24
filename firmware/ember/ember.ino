/*
 * ================================================================
 *  EMBER v2  -  an honest core-temperature estimator
 *  ESP32-S3-DevKitC-1  ·  chest strap  ·  no display, app over BLE
 * ================================================================
 *
 *  WHAT IT MEASURES                          PIN (J1 header)
 *    pulse sensor A  (analog, 3V3)           GPIO4   J1-4
 *    pulse sensor B  (analog, 3V3)           GPIO5   J1-5
 *    skin thermistor A (10k NTC divider)     GPIO6   J1-6
 *    skin thermistor B (10k NTC divider)     GPIO7   J1-7
 *    battery sense, held at 0 V by R4        GPIO8   J1-12   (reads "no battery")
 *    I2C SDA  (SHT40 0x44, IMU 0x68)         GPIO17  J1-10
 *    I2C SCL                                 GPIO18  J1-11
 *    3V3 out to every sensor                 3V3     J1-1
 *    power: USB-C port, from a power bank or the laptop
 *    ground                                  G       J1-22
 *
 *  Every analog input is on ADC1 (GPIO1-10). ADC2 is shared with the
 *  radio and returns garbage while BLE is running.
 *
 *  NO LIBRARIES TO INSTALL. Everything here ships with the ESP32 Arduino
 *  core (3.x): Wire, Preferences, BLE. The SHT40 and IMU are driven with
 *  a few raw register reads instead of Adafruit's libraries - because
 *  the Adafruit MPU6050 library refuses to start unless the chip answers
 *  WHO_AM_I = 0x68, and most "ITG/MPU" GY-521 boards sold today carry a
 *  clone or an MPU-6500 that answers something else. The accelerometer
 *  registers are identical, so we just read them.
 *
 *  ARDUINO IDE SETTINGS
 *    Board: "ESP32S3 Dev Module"
 *    Plug into the port marked UART  -> USB CDC On Boot: Disabled
 *    Plug into the port marked USB   -> USB CDC On Boot: Enabled
 *    Either works. Pick one and stick with it.
 *
 *  SERIAL 115200 - type HELP. Every build gate in the guide uses one of
 *  these commands, so this is the only firmware you ever flash.
 *
 *  NOT A MEDICAL DEVICE. Bench demonstrator, consenting adults.
 * ================================================================
 */

#include <Arduino.h>
#include <initializer_list>
#include <Wire.h>
#include <Preferences.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLE2902.h>
#include <esp_sleep.h>

#include "ember_core.h"
#include "conformal_table.h"

using namespace ember;

#define FW_VERSION "2.1"

// ----------------------------------------------------------------- pins
#define PIN_PPG_A   4
#define PIN_PPG_B   5
#define PIN_NTC_A   6
#define PIN_NTC_B   7
#define PIN_VBAT    8
#define PIN_SDA    17
#define PIN_SCL    18

// ------------------------------------------------------------------ BLE
#define BLE_NAME   "Ember"
#define UUID_SVC   "e3b10001-5a2f-4c8e-9b7d-656d62657200"
#define UUID_LIVE  "e3b10002-5a2f-4c8e-9b7d-656d62657200"   // notify, 20 B, 1 Hz
#define UUID_CMD   "e3b10003-5a2f-4c8e-9b7d-656d62657200"   // write, ASCII command

// -------------------------------------------------------------- buffers
// Written by the sampler task on core 0, read by loop() on core 1.
static const int PPG_N = 800;          // 8 s at 100 Hz
static const int ACC_N = 400;          // 8 s at 50 Hz
static float ppgA[PPG_N], ppgB[PPG_N];
static float accBuf[ACC_N];
static int ppgHead = 0, accHead = 0;
static uint32_t satA = 0, satB = 0;    // samples at the ADC rails this second
static float ntcAmV = NAN, ntcBmV = NAN, vbatmV = NAN;
static float shtT = NAN, shtRH = NAN;
static float accX = NAN, accY = NAN, accZ = NAN;
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

struct RawPair { uint16_t a, b; };
static QueueHandle_t rawQ;             // raw PPG for the PPG plotter command
static volatile bool streamPpg = false;

static TaskHandle_t samplerTask = nullptr;
static volatile bool i2cPaused = false;   // loop() borrows the bus for SCAN
static bool haveImu = false, haveSht = false;
static uint8_t imuAddr = 0x68, shtAddr = 0x44, imuWho = 0;

// -------------------------------------------------------------- devices

static bool i2cWrite(uint8_t addr, uint8_t reg, uint8_t val) {
  Wire.beginTransmission(addr);
  Wire.write(reg); Wire.write(val);
  return Wire.endTransmission() == 0;
}

static bool i2cPresent(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

// IMU: MPU-6050 / MPU-6500 / clones. Accel only, +/-8 g, 44 Hz DLPF.
static bool imuInit() {
  for (uint8_t a : {(uint8_t)0x68, (uint8_t)0x69}) {
    if (!i2cPresent(a)) continue;
    imuAddr = a;
    i2cWrite(a, 0x6B, 0x00);           // wake
    delay(50);
    i2cWrite(a, 0x1A, 0x03);           // DLPF ~44 Hz
    i2cWrite(a, 0x1C, 0x10);           // accel +/-8 g -> 4096 LSB/g
    Wire.beginTransmission(a); Wire.write(0x75); Wire.endTransmission(false);
    if (Wire.requestFrom(a, (uint8_t)1) == 1) imuWho = Wire.read();
    return true;
  }
  return false;
}

static bool imuRead(float &x, float &y, float &z) {
  Wire.beginTransmission(imuAddr);
  Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(imuAddr, (uint8_t)6) != 6) return false;
  int16_t ax = (Wire.read() << 8) | Wire.read();
  int16_t ay = (Wire.read() << 8) | Wire.read();
  int16_t az = (Wire.read() << 8) | Wire.read();
  x = ax / 4096.0f; y = ay / 4096.0f; z = az / 4096.0f;
  return true;
}

// SHT40: high-precision single shot. Trigger, wait >= 9 ms, read 6 bytes.
static uint8_t crc8(const uint8_t *d, int n) {
  uint8_t c = 0xFF;
  for (int i = 0; i < n; i++) {
    c ^= d[i];
    for (int b = 0; b < 8; b++) c = (c & 0x80) ? (uint8_t)((c << 1) ^ 0x31) : (uint8_t)(c << 1);
  }
  return c;
}

static bool shtInit() {
  for (uint8_t a : {(uint8_t)0x44, (uint8_t)0x45}) {
    if (i2cPresent(a)) { shtAddr = a; return true; }
  }
  return false;
}

static void shtTrigger() {
  Wire.beginTransmission(shtAddr);
  Wire.write(0xFD);
  Wire.endTransmission();
}

static bool shtFetch(float &t, float &rh) {
  if (Wire.requestFrom(shtAddr, (uint8_t)6) != 6) return false;
  uint8_t b[6];
  for (int i = 0; i < 6; i++) b[i] = Wire.read();
  if (crc8(b, 2) != b[2] || crc8(b + 3, 2) != b[5]) return false;
  uint16_t rt = (b[0] << 8) | b[1], rr = (b[3] << 8) | b[4];
  t  = -45.0f + 175.0f * rt / 65535.0f;
  rh = fminf(fmaxf(-6.0f + 125.0f * rr / 65535.0f, 0.0f), 100.0f);
  return true;
}

static float readMilliVoltsAvg(int pin, int n) {
  uint32_t s = 0;
  for (int i = 0; i < n; i++) s += analogReadMilliVolts(pin);
  return (float)s / n;
}

// ---------------------------------------------------------- sampler task
// Core 0, every 10 ms, never blocks for long. Owns the ADC and the I2C
// bus, so nothing else touches them while it runs.

static void samplerLoop(void *) {
  Prefilter pfA(PPG_HP_A, PPG_LP_A), pfB(PPG_HP_A, PPG_LP_A), pfAcc(ACC_HP_A, ACC_LP_A);
  TickType_t last = xTaskGetTickCount();
  uint32_t tick = 0;
  for (;;) {
    vTaskDelayUntil(&last, pdMS_TO_TICKS(10));
    tick++;

    int a = analogRead(PIN_PPG_A);
    int b = analogRead(PIN_PPG_B);
    float fa = pfA.step((float)a), fb = pfB.step((float)b);
    portENTER_CRITICAL(&mux);
    ppgA[ppgHead] = fa; ppgB[ppgHead] = fb;
    ppgHead = (ppgHead + 1) % PPG_N;
    if (a <= 8 || a >= 4087) satA++;
    if (b <= 8 || b >= 4087) satB++;
    portEXIT_CRITICAL(&mux);
    if (streamPpg) { RawPair p = {(uint16_t)a, (uint16_t)b}; xQueueSend(rawQ, &p, 0); }

    if (haveImu && !i2cPaused && (tick % 2 == 0)) {      // 50 Hz
      float x, y, z;
      if (imuRead(x, y, z)) {
        float m = pfAcc.step(sqrtf(x * x + y * y + z * z));
        portENTER_CRITICAL(&mux);
        accBuf[accHead] = m; accHead = (accHead + 1) % ACC_N;
        accX = x; accY = y; accZ = z;
        portEXIT_CRITICAL(&mux);
      }
    }

    if (tick % 100 == 50) {                              // 1 Hz, slow stuff
      float na = readMilliVoltsAvg(PIN_NTC_A, 16);
      float nb = readMilliVoltsAvg(PIN_NTC_B, 16);
      float vb = readMilliVoltsAvg(PIN_VBAT, 16);
      portENTER_CRITICAL(&mux);
      ntcAmV = na; ntcBmV = nb; vbatmV = vb;
      portEXIT_CRITICAL(&mux);
    }

    if (haveSht && !i2cPaused) {                         // every 2 s
      if (tick % 200 == 0) shtTrigger();
      if (tick % 200 == 2) {
        float t, rh;
        bool ok = shtFetch(t, rh);
        portENTER_CRITICAL(&mux);
        if (ok) { shtT = t; shtRH = rh; } else { shtT = NAN; shtRH = NAN; }
        portEXIT_CRITICAL(&mux);
      }
    }
  }
}

// ----------------------------------------------------------- persistent
Preferences prefs;
static float calA = 1.0f, calB = 1.0f;
static bool calibrated = false;
static NtcParams ntcP;

static void loadCal() {
  prefs.begin("ember", true);
  calA = prefs.getFloat("kA", 1.0f);
  calB = prefs.getFloat("kB", 1.0f);
  calibrated = prefs.getBool("cal", false);
  prefs.end();
}

static void saveCal() {
  prefs.begin("ember", false);
  prefs.putFloat("kA", calA);
  prefs.putFloat("kB", calB);
  prefs.putBool("cal", calibrated);
  prefs.end();
}

// --------------------------------------------------------------- state
static ECTemp ect;
static bool everUpdated = false;
static int coastMinutes = 0;
static int secInMinute = 0;
static double minuteHrSum = 0; static int minuteHrN = 0;
static HrReference hrRef;              // last good minute's HR, for the cadence check
static int lastStepKind = 0;           // 1 updated, 2 coasted, 0 neither (this second)

static bool baselineValid = false, baselineRunning = false;
static float restHr = NAN;
static int baselineSec = 0; static double baseSum = 0; static int baseN = 0;
static const int BASELINE_SEC = 300;

static bool calRunning = false; static int calSec = 0;
static int calStartIn = 0;                 // seconds until a delayed CAL begins
RTC_DATA_ATTR int calOnWake = 0;               // survives deep sleep: CALSLEEP sets it
static double calSumT = 0, calSumA = 0, calSumB = 0;
static float calMinT, calMaxT, calMinA, calMaxA, calMinB, calMaxB;
static const int CAL_SEC = 30;

static float activityG = 0.0f;
static const int NEVER_MOVED = 1000000;
static int secSinceMoving = NEVER_MOVED;   // for the "high HR while still" grace period
static int lowBattSec = 0, deadBattSec = 0;
static bool logging = false;
// (not called "Stream" - that is the Arduino base class of Serial)
enum StreamMode { S_NONE, S_HR, S_TEMP, S_IMU, S_BATT, S_STATUS };
static StreamMode stream = S_NONE;
static uint16_t seq = 0;

// Latest analysis, for STATUS and the frame.
struct Snapshot {
  Channel chA, chB; Periodicity pA, pB, cad; Fused hr;
  float tA, tB; SkinResult skin; float microC, microRh, headroom;
  float vbat; bool battPresent; uint8_t battPct;
  float ct, half, kalmanHalf; uint16_t flags; State state;
} snap;

// ------------------------------------------------------------------ BLE
static BLECharacteristic *liveChr = nullptr;
static volatile bool bleConnected = false, bleRestartAdv = false;
static String pendingCmd;
static portMUX_TYPE cmdMux = portMUX_INITIALIZER_UNLOCKED;
static volatile bool havePendingCmd = false;

class SrvCb : public BLEServerCallbacks {
  void onConnect(BLEServer *) override { bleConnected = true; }
  void onDisconnect(BLEServer *) override { bleConnected = false; bleRestartAdv = true; }
};

class CmdCb : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    auto v = c->getValue();              // String on core 3.x, std::string on 2.x
    String s(v.c_str());
    portENTER_CRITICAL(&cmdMux);
    pendingCmd = s; havePendingCmd = true;
    portEXIT_CRITICAL(&cmdMux);
  }
};

static void bleStart() {
  BLEDevice::init(BLE_NAME);
  BLEServer *srv = BLEDevice::createServer();
  srv->setCallbacks(new SrvCb());
  BLEService *svc = srv->createService(UUID_SVC);
  liveChr = svc->createCharacteristic(UUID_LIVE,
              BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
#if !defined(CONFIG_NIMBLE_ENABLED)
  // Bluedroid (older 3.x cores) needs the notify descriptor added by hand.
  // NimBLE (core 3.3+ on the S3) adds it itself and deprecates BLE2902.
  liveChr->addDescriptor(new BLE2902());
#endif
  BLECharacteristic *cmd = svc->createCharacteristic(UUID_CMD,
              BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  cmd->setCallbacks(new CmdCb());
  svc->start();
  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(UUID_SVC);
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
}

// ------------------------------------------------------------ utilities

static void i2cScan() {
  // Ask the sampler to keep off the bus rather than suspending it - a task
  // suspended mid-transaction would leave the I2C driver locked.
  i2cPaused = true;
  delay(30);
  Serial.println("# I2C scan (SDA=GPIO17, SCL=GPIO18):");
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    if (!i2cPresent(a)) continue;
    Serial.printf("#   0x%02X", a);
    if (a == 0x44 || a == 0x45) Serial.print("  SHT40 microclimate");
    if (a == 0x68 || a == 0x69) Serial.print("  IMU (GY-521 / ITG-MPU)");
    Serial.println();
    n++;
  }
  Serial.printf("# %d device(s). Expect 2: 0x44 and 0x68.\n", n);
  if (haveImu) Serial.printf("# IMU WHO_AM_I = 0x%02X (%s)\n", imuWho,
      imuWho == 0x68 ? "MPU-6050" : imuWho == 0x70 ? "MPU-6500" :
      imuWho == 0x72 ? "MPU-6050 clone" : "unknown clone - accel still works");
  i2cPaused = false;
}

static void printHelp() {
  Serial.println(
    "# EMBER commands (serial 115200, or written to the BLE command characteristic)\n"
    "#  bring-up\n"
    "#   SCAN      I2C scan - expect 0x44 SHT40 and 0x68 IMU\n"
    "#   PPG       raw pulse sensors at 100 Hz for Tools > Serial Plotter\n"
    "#   HR        per-sensor heart rate, signal quality, fused result, 1 Hz\n"
    "#   TEMP      thermistors (mV, kOhm, C), SHT40, evaporative headroom, 1 Hz\n"
    "#   IMU       accelerometer, activity, step cadence, 1 Hz\n"
    "#   BATT      battery voltage and percent, 1 Hz\n"
    "#   STATUS    everything, once\n"
    "#  calibration and use\n"
    "#   CAL       calibrate both thermistors against the SHT40 (30 s)\n"
    "#   CALSLEEP  sleep 20 min to cool, then CAL. Laptop USB only: a power\n"
    "#             bank switches off while the board sleeps\n"
    "#   CALCLEAR  forget the calibration\n"
    "#   BASELINE  5 min seated rest: personal resting HR and starting core temp\n"
    "#   START     CSV log at 1 Hz        STOP  stop logging / streaming\n"
    "#   SLEEP     deep sleep (~2 mA); press RST to wake\n"
    "#   ID        version and configuration\n"
    "#  any new command stops a running stream");
}

static void printId() {
  Serial.printf("# EMBER v%s - two pulse sensors, two thermistors, SHT40, IMU, BLE\n", FW_VERSION);
  Serial.printf("# coefficient check %s\n", coefficientsSane() ? "PASS" : "FAIL");
  Serial.printf("# conformal %.0f%% level, %d strata, measured coverage %.1f%%\n",
                CONF_LEVEL * 100, CONF_N_STRATA, CONF_MEASURED_COV * 100);
  Serial.printf("# never withholds the number at or above %.1f C\n", CT_WATCH_C);
  Serial.printf("# sensors: IMU %s, SHT40 %s\n", haveImu ? "yes" : "NO", haveSht ? "yes" : "NO");
  Serial.printf("# thermistor calibration: %s (kA %.4f, kB %.4f)\n",
                calibrated ? "yes" : "NO - run CAL (skin checks are off until then)", calA, calB);
  Serial.printf("# baseline: %s\n", baselineValid ? "captured" : "not captured - run BASELINE");
  Serial.printf("# BLE name \"%s\", %s\n", BLE_NAME, bleConnected ? "app connected" : "advertising");
}

static void csvHeader() {
  Serial.println("ms,hrA,sqiA,hrB,sqiB,hr,hr_q,step_hz,act_g,skinA,skinB,skin,skin_q,"
                 "micro_c,micro_rh,evap_kpa,vbat,ct_est,ct_lo,ct_hi,kalman_half,"
                 "filter_step,state,flags");
}

static void startCal() {
  calRunning = true; calSec = 0;
  calSumT = calSumA = calSumB = 0;
  calMinT = calMinA = calMinB = 1e9f;
  calMaxT = calMaxA = calMaxB = -1e9f;
  Serial.println("# CAL: thermistors and SHT40 must be at the SAME temperature.");
  Serial.println("# Device unpowered at room temperature for 30+ min, SHT40 lying");
  Serial.println("# against the case floor, nothing warm nearby. Collecting 30 s...");
}

static void finishCal(float mvA, float mvB) {
  (void)mvA; (void)mvB;
  calRunning = false;
  float T = calSumT / CAL_SEC, A = calSumA / CAL_SEC, B = calSumB / CAL_SEC;
  float spreadT = calMaxT - calMinT, spreadA = calMaxA - calMinA, spreadB = calMaxB - calMinB;
  Serial.printf("# SHT40 %.2f C (spread %.2f)\n", T, spreadT);
  if (spreadT > 0.15f) { Serial.println("# CAL FAILED: SHT40 still drifting. Wait and retry."); return; }
  NtcParams p = ntcP;
  float rA = ntcResistance(A, p), rB = ntcResistance(B, p);
  if (isnan(rA) || isnan(rB)) { Serial.println("# CAL FAILED: a thermistor reads open or short. Check wiring."); return; }
  float rTrue = ntcRFromTemp(T, p);
  float kA = rA / rTrue, kB = rB / rTrue;
  Serial.printf("# bead A %.0f ohm (raw %.2f C, spread %.0f mV)  ->  k = %.4f\n",
                rA, ntcTempC(A, 1.0f, p), spreadA, kA);
  Serial.printf("# bead B %.0f ohm (raw %.2f C, spread %.0f mV)  ->  k = %.4f\n",
                rB, ntcTempC(B, 1.0f, p), spreadB, kB);
  if (kA < 0.85f || kA > 1.15f || kB < 0.85f || kB > 1.15f) {
    Serial.println("# CAL FAILED: correction outside +/-15 %. That is not thermistor");
    Serial.println("# tolerance - check that the fixed resistors are 10k and the");
    Serial.println("# divider is wired 3V3 -> 10k -> node -> thermistor -> GND.");
    return;
  }
  calA = kA; calB = kB; calibrated = true;
  saveCal();
  Serial.printf("# CAL saved. Both beads now read %.2f / %.2f C against SHT40 %.2f C\n",
                ntcTempC(A, calA, p), ntcTempC(B, calB, p), T);
}

static void handleCommand(String s) {
  s.trim(); s.toUpperCase();
  if (s.length() == 0) return;
  streamPpg = false;
  stream = S_NONE;
  if      (s == "HELP")     printHelp();
  else if (s == "ID")       printId();
  else if (s == "SCAN")     i2cScan();
  else if (s == "PPG")      { xQueueReset(rawQ); streamPpg = true; }
  else if (s == "HR")       stream = S_HR;
  else if (s == "TEMP")     stream = S_TEMP;
  else if (s == "IMU")      stream = S_IMU;
  else if (s == "BATT")     stream = S_BATT;
  else if (s == "STATUS")   stream = S_STATUS;          // printed once, next tick
  else if (s == "CAL")      startCal();
  else if (s == "CALSLEEP") { Serial.println("# sleeping 20 min with the radio off, then calibrating.");
                              Serial.println("# Leave it alone - don't open the serial monitor until 21 min.");
                              Serial.flush(); calOnWake = 1;
                              esp_sleep_enable_timer_wakeup(20ULL * 60ULL * 1000000ULL);
                              delay(100); esp_deep_sleep_start(); }
  else if (s == "CALCLEAR") { calA = calB = 1.0f; calibrated = false; saveCal();
                              Serial.println("# calibration cleared"); }
  else if (s == "BASELINE") {
    if (!baselineAllowed(ect.clamped(), everUpdated)) {
      Serial.printf("# BASELINE ignored: estimate %.2f C is at or above %.1f C. Cool down first.\n",
                    ect.clamped(), CT_WATCH_C);
    } else {
      baselineRunning = true; baselineSec = 0; baseSum = 0; baseN = 0;
      Serial.println("# BASELINE: sit still and quiet for 5 minutes.");
    }
  }
  else if (s == "START")    { logging = true; csvHeader(); }
  else if (s == "STOP")     { logging = false; Serial.println("# stopped"); }
  else if (s == "SLEEP")    { Serial.println("# deep sleep. Press RST to wake."); Serial.flush();
                              delay(100); esp_deep_sleep_start(); }
  else Serial.printf("# unknown command '%s' - type HELP\n", s.c_str());
}

// ------------------------------------------------------- one analysis tick

static float bufA[PPG_N], bufB[PPG_N], bufAcc[ACC_N];

static void analyse() {
  uint32_t sA, sB; float nA, nB, vb, mT, mRH;
  portENTER_CRITICAL(&mux);
  for (int i = 0; i < PPG_N; i++) {
    int k = (ppgHead + i) % PPG_N;               // oldest first
    bufA[i] = ppgA[k]; bufB[i] = ppgB[k];
  }
  for (int i = 0; i < ACC_N; i++) bufAcc[i] = accBuf[(accHead + i) % ACC_N];
  sA = satA; sB = satB; satA = satB = 0;
  nA = ntcAmV; nB = ntcBmV; vb = vbatmV; mT = shtT; mRH = shtRH;
  portEXIT_CRITICAL(&mux);

  // motion
  Periodicity cad = { NAN, 0, 0 };
  float act = 0;
  if (haveImu) {
    cad = periodicity(bufAcc, ACC_N, ACC_FS, 0.8f, 3.5f);
    double ss = 0; int n = 100;                  // last 2 s
    for (int i = ACC_N - n; i < ACC_N; i++) ss += bufAcc[i] * bufAcc[i];
    act = sqrtf(ss / n);
  }
  activityG += 0.2f * (act - activityG);
  bool moving = activityG >= ACT_MOVING_G;
  if (moving) secSinceMoving = 0;
  else if (secSinceMoving < NEVER_MOVED) secSinceMoving++;
  float stepHz = (cad.sqi >= 0.4f) ? cad.freqHz : NAN;

  // heart rate
  Periodicity pA = periodicity(bufA, PPG_N, PPG_FS, HR_MIN / 60.0f, HR_MAX / 60.0f);
  Periodicity pB = periodicity(bufB, PPG_N, PPG_FS, HR_MIN / 60.0f, HR_MAX / 60.0f);
  Channel chA = judgeChannel(pA, sA > 5);
  Channel chB = judgeChannel(pB, sB > 5);
  cadenceCheck(chA, chB, stepHz, moving, hrRef.hr);
  Fused hr = fuseHr(chA, chB);

  // skin, microclimate, battery
  float tA = ntcTempC(nA, calA, ntcP), tB = ntcTempC(nB, calB, ntcP);
  SkinResult skin = fuseSkin(tA, tB);
  float headroom = evaporativeHeadroom(skin.tC, mT, mRH);
  float vbat = 2.0f * vb / 1000.0f;
  bool battPresent = vbat > 2.5f;               // below: no battery, running on USB

  // the filter steps once a minute
  lastStepKind = 0;
  if (!isnan(hr.hr)) { minuteHrSum += hr.hr; minuteHrN++; }
  if (++secInMinute >= 60) {
    if (minuteHrN >= MIN_GOOD_SEC_PER_MINUTE) {
      float minuteHr = (float)(minuteHrSum / minuteHrN);
      hrRef.endMinute(minuteHr);
      ect.update(minuteHr);
      everUpdated = true; coastMinutes = 0; lastStepKind = 1;
    } else {
      hrRef.endMinute(NAN);
      ect.coast(); coastMinutes++; lastStepKind = 2;
    }
    secInMinute = 0; minuteHrSum = 0; minuteHrN = 0;
  }

  // baseline
  if (baselineRunning) {
    baselineSec++;
    if (!isnan(hr.hr)) { baseSum += hr.hr; baseN++; }
    if (baselineSec % 30 == 0)
      Serial.printf("# baseline %3d/%d s  HR %s  (%d good seconds)\n", baselineSec, BASELINE_SEC,
                    isnan(hr.hr) ? "--" : String(hr.hr, 0).c_str(), baseN);
    if (baselineSec >= BASELINE_SEC) {
      baselineRunning = false;
      if (!baselineAllowed(ect.clamped(), everUpdated)) {
        Serial.printf("# baseline CANCELLED: estimate rose to %.2f C during it. Not resetting.\n", ect.clamped());
      } else if (baseN >= 120) {
        restHr = baseSum / baseN; baselineValid = true;
        ect.initFromRestingHr(restHr);
        everUpdated = false; coastMinutes = 0; secInMinute = 0; minuteHrSum = 0; minuteHrN = 0;
        Serial.printf("# baseline OK: resting HR %.1f, starting core estimate %.2f C\n", restHr, ect.ct);
      } else {
        Serial.printf("# baseline FAILED: only %d usable seconds of heart rate. Check sensor contact.\n", baseN);
      }
    }
  }

  // calibration
  if (calStartIn > 0 && --calStartIn == 0) startCal();   // sensors have settled
  if (calRunning) {
    if (isnan(mT) || isnan(nA) || isnan(nB)) {
      calRunning = false; Serial.println("# CAL FAILED: SHT40 or a thermistor not reading");
    } else {
      calSumT += mT; calSumA += nA; calSumB += nB; calSec++;
      calMinT = fminf(calMinT, mT); calMaxT = fmaxf(calMaxT, mT);
      calMinA = fminf(calMinA, nA); calMaxA = fmaxf(calMaxA, nA);
      calMinB = fminf(calMinB, nB); calMaxB = fmaxf(calMaxB, nB);
      if (calSec >= CAL_SEC) finishCal(nA, nB);
    }
  }

  // battery protection: a pouch run flat is a damaged pouch
  if (battPresent && vbat < 3.50f) lowBattSec++; else lowBattSec = 0;
  if (battPresent && vbat < 3.40f) deadBattSec++; else deadBattSec = 0;
  if (deadBattSec >= 60) {
    Serial.println("# battery below 3.40 V for 60 s - deep sleep to protect the cell. Press RST.");
    Serial.flush();
    esp_deep_sleep_start();
  }

  // decision
  float ct = ect.clamped();
  float half = conformal_half_width(ct) + coastInflation(coastMinutes);
  Inputs in{};
  in.ctEst = ct;
  in.hr = hr.hr; in.hrQ = hr.q;
  in.cadenceLockSeen = chA.cadenceLocked || chB.cadenceLocked;
  in.coastMinutes = coastMinutes; in.everUpdated = everUpdated;
  in.skinC = skin.tC; in.skinQ = skin.q; in.headroom = headroom;
  in.haveMicro = haveSht && !isnan(mT);
  in.haveImu = haveImu; in.activityG = activityG; in.secSinceMoving = secSinceMoving;
  in.baselineValid = baselineValid; in.baselineRunning = baselineRunning; in.restHr = restHr;
  in.calibrated = calibrated; in.lowBatt = lowBattSec >= 30;
  uint16_t flags = confoundFlags(in);
  State st = stateFromFlags(flags, ct);

  snap.chA = chA; snap.chB = chB; snap.pA = pA; snap.pB = pB; snap.cad = cad; snap.hr = hr;
  snap.tA = tA; snap.tB = tB; snap.skin = skin; snap.microC = mT; snap.microRh = mRH;
  snap.headroom = headroom; snap.vbat = vbat; snap.battPresent = battPresent;
  snap.battPct = battPresent ? lipoPercent(vbat) : 255;
  snap.ct = ct; snap.half = half; snap.kalmanHalf = 1.96f * sqrtf(ect.v);
  snap.flags = flags; snap.state = st;

  // to the app. The device itself withholds the number when it refuses -
  // the honest behaviour is enforced here, not left to the app. It never
  // refuses at or above CT_WATCH_C (see stateFromFlags).
  if (bleConnected && liveChr) {
    Frame f{};
    f.seq = seq++;
    bool show = showsNumber(st, everUpdated);
    f.ctC = show ? ct : NAN; f.halfC = show ? half : NAN;
    f.state = st; f.baselineRunning = baselineRunning; f.logging = logging;
    f.flags = flags; f.hr = hr.hr; f.hrQ = hr.q;
    f.skinC = skin.tC; f.microC = mT; f.microRh = mRH; f.headroomKpa = headroom;
    f.battPct = snap.battPct; f.activityG = activityG;
    f.hrA = chA.hr; f.hrB = chB.hr;
    uint8_t b[PACKET_LEN];
    encodeFrame(f, b);
    liveChr->setValue(b, PACKET_LEN);
    liveChr->notify();
  }

  // to the serial port
  if (logging) {
    Serial.printf("%lu,%.1f,%.2f,%.1f,%.2f,%.1f,%d,%.2f,%.3f,%.2f,%.2f,%.2f,%d,"
                  "%.2f,%.1f,%.3f,%.2f,%.3f,%.3f,%.3f,%.3f,%d,%d,0x%04X\n",
                  millis(), chA.hr, pA.sqi, chB.hr, pB.sqi, hr.hr, (int)hr.q, stepHz, activityG,
                  tA, tB, skin.tC, (int)skin.q, mT, mRH, headroom, vbat,
                  ct, ct - half, ct + half, snap.kalmanHalf, lastStepKind, (int)st, flags);
  }
  switch (stream) {
    case S_HR:
      Serial.printf("A %5.1f bpm sqi %.2f%s%s | B %5.1f bpm sqi %.2f%s%s | fused %5.1f %s | cadence %.2f Hz\n",
        chA.hr, pA.sqi, chA.cadenceLocked ? " CADENCE" : "", sA > 5 ? " SAT" : "",
        chB.hr, pB.sqi, chB.cadenceLocked ? " CADENCE" : "", sB > 5 ? " SAT" : "",
        hr.hr, hr.q == HRQ_AGREED ? "AGREED" : hr.q == HRQ_SINGLE ? "SINGLE" :
               hr.q == HRQ_DISAGREE ? "DISAGREE" : "NONE", stepHz);
      break;
    case S_TEMP:
      Serial.printf("A %4.0f mV %5.2f k %5.2f C | B %4.0f mV %5.2f k %5.2f C | skin %5.2f %s | SHT40 %5.2f C %4.1f %% | headroom %.2f kPa\n",
        nA, ntcResistance(nA, ntcP) / 1000.0f / calA, tA,
        nB, ntcResistance(nB, ntcP) / 1000.0f / calB, tB, skin.tC,
        skin.q == SKIN_AGREED ? "AGREED" : skin.q == SKIN_SINGLE ? "SINGLE" :
        skin.q == SKIN_DISAGREE ? "DISAGREE" : "NONE", mT, mRH, headroom);
      break;
    case S_IMU: {
      float x, y, z;
      portENTER_CRITICAL(&mux); x = accX; y = accY; z = accZ; portEXIT_CRITICAL(&mux);
      Serial.printf("accel %+.2f %+.2f %+.2f g  |a| %.2f g  activity %.3f g %s  cadence %.2f Hz (sqi %.2f)\n",
        x, y, z, sqrtf(x * x + y * y + z * z), activityG, moving ? "MOVING" : "still", cad.freqHz, cad.sqi);
      break; }
    case S_BATT:
      if (battPresent) Serial.printf("battery %.2f V  %d %%%s\n", vbat, snap.battPct, in.lowBatt ? "  LOW" : "");
      else Serial.printf("no battery seen (%.2f V at the divider) - running on USB\n", vbat);
      break;
    case S_STATUS:
      Serial.printf("# HR  A %.1f (sqi %.2f)  B %.1f (sqi %.2f)  fused %.1f q%d\n",
                    chA.hr, pA.sqi, chB.hr, pB.sqi, hr.hr, (int)hr.q);
      Serial.printf("# skin A %.2f  B %.2f  -> %.2f q%d   SHT40 %.2f C %.1f %%  headroom %.2f kPa\n",
                    tA, tB, skin.tC, (int)skin.q, mT, mRH, headroom);
      Serial.printf("# activity %.3f g  cadence %.2f Hz   battery %.2f V\n", activityG, stepHz, vbat);
      Serial.printf("# core %.2f +/- %.2f C (Kalman would claim +/- %.2f)  state %s  flags 0x%04X  %s\n",
                    ct, half, snap.kalmanHalf, st == STATE_OK ? "OK" : st == STATE_CAUTION ? "CAUTION" : "REFUSE",
                    flags, flagReason(flags));
      stream = S_NONE;
      break;
    default: break;
  }
}

// ----------------------------------------------------------------- main

void setup() {
  Serial.begin(115200);
  delay(600);
  Serial.printf("\n# EMBER v%s starting\n", FW_VERSION);
  if (!coefficientsSane()) {
    Serial.println("# COEFFICIENT CHECK FAILED - the ECTemp constants are wrong. Halting.");
    while (true) delay(1000);
  }

  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);      // full ~0-3.1 V range on every pin

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(100000);               // 100 kHz: the SHT40 is on a lead
  haveImu = imuInit();
  haveSht = shtInit();

  loadCal();
  for (int i = 0; i < PPG_N; i++) ppgA[i] = ppgB[i] = 0;
  for (int i = 0; i < ACC_N; i++) accBuf[i] = 0;

  rawQ = xQueueCreate(256, sizeof(RawPair));
  xTaskCreatePinnedToCore(samplerLoop, "sampler", 4096, nullptr, 3, &samplerTask, 0);

  bleStart();
  i2cScan();
  printId();
  if (calOnWake) {                     // woke from CALSLEEP: board is still cold
    calOnWake = 0;
    calStartIn = 5;                    // let the first SHT40 and NTC readings land
    Serial.println("# woke from CALSLEEP - calibrating in 5 s");
  }
  Serial.println("# type HELP for commands");
}

static uint32_t lastTick = 0;
static String serialLine;

void loop() {
  // serial commands
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') { if (serialLine.length()) handleCommand(serialLine); serialLine = ""; }
    else if (serialLine.length() < 32) serialLine += c;
  }
  // BLE commands
  if (havePendingCmd) {
    String s;
    portENTER_CRITICAL(&cmdMux); s = pendingCmd; havePendingCmd = false; portEXIT_CRITICAL(&cmdMux);
    handleCommand(s);
  }
  if (bleRestartAdv) { bleRestartAdv = false; delay(200); BLEDevice::startAdvertising(); }

  // raw PPG for the plotter
  if (streamPpg) {
    RawPair p;
    while (xQueueReceive(rawQ, &p, 0) == pdTRUE) Serial.printf("ppgA:%u,ppgB:%u\n", p.a, p.b);
  }

  uint32_t now = millis();
  if (now - lastTick >= 1000) {
    lastTick += 1000;
    if (now - lastTick > 3000) lastTick = now;   // don't try to catch up after a stall
    analyse();
  }
  delay(2);
}
