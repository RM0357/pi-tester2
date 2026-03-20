import tkinter as tk
from tkinter import ttk

# We rely on app/main.py to have correctly handled RPi.GPIO importing.

class AdvancedTab(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, padding=1)
        self.app = app
        self.setup_ui()

    def setup_ui(self):
        nb_g = ttk.Notebook(self)
        nb_g.pack(fill=tk.BOTH, expand=True)
        # We share gpio_elements with the app so its background thread can update it
        self.app.gpio_elements = {}
        
        for title, pins in [("2-14", range(2, 15)), ("15-27", range(15, 28))]:
            tab_g = ttk.Frame(nb_g, padding=1)
            nb_g.add(tab_g, text=title)
            for i, p in enumerate(pins):
                r, c = divmod(i, 2)
                f = ttk.Frame(tab_g, relief="groove", borderwidth=1)
                f.grid(row=r, column=c, padx=1, pady=0, sticky="ew")
                tab_g.columnconfigure(c, weight=1)
                
                ind_f = ttk.Frame(f)
                ind_f.pack(side=tk.LEFT, padx=1)
                led = tk.Canvas(ind_f, width=10, height=10, highlightthickness=0)
                led.pack(side=tk.LEFT, padx=1)
                obj = led.create_oval(2, 2, 8, 8, fill="gray")
                ttk.Label(ind_f, text=f"P{p}", font=("Arial", 8, "bold")).pack(side=tk.LEFT)
                
                btn_f = ttk.Frame(f)
                btn_f.pack(side=tk.RIGHT)
                
                for t, m, l in [("I","IN",None), ("O","OUT",None), ("H",None,1), ("L",None,0)]:
                    cmd_f = (lambda x=p,mode=m: self.app.bg_task(lambda: self.app.set_gpio_mode(x,mode))) if m else (lambda x=p,lvl=l: self.app.bg_task(lambda: self.app.set_gpio_level(x,lvl)))
                    ttk.Button(btn_f, text=t, style='GPIO.TButton', command=cmd_f).pack(side=tk.LEFT, padx=0)
                    
                self.app.gpio_elements[p] = {"led": led, "obj": obj}
