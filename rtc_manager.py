# rtc_manager.py
import subprocess

def run(cmd):
    """Run a shell command and return output (or error)."""
    try:
        result = subprocess.check_output(cmd, shell=True, text=True).strip()
        return result
    except subprocess.CalledProcessError as e:
        return f"⚠️ Error running: {cmd}\n{e.output}"

def show_rtc_time():
    return run("sudo hwclock --show -f /dev/rtc")

def show_system_time():
    return run("date")

def write_system_to_rtc():
    run("sudo hwclock --systohc -f /dev/rtc")
    return run("sudo hwclock -w")

def write_rtc_to_system():
    run("sudo hwclock --hctosys -f /dev/rtc")
    return run("sudo hwclock -s")

def set_rtc_time(date_str):
    run(f'sudo hwclock --set --date="{date_str}"')
    return run("sudo hwclock --show -f /dev/rtc")
