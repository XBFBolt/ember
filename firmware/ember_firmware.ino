/*
 * ================================================================
 *  EMBER  -  an honest core-temperature estimator
 *  ESP32-S3 firmware  ·  chest-mounted, single unit
 * ================================================================
 *
 *  FORM FACTOR
 *    ONE unit, mounted on the same chest strap as a commercial
 *    heart-rate sensor (Polar H10 class). The strap is bought and
 *    sealed; it broadcasts heart rate over Bluetooth. Everything
 *    else lives in the unit you build, pressed against the sternum.
 *
 *  WHAT THIS DEVICE CLAIMS
 *    Not "your core temperature is 38.4 C".
 *    It claims: "based on heart rate alone, which is a confounded
 *    signal, your core temperature is probably in this range - and
 *    here is when I cannot tell."
 *
 *  WHY CHEST MOUNTING IS THE RIGHT CHOICE
 *    - Chest is a validated skin-temperature site. PROSPIE, the
 *      dataset we calibrate against, has a chest skin-temp column,
 *      so our sensor site matches our calibration site.
 *    - A trunk-mounted IMU reads activity better than an arm one.
 *    - One strap instead of two.
 *
 *  THE CONSEQUENCE, AND WHY IT IS AN UPGRADE
 *    A sensor on the chest under clothing cannot measure ambient air.
 *    It measures MICROCLIMATE - the air trapped between skin and
 *    clothing. That is not a downgrade from an ambient index like
 *    WBGT. It is the better variable, because heat strain is caused
 *    by the failure of evaporative cooling AT THE SKIN, and the
 *    microclimate is where that failure happens.
 *
 *    So instead of WBGT we compute EVAPORATIVE HEADROOM: the water
 *    vapour pressure gradient from the skin to the microclimate,
 *    which is the physical driving force for sweat evaporation.
 *
 *        headroom = es(T_skin) - RH_micro/100 * es(T_micro)   [kPa]
 *
 *    When headroom approaches zero, sweat cannot evaporate and the
 *    body has lost its main cooling route. That single number is
 *    both a danger signal in its own right and the evidence that a
 *    high heart rate really does have a thermal explanation.
 *
 *    The firefighter dataset (DOI 10.17632/7ghxcsd9sz.1) records
 *    under-PPE microclimate temperature and humidity, so this
 *    variable can be validated against real data.
 *
 *  THREE THINGS NO SHIPPING PRODUCT DOES
 *   1. The interval on screen is CALIBRATED, from conformal_table.h,
 *      generated from real rectal measurements. The Kalman posterior
 *      variance is computed too, but ONLY so you can demonstrate how
 *      badly it under-covers. Never display it as a confidence
 *      interval.
 *   2. The device REFUSES when the signals disagree or the estimate
 *      falls outside its calibrated range.
 *   3. Three sensors vote on whether a high heart rate is thermal
 *      at all.
 *
 *  HARDWARE   all four I2C devices on SDA=GPIO8, SCL=GPIO9
 *    SSD1306 128x64 OLED        0x3C   faces outward on the unit
 *    MAX30205 skin temperature  0x48   flush with the back face,
 *                                      sprung against the sternum
 *    SHT40 microclimate T + RH  0x44   vented to the space between
 *                                      the unit and clothing
 *    MPU-6050 IMU               0x68   rigid inside the unit
 *    piezo buzzer               GPIO14
 *
 *  LIBRARIES
 *    NimBLE-Arduino, Adafruit SSD1306 + GFX, Adafruit SHT4x,
 *    Adafruit MPU6050 + Unified Sensor
 *
 *  SERIAL 115200.  ID  SCAN  BASELINE  START  STOP
 *
 *  NOT A MEDICAL DEVICE. Bench demonstrator, consenting adults.
 * ================================================================
 */

#include <NimBLEDevice.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_SHT4x.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <math.h>

#include "conformal_table.h"

// ---------------------------------------------------------------- pins
#define PIN_SDA     8
#define PIN_SCL     9
#define PIN_BUZZER  14

