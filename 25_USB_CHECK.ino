/*  Teensy 4.1 Water Quality Logger - 30 MINUTE INTERVAL - DEEP SLEEP VERSION
    Takes readings every 30 minutes
    Uses DS3231 RTC alarm (Alarm1) to wake the Teensy from deep sleep
    Keeps SD logging and Serial commands working after wake
*/

#include <Arduino.h>
#include <Wire.h>
#include <SD.h>
#include "RTClib.h"
#include "TSYS01.h"
#include "MS5837.h"
#include <Snooze.h>
#include <SnoozeBlock.h>

#define USB_BAUD_RATE 57600
#define PH_PIN A0
#define DO_PIN A1
#define CHIP_SELECT BUILTIN_SDCARD
#define MAX_SAMPLES 100
#define SERIAL_TIMEOUT 2000

// interval set to 30 minutes (1800 seconds)
#define ALARM_INTERVAL_SECONDS 1800UL

// RTC interrupt pin (DS3231 INT/SQW -> use physical pin 16 on Teensy as in your prior sketch)
#define CLOCK_INTERRUPT_PIN 13

MS5837 pressure_sensor;
TSYS01 temp_sensor;
RTC_DS3231 rtc;

// Snooze blocks
SnoozeDigital digital;        // digital wake-up block
SnoozeUSBSerial usb;         // keep USB serial available on wake
SnoozeBlock config_teensy(usb, digital);

bool sd_available = false;

// Sampling defaults (modifiable over serial)
int N_samples = 10;
int samplingInterval = 20; // ms between samples

unsigned long lastSampleTime = 0;

// Calibration/constants
const float VoltageReference = 3.3;
#define OFFSET 0.19
#define VREF_DO 3300
#define ADC_RES 1024
#define TWO_POINT_CALIBRATION 1
#define CAL1_V 1274
#define CAL1_T 28
#define CAL2_V 1262
#define CAL2_T 21

const uint16_t DO_Table[41] = {
  14460,14220,13820,13440,13090,12740,12420,12110,11810,11530,
  11260,11010,10770,10530,10300,10080,9860,9660,9460,9270,
  9080,8900,8730,8570,8410,8250,8110,7960,7820,7690,
  7560,7430,7300,7180,7070,6950,6840,6730,6630,6530,6410
};

int16_t readDO(uint32_t voltage_mv, uint8_t temperature_c) {
  if (temperature_c > 40) temperature_c = 40;

  #if TWO_POINT_CALIBRATION == 0
    uint16_t V_saturation = CAL1_V + 35 * (temperature_c - CAL1_T);
    return (voltage_mv * DO_Table[temperature_c]) / V_saturation;
  #else
    uint16_t V_saturation = ((int16_t)(temperature_c - CAL2_T)) *
                            (CAL1_V - CAL2_V) /
                            (CAL1_T - CAL2_T) + CAL2_V;
    return (voltage_mv * DO_Table[temperature_c]) / V_saturation;
  #endif
}

// ----- Serial commands -----
void sendSDFileOverSerial(const char *filename) {
  if (!sd_available) {
    Serial.println("[Error] SD not available");
    return;
  }

  File f = SD.open(filename);
  if (!f) {
    Serial.println("[Error] Cannot open file");
    return;
  }

  Serial.println("[START FILE]");
  while (f.available()) {
    uint8_t buf[64];
    int r = f.read(buf, sizeof(buf));
    Serial.write(buf, r);
  }
  f.close();
  Serial.println("\n[END FILE]");
}

void performSamplingAndLog(int N); // forward

