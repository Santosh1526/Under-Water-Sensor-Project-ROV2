/*** 
▗▖ ▗▖▗▖  ▗▖▗▄▄▄ ▗▄▄▄▖▗▄▄▖ ▗▖ ▗▖ ▗▄▖▗▄▄▄▖▗▄▄▄▖▗▄▄▖      ▗▄▄▖▗▄▄▄▖▗▖  ▗▖ ▗▄▄▖ ▗▄▖ ▗▄▄▖      ▗▄▄▖▗▖  ▗▖▗▄▄▖▗▄▄▄▖▗▄▄▄▖▗▖  ▗▖
▐▌ ▐▌▐▛▚▖▐▌▐▌  █▐▌   ▐▌ ▐▌▐▌ ▐▌▐▌ ▐▌ █  ▐▌   ▐▌ ▐▌    ▐▌   ▐▌   ▐▛▚▖▐▌▐▌   ▐▌ ▐▌▐▌ ▐▌    ▐▌    ▝▚▞▘▐▌     █  ▐▌   ▐▛▚▞▜▌
▐▌ ▐▌▐▌ ▝▜▌▐▌  █▐▛▀▀▘▐▛▀▚▖▐▌ ▐▌▐▛▀▜▌ █  ▐▛▀▀▘▐▛▀▚▖     ▝▀▚▖▐▛▀▀▘▐▌ ▝▜▌ ▝▀▚▖▐▌ ▐▌▐▛▀▚▖     ▝▀▚▖  ▐▌  ▝▀▚▖  █  ▐▛▀▀▘▐▌  ▐▌
▝▚▄▞▘▐▌  ▐▌▐▙▄▄▀▐▙▄▄▖▐▌ ▐▌▐▙█▟▌▐▌ ▐▌ █  ▐▙▄▄▖▐▌ ▐▌    ▗▄▄▞▘▐▙▄▄▖▐▌  ▐▌▗▄▄▞▘▝▚▄▞▘▐▌ ▐▌    ▗▄▄▞▘  ▐▌ ▗▄▄▞▘  █  ▐▙▄▄▖▐▌  ▐▌

Teensy 4.1 |  pH | DO | Temp | SD | RTC | Sleep | Pressure                                                                                                                                                                                                                                                                                                                                                                       
*/

//DONE: Add RTC and SD card module
//DONE: Add deepsleep and format saved strings
//DONE: Add RTC alarm interrupt for wakeup
//DONE: Add Pressure sensor support

#include <Arduino.h> //Core arduino library

#include <Wire.h> // I2C library

#include <Snooze.h> // Teensy deepsleep library

#include <SnoozeBlock.h> // Teensy deepsleep block class library

#include <SD.h> // SD card library

#include "RTClib.h" //RTC clock library

#include "TSYS01.h" //Temperature sensor

#include "MS5837.h"

MS5837 pressure_sensor; //Pressure sensor ( also give Temperature )
float Pressure =0;
int pressure_sen_available = 1;

#define USB_BAUD_RATE 57600 

// ------------------------------- Snooze variables -----------------------------
SnoozeDigital digital; // digital snooze block for interrupt
SnoozeUSBSerial usb; // usb block to enable serial on wakeup
//SnoozeAlarm  alarm; // alarm block to set wakeup alarms
SnoozeBlock config_teensy40(usb, digital); // add blocks to snooze config
unsigned long wakeup_millis = 0; // sleep after wakeup millis (10 + wakeup_millis)

// ---------------------------------------------------------------------------                                                   

const int chipSelect = BUILTIN_SDCARD; // SD card parameter
int sd_card = 1; //sd card status 


//------------------------------- PH sensor variables -----------------------------
#define PH_PIN A0 // pH meter Analog output to Teensy Analog Input A0
#define Offset 0.19 // deviation compensation
#define samplingInterval 20 //sampling interval for ph sensor 
#define printInterval 1000 //
#define ArrayLength 40 // number of samples to collect
float VoltageReference = 3.3; // Teensy 4.1 uses 3.3V as the analog reference
int pHArray[ArrayLength]; // Array to store sensor readings
int pHArrayIndex = 0;
// -----------------------------------------------------------------------------------


// ------------------------------ DO Sensor Variables ------------------------------

