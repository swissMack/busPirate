"""A simulated ESP32 Bit Pirate, for tests and the dashboard's demo mode.

It speaks the firmware's text command line the way the firmware does — every
string here is copied from the geo-tp/ESP32-Bit-Pirate sources (``pioarduino``
branch, v1.7), cited next to it. What matters most is copied exactly:

* the line editor redraws the whole line on every key as
  ``\\r<MODE>> <line>ESC[K`` (Managers/CommandLineManager.cpp), and Enter,
  whether ``\\r`` or ``\\n``, prints ``\\r\\n`` and runs the line;
* the prompt is the mode in capitals, ``>`` and a space
  (Views/SerialTerminalView.cpp printPrompt);
* a question is ``Label [default]: `` and an empty answer takes the default
  (Managers/UserInputManager.cpp);
* entering I2C, SPI or UART for the first time runs that mode's ``config``
  questions (Controllers/*Controller.cpp ensureConfigured);
* a ``[ ... ]`` instruction prints its read bytes as ``XX `` hex after a
  ``<MODE> Read:`` line, then a "ByteCode Sequence:" dump
  (Dispatchers/ActionDispatcher.cpp dispatchInstructions).

Like :class:`buspirate.simulator.FakeSerial` it answers synchronously: every
reply is waiting by the time ``write`` returns.
"""

from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

from .simulator import FakeFlash

CRLF = "\r\n"

# Views/SerialTerminalView.cpp welcome().
BANNER = CRLF.join(
    [
        "    ____  _ _     ____  _           _       ",
        "   | __ )(_) |_  |  _ \\(_)_ __ __ _| |_ ___ ",
        "   |  _ \\| | __| | |_) | | '__/ _` | __/ _ \\",
        "   | |_) | | |_  |  __/| | | | (_| | ||  __/",
        "   |____/|_|\\__| |_|   |_|_|  \\__,_|\\__\\___|",
        "",
        "             ESP32 SWISS ARMY KNIFE",
        "",
        "     Version 1.7           Ready to board",
        "",
        " Type 'mode' to start or 'help' for commands",
        "",
        "",
    ]
)

# Enums/ModeEnum.h, the names the prompt shows.
MODES = (
    "HIZ", "1WIRE", "UART", "HDUART", "I2C", "SPI", "2WIRE", "3WIRE", "DIO",
    "LED", "INFRARED", "USB", "BLUETOOTH", "WIFI", "JTAG", "I2S", "CAN",
    "ETHERNET", "SUBGHZ", "RFID", "RF24", "FM", "CELL", "LORA", "EXPANDER",
)

# Controllers/UtilityController.cpp handleEnablePullups / handleDisablePullups.
PULLUP_MESSAGES = {
    ("I2C", True): "I2C: Pull-ups enabled on SDA, SCL.",
    ("I2C", False): "I2C: Pull-ups disabled on SDA, SCL.",
    ("SPI", True): "SPI: Pull-up enabled on MISO.",
    ("SPI", False): "SPI: Pull-ups disabled on MISO",
    ("UART", True): "UART: Pull-up enabled on RX.",
    ("UART", False): "UART: Pull-ups disabled on RX.",
}

Question = Tuple[str, str, Callable[[str], None]]