#define OLED_W 128
#define OLED_H  64
#define ADDR_OLED     0x3C
#define ADDR_MAX30205 0x48
#define ADDR_SHT40    0x44
#define ADDR_MPU6050  0x68

// ------------------------------------------------------------- timing
#define STEP_MS        5000UL
#define HR_WINDOW_MS  30000UL
#define IMU_HZ            50
#define IMU_BUF          256
#define STALE_HR_MS   30000UL
#define CT_ALERT_C      38.5f

// Evaporative headroom thresholds, kPa. Tune these on your own
// recordings in build step E-08 and write down what you chose.
#define HEADROOM_CRITICAL  0.8f    // below: sweat cannot evaporate
#define HEADROOM_AMPLE     2.5f    // above: plenty of cooling capacity

// -------------------------------------------- ECTemp published params
//  HR = B2*CT^2 + B1*CT + B0
//  Buller et al. 2013; constants per USARIEM TR T17-08 and US patent
//  application 2014/0180027 A1. DO NOT retype. Run checkCoefficients().
static const float B2 = -4.5714f;
static const float B1 = 384.4286f;
static const float B0 = -7887.1f;
static const float GAMMA_SQ_PER_MIN = 0.000484f;
static const float SIGMA_SQ         = 356.4544f;
static const float CT_MIN = 35.0f, CT_MAX = 41.5f;

float ct = 37.1f;
float vv = 0.0f;
float gammaSqStep = GAMMA_SQ_PER_MIN * (STEP_MS / 60000.0f);

static inline float hrFromCt(float c) { return B2 * c * c + B1 * c + B0; }
static inline float dhrDct(float c)   { return 2.0f * B2 * c + B1; }

float ctFromHr(float hr) {
  float a = B2, b = B1, c = B0 - hr;
  float disc = b * b - 4 * a * c;
  if (disc < 0) return NAN;
  return (-b + sqrtf(disc)) / (2 * a);
}

void filterUpdate(float hr) {
  float ctPred = ct;
  float vPred  = vv + gammaSqStep;
  float slope  = dhrDct(ctPred);
  float denom  = slope * slope * vPred + SIGMA_SQ;
  float k      = (denom != 0.0f) ? (vPred * slope) / denom : 0.0f;
  ct = ctPred + k * (hr - hrFromCt(ctPred));
  vv = fmaxf(0.0f, (1.0f - k * slope) * vPred);
}

bool checkCoefficients() {
  struct { float ct, lo, hi; } t[] = {
    {36.5f, 40, 75}, {37.0f, 65, 95}, {38.0f, 105, 135}, {39.0f, 135, 170}
  };
  bool ok = true;
  for (auto &c : t) {
    float hr = hrFromCt(c.ct);
    bool g = (hr >= c.lo && hr <= c.hi);
    ok &= g;
    Serial.printf("# coeff CT %.1f -> HR %6.1f  [%s]\n", c.ct, hr, g ? "ok" : "BAD");
  }
  float peak = -B1 / (2.0f * B2);
  ok &= (peak > 41.0f);
  Serial.printf("# model peaks at %.2f C  [%s]\n", peak, peak > 41.0f ? "ok" : "BAD");
  return ok;
}

// ------------------------------------------------------- psychrometrics

/* Saturation vapour pressure, Magnus formula, kPa. */
float satVapourKpa(float tC) {
  if (isnan(tC)) return NAN;
  return 0.6112f * expf(17.62f * tC / (243.12f + tC));
}

/* Actual vapour pressure of the microclimate, kPa. */
float vapourKpa(float tC, float rhPct) {
  if (isnan(tC) || isnan(rhPct)) return NAN;
  return (fminf(fmaxf(rhPct, 0.0f), 100.0f) / 100.0f) * satVapourKpa(tC);
}

