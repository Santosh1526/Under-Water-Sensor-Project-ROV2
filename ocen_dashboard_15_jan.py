import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from PIL import Image, ImageTk, ImageEnhance
import serial
import threading
import time
import csv
import serial.tools.list_ports
from datetime import datetime, timedelta
import sys
import re

# -------------------- CONFIG --------------------
BAUD = 115200
SERIAL_TIMEOUT = 1.0

# -------------------- Global Variables --------------------
ser = None
sensor_data_list = []
csv_file_path = None
csv_writer = None
csv_file = None
continuous_csv_file = None
continuous_csv_writer = None

# runtime flags / thread handles
is_reading = False
read_thread = None
read_thread_stop = threading.Event()

# Current sensor values
current_ph = 0.0
current_do = 0.0
current_temp = 0.0
current_pressure = 0.0

# Last saved reading timestamp
last_saved_reading_time = None

# SD download variables
sd_download_active = False
sd_download_buffer = []
sd_download_file = None

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
                        root.after(0, lambda l=line: update_display(l))
                else:
                    time.sleep(0.02)
            except (serial.SerialException, OSError) as e:
                print(f"❌ Serial Exception in read loop: {e}")
                try:
                    text_box.insert(tk.END, f"[SERIAL ERROR] {e}\n", "red")
                    text_box.see(tk.END)
                except:
                    pass
                is_reading = False
                read_thread_stop.set()
                try:
                    if ser:
                        ser.close()
                except:
                    pass
                ser = None
                break
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
def update_display(line):
    """Parse incoming data and update GUI labels with sensor values"""
    global current_ph, current_do, current_temp, current_pressure, last_saved_reading_time
    global sd_download_active, sd_download_buffer, sd_download_file

    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated = False
        is_saved_reading = False

        # ========== SD DOWNLOAD PROTOCOL ==========
        if sd_download_active:
            if line == "SD_DOWNLOAD_END":
                # Download complete
                if sd_download_file:
                    sd_download_file.write("\n".join(sd_download_buffer))
                    sd_download_file.close()
                    sd_download_file = None
                    
                text_box.insert(tk.END, f"\n{'='*70}\n", "green")
                text_box.insert(tk.END, f"✅ SD CARD DOWNLOAD COMPLETE!\n", "green")
                text_box.insert(tk.END, f"📊 Total lines received: {len(sd_download_buffer)}\n", "cyan")
                text_box.insert(tk.END, f"{'='*70}\n\n", "green")
                text_box.see(tk.END)
                
                messagebox.showinfo("Download Complete", 
                    f"✅ SD Card data downloaded successfully!\n\n"
                    f"📊 Total lines: {len(sd_download_buffer)}\n"
                    f"💾 File saved")
                
                sd_download_active = False
                sd_download_buffer = []
                download_sd_button.config(state="normal", text="📥 Download SD Card")
                status_label.config(text="📊 Status: Connected - Monitoring", fg="#00BFFF")
                return
            
            elif line.startswith("SD_DOWNLOAD_ERROR"):
                # Download error
                if sd_download_file:
                    sd_download_file.close()
                    sd_download_file = None
                
                text_box.insert(tk.END, f"\n❌ SD DOWNLOAD ERROR: {line}\n\n", "red")
                text_box.see(tk.END)
                
                messagebox.showerror("Download Error", 
                    f"❌ SD Card download failed:\n\n{line}")
                
                sd_download_active = False
                sd_download_buffer = []
                download_sd_button.config(state="normal", text="📥 Download SD Card")
                status_label.config(text="📊 Status: Connected - Monitoring", fg="#00BFFF")
                return
            
            elif line.startswith("SD_DOWNLOAD_PROGRESS"):
                # Progress update
                parts = line.split(":")
                if len(parts) > 1:
                    text_box.insert(tk.END, f"📥 {parts[1]}\n", "cyan")
                    text_box.see(tk.END)
                return
            
            else:
                # Regular SD data line
                sd_download_buffer.append(line)
                
                # Update progress every 50 lines
                if len(sd_download_buffer) % 50 == 0:
                    text_box.insert(tk.END, f"📥 Received {len(sd_download_buffer)} lines...\n", "cyan")
                    text_box.see(tk.END)
                return

        # ========== PRIMARY FORMAT: $Params,pH*100,DO*10,Temp*50,Pressure*1000,FLAG ==========
        if "$Params" in line or "$params" in line:
            parts = line.split(',')
            if len(parts) >= 5:
                try:
                    current_ph = float(parts[1]) / 100.0
                    current_do = float(parts[2]) / 10.0
                    current_temp = float(parts[3]) / 50.0
                    current_pressure = float(parts[4]) / 1000.0
                    
                    if len(parts) >= 6 and "SAVED" in parts[5].upper():
                        is_saved_reading = True
                        last_saved_reading_time = datetime.now()
                    
                    ph_label.config(text=f"🌊 pH: {current_ph:.2f}")
                    do_label.config(text=f"💧 DO: {current_do:.2f} mg/L")
                    temp_label.config(text=f"🔥 Temperature: {current_temp:.2f}°C")
                    pressure_label.config(text=f"🌡️ Pressure: {current_pressure:.2f} mbar")
                    
                    if is_saved_reading:
                        save_sensor_data(current_time, current_ph, current_do, current_temp, current_pressure)
                        text_box.insert(tk.END, f"\n{'='*70}\n", "white")
                        text_box.insert(tk.END, f"[{current_time}] ✅ SD CARD READING SAVED:\n", "green")
                        text_box.insert(tk.END, f"{'='*70}\n", "white")
                        text_box.insert(tk.END, f"  🌊 pH: {current_ph:.2f}\n", "blue")
                        text_box.insert(tk.END, f"  💧 DO: {current_do:.2f} mg/L\n", "green")
                        text_box.insert(tk.END, f"  🔥 Temp: {current_temp:.2f}°C\n", "red")
                        text_box.insert(tk.END, f"  🌡️ Pressure: {current_pressure:.2f} mbar\n", "goldenrod")
                        text_box.insert(tk.END, f"  💾 Saved to: SD Card + CSV File\n", "cyan")
                        text_box.insert(tk.END, f"{'='*70}\n\n", "white")
                        
                        status_label.config(text="📊 Status: Reading Saved to SD + CSV", fg="#00FF00")
                        root.after(3000, lambda: status_label.config(text="📊 Status: Connected - Monitoring", fg="#00BFFF"))
                    else:
                        text_box.insert(tk.END, f"[{current_time}] 💓 Heartbeat - Display Updated\n", "cyan")
                        status_label.config(text="📊 Status: Live Display Update", fg="#00BFFF")
                    
                    text_box.see(tk.END)
                    updated = True
                    
                except ValueError as e:
                    text_box.insert(tk.END, f"[PARSE ERR] {e}\n", "red")
                    text_box.see(tk.END)

        # ========== Show system messages ==========
        if not updated:
            if any(keyword in line for keyword in ["READING #", "Time:", "Sleeping", "WAKING UP", 
                                                    "SD card", "Counter", "Runtime", "Temperature sensor",
                                                    "Pressure sensor", "Duration"]):
                if "READING #" in line:
                    text_box.insert(tk.END, f"\n{'='*70}\n", "yellow")
                    text_box.insert(tk.END, f"{line}\n", "yellow")
                    text_box.insert(tk.END, f"{'='*70}\n", "yellow")
                elif "Sleeping" in line:
                    text_box.insert(tk.END, f"\n😴 {line}\n", "cyan")
                    text_box.insert(tk.END, "⏰ Next reading in 30 minutes...\n", "yellow")
                    text_box.insert(tk.END, "💓 Display will remain updated with heartbeat data\n\n", "cyan")
                    status_label.config(text="😴 Status: Sleeping (Next reading in 30 min)", fg="#FFA500")
                elif "WAKING UP" in line:
                    text_box.insert(tk.END, f"\n⏰ {line}\n", "green")
                    text_box.insert(tk.END, "📊 Taking scheduled reading...\n\n", "green")
                    status_label.config(text="⏰ Status: Taking Reading", fg="#00FF00")
                elif "✓" in line or "✗" in line:
                    color = "green" if "✓" in line else "red"
                    text_box.insert(tk.END, f"{line}\n", color)
                else:
                    text_box.insert(tk.END, f"{line}\n", "white")
                text_box.see(tk.END)

    except Exception as e:
        text_box.insert(tk.END, f"ERROR in update_display: {e}\n", "red")
        text_box.see(tk.END)

