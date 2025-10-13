import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageEnhance
import serial, threading, time, csv, serial.tools.list_ports
from tkcalendar import Calendar  # pip install tkcalendar

# -------------------- Find Teensy Port Automatically --------------------
def find_teensy_port():
    ports = serial.tools.list_ports.comports()
    for port in ports:
        if "Teensy" in port.description or "usbmodem" in port.device:
            return port.device
    return None

ser = None
teensy_port = find_teensy_port()
if teensy_port:
    try:
        ser = serial.Serial(teensy_port, 57600, timeout=1)
        print(f"✅ Connected to Teensy on port: {teensy_port}")
    except Exception as e:
        print(f"Error connecting to Teensy: {e}")

sensor_data_list = []

# -------------------- Default Variables --------------------
sampling_interval = 1  # default 1 second
custom_datetime = None

# -------------------- Serial Reading --------------------
def read_serial_data():
    global ser
    try:
        while True:
            if ser and ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    update_display(line)
            time.sleep(sampling_interval)
    except Exception as e:
        print(f"Serial Error: {e}")
        messagebox.showerror("Serial Error", str(e))

# -------------------- Update Sensor Data --------------------

def update_display(line):
    sensor_data_list.append(line)

    try:
        # --- Handle $Params line ---
        if line.startswith("$Params"):
            parts = [x.strip() for x in line.split(',')]

            # Expecting: $Params ,1274 ,28 ,1262 ,21 ,0.19 ,1
            if len(parts) >= 7:
                ph_val = float(parts[1]) / 100   # Example conversion
                do_val = float(parts[2]) / 10
                temp_val = float(parts[3]) / 50
                pressure_val = float(parts[4]) / 1000

                ph_label.config(text=f"🌊 pH: {ph_val:.2f}")
                do_label.config(text=f"💧 DO: {do_val:.2f}")
                temp_label.config(text=f"🔥 Temperature: {temp_val:.2f}°C")
                pressure_label.config(text=f"🌡️ Pressure: {pressure_val:.2f} bar")

                color = "cyan"
            else:
                color = "white"

        # --- Handle individual sensor lines (optional) ---
        elif line.startswith("$PH"):
            value = float(line.split(',')[1])
            ph_label.config(text=f"🌊 pH: {value:.2f}")
            color = "blue"

        elif line.startswith("$DO"):
            value = float(line.split(',')[1])
            do_label.config(text=f"💧 DO: {value:.2f}")
            color = "green"

        elif "$TEMP" in line or "Temp" in line:
            value = float(line.split(',')[1])
            temp_label.config(text=f"🔥 Temperature: {value:.2f}°C")
            color = "red"

        elif "$PRESS" in line or "Pressure" in line:
            value = float(line.split(',')[1])
            pressure_label.config(text=f"🌡️ Pressure: {value:.2f} bar")
            color = "goldenrod"

        else:
            color = "white"

        # Show on GUI text box
        text_box.insert(tk.END, line + "\n", color)
        text_box.see(tk.END)

    except Exception as e:
        print("⚠️ Parse error:", line, e)


# -------------------- Connect Button --------------------
def connect_teensy():
    global ser
    port = find_teensy_port()
    if not port:
        messagebox.showwarning("Not Found", "⚠️ Teensy not detected! Connect and try again.")
        return
    try:
        ser = serial.Serial(port, 57600, timeout=1)
        time.sleep(2)
        messagebox.showinfo("Connected", f"✅ Connected to Teensy on {port}")
        threading.Thread(target=read_serial_data, daemon=True).start()
    except Exception as e:
        messagebox.showerror("Connection Error", str(e))

# -------------------- Download Data --------------------
def download_data():
    if not sensor_data_list:
        messagebox.showwarning("No Data", "⚠️ No sensor data available to download.")
        return

    # Ask for filename
    file_path = filedialog.asksaveasfilename(
        defaultextension=".csv",
        filetypes=[("CSV Files", "*.csv")],
        title="Save Sensor Data"
    )

    if file_path:
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            # Write header
            writer.writerow(["Timestamp", "pH", "DO", "Temperature (°C)", "Pressure (bar)"])
            # Write each reading
            for reading in sensor_data_list:
                writer.writerow([reading["timestamp"], reading["pH"], reading["DO"],
                                 reading["Temperature"], reading["Pressure"]])
        messagebox.showinfo("Saved", f"💾 All sensor data saved to {file_path}")