#define DO_PIN A1 // Analog input pin for DO sensor

//NOTE: For Teensy 4.1, analog reference is 3.3V (not 5V)
#define VREF_DO 3300  // in mV (3.3V reference)
#define ADC_RES 1024  // ADC resolution (10-bit)

#define TWO_POINT_CALIBRATION 1 // Calibration mode: 0 = Single-point, 1 = Two-point

#define READ_TEMP 25 //assumed water temperature (in ℃)

// --- Single-point calibration values ---
#define CAL1_V 1274  // in mV
#define CAL1_T 28    // in ℃

// --- Two-point calibration values (if needed) ---
#define CAL2_V 1262  // in mV
#define CAL2_T 21    // in ℃

// Dissolved Oxygen (DO) saturation table for 0–40 ℃
const uint16_t DO_Table[41] = {
  14460, 14220, 13820, 13440, 13090, 12740, 12420, 12110, 11810, 11530,
  11260, 11010, 10770, 10530, 10300, 10080, 9860, 9660, 9460, 9270,
  9080, 8900, 8730, 8570, 8410, 8250, 8110, 7960, 7820, 7690,
  7560, 7430, 7300, 7180, 7070, 6950, 6840, 6730, 6630, 6530, 6410
};

// Variables for raw ADC readings and computed voltage
uint8_t Temperaturet = READ_TEMP;     // Water temperature in ℃
uint16_t ADC_Raw = 0;                 // Raw ADC value
uint16_t ADC_Voltage = 0;             // Converted ADC voltage in mV

// -------------------------------------------------------------------------------

/**
 * @brief Calculates the dissolved oxygen (DO) concentration.
 *
 * This function uses either single-point or two-point calibration to compute
 * the DO concentration based on the supplied sensor voltage and water temperature.
 * The result is adjusted using a DO saturation lookup table.
 *
 * @param voltage_mv     The measured sensor voltage in millivolts (mV).
 * @param temperature_c  The water temperature in degrees Celsius (0–40 °C).
 *
 * @return The calculated dissolved oxygen value (unit depends on sensor scaling).
 *
 * @note Make sure temperature is in the range 0–40 °C. Values outside this
 *       range may cause table lookup errors or incorrect calibration.
 */

int16_t readDO(uint32_t voltage_mv, uint8_t temperature_c) {
  #if TWO_POINT_CALIBRATION == 0
    // Single-point calibration calculation
    uint16_t V_saturation = CAL1_V + 35 * (temperature_c - CAL1_T);
    return (voltage_mv * DO_Table[temperature_c]) / V_saturation;
  #else
    // Two-point calibration calculation
    uint16_t V_saturation = ((int16_t)(temperature_c - CAL2_T)) *
                            (CAL1_V - CAL2_V) /
                            (CAL1_T - CAL2_T) + CAL2_V;
    return (voltage_mv * DO_Table[temperature_c]) / V_saturation;
  #endif
}


//-------------------------------ds3232 rtc clock ----------------------------------
RTC_DS3231 rtc; //ds3231 rtc driver 
#define CLOCK_INTERRUPT_PIN 16 // the pin that is connected to SQW
// -------------------------------------------------------------------------------


//-------------------------------TSYS01 temperature sensor-------------------------
TSYS01 temp_sensor; //temp sensor
int temp_sen_available = 1; 

//-------------------------------------------------------------------------------



void init_peripherals() {
pHArrayIndex = 0;
Wire.begin();
Serial.begin(USB_BAUD_RATE); 
delay(200);
}

void disable_peripherals(){
Wire.end();
Serial.end(); 
}



