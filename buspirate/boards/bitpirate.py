"""The ESP32 Bit Pirate (geo-tp firmware) on an ESP32-S3 DevKit in its dock."""

from ._board import Board

BOARD = Board(
    variant="bitpirate",
    name="ESP32 Bit Pirate",
    # A text command line, not the binary protocol: none of the binary
    # extras, and no supplies to switch. What it can do is I2C, SPI and
    # UART through its own commands — see buspirate.bitpirate.
    capabilities=frozenset(),
    simulated_name="simulated ESP32 Bit Pirate",
    terminal_caption="The Bit Pirate's own command line. Type a command; 'help' lists them.",
    guide_page="bitpirate",
    manual="bitpirate-wiki",
)
