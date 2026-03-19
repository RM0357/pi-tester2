import tkinter as tk
from tkinter import scrolledtext
import os

# Example GPIO pins (kernel numbers, adjust for your setup)
GPIO_PINS = [524, 525, 526]  

# Initialize pins (export and set as output)
for pin in GPIO_PINS:
    try:
        os.system(f"echo {pin} | sudo tee /sys/class/gpio/export > /dev/null")
        os.system(f"echo out | sudo tee /sys/class/gpio/gpio{pin}/direction > /dev/null")
    except Exception as e:
        print(f"Error initializing GPIO {pin}: {e}")

def read_pin(pin):
    """Read GPIO value"""
    try:
        with open(f"/sys/class/gpio/gpio{pin}/value", "r") as f:
            return f.read().strip()
    except:
        return "err"

def set_pin(pin, value):
    """Set GPIO value and log it"""
    try:
        os.system(f"echo {value} | sudo tee /sys/class/gpio/gpio{pin}/value > /dev/null")
        status = "HIGH" if value=="1" else "LOW"
        log(f"Pin {pin} set to {status}")
    except Exception as e:
        log(f"Error setting pin {pin}: {e}")

def log(message):
    """Append message to log window"""
    info_window.configure(state='normal')
    info_window.insert(tk.END, message + "\n")
    info_window.see(tk.END)
    info_window.configure(state='disabled')

# Tkinter GUI
root = tk.Tk()
root.title("GPIO Control Panel")

# Frame for buttons
button_frame = tk.Frame(root)
button_frame.pack(padx=10, pady=10)

for pin in GPIO_PINS:
    frame = tk.Frame(button_frame)
    frame.pack(pady=5)
    
    label = tk.Label(frame, text=f"GPIO {pin}", width=10)
    label.pack(side=tk.LEFT)
    
    btn_high = tk.Button(frame, text="HIGH", command=lambda p=pin: set_pin(p, "1"))
    btn_high.pack(side=tk.LEFT, padx=5)
    
    btn_low = tk.Button(frame, text="LOW", command=lambda p=pin: set_pin(p, "0"))
    btn_low.pack(side=tk.LEFT, padx=5)
    
    btn_read = tk.Button(frame, text="Read", command=lambda p=pin: log(f"Pin {p} value is {read_pin(p)}"))
    btn_read.pack(side=tk.LEFT, padx=5)

# Info window
info_window = scrolledtext.ScrolledText(root, width=50, height=10, state='disabled')
info_window.pack(padx=10, pady=10)

root.mainloop()
