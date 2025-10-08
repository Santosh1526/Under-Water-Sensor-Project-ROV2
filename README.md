**⚙️ Time Sampling Data Logger UI with Teensy 4.1**

This project is a real-time time-sampling and data logging system using Teensy 4.1 and multiple sensors.
It provides a Streamlit-based User Interface (UI) to visualize sensor readings, record data at fixed intervals, and download the collected dataset as a CSV file.

**🧠 Project Overview**

The system continuously collects data from various environmental sensors connected to the Teensy 4.1 microcontroller, samples them at fixed intervals, and stores the readings for analysis.
The Streamlit UI displays the time-sampled data and allows users to download the readings in .csv format for further processing or visualization.

**🧩 Hardware Components Used**

| Component                                           | Description                                              | Function                                                  |
| --------------------------------------------------- | -------------------------------------------------------- | --------------------------------------------------------- |
| **Teensy 4.1**                                      | High-performance ARM Cortex-M7 microcontroller (600 MHz) | Central controller for reading and processing sensor data |
| **TSYS01 Sensor**                                   | Temperature and pressure sensor (I²C)                    | Measures accurate temperature and pressure data           |
| **Pressure Sensor (Optional - if additional used)** | Analog or digital pressure sensor                        | Measures depth or pressure changes                        |
| **SD Card Module**                                  | SPI-based storage module                                 | Logs sampled sensor data locally on the SD card           |
| **RTC Module (Real Time Clock)**                    | Built-in or external                                     | Provides accurate timestamps for each sampled data point  |
| **Power Source (USB / External 5V)**                | -                                                        | Powers the Teensy and all connected peripherals           |

**🧠 Software & Tools**

1.Programming Language: Python 3

2.Microcontroller Platform: Teensy 4.1 (Arduino IDE)

3.UI Framework: Streamlit

4.Data Handling: Pandas

5.Data Format: CSV

**⚙️ Working Principle**

Teensy 4.1 collects data from all sensors via I²C/SPI.

Each reading includes:
1.!Timestamp (from RTC)

2.Temperature (from TSYS01)

3.Pressure (from TSYS01 or external sensor)

4.The data is sent via Serial or stored on the SD card.

5.The Streamlit UI reads the incoming data stream or file, displays it, and allows export to CSV.
