###############################################################
#   TEENSY 4.1 – OCEAN SENSOR GUI (FINAL CLEAN VERSION)
#   Real-time display, sleep detection, CSV logging,
#   interval sampling, SD card download (fixed protocol),
#   clean GUI layout.
###############################################################

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from PIL import Image, ImageTk, ImageEnhance
import serial
import threading
import time
import csv
import serial.tools.list_ports
from datetime import datetime, timedelta
from tkcalendar import Calendar
import sys
import re

# -------------------- CONFIG --------------------
BAUD = 57600
SERIAL_TIMEOUT = 1.0

# -------------------- Global Variables --------------------
ser = None
sensor_data_list = []
sampling_interval = 1
custom_datetime = None
csv_file_path = None
csv_writer = None
csv_file = None
continuous_csv_file = None
continuous_csv_writer = None

# runtime flags / thread handles
is_reading = False
read_thread = None
read_thread_stop = threading.Event()

# Current sensor values (always updated for display)
current_ph = 0.0
current_do = 0.0
current_temp = 0.0
current_pressure = 0.0

# Time sampling variables
sampling_enabled = False
sampling_interval_seconds = 1800
last_sample_time = None
sampling_window = None
start_time_set = "00:00:00"
end_time_set = "23:59:59"
within_time_window = False

# -------------------- Find Teensy Port --------------------
def find_teensy_port():
    """Automatically detect Teensy port"""
    ports = serial.tools.list_ports.comports()
    print("\n🔍 Scanning for Teensy...")
    for port in ports:
        print(f"  📍 {port.device} - {port.description}")
        desc = (port.description or "").lower()
        dev = (port.device or "").lower()
        if "teensy" in desc or "teensy" in dev:
            print(f"  ✅ Found Teensy!")
            return port.device
        if "usbmodem" in dev or "ttyacm" in dev or "usbserial" in dev:
            print(f"  ✅ Found USB Serial Device!")
            return port.device
        if getattr(port, "vid", None) == 0x16C0:
            print(f"  ✅ Found Teensy by VID!")
            return port.device
    print("  ❌ No Teensy found")
    return None

# -------------------- Serial Reading Thread --------------------
def read_serial_data():
    """Continuously read data from Teensy and update display"""
    global ser, is_reading, read_thread_stop
    print("📡 Serial reading thread started")
    try:
        while not read_thread_stop.is_set() and is_reading:

            # If Teensy is sleeping, serial port stays open but no data arrives.
            # We never disconnect automatically.
            if ser is None or not getattr(ser, "is_open", False):
                time.sleep(0.1)
                continue

            try:
                if getattr(ser, "in_waiting", 0) > 0:
                    raw = ser.readline()
                    if not raw:
                        continue
                    try:
                        line = raw.decode("utf-8", errors="ignore").strip()
                    except Exception:
                        line = raw.decode("latin-1", errors="ignore").strip()
                    if line:
                        print(f"📥 RECEIVED: {line}")
                        root.after(0, lambda l=line: update_display(l, save_data=False))
                else:
                    # Teensy might be in deep sleep → no data
                    time.sleep(0.02)

            except (serial.SerialException, OSError) as e:
                print(f"❌ Serial Exception in read loop: {e}")
                # DO NOT DISCONNECT — Teensy might be sleeping
                text_box.insert(tk.END, f"[SERIAL ERROR] {e}\n", "red")
                text_box.see(tk.END)
                time.sleep(0.5)
                continue

            except Exception as e:
                print(f"❌ Unexpected read error: {e}")
                try:
                    text_box.insert(tk.END, f"[READ ERROR] {e}\n", "red")
                    text_box.see(tk.END)
                except:
                    pass
                time.sleep(0.2)

    finally:
        print("📴 Serial reading thread exiting")

