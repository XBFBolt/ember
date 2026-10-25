/*
 * ================================================================
 *  EMBER v2  -  an honest core-temperature estimator
 *  ESP32-S3-DevKitC-1  ·  chest strap  ·  no display, app over BLE
 * ================================================================
 *
 *  WHAT IT MEASURES (hardware v5)            PIN (J1 header)
 *    pulse sensor    (analog, 3V3)           GPIO4   J1-4
 *    air thermistor C (10k NTC divider, R3)  GPIO5   J1-5    hangs outside the strap
 *    skin thermistor A (10k NTC divider, R1) GPIO6   J1-6
 *    skin thermistor B (10k NTC divider, R2) GPIO7   J1-7
 *    battery sense, held at 0 V by R4        GPIO8   J1-12   (reads "no battery")
 *    I2C SDA  (IMU 0x68)                     GPIO17  J1-10
 *    I2C SCL                                 GPIO18  J1-11
 *    3V3 out to every sensor                 3V3     J1-1
 *    power: USB-C port, from a power bank or the laptop
 *    ground                                  G       J1-22
 *
 *  Every analog input is on ADC1 (GPIO1-10). ADC2 is shared with the
 *  radio and returns garbage while BLE is running.
 *
 *  NO LIBRARIES TO INSTALL. Everything here ships with the ESP32 Arduino
 *  core (3.x): Wire, Preferences, BLE. The IMU is driven with a few raw
 *  register reads instead of Adafruit's library - because
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
 *  SERIAL 115200 - type HELP. Every bench check uses one of these
 *  commands, so this is the only firmware you ever flash.
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

#define FW_VERSION "2.3.0"

// ----------------------------------------------------------------- pins
#define PIN_PPG     4
#define PIN_NTC_C   5          // air thermistor (was pulse sensor B before v5)
#define PIN_NTC_A   6
#define PIN_NTC_B   7
#define PIN_VBAT    8
#define PIN_SDA    17
#define PIN_SCL    18

// The demo board's three dividers are built upside down: 3V3 -> thermistor ->
// node -> R1/R2/R3 -> GND (the diagram has the 10k on the 3V3 side). Heat read
// as cold until the firmware flipped them (ntcNodeMv). If a divider is rewired
// to match the diagram, set its line to 0, reflash and run CAL again.
#define NTC_A_ON_TOP 1         // skin A, R1
#define NTC_B_ON_TOP 1         // skin B, R2
#define NTC_C_ON_TOP 1         // air C, R3

// ------------------------------------------------------------------ BLE
#define BLE_NAME   "Ember"
#define UUID_SVC   "e3b10001-5a2f-4c8e-9b7d-656d62657200"
#define UUID_LIVE  "e3b10002-5a2f-4c8e-9b7d-656d62657200"   // notify, 20 B, 1 Hz
#define UUID_CMD   "e3b10003-5a2f-4c8e-9b7d-656d62657200"   // write, ASCII command

// -------------------------------------------------------------- buffers
// Written by the sampler task on core 0, read by loop() on core 1.
static const int PPG_N = 800;          // 8 s at 100 Hz
static const int ACC_N = 400;          // 8 s at 50 Hz
static float ppg[PPG_N];
static float accBuf[ACC_N];
static int ppgHead = 0, accHead = 0;
static uint32_t sat = 0;               // samples at the ADC rails this second
static float ntcAmV = NAN, ntcBmV = NAN, ntcCmV = NAN, vbatmV = NAN;
static float accX = NAN, accY = NAN, accZ = NAN;
static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;

static NtcParams ntcP;                 // thermistor and divider constants
static QueueHandle_t rawQ;             // raw PPG for the PPG plotter command
static volatile bool streamPpg = false;

static TaskHandle_t samplerTask = nullptr;
static volatile bool i2cPaused = false;   // loop() borrows the bus for SCAN
static bool haveImu = false;
static uint8_t imuAddr = 0x68, imuWho = 0;

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

static float readMilliVoltsAvg(int pin, int n) {
  uint32_t s = 0;
  for (int i = 0; i < n; i++) s += analogReadMilliVolts(pin);
  return (float)s / n;
}

// ---------------------------------------------------------- sampler task
// Core 0, every 10 ms, never blocks for long. Owns the ADC and the I2C
// bus, so nothing else touches them while it runs.

static void samplerLoop(void *) {
  Prefilter pf(PPG_HP_A, PPG_LP_A), pfAcc(ACC_HP_A, ACC_LP_A);
  TickType_t last = xTaskGetTickCount();
  uint32_t tick = 0;
  for (;;) {
    vTaskDelayUntil(&last, pdMS_TO_TICKS(10));
    tick++;

    int a = analogRead(PIN_PPG);
    float fa = pf.step((float)a);
    portENTER_CRITICAL(&mux);
    ppg[ppgHead] = fa;
    ppgHead = (ppgHead + 1) % PPG_N;
    if (a <= 8 || a >= 4087) sat++;
    portEXIT_CRITICAL(&mux);
    if (streamPpg) { uint16_t raw = (uint16_t)a; xQueueSend(rawQ, &raw, 0); }

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
      // Flipped here, once, so CAL, TEMP and the frame all see the same
      // value. TEMP's mV for a flipped bead is then the standard divider's
      // equivalent (3300 minus the pin voltage), not what a multimeter shows.
      float na = ntcNodeMv(readMilliVoltsAvg(PIN_NTC_A, 16), NTC_A_ON_TOP, ntcP);
      float nb = ntcNodeMv(readMilliVoltsAvg(PIN_NTC_B, 16), NTC_B_ON_TOP, ntcP);
      float nc = ntcNodeMv(readMilliVoltsAvg(PIN_NTC_C, 16), NTC_C_ON_TOP, ntcP);
      float vb = readMilliVoltsAvg(PIN_VBAT, 16);
      portENTER_CRITICAL(&mux);
      ntcAmV = na; ntcBmV = nb; ntcCmV = nc; vbatmV = vb;
      portEXIT_CRITICAL(&mux);
    }
  }
}

// ----------------------------------------------------------- persistent
// "cal" covers the skin beads A and B (it gates the skin doubt); "calC" the
// air bead, new in 2.2. A board calibrated under 2.1 has "cal" (against the
// SHT40) and no "calC": CAL then keeps A and B and calibrates C against them.
Preferences prefs;
static float calA = 1.0f, calB = 1.0f, calC = 1.0f;
static bool calibrated = false, calAir = false;

static void loadCal() {
  prefs.begin("ember", true);
  calA = prefs.getFloat("kA", 1.0f);
  calB = prefs.getFloat("kB", 1.0f);
  calC = prefs.getFloat("kC", 1.0f);
  calibrated = prefs.getBool("cal", false);
  calAir = prefs.getBool("calC", false);
  prefs.end();
}

static void saveCal() {
  prefs.begin("ember", false);
  prefs.putFloat("kA", calA);
  prefs.putFloat("kB", calB);
  prefs.putFloat("kC", calC);
  prefs.putBool("cal", calibrated);
  prefs.putBool("calC", calAir);
  prefs.end();
}

// --------------------------------------------------------------- state
static ECTemp ect;
static Correction corrector;           // learned correction on top of ect (2.3)
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
static double calSum[NTC_BEADS];           // per bead: A, B, C (node mV)
static float calMin[NTC_BEADS], calMax[NTC_BEADS];
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
  Channel ch; Periodicity p, cad; HeartRate hr;
  float tA, tB, tC; SkinResult skin; float airC;
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
    if (a == 0x68 || a == 0x69) Serial.print("  IMU (GY-521 / ITG-MPU)");
    Serial.println();
    n++;
  }
  Serial.printf("# %d device(s). Expect 1: 0x68.\n", n);
  if (haveImu) Serial.printf("# IMU WHO_AM_I = 0x%02X (%s)\n", imuWho,
      imuWho == 0x68 ? "MPU-6050" : imuWho == 0x70 ? "MPU-6500" :
      imuWho == 0x72 ? "MPU-6050 clone" : "unknown clone - accel still works");
  i2cPaused = false;
}

static void printHelp() {
  Serial.println(
    "# EMBER commands (serial 115200, or written to the BLE command characteristic)\n"
    "#  bring-up\n"
    "#   SCAN      I2C scan - expect 0x68 IMU\n"
    "#   PPG       raw pulse sensor at 100 Hz for Tools > Serial Plotter\n"
    "#   HR        heart rate, signal quality, cadence check, 1 Hz\n"
    "#   TEMP      thermistors (mV, kOhm, C): skin A, skin B, air C, 1 Hz\n"
    "#   IMU       accelerometer, activity, step cadence, 1 Hz\n"
    "#   BATT      battery voltage and percent, 1 Hz\n"
    "#   STATUS    everything, once\n"
    "#  calibration and use\n"
    "#   CAL       calibrate the three thermistors against each other (30 s)\n"
    "#   CALSLEEP  sleep 20 min to cool, then CAL. Laptop USB only: a power\n"
    "#             bank switches off while the board sleeps\n"
    "#   CALCLEAR  forget the calibration\n"
    "#   BASELINE  5 min seated rest: personal resting HR and starting core temp\n"
    "#   START     CSV log at 1 Hz        STOP  stop logging / streaming\n"
    "#   SLEEP     deep sleep (~2 mA); press RST to wake\n"
    "#   ID        version and configuration\n"
    "#  any new command stops a running stream");
}

// The air bead's latest temperature, NAN if it isn't reading.
static float latestAirC() {
  float mv;
  portENTER_CRITICAL(&mux); mv = ntcCmV; portEXIT_CRITICAL(&mux);
  return airTemp(ntcTempC(mv, calC, ntcP));
}

static void printId() {
  Serial.printf("# EMBER v%s - one pulse sensor, three thermistors (2 skin, 1 air), IMU, BLE\n", FW_VERSION);
  Serial.printf("# coefficient check %s\n", coefficientsSane() ? "PASS" : "FAIL");
  Serial.printf("# conformal %.0f%% level, %d strata, measured coverage %.1f%% (%.1f%% before baseline)\n",
                CONF_LEVEL * 100, CONF_N_STRATA, CONF_MEASURED_COV * 100, CONF_RAW_MEASURED_COV * 100);
  Serial.printf("# learned correction: %s (max +/- %.1f C)\n",
                corrector.on ? "on" : baselineValid ? "off until a heart rate" : "off until BASELINE",
                CORR_MAX_C);
  Serial.printf("# never withholds the number at or above %.1f C\n", CT_WATCH_C);
  float air = latestAirC();
  if (isnan(air)) Serial.printf("# sensors: IMU %s, air thermistor NO\n", haveImu ? "yes" : "NO");
  else Serial.printf("# sensors: IMU %s, air thermistor yes (%.1f C)\n", haveImu ? "yes" : "NO", air);
  const char *cal = calibrated && calAir ? "yes"
                  : calibrated ? "skin yes, air NO - run CAL (calibrates air against skin)"
                  : "NO - run CAL (skin checks are off until then)";
  Serial.printf("# thermistor calibration: %s (kA %.4f, kB %.4f, kC %.4f)\n", cal, calA, calB, calC);
  Serial.printf("# baseline: %s\n", baselineValid ? "captured" : "not captured - run BASELINE");
  Serial.printf("# BLE name \"%s\", %s\n", BLE_NAME, bleConnected ? "app connected" : "advertising");
}

static void csvHeader() {
  Serial.println("ms,hr,sqi,hr_q,step_hz,act_g,skinA,skinB,skin,skin_q,air_c,vbat,"
                 "ct_est,ct_lo,ct_hi,kalman_half,filter_step,state,flags");
}

// A board calibrated under 2.1 (skin beads against the SHT40) keeps A and B
// and calibrates only C against them. CALCLEAR first to redo all three.
static bool calKeepsSkin() { return calibrated && !calAir; }

static void startCal() {
  calRunning = true; calSec = 0;
  for (int i = 0; i < NTC_BEADS; i++) { calSum[i] = 0; calMin[i] = 1e9f; calMax[i] = -1e9f; }
  Serial.println("# CAL: all three thermistors must be at the SAME temperature.");
  Serial.println("# Device unpowered at room temperature for 30+ min, the air bead");
  Serial.println("# lying beside the case, nothing warm nearby. Collecting 30 s...");
  if (calKeepsSkin())
    Serial.println("# skin beads keep their SHT40 calibration; calibrating the air bead against them.");
}

static void finishCal() {
  calRunning = false;
  const NtcParams p = ntcP;
  const char *name[NTC_BEADS] = {"skin A", "skin B", "air C"};
  float mv[NTC_BEADS], k[NTC_BEADS] = {calA, calB, calC};
  bool keep[NTC_BEADS] = {calKeepsSkin(), calKeepsSkin(), false};
  for (int i = 0; i < NTC_BEADS; i++) {
    mv[i] = calSum[i] / CAL_SEC;
    if (isnan(ntcTempC(mv[i], 1.0f, p))) {
      Serial.printf("# CAL FAILED: %s reads open or short. Check wiring.\n", name[i]);
      return;
    }
    float drift = fabsf(ntcTempC(calMin[i], 1.0f, p) - ntcTempC(calMax[i], 1.0f, p));
    if (!(drift <= CAL_DRIFT_C)) {         // also catches a bead that went open mid-CAL
      Serial.printf("# CAL FAILED: %s moved %.2f C in 30 s - still settling. Wait and retry.\n",
                    name[i], drift);
      return;
    }
  }
  float ref = NAN;
  CalStatus st = ntcCalibrate(mv, NTC_BEADS, keep, k, p, &ref);
  for (int i = 0; i < NTC_BEADS; i++)
    Serial.printf("# %-6s %6.0f ohm (raw %.2f C)%s\n", name[i], ntcResistance(mv[i], p),
                  ntcTempC(mv[i], 1.0f, p), keep[i] ? "  kept" : "");
  if (st == CAL_OPEN_OR_SHORT) {
    Serial.println("# CAL FAILED: a thermistor reads open or short. Check wiring.");
    return;
  }
  if (st == CAL_BEADS_APART) {
    Serial.printf("# CAL FAILED: the beads are more than %.1f C apart. They are not at the\n", CAL_MAX_APART_C);
    Serial.println("# same temperature (one in a hand or on skin?), or a divider is miswired:");
    Serial.println("# check R1-R3 are 10k, wired 3V3 -> 10k -> node -> thermistor -> GND.");
    return;
  }
  if (st == CAL_NOT_ROOM) {
    Serial.printf("# CAL FAILED: the beads agree on %.1f C, which is not room temperature\n", ref);
    Serial.printf("# (%.0f-%.0f C). Calibrate indoors, or check R1-R3 are all 10k.\n", CAL_ROOM_LO, CAL_ROOM_HI);
    return;
  }
  calA = k[0]; calB = k[1]; calC = k[2];
  calibrated = true; calAir = true;
  saveCal();
  Serial.printf("# CAL saved (kA %.4f, kB %.4f, kC %.4f). Beads now read %.2f / %.2f / %.2f C,\n",
                calA, calB, calC, ntcTempC(mv[0], calA, p), ntcTempC(mv[1], calB, p), ntcTempC(mv[2], calC, p));
  Serial.printf("# %s %.2f C.\n", keep[0] ? "against the skin beads'" : "their shared reference", ref);
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
  else if (s == "CALCLEAR") { calA = calB = calC = 1.0f; calibrated = calAir = false; saveCal();
                              Serial.println("# calibration cleared"); }
  else if (s == "BASELINE") {
    float shown = corrector.estimate(ect.clamped());
    if (!baselineAllowed(shown, everUpdated)) {
      Serial.printf("# BASELINE ignored: estimate %.2f C is at or above %.1f C. Cool down first.\n",
                    shown, CT_WATCH_C);
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

static float buf[PPG_N], bufAcc[ACC_N];

static void analyse() {
  uint32_t sats; float nA, nB, nC, vb;
  portENTER_CRITICAL(&mux);
  for (int i = 0; i < PPG_N; i++) buf[i] = ppg[(ppgHead + i) % PPG_N];   // oldest first
  for (int i = 0; i < ACC_N; i++) bufAcc[i] = accBuf[(accHead + i) % ACC_N];
  sats = sat; sat = 0;
  nA = ntcAmV; nB = ntcBmV; nC = ntcCmV; vb = vbatmV;
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
  Periodicity p = periodicity(buf, PPG_N, PPG_FS, HR_MIN / 60.0f, HR_MAX / 60.0f);
  Channel ch = judgeChannel(p, sats > 5);
  cadenceCheck(ch, stepHz, moving, hrRef.hr);
  HeartRate hr = heartRateOf(ch);

  // skin, air, battery
  float tA = ntcTempC(nA, calA, ntcP), tB = ntcTempC(nB, calB, ntcP);
  SkinResult skin = fuseSkin(tA, tB);
  float tC = ntcTempC(nC, calC, ntcP);
  float airC = airTemp(tC);
  float vbat = 2.0f * vb / 1000.0f;
  bool battPresent = vbat > 2.5f;               // below: no battery, running on USB

  // the filter steps once a minute
  lastStepKind = 0;
  if (!isnan(hr.hr)) { minuteHrSum += hr.hr; minuteHrN++; }
  if (++secInMinute >= 60) {
    float minuteHr = NAN;
    if (minuteHrN >= MIN_GOOD_SEC_PER_MINUTE) {
      minuteHr = (float)(minuteHrSum / minuteHrN);
      hrRef.endMinute(minuteHr);
      ect.update(minuteHr);
      everUpdated = true; coastMinutes = 0; lastStepKind = 1;
    } else {
      hrRef.endMinute(NAN);
      ect.coast(); coastMinutes++; lastStepKind = 2;
    }
    // Same cadence as the filter: once a minute, after its step.
    corrector.step(minuteHr, ect.clamped(), baselineValid ? restHr : NAN);
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
      float shown = corrector.estimate(ect.clamped());
      if (!baselineAllowed(shown, everUpdated)) {
        Serial.printf("# baseline CANCELLED: estimate rose to %.2f C during it. Not resetting.\n", shown);
      } else if (baseN >= 120) {
        restHr = baseSum / baseN; baselineValid = true;
        ect.initFromRestingHr(restHr);
        corrector.reset();                 // new filter start: new history
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
    const float mv[NTC_BEADS] = {nA, nB, nC};
    if (isnan(nA) || isnan(nB) || isnan(nC)) {
      calRunning = false; Serial.println("# CAL FAILED: a thermistor is not reading yet. Retry in a few seconds.");
    } else {
      for (int i = 0; i < NTC_BEADS; i++) {
        calSum[i] += mv[i];
        calMin[i] = fminf(calMin[i], mv[i]); calMax[i] = fmaxf(calMax[i], mv[i]);
      }
      if (++calSec >= CAL_SEC) finishCal();
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

  // decision. ct is the estimate on screen: corrected once a baseline is
  // captured, the filter's own before that. Every decision below uses it.
  float ctFilter = ect.clamped();
  float ct = corrector.estimate(ctFilter);
  float half = calibratedHalf(ct, corrector.on, coastMinutes);
  Inputs in{};
  in.ctEst = ct;
  in.hr = hr.hr;
  in.cadenceLockSeen = ch.cadenceLocked;
  in.coastMinutes = coastMinutes; in.everUpdated = everUpdated;
  in.skinC = skin.tC; in.skinQ = skin.q;
  in.haveAir = !isnan(airC);
  in.haveImu = haveImu; in.activityG = activityG; in.secSinceMoving = secSinceMoving;
  in.baselineValid = baselineValid; in.baselineRunning = baselineRunning; in.restHr = restHr;
  in.calibrated = calibrated; in.lowBatt = lowBattSec >= 30;
  uint16_t flags = confoundFlags(in);
  State st = stateFromFlags(flags, ct);

  snap.ch = ch; snap.p = p; snap.cad = cad; snap.hr = hr;
  snap.tA = tA; snap.tB = tB; snap.tC = tC; snap.skin = skin; snap.airC = airC;
  snap.vbat = vbat; snap.battPresent = battPresent;
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
    f.skinC = skin.tC; f.airC = airC;
    f.battPct = snap.battPct; f.activityG = activityG;
    uint8_t b[PACKET_LEN];
    encodeFrame(f, b);
    liveChr->setValue(b, PACKET_LEN);
    liveChr->notify();
  }

  // to the serial port
  if (logging) {
    Serial.printf("%lu,%.1f,%.2f,%d,%.2f,%.3f,%.2f,%.2f,%.2f,%d,%.2f,%.2f,"
                  "%.3f,%.3f,%.3f,%.3f,%d,%d,0x%04X\n",
                  millis(), hr.hr, p.sqi, (int)hr.q, stepHz, activityG,
                  tA, tB, skin.tC, (int)skin.q, airC, vbat,
                  ct, ct - half, ct + half, snap.kalmanHalf, lastStepKind, (int)st, flags);
  }
  switch (stream) {
    case S_HR:
      Serial.printf("HR %5.1f bpm sqi %.2f %s%s%s | cadence %.2f Hz\n",
        hr.hr, p.sqi, hr.q == HRQ_OK ? "OK" : "NONE",
        ch.cadenceLocked ? " CADENCE" : "", sats > 5 ? " SAT" : "", stepHz);
      break;
    case S_TEMP:
      Serial.printf("A %4.0f mV %5.2f k %5.2f C | B %4.0f mV %5.2f k %5.2f C | skin %5.2f %s | air C %4.0f mV %5.2f k %5.2f C\n",
        nA, ntcResistance(nA, ntcP) / 1000.0f / calA, tA,
        nB, ntcResistance(nB, ntcP) / 1000.0f / calB, tB, skin.tC,
        skin.q == SKIN_AGREED ? "AGREED" : skin.q == SKIN_SINGLE ? "SINGLE" :
        skin.q == SKIN_DISAGREE ? "DISAGREE" : "NONE",
        nC, ntcResistance(nC, ntcP) / 1000.0f / calC, airC);
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
      Serial.printf("# HR %.1f (sqi %.2f) q%d%s\n", hr.hr, p.sqi, (int)hr.q, ch.cadenceLocked ? " CADENCE" : "");
      Serial.printf("# skin A %.2f  B %.2f  -> %.2f q%d   air %.2f C\n",
                    tA, tB, skin.tC, (int)skin.q, airC);
      Serial.printf("# activity %.3f g  cadence %.2f Hz   battery %.2f V\n", activityG, stepHz, vbat);
      Serial.printf("# core %.2f +/- %.2f C (Kalman would claim +/- %.2f)  state %s  flags 0x%04X  %s\n",
                    ct, half, snap.kalmanHalf, st == STATE_OK ? "OK" : st == STATE_CAUTION ? "CAUTION" : "REFUSE",
                    flags, flagReason(flags));
      if (corrector.on)
        Serial.printf("# filter %.2f C, learned correction %+.2f C\n", ctFilter, corrector.corr);
      else
        Serial.printf("# filter %.2f C, learned correction off (%s)\n", ctFilter,
                      baselineValid ? "no heart rate yet" : "no baseline yet");
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
  Wire.setClock(100000);               // 100 kHz is plenty for the IMU
  haveImu = imuInit();

  loadCal();
  for (int i = 0; i < PPG_N; i++) ppg[i] = 0;
  for (int i = 0; i < ACC_N; i++) accBuf[i] = 0;

  rawQ = xQueueCreate(256, sizeof(uint16_t));
  xTaskCreatePinnedToCore(samplerLoop, "sampler", 4096, nullptr, 3, &samplerTask, 0);

  bleStart();
  i2cScan();
  // Let the first thermistor reading land (1 Hz), so ID can say whether the air bead reads.
  for (uint32_t t0 = millis(); millis() - t0 < 1500; delay(10)) {
    float mv;
    portENTER_CRITICAL(&mux); mv = ntcCmV; portEXIT_CRITICAL(&mux);
    if (!isnan(mv)) break;
  }
  printId();
  if (calOnWake) {                     // woke from CALSLEEP: board is still cold
    calOnWake = 0;
    calStartIn = 5;                    // let the first thermistor readings land
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
    uint16_t raw;
    while (xQueueReceive(rawQ, &raw, 0) == pdTRUE) Serial.printf("ppg:%u\n", raw);
  }

  uint32_t now = millis();
  if (now - lastTick >= 1000) {
    lastTick += 1000;
    if (now - lastTick > 3000) lastTick = now;   // don't try to catch up after a stall
    analyse();
  }
  delay(2);
}