/*
 * EVAPORATIVE HEADROOM, kPa.
 *
 * The driving gradient for sweat evaporation: saturated vapour pressure
 * at the skin surface, minus the actual vapour pressure of the air
 * touching it. Near zero means the skin is sitting in air that is already
 * saturated at skin temperature - sweat forms, does not evaporate, and
 * the body's main cooling route has failed.
 *
 * This is the mechanism of heat strain, measured directly, with two
 * sensors that cost $17 together.
 */
float evaporativeHeadroom(float skinC_, float microC, float microRh) {
  float es = satVapourKpa(skinC_);
  float e  = vapourKpa(microC, microRh);
  if (isnan(es) || isnan(e)) return NAN;
  return es - e;
}

// ------------------------------------------------------------ hardware

Adafruit_SSD1306 oled(OLED_W, OLED_H, &Wire, -1);
Adafruit_SHT4x sht;
Adafruit_MPU6050 mpu;

bool haveOled = false, haveSkin = false, haveMicro = false, haveImu = false;

float skinC = NAN, microC = NAN, microRh = NAN, headroom = NAN;
float actRms = 0.0f, stepHz = 0.0f;

/* MAX30205: 16-bit two's complement in reg 0x00, 0.00390625 C per LSB. */
float readMax30205() {
  Wire.beginTransmission(ADDR_MAX30205);
  Wire.write(0x00);
  if (Wire.endTransmission(false) != 0) return NAN;
  if (Wire.requestFrom(ADDR_MAX30205, (uint8_t)2) != 2) return NAN;
  int16_t raw = ((int16_t)Wire.read() << 8) | Wire.read();
  return raw * 0.00390625f;
}

// ----------------------------------------------------------- IMU state

float accBuf[IMU_BUF];
int accHead = 0;
uint32_t lastImuUs = 0;

void imuSample() {
  if (!haveImu) return;
  uint32_t now = micros();
  if (now - lastImuUs < (1000000UL / IMU_HZ)) return;
  lastImuUs = now;
  sensors_event_t a, g, t;
  mpu.getEvent(&a, &g, &t);
  float mag = sqrtf(a.acceleration.x * a.acceleration.x +
                    a.acceleration.y * a.acceleration.y +
                    a.acceleration.z * a.acceleration.z);
  accBuf[accHead] = mag - 9.81f;
  accHead = (accHead + 1) % IMU_BUF;
}

/*
 * Activity level and a crude step frequency. Trunk mounting makes both
 * better than an arm would: the chest moves with the whole body rather
 * than swinging independently.
 *
 * Step frequency matters for one specific reason: if you ever drive this
 * from an OPTICAL pulse sensor, motion artifact appears at cadence, so a
 * reported heart rate near 60 * stepHz is artifact, not pulse.
 */
void imuFeatures() {
  if (!haveImu) { actRms = 0; stepHz = 0; return; }
  float mean = 0;
  for (int i = 0; i < IMU_BUF; i++) mean += accBuf[i];
  mean /= IMU_BUF;
  float ss = 0; int crossings = 0;
  for (int i = 0; i < IMU_BUF - 1; i++) {
    float v = accBuf[i] - mean;
    float w = accBuf[i + 1] - mean;
    ss += v * v;
    if ((v < 0 && w >= 0) || (v >= 0 && w < 0)) crossings++;
  }
  actRms = sqrtf(ss / (IMU_BUF - 1));
  stepHz = (crossings / 2.0f) / ((float)IMU_BUF / IMU_HZ);
}

// ------------------------------------------------------------- BLE HR

static NimBLEUUID SVC_HR((uint16_t)0x180D);
static NimBLEUUID CHR_HR((uint16_t)0x2A37);

volatile bool hrConnected = false;
float hrBuf[64]; uint32_t hrBufT[64]; int hrHead = 0;
uint32_t lastHrMs = 0;

void pushHr(float hr) {
  hrBuf[hrHead] = hr; hrBufT[hrHead] = millis();
  hrHead = (hrHead + 1) % 64;
  lastHrMs = millis();
}