# -------------------- Update Display with Synchronized Output --------------------
def update_display(line, save_data=True):
    """Parse incoming data and update GUI labels with CORRECT sensor values"""
    global current_ph, current_do, current_temp, current_pressure

    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated = False

        # ========== FORMAT 1: $Params,pH*100,DO*10,Temp*50,Pressure*1000 ==========
        if "$Params" in line or "$params" in line:
            parts = line.split(',')
            if len(parts) >= 5:
                try:
                    current_ph = float(parts[1]) / 100.0
                    current_do = float(parts[2]) / 10.0
                    current_temp = float(parts[3]) / 50.0
                    current_pressure = float(parts[4]) / 1000.0
                    
                ph_label.config(text=f"🌊 pH: {current_ph:.2f}")
                do_label.config(text=f"💧 DO: {current_do:.2f} mg/L")
                temp_label.config(text=f"🔥 Temperature: {current_temp:.2f}°C")
                pressure_label.config(text=f"🌡️ Pressure: {current_pressure:.2f} bar")

                    if save_data:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"[{current_time}] ✅ SAVED TO SD CARD:\n", "green")
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 📡 LIVE READING:\n", "cyan")
                    
                    text_box.insert(tk.END, f"  🌊 pH: {current_ph:.2f}\n", "blue")
                    text_box.insert(tk.END, f"  💧 DO: {current_do:.2f} mg/L\n", "green")
                    text_box.insert(tk.END, f"  🔥 Temp: {current_temp:.2f}°C\n", "red")
                    text_box.insert(tk.END, f"  🌡️ Press: {current_pressure:.2f} bar\n\n", "goldenrod")
                    text_box.see(tk.END)
                    updated = True
                except ValueError as e:
                    text_box.insert(tk.END, f"[PARSE ERR] {e}\n", "red")
                    text_box.see(tk.END)

        # ========== FORMAT 2: $PH,value ==========
        elif "$PH" in line or "$ph" in line:
            parts = line.split(',')
            if len(parts) >= 2:
                try:
                    current_ph = float(parts[1])
                    ph_label.config(text=f"🌊 pH: {current_ph:.2f}")
                    if save_data:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"[{current_time}] ✅ SAVED pH: {current_ph:.2f}\n", "green")
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 📡 pH: {current_ph:.2f}\n", "blue")
                    text_box.see(tk.END)
                    updated = True
                except ValueError as e:
                    text_box.insert(tk.END, f"[PH ERR] {e}\n", "red")
                    text_box.see(tk.END)

        # ========== FORMAT 3: $DO,value ==========
        elif "$DO" in line or "$do" in line:
            parts = line.split(',')
            if len(parts) >= 2:
                try:
                    current_do = float(parts[1])
                    do_label.config(text=f"💧 DO: {current_do:.2f} mg/L")
                    if save_data:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"[{current_time}] ✅ SAVED DO: {current_do:.2f} mg/L\n", "green")
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 📡 DO: {current_do:.2f} mg/L\n", "green")
                    text_box.see(tk.END)
                    updated = True
                except ValueError as e:
                    text_box.insert(tk.END, f"[DO ERR] {e}\n", "red")
                    text_box.see(tk.END)

        # ========== FORMAT 4: $TEMP or $Temp,value ==========
        elif "$TEMP" in line or "$Temp" in line or "$temp" in line:
            parts = line.split(',')
            if len(parts) >= 2:
                try:
                    current_temp = float(parts[1])
                    temp_label.config(text=f"🔥 Temperature: {current_temp:.2f}°C")
                    if save_data:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"[{current_time}] ✅ SAVED Temp: {current_temp:.2f}°C\n", "red")
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 📡 Temp: {current_temp:.2f}°C\n", "red")
                    text_box.see(tk.END)
                    updated = True
                except ValueError as e:
                    text_box.insert(tk.END, f"[TEMP ERR] {e}\n", "red")
                    text_box.see(tk.END)
        # ========== FORMAT 5: $PRESS or $Pressure,value ==========
        elif "$PRESS" in line or "$Pressure" in line or "$press" in line:
            parts = line.split(',')
            if len(parts) >= 2:
                try:
                    current_pressure = float(parts[1])
                    pressure_label.config(text=f"🌡️ Pressure: {current_pressure:.2f} bar")
                    if save_data:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"[{current_time}] ✅ SAVED Pressure: {current_pressure:.2f} bar\n", "goldenrod")
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 📡 Pressure: {current_pressure:.2f} bar\n", "goldenrod")
                    text_box.see(tk.END)
                    updated = True
                except ValueError as e:
                    text_box.insert(tk.END, f"[PRESS ERR] {e}\n", "red")
                    text_box.see(tk.END)

        # ========== FORMAT 6: Simple CSV (pH,DO,Temp,Pressure) ==========
        elif ',' in line and not line.startswith('$'):
            parts = line.split(',')
            if len(parts) >= 4:
                try:
                    current_ph = float(parts[0])
                    current_do = float(parts[1])
                    current_temp = float(parts[2])
                    current_pressure = float(parts[3])
                    
                    ph_label.config(text=f"🌊 pH: {current_ph:.2f}")
                    do_label.config(text=f"💧 DO: {current_do:.2f} mg/L")
                    temp_label.config(text=f"🔥 Temperature: {current_temp:.2f}°C")
                    pressure_label.config(text=f"🌡️ Pressure: {current_pressure:.2f} bar")
                    
                    if save_data:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"[{current_time}] ✅ SAVED TO SD CARD:\n", "green")
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 📡 LIVE READING:\n", "cyan")
                    
                    text_box.insert(tk.END, f"  🌊 pH: {current_ph:.2f}\n", "blue")
                    text_box.insert(tk.END, f"  💧 DO: {current_do:.2f} mg/L\n", "green")
                    text_box.insert(tk.END, f"  🔥 Temp: {current_temp:.2f}°C\n", "red")
                    text_box.insert(tk.END, f"  🌡️ Press: {current_pressure:.2f} bar\n\n", "goldenrod")
                    text_box.see(tk.END)
                    updated = True
                except ValueError as e:
                    text_box.insert(tk.END, f"[CSV ERR] {e}\n", "red")
                    text_box.see(tk.END)

        # ========== FORMAT 7: Multi-line formatted readings ==========
        if not updated:
            # PH Value format: "PH Value:   11.73"
            if "PH Value:" in line or "PH value:" in line:
                match = re.search(r"PH [Vv]alue:\s*([-+]?\d*\.?\d+)", line)
                if match:
                    current_ph = float(match.group(1))
                    ph_label.config(text=f"🌊 pH: {current_ph:.2f}")
                    if save_data:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"[{current_time}] ✅ SAVED pH: {current_ph:.2f}\n", "green")
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 📡 pH: {current_ph:.2f}\n", "blue")
                    text_box.see(tk.END)
                    updated = True

            # DO Value: "DO Value:   963 ug/L"
            elif "DO Value:" in line or "DO value:" in line:
                match = re.search(r"DO [Vv]alue:\s*([-+]?\d*\.?\d+)", line)
                if match:
                    current_do = float(match.group(1))
                    do_label.config(text=f"💧 DO: {current_do:.2f} mg/L")
                    if save_data:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"[{current_time}] ✅ SAVED DO: {current_do:.2f} mg/L\n", "green")
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 📡 DO: {current_do:.2f} mg/L\n", "green")
                    text_box.see(tk.END)
                    updated = True

            # Temperature: "Temp: 27.53 °C"
            elif "Temp:" in line or "temp:" in line:
                match = re.search(r"[Tt]emp:\s*([-+]?\d*\.?\d+)", line)
                if match:
                    current_temp = float(match.group(1))
                    temp_label.config(text=f"🔥 Temperature: {current_temp:.2f}°C")
                    if save_data:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"[{current_time}] ✅ SAVED Temp: {current_temp:.2f}°C\n", "red")
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 📡 Temp: {current_temp:.2f}°C\n", "red")
                    text_box.see(tk.END)
                    updated = True

            # Pressure: "Pressure: 953.07 mbar"
            elif "Pressure:" in line or "pressure:" in line:
                match = re.search(r"[Pp]ressure:\s*([-+]?\d*\.?\d+)", line)
                if match:
                    current_pressure = float(match.group(1))
                    pressure_label.config(text=f"🌡️ Pressure: {current_pressure:.2f} bar")
                    if save_data:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"[{current_time}] ✅ SAVED Pressure: {current_pressure:.2f} bar\n", "goldenrod")
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 📡 Pressure: {current_pressure:.2f} bar\n", "goldenrod")
                    text_box.see(tk.END)
                    updated = True

        # ========== FORMAT 8: Raw fallback ==========
        if not updated:
            if line.strip() and "---" not in line and "===" not in line:
                text_box.insert(tk.END, f"[{current_time}] RAW: {line}\n", "white")
                text_box.see(tk.END)

    except Exception as e:
        text_box.insert(tk.END, f"ERROR in update_display: {e}\n", "red")
        text_box.see(tk.END)

