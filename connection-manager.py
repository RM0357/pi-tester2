import sys
import os
import time
from connection import ConnectionManager

def main():
    # Parse basic flags
    human = "--human" in sys.argv
    electrical = "--electrical" in sys.argv
    debug = "--debug" in sys.argv
    at_cmd = None
    if "--at" in sys.argv:
        idx = sys.argv.index("--at")
        if idx + 1 < len(sys.argv):
            at_cmd = sys.argv[idx+1]

    # Create session folder
    now = time.strftime("%y%m%d_%H%M%S")
    folder = f"cli_{now}"
    
    try:
        # Initialize the real ConnectionManager
        # We provide default values to avoid interactive prompts
        cm = ConnectionManager(folder=folder, location="CLI", card="M2", cable="USB", antenna="INTERNAL")
        
        if electrical:
            print(">>> Starting Electrical Test / Power Up...")
            cm.Start()
            print(">>> M.2 Slot Powered & Reset.")
            
        if at_cmd:
            print(f">>> Sending AT Command: {at_cmd}")
            if cm.Modem:
                cm.Modem.AtSend(at_cmd)
            else:
                print("!!! Serial modem not found (Check power/USB).")
            
        if not electrical and not at_cmd:
            print(">>> Standard Connection Check...")
            if cm.Modem:
                cm.Modem.Diag()
            else:
                print("!!! Skipping diagnostics: modem not found.")
            
        print(">>> Task completed successfully.")
        
    except Exception as e:
        print(f"!!! Error in connection-manager: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if "-detect" in sys.argv:
        print("Modem detected")
    else:
        main()
