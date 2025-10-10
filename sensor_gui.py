import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk
import serial
import threading
import time
import csv
import serial.tools.list_ports

# -------------------- Find Teensy Port Automatically --------------------
def find_teensy_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "Teensy" in port.description or "usbmodem" in port.device:
            return port.device
    return None

# -------------------- Connect to Teensy --------------------
ser = None
teensy_port = find_teensy_port()
if teensy_port:
    try:
        ser = serial.Serial(teensy_port, 57600, timeout=1)
        print(f"✅ Connected to Teensy on port: {teensy_port}")
    except Exception as e:
        print(f"Error connecting to Teensy: {e}")

# -------------------- Read Serial Data --------------------
sensor_data_list = []

def read_serial_data():
    global ser
    try:
        while True:
            if ser and ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    update_display(line)
    except Exception as e:
        print(f"Serial Error: {e}")
        messagebox.showerror("Serial Error", str(e))

# -------------------- Update GUI Labels --------------------
def update_display(line):
    sensor_data_list.append(line)
    text_box.insert(tk.END, line + "\n")
    text_box.see(tk.END)

    if line.startswith("$PH"):
        ph_label.config(text=f"🌊 pH: {line.split(',')[-1]}")
    elif line.startswith("$DO"):
        do_label.config(text=f"💧 DO: {line.split(',')[-1]}")
    elif "Pressure" in line or "pressure" in line:
        pressure_label.config(text=f"🌡️ Pressure: {line.split(',')[-1]}")
    elif "Temp" in line or "temperature" in line:
        temp_label.config(text=f"🔥 Temperature: {line.split(',')[-1]}")

# -------------------- Connect Button --------------------
def connect_teensy():
    global ser
    port = find_teensy_port()
    if not port:
        messagebox.showwarning("Not Found", "Teensy not detected! Connect and try again.")
        return

    try:
        ser = serial.Serial(port, 57600, timeout=1)
        time.sleep(2)
        messagebox.showinfo("Connected", f"Connected to Teensy on {port}")
        threading.Thread(target=read_serial_data, daemon=True).start()
    except Exception as e:
        messagebox.showerror("Connection Error", str(e))

# -------------------- Download Data --------------------
def download_data():
    if not sensor_data_list:
        messagebox.showwarning("No Data", "No sensor data available to download.")
        return

    file_path = filedialog.asksaveasfilename(defaultextension=".csv",
                                             filetypes=[("CSV Files", "*.csv")],
                                             title="Save Sensor Data")
    if file_path:
        with open(file_path, mode='w', newline='') as f:
            writer = csv.writer(f)
            for line in sensor_data_list:
                writer.writerow(line.split(','))
        messagebox.showinfo("Saved", f"Sensor data saved to {file_path}")

# -------------------- GUI Setup --------------------
root = tk.Tk()
root.title("🌊 Ocean Sensor Dashboard - Teensy 4.1")
root.geometry("900x650")

# Light ocean-themed background
bg_image = Image.open("/Users/santoshambule/Downloads/silas-baisch-K785Da4A_JA-unsplash.jpg")
bg_image = bg_image.resize((900, 650))
bg_photo = ImageTk.PhotoImage(bg_image)

canvas = tk.Canvas(root, width=900, height=650, highlightthickness=0)
canvas.pack(fill="both", expand=True)
canvas.create_image(0, 0, image=bg_photo, anchor="nw")

# Fonts
title_font = ("Segoe UI", 24, "bold")
label_font = ("Helvetica", 14, "bold")
text_font = ("Consolas", 11)

# Title
title_label = tk.Label(root, text="🌊 Ocean Sensor Dashboard", font=title_font, bg="#E8F6F3", fg="#004D61")
title_label.place(x=220, y=15)

# Buttons
style = ttk.Style()
style.configure("TButton", font=("Helvetica", 12, "bold"), padding=8)

connect_button = ttk.Button(root, text="🔌 Connect to Teensy", command=connect_teensy)
connect_button.place(x=200, y=80)

download_button = ttk.Button(root, text="💾 Download Data", command=download_data)
download_button.place(x=500, y=80)

# Sensor Labels (soft pastel backgrounds)
ph_label = tk.Label(root, text="🌊 pH: --", font=label_font, bg="#DFF6FF", fg="#004D61", width=25, anchor="w", padx=10)
ph_label.place(x=80, y=150)

do_label = tk.Label(root, text="💧 DO: --", font=label_font, bg="#FFF6E5", fg="#7A4B00", width=25, anchor="w", padx=10)
do_label.place(x=80, y=190)

temp_label = tk.Label(root, text="🔥 Temperature: --", font=label_font, bg="#FFECEC", fg="#A80000", width=25, anchor="w", padx=10)
temp_label.place(x=80, y=230)

pressure_label = tk.Label(root, text="🌡️ Pressure: --", font=label_font, bg="#EAF8E6", fg="#004D00", width=25, anchor="w", padx=10)
pressure_label.place(x=80, y=270)

# Text box for raw data
text_box = tk.Text(root, height=15, width=100, bg="#F8F9FA", fg="#000000", font=text_font, relief="flat")
text_box.place(x=50, y=330)

# Footer
footer = tk.Label(root, text="Developed for Teensy 4.1 Sensor Monitoring | 🌤️ Powered by Python Tkinter",
                  font=("Segoe UI", 10, "italic"), fg="#004D61", bg="#E8F6F3")
footer.place(x=180, y=610)

root.mainloop()
