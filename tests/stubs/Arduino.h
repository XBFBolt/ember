// Minimal host stubs with arduino-esp32 3.x signatures. For syntax and
// type checking only - nothing here behaves like hardware.
#pragma once
#include <cstdint>
#include <cstddef>
#include <cstdio>
#include <cstdarg>
#include <cmath>
#include <string>
#include <cstring>
#include <initializer_list>
using std::isnan;
class String {
  std::string s;
public:
  String() {}
  String(const char *c) : s(c ? c : "") {}
  String(float v, unsigned int dec) { char b[32]; snprintf(b, 32, "%.*f", dec, v); s = b; }
  const char *c_str() const { return s.c_str(); }
  unsigned int length() const { return s.size(); }
  void trim() {}
  void toUpperCase() {}
  String &operator+=(char c) { s += c; return *this; }
  String &operator=(const String &o) { s = o.s; return *this; }
  bool operator==(const char *o) const { return s == o; }
};
class Print { public: virtual size_t write(uint8_t) { return 1; } virtual ~Print() {} };
class Stream : public Print { public: virtual int available() { return 0; } virtual int read() { return -1; } };
class HWSerial : public Stream {
public:
  void begin(unsigned long) {}
  size_t printf(const char *f, ...) __attribute__((format(printf, 2, 3))) { va_list a; va_start(a, f); int n = vprintf(f, a); va_end(a); return n; }
  size_t println(const char *s = "") { return ::printf("%s\n", s); }
  size_t print(const char *s) { return ::printf("%s", s); }
  void flush() {}
};
extern HWSerial Serial;
unsigned long millis();
void delay(uint32_t);
uint16_t analogRead(uint8_t);
uint32_t analogReadMilliVolts(uint8_t);
void analogReadResolution(uint8_t);
typedef enum { ADC_0db, ADC_2_5db, ADC_6db, ADC_11db, ADC_ATTENDB_MAX } adc_attenuation_t;
void analogSetAttenuation(adc_attenuation_t);
// FreeRTOS
typedef uint32_t TickType_t;
typedef void *TaskHandle_t;
typedef void *QueueHandle_t;
typedef int BaseType_t;
#define pdTRUE 1
#define pdMS_TO_TICKS(x) (x)
typedef struct { int x; } portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED {0}
inline void portENTER_CRITICAL(portMUX_TYPE *) {}
inline void portEXIT_CRITICAL(portMUX_TYPE *) {}
TickType_t xTaskGetTickCount();
void vTaskDelayUntil(TickType_t *, TickType_t);
BaseType_t xTaskCreatePinnedToCore(void (*)(void *), const char *, uint32_t, void *, unsigned, TaskHandle_t *, int);
QueueHandle_t xQueueCreate(unsigned, unsigned);
BaseType_t xQueueSend(QueueHandle_t, const void *, TickType_t);
BaseType_t xQueueReceive(QueueHandle_t, void *, TickType_t);
BaseType_t xQueueReset(QueueHandle_t);
