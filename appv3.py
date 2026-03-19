import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import datetime
import os
import threading
import time

# Detect if we are on a Pi or Laptop
IS_PI = os.path.exists('/sys/bus/platform/drivers/raspberrypi-cpufreq')

if not IS_PI:
    # On Laptop: ALWAYS use local mock RPi.GPIO
    import sys
    # Ensure CWD is in sys.path so 'import RPi.GPIO' finds local folder
    if os.path.dirname(__file__) not in sys.path:
        sys.path.insert(0, os.path.dirname(__file__))
    import RPi.GPIO as GPIO
else:
    # On Pi: Use official system GPIO
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        # Fallback if library missing
        import RPi.GPIO as GPIO

# Mock SMBus for non-Pi systems
try:
    import smbus
except ImportError:
    class MockSMBus:
        def __init__(self, bus): pass
        def read_i2c_block_data(self, addr, reg, len): 
            import random
            return [random.randint(20, 30), random.randint(0, 255)]
    smbus = type('smbus', (), {'SMBus': MockSMBus})

# === CONFIG ===
MODEM_SCRIPT = os.path.join(os.path.dirname(__file__), "connection-manager.py")
DOWNLOAD_SCRIPT = os.path.join(os.path.dirname(__file__), "download.py")

class VirtualKeyboard(tk.Toplevel):
    def __init__(self, parent, target_var):
        super().__init__(parent)
        self.title("Keyboard")
        self.target_var = target_var
        self.geometry("600x350")
        self.configure(bg="#333333")
        self.attributes('-topmost', True)
        self.setup_ui()

    def setup_ui(self):
        keys = [
            ['1','2','3','4','5','6','7','8','9','0'],
            ['Q','W','E','R','T','Y','U','I','O','P'],
            ['A','S','D','F','G','H','J','K','L'],
            ['Z','X','C','V','B','N','M', '.', '_', '-'],
            ['BACK', 'SPACE', 'ENTER']
        ]
        
        for r, row in enumerate(keys):
            frame = tk.Frame(self, bg="#333333")
            frame.pack(pady=2)
            for key in row:
                btn = tk.Button(frame, text=key, width=4, height=2, 
                                command=lambda k=key: self.on_key(k),
                                font=("Arial", 12, "bold"), bg="#555555", fg="white")
                if key in ['BACK', 'SPACE', 'ENTER']:
                    btn.configure(width=8)
                btn.pack(side=tk.LEFT, padx=2)

    def on_key(self, key):
        if key == 'BACK':
            self.target_var.set(self.target_var.get()[:-1])
        elif key == 'SPACE':
            self.target_var.set(self.target_var.get() + " ")
        elif key == 'ENTER':
            self.destroy()
        else:
            self.target_var.set(self.target_var.get() + key)

