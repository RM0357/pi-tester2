import os
import subprocess

def run(cmd):
    try:
        result = subprocess.check_output(cmd, shell=True, text=True).strip()
        print(result)
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Error running: {cmd}\n{e.output}")

def show_menu():
    print("""
========= 🕒 RTC & System Time Manager =========
1. Show RTC time
2. Show system time
3. Write system time to RTC
4. Write RTC time to system
5. Manually set RTC time
6. Exit
===============================================
""")

while True:
    show_menu()
    choice = input("Select option (1–6): ").strip()

    if choice == "1":
        print("\n📟 RTC Time:")
        run("sudo hwclock --show -f /dev/rtc")

    elif choice == "2":
        print("\n🖥️  System Time:")
        run("date")

    elif choice == "3":
        print("\n⏩ Writing system time to RTC...")
        run("sudo hwclock --systohc -f /dev/rtc")
        run("sudo hwclock -w")

    elif choice == "4":
        print("\n⏪ Writing RTC time to system...")
        run("sudo hwclock --hctosys -f /dev/rtc")
        run("sudo hwclock -s")

    elif choice == "5":
        date_str = input('Enter new RTC date/time (e.g. "2025-12-24 13:45:30"): ')
        run(f'sudo hwclock --set --date="{date_str}"')
        run("sudo hwclock --show -f /dev/rtc")

    elif choice == "6":
        print("Bye 👋")
        break

    else:
        print("❌ Invalid choice, try again!")

    print("\n-------------------------------------------\n")
