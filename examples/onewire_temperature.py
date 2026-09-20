"""Read every DS18B20 on a 1-Wire bus.

    python examples/onewire_temperature.py /dev/tty.usbserial-A700eEoR

Needs an external 4k7 pull-up from the data line to Vpu — the Bus Pirate's
internal pull-ups are too weak for 1-Wire.
"""

import sys
import time

from buspirate import BusPirate
from buspirate.onewire import ROM_MATCH

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/tty.usbserial-A700eEoR"

CONVERT_T = 0x44
READ_SCRATCHPAD = 0xBE
DS18B20_FAMILY = 0x28

with BusPirate(port) as bp:
    with bp.onewire() as ow:
        ow.configure_peripherals(power=True, pullups=True)

        devices = [rom for rom in ow.search_rom() if rom[0] == DS18B20_FAMILY]
        if not devices:
            sys.exit("no DS18B20 found — check the pull-up and the data line")

        for rom in devices:
            ow.reset()
            ow.write(bytes([ROM_MATCH]) + rom + bytes([CONVERT_T]))
            time.sleep(0.8)  # 12-bit conversion takes up to 750 ms

            ow.reset()
            ow.write(bytes([ROM_MATCH]) + rom + bytes([READ_SCRATCHPAD]))
            scratchpad = ow.read(9)

            raw = int.from_bytes(scratchpad[0:2], "little", signed=True)
            print(f"{rom.hex(':')}  {raw / 16.0:.2f} °C")