float meanHr() {
  uint32_t now = millis(); float s = 0; int n = 0;
  for (int i = 0; i < 64; i++)
    if (hrBufT[i] && (now - hrBufT[i]) <= HR_WINDOW_MS) { s += hrBuf[i]; n++; }
  return n ? s / n : -1.0f;
}

void onHrNotify(NimBLERemoteCharacteristic*, uint8_t* d, size_t len, bool) {
  if (len < 2) return;
  uint8_t flags = d[0]; uint16_t hr;
  if (flags & 0x01) { if (len < 3) return; hr = d[1] | (d[2] << 8); }
  else              { hr = d[1]; }
  if (hr >= 30 && hr <= 230) pushHr((float)hr);
}

class ClientCb : public NimBLEClientCallbacks {
  void onDisconnect(NimBLEClient*) override {
    hrConnected = false;
    Serial.println("# strap disconnected, rescanning");
    NimBLEDevice::getScan()->start(0, nullptr, false);
  }
} clientCb;

bool connectTo(const NimBLEAdvertisedDevice* dev) {
  NimBLEClient* cli = NimBLEDevice::createClient();
  cli->setClientCallbacks(&clientCb, false);
  if (!cli->connect(dev)) { NimBLEDevice::deleteClient(cli); return false; }
  auto* svc = cli->getService(SVC_HR);
  if (!svc) { cli->disconnect(); return false; }
  auto* chr = svc->getCharacteristic(CHR_HR);
  if (!chr || !chr->canNotify() || !chr->subscribe(true, onHrNotify)) {
    cli->disconnect(); return false;
  }
  hrConnected = true;
  Serial.printf("# connected to %s\n", dev->getName().c_str());
  return true;
}

class ScanCb : public NimBLEScanCallbacks {
  void onResult(const NimBLEAdvertisedDevice* dev) override {
    if (dev->isAdvertisingService(SVC_HR)) {
      NimBLEDevice::getScan()->stop();
      connectTo(dev);
    }
  }
} scanCb;

// -------------------------------------------------- personal baseline

struct Baseline {
  bool valid = false;
  float restHr = NAN;
  float restSkin = NAN;
  float restHeadroom = NAN;
} base;

// ------------------------------------------------- confound detector

enum DeviceState { STATE_OK, STATE_CAUTION, STATE_REFUSE };

#define F_MOTIONLESS_TACHY  0x01
#define F_NO_THERMAL_LOAD   0x02
#define F_COOL_SKIN         0x04
#define F_STALE_HR          0x08
#define F_WIDE_INTERVAL     0x10
#define F_NO_BASELINE       0x20
#define F_CADENCE_LOCK      0x40
#define F_EVAP_FAILING      0x80   // not a doubt - a danger signal

/*
 * The estimator cannot tell WHY a heart rate is high. These checks ask
 * whether the rest of the body agrees that heat is the explanation.
 * Each one is deliberately simple and each is defensible out loud.
 */