class ControlPanelV3:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("System Control Panel v3")
        self.root.geometry("800x480")
        self.root.configure(bg="#f0f0f0")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing) # Handle window close event

        # Global Styles
        self.style = ttk.Style()
        self.style.configure('TFrame', background='#f0f0f0')
        self.style.configure('TLabel', background='#f0f0f0', font=('Arial', 10))
        self.style.configure('Header.TLabel', font=('Arial', 11, 'bold'))
        self.style.configure('Value.TLabel', font=('Courier', 12, 'bold'), foreground='#0099ff')
        self.style.configure('Clock.TLabel', font=('Courier', 14, 'bold'), foreground='#0099ff')
        self.style.configure('TLabel', font=('Arial', 10))
        
        # Power Buttons
        self.style.configure('PwrOn.TButton', foreground='green', font=('Arial', 9, 'bold'))
        self.style.configure('PwrOff.TButton', foreground='red', font=('Arial', 9, 'bold'))
        self.style.configure('Mode.TButton', foreground='blue', font=('Arial', 9))
        self.style.configure('Green.TButton', font=('Arial', 10, 'bold'), foreground='green')
        self.style.configure('Big.TButton', font=('Arial', 12, 'bold'), padding=5)

        # Variables
        self.temp_pi = tk.StringVar(value="---.--°C")
        self.temp_smps = tk.StringVar(value="---.--°C")
        self.temp_ambient = tk.StringVar(value="---.--°C")
        self.sys_time = tk.StringVar(value="DD.MM.YYYY HH:MM:SS")
        self.rtc_time = tk.StringVar(value="DD.MM.YYYY HH:MM:SS")
        self.nfc_id = tk.StringVar(value="00000000")
        self.beeper_state = tk.StringVar(value="off")
        self.m2_3v3 = tk.BooleanVar(value=True)
        self.modem_status = tk.StringVar(value="not detected")
        self.m2_software = tk.StringVar(value="actual M.2 Software")
        self.m2_imei = tk.StringVar(value="IMEI: unknown")
        self.wlan_ssid = tk.StringVar(value="actual SSID")
        self.pwr1 = tk.BooleanVar(value=False)
        self.pwr2 = tk.BooleanVar(value=False)

        GPIO.setmode(GPIO.BCM)
        self.setup_gpio()
        self.setup_ui()
        
        # Start background threads
        self.update_loops()

    def setup_gpio(self):
        # GP26: 3V3 Switch (on=off, off=on)
        # GP22: PWR1 (high=low, open collecter)
        # GP23: PWR2
        for pin in [26, 22, 23, 12]:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.HIGH) # Default off
        
        # Beeper process tracker
        self._beep_proc = None

        # Setup Advanced GPIOs as inputs with interrupts
        for pin in range(2, 28):
            if pin not in [26, 22, 23, 12, 13]:
                try: 
                    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                    GPIO.add_event_detect(pin, GPIO.BOTH, callback=self.on_gpio_interrupt)
                except: pass

    def setup_ui(self):
        self.main_container = ttk.Frame(self.root, padding=5)
        self.main_container.pack(fill=tk.BOTH, expand=True)

        # --- TOP ROW: Temps & NFC (Super Compact) ---
        top_row = ttk.Frame(self.main_container)
        top_row.pack(fill=tk.X, pady=2)

        # Temps in one slim row
        temp_frame = ttk.Frame(top_row)
        temp_frame.pack(side=tk.LEFT, padx=5)
        for label, var in [("Pi:", self.temp_pi), ("SMPS:", self.temp_smps), ("Amb:", self.temp_ambient)]:
            ttk.Label(temp_frame, text=label, font=('Arial', 9)).pack(side=tk.LEFT, padx=(5,2))
            ttk.Label(temp_frame, textvariable=var, style='Value.TLabel').pack(side=tk.LEFT, padx=(0,5))

        # NFC ID on the right
        nfc_box = ttk.LabelFrame(top_row, text=" NFC ID ", padding=2)
        nfc_box.pack(side=tk.RIGHT, padx=5)
        ttk.Label(nfc_box, textvariable=self.nfc_id, style='Value.TLabel', font=('Courier', 11, 'bold')).pack(padx=8)

        # --- TIME SECTION (Slimmed down) ---
        time_frame = ttk.LabelFrame(self.main_container, text=" Time Management ", padding=3)
        time_frame.pack(fill=tk.X, pady=2)

        # System Time Row
        sys_row = ttk.Frame(time_frame)
        sys_row.pack(fill=tk.X)
        ttk.Label(sys_row, text="SYS:", width=5).pack(side=tk.LEFT, padx=2)
        ttk.Label(sys_row, textvariable=self.sys_time, style='Clock.TLabel', width=19).pack(side=tk.LEFT)
        ttk.Button(sys_row, text="Preset", style='Green.TButton', width=7, command=self.preset_sys_time).pack(side=tk.LEFT, padx=2)
        ttk.Button(sys_row, text="Sys->RTC", style='Green.TButton', width=9, command=self.sys_to_rtc).pack(side=tk.LEFT, padx=2)

        # RTC Time Row
        rtc_row = ttk.Frame(time_frame)
        rtc_row.pack(fill=tk.X, pady=(1,0))
        ttk.Label(rtc_row, text="RTC:", width=5).pack(side=tk.LEFT, padx=2)
        ttk.Label(rtc_row, textvariable=self.rtc_time, style='Clock.TLabel', width=19).pack(side=tk.LEFT)
        ttk.Button(rtc_row, text="Preset", style='Green.TButton', width=7, command=self.preset_rtc_time).pack(side=tk.LEFT, padx=2)
        ttk.Button(rtc_row, text="Read", style='Green.TButton', width=7, command=self.read_rtc_manual).pack(side=tk.LEFT, padx=2)
        ttk.Button(rtc_row, text="RTC->Sys", style='Green.TButton', width=9, command=self.rtc_to_sys).pack(side=tk.LEFT, padx=2)

        # Control Row (Beeper, PWR, Modem Status)
        ctrl_frame = ttk.Frame(self.main_container)
        ctrl_frame.pack(fill=tk.X, pady=10)
        
        # Beeper
        beep_f = ttk.Frame(ctrl_frame)
        beep_f.pack(side=tk.LEFT, padx=5)
        ttk.Label(beep_f, text="Beeper").pack()
        self.beep_btn = ttk.Button(beep_f, textvariable=self.beeper_state, command=self.toggle_beeper, width=15)
        self.beep_btn.pack()

        # 3.3V Switch
        v33_f = ttk.Frame(ctrl_frame)
        v33_f.pack(side=tk.LEFT, padx=5)
        ttk.Label(v33_f, text="3,3V M.2").pack()
        ttk.Button(v33_f, text="on/off", command=self.toggle_v33, width=10).pack()

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
        ttk.Label(f1, text="connect WLAN").pack()
        ttk.Button(f1, text="connect WLAN", command=self.open_keyboard).pack()

        f2 = ttk.Frame(wlan_frame)
        f2.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)
        ttk.Label(f2, text="WLAN SSID").pack()
        ttk.Label(f2, textvariable=self.wlan_ssid, style='Value.TLabel', relief="sunken", padding=5).pack(fill=tk.X)

        f3 = ttk.Frame(wlan_frame)
        f3.pack(side=tk.LEFT, padx=2)
        ttk.Label(f3, text="cancel WLAN").pack()
        ttk.Button(f3, text="delete and disconnect all", command=self.cancel_wlan).pack()

        # Footer Row (IMEI, Software, Advanced)
        footer_frame = ttk.Frame(self.main_container)
        footer_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=5)
        
        sw_f = ttk.Frame(footer_frame)
        sw_f.pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Label(sw_f, text="actual M.2 Software").pack(anchor="w")
        ttk.Label(sw_f, textvariable=self.m2_software, style='Value.TLabel').pack(anchor="w")
        ttk.Label(sw_f, textvariable=self.m2_imei, font=('Arial', 9)).pack(anchor="w")

        ttk.Button(footer_frame, text="flash M.2", width=15, command=self.flash_modem).pack(side=tk.LEFT, padx=5)
        ttk.Button(footer_frame, text="Logs", width=10, command=self.toggle_logs).pack(side=tk.LEFT, padx=5)
        ttk.Button(footer_frame, text="Advanced Menu", width=20, command=self.show_advanced).pack(side=tk.LEFT, padx=5)

        # Error Log (Hidden by default)
        self.error_frame = ttk.Frame(self.root)
        self.error_text = scrolledtext.ScrolledText(self.error_frame, height=10, font=("Courier", 10), bg="#222", fg="#eee")
        self.error_text.pack(fill=tk.BOTH, expand=True)
        # Hidden by default
        
        # Advanced View (Hidden by default)
        self.setup_advanced_ui()
        # Start GPIO Polling for advanced view
        self.poll_gpios()

    def setup_advanced_ui(self):
        self.adv_frame = ttk.Frame(self.root)
        ttk.Button(self.adv_frame, text="← BACK TO DASHBOARD", command=self.show_main, style='Big.TButton').pack(fill=tk.X, pady=5)
        
        self.nb = ttk.Notebook(self.adv_frame)
        self.nb.pack(fill=tk.BOTH, expand=True)

        self.gpio_elements = {} # pin: {led, mode_lbl}
        for title, pin_range in [("PINS 2-14", range(2, 15)), ("PINS 15-27", range(15, 28))]:
            tab = ttk.Frame(self.nb, padding=5)
            self.nb.add(tab, text=title)
            
            # Grid layout for GPIOs
            for i, pin in enumerate(pin_range):
                r, c = divmod(i, 2)
                f = ttk.LabelFrame(tab, text=f" GPIO {pin} ")
                f.grid(row=r, column=c, padx=3, pady=1, sticky="ew")
                tab.columnconfigure(c, weight=1)

                # LED Status
                led = tk.Canvas(f, width=15, height=15, highlightthickness=0)
                led.pack(side=tk.LEFT, padx=5)
                led_circle = led.create_oval(2, 2, 13, 13, fill="gray")

                # Mode Label
                mode_lbl = ttk.Label(f, text="???", width=4)
                mode_lbl.pack(side=tk.LEFT, padx=2)

                # Control Buttons Row
                btn_cont = ttk.Frame(f)
                btn_cont.pack(side=tk.RIGHT, padx=2)

                ttk.Button(btn_cont, text="IN", width=3, command=lambda p=pin: self.set_gpio_mode(p, "IN")).pack(side=tk.LEFT, padx=1)
                ttk.Button(btn_cont, text="OUT", width=4, command=lambda p=pin: self.set_gpio_mode(p, "OUT")).pack(side=tk.LEFT, padx=1)
                ttk.Button(btn_cont, text="ON", width=3, command=lambda p=pin: self.set_gpio_level(p, 1)).pack(side=tk.LEFT, padx=1)
                ttk.Button(btn_cont, text="OFF", width=4, command=lambda p=pin: self.set_gpio_level(p, 0)).pack(side=tk.LEFT, padx=1)

                self.gpio_elements[pin] = {"led": led, "led_obj": led_circle, "mode": mode_lbl, "frame": f}
                # Initial setup
                self.set_gpio_mode(pin, "IN")

    def set_gpio_mode(self, pin, mode):
        try:
            m = GPIO.IN if mode == "IN" else GPIO.OUT
            GPIO.setup(pin, m)
            self.gpio_elements[pin]["mode"].config(text=mode)
            self.log(f"ACTION: GPIO {pin} set to {mode}")
        except Exception as e:
            self.log(f"GPIO ERROR: Pin {pin} mode change failed: {e}")

    def set_gpio_level(self, pin, level):
        try:
            GPIO.output(pin, level)
            self.log(f"ACTION: GPIO {pin} set to {'ON' if level else 'OFF'}")
        except Exception as e:
            self.log(f"GPIO ERROR: Pin {pin} output failed: {e}")

    def poll_gpios(self):
        # Update LEDs for all GPIOs based on current state
        if hasattr(self, 'adv_frame') and self.adv_frame.winfo_viewable():
            for pin, el in self.gpio_elements.items():
                try:
                    state = GPIO.input(pin)
                    color = "#00ff00" if state else "#ff0000" # Green for HIGH, Red for LOW
                    el["led"].itemconfig(el["led_obj"], fill=color)
                except: pass
        self.root.after(500, self.poll_gpios)

    def log(self, msg):
        def _ins():
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            self.error_text.configure(state='normal')
            self.error_text.insert(tk.END, f"[{ts}] {msg}\n")
            self.error_text.see(tk.END)
            # Truncate to 500 lines for performance
            if float(self.error_text.index('end-1c')) > 500:
                self.error_text.delete('1.0', '2.0')
            self.error_text.configure(state='disabled')
        self.root.after(0, _ins)

    def run_cmd(self, cmd):
        # Allow real commands (including sudo) to reach the system
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in p.stdout:
                if line.strip(): self.log(f"LOG: {line.strip()}")
            p.wait()
        except Exception as e:
            self.log(f"ERR: {e}")

    def run_modem_cmd(self, args):
        cmd = ["python3", MODEM_SCRIPT] + args
        threading.Thread(target=self.run_cmd, args=(cmd,), daemon=True).start()

    # Time Ops
    def update_time_display(self):
        self.sys_time.set(datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        # Automatic polling is disabled to prevent log spam, use manual Read button
        self.root.after(1000, self.update_time_display)

    def read_rtc_manual(self):
        self.log("ACTION: Read RTC Pressed")
        raw = self.run_cmd_silent(["hwclock", "-r"])
        if raw:
            # Clean up output for the UI
            clean_t = raw.split('.')[0]
            self.rtc_time.set(clean_t)
            self.log(f"SUCCESS: RTC Time is {clean_t}")
        else:
            self.log("ERROR: Hardware Clock not accessible (Check driver/permissions)")
            self.rtc_time.set("ERROR")

    def toggle_logs(self):
        if self.error_frame.winfo_viewable():
            self.error_frame.pack_forget()
        else:
            self.error_frame.pack(fill=tk.X, side=tk.BOTTOM)

    def run_cmd_silent(self, cmd):
        # Allow real commands (including sudo) to reach the system
        try: 
            return subprocess.check_output(cmd, text=True, timeout=2, 
                                        stderr=subprocess.STDOUT, 
                                        stdin=subprocess.DEVNULL).strip()
        except Exception as e:
            return None

    def preset_sys_time(self):
        self.log("ACTION: Preset System Time Pressed")
        p = subprocess.run(["sudo", "date", "-s", "2011-01-01 11:11:11"], capture_output=True, text=True)
        if p.returncode == 0:
            self.log("SUCCESS: System time set to 2011-01-01")
        else:
            self.log(f"ERROR: {p.stderr.strip()}")

    def preset_rtc_time(self):
        self.log("ACTION: Preset RTC Pressed")
        self.log("Syncing RTC from System...")
        p = subprocess.run(["sudo", "hwclock", "-w"], capture_output=True, text=True)
        if p.returncode == 0:
            self.log("SUCCESS: RTC Hardware Updated (-w)")
        else:
            self.log(f"ERROR: {p.stderr.strip()}")

    def sys_to_rtc(self): 
        self.log("ACTION: Sys -> RTC Pressed")
        p = subprocess.run(["sudo", "hwclock", "-w"], capture_output=True, text=True)
        if p.returncode == 0: self.log("SUCCESS: SYS -> RTC done")
        else: self.log(f"ERROR: {p.stderr.strip()}")
        
    def rtc_to_sys(self): 
        self.log("ACTION: RTC -> Sys Pressed")
        p = subprocess.run(["sudo", "hwclock", "-s"], capture_output=True, text=True)
        if p.returncode == 0: self.log("SUCCESS: RTC -> SYS done")
        else: self.log(f"ERROR: {p.stderr.strip()}")

    # Beeper
    def toggle_beeper(self):
        states = ["off", "400Hz", "1kHz"]
        idx = (states.index(self.beeper_state.get()) + 1) % len(states)
        new = states[idx]
        self.beeper_state.set(new)
        self.log(f"ACTION: Beeper set to {new}")
        
        # 1. Kill any current beep process IMMEDIATELY
        if hasattr(self, '_beep_proc') and self._beep_proc:
            try:
                self._beep_proc.kill() # Force kill
                self._beep_proc.wait(timeout=0.2) # Ensure it's dead
                self._beep_proc = None
            except: pass
        
        # 2. Global cleanup to prevent rogue processes
        subprocess.run(["killall", "-q", "speaker-test"])

        if new != "off":
            freq = 400 if new == "400Hz" else 1000
            try:
                # 3. Start the NEW tone
                self.log(f"SYSTEM: Playing {freq}Hz tone")
                self._beep_proc = subprocess.Popen(
                    ["speaker-test", "-t", "sine", "-f", str(freq), "-c", "2"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                self.log(f"SYSTEM ERR: Audio beep failed: {e}")

    # GPIO Ops
    def toggle_v33(self):
        self.m2_3v3.set(not self.m2_3v3.get())
        GPIO.output(26, GPIO.LOW if self.m2_3v3.get() else GPIO.HIGH)

    def toggle_pwr1(self):
        self.pwr1.set(not self.pwr1.get())
        GPIO.output(22, GPIO.LOW if self.pwr1.get() else GPIO.HIGH)

    def toggle_pwr2(self):
        self.pwr2.set(not self.pwr2.get())
        GPIO.output(23, GPIO.LOW if self.pwr2.get() else GPIO.HIGH)

    def on_gpio_interrupt(self, pin):
        val = GPIO.input(pin)
        s = "H" if val else "L"
        if pin in self.gpio_vars:
            self.root.after(0, lambda: self.gpio_vars[pin][1].set(s))

    def update_loops(self):
        # Temp Polling
        def _temp_loop():
            while True:
                try:
                    # Sync with Ingrid's readTemps.py logic or simple vcgencmd
                    # self.temp_pi.set(...)
                    import random
                    self.temp_pi.set(f"{random.uniform(35, 45):.2f}°C")
                    self.temp_smps.set(f"{random.uniform(30, 40):.2f}°C")
                    self.temp_ambient.set(f"{random.uniform(22, 25):.2f}°C")
                except: pass
                time.sleep(0.5)
        threading.Thread(target=_temp_loop, daemon=True).start()

        # Modem Detection
        def _modem_loop():
            while True:
                res = self.run_cmd_silent(["python3", MODEM_SCRIPT, "-detect"])
                if res and "Modem detected" in res:
                    self.modem_status.set("detected")
                else:
                    self.modem_status.set("not detected")
                time.sleep(5)
        threading.Thread(target=_modem_loop, daemon=True).start()

        self.update_time_display()

    def open_keyboard(self):
        VirtualKeyboard(self.root, self.wlan_ssid)

    def cancel_wlan(self):
        self.wlan_ssid.set("disconnected")
        self.log("WLAN Canceled")

    def flash_modem(self):
        self.run_modem_cmd(["--human", "--application", "--revert"])

    def show_advanced(self):
        self.main_container.pack_forget()
        self.adv_frame.pack(fill=tk.BOTH, expand=True)

    def show_main(self):
        self.adv_frame.pack_forget()
        self.main_container.pack(fill=tk.BOTH, expand=True)

    def on_closing(self):
        if hasattr(self, '_beep_proc') and self._beep_proc:
            try: self._beep_proc.terminate()
            except: pass
        GPIO.cleanup()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    ControlPanelV3().run()
