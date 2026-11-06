"""The Bus Pirate v3 (and v2go, which shares its command set)."""

from ..capabilities import (
    BUS_PIRATE_ONLY, CAP_ADC, CAP_EXTENDED_AUX, CAP_FREQUENCY, CAP_PWM, CAP_SELF_TEST,
)
from ._board import Board

BOARD = Board(
    variant="v3",
    name="Bus Pirate v3",
    # On a v3 the PIC's hardware UART is the FT232R link, so extended AUX works.
    capabilities=BUS_PIRATE_ONLY
    | frozenset({CAP_PWM, CAP_ADC, CAP_FREQUENCY, CAP_SELF_TEST, CAP_EXTENDED_AUX}),
    simulated_name="simulated Bus Pirate v3",
    terminal_caption="The Bus Pirate's own terminal. Type a command; '?' lists them.",
    guide_page=None,
    manual="official",
)