uint8_t confoundFlags(float hr, float ctEst) {
  uint8_t f = 0;

  if (millis() - lastHrMs > STALE_HR_MS || hr <= 0) f |= F_STALE_HR;
  if (!base.valid) f |= F_NO_BASELINE;

  // 1. Elevated heart rate while essentially motionless. The caffeine,
  //    anxiety, illness and dehydration signature. Heat strain at rest
  //    exists but develops slowly; a fast rise at rest is suspicious.
  if (base.valid && hr > base.restHr + 25.0f && actRms < 0.35f)
    f |= F_MOTIONLESS_TACHY;

  // 2. There is no thermal load to explain anything. Plenty of
  //    evaporative headroom AND skin not warm means the body is shedding
  //    heat without difficulty, so a high heart rate is coming from
  //    somewhere else.
  if (!isnan(headroom) && headroom > HEADROOM_AMPLE &&
      !isnan(skinC) && skinC < 33.0f)
    f |= F_NO_THERMAL_LOAD;

  // 3. Skin frankly cool. During work skin temperature FALLS as sweat
  //    evaporates, so this alone is weak evidence - it only counts
  //    alongside ample headroom, which is why it is a separate flag.
  if (!isnan(skinC) && skinC < 31.0f) f |= F_COOL_SKIN;

  // 4. Cadence lock. Only meaningful with an optical heart-rate source;
  //    harmless to leave enabled with a chest strap.
  if (stepHz > 0.8f && hr > 0 && fabsf(hr - 60.0f * stepHz) < 6.0f)
    f |= F_CADENCE_LOCK;

  // 5. The calibrated interval is too wide to be useful here.
  if (conformal_should_refuse(ctEst)) f |= F_WIDE_INTERVAL;

  // 6. NOT a doubt. Evaporative cooling has failed: the air against the
  //    skin is nearly saturated at skin temperature. This RAISES
  //    confidence that a rising estimate is real, and is worth showing
  //    on its own even when the estimate is still normal.
  if (!isnan(headroom) && headroom < HEADROOM_CRITICAL) f |= F_EVAP_FAILING;

  return f;
}

DeviceState stateFromFlags(uint8_t f) {
  if (f & (F_STALE_HR | F_WIDE_INTERVAL | F_CADENCE_LOCK)) return STATE_REFUSE;

  // Evaporative failure corroborates a thermal explanation, so it
  // cancels one doubt rather than adding to them.
  int doubts = 0;
  if (f & F_MOTIONLESS_TACHY) doubts++;
  if (f & F_NO_THERMAL_LOAD)  doubts++;
  if (f & F_COOL_SKIN)        doubts++;
  if (f & F_EVAP_FAILING)     doubts--;

  if (doubts >= 2) return STATE_REFUSE;
  if (doubts == 1 || (f & F_NO_BASELINE)) return STATE_CAUTION;
  return STATE_OK;
}

const char* flagReason(uint8_t f) {
  if (f & F_STALE_HR)         return "no heart rate";
  if (f & F_CADENCE_LOCK)     return "HR matches cadence";
  if (f & F_WIDE_INTERVAL)    return "outside calibration";
  if (f & F_MOTIONLESS_TACHY) return "high HR, no motion";
  if (f & F_NO_THERMAL_LOAD)  return "no thermal load";
  if (f & F_COOL_SKIN)        return "skin not warm";
  if (f & F_NO_BASELINE)      return "no baseline yet";
  return "";
}

// ------------------------------------------------------------- display

void drawScreen(float hr, float ctShow, float half, DeviceState st, uint8_t f) {
  if (!haveOled) return;
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);

  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.print("EMBER ");
  oled.print(hrConnected ? "strap" : "NO HR");
  if (f & F_EVAP_FAILING) { oled.setCursor(80, 0); oled.print("NO EVAP"); }

  if (st == STATE_REFUSE) {
    oled.setCursor(0, 18);
    oled.println("CANNOT ESTIMATE");
    oled.setCursor(0, 30);
    oled.println(flagReason(f));
  } else {
    oled.setTextSize(2);
    oled.setCursor(0, 15);
    oled.print(ctShow, 2);
    oled.setTextSize(1);
    oled.print(" C");
    if (st == STATE_CAUTION) { oled.setCursor(104, 15); oled.print("?"); }
    oled.setCursor(0, 34);
    oled.print("+/-");
    oled.print(half, 2);
    oled.print(" C  ");
    oled.print((int)(CONF_LEVEL * 100));
    oled.print("%");
  }

  oled.setCursor(0, 46);
  oled.print("HR ");
  if (hr > 0) oled.print(hr, 0); else oled.print("--");
  oled.print("  skin ");
  if (!isnan(skinC)) oled.print(skinC, 1); else oled.print("--");

  oled.setCursor(0, 56);
  oled.print("evap ");
  if (!isnan(headroom)) { oled.print(headroom, 2); oled.print("kPa"); }
  else oled.print("--");
  oled.print(actRms > 0.35f ? " MOVE" : " still");

  if (st == STATE_OK && ctShow >= CT_ALERT_C) {
    oled.fillRect(100, 30, 28, 14, SSD1306_WHITE);
    oled.setTextColor(SSD1306_BLACK);
    oled.setCursor(104, 34);
    oled.print("HOT");
    oled.setTextColor(SSD1306_WHITE);
  }
  oled.display();
}