# -------------------- Save Sensor Data --------------------
def save_sensor_data(timestamp, ph, do, temp, pressure):
    """Store sensor readings and save to BOTH continuous and interval CSV files"""
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
        print(f"Error writing to continuous CSV: {e}")

    data_count_label.config(text=f"📊 Saved Readings: {len(sensor_data_list)}")

# -------------------- Download SD Card Data --------------------
def download_sd_card():
    """Request SD card data download from Teensy"""
    global ser, sd_download_active, sd_download_buffer, sd_download_file

    if not ser or not getattr(ser, "is_open", False):
        messagebox.showerror("Not Connected", "⚠️ Please connect to Teensy first!")
        return

    if sd_download_active:
        messagebox.showwarning("Download Active", "⚠️ SD download already in progress!")
        return

    # Ask user for save location
    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        initialfile=f"Datalog_Download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )

    if not file_path:
        return

    try:
        # Open file for writing
        sd_download_file = open(file_path, 'w')
        sd_download_buffer = []
        sd_download_active = True

        # Update UI
        download_sd_button.config(state="disabled", text="⏳ Downloading...")
        status_label.config(text="📥 Status: Downloading SD Card...", fg="#FFA500")

        text_box.insert(tk.END, f"\n{'='*70}\n", "cyan")
        text_box.insert(tk.END, f"📥 REQUESTING SD CARD DOWNLOAD\n", "cyan")
        text_box.insert(tk.END, f"{'='*70}\n", "cyan")
        text_box.insert(tk.END, f"💾 Save location: {file_path}\n", "yellow")
        text_box.insert(tk.END, f"⏳ Waiting for Teensy response...\n\n", "yellow")
        text_box.see(tk.END)

        # Send download command to Teensy
        ser.write(b"DOWNLOAD_SD\n")
        ser.flush()

        print("📥 SD download request sent to Teensy")

    except Exception as e:
        messagebox.showerror("Download Error", f"Failed to start download:\n\n{e}")
        sd_download_active = False
        sd_download_buffer = []
        if sd_download_file:
            sd_download_file.close()
            sd_download_file = None
        download_sd_button.config(state="normal", text="📥 Download SD Card")

