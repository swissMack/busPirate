"""The Bus Pirate v4."""

from ..capabilities import BUS_PIRATE_ONLY, CAP_ADC, CAP_FREQUENCY, CAP_PULLUP_VOLTAGE, CAP_PWM
from ._board import Board

BOARD = Board(
    variant="v4",
    name="Bus Pirate v4",
    # The wiki notes binary self-tests are v2go/v3 hardware only.
    # No extended AUX: the firmware reads its sub-command from the PIC's
    # hardware UART, which on a v4 is not the host link — it waits
    # forever. Found on a real v4 on firmware 7.0, 2026-09-28.
    capabilities=BUS_PIRATE_ONLY
    | frozenset({CAP_PWM, CAP_ADC, CAP_FREQUENCY, CAP_PULLUP_VOLTAGE}),
    simulated_name="simulated Bus Pirate v4",
    terminal_caption="The Bus Pirate's own terminal. Type a command; '?' lists them.",
    guide_page="bus-pirate-v4",
    manual="official",
)