// ---------------------------------------------------------- utilities

void i2cScan() {
  Serial.println("# I2C scan:");
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      Serial.printf("#   0x%02X", a);
      if (a == ADDR_OLED)     Serial.print("  OLED");
      if (a == ADDR_MAX30205) Serial.print("  MAX30205 skin");
      if (a == ADDR_SHT40)    Serial.print("  SHT40 microclimate");
      if (a == ADDR_MPU6050)  Serial.print("  MPU6050 IMU");
      Serial.println();
      n++;
    }
  }
  Serial.printf("# %d device(s). Expect 4.\n", n);
}

void readSensors() {
  if (haveSkin) {
    float t = readMax30205();
    if (!isnan(t) && t > 15 && t < 45) skinC = t;
  }
  if (haveMicro) {
    sensors_event_t h, t;
    if (sht.getEvent(&h, &t)) {
      microC  = t.temperature;
      microRh = h.relative_humidity;
    }
  }
  headroom = evaporativeHeadroom(skinC, microC, microRh);
}

void captureBaseline() {
  Serial.println("# BASELINE: sit still and quiet for 5 minutes.");
  Serial.println("# Sets CT0 from YOUR resting heart rate instead of assuming");
  Serial.println("# 37.1 C, and gives the confound detector a personal");
  Serial.println("# reference for what nothing-happening looks like on you.");
  uint32_t end = millis() + 300000UL;
  uint32_t nextLog = millis();
  double hrSum = 0, skinSum = 0, hrmSum = 0; int n = 0;
  while (millis() < end) {
    imuSample();
    if ((int32_t)(millis() - nextLog) >= 0) {
      nextLog += 2000;
      readSensors();
      float h = meanHr();
      if (h > 0) {
        hrSum += h;
        if (!isnan(skinC))    skinSum += skinC;
        if (!isnan(headroom)) hrmSum  += headroom;
        n++;
        Serial.printf("# baseline %3lus  HR %.0f  skin %.1f  evap %.2f\n",
                      (300000UL - (end - millis())) / 1000, h, skinC, headroom);
      }
    }
    delay(5);
  }
  if (n < 10) { Serial.println("# baseline FAILED - no heart rate"); return; }
  base.restHr       = hrSum / n;
  base.restSkin     = skinSum / n;
  base.restHeadroom = hrmSum / n;
  base.valid = true;

  float ct0 = ctFromHr(base.restHr);
  if (isnan(ct0)) ct0 = 37.1f;
  ct = fminf(fmaxf(ct0, 36.4f), 37.6f);
  vv = 0.0f;

  Serial.printf("# baseline ok: HR %.1f  skin %.1f  evap headroom %.2f kPa\n",
                base.restHr, base.restSkin, base.restHeadroom);
  Serial.printf("# CT0 = %.2f C, from this wearer's own resting HR\n", ct);
  tone(PIN_BUZZER, 1500, 120);
}

void printId() {
  Serial.println();
  Serial.println("# EMBER v2 - chest-mounted honest estimator");
  Serial.printf("# conformal: %.0f%% level, %d strata, MEASURED coverage %.1f%%\n",
                CONF_LEVEL * 100, CONF_N_STRATA, CONF_MEASURED_COV * 100);
  Serial.printf("# refuse when half-width > %.2f C\n", REFUSE_ABOVE_C);
  Serial.printf("# evap thresholds: critical %.2f, ample %.2f kPa\n",
                HEADROOM_CRITICAL, HEADROOM_AMPLE);
  Serial.printf("# sensors: oled %d skin %d micro %d imu %d\n",
                haveOled, haveSkin, haveMicro, haveImu);
  Serial.printf("# baseline %s\n", base.valid ? "captured" : "NOT CAPTURED");
}

