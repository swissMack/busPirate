"""Scan the I2C bus and read the first few bytes of anything found.

    python examples/i2c_scan.py /dev/tty.usbserial-A700eEoR
"""

import sys

from buspirate import BusPirate, NackError

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/tty.usbserial-A700eEoR"

with BusPirate(port) as bp:
    with bp.i2c() as i2c:
        # Bus Pirate supplies 3V3/5V and its own (passive) pull-ups.
        i2c.configure_peripherals(power=True, pullups=True)
        i2c.set_speed(i2c.SPEED_100KHZ)

        for address in i2c.scan():
            print(f"0x{address:02X} responded", end="")
            try:
                print(f" — first 8 bytes: {i2c.read_register(address, 0x00, 8).hex(' ')}")
            except NackError:
                print(" — but refused a register read")
