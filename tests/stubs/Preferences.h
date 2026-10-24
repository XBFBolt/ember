#pragma once
class Preferences {
public:
  bool begin(const char *, bool ro = false);
  void end();
  float getFloat(const char *, float d = 0);
  bool getBool(const char *, bool d = false);
  size_t putFloat(const char *, float);
  size_t putBool(const char *, bool);
};
