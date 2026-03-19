import sys
import time

def p(m):
    print(m, flush=True)

if "-detect" in sys.argv:
    p("Modem detected (Simulated)")
else:
    p("connection manager.py started")
    time.sleep(1)
    p("Status: Powering on M.2 Slot...")
    time.sleep(1)
    p("connection is ok")
