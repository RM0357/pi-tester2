# app.py
import tkinter as tk
from tkinter import scrolledtext
import os
import atexit
import subprocess
import urllib.request
import json
import readTemps

# ----------------------------------------------------------------------
# --------------------------  Helper functions  -------------------------
# ----------------------------------------------------------------------
def log(msg: str):
    """Append a line to the scrolling info window."""
    info_window.configure(state="normal")
    info_window.insert(tk.END, msg + "\n")
    info_window.see(tk.END)
    info_window.configure(state="disabled")


def run(cmd: str):
    """Execute a shell command and log real output / errors."""
    log(f"> {cmd}")
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=15
    )
    if result.stdout.strip():
        log(result.stdout.strip())
    if result.returncode != 0:
        log(f"FAILED (rc={result.returncode}): {result.stderr.strip()}")
    else:
        log("Success")


# ----------------------------------------------------------------------
# --------------------------  GPIO handling  ---------------------------
# ----------------------------------------------------------------------
GPIO_PINS = [524, 525, 526]

# Export & set direction
for pin in GPIO_PINS:
    gpio_path = f"/sys/class/gpio/gpio{pin}"
    if not os.path.exists(gpio_path):
        os.system(f"sudo sh -c 'echo {pin} > /sys/class/gpio/export'")
    os.system(f"sudo sh -c 'echo out > /sys/class/gpio/gpio{pin}/direction'")


def read_pin(pin):
    try:
        with open(f"/sys/class/gpio/gpio{pin}/value", "r") as f:
            return f.read().strip()
    except Exception:
        return "err"


def set_pin(pin, value):
    os.system(f"sudo sh -c 'echo {value} > /sys/class/gpio/gpio{pin}/value'")
    status = "HIGH" if value == "1" else "LOW"
    log(f"Pin {pin} -> {status}")


def cleanup_gpio():
    for pin in GPIO_PINS:
        os.system(f"sudo sh -c 'echo {pin} > /sys/class/gpio/unexport'")


atexit.register(cleanup_gpio)

# ----------------------------------------------------------------------
# --------------------------  Tkinter GUI  -----------------------------
# ----------------------------------------------------------------------
root = tk.Tk()
root.title("Raspberry Pi Dashboard")
root.geometry("800x480")
root.resizable(False, False)

# ---- warn if not root -------------------------------------------------
if os.getuid() != 0:
    log("WARNING: NOT running as root! RTC / GPIO commands will fail.")
    log("Start the script with: sudo python3 app.py")

# ---- frames -----------------------------------------------------------
main_frame = tk.Frame(root)
gpio_frame_panel = tk.Frame(root)
main_frame.pack(fill="both", expand=True)

left_frame = tk.Frame(main_frame)
left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
right_frame = tk.Frame(main_frame)
right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

# ---- temperature display -----------------------------------------------
temp_labels = ["TempPi", "Temp SMPS", "Temp Ambient"]
temp_vars = [tk.StringVar(value="--") for _ in range(3)]

temp_container = tk.Frame(left_frame)
temp_container.pack(anchor="w", pady=5)

tk.Label(temp_container, text="Temps:", font=("Arial", 10)).pack(side=tk.LEFT)
for i, var in enumerate(temp_vars):
    tk.Label(temp_container, text=f"{temp_labels[i]}: ", font=("Arial", 10)).pack(
        side=tk.LEFT
    )
    tk.Label(
        temp_container, textvariable=var, font=("Arial", 10), width=6
    ).pack(side=tk.LEFT, padx=5)


def update_temps():
    temps = readTemps.read_all_temps()
    for i, t in enumerate(temps):
        temp_vars[i].set(f"{t:.2f}" if t is not None else "Err")
    root.after(500, update_temps)


# ---- scrolling log window ---------------------------------------------
info_window = scrolledtext.ScrolledText(
    right_frame, width=40, height=25, state="disabled"
)
info_window.pack(fill=tk.BOTH, expand=True)

# ---- time display / RTC controls ---------------------------------------
time_frame = tk.Frame(left_frame)
time_frame.pack(anchor="w", pady=(10, 5))

# System time
sys_time_var = tk.StringVar()
tk.Label(time_frame, text="SysTime:", font=("Arial", 10)).grid(
    row=0, column=0, sticky="w"
)
tk.Entry(time_frame, textvariable=sys_time_var, width=20, font=("Arial", 10)).grid(
    row=0, column=1, padx=2
)

# RTC time
rtc_time_var = tk.StringVar()
tk.Label(time_frame, text="RTC:", font=("Arial", 10)).grid(
    row=1, column=0, sticky="w"
)
tk.Entry(time_frame, textvariable=rtc_time_var, width=20, font=("Arial", 10)).grid(
    row=1, column=1, padx=2
)

# Buttons column
btn_frame = tk.Frame(time_frame)
btn_frame.grid(row=0, column=2, rowspan=2, padx=(10, 0))

