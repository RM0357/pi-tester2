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

class ControlPanelV4:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pi Tester Control Panel")
        self.root.geometry("800x480")
        self.root.resizable(False, False)
        self.root.configure(bg='#e1e1e1')

        # Concurrency Protection
        self.clock_lock = threading.Lock()
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

        # Style Configuration
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TNotebook.Tab', padding=[10, 2], font=('Arial', 9, 'bold'))
        self.style.configure('Value.TLabel', font=('Courier', 10, 'bold'), foreground='#0099ff')
        self.style.configure('Clock.TLabel', font=('Courier', 11, 'bold'), foreground='#0099ff')
        self.style.configure('GPIO.TButton', font=('Arial', 8), width=2, padding=1)

        self.setup_ui()
        self.start_loops()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_ui(self):
        # 1. 50% LOG SIDEBAR (400px Wide)
        self.sidebar_w = 400
        self.log_frame = tk.Frame(self.root, width=self.sidebar_w, bg="#1a1a1a")
        self.log_frame.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_frame.pack_propagate(False)
        
        tk.Label(self.log_frame, text=" SYSTEM LOGS & OUTPUT ", fg="white", bg="#333", font=('Arial', 10, 'bold')).pack(fill=tk.X)
        self.error_text = scrolledtext.ScrolledText(self.log_frame, bg="#000", fg="#00ff41", font=("Courier", 8), borderwidth=0)
        self.error_text.pack(fill=tk.BOTH, expand=True)

        # 2. 50% MAIN NOTEBOOK
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ---- TAB 1: DASHBOARD ----
        tab1 = ttk.Frame(self.nb, padding=2)
        self.nb.add(tab1, text=" DASHBOARD ")
        
        # Combined Top Bar
        top_bar = ttk.Frame(tab1, relief="groove", padding=2)
        top_bar.pack(fill=tk.X, pady=1)
        ttk.Label(top_bar, text="NFC:", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=2)
        ttk.Label(top_bar, textvariable=self.nfc_id, font=("Courier", 9, "bold"), foreground="blue").pack(side=tk.LEFT, padx=(0, 10))
        for lbl, var in [("Pi:", self.temp_pi), ("PSU:", self.temp_smps), ("Amb:", self.temp_ambient)]:
            ttk.Label(top_bar, text=lbl, font=("Arial", 8)).pack(side=tk.LEFT, padx=(5,0))
            ttk.Label(top_bar, textvariable=var, style='Value.TLabel').pack(side=tk.LEFT, padx=(0,5))

        # Time Group
        t_box = ttk.LabelFrame(tab1, text=" Time Control (Real Time) ", padding=3)
        t_box.pack(fill=tk.BOTH, expand=True, pady=1)
        
        # Clocks
        s_row = ttk.Frame(t_box); s_row.pack(fill=tk.X)
        ttk.Label(s_row, text="SYS:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(s_row, textvariable=self.sys_time, style='Clock.TLabel').pack(side=tk.LEFT, padx=5)
        
        b_row1 = ttk.Frame(t_box); b_row1.pack(fill=tk.X, pady=1)
        ttk.Button(b_row1, text="Preset 2011", command=self.preset_sys_time).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(b_row1, text="SysPrefix", command=self.sync_sys_prefix).pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        r_row = ttk.Frame(t_box); r_row.pack(fill=tk.X, pady=(2,0))
        ttk.Label(r_row, text="RTC:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(r_row, textvariable=self.rtc_time, style='Clock.TLabel').pack(side=tk.LEFT, padx=5)
        
        b_row2 = ttk.Frame(t_box); b_row2.pack(fill=tk.X, pady=1)
        ttk.Button(b_row2, text="Read RTC", command=self.refresh_rtc_display).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(b_row2, text="Set Preset", command=self.preset_rtc_time).pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        b_row3 = ttk.Frame(t_box); b_row3.pack(fill=tk.X, pady=1)
        ttk.Button(b_row3, text="Sys->RTC", command=self.sys_to_rtc).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(b_row3, text="RTC->Sys", command=self.rtc_to_sys).pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        man_f = ttk.Frame(t_box); man_f.pack(fill=tk.X, pady=2)
        ttk.Label(man_f, text="Set Manual:", font=("Arial", 8)).pack(anchor="w")
        self.rtc_entry = ttk.Entry(man_f, font=("Courier", 10))
        self.rtc_entry.insert(0, "2025-12-24 13:45:30")
        self.rtc_entry.pack(fill=tk.X, pady=1)
        ttk.Button(man_f, text="SET HARDWARE CLOCK NOW", command=lambda: self.set_rtc_manual(self.rtc_entry.get())).pack(fill=tk.X)

        # ---- TAB 2: CONNECT ----
        tab2 = ttk.Frame(self.nb, padding=2)
        self.nb.add(tab2, text=" CONNECT ")
        for name, var, cmd in [("Beeper", self.beeper_state, self.toggle_beeper), ("PWR 1", None, self.toggle_pwr1), ("PWR 2", None, self.toggle_pwr2)]:
            f = ttk.Frame(tab2); f.pack(fill=tk.X, pady=1)
            t = var if var else name
            ttk.Button(f, textvariable=t if var else None, text=None if var else name, command=cmd).pack(fill=tk.X)
        
        m_f = ttk.LabelFrame(tab2, text=" Modem ", padding=2); m_f.pack(fill=tk.X, pady=1)
        for l, v in [("Stat:", self.modem_status), ("Ver:", self.m2_software), ("IMEI:", self.m2_imei)]:
            f = ttk.Frame(m_f); f.pack(fill=tk.X)
            ttk.Label(f, text=l, font=("Arial",8)).pack(side=tk.LEFT)
            ttk.Label(f, textvariable=v, style='Value.TLabel' if v==self.modem_status else 'TLabel').pack(side=tk.LEFT)
        
        for t, c in [("Wiring Check", lambda: self.run_modem_cmd(["--human","--electrical"])), ("LTE Check", lambda: self.run_modem_cmd(["--human"])), ("Test Download", lambda: self.run_modem_cmd(["python3","download.py"]))]:
            ttk.Button(tab2, text=t, command=c).pack(fill=tk.X, pady=1)
        
        w_f = ttk.LabelFrame(tab2, text=" WLAN ", padding=2); w_f.pack(fill=tk.X, pady=1)
        ttk.Label(w_f, textvariable=self.wlan_ssid, relief="sunken", font=("Arial", 8)).pack(fill=tk.X)
        ttk.Button(w_f, text="Connect WLAN", command=lambda: self.log("Request: Kbd")).pack(fill=tk.X)

        # ---- TAB 3: ADVANCED ----
        tab3 = ttk.Frame(self.nb, padding=1)
        self.nb.add(tab3, text=" ADV ")
        nb_g = ttk.Notebook(tab3); nb_g.pack(fill=tk.BOTH, expand=True)
        self.gpio_elements = {}
        for title, pins in [("2-14", range(2, 15)), ("15-27", range(15, 28))]:
            tab_g = ttk.Frame(nb_g, padding=2); nb_g.add(tab_g, text=title)
            for i, p in enumerate(pins):
                r, c = divmod(i, 2)
                f = ttk.Frame(tab_g, relief="groove", borderwidth=1); f.grid(row=r, column=c, padx=1, pady=1, sticky="ew")
                tab_g.columnconfigure(c, weight=1)
                
                ind_f = ttk.Frame(f); ind_f.pack(side=tk.LEFT, padx=1)
                led = tk.Canvas(ind_f, width=10, height=10, highlightthickness=0); led.pack(side=tk.LEFT, padx=1)
                obj = led.create_oval(2, 2, 8, 8, fill="gray")
                ttk.Label(ind_f, text=f"P{p}", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
                
                btn_f = ttk.Frame(f); btn_f.pack(side=tk.RIGHT)
                for txt, mode, lvl in [("I","IN",None), ("O","OUT",None), ("H",None,1), ("L",None,0)]:
                    if mode:
                        cmd_func = lambda x=p,m=mode: self.set_gpio_mode(x,m)
                    else:
                        cmd_func = lambda x=p,v=lvl: self.set_gpio_level(x,v)
                    ttk.Button(btn_f, text=txt, style='GPIO.TButton', command=cmd_func).pack(side=tk.LEFT, padx=0)
                
                self.gpio_elements[p] = {"led": led, "obj": obj}

    def log(self, text):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        self.error_text.configure(state='normal')
        self.error_text.insert(tk.END, f"{t}: {text}\n")
        self.error_text.see(tk.END)
        self.error_text.configure(state='disabled')

    def run_raw(self, cmd):
        self.is_busy = True
        self.log(f"> {cmd}")
        with self.clock_lock:
            try:
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
                if res.stdout: self.log(res.stdout.strip())
                success = (res.returncode == 0)
            except Exception as e:
                self.log(f"Err: {e}"); success = False
        self.is_busy = False
        self.refresh_rtc_display()
        return success

    def refresh_rtc_display(self):
        with self.clock_lock:
            try:
                v = subprocess.check_output("sudo hwclock --show -f /dev/rtc", shell=True, text=True).split('.')[0].strip()
                self.rtc_time.set(v)
            except:
                self.rtc_time.set("Err")

    def sync_sys_prefix(self):
        def _task():
            try:
                r = urllib.request.urlopen("http://worldtimeapi.org/api/timezone/Etc/UTC", timeout=5)
                dt = json.load(r)["utc_datetime"].split(".")[0].replace("T", " ")
                if self.run_raw(f"sudo date -s '{dt}'"):
                    self.run_raw("sudo hwclock --systohc -f /dev/rtc")
                    self.log(f"Net Sync Done: {dt}")
            except Exception as e: self.log(f"Sync Fail: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def sys_to_rtc(self): self.run_raw("sudo hwclock --systohc -f /dev/rtc")
    def rtc_to_sys(self): self.run_raw("sudo hwclock --hctosys -f /dev/rtc")
    def preset_rtc_time(self): self.run_raw('sudo hwclock --set --date="2025-12-24 13:45:30" -f /dev/rtc')
    def preset_sys_time(self): self.run_raw("sudo date -s '2011-01-01 11:11:11'")
    def set_rtc_manual(self, t): self.run_raw(f'sudo hwclock --set --date="{t}" -f /dev/rtc')

    def toggle_beeper(self):
        ops = ["off", "400Hz", "1kHz"]
        nxt = ops[(ops.index(self.beeper_state.get()) + 1) % 3]
        self.beeper_state.set(nxt)
        if self._pi_pwm: self._pi_pwm.stop(); self._pi_pwm = None
        if self._beep_proc: self._beep_proc.kill(); self._beep_proc = None
        subprocess.run("killall -q speaker-test", shell=True)
        if nxt != "off":
            f = 400 if nxt == "400Hz" else 1000
            if IS_PI:
                GPIO.setup(13, GPIO.OUT); self._pi_pwm = GPIO.PWM(13, f); self._pi_pwm.start(50)
            else:
                self._beep_proc = subprocess.Popen(f"speaker-test -t sine -f {f} -c 2", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.log(f"Beeper: {nxt}")

    def toggle_pwr1(self):
        self.pwr1.set(not self.pwr1.get()); GPIO.setup(26, GPIO.OUT); GPIO.output(26, self.pwr1.get()); self.log("PWR 1 toggled")
    def toggle_pwr2(self):
        self.pwr2.set(not self.pwr2.get()); GPIO.setup(22, GPIO.OUT); GPIO.output(22, self.pwr2.get()); self.log("PWR 2 toggled")
    def set_gpio_mode(self, p, m):
        GPIO.setup(p, GPIO.IN if m=="IN" else GPIO.OUT); self.log(f"P{p} -> {m}")
    def set_gpio_level(self, p, l):
        try: GPIO.output(p, l); self.log(f"P{p} -> {l}")
        except: self.log(f"Fail P{p}")

    def start_loops(self):
        def _clock_timer():
            while True:
                # Smooth system clock (updates 10 times a second)
                self.sys_time.set(datetime.datetime.now().strftime("%H:%M:%S"))
                
                # Check RTC every 1 second, but only if not busy with a command
                if not self.is_busy:
                    self.refresh_rtc_display()
                time.sleep(1)
        threading.Thread(target=_clock_timer, daemon=True).start()

        def _temp_timer():
            while True:
                if IS_PI:
                    t = readTemps.read_all_temps() or [None,None,None]
                    self.temp_pi.set(f"{t[0]:.1f}" if t[0] else "?")
                    self.temp_smps.set(f"{t[1]:.1f}" if t[1] else "?")
                    self.temp_ambient.set(f"{t[2]:.1f}" if t[2] else "?")
                else: self.temp_pi.set("32.1"); self.temp_smps.set("40.5"); self.temp_ambient.set("20.2")
                time.sleep(2)
        threading.Thread(target=_temp_timer, daemon=True).start()

        def _gpio_poll():
            while True:
                if hasattr(self, 'nb') and self.nb.index("current") == 2:
                    for p, el in self.gpio_elements.items():
                        try:
                            c = "#0f0" if GPIO.input(p) else "#f00"
                            el["led"].itemconfig(el["obj"], fill=c)
                        except: pass
                time.sleep(1)
        threading.Thread(target=_gpio_poll, daemon=True).start()

    def run_modem_cmd(self, args): threading.Thread(target=lambda: self.log(f"Exec: {args}"), daemon=True).start()
    def on_closing(self):
        if self._pi_pwm: self._pi_pwm.stop()
        if self._beep_proc: self._beep_proc.kill()
        GPIO.cleanup(); self.root.destroy()
    def run(self): self.root.mainloop()

if __name__ == "__main__":
    ControlPanelV4().run()