# -------------------- Save Sensor Data --------------------
def save_sensor_data(timestamp, ph, do, temp, pressure):
    global csv_file, csv_writer, continuous_csv_file, continuous_csv_writer
    
    sensor_data_list.append({
        "timestamp": timestamp,
        "pH": f"{ph:.2f}",
        "DO": f"{do:.2f}",
        "Temperature": f"{temp:.2f}",
        "Pressure": f"{pressure:.2f}"
    })

    if len(sensor_data_list) > 10000:
        sensor_data_list.pop(0)

    # Continuous CSV
    try:
        if continuous_csv_file and continuous_csv_writer:
            continuous_csv_writer.writerow({
                "timestamp": timestamp,
                "pH": f"{ph:.2f}",
                "DO": f"{do:.2f}",
                "Temperature": f"{temp:.2f}",
                "Pressure": f"{pressure:.2f}"
            })
            continuous_csv_file.flush()
    except Exception as e:
        print(f"Error writing continuous CSV: {e}")

    # Interval CSV
    try:
        if csv_file and csv_writer:
            csv_writer.writerow({
                "timestamp": timestamp,
                "pH": f"{ph:.2f}",
                "DO": f"{do:.2f}",
                "Temperature": f"{temp:.2f}",
                "Pressure": f"{pressure:.2f}"
            })
            csv_file.flush()
    except Exception as e:
        print(f"Error writing interval CSV: {e}")

    data_count_label.config(text=f"📊 Stored Readings: {len(sensor_data_list)}")

