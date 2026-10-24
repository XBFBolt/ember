#pragma once
#include "Arduino.h"
class TwoWire {
public:
  bool begin(int sda, int scl, uint32_t f = 0);
  bool setClock(uint32_t);
  void beginTransmission(uint8_t);
  uint8_t endTransmission(bool stop = true);
  size_t write(uint8_t);
  uint8_t requestFrom(uint8_t addr, uint8_t len);
  int read();
};
extern TwoWire Wire;
