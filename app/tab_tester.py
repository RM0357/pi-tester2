import tkinter as tk
from tkinter import ttk

class TesterTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=5)
        self.app = app
        self.setup_ui()

    def setup_ui(self):
        tester_inner = ttk.Frame(self)
        tester_inner.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(tester_inner, text="Connection Tester Tools", font=("Arial", 11, "bold")).pack(pady=5)
        
        btns_tester = [
            ("Init Tester Session", self.app.init_tester),
            ("Check Ethernet", self.app.tester_check_eth),
            ("Check WLAN", self.app.tester_check_wlan),
            ("Modem Diag (Full)", self.app.tester_modem_diag),
            ("Modem Check Mode", self.app.tester_modem_check_mode),
            ("Start PPP Daemon", self.app.tester_ppp_on),
            ("Stop PPP Daemon", self.app.tester_ppp_off),
        ]
        
        for txt, cmd in btns_tester:
            ttk.Button(tester_inner, text=txt, command=cmd, style='Action.TButton').pack(fill=tk.X, pady=2, padx=10)