# -------------------------------------------
# TIME SAMPLING DIALOG (VERY LARGE)
# -------------------------------------------
def open_time_sampling_dialog():
    global sampling_window
    
    sampling_window = tk.Toplevel(root)
    sampling_window.title("⏱️ Time-Based Sampling")
    sampling_window.geometry("500x650")
    sampling_window.configure(bg="#f0f0f0")
    sampling_window.resizable(False, False)

    title_label = tk.Label(sampling_window, text="Configure Time-Based Interval Sampling", 
                          font=("Arial", 14, "bold"), bg="#f0f0f0")
    title_label.pack(pady=15)

    instruction = tk.Label(
        sampling_window,
        text="Teensy will take readings at set intervals ONLY within time window",
        font=("Arial", 9, "italic"), bg="#f0f0f0", fg="#666"
    )
    instruction.pack(pady=5)
    # ---------------- TIME WINDOW CONFIG ----------------
    time_window_frame = tk.LabelFrame(
        sampling_window, text="⏰ Operating Time Window",
        font=("Arial", 11, "bold"), bg="#f0f0f0", fg="#007A99"
    )
    time_window_frame.pack(pady=10, padx=20, fill="x")

    # START TIME
    tk.Label(time_window_frame, text="Start Time:", 
            font=("Arial", 10, "bold"), bg="#f0f0f0").grid(
        row=0, column=0, padx=10, pady=10, sticky="w"
    )

    start_hour_spinbox = tk.Spinbox(
        time_window_frame, from_=0, to=23, width=5,
        font=("Arial", 10), format="%02.0f"
    )
    start_hour_spinbox.grid(row=0, column=1, padx=2)
    start_hour_spinbox.delete(0, tk.END)
    start_hour_spinbox.insert(0, "08")

    tk.Label(time_window_frame, text=":", font=("Arial", 12, "bold"),
             bg="#f0f0f0").grid(row=0, column=2)

    start_minute_spinbox = tk.Spinbox(
        time_window_frame, from_=0, to=59, width=5,
        font=("Arial", 10), format="%02.0f"
    )
    start_minute_spinbox.grid(row=0, column=3, padx=2)
    start_minute_spinbox.delete(0, tk.END)
    start_minute_spinbox.insert(0, "00")

    tk.Label(time_window_frame, text=":", font=("Arial", 12, "bold"),
             bg="#f0f0f0").grid(row=0, column=4)

    start_second_spinbox = tk.Spinbox(
        time_window_frame, from_=0, to=59, width=5,
        font=("Arial", 10), format="%02.0f"
    )
    start_second_spinbox.grid(row=0, column=5, padx=2)
    start_second_spinbox.delete(0, tk.END)
    start_second_spinbox.insert(0, "00")

    # END TIME
    tk.Label(time_window_frame, text="End Time:", 
            font=("Arial", 10, "bold"), bg="#f0f0f0").grid(
        row=1, column=0, padx=10, pady=10, sticky="w"
    )

    end_hour_spinbox = tk.Spinbox(
        time_window_frame, from_=0, to=23, width=5,
        font=("Arial", 10), format="%02.0f"
    )
    end_hour_spinbox.grid(row=1, column=1, padx=2)
    end_hour_spinbox.delete(0, tk.END)
    end_hour_spinbox.insert(0, "18")

    tk.Label(time_window_frame, text=":", font=("Arial", 12, "bold"),
             bg="#f0f0f0").grid(row=1, column=2)

    end_minute_spinbox = tk.Spinbox(
        time_window_frame, from_=0, to=59, width=5,
        font=("Arial", 10), format="%02.0f"
    )
    end_minute_spinbox.grid(row=1, column=3, padx=2)
    end_minute_spinbox.delete(0, tk.END)
    end_minute_spinbox.insert(0, "00")

    tk.Label(time_window_frame, text=":", font=("Arial", 12, "bold"),
             bg="#f0f0f0").grid(row=1, column=4)

    end_second_spinbox = tk.Spinbox(
        time_window_frame, from_=0, to=59, width=5,
        font=("Arial", 10), format="%02.0f"
    )
    end_second_spinbox.grid(row=1, column=5, padx=2)
    end_second_spinbox.delete(0, tk.END)
    end_second_spinbox.insert(0, "00")

    # ---------------- SAMPLING INTERVAL ----------------
    interval_frame = tk.LabelFrame(
        sampling_window, text="⏲️ Sampling Interval",
        font=("Arial", 11, "bold"), bg="#f0f0f0", fg="#007A99"
    )
    interval_frame.pack(pady=10, padx=20, fill="x")

    tk.Label(interval_frame, text="Take reading every:",
            font=("Arial", 10, "bold"), bg="#f0f0f0").grid(
        row=0, column=0, padx=10, pady=10, sticky="w"
    )

    tk.Label(interval_frame, text="Minutes:", font=("Arial", 10),
             bg="#f0f0f0").grid(row=1, column=0, padx=20, pady=5, sticky="e")
    minutes_spinbox = tk.Spinbox(interval_frame, from_=0, to=59,
                                 width=8, font=("Arial", 10))
    minutes_spinbox.grid(row=1, column=1, padx=5, pady=5)
    minutes_spinbox.delete(0, tk.END)
    minutes_spinbox.insert(0, "10")

    tk.Label(interval_frame, text="Seconds:", font=("Arial", 10),
             bg="#f0f0f0").grid(row=2, column=0, padx=20, pady=5, sticky="e")
    seconds_spinbox = tk.Spinbox(interval_frame, from_=0, to=59,
                                 width=8, font=("Arial", 10))
    seconds_spinbox.grid(row=2, column=1, padx=5, pady=5)
    seconds_spinbox.delete(0, tk.END)
    seconds_spinbox.insert(0, "0")

    # -------------------------------------------------
    # BUTTONS: START / STOP SAMPLING
    # -------------------------------------------------
root.mainloop()
