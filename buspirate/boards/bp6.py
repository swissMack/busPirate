"""The Bus Pirate 6 (and, untested, the Bus Pirate 5), over BPIO2."""

from ..capabilities import (
    CAP_ONEWIRE, CAP_PSU_PROGRAMMABLE, CAP_PSU_READOUT, CAP_SPI_FLASH_PROGRAM, CAP_SPI_MODES,
    CAP_SUPPLIES, CAP_UART_BUFFERED,
)
from ._board import Board

BOARD = Board(
    variant="bp6",
    name="Bus Pirate 6",
    # BPIO2: I2C, SPI (any mode, page writes fit in 512 bytes), UART with
    # its async receive, 1-Wire, and the programmable supply. No bitbang,
    # raw-wire, sniffers or bridge — see buspirate.bp6.
    capabilities=frozenset(
        {CAP_SUPPLIES, CAP_ONEWIRE, CAP_SPI_MODES, CAP_UART_BUFFERED,
         CAP_SPI_FLASH_PROGRAM, CAP_PSU_PROGRAMMABLE, CAP_PSU_READOUT}
    ),
    simulated_name="simulated Bus Pirate 6",
    terminal_caption=("The Bus Pirate 6's own terminal. Type a command; '?' lists them. "
                      "If it asks 'VT100 compatible color mode?', answer n."),
    guide_page="bus-pirate-6",
    manual="official",
)