# -------------------- GUI Setup --------------------
root = tk.Tk()
root.title("🌊 Ocean Sensor Dashboard - Teensy 4.1")
root.geometry("950x700")
root.resizable(False, False)

# -------------------- Background --------------------
bg_image = Image.open("/Users/santoshambule/Downloads/silas-baisch-K785Da4A_JA-unsplash.jpg").resize((950, 700))
enhancer = ImageEnhance.Brightness(bg_image)
bg_image = enhancer.enhance(0.6)
bg_photo = ImageTk.PhotoImage(bg_image)
canvas = tk.Canvas(root, width=950, height=700, highlightthickness=0)
canvas.pack(fill="both", expand=True)
canvas.create_image(0, 0, image=bg_photo, anchor="nw")

# -------------------- Title --------------------
title_label = tk.Label(root, text="🌊 Ocean Sensor Dashboard 🌊",
                       font=("times", 28, "bold"), fg="#B7DEE4", bg="#001F33")
title_label.place(x=230, y=20)

def glow_effect():
    colors = ["#00E1FF", "#33F2FF", "#66FFFF", "#99F9FF", "#CCFFFF"]
    i = 0
    while True:
        time.sleep(0.2)
        title_label.config(fg=colors[i % len(colors)])
        i += 1
threading.Thread(target=glow_effect, daemon=True).start()

# -------------------- Live Clock --------------------
clock_label = tk.Label(root, font=("Consolas", 12, "bold"), bg="#070C0E", fg="white")
clock_label.place(x=790, y=25)
def update_clock():
    if custom_datetime:
        clock_label.config(text=time.strftime("⏰ %Y-%m-%d %H:%M:%S", custom_datetime))
    else:
        clock_label.config(text=time.strftime("⏰ %H:%M:%S"))
    root.after(1000, update_clock)
update_clock()

# -------------------- Glass Panel --------------------
panel = tk.Frame(root, bg="#75BBD4", bd=0, highlightbackground="#84B5B5", highlightthickness=2)
panel.place(x=65, y=100, width=820, height=520)

# -------------------- Hover Animations --------------------
def hover_in(e): e.widget.config(bg="#00BFFF")
def hover_out(e): e.widget.config(bg="#007A99")

# -------------------- Buttons --------------------
connect_button = tk.Button(root, text="🔌 Connect to Teensy", command=connect_teensy,
                           font=("times", 13, "bold"), bg="#061317", fg="black",
                           relief="flat", width=18, activebackground="#6724E3")
connect_button.place(x=180, y=80)
connect_button.bind("<Enter>", hover_in)
connect_button.bind("<Leave>", hover_out)

download_button = tk.Button(root, text="💾 Download Data", command=download_data,
                            font=("times", 13, "bold"), bg="#0B0E0F", fg="black",
                            relief="flat", width=18, activebackground="#B6981C")
download_button.place(x=540, y=80)
download_button.bind("<Enter>", hover_in)
download_button.bind("<Leave>", hover_out)

