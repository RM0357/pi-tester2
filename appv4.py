import tkinter as tk
from tkinter import ttk, scrolledtext
import subprocess
import threading
import time
import datetime
import os
import sys
import urllib.request
import json

# Try to import RPi.GPIO (provided by your environment or our local mock)
try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    # Laptop path or missing library: use local mock
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))
    import RPi.GPIO as GPIO
    IS_PI = False
else:
    IS_PI = True

# Try to import smbus for real temperature sensors
try:
    import smbus
    HAS_SMBUS = True
except ImportError:
    HAS_SMBUS = False

import readTemps

# Constants
MODEM_SCRIPT = "connection-manager.py"
DOWNLOAD_SCRIPT = "download.py"

class ControlPanelV4:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Raspberry Pi Control Panel v4")
        self.root.geometry("800x480")
        self.root.resizable(False, False)
        self.root.configure(bg='#f0f0f0')

        # Variables
        self.temp_pi = tk.StringVar(value="--")
        self.temp_smps = tk.StringVar(value="--")
        self.temp_ambient = tk.StringVar(value="--")
        self.sys_time = tk.StringVar(value="--")
        self.rtc_time = tk.StringVar(value="--")
        self.nfc_id = tk.StringVar(value="NO CARD")
        self.beeper_state = tk.StringVar(value="off")
        self.pwr1 = tk.BooleanVar(value=True)
        self.pwr2 = tk.BooleanVar(value=True)
        self.modem_status = tk.StringVar(value="checking...")
        self.wlan_ssid = tk.StringVar(value="disconnected")
        self.m2_software = tk.StringVar(value="Checking SW...")
        self.m2_imei = tk.StringVar(value="IMEI: ----")
        
        self._beep_proc = None

        # Styles
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TFrame', background='#f0f0f0')
        self.style.configure('TLabel', background='#f0f0f0', font=('Arial', 10))
        self.style.configure('Header.TLabel', font=('Arial', 11, 'bold'))
        self.style.configure('Value.TLabel', font=('Courier', 12, 'bold'), foreground='#0099ff')
        self.style.configure('Clock.TLabel', font=('Courier', 14, 'bold'), foreground='#0099ff')
        self.style.configure('Green.TButton', font=('Arial', 10, 'bold'), foreground='green')
        self.style.configure('Big.TButton', font=('Arial', 12, 'bold'), padding=5)

        self.setup_ui()
        self.start_threads()
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        self.main_container = ttk.Frame(self.root, padding=5)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # --- TOP ROW: Temps & NFC ---
        top_row = ttk.Frame(self.main_container)
        top_row.pack(fill=tk.X, pady=2)

        temp_frame = ttk.Frame(top_row)
        temp_frame.pack(side=tk.LEFT, padx=5)
        for label, var in [("Pi:", self.temp_pi), ("SMPS:", self.temp_smps), ("Amb:", self.temp_ambient)]:
            ttk.Label(temp_frame, text=label, font=('Arial', 9)).pack(side=tk.LEFT, padx=(5,2))
            ttk.Label(temp_frame, textvariable=var, style='Value.TLabel').pack(side=tk.LEFT, padx=(0,5))

        nfc_box = ttk.LabelFrame(top_row, text=" NFC ID ", padding=2)
        nfc_box.pack(side=tk.RIGHT, padx=5)
        ttk.Label(nfc_box, textvariable=self.nfc_id, style='Value.TLabel', font=('Courier', 11, 'bold')).pack(padx=8)

        # --- TIME SECTION (V4 Fixed Logic) ---
        time_frame = ttk.LabelFrame(self.main_container, text=" Time Management (RTC Fixed) ", padding=3)
        time_frame.pack(fill=tk.X, pady=2)

        # System Time Row
        sys_row = ttk.Frame(time_frame)
        sys_row.pack(fill=tk.X)
        ttk.Label(sys_row, text="SYS:", width=5).pack(side=tk.LEFT, padx=2)
        ttk.Label(sys_row, textvariable=self.sys_time, style='Clock.TLabel', width=19).pack(side=tk.LEFT)
        ttk.Button(sys_row, text="Preset", width=7, command=self.preset_sys_time).pack(side=tk.LEFT, padx=2)
        ttk.Button(sys_row, text="Sys->RTC", width=9, command=self.sys_to_rtc).pack(side=tk.LEFT, padx=2)
        ttk.Button(sys_row, text="SysPrefix", style='Green.TButton', width=10, command=self.sync_sys_prefix).pack(side=tk.LEFT, padx=2)

        # RTC Time Row
        rtc_row = ttk.Frame(time_frame)
        rtc_row.pack(fill=tk.X, pady=(1,0))
        ttk.Label(rtc_row, text="RTC:", width=5).pack(side=tk.LEFT, padx=2)
        ttk.Label(rtc_row, textvariable=self.rtc_time, style='Clock.TLabel', width=19).pack(side=tk.LEFT)
        ttk.Button(rtc_row, text="Preset", width=7, command=self.preset_rtc_time).pack(side=tk.LEFT, padx=2)
        ttk.Button(rtc_row, text="Read", width=7, command=self.read_rtc_manual).pack(side=tk.LEFT, padx=2)
        ttk.Button(rtc_row, text="RTC->Sys", width=9, command=self.rtc_to_sys).pack(side=tk.LEFT, padx=2)

        # Manual Set Row
        man_row = ttk.Frame(time_frame)
        man_row.pack(fill=tk.X, pady=2)
        ttk.Label(man_row, text="Manual Set:").pack(side=tk.LEFT, padx=2)
        self.time_entry = ttk.Entry(man_row, width=25)
        self.time_entry.insert(0, "2025-12-24 13:45:30")
        self.time_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(man_row, text="Set RTC", command=lambda: self.set_rtc_manual(self.time_entry.get())).pack(side=tk.LEFT)

        # Control Row (Beeper, PWR, Modem Status)
        ctrl_frame = ttk.Frame(self.main_container)
        ctrl_frame.pack(fill=tk.X, pady=5)
        
        # Beeper
        beep_f = ttk.Frame(ctrl_frame)
        beep_f.pack(side=tk.LEFT, padx=5)
        ttk.Label(beep_f, text="Beeper").pack()
        ttk.Button(beep_f, textvariable=self.beeper_state, command=self.toggle_beeper, width=8).pack()

        # PWR Outs
        for txt, var, cmd in [("PWR out 1", self.pwr1, self.toggle_pwr1), ("PWR out 2", self.pwr2, self.toggle_pwr2)]:
            f = ttk.Frame(ctrl_frame)
            f.pack(side=tk.LEFT, padx=5)
            ttk.Label(f, text=txt).pack()
            ttk.Button(f, text="on/off", command=cmd, width=10).pack()

        # Modem Detected
        mod_f = ttk.Frame(ctrl_frame)
        mod_f.pack(side=tk.RIGHT, padx=5)
        ttk.Label(mod_f, text="M.2 Modem").pack()
        ttk.Label(mod_f, textvariable=self.modem_status, style='Value.TLabel').pack()

        # Large Buttons Row
        btn_frame = ttk.Frame(self.main_container)
        btn_frame.pack(fill=tk.X, pady=5)
        
        btns = [
            ("Test M.2 wiring", lambda: self.run_modem_cmd(["--human", "--electrical"])),
            ("Test LTE connection", lambda: self.run_modem_cmd(["--human"])),
            ("Test LTE download", lambda: self.run_cmd(["python3", DOWNLOAD_SCRIPT]))
        ]
        for txt, cmd in btns:
            ttk.Button(btn_frame, text=txt, command=cmd, style='Big.TButton').pack(side=tk.LEFT, expand=True, fill=tk.X, padx=2)

        # WLAN Row
        wlan_frame = ttk.Frame(self.main_container)
        wlan_frame.pack(fill=tk.X, pady=5)
        
        f1 = ttk.Frame(wlan_frame)
        f1.pack(side=tk.LEFT, padx=2)
        ttk.Button(f1, text="Connect WLAN", command=self.open_keyboard).pack()

        f2 = ttk.Frame(wlan_frame, relief="sunken", padding=2)
        f2.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)
        ttk.Label(f2, textvariable=self.wlan_ssid, style='Value.TLabel').pack()

        f3 = ttk.Frame(wlan_frame)
        f3.pack(side=tk.LEFT, padx=2)
        ttk.Button(f3, text="Delete & Disconnect All", command=self.cancel_wlan).pack()

        # Footer Row (IMEI, Software, Advanced)
        footer_frame = ttk.Frame(self.main_container)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        
        sw_f = ttk.Frame(footer_frame)
        sw_f.pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Label(sw_f, textvariable=self.m2_software, style='Value.TLabel').pack(anchor="w")
        ttk.Label(sw_f, textvariable=self.m2_imei, font=('Arial', 9)).pack(anchor="w")

        ttk.Button(footer_frame, text="Flash M.2", width=12, command=self.flash_modem).pack(side=tk.LEFT, padx=2)
        ttk.Button(footer_frame, text="Logs", width=8, command=self.toggle_logs).pack(side=tk.LEFT, padx=2)
        ttk.Button(footer_frame, text="Advanced Menu", width=16, command=self.show_advanced).pack(side=tk.LEFT, padx=2)

        # Log Window (Hidden)
        self.error_frame = ttk.Frame(self.root)
        self.error_text = scrolledtext.ScrolledText(self.error_frame, height=8, font=("Courier", 10), bg="#222", fg="#eee")
        self.error_text.pack(fill=tk.BOTH, expand=True)
        
        # Advanced View (Hidden)
        self.setup_advanced_ui()
        self.poll_gpios()

    def setup_advanced_ui(self):
        self.adv_frame = ttk.Frame(self.root)
        ttk.Button(self.adv_frame, text="← BACK TO DASHBOARD", command=self.show_main, style='Big.TButton').pack(fill=tk.X, pady=5)
        
        nb = ttk.Notebook(self.adv_frame)
        nb.pack(fill=tk.BOTH, expand=True)

        self.gpio_elements = {}
        for title, pin_range in [("PINS 2-14", range(2, 15)), ("PINS 15-27", range(15, 28))]:
            tab = ttk.Frame(nb, padding=5)
            nb.add(tab, text=title)
            for i, pin in enumerate(pin_range):
                r, c = divmod(i, 2)
                f = ttk.LabelFrame(tab, text=f" GPIO {pin} ")
                f.grid(row=r, column=c, padx=3, pady=1, sticky="ew")
                tab.columnconfigure(c, weight=1)

                led = tk.Canvas(f, width=15, height=15, highlightthickness=0)
                led.pack(side=tk.LEFT, padx=5)
                circ = led.create_oval(2, 2, 13, 13, fill="gray")

                mode_lbl = ttk.Label(f, text="???", width=4)
                mode_lbl.pack(side=tk.LEFT, padx=2)

                btn_c = ttk.Frame(f)
                btn_c.pack(side=tk.RIGHT, padx=2)
                ttk.Button(btn_c, text="IN", width=3, command=lambda p=pin: self.set_gpio_mode(p, "IN")).pack(side=tk.LEFT, padx=1)
                ttk.Button(btn_c, text="OUT", width=4, command=lambda p=pin: self.set_gpio_mode(p, "OUT")).pack(side=tk.LEFT, padx=1)
                ttk.Button(btn_c, text="ON", width=3, command=lambda p=pin: self.set_gpio_level(p, 1)).pack(side=tk.LEFT, padx=1)
                ttk.Button(btn_c, text="OFF", width=4, command=lambda p=pin: self.set_gpio_level(p, 0)).pack(side=tk.LEFT, padx=1)

                self.gpio_elements[pin] = {"led": led, "circ": circ, "mode": mode_lbl}

    # Commands and Logic
    def log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.error_text.configure(state='normal')
        self.error_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.error_text.see(tk.END)
        self.error_text.configure(state='disabled')

    def run(self, cmd: str):
        """Run shell command like in app.py"""
        self.log(f"> {cmd}")
        try:
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=15
            )
            if result.stdout.strip():
                self.log(result.stdout.strip())
            if result.returncode != 0:
                self.log(f"FAILED (rc={result.returncode}): {result.stderr.strip()}")
            else:
                self.log("Success")
        except Exception as e:
            self.log(f"EXCEPTION: {e}")

    def run_cmd(self, cmd_list):
        """Helper for list-based commands (Modem/Download)"""
        try:
            p = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                if line.strip(): self.log(f"CMD: {line.strip()}")
            p.wait()
        except Exception as e:
            self.log(f"ERR: {e}")

    # Time Ops (Directly from app.py)
    def update_time_display(self):
        try:
            sys_time = subprocess.check_output(["date", "+%d.%m.%Y %H:%M:%S"], text=True).strip()
            self.sys_time.set(sys_time)
        except:
            self.sys_time.set("Err")

        try:
            rtc_time = subprocess.check_output(["sudo", "hwclock", "--show", "-f", "/dev/rtc"], text=True).strip()
            self.rtc_time.set(rtc_time)
        except:
            self.rtc_time.set("Err")
        self.root.after(1000, self.update_time_display)

    def refresh_rtc_display(self):
        """Exactly from app.py"""
        try:
            rtc_time = subprocess.check_output(
                ["sudo", "hwclock", "--show", "-f", "/dev/rtc"], text=True
            ).strip()
            self.rtc_time.set(rtc_time)
            self.log(f"RTC now: {rtc_time}")
        except Exception as e:
            self.log(f"RTC read failed: {e}")
            self.rtc_time.set("Err")

    def read_rtc_manual(self):
        self.refresh_rtc_display()

    def preset_sys_time(self):
        self.run("sudo date -s '2011-01-01 11:11:11'")

    def preset_rtc_time(self):
        date_str = "2025-12-24 13:45:30"
        self.run(f'sudo hwclock --set --date="{date_str}" -f /dev/rtc')
        self.refresh_rtc_display()

    def set_rtc_manual(self, dstr):
        if not dstr.strip():
            self.log("Error: Empty date/time")
            return
        self.run(f'sudo hwclock --set --date="{dstr.strip()}" -f /dev/rtc')
        self.refresh_rtc_display()

    def sys_to_rtc(self):
        self.run("sudo hwclock --systohc -f /dev/rtc")
        self.refresh_rtc_display()

    def rtc_to_sys(self):
        self.run("sudo hwclock --hctosys -f /dev/rtc")
        self.refresh_rtc_display()

    def sync_sys_prefix(self):
        self.log("ACTION: Internet Sync (SysPrefix)")
        def _task():
            try:
                with urllib.request.urlopen("http://worldtimeapi.org/api/timezone/Etc/UTC", timeout=10) as resp:
                    data = json.load(resp)
                dt = data["utc_datetime"].split(".")[0].replace("T", " ")
                p = subprocess.run(["sudo", "date", "-s", dt], capture_output=True, text=True)
                if p.returncode == 0:
                    subprocess.run(["sudo", "hwclock", "--systohc", "-f", "/dev/rtc"])
                    self.log(f"SUCCESS: Synced from Web -> {dt}")
                else: self.log(f"OS ERR: {p.stderr}")
            except Exception as e: self.log(f"NET ERR: {e}")
        threading.Thread(target=_task, daemon=True).start()

    # Hardware Ops
    def toggle_beeper(self):
        states = ["off", "400Hz", "1kHz"]
        idx = (states.index(self.beeper_state.get()) + 1) % len(states)
        new = states[idx]
        self.beeper_state.set(new)
        self.log(f"ACTION: Beeper set to {new}")
        
        # 1. Stop existing noise
        if hasattr(self, '_pi_pwm') and self._pi_pwm:
            try: self._pi_pwm.stop()
            except: pass
            self._pi_pwm = None

        if hasattr(self, '_beep_proc') and self._beep_proc:
            try: self._beep_proc.kill(); self._beep_proc.wait(0.1)
            except: pass
            self._beep_proc = None
        
        # Kill any lingering speaker-test processes
        if not IS_PI:
            subprocess.run(["killall", "-q", "speaker-test"])

        # 2. Start new noise
        if new != "off":
            freq = 400 if new == "400Hz" else 1000
            if IS_PI:
                try:
                    self.log(f"SYSTEM: Using GPIO 13 PWM for {freq}Hz")
                    GPIO.setup(13, GPIO.OUT)
                    self._pi_pwm = GPIO.PWM(13, freq)
                    self._pi_pwm.start(50) # 50% duty cycle for buzzer
                except Exception as e:
                    self.log(f"GPIO ERR: Pin 13 beeper failed: {e}")
            else:
                try:
                    self.log(f"SYSTEM: Using Audio Speaker for {freq}Hz")
                    self._beep_proc = subprocess.Popen(
                        ["speaker-test", "-t", "sine", "-f", str(freq), "-c", "2"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                except Exception as e:
                    self.log(f"SIM ERR: Audio beep failed: {e}")

    def toggle_pwr1(self):
        self.pwr1.set(not self.pwr1.get()); s = GPIO.HIGH if self.pwr1.get() else GPIO.LOW
        GPIO.setup(26, GPIO.OUT); GPIO.output(26, s)

    def toggle_pwr2(self):
        self.pwr2.set(not self.pwr2.get()); s = GPIO.HIGH if self.pwr2.get() else GPIO.LOW
        GPIO.setup(22, GPIO.OUT); GPIO.output(22, s)

    def set_gpio_mode(self, pin, mode):
        m = GPIO.IN if mode == "IN" else GPIO.OUT
        GPIO.setup(pin, m); self.gpio_elements[pin]["mode"].config(text=mode)

    def set_gpio_level(self, pin, lvl):
        try: GPIO.output(pin, lvl)
        except: pass

    def poll_gpios(self):
        if self.adv_frame.winfo_viewable():
            for pin, el in self.gpio_elements.items():
                try:
                    state = GPIO.input(pin)
                    el["led"].itemconfig(el["circ"], fill="#00ff00" if state else "#ff0000")
                except: pass
        self.root.after(500, self.poll_gpios)

    def start_threads(self):
        # Temps Loop
        def _temp():
            while True:
                if IS_PI:
                    try:
                        t = readTemps.read_all_temps()
                        self.temp_pi.set(f"{t[0]:.1f}" if t[0] else "Err")
                        self.temp_smps.set(f"{t[1]:.1f}" if t[1] else "Err")
                        self.temp_ambient.set(f"{t[2]:.1f}" if t[2] else "Err")
                    except: pass
                else:
                    self.temp_pi.set("35.2"); self.temp_smps.set("42.0"); self.temp_ambient.set("22.5")
                time.sleep(2)
        threading.Thread(target=_temp, daemon=True).start()

        # Update display clock
        self.update_time_display()

    # Nav
    def toggle_logs(self):
        if self.error_frame.winfo_viewable(): self.error_frame.pack_forget()
        else: self.error_frame.pack(fill=tk.BOTH, expand=True)

    def show_advanced(self):
        self.main_container.pack_forget()
        self.adv_frame.pack(fill=tk.BOTH, expand=True)

    def show_main(self):
        self.adv_frame.pack_forget()
        self.main_container.pack(fill=tk.BOTH, expand=True)

    def open_keyboard(self): 
        # VirtualKeyboard dummy or implementation
        self.log("Opening Virtual Keyboard...")

    def cancel_wlan(self): self.wlan_ssid.set("disconnected")

    def flash_modem(self): self.log("Flashing Modem Firmware...")

    def run_modem_cmd(self, args):
        cmd = ["python3", MODEM_SCRIPT] + args
        threading.Thread(target=self.run_cmd, args=(cmd,), daemon=True).start()

    def on_closing(self):
        if hasattr(self, '_pi_pwm') and self._pi_pwm:
            try: self._pi_pwm.stop()
            except: pass
        if hasattr(self, '_beep_proc') and self._beep_proc:
            try: self._beep_proc.kill()
            except: pass
        GPIO.cleanup()
        self.root.destroy()

    def run(self): self.root.mainloop()

if __name__ == "__main__":
    ControlPanelV4().run()
