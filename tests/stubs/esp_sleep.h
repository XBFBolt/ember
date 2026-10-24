#pragma once
#define RTC_DATA_ATTR
void esp_deep_sleep_start();
int esp_sleep_enable_timer_wakeup(unsigned long long);