# -------------------- Connect to Teensy --------------------
def connect_teensy():
    """Connect to Teensy and start read thread"""
    global ser, is_reading, read_thread, read_thread_stop, continuous_csv_file, continuous_csv_writer

    if ser and getattr(ser, "is_open", False):
        messagebox.showinfo("Already Connected", "✅ Already connected to Teensy!")
        return

    port = find_teensy_port()

    if not port:
        response = messagebox.askyesno("Teensy Not Found",
            "⚠️ Could not find Teensy!\n\nTry manual port entry?")
        if response:
            port = simpledialog.askstring("Manual Port",
                "Enter port (e.g., COM3, /dev/ttyACM0):")
        if not port:
            text_box.insert(tk.END, "❌ No port provided. Connect aborted.\n", "red")
            text_box.see(tk.END)
            return

    try:
        try:
            continuous_csv_file_path = f"teensy_30min_readings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            continuous_csv_file = open(continuous_csv_file_path, 'w', newline='')
            continuous_csv_writer = csv.DictWriter(continuous_csv_file, 
                                                   fieldnames=["timestamp", "pH", "DO", "Temperature", "Pressure"])
            continuous_csv_writer.writeheader()
            continuous_csv_file.flush()
            text_box.insert(tk.END, f"📝 CSV file created: {continuous_csv_file_path}\n", "cyan")
        except Exception as e:
            messagebox.showerror("File Error", f"Could not create CSV file:\n{e}")
            return

        text_box.insert(tk.END, f"🔌 Connecting to {port} at {BAUD} baud...\n", "white")
        text_box.see(tk.END)
        ser = serial.Serial(port, BAUD, timeout=SERIAL_TIMEOUT)
        time.sleep(0.2)
        try:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except Exception:
            pass

        is_reading = True
        read_thread_stop.clear()
        read_thread = threading.Thread(target=read_serial_data, daemon=True)
        read_thread.start()

        text_box.insert(tk.END, "\n" + "="*70 + "\n", "green")
        text_box.insert(tk.END, f"✅ CONNECTED to {port}\n", "green")
        text_box.insert(tk.END, "="*70 + "\n\n", "green")
        text_box.insert(tk.END, "📊 Mode: 30-Minute Interval Monitoring\n", "cyan")
        text_box.insert(tk.END, "💾 All scheduled readings saved to SD + CSV\n", "cyan")
        text_box.insert(tk.END, "💓 Display updates continuously (including during sleep)\n", "cyan")
        text_box.insert(tk.END, "⏰ Readings taken every 30 minutes\n", "cyan")
        text_box.insert(tk.END, "📁 CSV file: " + continuous_csv_file_path + "\n", "yellow")
        text_box.insert(tk.END, "📥 Use 'Download SD Card' to retrieve all SD data\n\n", "cyan")
        text_box.see(tk.END)
        
        connect_button.config(text="✅ Connected", bg="#00AA00", state="disabled")
        download_sd_button.config(state="normal")
        status_label.config(text="📊 Status: Connected - Monitoring", fg="#00BFFF")
        
        messagebox.showinfo("Connected", 
                          f"✅ Connected to {port}\n\n"
                          f"📊 30-Minute Interval Mode Active\n\n"
                          f"Readings saved to:\n{continuous_csv_file_path}\n\n"
                          f"You can now download SD card data!")
        
    except Exception as e:
        text_box.insert(tk.END, f"❌ Connection failed: {e}\n", "red")
        text_box.see(tk.END)
        messagebox.showerror("Connection Error", f"Failed to connect to {port}\n\n{e}")