# ---- RTC buttons -------------------------------------------------------
tk.Button(
    btn_frame,
    text="Sys->RTC",
    width=10,
    command=lambda: run("sudo hwclock --systohc -f /dev/rtc"),
).pack(pady=2)

tk.Button(
    btn_frame,
    text="RTC->Sys",
    width=10,
    command=lambda: run("sudo hwclock --hctosys -f /dev/rtc"),
).pack(pady=2)

tk.Button(
    btn_frame,
    text="[Preset] RTC",
    width=10,
    command=lambda: [
        run('sudo hwclock --set --date="2025-12-24 13:45:30" -f /dev/rtc'),
        run('sudo hwclock --show -f /dev/rtc')
    ],
).pack(pady=2)

# ---- Sync from internet ------------------------------------------------
def sync_sys_prefix():
    try:
        with urllib.request.urlopen(
            "http://worldtimeapi.org/api/timezone/Etc/UTC", timeout=10
        ) as resp:
            data = json.load(resp)
        dt = data["utc_datetime"].split(".")[0].replace("T", " ")
        run(f"sudo date -s '{dt}'")
        run("sudo hwclock --systohc -f /dev/rtc")
        log(f"Internet sync -> {dt}")
    except Exception as e:
        log(f"Internet sync error: {e}")


tk.Button(btn_frame, text="SysPrefix", width=10, command=sync_sys_prefix).pack(pady=2)

# ---- Manual RTC set ----------------------------------------------------
manual_frame = tk.Frame(left_frame)
manual_frame.pack(anchor="w", pady=5)
tk.Label(
    manual_frame,
    text="Set RTC (YYYY-MM-DD HH:MM:SS):",
    font=("Arial", 10),
).pack(side=tk.LEFT)
rtc_entry = tk.Entry(manual_frame, width=20)
rtc_entry.pack(side=tk.LEFT, padx=2)
tk.Button(
    manual_frame,
    text="Set",
    command=lambda: [
        run(
            f'sudo hwclock --set --date="{rtc_entry.get().strip()}" -f /dev/rtc'
        ),
        run("sudo hwclock --systohc -f /dev/rtc"),
        run("sudo hwclock --show -f /dev/rtc"),
    ],
).pack(side=tk.LEFT, padx=2)

# ---- Periodic time update -----------------------------------------------
def update_times():
    try:
        sys_time = subprocess.check_output(
            ["date", "+%d.%m.%Y %H:%M:%S"], text=True
        ).strip()
        sys_time_var.set(sys_time)
    except Exception:
        sys_time_var.set("Err")

    try:
        rtc_time = subprocess.check_output(
            ["sudo", "hwclock", "--show", "-f", "/dev/rtc"], text=True
        ).strip()
        rtc_time_var.set(rtc_time)
    except Exception as e:
        log(f"RTC read error: {e}")
        rtc_time_var.set("Err")

    root.after(1000, update_times)


# ---- GPIO control panel ------------------------------------------------
tk.Button(
    left_frame,
    text="Show GPIOs",
    width=18,
    command=lambda: show_gpio_frame(),
).pack(anchor="w", pady=(10, 0))


def show_gpio_frame():
    main_frame.pack_forget()
    gpio_frame_panel.pack(fill="both", expand=True)

    # clear previous contents
    for w in gpio_frame_panel.winfo_children():
        w.destroy()

    left_gpio = tk.Frame(gpio_frame_panel)
    left_gpio.pack(side=tk.LEFT, padx=5, pady=5, anchor="n")

    tk.Label(left_gpio, text="GPIO Control Panel", font=("Arial", 12)).pack(
        anchor="w", pady=2
    )

    for pin in GPIO_PINS:
        f = tk.Frame(left_gpio)
        f.pack(anchor="w", pady=2)
        tk.Label(f, text=f"GPIO {pin}", width=10).pack(side=tk.LEFT)
        tk.Button(
            f, text="HIGH", command=lambda p=pin: set_pin(p, "1")
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            f, text="LOW", command=lambda p=pin: set_pin(p, "0")
        ).pack(side=tk.LEFT, padx=2)
        tk.Button(
            f,
            text="Read",
            command=lambda p=pin: log(f"Pin {p} = {read_pin(p)}"),
        ).pack(side=tk.LEFT, padx=2)

    # re-pack the log window on the right side of the GPIO panel
    info_window.pack_forget()
    info_window.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

    tk.Button(
        left_gpio, text="Back", width=18, command=show_main_frame
    ).pack(anchor="w", pady=5)


def show_main_frame():
    gpio_frame_panel.pack_forget()
    main_frame.pack(fill="both", expand=True)


# ----------------------------------------------------------------------
# --------------------------  Start loops  -----------------------------
# ----------------------------------------------------------------------
update_temps()
update_times()

root.mainloop()
