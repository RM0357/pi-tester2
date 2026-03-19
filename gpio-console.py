# gpio-console.py
# Run with: sudo python3 gpio-console.py
# Shows and controls ALL exported GPIOs from /sys/class/gpio

import os
import sys

# ----------------------------------------------------------------------
# Get all exported GPIO numbers (skip gpiochip*)
# ----------------------------------------------------------------------
def get_all_gpios() -> list[int]:
    path = "/sys/class/gpio"
    if not os.path.exists(path):
        return []
    dirs = [d for d in os.listdir(path) if d.startswith("gpio") and not d.startswith("gpiochip")]
    try:
        return sorted(int(d[4:]) for d in dirs)
    except ValueError:
        return []

# ----------------------------------------------------------------------
# GPIO operations
# ----------------------------------------------------------------------
def export(pin: int):
    if pin not in get_all_gpios():
        os.system(f"echo {pin} > /sys/class/gpio/export")

def unexport(pin: int):
    os.system(f"echo {pin} > /sys/class/gpio/unexport")

def set_direction(pin: int, direction: str):
    export(pin)
    os.system(f"echo {direction} > /sys/class/gpio/gpio{pin}/direction")

def set_value(pin: int, value: str):
    export(pin)
    os.system(f"echo {value} > /sys/class/gpio/gpio{pin}/value")

def read_value(pin: int) -> str:
    try:
        with open(f"/sys/class/gpio/gpio{pin}/value") as f:
            return "HIGH" if f.read().strip() == "1" else "LOW"
    except:
        return "ERR"

def read_direction(pin: int) -> str:
    try:
        with open(f"/sys/class/gpio/gpio{pin}/direction") as f:
            return f.read().strip()
    except:
        return "ERR"

# ----------------------------------------------------------------------
# Display
# ----------------------------------------------------------------------
def show():
    pins = get_all_gpios()
    if not pins:
        print("No GPIOs exported.")
        return
    print(f"{'PIN':<6} {'STATE':<6} {'MODE':<6}")
    print("-" * 22)
    for pin in pins:
        state = read_value(pin)
        mode = read_direction(pin)
        print(f"{pin:<6} {state:<6} {mode:<6}")

# ----------------------------------------------------------------------
# Interactive menu
# ----------------------------------------------------------------------
def interactive():
    print("Raspberry Pi GPIO Control (all exported pins)")
    print("Commands: show | export <n> | unexport <n> | in <n> | out <n> | high <n> | low <n> | read <n> | exit")
    show()
    while True:
        try:
            cmd = input("\n> ").strip().lower().split()
            if not cmd:
                continue
            action = cmd[0]

            if action == "exit":
                break
            elif action == "show":
                show()
            elif len(cmd) < 2:
                print("Missing pin number")
                continue
            else:
                try:
                    pin = int(cmd[1])
                except ValueError:
                    print("Invalid pin number")
                    continue

                if action == "export":
                    export(pin); show()
                elif action == "unexport":
                    unexport(pin); show()
                elif action == "in":
                    set_direction(pin, "in"); show()
                elif action == "out":
                    set_direction(pin, "out"); show()
                elif action == "high":
                    set_value(pin, "1"); show()
                elif action == "low":
                    set_value(pin, "0"); show()
                elif action == "read":
                    print(f"Pin {pin}: {read_value(pin)} ({read_direction(pin)})")
                else:
                    print("Unknown command")
        except (KeyboardInterrupt, EOFError):
            print("\nExiting...")
            break

    print("Cleaning up...")
    for p in get_all_gpios():
        unexport(p)

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
if __name__ == "__main__":
    if os.getuid() != 0:
        print("Error: This script requires sudo")
        sys.exit(1)
    interactive()