# -------------------- Disconnect --------------------
def disconnect_teensy():
    """Disconnect from Teensy and stop reading thread safely"""
    global ser, is_reading, read_thread_stop, read_thread, continuous_csv_file, continuous_csv_writer

    is_reading = False
    read_thread_stop.set()
    if read_thread and read_thread.is_alive():
        read_thread.join(timeout=1.0)

    if continuous_csv_file:
        try:
            continuous_csv_file.close()
            text_box.insert(tk.END, "\n💾 CSV file saved and closed\n", "green")
            text_box.see(tk.END)
        except Exception as e:
            print(f"Error closing continuous CSV: {e}")
    
    continuous_csv_file = None
    continuous_csv_writer = None

    if ser and getattr(ser, "is_open", False):
        try:
            ser.close()
        except:
            pass
    ser = None

    text_box.insert(tk.END, "\n⚠️ DISCONNECTED\n\n", "red")
    text_box.see(tk.END)
    connect_button.config(text="🔌 Connect to Teensy", bg="#007A99", state="normal")
    download_sd_button.config(state="disabled")
    status_label.config(text="📊 Status: Disconnected", fg="#FF0000")
    messagebox.showinfo("Disconnected", "Serial connection closed.\nCSV file saved.")

# -------------------- Download Data --------------------
def download_data():
    """Download all sensor data to CSV"""
    global sensor_data_list

    if not sensor_data_list:
        messagebox.showwarning("No Data",
            "⚠️ No sensor data to download!\n\nConnect to Teensy and wait for scheduled readings.")
        return

    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv")],
        initialfile=f"teensy_download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

    if file_path:
        try:
            with open(file_path, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=["timestamp", "pH", "DO", "Temperature", "Pressure"])
                writer.writeheader()
                writer.writerows(sensor_data_list)

            messagebox.showinfo("Success",
                f"💾 Saved {len(sensor_data_list)} readings to:\n\n{file_path}")

            text_box.insert(tk.END, f"💾 Downloaded {len(sensor_data_list)} readings to {file_path}\n", "green")
            text_box.see(tk.END)
        except Exception as e:
            messagebox.showerror("Save Error", f"Error saving file:\n{e}")

