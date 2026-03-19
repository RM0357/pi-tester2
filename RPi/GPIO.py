# Mock RPi.GPIO
import time

BCM = 11
BOARD = 10
IN = 1
OUT = 0
HIGH = 1
LOW = 0
PUD_UP = 22
PUD_DOWN = 21
PUD_OFF = 20

_states = {} # pin: value
_modes = {}  # pin: mode (IN or OUT)

def setmode(mode): 
    print(f"MOCK GPIO: Mode set to {mode}")

def setwarnings(flag): pass

def setup(pin, mode, pull_up_down=None, initial=LOW):
    _modes[pin] = mode
    if mode == OUT:
        _states[pin] = initial
    else:
        # Default for IN
        _states[pin] = LOW
    m_str = "IN" if mode == IN else "OUT"
    print(f"MOCK GPIO: Pin {pin} setup as {m_str}")

def output(pin, val):
    if _modes.get(pin) == OUT:
        _states[pin] = val
        print(f"MOCK GPIO: Pin {pin} set to {'HIGH' if val else 'LOW'}")
    else:
        print(f"MOCK GPIO: WARNING - Attempted output on pin {pin} set as IN")

def input(pin):
    # Return the current state
    return _states.get(pin, LOW)

def cleanup():
    _states.clear()
    _modes.clear()
    print("MOCK GPIO: Cleanup")

class PWM:
    def __init__(self, pin, freq):
        self.pin = pin
        self.freq = freq
        print(f"MOCK PWM: Initialized on Pin {pin} at {freq}Hz")
    def start(self, duty):
        print(f"MOCK PWM: Started on Pin {self.pin} with {duty}% duty")
    def ChangeDutyCycle(self, duty):
        pass
    def ChangeFrequency(self, freq):
        self.freq = freq
    def stop(self):
        print(f"MOCK PWM: Stopped")
