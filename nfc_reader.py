#!/usr/bin/env python3
import time
import threading

# Try to import Pi-specific GPIO and NFC libraries
try:
    import RPi.GPIO as GPIO
    from mfrc522 import SimpleMFRC522
    IS_PI = True
except (ImportError, RuntimeError):
    IS_PI = False

class NFCManager:
    def __init__(self):
        self.reader = None
        self.status = "Not Initialized"
        self.is_connected = False
        self._init_hardware()

    def _init_hardware(self):
        """Checks if the NFC chip is connected and initializes it."""
        if not IS_PI:
            self.status = "Mock Mode (Running on non-Pi device)"
            self.is_connected = False
            return

        try:
            # Attempt to initialize the MFRC522 reader via SPI
            self.reader = SimpleMFRC522()
            self.status = "Connected and Ready (RC522)"
            self.is_connected = True
        except Exception as e:
            self.status = f"Hardware Error: Could not connect to NFC chip. ({e})"
            self.is_connected = False
            self.reader = None

    def get_status(self):
        """Returns the current status of the NFC reader hardware."""
        return self.status

    def scan_for_tag(self):
        """
        Checks if an NFC tag is currently present.
        Returns the tag ID if found, else None.
        """
        if not self.is_connected or not self.reader:
            return None
        
        try:
            # read_no_block() returns (id, text) if a tag is present, else (None, None)
            tag_id, text = self.reader.read_no_block()
            return tag_id
        except Exception as e:
            self.status = f"Read Error: {e}"
            return None


# --- Standalone Diagnostic Mode ---
if __name__ == "__main__":
    print("=== NFC Reader Diagnostic ===")
    nfc = NFCManager()
    print(f"Reader Status: {nfc.get_status()}")

    if nfc.is_connected:
        print("\nWaiting for NFC tag... (Press Ctrl+C to quit)")
        last_id = None
        try:
            while True:
                tag_id = nfc.scan_for_tag()
                if tag_id and tag_id != last_id:
                    print(f"[+] New Tag Detected! ID: {tag_id}")
                    last_id = tag_id
                elif not tag_id:
                    last_id = None # Reset so we can read the same tag again if removed and tapped
                
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nExiting diagnostic mode...")
        finally:
            GPIO.cleanup()
    else:
        print("\nTroubleshooting:")
        print("1. Ensure the NFC module is physically wired to the Pi (SPI pins).")
        print("2. Make sure SPI is enabled via 'sudo raspi-config'.")
        print("3. Install library: pip3 install mfrc522")