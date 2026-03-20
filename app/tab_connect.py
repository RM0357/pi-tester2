import tkinter as tk
from tkinter import ttk

class ConnectTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=2)
        self.app = app
        self.setup_ui()

    def setup_ui(self):
        for name, var, cmd in [("Beeper", self.app.beeper_state, self.app.toggle_beeper), 
                               ("PWR 1", None, self.app.toggle_pwr1), 
                               ("PWR 2", None, self.app.toggle_pwr2)]:
            f = ttk.Frame(self)
            f.pack(fill=tk.X, pady=1)
            t = var if var else name
            ttk.Button(f, textvariable=t if var else None, text=None if var else name, command=cmd).pack(fill=tk.X)
            
        m_f = ttk.LabelFrame(self, text=" Modem Info ", padding=2)
        m_f.pack(fill=tk.X, pady=1)
        
        for l, v in [("Stat:", self.app.modem_status), ("Ver:", self.app.m2_software), ("IMEI:", self.app.m2_imei)]:
            f = ttk.Frame(m_f)
            f.pack(fill=tk.X)
            ttk.Label(f, text=l, font=("Arial",8)).pack(side=tk.LEFT)
            ttk.Label(f, textvariable=v, style='Value.TLabel' if v==self.app.modem_status else 'TLabel').pack(side=tk.LEFT)
            
        for t, c in [("Wiring Check", lambda: self.app.run_modem_cmd(["--human","--electrical"])), 
                     ("LTE Check", lambda: self.app.run_modem_cmd(["--human"])), 
                     ("Test Download", lambda: self.app.run_modem_cmd(["python3","download.py"]))]:
            ttk.Button(self, text=t, command=c).pack(fill=tk.X, pady=1)
            
        w_f = ttk.LabelFrame(self, text=" WLAN ", padding=2)
        w_f.pack(fill=tk.X, pady=1)
        ttk.Label(w_f, textvariable=self.app.wlan_ssid, relief="sunken", font=("Arial", 8)).pack(fill=tk.X)
        ttk.Button(w_f, text="Connect WLAN", command=lambda: self.app.log("Request: Kbd")).pack(fill=tk.X)
