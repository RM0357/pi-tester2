# app.py
import tkinter as tk
from tkinter import scrolledtext
import os
import atexit
import subprocess
import threading
import readTemps

# ---------------- Tkinter root ----------------
root = tk.Tk()
root.title("Raspberry Pi Dashboard")
root.geometry("800x480")
root.resizable(False, False)

# ---------------- Logging function ----------------
def log(msg):
    info_window.configure(state='normal')
    info_window.insert(tk.END, msg + "\n")
    info_window.see(tk.END)
    info_window.configure(state='disabled')

# ---------------- RTC helper using old working logic ----------------
def rtc_run(cmd):
    """Run hwclock commands exactly like your old working script, log output"""
    try:
        result = subprocess.check_output(cmd, shell=True, text=True).strip()
        if result:
            log(result)
        else:
            log("✅ Command executed successfully.")
    except subprocess.CalledProcessError as e:
        log(f"⚠️ Error running: {cmd}\n{e.output}")

# ---------------- GPIO Setup ----------------
GPIO_PINS = [524, 525, 526]

for pin in GPIO_PINS:
    gpio_path = f"/sys/class/gpio/gpio{pin}"
    if not os.path.exists(gpio_path):
        os.system(f"sudo sh -c 'echo {pin} > /sys/class/gpio/export'")
    os.system(f"sudo sh -c 'echo out > /sys/class/gpio/gpio{pin}/direction'")

def read_pin(pin):
    try:
        with open(f"/sys/class/gpio/gpio{pin}/value", "r") as f:
            return f.read().strip()
    except:
        return "err"

def set_pin(pin, value):
    os.system(f"sudo sh -c 'echo {value} > /sys/class/gpio/gpio{pin}/value'")
    status = "HIGH" if value == "1" else "LOW"
    log(f"Pin {pin} set to {status}")

def cleanup_gpio():
    for pin in GPIO_PINS:
        os.system(f"sudo sh -c 'echo {pin} > /sys/class/gpio/unexport'")
atexit.register(cleanup_gpio)

# ---------------- Multi-frame GUI ----------------
main_frame = tk.Frame(root)
gpio_frame_panel = tk.Frame(root)
main_frame.pack(fill='both', expand=True)

# ---------------- Layout ----------------
left_frame = tk.Frame(main_frame)
left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
right_frame = tk.Frame(main_frame)
right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

# ---------------- Temperature fields ----------------
temp_labels = ["TempPi", "Temp SMPS", "Temp Ambient"]
temp_vars = [tk.StringVar(value="--") for _ in range(3)]

temp_container = tk.Frame(left_frame)
temp_container.pack(anchor='w', pady=5)

tk.Label(temp_container, text="Temps:", font=("Arial", 10)).pack(side=tk.LEFT)
for i, var in enumerate(temp_vars):
    tk.Label(temp_container, text=f"{temp_labels[i]}: ", font=("Arial", 10)).pack(side=tk.LEFT)
    tk.Label(temp_container, textvariable=var, font=("Arial", 10), width=6).pack(side=tk.LEFT, padx=5)

def update_temps():
    temps = readTemps.read_all_temps()
    for i, temp in enumerate(temps):
        if temp is not None:
            temp_vars[i].set(f"{temp:.2f}")
        else:
            temp_vars[i].set("Err")
    root.after(500, update_temps)

# ---------------- Info window ----------------
info_window = scrolledtext.ScrolledText(right_frame, width=40, height=25, state='disabled')
info_window.pack(fill=tk.BOTH, expand=True)

# ---------------- RTC / System Time ----------------
time_frame = tk.Frame(left_frame)
time_frame.pack(anchor='w', pady=(10,5))

# System time
sys_time_var = tk.StringVar()
tk.Label(time_frame, text="SysTime:", font=("Arial",10)).grid(row=0, column=0, sticky='w')
sys_time_entry = tk.Entry(time_frame, textvariable=sys_time_var, width=20, font=("Arial",10))
sys_time_entry.grid(row=0, column=1, padx=2)