class FakeBitPirateSerial:
    """A pyserial stand-in that behaves like an ESP32 Bit Pirate on USB."""

    def __init__(
        self,
        i2c_devices: Optional[Dict[int, bytearray]] = None,
        flash: Optional[FakeFlash] = None,
        uart_rx: bytes = b"",
        booting: bool = False,
    ) -> None:
        #: 7-bit address to a 256-byte register file.
        self.i2c_devices = (
            i2c_devices
            if i2c_devices is not None
            else {0x68: bytearray(range(256)), 0x50: bytearray(b"\xff" * 256)}
        )
        #: Address to how many bytes its memory pointer takes; 1 if unlisted.
        #: A 24C32 and up wants 2.
        self.i2c_pointer_width: Dict[int, int] = {}
        self.flash = flash or FakeFlash()
        #: Bytes the target will have sent by the time "read" starts.
        self.uart_rx = bytes(uart_rx)
        #: What the host has made the UART send, via [ ... ] instructions.
        self.uart_tx = bytearray()
        self.written = bytearray()
        #: Every command line the firmware ran, in order.
        self.commands: List[str] = []
        self.mode = "HIZ"
        self.configured: set = set()
        self.pullups = False
        self.settings = {
            # The s3-devkit build's pins (platformio.ini [env:s3-devkit]) over
            # the defaults in States/GlobalState.h.
            "I2C": {"SDA GPIO": "6", "SCL GPIO": "7", "Frequency": "100000"},
            "SPI": {
                "MOSI GPIO": "13", "MISO GPIO": "11", "SCLK GPIO": "12",
                "CS GPIO": "10", "Frequency (MHz)": "20", "Use WP or HOLD ?": "n",
            },
            "UART": {
                "RX GPIO number": "17", "TX GPIO number": "18", "Baud rate": "9600",
                "Data bits (5-8)": "8", "Parity (N/E/O)": "N",
                "Stop bits (1 or 2)": "1", "Inverted?": "n",
            },
        }
        self.closed = False
        self.is_open = True
        self._out = bytearray()
        self._line = ""
        self._questions: List[Question] = []
        self._after_questions: List[str] = []
        self._answer = ""
        self._state = "boot" if booting else "prompt"
        if booting:
            # Views/SerialTerminalView.cpp waitPress().
            self._emit("\n\n\rPress any key to start..." + CRLF)

    # -- pyserial surface --------------------------------------------------

    @property
    def in_waiting(self) -> int:
        return len(self._out)

    def write(self, data: bytes) -> int:
        self.written += data
        for byte in bytes(data):
            self._key(chr(byte))
        return len(data)

    def read(self, count: int = 1) -> bytes:
        chunk = bytes(self._out[:count])
        del self._out[:count]
        return chunk

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self._out.clear()

    def close(self) -> None:
        self.closed = True
        self.is_open = False

    # -- helpers for tests -------------------------------------------------

    def screen(self) -> str:
        """Everything not yet read, decoded."""
        return self._out.decode("ascii", "replace")

    # -- the firmware ------------------------------------------------------

    def _emit(self, text: str) -> None:
        self._out += text.encode("utf-8")

    def _println(self, text: str = "") -> None:
        self._emit(text + CRLF)

    def _prompt(self) -> None:
        self._emit(f"{self.mode}> ")

    def _key(self, char: str) -> None:
        if self._state == "boot":
            # Any key at all starts it, even one that is not printable.
            self._emit(BANNER)
            self._state = "prompt"
            self._prompt()
            return
        if self._state == "uart_read":
            if char in "\r\n":
                self._println()
                self._println("UART Read: Stopped by user.")
                self._state = "prompt"
                self._prompt()
            return
        if self._state == "question":
            self._question_key(char)
            return
        if self._state == "mode_number":
            self._mode_number_key(char)
            return
        # The command line.
        if char in "\r\n":
            self._println()
            line, self._line = self._line, ""
            self._run(line)
            if self._state == "prompt":
                self._prompt()
        elif char.isprintable() and len(self._line) < 512:
            self._line += char
            self._emit(f"\r{self.mode}> {self._line}\x1b[K")
        # Everything else — nulls, 0x0F, BEL — is ignored, as the firmware's
        # line editor ignores anything it has no handler for.

    # -- questions ---------------------------------------------------------

    def _ask(self, questions: List[Question], after: List[str]) -> None:
        self._questions = list(questions)
        self._after_questions = after
        self._state = "question"
        self._next_question()

    def _next_question(self) -> None:
        if not self._questions:
            for line in self._after_questions:
                self._println(line)
            self._state = "prompt"
            self._prompt()
            return
        label, default, _ = self._questions[0]
        self._emit(f"{label} [{default}]: ")

    def _question_key(self, char: str) -> None:
        if char in "\r\n":
            self._println()
            label, default, store = self._questions.pop(0)
            store(self._answer or default)
            self._answer = ""
            self._next_question()
        elif char.isprintable():
            self._answer += char
            self._emit(char)

    def _config_questions(self, mode: str) -> List[Question]:
        settings = self.settings[mode]
        return [
            (label, settings[label], lambda value, label=label: settings.__setitem__(label, value))
            for label in settings
        ]

    def _configure(self, mode: str) -> None:
        self._println(f"{mode} Configuration:")
        after = {"I2C": ["I2C configured.\n"], "SPI": ["SPI configured.\n"],
                 "UART": ["UART configured.", ""]}[mode]
        self._ask(self._config_questions(mode), after)

    # -- commands ----------------------------------------------------------

    def _run(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        self.commands.append(line)
        if line.startswith("["):
            self._instruction(line)
            return
        root, _, rest = line.partition(" ")
        rest = rest.strip()
        if root in ("m", "mode") and not rest:
            self._mode_menu()
        elif root in ("m", "mode"):
            self._mode_change(rest)
        elif root in ("help", "h", "?"):
            self._help()
        elif root in ("P", "p"):
            enable = root == "P"
            message = PULLUP_MESSAGES.get((self.mode, enable))
            self.pullups = enable if message else self.pullups
            self._println(message or "Pull-ups not applicable for this mode.")
        elif self.mode == "HIZ":
            self._println("Type 'help' or 'mode'")
        elif root == "config" and self.mode in self.settings:
            self._configure(self.mode)
        elif self.mode == "I2C" and root == "scan":
            self._scan()
        elif self.mode == "I2C" and root == "ping":
            self._ping(rest)
        elif self.mode == "UART" and root == "read":
            self._println("UART Read: Streaming until [ENTER] is pressed...")
            self._emit(self.uart_rx.decode("latin-1"))
            self.uart_rx = b""
            self._state = "uart_read"
        else:
            self._println(f"\nUnknown command. Available {self.mode} commands:")

    def _mode_change(self, name: str) -> None:
        # Controllers/UtilityController.cpp handleModeChangeCommand.
        wanted = name.upper()
        if wanted not in MODES:
            self._println(f"Unknown mode: {name}")
            return
        self._println(f"Mode changed to {wanted}")
        self._println()
        self._enter(wanted)

    def _enter(self, wanted: str) -> None:
        self.mode = wanted
        if wanted in self.settings and wanted not in self.configured:
            self.configured.add(wanted)
            self._configure(wanted)

    # Controllers/UtilityController.cpp handleModeSelect: ModeEnum's names in
    # order, "None" included, then a number read by
    # Managers/UserInputManager.cpp readModeNumber (digits only).
    _MENU = ("None",) + MODES

    def _mode_menu(self) -> None:
        self._println()
        self._println("Select mode:")
        for number, name in enumerate(self._MENU, start=1):
            self._println(f"  {number}. {name}")
        self._println()
        self._emit("Mode Number > ")
        self._answer = ""
        self._state = "mode_number"

    def _mode_number_key(self, char: str) -> None:
        if char in "\r\n":
            self._println()
            number, self._answer = self._answer, ""
            self._state = "prompt"
            if not number:
                self._println()
                self._println()
                self._println("Invalid input.")
            elif 1 <= int(number) <= len(self._MENU):
                chosen = self._MENU[int(number) - 1]
                self._println()
                self._println(f"Mode changed to {chosen}")
                self._println()
                if chosen != "None":
                    self._enter(chosen)
            else:
                self._println()
                self._println("Invalid mode number.")
                self._println()
            if self._state == "prompt":
                self._prompt()
        elif char.isdigit():
            self._answer += char
            self._emit(char)

    def _help(self) -> None:
        # An abbreviation of Shells/HelpShell.cpp: the real list is far longer.
        self._println()
        self._println("General commands:")
        self._println("  help / h / ?     This help")
        self._println("  mode / m [name]  Change mode (no name: pick from a list)")
        self._println("  P / p            Pull-ups on / off")
        self._println("  config           Pins and speed for the current mode")
        self._println("  [0x.. r:N]       Bus instructions: write bytes, read N")
        self._println()
        if self.mode == "I2C":
            self._println("I2C commands: scan, ping <addr>, read <addr> [reg], write <addr> [reg] [val]")
        elif self.mode == "UART":
            self._println("UART commands: read, write <text>")
        elif self.mode == "SPI":
            self._println("SPI commands: flash, eeprom, sniff")
        self._println()

    def _scan(self) -> None:
        # Controllers/I2cController.cpp handleScan.
        self._println("I2C Scan: Scanning I2C bus... Press [ENTER] to stop")
        self._println()
        found = sorted(a for a in self.i2c_devices if 1 <= a < 127)
        for address in found:
            self._println(f"Found device at 0x{address:X}")
        if not found:
            self._println("I2C Scan: No I2C devices found.")
        self._println()

    def _ping(self, argument: str) -> None:
        # Controllers/I2cController.cpp handlePing.
        address = int(argument, 0)
        if address in self.i2c_devices:
            reply = "I2C Ping: ACK received! Device is present."
        else:
            reply = "I2C Ping: No response (NACK or error)."
        self._println(f"Ping 0x{address:X}: {reply}")

    # -- [ ... ] instructions ----------------------------------------------

    def _instruction(self, line: str) -> None:
        if self.mode not in ("I2C", "SPI", "UART"):
            self._println("Cannot execute instruction in this mode.")
            return
        codes = _bytecodes(line)
        if self.mode == "I2C":
            data = self._i2c_bytecodes(codes)
            if data:
                self._println("I2C Read:\n")
                self._println(" ".join(f"{b:02X}" for b in data) + " ")
        elif self.mode == "SPI":
            written = bytes(v for kind, v in codes if kind == "write")
            count = sum(v for kind, v in codes if kind == "read")
            data = self.flash.exchange(written, count)
            if data:
                self._println("SPI Read:\n")
                self._println(" ".join(f"{b:02X}" for b in data) + " ")
        else:
            self.uart_tx += bytes(v for kind, v in codes if kind == "write")
            self._println()
            self._emit("UART Read: ")
            self._emit("No data")
            self._println()
        self._println()
        self._println("ByteCode Sequence:")
        for kind, value in codes:
            self._println(f"{kind.upper()} | data={value} | bits=8 | repeat=1")
        self._println()

    def _i2c_bytecodes(self, codes: List[Tuple[str, int]]) -> bytes:
        # Services/I2cService.cpp executeByteCode: the first write after a
        # start is the 7-bit address; later writes go to the device; a read
        # requests from the last address.
        address: Optional[int] = None
        expect_address = False
        pointer_bytes = 0
        result = bytearray()
        for kind, value in codes:
            if kind == "start":
                expect_address = True
                pointer_bytes = 0
            elif kind == "write" and expect_address:
                address, expect_address = value, False
            elif kind == "write":
                memory = self.i2c_devices.get(address)
                if memory is None:
                    continue
                if pointer_bytes < self.i2c_pointer_width.get(address, 1):
                    self._pointer = (self._pointer << 8 if pointer_bytes else 0) | value
                    pointer_bytes += 1
                else:
                    memory[self._pointer % len(memory)] = value
                    self._pointer += 1
            elif kind == "read":
                memory = self.i2c_devices.get(address)
                if memory is None:
                    continue  # Wire.requestFrom got nothing back
                start = getattr(self, "_pointer", 0)
                for offset in range(value):
                    result.append(memory[(start + offset) % len(memory)])
                self._pointer = start + value
        return bytes(result)

    _pointer = 0


def _bytecodes(line: str) -> List[Tuple[str, int]]:
    """Transformers/InstructionTransformer.cpp, the parts the dashboard uses."""
    codes: List[Tuple[str, int]] = []
    for block in re.findall(r"\[([^\]]*)\]", line):
        codes.append(("start", 0))
        for token in block.split():
            token = token.rstrip(",")
            if re.fullmatch(r"0[xX][0-9a-fA-F]+", token):
                codes.append(("write", int(token, 16)))
            elif token.isdigit():
                codes.append(("write", int(token)))
            elif re.fullmatch(r"r(:\d+)?", token):
                codes.append(("read", int(token[2:]) if ":" in token else 1))
        codes.append(("stop", 0))
    return codes