# -------------------- Load Background Image --------------------
def load_background_image():
    """Load and prepare background image"""
    try:
        # Ask user to select the image file
        file_path = filedialog.askopenfilename(
            title="Select Background Image",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.gif *.bmp")]
        )
        
        if file_path:
            # Load image
            img = Image.open(file_path)
            # Resize to fit window (1000x800)
            img = img.resize((1000, 800), Image.Resampling.LANCZOS)
            # Optional: Darken the image slightly for better text visibility
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(0.7)  # 0.7 = 70% brightness
            
            return ImageTk.PhotoImage(img)
        return None
    except Exception as e:
        print(f"Error loading background image: {e}")
        messagebox.showerror("Image Load Error", f"Could not load image:\n{e}")
        return None

# -------------------- GUI Setup --------------------
root = tk.Tk()
root.title("🌊 Ocean Sensor Dashboard - Teensy 4.1 (30-Min Intervals)")
root.geometry("1000x800")
root.resizable(False, False)

def on_closing():
    global is_reading, ser, read_thread_stop, csv_file, continuous_csv_file
    is_reading = False
    read_thread_stop.set()
    
    if csv_file:
        try:
            csv_file.close()
        except:
            pass
    
    if continuous_csv_file:
        try:
            continuous_csv_file.close()
        except:
            pass
    
    try:
        if ser and getattr(ser, "is_open", False):
            ser.close()
    except:
        pass
    root.destroy()
    try:
        sys.exit(0)
    except:
        pass

root.protocol("WM_DELETE_WINDOW", on_closing)

# Create canvas for background
canvas = tk.Canvas(root, width=1000, height=800, bg="#001F33", highlightthickness=0)
canvas.pack(fill="both", expand=True)

# Load background image on startup
print("Please select your ocean background image...")
bg_image = load_background_image()

if bg_image:
    # Display background image
    canvas.create_image(0, 0, image=bg_image, anchor="nw")
    # Keep a reference to prevent garbage collection
    canvas.bg_image = bg_image
else:
    # Use default blue background if no image selected
    canvas.config(bg="#001F33")

title_label = tk.Label(root, text="🌊 Teensy 4.1 - 30 Minute Interval Monitor 🌊",
                       font=("Times", 24, "bold"), fg="#00E1FF", bg="#0E0F0F")
title_label.place(x=150, y=15)

clock_label = tk.Label(root, font=("Consolas", 11, "bold"), bg="#0E0F0F", fg="white")
clock_label.place(x=850, y=20)

def update_clock():
    try:
        clock_label.config(text=time.strftime("⏰ %H:%M:%S"))
        root.after(1000, update_clock)
    except:
        pass

update_clock()

data_count_label = tk.Label(root, text="📊 Saved Readings: 0",
                           font=("Times", 14, "bold"), bg="#001F33", fg="#00FF00")
data_count_label.place(x=20, y=20)

status_label = tk.Label(root, text="📊 Status: Not Connected",
                       font=("Times", 12, "bold"), bg="#001F33", fg="#FF0000")
status_label.place(x=20, y=50)

# -------------------- Buttons --------------------
connect_button = tk.Button(root, text="🔌 Connect to Teensy", command=connect_teensy,
                           font=("Times", 12, "bold"), bg="#021519", fg="white",
                           relief="flat", width=18, height=2)
connect_button.place(x=50, y=90)

disconnect_button = tk.Button(root, text="⚠️ Disconnect", command=disconnect_teensy,
                              font=("Times", 12, "bold"), bg="#CC0000", fg="white",
                              relief="flat", width=14, height=2)
disconnect_button.place(x=290, y=90)

download_button = tk.Button(root, text="💾 Download CSV", command=download_data,
                            font=("Times", 12, "bold"), bg="#021519", fg="white",
                            relief="flat", width=15, height=2)