void handleSerialCommands() {
  if (!Serial.available()) return;

  String cmd = Serial.readStringUntil('\n');
  cmd.trim();
  if (cmd.length() == 0) return;

  if (cmd.startsWith("N=")) {
    int v = cmd.substring(2).toInt();
    v = constrain(v, 1, MAX_SAMPLES);
    N_samples = v;
    Serial.print("N_samples = "); Serial.println(N_samples);

  } else if (cmd.startsWith("T=")) {
    int v = cmd.substring(2).toInt();
    v = constrain(v, 1, 60000);
    samplingInterval = v;
    Serial.print("samplingInterval = "); Serial.println(samplingInterval);

  } else if (cmd.equalsIgnoreCase("SEND")) {
    sendSDFileOverSerial("datalog.txt");

  } else if (cmd.equalsIgnoreCase("STATUS")) {
    Serial.print("N="); Serial.print(N_samples);
    Serial.print(" T="); Serial.print(samplingInterval);
    Serial.print(" SD="); Serial.println(sd_available ? "YES" : "NO");
    DateTime now = rtc.now();
    Serial.print("Time: "); Serial.println(now.timestamp());
    unsigned long nextReading = (ALARM_INTERVAL_SECONDS * 1000UL) - (millis() - lastSampleTime);
    if ((long)nextReading < 0) nextReading = 0;
    Serial.print("Next reading in: "); Serial.print(nextReading / 1000); Serial.println(" seconds");

  } else if (cmd.equalsIgnoreCase("NOW")) {
    Serial.println("[Manual] Taking reading now...");
    performSamplingAndLog(N_samples);
    lastSampleTime = millis();

  } else if (cmd.equalsIgnoreCase("SETTIME")) {
    rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
    DateTime now = rtc.now();
    Serial.print("RTC set to compile time: "); Serial.println(now.timestamp());

  } else if (cmd.startsWith("TIME=")) {
    // Format: TIME=YYYY-MM-DD HH:MM:SS
    String timeStr = cmd.substring(5);
    int year = timeStr.substring(0, 4).toInt();
    int month = timeStr.substring(5, 7).toInt();
    int day = timeStr.substring(8, 10).toInt();
    int hour = timeStr.substring(11, 13).toInt();
    int minute = timeStr.substring(14, 16).toInt();
    int second = timeStr.substring(17, 19).toInt();

    rtc.adjust(DateTime(year, month, day, hour, minute, second));
    DateTime now = rtc.now();
    Serial.print("RTC set to: "); Serial.println(now.timestamp());

  } else {
    Serial.println("Commands: N=<num> T=<ms> NOW SEND STATUS SETTIME TIME=YYYY-MM-DD HH:MM:SS");
  }
}

// ----- Peripherals -----
bool init_peripherals() {
  Wire.begin();

  bool temp_ok = temp_sensor.init();

  pressure_sensor.setModel(MS5837::MS5837_30BA);
  pressure_sensor.setFluidDensity(997);
  bool pres_ok = pressure_sensor.init();

  analogReadResolution(10);

  return temp_ok && pres_ok;
}