void setup() {
  digital.pinMode(21, INPUT_PULLUP, RISING);//NOTE: need to setup rtc interrup alarm
  //alarm.setRtcTimer(0, 0, 35);//NOTE: temporary rtc timer for wakeup add digital wakeup
  pinMode(LED_BUILTIN, OUTPUT); // LEd pin setup 

  Serial.begin(USB_BAUD_RATE); // serial setup baud rate 576000
  Serial.println("[Debug] pH meter experiment on Teensy 4.1!"); //
  while (!Serial); // Wait for Serial to re-enumerate  

  Wire.begin(); // I2C on SDA=PIN 18 , SCL=PIN 19
  
  // ------------------------------- RTC setup -----------------------------------
  //check if rtc exists

  if(!rtc.begin()) 
  {
    Serial.println("Couldn't find RTC!");
    Serial.flush();
    while (1) delay(10);
  }
  rtc.adjust(DateTime(F(__DATE__), F(__TIME__)));
  rtc.disable32K();

  // set alarm 1, 2 flag to false (so alarm 1, 2 didn't happen so far)
  // if not done, this easily leads to problems, as both register aren't reset on reboot/recompile
  rtc.clearAlarm(1);
  rtc.clearAlarm(2);

  // stop oscillating signals at SQW Pin
  // otherwise setAlarm1 will fail
  rtc.writeSqwPinMode(DS3231_OFF);

  // turn off alarm 2 (in case it isn't off already)
  // again, this isn't done at reboot, so a previously set alarm could easily go overlooked
  
if (rtc.alarmFired(1)) {
    rtc.clearAlarm(1);
    Serial.println("⏰ RTC Alarm triggered! Resetting for next 30 minutes...");

    // Re-arm the alarm 30 minutes from current RTC time
    if (!rtc.setAlarm1(
        rtc.now() + TimeSpan(0, 0, 30, 0),
        DS3231_A1_Minute))
    {
        Serial.println("[Error] Failed to reset 30-minute alarm!");
    } 
    else {
        Serial.println("[OK] Next alarm set for 30 minutes later.");
    }
}


  // -----------------------------------------------------------------------------------
  digital.pinMode(CLOCK_INTERRUPT_PIN, INPUT_PULLUP, FALLING);


  
  // check if temperature sensor is connected
  int counter = 0;
  while (!temp_sensor.init()) 
  {
    Serial.println("[Error] TSYS01 device failed to initialize!");
    delay(200);
    counter++;
    if (counter > 15) 
    {
      temp_sen_available = 0; //temperature sensor not found
      break;
    }
  }

  //-------------------------------MS5837 pressure sensor--------------------------
  pressure_sensor.setModel(MS5837::MS5837_30BA);
  pressure_sensor.setFluidDensity(997); // kg/m^3 (freshwater, 1029 for seawater)

  counter = 0;
  while (!pressure_sensor.init()) 
  {
    Serial.println("[Error] TSYS01 device failed to initialize!");
    delay(200);
    counter++;
    if (counter > 15) 
    {
      pressure_sen_available = 0; //temperature sensor not found
      break;
    }
  }
//-----------------------------------------------------------------------------
  // check if sd card is connected
  if (!SD.begin(chipSelect)) {
    Serial.println("[Error] initialization failed. Things to check:");
    sd_card = 0; //sd card not found
  }

  DateTime now = rtc.now(); // get current time from rtc
  analogReadResolution(10); // Explicitly set ADC resolution to 10-bit for consistency
  String params = "$Params ,"+ String(CAL1_V) + " ," + String(CAL1_T) + " ," + String(CAL2_V) + " ," + String(CAL2_T) + " ," + String(Offset) + " ," + String(temp_sen_available) + "\n";
  Serial.println(params); //$Params , Cal1_V, Cal1_T, Cal2_V, Cal2_T, Offset, Temp_sensor_avilable 
  
  // writing parameter data to sd card in file datalog.txt
  if (sd_card) {
    File dataFile = SD.open("datalog.txt", FILE_WRITE);
    if (dataFile) {
      dataFile.println(params);
      dataFile.close();
    } else {
      Serial.println("[Error] error opening datalog.txt");
    } 
  } 
}

