# readTemps.py
try:
    import smbus
    HAS_SMBUS = True
except ImportError:
    HAS_SMBUS = False

sensors = [0x48, 0x49, 0x4a]

if HAS_SMBUS:
    try:
        bus = smbus.SMBus(1)
    except:
        HAS_SMBUS = False

def read_temp(address):
    """Read temperature from one sensor (Real hardware)"""
    if not HAS_SMBUS:
        return None
    try:
        data = bus.read_i2c_block_data(address, 0x00, 2)
        raw = (data[0] << 8) | data[1]
        val = raw >> 4
        # Handle 12-bit sign bit (bit 11 is the sign)
        if val & 0x800:
            val -= 0x1000
        temp_c = val * 0.0625
        return round(temp_c, 2)
    except Exception:
        return None

def read_all_temps():
    """Return a list of temperatures from all sensors"""
    # If on a laptop with no SMBus, this will return [None, None, None]
    # ControlPanelV4 will then use its mock values.
    temps = []
    for addr in sensors:
        temps.append(read_temp(addr))
    return temps