// ----- Sampling and logging implementation -----
void performSamplingAndLog(int N) {
  N = constrain(N, 1, MAX_SAMPLES);

  static int ph_samples[MAX_SAMPLES];
  static uint32_t do_samples[MAX_SAMPLES];
  static float temp_samples[MAX_SAMPLES];
  static float pres_samples[MAX_SAMPLES];

  Serial.print("Sampling ");
  Serial.print(N);
  Serial.println(" times...");

  // Take samples
  for (int i = 0; i < N; ++i) {
    ph_samples[i] = analogRead(PH_PIN);
    do_samples[i] = (uint32_t)analogRead(DO_PIN);

    temp_sensor.read();
    temp_samples[i] = temp_sensor.temperature();

    pressure_sensor.read();
    pres_samples[i] = pressure_sensor.pressure();

    if (i < N - 1) delay(samplingInterval);
  }

  // Compute aggregated values
  long ph_total = 0;
  int ph_min = ph_samples[0], ph_max = ph_samples[0];
  uint64_t do_total = 0;
  double temp_total = 0.0;
  double pres_total = 0.0;

  for (int i = 0; i < N; ++i) {
    ph_total += ph_samples[i];
    if (ph_samples[i] < ph_min) ph_min = ph_samples[i];
    if (ph_samples[i] > ph_max) ph_max = ph_samples[i];
    do_total += do_samples[i];
    temp_total += temp_samples[i];
    pres_total += pres_samples[i];
  }

  // Remove outliers for pH if we have enough samples
  long ph_adj = ph_total;
  int ph_divisor = N;
  if (N > 2) {
    ph_adj = ph_total - ph_min - ph_max;
    ph_divisor = N - 2;
  }

  double ph_avg = (double)ph_adj / (double)ph_divisor;
  double voltage = ph_avg * VoltageReference / 1024.0;
  double pHValue = 3.5 * voltage + OFFSET;

  double do_adc_avg = (double)do_total / (double)N;
  uint32_t do_voltage_mv = (uint32_t)((VREF_DO * do_adc_avg) / ADC_RES);
  double temp_avg = temp_total / (double)N;
  uint8_t temp_for_do = (uint8_t)constrain((int)round(temp_avg), 0, 40);
  int16_t do_value = readDO(do_voltage_mv, temp_for_do);

  double pres_avg = pres_total / (double)N;

  DateTime now = rtc.now();

  //-------------------------------------------
  // Print to Serial in readable format
  //-------------------------------------------
  Serial.println("🔴");
  Serial.println("========================================");
  Serial.print("Timestamp: ");
  Serial.print(now.day()); Serial.print("/");
  Serial.print(now.month()); Serial.print("/");
  Serial.print(now.year()); Serial.print(" ");
  Serial.print(now.hour()); Serial.print(":");
  Serial.print(now.minute()); Serial.print(":");
  Serial.println(now.second());
  Serial.println("----------------------------------------");
  Serial.print("PH Raw ADC: "); Serial.println(ph_avg, 1);
  Serial.print("PH Voltage: "); Serial.print(voltage, 3); Serial.println(" V");
  Serial.print("PH Value:   "); Serial.println(pHValue, 2);
  Serial.println("----------------------------------------");
  Serial.print("DO mV:      "); Serial.println(do_voltage_mv);
  Serial.print("DO Value:   "); Serial.print(do_value); Serial.println(" ug/L");
  Serial.println("----------------------------------------");
  Serial.print("Temp:       "); Serial.print(temp_avg, 2); Serial.println(" °C");
  Serial.print("Pressure:   "); Serial.print(pres_avg, 2); Serial.println(" mbar");
  Serial.println("========================================\n");

  // Save to SD card in human-readable multi-line format
  if (sd_available) {
    File f = SD.open("datalog.txt", FILE_WRITE);
    if (f) {
      f.println("🔴");
      f.println("=== Water Quality Reading ===");
      f.print("Timestamp: ");
      f.print(now.day()); f.print("/");
      f.print(now.month()); f.print("/");
      f.print(now.year()); f.print(" ");
      f.print(now.hour()); f.print(":");
      f.print(now.minute()); f.print(":");
      f.println(now.second());
      f.println("-----------------------------");
      f.print("PH Raw ADC: "); f.println(ph_avg, 1);
      f.print("PH Voltage: "); f.print(voltage, 3); f.println(" V");
      f.print("PH Value: "); f.println(pHValue, 2);
      f.println("-----------------------------");
      f.print("DO Voltage: "); f.print(do_voltage_mv); f.println(" mV");
      f.print("DO Value: "); f.print(do_value); f.println(" ug/L");
      f.println("-----------------------------");
      f.print("Temperature: "); f.print(temp_avg, 2); f.println(" °C");
      f.print("Pressure: "); f.print(pres_avg, 2); f.println(" mbar");
      f.println("=============================");
      f.println();  // Empty line between readings
      f.close();
      Serial.println("[SD] Data saved to datalog.txt");
    } else {
      Serial.println("[Error] Failed to write to datalog.txt");
    }
  }
}