# -------------------- Settings Window --------------------
def open_settings():
    settings_win = tk.Toplevel(root)
    settings_win.title("⚙️ Settings")
    settings_win.geometry("450x450")
    settings_win.resizable(False, False)
    
    # Sampling Interval
    tk.Label(settings_win, text="⏱️ Sampling Interval:", font=("times", 12, "bold"),
             bg='#0B0E0F', fg='white').place(x=20, y=20)
    sampling_var = tk.StringVar(value=str(sampling_interval))
    tk.Entry(settings_win, textvariable=sampling_var, width=10, font=("times", 12)).place(x=150, y=20)
    unit_var = tk.StringVar(value="seconds")
    tk.OptionMenu(settings_win, unit_var, "seconds", "minutes").place(x=280, y=18)

    def set_sampling_time():
        global sampling_interval
        try:
            value = float(sampling_var.get())
            if unit_var.get() == "minutes":
                value *= 60
            sampling_interval = value
            messagebox.showinfo("Saved", f"Sampling interval set to {sampling_var.get()} {unit_var.get()} ({sampling_interval} sec)")
        except ValueError:
            messagebox.showerror("Invalid Input", "Enter valid number.")
    tk.Button(settings_win, text="Set Sampling Time", bg='#0B0E0F', fg='black',
              font=("times", 12, "bold"), command=set_sampling_time).place(x=150, y=60)

    # System time
    def set_system_time():
        global custom_datetime
        custom_datetime = time.localtime()
        messagebox.showinfo("Saved", f"System time will be used: {time.strftime('%Y-%m-%d %H:%M:%S', custom_datetime)}")
    tk.Button(settings_win, text="Use System Time", command=set_system_time,
              font=("times", 12, "bold"), bg="#33A1C9", fg="black").place(x=30, y=160)

    # Calendar
    tk.Label(settings_win, text="Select Date:", font=("times", 10, "bold"), bg='#0B0E0F', fg='white').place(x=200, y=120)
    cal = Calendar(settings_win, selectmode='day', date_pattern='yyyy-mm-dd', background='white', foreground='black')
    cal.place(x=200, y=140)
    tk.Label(settings_win, text="HH:MM:SS", font=("times", 10, "bold"), bg='#0B0E0F', fg='white').place(x=200, y=270)
    time_var = tk.StringVar(value="00:00:00")
    tk.Entry(settings_win, textvariable=time_var, width=10, font=("times", 12)).place(x=280, y=270)

    def set_custom_datetime():
        global custom_datetime
        datetime_str = f"{cal.get_date()} {time_var.get()}"
        try:
            custom_datetime = time.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
            messagebox.showinfo("Saved", f"Custom date/time set: {datetime_str}")
        except ValueError:
            messagebox.showerror("Invalid Date/Time", "Use format YYYY-MM-DD HH:MM:SS")
    tk.Button(settings_win, text="Set Custom Date & Time", command=set_custom_datetime,
              font=("times", 12, "bold"), bg="#FF8C00", fg="white").place(x=200, y=300)

settings_button = tk.Button(root, text="⚙️ Settings", command=open_settings,
                            font=("times", 13, "bold"), bg="#0A0C0D", fg="black",
                            relief="flat", width=15, activebackground="#B6981C")
settings_button.place(x=370, y=80)
settings_button.bind("<Enter>", hover_in)
settings_button.bind("<Leave>", hover_out)

# -------------------- Sensor Display Labels --------------------
def create_sensor_label(parent, text, color, y):
    frame = tk.Frame(parent, bg=color, highlightthickness=0, bd=0)
    frame.place(x=90, y=y, width=640, height=50)
    label = tk.Label(frame, text=text, font=("times", 20, "bold"),
                     bg=color, fg="#010C13", anchor="w", padx=10)
    label.pack(fill="both")
    return label

ph_label = create_sensor_label(panel, "🌊 pH: --", "#B3F0FF", 40)
do_label = create_sensor_label(panel, "💧 DO: --", "#FFF0B3", 100)
temp_label = create_sensor_label(panel, "🔥 Temperature: --", "#FFB3B3", 160)
pressure_label = create_sensor_label(panel, "🌡️ Pressure: --", "#B3FFCC", 220)

# -------------------- Text Output --------------------
text_frame = tk.Frame(panel, bg="#1B7DBE")
text_frame.place(x=60, y=290)
scrollbar = tk.Scrollbar(text_frame)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
text_box = tk.Text(text_frame, height=13, width=78, bg="#001F33",
                   fg="#E0FFFF", font=("Consolas", 11),
                   yscrollcommand=scrollbar.set, relief="flat")
text_box.pack(side=tk.LEFT)
scrollbar.config(command=text_box.yview)
for color in ["blue", "green", "red", "goldenrod", "white"]:
    text_box.tag_config(color, foreground=color)

# -------------------- Footer --------------------
footer = tk.Label(root,
    text="Developed for Teensy 4.1 | 🌤️ Ocean Research | Powered by Python Tkinter",
    font=("Segoe UI", 10, "italic"), fg="#0A0C0D", bg="#92B6CD")
footer.place(x=220, y=665)

root.mainloop()
