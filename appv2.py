#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk
try:
    import RPi.GPIO as GPIO
except (RuntimeError, ImportError):
    # Fallback to local RPi mock if system one is missing or not on a Pi
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        from unittest.mock import MagicMock
        GPIO = MagicMock()

import subprocess
import serial
import datetime
import time
import os
import re
import threading

# === CONFIG ===
MODEM_SCRIPT = os.path.join(os.path.dirname(__file__), "connection-manager.py")
DOWNLOAD_SCRIPT = os.path.join(os.path.dirname(__file__), "download.py")
SERIAL_PORT = "/dev/ttySOFT0"
BAUDRATE = 4800

class ControlPanel:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Raspberry Pi Control Panel v2")
        self.root.geometry("800x480")
        self.root.configure(bg="#f0f0f0")
        
        # Global Style for bigger touch targets
        self.style = ttk.Style()
        self.style.configure('Big.TButton', font=('Arial', 14, 'bold'), padding=10)
        self.style.configure('TNotebook.Tab', font=('Arial', 12, 'bold'), padding=[15, 8])

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        self.setup_gpio()

        # Variables
        self.temp_pi = tk.StringVar(value="??.??°C")
        self.temp_smps = tk.StringVar(value="??.??°C")
        self.temp_ambient = tk.StringVar(value="??.??°C")
        self.sys_time = tk.StringVar()
        self.rtc_time = tk.StringVar(value="N/A")
        self.nfc_text = tk.StringVar(value="Not found")
        self.beeper_mode = tk.StringVar(value="off")
        self.m2_3v3 = tk.BooleanVar(value=False)
        self.pwr1 = tk.BooleanVar(value=False)
        self.pwr2 = tk.BooleanVar(value=False)
        self.modem_detected = tk.StringVar(value="---")
        self.modem_version = tk.StringVar(value="---")
        self.imei = tk.StringVar(value="---")

        self.modem_serial = None
        self.modem_lock = threading.Lock()

        # Layout
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.left_frame = ttk.Frame(self.main_frame, width=500)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.right_frame = ttk.Frame(self.main_frame, width=300)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5, pady=5)

        self.setup_main_ui()
        self.setup_error_log()
        self.setup_advanced_ui()

        # Initial read of values
        self.update_all_pin_states()
        self.update_temps()
        self.update_time()
        # self.update_rtc_time() # Disabled: Spams logs on laptop
        self.update_nfc()
        # self.update_modem_detection() # Disabled: Spams logs on laptop
        # self.update_modem_version()   # Disabled: Spams logs on laptop
        # self.update_imei()            # Disabled: Spams logs on laptop

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def log_error(self, msg: str):
        # Thread-safe UI update
        def _update():
            ts = datetime.datetime.now().strftime("%H:%M:%S")
            line = f"[{ts}] {msg}\n"
            self.error_text.configure(state='normal')
            self.error_text.insert(tk.END, line)
            self.error_text.see(tk.END)
            self.error_text.configure(state='disabled')
        self.root.after(0, _update)

    def run_cmd(self, cmd):
        # Local mock fix: remove 'sudo' and 'python3' if running local mocks
        if any(x in str(cmd) for x in ["connection-manager.py", "download.py"]):
            if "sudo" in cmd: cmd.remove("sudo")
            
        try:
            # Use Popen to stream output line-by-line
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            
            # Read and log each line as it comes in
            for line in process.stdout:
                if line.strip():
                    self.log_error(f"LOG: {line.strip()}")
            
            process.wait() # Ensure it's finished
            return None
        except Exception as e:
            if "hwclock" not in str(cmd):
                self.log_error(f"CMD ERROR: {cmd[0]} → {e}")
            return None

    def setup_gpio(self):
        # Setup all pins as IN by default and add interrupts
        for pin in range(2, 28):
            try:
                # Default pins that should be OUT based on app logic
                if pin in [13, 26, 22, 23, 12]:
                    GPIO.setup(pin, GPIO.OUT)
                else:
                    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                    # Add interrupt for both rising and falling edges
                    GPIO.add_event_detect(pin, GPIO.BOTH, callback=self.on_gpio_interrupt, bouncetime=100)
            except Exception as e:
                self.log_error(f"GPIO {pin} setup error: {e}")
        self.beeper_pwm = GPIO.PWM(13, 1000)
        self.beeper_pwm.start(0)
        for pin in [26, 22, 23, 12]:
            GPIO.output(pin, GPIO.HIGH)

    def setup_main_ui(self):
        # Temps
        top = ttk.Frame(self.left_frame)
        top.pack(fill=tk.X, pady=2)
        for label, var in [("Temp Pi", self.temp_pi), ("Temp SMPS", self.temp_smps), ("Temp Ambient", self.temp_ambient)]:
            f = ttk.Frame(top)
            f.pack(side=tk.LEFT, padx=12)
            ttk.Label(f, textvariable=var, font=("Arial", 14, "bold")).pack()
            ttk.Label(f, text=label, font=("Arial", 10)).pack()

        # NFC
        nfc_f = ttk.Frame(top)
        nfc_f.pack(side=tk.RIGHT, padx=10)
        ttk.Label(nfc_f, text="NFC ID:", font=("Arial", 9)).pack()
        ttk.Label(nfc_f, textvariable=self.nfc_text, relief=tk.SUNKEN, width=18, anchor="w").pack()

        # Time
        time_f = ttk.LabelFrame(self.left_frame, text="Time", padding=5)
        time_f.pack(fill=tk.X, pady=3)
        ttk.Label(time_f, text="System:", font=("Arial", 9)).grid(row=0, column=0, sticky=tk.W, padx=2)
        ttk.Label(time_f, textvariable=self.sys_time, font=("Arial", 9)).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(time_f, text="RTC:", font=("Arial", 9)).grid(row=1, column=0, sticky=tk.W, padx=2)
        ttk.Label(time_f, textvariable=self.rtc_time, font=("Arial", 9)).grid(row=1, column=1, sticky=tk.W)

        btns = [
            ("Sys→RTC", lambda: self.run_cmd(["sudo", "hwclock", "-w"])),
            ("RTC→Sys", lambda: self.run_cmd(["sudo", "hwclock", "-s"])),
            ("Set RTC", lambda: self.run_cmd(["sudo", "hwclock", "--set", "--date=2025-12-24 13:45:30"])),
            ("Set Sys", lambda: self.run_cmd(["sudo", "date", "-s", "2025-12-24 13:45:30"])),
        ]
        for i, (txt, cmd) in enumerate(btns):
            ttk.Button(time_f, text=txt, command=cmd).grid(row=2, column=i, padx=2, pady=2)

        # Modem
        modem_f = ttk.LabelFrame(self.left_frame, text="M.2 Modem", padding=5)
        modem_f.pack(fill=tk.X, pady=3)
        ttk.Label(modem_f, text="Detected:", font=("Arial", 9)).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(modem_f, textvariable=self.modem_detected, font=("Arial", 9)).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(modem_f, text="Software:", font=("Arial", 9)).grid(row=1, column=0, sticky=tk.W)
        ttk.Label(modem_f, textvariable=self.modem_version, font=("Arial", 9)).grid(row=1, column=1, sticky=tk.W)
        ttk.Label(modem_f, text="IMEI:", font=("Arial", 9)).grid(row=2, column=0, sticky=tk.W)
        ttk.Label(modem_f, textvariable=self.imei, font=("Arial", 9)).grid(row=2, column=1, sticky=tk.W)

        btns = [
            ("Test M.2", lambda: self.run_modem_script(["--human", "--electrical"])),
            ("LTE Conn", lambda: self.run_modem_script(["--human"])),
            ("LTE DL", lambda: threading.Thread(target=self.run_cmd, args=(["python3", DOWNLOAD_SCRIPT],), daemon=True).start()),
            ("Flash M.2", lambda: self.run_modem_script(["--human", "--application", "--revert"])),
        ]
        for i, (txt, cmd) in enumerate(btns):
            ttk.Button(modem_f, text=txt, command=cmd).grid(row=3, column=i, padx=2, pady=2)

        # Controls
        ctrl = ttk.LabelFrame(self.left_frame, text="Controls", padding=5)
        ctrl.pack(fill=tk.X, pady=3)
        ttk.Label(ctrl, text="Beeper", font=("Arial", 9)).grid(row=0, column=0)
        cb = ttk.Combobox(ctrl, textvariable=self.beeper_mode, values=["off", "400Hz", "1kHz"], state="readonly", width=8)
        cb.grid(row=0, column=1, padx=3)
        self.beeper_mode.trace('w', self.on_beeper_change)

        toggles = [
            ("3V3 M.2", self.m2_3v3, self.toggle_m2_3v3, 26),
            ("PWR1", self.pwr1, self.toggle_pwr1, 22),
            ("PWR2", self.pwr2, self.toggle_pwr2, 23)
        ]
        for i, (txt, var, cmd, pin) in enumerate(toggles, 2):
            ttk.Checkbutton(ctrl, text=txt, variable=var, command=cmd).grid(row=0, column=i, padx=5)

        ttk.Button(self.left_frame, text="ADVANCED GPIO GRID", 
                   command=self.show_advanced, style='Big.TButton').pack(pady=10, fill=tk.X, padx=10)

    def run_modem_script(self, args):
        cmd = ["sudo", "python3", MODEM_SCRIPT] + args
        threading.Thread(target=self.run_cmd, args=(cmd,), daemon=True).start()

    def setup_error_log(self):
        log_frame = ttk.LabelFrame(self.right_frame, text="Error Log", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.error_text = tk.Text(log_frame, height=20, state='disabled', wrap='word', font=("Courier", 8))
        sb = ttk.Scrollbar(log_frame, orient="vertical", command=self.error_text.yview)
        self.error_text.configure(yscrollcommand=sb.set)
        self.error_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def setup_advanced_ui(self):
        self.adv_frame = ttk.Frame(self.root)
        self.adv_back_btn = ttk.Button(self.adv_frame, text="← BACK TO DASHBOARD", 
                                      command=self.show_main, style='Big.TButton')
        self.adv_back_btn.pack(fill=tk.X, padx=10, pady=10)
        
        # Notebook for Tabs
        self.nb = ttk.Notebook(self.adv_frame)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.gpio_mode = {}
        self.gpio_val = {}
        self.gpio_state_label = {}

        # 3 Groups of pins
        groups = [
            ("PINS 2-9", range(2, 10)),
            ("PINS 10-18", range(10, 19)),
            ("PINS 19-27", range(19, 28))
        ]

        for title, pin_range in groups:
            tab = ttk.Frame(self.nb, padding=10)
            self.nb.add(tab, text=title)
            
            # Using 2 columns to make each PIN control much bigger
            for i, pin in enumerate(pin_range):
                r, c = divmod(i, 2)
                f = ttk.LabelFrame(tab, text=f" GPIO {pin} ", padding=10)
                f.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
                tab.columnconfigure(c, weight=1)

                mode = tk.StringVar(value="IN" if pin not in [13,26,22,23,12] else "OUT")
                val = tk.StringVar(value="OFF")
                state = tk.StringVar(value="-")

                # Font for controls
                big_font = ("Arial", 14, "bold")

                cb_mode = ttk.Combobox(f, textvariable=mode, values=["IN", "OUT"], width=5, state="readonly", font=big_font)
                cb_mode.pack(side=tk.LEFT, padx=10)
                cb_mode.bind("<<ComboboxSelected>>", lambda e, p=pin: self.on_gpio_mode_change(p))

                cb_val = ttk.Combobox(f, textvariable=val, values=["ON", "OFF"], width=5, state="readonly", font=big_font)
                cb_val.pack(side=tk.LEFT, padx=10)
                cb_val.bind("<<ComboboxSelected>>", lambda e, p=pin: self.on_gpio_value_change(p))

                # Display label for state (H / L) with bigger font
                lbl = ttk.Label(f, textvariable=state, font=("Courier", 18, "bold"), foreground="blue", width=2)
                lbl.pack(side=tk.RIGHT, padx=15)

                self.gpio_mode[pin] = mode
                self.gpio_val[pin] = val
                self.gpio_state_label[pin] = state

        self.adv_frame.pack_forget()

    def show_advanced(self):
        self.main_frame.pack_forget()
        self.adv_frame.pack(fill=tk.BOTH, expand=True)
        self.update_all_pin_states()

    def show_main(self):
        self.adv_frame.pack_forget()
        self.main_frame.pack(fill=tk.BOTH, expand=True)

    # Updates
    def update_temps(self):
        try:
            temp = subprocess.check_output(['vcgencmd', 'measure_temp']).decode()
            temp = float(temp.split('=')[1].strip("'C\n"))
            self.temp_pi.set(f"{temp:05.2f}°C")
        except:
            self.temp_pi.set("???.??°C")
        self.temp_smps.set("45.67°C")  # Replace with real sensor later
        self.temp_ambient.set("23.45°C")
        self.root.after(500, self.update_temps)

    def update_time(self):
        self.sys_time.set(datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        self.root.after(1000, self.update_time)

    def update_rtc_time(self):
        res = self.run_cmd(["sudo", "hwclock", "-r"])
        if res:
            try:
                parts = res.strip().split()
                date = parts[0]
                time = parts[1].split('.')[0]
                self.rtc_time.set(f"{date} {time}")
            except:
                self.rtc_time.set("Invalid")
        else:
            self.rtc_time.set("Error")
        self.root.after(2000, self.update_rtc_time)

    def update_nfc(self):
        self.nfc_text.set("Not found")
        self.root.after(3000, self.update_nfc)

    def update_modem_detection(self):
        res = self.run_cmd(["sudo", "python3", MODEM_SCRIPT, "-detect"])
        self.modem_detected.set("Detected" if res and "detected" in res else "Not detected")
        self.root.after(3000, self.update_modem_detection)

    def update_modem_version(self):
        ver = self.send_at("AT#XSLMVER")
        if ver and "XSLMVER" in ver:
            m = re.search(r'#XSLMVER:\s*"([^"]+)"', ver)
            self.modem_version.set(m.group(1) if m else "Unknown")
        else:
            self.modem_version.set("---")
        self.root.after(10000, self.update_modem_version)

    def update_imei(self):
        imei = self.send_at("AT+CGSN")
        if imei and len(imei.strip()) == 15:
            self.imei.set(imei.strip())
        else:
            self.imei.set("---")
        self.root.after(15000, self.update_imei)

    def send_at(self, cmd):
        with self.modem_lock:
            try:
                if not self.modem_serial:
                    self.modem_serial = serial.Serial(SERIAL_PORT, BAUDRATE, timeout=2)
                    time.sleep(0.1)
                self.modem_serial.write(f"{cmd}\r\n".encode())
                time.sleep(0.3)
                return self.modem_serial.read(1000).decode(errors='ignore')
            except Exception as e:
                self.log_error(f"AT error: {e}")
                return None

    def on_beeper_change(self, *args):
        freq = {"off": 0, "400Hz": 400, "1kHz": 1000}[self.beeper_mode.get()]
        if freq == 0:
            self.beeper_pwm.ChangeDutyCycle(0)
        else:
            self.beeper_pwm.ChangeFrequency(freq)
            self.beeper_pwm.ChangeDutyCycle(50)

    def toggle_m2_3v3(self): GPIO.output(26, GPIO.LOW if self.m2_3v3.get() else GPIO.HIGH)
    def toggle_pwr1(self): GPIO.output(22, GPIO.LOW if self.pwr1.get() else GPIO.HIGH)
    def toggle_pwr2(self): GPIO.output(23, GPIO.LOW if self.pwr2.get() else GPIO.HIGH)

    def on_gpio_interrupt(self, pin):
        # This is called from a separate thread by RPi.GPIO
        try:
            val = GPIO.input(pin)
            state_str = "H" if val else "L"
            
            # Update UI from the main thread
            if pin in self.gpio_state_label:
                self.root.after(0, lambda p=pin, s=state_str: self.gpio_state_label[p].set(s))
        except: pass

    def update_all_pin_states(self):
        # One-time read for all current values
        for pin, lbl in self.gpio_state_label.items():
            if self.gpio_mode[pin].get() == "IN":
                try:
                    val = GPIO.input(pin)
                    lbl.set("H" if val else "L")
                except: lbl.set("?")
            else:
                lbl.set("-")

    def on_gpio_mode_change(self, pin):
        new_mode = self.gpio_mode[pin].get()
        try:
            if new_mode == "IN":
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                # Ensure we don't add duplicate interrupts
                try: GPIO.remove_event_detect(pin)
                except: pass
                GPIO.add_event_detect(pin, GPIO.BOTH, callback=self.on_gpio_interrupt, bouncetime=100)
            else:
                # Switching to OUT: remove interrupt
                try: GPIO.remove_event_detect(pin)
                except: pass
                GPIO.setup(pin, GPIO.OUT)
                
            self.update_all_pin_states()
        except Exception as e:
            self.log_error(f"Mode change error on {pin}: {e}")

    def on_gpio_value_change(self, pin):
        if self.gpio_mode[pin].get() == "OUT":
            val = 1 if self.gpio_val[pin].get() == "ON" else 0
            try: GPIO.output(pin, val)
            except: pass

    def on_closing(self):
        self.beeper_pwm.stop()
        if self.modem_serial: self.modem_serial.close()
        GPIO.cleanup()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    ControlPanel().run()