# RTC time
rtc_time_var = tk.StringVar()
tk.Label(time_frame, text="RTC:", font=("Arial",10)).grid(row=1, column=0, sticky='w')
rtc_time_entry = tk.Entry(time_frame, textvariable=rtc_time_var, width=20, font=("Arial",10))
rtc_time_entry.grid(row=1, column=1, padx=2)

# Buttons to the right
btn_frame = tk.Frame(time_frame)
btn_frame.grid(row=0, column=2, rowspan=2, padx=(10,0))

tk.Button(btn_frame, text="Sys->RTC", width=10,
          command=lambda: rtc_run("sudo hwclock --systohc -f /dev/rtc && sudo hwclock -w")).pack(pady=2)

tk.Button(btn_frame, text="RTC->Sys", width=10,
          command=lambda: rtc_run("sudo hwclock --hctosys -f /dev/rtc && sudo hwclock -s")).pack(pady=2)

tk.Button(btn_frame, text="[Preset] RTC", width=10,
          command=lambda: rtc_run('sudo hwclock --set --date="2025-12-24 13:45:30"')).pack(pady=2)

# Manual RTC set
manual_frame = tk.Frame(left_frame)
manual_frame.pack(anchor='w', pady=5)
tk.Label(manual_frame, text="Set RTC (YYYY-MM-DD HH:MM:SS):", font=("Arial",10)).pack(side=tk.LEFT)
rtc_entry = tk.Entry(manual_frame, width=16)
rtc_entry.pack(side=tk.LEFT, padx=2)
tk.Button(manual_frame, text="Set",
          command=lambda: rtc_run(f'sudo hwclock --set --date="{rtc_entry.get().strip()}" && sudo hwclock --show -f /dev/rtc')).pack(side=tk.LEFT, padx=2)

# ---------------- Threaded update of time fields ----------------
def update_times():
    def worker():
        try:
            sys_time_var.set(subprocess.getoutput("date '+%d.%m.%Y %H:%M:%S'"))
        except Exception as e:
            sys_time_var.set("Err")
            log(f"⚠️ Sys time read error: {e}")

        try:
            rtc_time_var.set(subprocess.getoutput("sudo hwclock --show -f /dev/rtc"))
        except Exception as e:
            rtc_time_var.set("Err")
            log(f"⚠️ RTC time read error: {e}")

    threading.Thread(target=worker).start()
    root.after(1000, update_times)

# ---------------- GPIO Button ----------------
tk.Button(left_frame, text="Show GPIOs", width=18, command=lambda: show_gpio_frame()).pack(anchor='w', pady=(10,0))

# ---------------- GPIO frame GUI ----------------
def show_gpio_frame():
    main_frame.pack_forget()
    gpio_frame_panel.pack(fill='both', expand=True)
    for widget in gpio_frame_panel.winfo_children():
        widget.destroy()
    left_gpio = tk.Frame(gpio_frame_panel)
    left_gpio.pack(side=tk.LEFT, padx=5, pady=5, anchor='n')
    tk.Label(left_gpio, text="GPIO Control Panel", font=("Arial", 12)).pack(anchor='w', pady=2)
    for pin in GPIO_PINS:
        frame = tk.Frame(left_gpio)
        frame.pack(anchor='w', pady=2)
        tk.Label(frame, text=f"GPIO {pin}", width=10).pack(side=tk.LEFT)
        tk.Button(frame, text="HIGH", command=lambda p=pin: set_pin(p, "1")).pack(side=tk.LEFT, padx=2)
        tk.Button(frame, text="LOW", command=lambda p=pin: set_pin(p, "0")).pack(side=tk.LEFT, padx=2)
        tk.Button(frame, text="Read", command=lambda p=pin: log(f"Pin {p} value is {read_pin(p)}")).pack(side=tk.LEFT, padx=2)
    info_window.pack_forget()
    info_window.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
    tk.Button(left_gpio, text="Back", width=18, command=show_main_frame).pack(anchor='w', pady=5)

def show_main_frame():
    gpio_frame_panel.pack_forget()
    main_frame.pack(fill='both', expand=True)

# ---------------- Start updates ----------------
update_temps()
update_times()

# ---------------- Start GUI ----------------
root.mainloop()
