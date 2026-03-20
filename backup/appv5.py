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

# Try to import RPi.GPIO
try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))
    import RPi.GPIO as GPIO
    IS_PI = False
else:
    IS_PI = True

import readTemps
import connection_tester

class ControlPanelV5:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pi Tester Control Panel V5")
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

        # Style Configuration
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TNotebook.Tab', padding=[10, 2], font=('Arial', 9, 'bold'))
        self.style.configure('Value.TLabel', font=('Courier', 10, 'bold'), foreground='#0099ff')
        self.style.configure('Clock.TLabel', font=('Courier', 11, 'bold'), foreground='#0099ff')
        self.style.configure('GPIO.TButton', font=('Arial', 12, 'bold'), width=2, padding=4)
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

        # ---- TAB 1: DASHBOARD ----
        tab1 = ttk.Frame(self.nb, padding=2)
        self.nb.add(tab1, text=" DASHBOARD ")
        
        top_bar = ttk.Frame(tab1, relief="groove", padding=2)
        top_bar.pack(fill=tk.X, pady=1)
        ttk.Label(top_bar, text="NFC:", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=1)
        ttk.Label(top_bar, textvariable=self.nfc_id, font=("Courier", 9, "bold"), foreground="blue").pack(side=tk.LEFT, padx=(0, 5))
        for lbl, var in [("Pi:", self.temp_pi), ("PSU:", self.temp_smps), ("Amb:", self.temp_ambient)]:
            f_tmp = ttk.Frame(top_bar); f_tmp.pack(side=tk.LEFT, padx=1)
            ttk.Label(f_tmp, text=lbl, font=("Arial", 8)).pack(side=tk.LEFT)
            ttk.Label(f_tmp, textvariable=var, style='Value.TLabel').pack(side=tk.LEFT, padx=1)

        t_box = ttk.LabelFrame(tab1, text=" Time Control ", padding=3)
        t_box.pack(fill=tk.BOTH, expand=True, pady=1)
        
        sr = ttk.Frame(t_box); sr.pack(fill=tk.X); ttk.Label(sr, text="SYS:", font=("Arial", 9, "bold")).pack(side=tk.LEFT); ttk.Label(sr, textvariable=self.sys_time, style='Clock.TLabel').pack(side=tk.LEFT, padx=3)
        br1 = ttk.Frame(t_box); br1.pack(fill=tk.X, pady=1)
        ttk.Button(br1, text="Preset 2011", command=lambda: self.run_bg("sudo date -s '2011-01-01 11:11:11'")).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(br1, text="SysPrefix", command=self.sync_sys_prefix).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        
        rr = ttk.Frame(t_box); rr.pack(fill=tk.X, pady=(2,0)); ttk.Label(rr, text="RTC:", font=("Arial", 9, "bold")).pack(side=tk.LEFT); ttk.Label(rr, textvariable=self.rtc_time, style='Clock.TLabel').pack(side=tk.LEFT, padx=3)
        br2 = ttk.Frame(t_box); br2.pack(fill=tk.X, pady=1)
        ttk.Button(br2, text="Read RTC", command=self.refresh_rtc_btn).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(br2, text="Set Preset", command=lambda: self.run_bg('sudo hwclock --set --date="2025-12-24 13:45:30" -f /dev/rtc', self.refresh_rtc_display)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        
        br3 = ttk.Frame(t_box); br3.pack(fill=tk.X, pady=1)
        ttk.Button(br3, text="Sys->RTC", command=lambda: self.run_bg("sudo hwclock --systohc -f /dev/rtc", self.refresh_rtc_display)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(br3, text="RTC->Sys", command=lambda: self.run_bg("sudo hwclock --hctosys -f /dev/rtc", self.refresh_rtc_display)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        
        man_f = ttk.Frame(t_box); man_f.pack(fill=tk.X, pady=1); ttk.Label(man_f, text="Set Manual:", font=("Arial", 8)).pack(anchor="w")
        self.rtc_entry = ttk.Entry(man_f, font=("Courier", 10)); self.rtc_entry.insert(0, "2025-12-24 13:45:30"); self.rtc_entry.pack(fill=tk.X, pady=1)
        ttk.Button(man_f, text="SET HARDWARE CLOCK", command=lambda: self.run_bg(f'sudo hwclock --set --date="{self.rtc_entry.get()}" -f /dev/rtc', self.refresh_rtc_display)).pack(fill=tk.X)

        # ---- TAB 2: TESTER (NEW) ----
        tab_tester = ttk.Frame(self.nb, padding=5)
        self.nb.add(tab_tester, text=" TESTER ")
        
        tester_inner = ttk.Frame(tab_tester)
        tester_inner.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(tester_inner, text="Connection Tester Tools", font=("Arial", 11, "bold")).pack(pady=5)
        
        btns_tester = [
            ("Init Tester Session", self.init_tester),
            ("Check Ethernet", self.tester_check_eth),
            ("Check WLAN", self.tester_check_wlan),
            ("Modem Diag (Full)", self.tester_modem_diag),
            ("Modem Check Mode", self.tester_modem_check_mode),
            ("Start PPP Daemon", self.tester_ppp_on),
            ("Stop PPP Daemon", self.tester_ppp_off),
        ]
        
        for txt, cmd in btns_tester:
            ttk.Button(tester_inner, text=txt, command=cmd, style='Action.TButton').pack(fill=tk.X, pady=2, padx=10)

        # ---- TAB 3: CONNECT ----
        tab2 = ttk.Frame(self.nb, padding=2)
        self.nb.add(tab2, text=" CONNECT ")
        for name, var, cmd in [("Beeper", self.beeper_state, self.toggle_beeper), ("PWR 1", None, self.toggle_pwr1), ("PWR 2", None, self.toggle_pwr2)]:
            f = ttk.Frame(tab2); f.pack(fill=tk.X, pady=1); t = var if var else name; ttk.Button(f, textvariable=t if var else None, text=None if var else name, command=cmd).pack(fill=tk.X)
        m_f = ttk.LabelFrame(tab2, text=" Modem Info ", padding=2); m_f.pack(fill=tk.X, pady=1)
        for l, v in [("Stat:", self.modem_status), ("Ver:", self.m2_software), ("IMEI:", self.m2_imei)]:
            f = ttk.Frame(m_f); f.pack(fill=tk.X); ttk.Label(f, text=l, font=("Arial",8)).pack(side=tk.LEFT); ttk.Label(f, textvariable=v, style='Value.TLabel' if v==self.modem_status else 'TLabel').pack(side=tk.LEFT)
        for t, c in [("Wiring Check", lambda: self.run_modem_cmd(["--human","--electrical"])), ("LTE Check", lambda: self.run_modem_cmd(["--human"])), ("Test Download", lambda: self.run_modem_cmd(["python3","download.py"]))]:
            ttk.Button(tab2, text=t, command=c).pack(fill=tk.X, pady=1)
        w_f = ttk.LabelFrame(tab2, text=" WLAN ", padding=2); w_f.pack(fill=tk.X, pady=1); ttk.Label(w_f, textvariable=self.wlan_ssid, relief="sunken", font=("Arial", 8)).pack(fill=tk.X); ttk.Button(w_f, text="Connect WLAN", command=lambda: self.log("Request: Kbd")).pack(fill=tk.X)

        # ---- TAB 4: ADVANCED ----
        tab3 = ttk.Frame(self.nb, padding=1)
        self.nb.add(tab3, text=" ADV ")
        nb_g = ttk.Notebook(tab3); nb_g.pack(fill=tk.BOTH, expand=True)
        self.gpio_elements = {}
        for title, pins in [("2-9", range(2, 10)), ("10-17", range(10, 18)), ("18-25", range(18, 26)), ("26-27", range(26, 28))]:
            tab_g = ttk.Frame(nb_g, padding=2); nb_g.add(tab_g, text=title)
            for i, p in enumerate(pins):
                r, c = divmod(i, 2); f = ttk.Frame(tab_g, relief="groove", borderwidth=1); f.grid(row=r, column=c, padx=1, pady=3, sticky="ew", ipady=1)
                tab_g.columnconfigure(c, weight=1); ind_f = ttk.Frame(f); ind_f.pack(side=tk.LEFT, padx=(2, 5))
                led = tk.Canvas(ind_f, width=16, height=16, highlightthickness=0); led.pack(side=tk.LEFT, padx=1); obj = led.create_oval(2, 2, 14, 14, fill="gray"); ttk.Label(ind_f, text=f"P{p}", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
                btn_f = ttk.Frame(f); btn_f.pack(side=tk.LEFT)
                for t, m, l in [("I","IN",None), ("O","OUT",None), ("H",None,1), ("L",None,0)]:
                    cmd_f = (lambda x=p,mode=m: self.bg_task(lambda: self.set_gpio_mode(x,mode))) if m else (lambda x=p,lvl=l: self.bg_task(lambda: self.set_gpio_level(x,lvl)))
                    ttk.Button(btn_f, text=t, style='GPIO.TButton', command=cmd_f).pack(side=tk.LEFT, padx=0)
                self.gpio_elements[p] = {"led": led, "obj": obj}

    # --- LOGIC ---
    def log(self, m):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        strip_m = str(m).replace('\x1b[31;1;5m', '').replace('\x1b[32m', '').replace('\x1b[31m', '').replace('\x1b[33m', '').replace('\x1b[36m', '').replace('\x1b[35m', '').replace('\x1b[0m', '').replace('\x1b[22m', '')
        self.error_text.configure(state='normal'); self.error_text.insert(tk.END, f"{t}: {strip_m}\n"); self.error_text.see(tk.END); self.error_text.configure(state='disabled')

    def run_raw_sync(self, cmd):
        self.is_busy = True; self.log(f"> {cmd}")
        with self.cmd_lock:
            try:
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                if r.stdout: self.log(r.stdout.strip())
                success = (r.returncode == 0)
            except Exception as e: self.log(f"Err: {e}"); success = False
        self.is_busy = False; return success

    def run_bg(self, cmd, after_func=None):
        def _t():
            s = self.run_raw_sync(cmd)
            if after_func: after_func()
        threading.Thread(target=_t, daemon=True).start()

    def bg_task(self, func): threading.Thread(target=func, daemon=True).start()

    # --- TESTER WRAPPERS ---
    def init_tester(self):
        def _task():
            try:
                self.log("Tester: Initializing...")
                # We provide default values to avoid interactive inputs
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
            # Capture output from DiagDecode
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
    
    def refresh_rtc_btn(self): self.bg_task(lambda: (self.refresh_rtc_display(), self.log(f"RTC: {self.rtc_time.get()}")))

    def toggle_beeper(self):
        def _task():
            ops = ["off", "400Hz", "1kHz"]; nxt = ops[(ops.index(self.beeper_state.get()) + 1) % 3]; self.beeper_state.set(nxt)
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
                else: self._beep_proc = subprocess.Popen(f"speaker-test -t sine -f {f} -c 2", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.log(f"Beeper: {nxt}")
        self.bg_task(_task)

    def toggle_pwr1(self): self.bg_task(lambda: (self.pwr1.set(not self.pwr1.get()), GPIO.setup(26, GPIO.OUT), GPIO.output(26, self.pwr1.get()), self.log(f"PWR 1: {'ON' if self.pwr1.get() else 'OFF'}")))
    def toggle_pwr2(self): self.bg_task(lambda: (self.pwr2.set(not self.pwr2.get()), GPIO.setup(22, GPIO.OUT), GPIO.output(22, self.pwr2.get()), self.log(f"PWR 2: {'ON' if self.pwr2.get() else 'OFF'}")))
    
    def set_gpio_mode(self, p, m): 
        try: GPIO.setup(p, GPIO.IN if m=="IN" else GPIO.OUT); self.log(f"Pin P{p} -> {m}")
        except: self.log(f"Pin P{p} mode fail")

    def set_gpio_level(self, p, l): 
        try: GPIO.output(p, l); self.log(f"Pin P{p} -> {l}")
        except: self.log(f"P{p} output fail")

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
                    self.temp_pi.set(f"{t[0]:.1f}" if t[0] else "?"); self.temp_smps.set(f"{t[1]:.1f}" if t[1] else "?"); self.temp_ambient.set(f"{t[2]:.1f}" if t[2] else "?")
                else: self.temp_pi.set("30.0"); self.temp_smps.set("40.0"); self.temp_ambient.set("20.0")
                time.sleep(2)
        threading.Thread(target=_temp, daemon=True).start()
        def _poll():
            while True:
                if hasattr(self, 'nb') and self.nb.index("current") == 3: # Adv tab
                    for p, el in self.gpio_elements.items():
                        try: c = "#0f0" if GPIO.input(p) else "#f00"; el["led"].itemconfig(el["obj"], fill=c)
                        except: pass
                time.sleep(1)
        threading.Thread(target=_poll, daemon=True).start()

    def run_modem_cmd(self, args):
        cmd_str = " ".join(args)
        self.run_bg(cmd_str)

    def on_closing(self):
        if self._pi_pwm: self._pi_pwm.stop()
        if self._beep_proc: self._beep_proc.kill()
        GPIO.cleanup(); self.root.destroy()
    def run(self): self.root.mainloop()

if __name__ == "__main__":
    ControlPanelV5().run()