// ----- Setup & Loop -----
void setup() {
  // Prepare RTC interrupt pin
  pinMode(CLOCK_INTERRUPT_PIN, INPUT_PULLUP);

  Serial.begin(USB_BAUD_RATE);
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < SERIAL_TIMEOUT) { }

  Serial.println("\n\n");
  Serial.println("========================================");
  Serial.println("  Teensy 4.1 Water Quality Logger");
  Serial.println("  30 MINUTE READING INTERVAL (DEEP SLEEP)");
  Serial.println("========================================\n");

  Wire.begin();

  if (!rtc.begin()) {
    Serial.println("[FATAL] RTC not found! Cannot continue.");
    while (1) { delay(1000); }
  }

  // Always set RTC to compile time (PC time when uploading)
  Serial.println("[RTC] Setting to PC compile time...");
  rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  rtc.disable32K();
  rtc.clearAlarm(1);
  rtc.clearAlarm(2);
  rtc.writeSqwPinMode(DS3231_OFF); // ensure INT used for alarms

  DateTime now = rtc.now();
  Serial.print("[RTC] Time set to: "); Serial.println(now.timestamp());

  // Initialize SD card
  if (SD.begin(CHIP_SELECT)) {
    sd_available = true;
    Serial.println("[SD] Card initialized");
  } else {
    Serial.println("[SD] Card failed - logging to Serial only");
    sd_available = false;
  }

  // Initialize sensors
  if (init_peripherals()) {
    Serial.println("[Sensors] Initialized successfully");
  } else {
    Serial.println("[Sensors] Warning: Initialization issue");
  }

  Serial.println("\n========================================");
  Serial.print("Configuration: N="); Serial.print(N_samples);
  Serial.print(" samples, T="); Serial.print(samplingInterval); Serial.println("ms interval");
  Serial.print("Reading every "); Serial.print(ALARM_INTERVAL_SECONDS / 60); Serial.println(" minutes");
  Serial.println("========================================\n");

  // Take first reading immediately
  Serial.println("[Startup] Taking first reading NOW...\n");
  performSamplingAndLog(N_samples);
  lastSampleTime = millis();

  // Set first RTC alarm 30 minutes from now
  now = rtc.now();
  rtc.clearAlarm(1);
  rtc.setAlarm1(now + TimeSpan(0, 0, 30, 0), DS3231_A1_Minute); // first wake in 30 minutes
  Serial.println("⏰ RTC alarm set for 30 minutes from now.");

  Serial.println("Device will now go to deep sleep until next alarm.");
  Serial.println("Commands available when awake: STATUS NOW SEND N=<num> T=<ms>\n");

  // Prepare digital snooze block to wake on falling edge of RTC INT (pin 16)
  digital.pinMode(CLOCK_INTERRUPT_PIN, INPUT_PULLUP, FALLING);
  // keep usb block so Serial is usable right after wake
  // config_teensy already created with usb,digital
}

void loop() {

  // give serial a few seconds
  unsigned long activeWindow = 5000;
  unsigned long startActive = millis();
  while (millis() - startActive < activeWindow) {
    handleSerialCommands();
    delay(10);
  }

  Serial.println("[SLEEP] Preparing to sleep now...");

  // ----- FIXED: Set next alarm properly -----
  DateTime now2 = rtc.now();
  DateTime nextAlarm = now2 + TimeSpan(0, 0, 30, 0);

  rtc.clearAlarm(1);
  rtc.setAlarm1(nextAlarm, DS3231_A1_Hour);

  Serial.print("[SLEEP] Next wake scheduled at: ");
  Serial.println(nextAlarm.timestamp());

  Serial.println("[SLEEP] Entering deep sleep...");
  Serial.flush();

  Snooze.deepSleep(config_teensy);
  // ------------------------------------------

  // On wake
  unsigned long t0 = millis();
  while (!Serial && millis() - t0 < 1000) {}

  Serial.println("\n[WAKE] Woke up from deep sleep");

  if (rtc.alarmFired(1)) {
    rtc.clearAlarm(1);
    Serial.println("[WAKE] RTC alarm cleared.");
  }

  Wire.begin();
  init_peripherals();

  Serial.println("[WAKE] Taking reading...");
  performSamplingAndLog(N_samples);
}