download_button.place(x=490, y=90)

download_sd_button = tk.Button(root, text="📥 Download SD Card", command=download_sd_card,
                               font=("Times", 12, "bold"), bg="#007A00", fg="white",
                               relief="flat", width=18, height=2, state="disabled")
download_sd_button.place(x=690, y=90)

panel = tk.Frame(root, bd=0, highlightbackground="#00BFFF", highlightthickness=3, bg="#0D1113")
panel.place(x=50, y=160, width=900, height=600)

def create_sensor_label(parent, text, color, y):
    frame = tk.Frame(parent, bg=color, highlightthickness=0, bd=0)
    frame.place(x=80, y=y, width=740, height=65)
    label = tk.Label(frame, text=text, font=("Arial", 24, "bold"),
                     bg=color, fg="#000000", anchor="w", padx=20)
    label.pack(fill="both", expand=True)
    return label

ph_label = create_sensor_label(panel, "🌊 pH: --", "#B3F0FF", 30)
do_label = create_sensor_label(panel, "💧 DO: -- mg/L", "#FFF0B3", 110)
temp_label = create_sensor_label(panel, "🔥 Temperature: --°C", "#FFB3B3", 190)
pressure_label = create_sensor_label(panel, "🌡️ Pressure: -- mbar", "#B3FFCC", 270)

text_frame = tk.Frame(panel, bg="#001F33")
text_frame.place(x=50, y=360, width=800, height=220)

scrollbar = tk.Scrollbar(text_frame)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

text_box = tk.Text(text_frame, height=13, width=90, bg="#000B1A",
                   fg="#00FF00", font=("Consolas", 9),
                   yscrollcommand=scrollbar.set, relief="flat")
text_box.pack(side=tk.LEFT, fill="both", expand=True)
scrollbar.config(command=text_box.yview)

for color in ["blue", "green", "red", "goldenrod", "white", "cyan", "yellow"]:
    text_box.tag_config(color, foreground=color)

text_box.insert(tk.END, "🌊 TEENSY 4.1 - 30 MINUTE INTERVAL MONITOR\n", "cyan")
text_box.insert(tk.END, "=" * 80 + "\n\n", "white")
text_box.insert(tk.END, "📡 Click 'Connect to Teensy' to start monitoring\n\n", "white")
text_box.insert(tk.END, "⏰ OPERATING MODE:\n", "yellow")
text_box.insert(tk.END, "   • Teensy takes readings every 30 minutes\n", "white")
text_box.insert(tk.END, "   • Each reading is saved to SD card + GUI CSV file\n", "white")
text_box.insert(tk.END, "   • Display updates continuously (even during sleep)\n", "white")
text_box.insert(tk.END, "   • Expected ~4,320 readings over 90 days\n", "white")
text_box.insert(tk.END, "   • Serial connection remains active throughout\n\n", "white")
text_box.insert(tk.END, "💾 Click 'Download CSV' to save GUI readings\n", "white")
text_box.insert(tk.END, "📥 Click 'Download SD Card' to retrieve all SD data\n\n", "cyan")
text_box.insert(tk.END, "✅ Ready to connect!\n", "green")

footer = tk.Label(root,
    text="Teensy 4.1 - 30 Minute Intervals | Continuous Monitoring | SD + CSV Logging | Remote SD Download",
    font=("Arial", 10, "italic"), fg="#FFFFFF", bg="#001F33")
footer.place(x=120, y=770)

print("\n" + "="*70)
print("🌊 TEENSY 4.1 - 30 MINUTE INTERVAL DASHBOARD")
print("="*70)
print("Ready to connect to Teensy...")
print("\nFeatures:")
print("  • Receives data every 30 minutes from Teensy")
print("  • Displays live sensor values continuously")
print("  • Saves all scheduled readings to CSV")
print("  • Maintains connection during sleep periods")
print("  • Synchronized with Teensy SD card logging")
print("  • Download SD card data remotely via serial")
print("="*70 + "\n")

root.mainloop()