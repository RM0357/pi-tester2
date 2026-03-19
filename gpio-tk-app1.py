#!/usr/bin/env python3
import tkinter as tk
from tkinter import messagebox
import gpiod
import os
import threading
import time

# --------------------- Config ---------------------
CHIP_NAME = 'gpiochip0'
PINS = [20, 22, 23]      # Your pins - change if needed
RESERVED = {0,1,2,3,27,28,44,45}

PHYSICAL = {
    20: 38, 22: 15, 23: 16, 18: 12, 16: 36, 24: 18, 25: 22, 26: 37,
    12: 32, 13: 33, 19: 35, 21: 40, 5: 29, 6: 31,
}
# --------------------------------------------------

class GPIOApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RPi GPIO Control - LIVE PIGPIO SYNC")
        self.root.geometry("500x450")
        self.root.configure(bg="#1e1e1e")

        self.chip = gpiod.Chip(CHIP_NAME)
        self.lines = {}
        self.current_val = {}
        self.buttons = {}
        self.event_threads = {}

        # Header
        tk.Label(root, text="Works with pigs/pigpio!\nLeft=HIGH | Right=LOW | Double=READ",
                 fg="#00ff00", bg="#1e1e1e", font=("Arial", 12, "bold")).pack(pady=20)

        frame = tk.Frame(root, bg="#1e1e1e")
        frame.pack(expand=True)

        row, col = 0, 0
        for pin in PINS:
            if pin in RESERVED:
                continue
            phys = PHYSICAL.get(pin, "??")
            btn = tk.Button(frame,
                            text=f"GPIO {pin}\nPhys {phys}\n???",
                            width=14, height=5,
                            font=("Arial", 11, "bold"),
                            relief="raised", bd=5,
                            bg="#666666", fg="white")
            btn.grid(row=row, column=col, padx=15, pady=15)

            btn.bind("<Button-1>", lambda e, p=pin: self.write_pin(p, 1))
            btn.bind("<Button-3>", lambda e, p=pin: self.write_pin(p, 0))
            btn.bind("<Double-Button-1>", lambda e, p=pin: self.read_pin(p))

            self.buttons[pin] = btn
            self.update_button(pin, None)

            col += 1
            if col > 2:
                col = 0
                row += 1

        # Start event monitoring threads
        for pin in PINS:
            if pin not in RESERVED:
                threading.Thread(target=self.monitor_pin, args=(pin,), daemon=True).start()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def get_line(self, pin):
        if pin not in self.lines:
            self.lines[pin] = self.chip.get_line(pin)
        return self.lines[pin]

    def write_pin(self, pin, value):
        try:
            line = self.get_line(pin)
            line.request(consumer="gpio-tk", type=gpiod.LINE_REQ_DIR_OUT, default_val=value)
            line.set_value(value)
            self.current_val[pin] = value
            self.update_button(pin, value)
        except Exception as e:
            messagebox.showerror("Write Error", f"GPIO {pin}:\n{e}\n\nIs pigpiod running? Try: sudo pigpiod")

    def read_pin(self, pin):
        try:
            line = self.get_line(pin)
            line.request(consumer="gpio-tk", type=gpiod.LINE_REQ_DIR_IN)
            val = line.get_value()
            messagebox.showinfo("Read", f"GPIO {pin} = {'HIGH' if val else 'LOW'}")
            self.current_val[pin] = val
            self.update_button(pin, val)
        except Exception as e:
            messagebox.showerror("Error", f"{e}")

    def update_button(self, pin, value):
        btn = self.buttons[pin]
        phys = PHYSICAL.get(pin, "??")
        if value is None:
            color, status = "#666666", "???"
        elif value == 1:
            color, status = "#00ff00", "HIGH"
        else:
            color, status = "#ff0055", "LOW"
        btn.config(bg=color, text=f"GPIO {pin}\nPhys {phys}\n{status}")

    def monitor_pin(self, pin):
        """Background thread: watch for external changes (pigs, wiring, etc.)"""
        line = self.get_line(pin)
        while True:
            try:
                # Request with event monitoring (both edges)
                req = line.request(consumer="gpio-tk-monitor",
                                   type=gpiod.LINE_REQ_EV_BOTH_EDGES)
                while True:
                    # Wait for event (timeout 1s to allow thread exit)
                    events = req.wait_edge_events(timeout=1.0)
                    if events:
                        for event in req.read_edge_events():
                            val = event.line_value
                            if self.current_val.get(pin) != val:
                                self.current_val[pin] = val
                                self.root.after(0, lambda p=pin, v=val: self.update_button(p, v))
                    # Small sleep to prevent 100% CPU
                    time.sleep(0.01)
            except Exception as e:
                # Line busy? Re-try after delay
                time.sleep(2)

    def on_close(self):
        for line in self.lines.values():
            try:
                line.release()
            except:
                pass
        self.chip.close()
        self.root.destroy()

# --------------------- Run ---------------------
if __name__ == "__main__":
    if os.getuid() != 0:
        messagebox.showerror("Error", "Run with: sudo python3 gpio-tk-app.py")
        exit(1)
    root = tk.Tk()
    app = GPIOApp(root)
    root.mainloop()
