"""Read the JEDEC ID and first page of an SPI NOR flash.

    python examples/spi_flash_id.py /dev/tty.usbserial-A700eEoR
"""

import sys

from buspirate import BusPirate

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/tty.usbserial-A700eEoR"

CMD_JEDEC_ID = 0x9F
CMD_READ = 0x03

with BusPirate(port) as bp:
    with bp.spi() as spi:
        spi.configure_peripherals(power=True)
        spi.set_speed(spi.SPEED_1MHZ)
        spi.set_mode(0)

        print("JEDEC ID:", spi.write_then_read(bytes([CMD_JEDEC_ID]), 3).hex(" "))

        # 24-bit address 0x000000, then 256 bytes of data.
        page = spi.write_then_read(bytes([CMD_READ, 0x00, 0x00, 0x00]), 256)
        for offset in range(0, len(page), 16):
            row = page[offset : offset + 16]
            ascii_row = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
            print(f"{offset:04X}  {row.hex(' '):<47}  {ascii_row}")
