import tkinter as tk
from tkinter import ttk

class DashboardTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=2)
        self.app = app
        self.setup_ui()

    def setup_ui(self):
        top_bar = ttk.Frame(self, relief="groove", padding=2)
        top_bar.pack(fill=tk.X, pady=1)
        ttk.Label(top_bar, text="NFC:", font=("Arial", 8, "bold")).pack(side=tk.LEFT, padx=1)
        ttk.Label(top_bar, textvariable=self.app.nfc_id, font=("Courier", 9, "bold"), foreground="blue").pack(side=tk.LEFT, padx=(0, 5))
        for lbl, var in [("Pi:", self.app.temp_pi), ("PSU:", self.app.temp_smps), ("Amb:", self.app.temp_ambient)]:
            f_tmp = ttk.Frame(top_bar)
            f_tmp.pack(side=tk.LEFT, padx=1)
            ttk.Label(f_tmp, text=lbl, font=("Arial", 8)).pack(side=tk.LEFT)
            ttk.Label(f_tmp, textvariable=var, style='Value.TLabel').pack(side=tk.LEFT, padx=1)

        t_box = ttk.LabelFrame(self, text=" Time Control ", padding=3)
        t_box.pack(fill=tk.BOTH, expand=True, pady=1)
        
        sr = ttk.Frame(t_box)
        sr.pack(fill=tk.X)
        ttk.Label(sr, text="SYS:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(sr, textvariable=self.app.sys_time, style='Clock.TLabel').pack(side=tk.LEFT, padx=3)
        
        br1 = ttk.Frame(t_box)
        br1.pack(fill=tk.X, pady=1)
        ttk.Button(br1, text="Preset 2011", command=lambda: self.app.run_bg("sudo date -s '2011-01-01 11:11:11'")).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(br1, text="SysPrefix", command=self.app.sync_sys_prefix).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        
        rr = ttk.Frame(t_box)
        rr.pack(fill=tk.X, pady=(2,0))
        ttk.Label(rr, text="RTC:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        ttk.Label(rr, textvariable=self.app.rtc_time, style='Clock.TLabel').pack(side=tk.LEFT, padx=3)
        
        br2 = ttk.Frame(t_box)
        br2.pack(fill=tk.X, pady=1)
        ttk.Button(br2, text="Read RTC", command=self.app.refresh_rtc_btn).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(br2, text="Set Preset", command=lambda: self.app.run_bg('sudo hwclock --set --date="2025-12-24 13:45:30" -f /dev/rtc', self.app.refresh_rtc_display)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        
        br3 = ttk.Frame(t_box)
        br3.pack(fill=tk.X, pady=1)
        ttk.Button(br3, text="Sys->RTC", command=lambda: self.app.run_bg("sudo hwclock --systohc -f /dev/rtc", self.app.refresh_rtc_display)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        ttk.Button(br3, text="RTC->Sys", command=lambda: self.app.run_bg("sudo hwclock --hctosys -f /dev/rtc", self.app.refresh_rtc_display)).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=1)
        
        man_f = ttk.Frame(t_box)
        man_f.pack(fill=tk.X, pady=1)
        ttk.Label(man_f, text="Set Manual:", font=("Arial", 8)).pack(anchor="w")
        self.app.rtc_entry = ttk.Entry(man_f, font=("Courier", 10))
        self.app.rtc_entry.insert(0, "2025-12-24 13:45:30")
        self.app.rtc_entry.pack(fill=tk.X, pady=1)
        ttk.Button(man_f, text="SET HARDWARE CLOCK", command=lambda: self.app.run_bg(f'sudo hwclock --set --date="{self.app.rtc_entry.get()}" -f /dev/rtc', self.app.refresh_rtc_display)).pack(fill=tk.X)
