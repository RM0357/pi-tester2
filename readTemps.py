# readTemps.py
import smbus

bus = smbus.SMBus(1)
sensors = [0x48, 0x49, 0x4a]

def read_temp(address):
    """Read temperature from one sensor"""
    try:
        data = bus.read_i2c_block_data(address, 0x00, 2)
        raw = (data[0] << 8) | data[1]
        temp_c = (raw >> 4) * 0.0625
        return round(temp_c, 2)
    except Exception as e:
        return None

def read_all_temps():
    """Return a list of temperatures from all sensors"""
    temps = []
    for addr in sensors:
        temps.append(read_temp(addr))
    return temps
