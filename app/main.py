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
import io

# Setup path to import from parent directory correctly (readTemps, connection_tester, RPi mock)
_parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _parent_dir)

IS_PI = False
try:
    with open('/proc/device-tree/model', 'r') as f:
        if 'Raspberry Pi' in f.read():
            IS_PI = True
except Exception:
    pass

if IS_PI:
    # On an actual Raspberry Pi, remove local mock from path to load system RPi.GPIO
    sys.path.remove(_parent_dir)
    import RPi.GPIO as GPIO
    sys.path.insert(0, _parent_dir)
else:
    # On a normal PC, safely import the local mock from the parent directory
    import RPi.GPIO as GPIO

import readTemps
import connection_tester

from .tab_dashboard import DashboardTab
from .tab_tester import TesterTab
from .tab_connect import ConnectTab
from .tab_advanced import AdvancedTab

class PiTesterAppV6:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pi Tester Control Panel V6")
        self.root.geometry("800x480")
        self.root.resizable(False, False)
        self.root.configure(bg='#e1e1e1')

        # Locks & Concurrency
        self.cmd_lock = threading.Lock()
        self.is_busy = False

        # Variables
        self.temp_pi = tk.StringVar(value="--")
        self.temp_smps = tk.StringVar(value="--")
        self.temp_ambient = tk.StringVar(value="--")
        self.sys_time = tk.StringVar(value="--")
        self.rtc_time = tk.StringVar(value="--")
        self.nfc_id = tk.StringVar(value="no card")
        self.beeper_state = tk.StringVar(value="off")
        self.pwr1 = tk.BooleanVar(value=True)
        self.pwr2 = tk.BooleanVar(value=True)
        self.modem_status = tk.StringVar(value="---")
        self.wlan_ssid = tk.StringVar(value="disconnected")
        self.m2_software = tk.StringVar(value="...")
        self.m2_imei = tk.StringVar(value="IMEI: ----")
        
        self._beep_proc = None
        self._pi_pwm = None

        # Tester Instance (Lazy Init)
        self.tester = None
        
        # GPIO Elements for Advanced Tab
        self.gpio_elements = {}

        # Style Configuration
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TNotebook.Tab', padding=[10, 2], font=('Arial', 9, 'bold'))
        self.style.configure('Value.TLabel', font=('Courier', 10, 'bold'), foreground='#0099ff')
        self.style.configure('Clock.TLabel', font=('Courier', 11, 'bold'), foreground='#0099ff')
        self.style.configure('GPIO.TButton', font=('Arial', 8), width=2, padding=1)
        self.style.configure('Action.TButton', font=('Arial', 10, 'bold'), padding=5)

        self.setup_ui()
        self.start_loops()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        # 1. 50% LOG SIDEBAR
        self.sidebar_w = 400
        self.log_frame = tk.Frame(self.root, width=self.sidebar_w, bg="#1a1a1a")
        self.log_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_frame.pack_propagate(False)
        
        tk.Label(self.log_frame, text=" SYSTEM LOGS & OUTPUT ", fg="white", bg="#333", font=('Arial', 10, 'bold')).pack(fill=tk.X)
        self.error_text = scrolledtext.ScrolledText(self.log_frame, bg="#000", fg="#cccccc", font=("Courier", 10), borderwidth=0)
        self.error_text.pack(fill=tk.BOTH, expand=True)

        # 2. 50% MAIN NOTEBOOK
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # TAB 1: DASHBOARD
        self.tab_dashboard = DashboardTab(self.nb, self)
        self.nb.add(self.tab_dashboard, text=" DASHBOARD ")
        
        # TAB 2: TESTER
        self.tab_tester = TesterTab(self.nb, self)
        self.nb.add(self.tab_tester, text=" TESTER ")
        
        # TAB 3: CONNECT
        self.tab_connect = ConnectTab(self.nb, self)
        self.nb.add(self.tab_connect, text=" CONNECT ")
        
        # TAB 4: ADVANCED
        self.tab_advanced = AdvancedTab(self.nb, self)
        self.nb.add(self.tab_advanced, text=" ADV ")

    # --- LOGIC ---
    def log(self, m):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        strip_m = str(m).replace('\x1b[31;1;5m', '').replace('\x1b[32m', '').replace('\x1b[31m', '').replace('\x1b[33m', '').replace('\x1b[36m', '').replace('\x1b[35m', '').replace('\x1b[0m', '').replace('\x1b[22m', '')
        self.error_text.configure(state='normal')
        self.error_text.insert(tk.END, f"{t}: {strip_m}\n")
        self.error_text.see(tk.END)
        self.error_text.configure(state='disabled')

    def run_raw_sync(self, cmd):
        self.is_busy = True
        self.log(f"> {cmd}")
        with self.cmd_lock:
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                if r.stdout: self.log(r.stdout.strip())
                success = (r.returncode == 0)
            except Exception as e: 
                self.log(f"Err: {e}")
                success = False
        self.is_busy = False
        return success

    def run_bg(self, cmd, after_func=None):
        def _t():
            s = self.run_raw_sync(cmd)
            if after_func: after_func()
        threading.Thread(target=_t, daemon=True).start()

    def bg_task(self, func): 
        threading.Thread(target=func, daemon=True).start()

    # --- TESTER WRAPPERS ---
    def init_tester(self):
        def _task():
            try:
                self.log("Tester: Initializing...")
                now = datetime.datetime.now().strftime("%y%m%d_%H%M")
                self.tester = connection_tester.ConnectionManager(
                    folder=f"test_{now}", 
                    location="Lab", card="M2", cable="USB", antenna="Internal"
                )
                self.log("Tester: Init OK (Session: test_" + now + ")")
            except Exception as e: self.log(f"Tester Init Fail: {e}")
        self.bg_task(_task)

    def tester_check_eth(self):
        if not self.tester: self.log("Error: Init Tester first!"); return
        def _task():
            res = self.tester.Check_ETH()
            self.log(f"Tester: ETH Carrier = {res}")
        self.bg_task(_task)

    def tester_check_wlan(self):
        if not self.tester: self.log("Error: Init Tester first!"); return
        def _task():
            res = self.tester.Check_WLAN()
            self.log(f"Tester: WLAN connected = {res}")
        self.bg_task(_task)

    def tester_modem_diag(self):
        if not self.tester: self.log("Error: Init Tester first!"); return
        def _task():
            self.log("Tester: Starting Modem Diag...")
            old_stdout = sys.stdout
            sys.stdout = mystdout = io.StringIO()
            try:
                self.tester.Modem.Diag()
                self.tester.Modem.DiagDecode(self.tester.LogFile)
                output = mystdout.getvalue()
                for line in output.split('\n'):
                    if line.strip(): self.log(line)
            finally:
                sys.stdout = old_stdout
            self.log("Tester: Diag Complete.")
        self.bg_task(_task)

    def tester_modem_check_mode(self):
        if not self.tester: self.log("Error: Init Tester first!"); return
        def _task():
            self.tester.Modem.CheckMode()
            self.log("Tester: Mode check sent.")
        self.bg_task(_task)

    def tester_ppp_on(self):
        if not self.tester: self.log("Error: Init Tester first!"); return
        self.bg_task(lambda: (self.tester.PPPD_on(), self.log("Tester: pppd start request sent.")))

    def tester_ppp_off(self):
        if not self.tester: self.log("Error: Init Tester first!"); return
        self.bg_task(lambda: (self.tester.PPPD_off(), self.log("Tester: pppd stop request sent.")))

    # --- OTHER METHODS ---
    def sync_sys_prefix(self):
        def _task():
            urls = ["https://worldtimeapi.org/api/timezone/Etc/UTC", "https://timeapi.io/api/Time/current/zone?timeZone=UTC"]
            for url in urls:
                try:
                    self.log(f"Sync: Querying {url.split('/')[2]}...")
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=5) as res:
                        data = json.load(res)
                        dt = data.get("utc_datetime") or data.get("dateTime")
                        if dt:
                            dt = dt.split(".")[0].replace("T", " ")
                            if self.run_raw_sync(f"sudo date -s '{dt}'"):
                                self.run_raw_sync("sudo hwclock --systohc -f /dev/rtc")
                                self.log(f"Sync Success: {dt}"); self.refresh_rtc_display(); return
                except Exception as e: self.log(f"Sync attempt failed: {e}")
            self.log("Sync Fail: All sources exhausted.")
        threading.Thread(target=_task, daemon=True).start()

    def refresh_rtc_display(self):
        with self.cmd_lock:
            try:
                v = subprocess.check_output("sudo hwclock -r -f /dev/rtc", shell=True, text=True).split('.')[0].strip()
                self.rtc_time.set(v)
            except: self.rtc_time.set("Err")
    
    def refresh_rtc_btn(self): 
        self.bg_task(lambda: (self.refresh_rtc_display(), self.log(f"RTC: {self.rtc_time.get()}")))

    def toggle_beeper(self):
        def _task():
            ops = ["off", "400Hz", "1kHz"]
            nxt = ops[(ops.index(self.beeper_state.get()) + 1) % 3]
            self.beeper_state.set(nxt)
            if self._pi_pwm: self._pi_pwm.stop(); self._pi_pwm = None
            if self._beep_proc: self._beep_proc.kill(); self._beep_proc = None
            subprocess.run("killall -q speaker-test", shell=True)
            if nxt != "off":
                f = 400 if nxt == "400Hz" else 1000
                if IS_PI: 
                    try:
                        GPIO.setup(13, GPIO.OUT)
                        self._pi_pwm = GPIO.PWM(13, f)
                        self._pi_pwm.start(50)
                    except: pass
                else: 
                    self._beep_proc = subprocess.Popen(f"speaker-test -t sine -f {f} -c 2", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.log(f"Beeper: {nxt}")
        self.bg_task(_task)

    def toggle_pwr1(self): 
        self.bg_task(lambda: (self.pwr1.set(not self.pwr1.get()), GPIO.setup(26, GPIO.OUT) if IS_PI else None, GPIO.output(26, self.pwr1.get()) if IS_PI else None, self.log(f"PWR 1: {'ON' if self.pwr1.get() else 'OFF'}")))
        
    def toggle_pwr2(self): 
        self.bg_task(lambda: (self.pwr2.set(not self.pwr2.get()), GPIO.setup(22, GPIO.OUT) if IS_PI else None, GPIO.output(22, self.pwr2.get()) if IS_PI else None, self.log(f"PWR 2: {'ON' if self.pwr2.get() else 'OFF'}")))
    
    def set_gpio_mode(self, p, m): 
        if not IS_PI:
            self.log(f"Pin P{p} -> {m} (simulated)")
            return
        try: 
            GPIO.setup(p, GPIO.IN if m=="IN" else GPIO.OUT)
            self.log(f"Pin P{p} -> {m}")
        except: 
            self.log(f"Pin P{p} mode fail")

    def set_gpio_level(self, p, l): 
        if not IS_PI:
            self.log(f"Pin P{p} -> {l} (simulated)")
            return
        try: 
            GPIO.output(p, l)
            self.log(f"Pin P{p} -> {l}")
        except: 
            self.log(f"P{p} output fail")

    def start_loops(self):
        def _clock():
            while True:
                self.sys_time.set(datetime.datetime.now().strftime("%H:%M:%S"))
                if not self.is_busy: self.refresh_rtc_display()
                time.sleep(1)
        threading.Thread(target=_clock, daemon=True).start()
        
        def _temp():
            while True:
                if IS_PI:
                    t = readTemps.read_all_temps() or [None,None,None]
                    self.temp_pi.set(f"{t[0]:.1f}" if t[0] else "?")
                    self.temp_smps.set(f"{t[1]:.1f}" if t[1] else "?")
                    self.temp_ambient.set(f"{t[2]:.1f}" if t[2] else "?")
                else: 
                    self.temp_pi.set("30.0")
                    self.temp_smps.set("40.0")
                    self.temp_ambient.set("20.0")
                time.sleep(2)
        threading.Thread(target=_temp, daemon=True).start()
        
        def _poll():
            while True:
                if hasattr(self, 'nb') and self.nb.index("current") == 3: # Adv tab
                    for p, el in self.gpio_elements.items():
                        try: 
                            c = "#0f0" if (IS_PI and GPIO.input(p)) else "#f00"
                            el["led"].itemconfig(el["obj"], fill=c)
                        except: pass
                time.sleep(1)
        threading.Thread(target=_poll, daemon=True).start()

    def run_modem_cmd(self, args):
        cmd_str = " ".join(args)
        self.run_bg(cmd_str)

    def on_closing(self):
        if self._pi_pwm: self._pi_pwm.stop()
        if self._beep_proc: self._beep_proc.kill()
        if IS_PI:
            try:
                GPIO.cleanup()
            except:
                pass
        self.root.destroy()
        
    def run(self): 
        self.root.mainloop()

if __name__ == "__main__":
    PiTesterAppV6().run()
