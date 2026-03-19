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

# Constants
MODEM_SCRIPT = "connection-manager.py"
DOWNLOAD_SCRIPT = "download.py"

class ControlPanelV4:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Raspberry Pi Control Panel (v4 Fixed UI)")
        self.root.geometry("800x480")
        self.root.resizable(False, False)
        self.root.configure(bg='#e1e1e1')

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

        # Style Configuration
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TNotebook.Tab', padding=[5, 2], font=('Arial', 9, 'bold'))
        self.style.configure('Value.TLabel', font=('Courier', 11, 'bold'), foreground='#0099ff')
        self.style.configure('Clock.TLabel', font=('Courier', 12, 'bold'), foreground='#0099ff')
        self.style.configure('TButton', font=('Arial', 9))

        self.setup_ui()
        self.start_loops()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        # 1. FIXED LOG SIDEBAR (Forced Width)
        self.sidebar_w = 200
        self.log_frame = tk.Frame(self.root, width=self.sidebar_w, bg="#222")
        self.log_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_frame.pack_propagate(False) # CRITICAL: Don't let inner text resize this frame
        
        tk.Label(self.log_frame, text=" SYSTEM LOGS ", fg="white", bg="#333", font=('Arial', 9, 'bold')).pack(fill=tk.X)
        self.error_text = scrolledtext.ScrolledText(self.log_frame, bg="#111", fg="#0f0", font=("Courier", 8), borderwidth=0)
        self.error_text.pack(fill=tk.BOTH, expand=True)

        # 2. MAIN NOTEBOOK
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ---- TAB 1: DASHBOARD ----
        tab1 = ttk.Frame(self.nb, padding=2)
        self.nb.add(tab1, text=" DASHBOARD ")
        
        # Environment
        s_box = ttk.LabelFrame(tab1, text=" Environment ", padding=2)
        s_box.pack(fill=tk.X, pady=1)
        for lbl, var in [("Pi:", self.temp_pi), ("Power:", self.temp_smps), ("Amb:", self.temp_ambient)]:
            f = ttk.Frame(s_box); f.pack(side=tk.LEFT, padx=10)
            ttk.Label(f, text=lbl).pack(side=tk.LEFT)
            ttk.Label(f, textvariable=var, style='Value.TLabel').pack(side=tk.LEFT, padx=2)

        # NFC
        nfc_f = ttk.LabelFrame(tab1, text=" NFC Scan ", padding=2)
        nfc_f.pack(fill=tk.X, pady=1)
        ttk.Label(nfc_f, text="NFC ID:").pack(side=tk.LEFT)
        ttk.Label(nfc_f, textvariable=self.nfc_id, style='Value.TLabel').pack(side=tk.LEFT, padx=5)

        # Time Group (Full suite)
        t_box = ttk.LabelFrame(tab1, text=" Time & RTC ", padding=2)
        t_box.pack(fill=tk.X, pady=1)
        
        # SYS Time Row
        r1 = ttk.Frame(t_box); r1.pack(fill=tk.X, pady=1)
        ttk.Label(r1, text="SYS:", width=5).pack(side=tk.LEFT)
        ttk.Label(r1, textvariable=self.sys_time, style='Clock.TLabel', width=18).pack(side=tk.LEFT)
        ttk.Button(r1, text="Preset 2011", width=10, command=self.preset_sys_time).pack(side=tk.LEFT, padx=1)
        ttk.Button(r1, text="SysPrefix", width=10, command=self.sync_sys_prefix).pack(side=tk.LEFT, padx=1)
        
        # RTC Time Row
        r2 = ttk.Frame(t_box); r2.pack(fill=tk.X, pady=1)
        ttk.Label(r2, text="RTC:", width=5).pack(side=tk.LEFT)
        ttk.Label(r2, textvariable=self.rtc_time, style='Clock.TLabel', width=18).pack(side=tk.LEFT)
        ttk.Button(r2, text="Read RTC", width=10, command=self.refresh_rtc_display).pack(side=tk.LEFT, padx=1)
        ttk.Button(r2, text="Set Preset", width=10, command=self.preset_rtc_time).pack(side=tk.LEFT, padx=1)

        # Sync Row
        r3 = ttk.Frame(t_box); r3.pack(fill=tk.X, pady=2)
        ttk.Button(r3, text="Sys -> RTC", command=self.sys_to_rtc).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(r3, text="RTC -> Sys", command=self.rtc_to_sys).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        # Manual Set
        r4 = ttk.Frame(t_box); r4.pack(fill=tk.X)
        ttk.Label(r4, text="Man:").pack(side=tk.LEFT)
        self.rtc_entry = ttk.Entry(r4); self.rtc_entry.insert(0, "2025-12-24 13:45:30"); self.rtc_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(r4, text="Set RTC", width=8, command=lambda: self.set_rtc_manual(self.rtc_entry.get())).pack(side=tk.LEFT)

        # ---- TAB 2: CONNECTIVITY ----
        tab2 = ttk.Frame(self.nb, padding=5)
        self.nb.add(tab2, text=" CONNECTIVITY ")
        
        c_row = ttk.Frame(tab2); c_row.pack(fill=tk.X, pady=2)
        beep_f = ttk.LabelFrame(c_row, text=" Beeper ", padding=3); beep_f.pack(side=tk.LEFT, padx=3)
        ttk.Button(beep_f, textvariable=self.beeper_state, command=self.toggle_beeper, width=8).pack()
        pwr_f = ttk.LabelFrame(c_row, text=" Power Out ", padding=3); pwr_f.pack(side=tk.LEFT, padx=3)
        ttk.Button(pwr_f, text="PWR 1", command=self.toggle_pwr1, width=7).pack(side=tk.LEFT, padx=1)
        ttk.Button(pwr_f, text="PWR 2", command=self.toggle_pwr2, width=7).pack(side=tk.LEFT, padx=1)

        m_f = ttk.LabelFrame(tab2, text=" Modem Info ", padding=5); m_f.pack(fill=tk.X, pady=2)
        for r, (l, v) in enumerate([("Detect:", self.modem_status), ("Ver:", self.m2_software), ("IMEI:", self.m2_imei)]):
            ttk.Label(m_f, text=l).grid(row=r, column=0, sticky="w"); ttk.Label(m_f, textvariable=v, style='Value.TLabel' if r==0 else 'TLabel').grid(row=r, column=1, padx=10, sticky="w")

        btn_f = ttk.Frame(tab2); btn_f.pack(fill=tk.X, pady=2)
        for t, c in [("Wiring", lambda: self.run_modem_cmd(["--human","--electrical"])), ("LTE", lambda: self.run_modem_cmd(["--human"])), ("Dl Test", lambda: self.run_modem_cmd(["python3",DOWNLOAD_SCRIPT]))]:
            ttk.Button(btn_f, text=t, command=c).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)

        w_f = ttk.LabelFrame(tab2, text=" WLAN ", padding=5); w_f.pack(fill=tk.X, pady=2)
        ttk.Button(w_f, text="Connect", command=lambda: self.log("Request: Keyboard")).pack(side=tk.LEFT)
        ttk.Label(w_f, textvariable=self.wlan_ssid, relief="sunken", width=20).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # ---- TAB 3: ADVANCED ----
        tab3 = ttk.Frame(self.nb, padding=1)
        self.nb.add(tab3, text=" ADVANCED ")
        nb_g = ttk.Notebook(tab3); nb_g.pack(fill=tk.BOTH, expand=True)
        self.gpio_elements = {}
        for title, pins in [("LOWER", range(2, 15)), ("UPPER", range(15, 28))]:
            tab_g = ttk.Frame(nb_g, padding=1); nb_g.add(tab_g, text=title)
            for i, p in enumerate(pins):
                r, c = divmod(i, 2); f = ttk.Frame(tab_g, relief="groove", borderwidth=1); f.grid(row=r, column=c, padx=1, pady=0, sticky="ew")
                led = tk.Canvas(f, width=10, height=10, highlightthickness=0); led.pack(side=tk.LEFT, padx=2)
                obj = led.create_oval(2, 2, 8, 8, fill="gray")
                lbl = ttk.Label(f, text=f"P{p}", font=('Arial', 8)); lbl.pack(side=tk.LEFT)
                bc = ttk.Frame(f); bc.pack(side=tk.RIGHT)
                for t, m, l in [("I","IN",None), ("O","OUT",None), ("H",None,1), ("L",None,0)]:
                    cmd = (lambda x=p,mode=m: self.set_gpio_mode(x,mode)) if m else (lambda x=p,lvl=l: self.set_gpio_level(x,lvl))
                    ttk.Button(bc, text=t, width=2, command=cmd).pack(side=tk.LEFT, padx=0)
                self.gpio_elements[p] = {"led": led, "obj": obj}

    # --- LOGIC (From app.py) ---
    def log(self, m):
        t = datetime.datetime.now().strftime("%H:%M:%S"); self.error_text.configure(state='normal'); self.error_text.insert(tk.END, f"{t}: {m}\n"); self.error_text.see(tk.END); self.error_text.configure(state='disabled')
    def run_raw(self, c):
        self.log(f"> {c}")
        try:
            res = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=10)
            if res.stdout: self.log(res.stdout.strip())
            return res.returncode == 0
        except Exception as e:
            self.log(f"Err: {e}")
            return False
    def refresh_rtc_display(self):
        try:
            val = subprocess.check_output("sudo hwclock --show -f /dev/rtc", shell=True, text=True).split('.')[0].strip()
            self.rtc_time.set(val)
            self.log(f"RTC: {val}")
        except:
            self.rtc_time.set("Err")
    def sync_sys_prefix(self):
        def _t():
            try:
                r = urllib.request.urlopen("http://worldtimeapi.org/api/timezone/Etc/UTC", timeout=5); dt = json.load(r)["utc_datetime"].split(".")[0].replace("T", " ")
                if self.run_raw(f"sudo date -s '{dt}'"): self.run_raw("sudo hwclock --systohc -f /dev/rtc"); self.log(f"NTP: {dt}"); self.refresh_rtc_display()
            except Exception as e: self.log(f"Sync Fail: {e}")
        threading.Thread(target=_t, daemon=True).start()
    def sys_to_rtc(self): self.run_raw("sudo hwclock --systohc -f /dev/rtc"); self.refresh_rtc_display()
    def rtc_to_sys(self): self.run_raw("sudo hwclock --hctosys -f /dev/rtc"); self.refresh_rtc_display()
    def preset_rtc_time(self): self.run_raw('sudo hwclock --set --date="2025-12-24 13:45:30" -f /dev/rtc'); self.refresh_rtc_display()
    def preset_sys_time(self): self.run_raw("sudo date -s '2011-01-01 11:11:11'"); self.log("Set SysTime: 2011")
    def set_rtc_manual(self, t): self.run_raw(f'sudo hwclock --set --date="{t}" -f /dev/rtc'); self.refresh_rtc_display()
    def toggle_beeper(self):
        s = ["off", "400Hz", "1kHz"]; n = s[(s.index(self.beeper_state.get())+1)%3]; self.beeper_state.set(n)
        if self._pi_pwm: self._pi_pwm.stop(); self._pi_pwm = None
        if self._beep_proc: self._beep_proc.kill(); self._beep_proc = None
        subprocess.run("killall -q speaker-test", shell=True)
        if n != "off":
            f = 400 if n == "400Hz" else 1000
            if IS_PI: GPIO.setup(13, GPIO.OUT); self._pi_pwm = GPIO.PWM(13, f); self._pi_pwm.start(50)
            else: self._beep_proc = subprocess.Popen(f"speaker-test -t sine -f {f} -c 2", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.log(f"Beeper: {n}")
    def toggle_pwr1(self): self.pwr1.set(not self.pwr1.get()); GPIO.setup(26, GPIO.OUT); GPIO.output(26, self.pwr1.get()); self.log("PWR 1 toggle")
    def toggle_pwr2(self): self.pwr2.set(not self.pwr2.get()); GPIO.setup(22, GPIO.OUT); GPIO.output(22, self.pwr2.get()); self.log("PWR 2 toggle")
    def set_gpio_mode(self, p, m): GPIO.setup(p, GPIO.IN if m=="IN" else GPIO.OUT); self.log(f"P{p} mode: {m}")
    def set_gpio_level(self, p, l): 
        try: GPIO.output(p, l); self.log(f"P{p} level: {l}")
        except: self.log(f"P{p} fail")
    def start_loops(self):
        def _time():
            while True:
                self.sys_time.set(datetime.datetime.now().strftime("%H:%M:%S"))
                try: v = subprocess.check_output("sudo hwclock --show -f /dev/rtc", shell=True, text=True).strip().split('.')[0]; self.rtc_time.set(v)
                except: self.rtc_time.set("Err")
                time.sleep(1)
        threading.Thread(target=_time, daemon=True).start()
        def _temp():
            while True:
                if IS_PI:
                    t = readTemps.read_all_temps() or [None, None, None]; self.temp_pi.set(f"{t[0]:.1f}" if t[0] else "Err"); self.temp_smps.set(f"{t[1]:.1f}" if t[1] else "Err"); self.temp_ambient.set(f"{t[2]:.1f}" if t[2] else "Err")
                else: self.temp_pi.set("35.7"); self.temp_smps.set("42.2"); self.temp_ambient.set("22.4")
                time.sleep(2)
        threading.Thread(target=_temp, daemon=True).start()
        def _poll():
            while True:
                for p, el in self.gpio_elements.items():
                    try: c = "#0f0" if GPIO.input(p) else "#f00"; el["led"].itemconfig(el["obj"], fill=c)
                    except: pass
                time.sleep(0.5)
        threading.Thread(target=_poll, daemon=True).start()

    def run_modem_cmd(self, args): threading.Thread(target=lambda: self.log(f"Action: {args}"), daemon=True).start()
    def on_closing(self):
        if self._pi_pwm: self._pi_pwm.stop()
        if self._beep_proc: self._beep_proc.kill()
        GPIO.cleanup(); self.root.destroy()
    def run(self): self.root.mainloop()

if __name__ == "__main__":
    ControlPanelV4().run()
