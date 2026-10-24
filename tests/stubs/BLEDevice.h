#pragma once
#include "Arduino.h"
class BLEServer;
class BLECharacteristic;
class BLEDescriptor { public: virtual ~BLEDescriptor() {} };
class BLEServerCallbacks { public: virtual ~BLEServerCallbacks() {} virtual void onConnect(BLEServer *) {} virtual void onDisconnect(BLEServer *) {} };
class BLECharacteristicCallbacks { public: virtual ~BLECharacteristicCallbacks() {} virtual void onWrite(BLECharacteristic *) {} };
class BLECharacteristic {
public:
  static const uint32_t PROPERTY_READ = 1, PROPERTY_WRITE = 2, PROPERTY_NOTIFY = 4, PROPERTY_WRITE_NR = 8;
  void addDescriptor(BLEDescriptor *);
  void setCallbacks(BLECharacteristicCallbacks *);
  String getValue();
  void setValue(uint8_t *data, size_t len);
  void notify(bool is_notification = true);
};
class BLEService { public: BLECharacteristic *createCharacteristic(const char *, uint32_t); void start(); };
class BLEServer { public: void setCallbacks(BLEServerCallbacks *); BLEService *createService(const char *); };
class BLEAdvertising { public: void addServiceUUID(const char *); void setScanResponse(bool); };
class BLEDevice { public: static void init(String); static BLEServer *createServer(); static BLEAdvertising *getAdvertising(); static void startAdvertising(); };