// --------------------------------------------------------------- main

uint32_t lastStep = 0;
bool logging = false;

void setup() {
  Serial.begin(115200);
  delay(400);
  Serial.println("\n# EMBER starting");

  if (!checkCoefficients()) {
    Serial.println("# COEFFICIENT CHECK FAILED - halting");
    while (true) delay(1000);
  }
  Serial.println("# coefficient check PASS");

  pinMode(PIN_BUZZER, OUTPUT);
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);

  haveOled = oled.begin(SSD1306_SWITCHCAPVCC, ADDR_OLED);
  if (haveOled) {
    oled.clearDisplay(); oled.setTextColor(SSD1306_WHITE);
    oled.setCursor(0, 0); oled.println("EMBER"); oled.println("starting...");
    oled.display();
  }

  Wire.beginTransmission(ADDR_MAX30205);
  haveSkin = (Wire.endTransmission() == 0);

  haveMicro = sht.begin();
  if (haveMicro) {
    sht.setPrecision(SHT4X_HIGH_PRECISION);
    sht.setHeater(SHT4X_NO_HEATER);
  }

  haveImu = mpu.begin(ADDR_MPU6050);
  if (haveImu) {
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  }

  i2cScan();
  printId();

  for (int i = 0; i < 64; i++) { hrBuf[i] = 0; hrBufT[i] = 0; }
  for (int i = 0; i < IMU_BUF; i++) accBuf[i] = 0;

  NimBLEDevice::init("ember");
  auto* scan = NimBLEDevice::getScan();
  scan->setScanCallbacks(&scanCb, false);
  scan->setActiveScan(true);
  scan->start(0, nullptr, false);

  Serial.println("# commands: ID SCAN BASELINE START STOP");
  lastStep = millis();
}

void loop() {
  imuSample();

  if (Serial.available()) {
    String s = Serial.readStringUntil('\n'); s.trim(); s.toUpperCase();
    if      (s == "ID")       printId();
    else if (s == "SCAN")     i2cScan();
    else if (s == "BASELINE") captureBaseline();
    else if (s == "START") {
      logging = true;
      Serial.println("ms,hr,ct_est,ct_lo,ct_hi,kalman_half,skin_c,micro_c,"
                     "micro_rh,evap_kpa,act_rms,step_hz,state,flags");
    }
    else if (s == "STOP") { logging = false; Serial.println("# stopped"); }
  }

  uint32_t now = millis();
  if (now - lastStep < STEP_MS) { delay(2); return; }
  lastStep = now;

  readSensors();
  imuFeatures();

  float hr = meanHr();
  if (hr > 0) filterUpdate(hr);
  else        vv += gammaSqStep;      // no data: confidence decays, correctly

  float ctShow = fminf(fmaxf(ct, CT_MIN), CT_MAX);

  float half       = conformal_half_width(ctShow);   // the calibrated one
  float kalmanHalf = 1.96f * sqrtf(vv);              // logged for the demo only

  uint8_t flags = confoundFlags(hr, ctShow);
  DeviceState st = stateFromFlags(flags);

  if (logging) {
    Serial.printf("%lu,%.1f,%.3f,%.3f,%.3f,%.3f,%.2f,%.2f,%.1f,%.3f,"
                  "%.3f,%.2f,%d,0x%02X\n",
                  now, hr > 0 ? hr : 0.0f, ctShow,
                  ctShow - half, ctShow + half, kalmanHalf,
                  skinC, microC, microRh, headroom, actRms, stepHz,
                  (int)st, flags);
  }

  drawScreen(hr, ctShow, half, st, flags);

  if (st == STATE_OK && ctShow >= CT_ALERT_C) tone(PIN_BUZZER, 2200, 150);
  else if (flags & F_EVAP_FAILING)            tone(PIN_BUZZER, 1400, 80);
}