void loop() {
  Serial.print("Looping - millis "); Serial.println(millis());
  Serial.flush();

  //------------------------------- PH sensor logic -----------------------------
  static unsigned long samplingTime = millis();
  static unsigned long printTime = millis();
  static float pHValue, voltage;
  int V = 0;
  // Sampling the sensor
  if (millis() - samplingTime > samplingInterval) {
    V = analogRead(PH_PIN);
    pHArray[pHArrayIndex++] = V;
    if (pHArrayIndex == ArrayLength) pHArrayIndex = 0;

    // Calculate average and then convert to voltage
    voltage = averageArray(pHArray, ArrayLength) * VoltageReference / 1024.0;

    // Compute the pH value based on sensor characteristics (this linear relationship may require calibration)
    pHValue = 3.5 * voltage + Offset;
    samplingTime = millis();
  }

  // Print data and toggle LED at regular intervals
  if (millis() - printTime > printInterval) {
    DateTime now = rtc.now();

    Serial.print("Voltage: ");
    Serial.print(voltage);
    Serial.print("    pH value: ");
    Serial.println(pHValue, 2);
    
    // String format $PH,timestamp,voltage,average voltage,average ph ,ph value
    char ph_buf[128];
    snprintf(ph_buf, sizeof(ph_buf),
    "$PH,%02d/%02d/%04d %02d:%02d:%02d,%d,%f,%.2f\n",
    now.day(), now.month(), now.year(),
    now.hour(), now.minute(), now.second(),V,
    voltage,pHValue);
    Serial.println(ph_buf);
    // Toggle LED state
    printTime = millis();
    if (sd_card) {
      File dataFile = SD.open("datalog.txt", FILE_WRITE);
      if (dataFile) {
        dataFile.println(ph_buf);
        dataFile.close();
        delay(100);
      } else {
        Serial.println("[Error] error opening datalog.txt");
      }
    }

  }
  // -----------------------------------------------------------------------------------

  // ------------------------------- DO sensor logic -----------------------------------
  temp_sensor.read();
  pressure_sensor.read();
  Temperaturet = (uint8_t) temp_sensor.temperature();
  Pressure = pressure_sensor.pressure();
  ADC_Raw = analogRead(DO_PIN);
  ADC_Voltage = (uint32_t(VREF_DO) * ADC_Raw) / ADC_RES;
  static unsigned long DOprintTime = millis();
  if (millis() - DOprintTime > printInterval) {
    DateTime now = rtc.now();
    // String format $DO,Temp,ADC raw voltage,actual voltage,DO value,temp sensor status
   char do_buf[128];
  snprintf(do_buf, sizeof(do_buf),
  "$DO,%02d/%02d/%04d %02d:%02d:%02d,%.2f,%u,%u,%d,%f,%d,%d\n",
  now.day(), now.month(), now.year(),
  now.hour(), now.minute(), now.second(),
  float(Temperaturet), ADC_Raw, ADC_Voltage,
  readDO(ADC_Voltage, Temperaturet),Pressure, temp_sen_available,pressure_sen_available
  );
  Serial.println(do_buf);
    // Toggle LED state
    if (sd_card) {
      File dataFile = SD.open("datalog.txt", FILE_WRITE);
      if (dataFile) {
        dataFile.println(do_buf);
        dataFile.close();
        delay(100);
      } else {
      Serial.println("[Error] error opening datalog.txt");
    }
  }
  DOprintTime = millis();
  }
  // -----------------------------------------------------------------------------------

  // ------------------------------- Snooze logic --------------------------------------
  // Sleep a little while every 10 seconds
  if (millis() > 10000 + wakeup_millis){
    disable_peripherals();
    Snooze.deepSleep(config_teensy40);
    // Led blink to indicate coming out from sleep
    digitalWrite(LED_BUILTIN, HIGH);
    delay(50);
    digitalWrite(LED_BUILTIN, LOW);
    init_peripherals();
    wakeup_millis = millis();
    if (rtc.alarmFired(1)) {
        rtc.clearAlarm(1);
        Serial.print(" - Alarm cleared");
    }
    Serial.println();

    delay(2000);
  }
  
  Serial.flush();
  // -----------------------------------------------------------------------------------
}


double averageArray(int * arr, int number) {
  if (number <= 0) {
    Serial.println("Error: Invalid array size!");
    return 0;
  }

  if (number < 5) { // Direct average if few samples
    long total = 0;
    for (int i = 0; i < number; i++) {
      total += arr[i];
    }
    return (double) total / number;
  } else {
    int minVal = arr[0], maxVal = arr[0];
    long total = 0;
    for (int i = 0; i < number; i++) {
      int val = arr[i];
      if (val < minVal) minVal = val;
      if (val > maxVal) maxVal = val;
      total += val;
    }
    // Subtract min and max for a robust average
    total = total - minVal - maxVal;
    return (double) total / (number - 2);
  }
}