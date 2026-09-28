"""I2C mode (``I2Cx``)."""

from __future__ import annotations

from typing import Iterable, List

from . import device as device_module
from .exceptions import (
    ExternalVoltageError,
    NackError,
    ProtocolError,
    UnsupportedFeatureError,
)
from .mode import ACK, Mode

CMD_START = 0x02
CMD_STOP = 0x03
CMD_READ_BYTE = 0x04
CMD_ACK = 0x06
CMD_NACK = 0x07
CMD_WRITE_THEN_READ = 0x08
CMD_EXTENDED_AUX = 0x09
CMD_SNIFFER = 0x0F
SPEED_BASE = 0x60
PULLUP_VOLTAGE_BASE = 0x50  # 0b010100xy, BPv4 only

MAX_WRITE_THEN_READ = 4096

#: The addresses a scan probes: the whole map less the reserved ends.
SCAN_RANGE = range(0x08, 0x78)


def stuck_bus_warning(found: Iterable[int], probed: Iterable[int]) -> str:
    """Say so when every probed address answered, which no real bus does.

    A low SDA in the ACK slot reads as an ACK, so a bus whose pull-ups have
    nothing to pull up to acknowledges everything — seen on a real v3 with
    VPU floating, where all 112 addresses "answered". Returns "" for an
    ordinary result.
    """
    probed = list(probed)
    if len(probed) < 2 or set(probed) - set(found):
        return ""
    return (
        f"Every address answered ({len(probed)} of {len(probed)}), which no real "
        "bus does: SDA is being held low, and a low SDA reads as an ACK. Most "
        "often the pull-ups have nothing to pull up to — tie VPU to the bus's "
        "supply (the Bus Pirate's +3.3V or +5V will do). Otherwise something "
        "on the bus is holding SDA down."
    )

# Argument bytes for the extended AUX command. It works on a v3 only: a v4
# hangs waiting for the argument (see device.capabilities_for).
AUX_LOW = 0x00
AUX_HIGH = 0x01
AUX_HIZ = 0x02
AUX_READ = 0x03
AUX_USE_AUX = 0x10
AUX_USE_CS = 0x20


class I2C(Mode):
    """Bit-banged I2C master.

    Addresses are 7-bit throughout; the read/write bit is added internally.
    """

    enter_command = 0x02
    banner_prefix = "I2C"
    title = "I2C"

    SPEED_5KHZ = 0
    SPEED_50KHZ = 1
    SPEED_100KHZ = 2
    SPEED_400KHZ = 3

    #: Pull-up rail selection (Bus Pirate v4 only). These connect the VPU
    #: (VEXTERN) pin to an on-board rail; they do not change the supplies.
    PULLUP_OFF = 0
    PULLUP_3V3 = 1
    PULLUP_5V = 2

    # -- bus primitives ----------------------------------------------------

    def start(self) -> None:
        """Send a start condition. Issue it again for a repeated start."""
        self._check_active()
        self.bp.command_expect_ack(CMD_START)

    def stop(self) -> None:
        self._check_active()
        self.bp.command_expect_ack(CMD_STOP)

    def read_byte(self, ack: bool = True) -> int:
        """Read one byte, then send ACK (continue) or NACK (last byte)."""
        self._check_active()
        self.bp.write(bytes([CMD_READ_BYTE]))
        value = self.bp.read(1)[0]
        self.bp.command_expect_ack(CMD_ACK if ack else CMD_NACK)
        return value

    def write_bytes(self, data: bytes) -> List[bool]:
        """Write bytes, returning the target's ACK flag per byte.

        ``True`` means the target acknowledged. No start or stop is sent, and
        payloads longer than 16 bytes are split into bulk chunks for you.
        """
        # The firmware answers 0x00 for ACK and 0x01 for NACK.
        return [b == 0x00 for b in self._write_bulk_chunks(data, "I2C bulk write")]

    def set_speed(self, speed: int) -> None:
        """Set the bus clock. Use one of the ``SPEED_*`` constants.

        Firmware older than v4.2 knows only two speeds (0 = 5 kHz,
        1 = 50 kHz), so the valid range depends on the connected device.
        """
        self._check_active()
        available = self.bp.profile.i2c_speeds
        if speed not in available:
            options = ", ".join(
                f"{index}={hz // 1000}kHz" for index, hz in sorted(available.items())
            )
            raise ValueError(
                f"speed {speed} is not available on {self.bp.profile.describe()}; "
                f"choose from {options}"
            )
        self.bp.command_expect_ack(SPEED_BASE | speed)

    # -- transactions ------------------------------------------------------

    def write(self, address: int, data: bytes = b"") -> None:
        """START, address + W, ``data``, STOP. Raises on any NACK."""
        payload = bytes([_addr_byte(address, read=False)]) + bytes(data)
        self.start()
        try:
            acks = self.write_bytes(payload)
            if not all(acks):
                index = acks.index(False)
                where = "its address" if index == 0 else f"data byte {index - 1}"
                raise NackError(f"0x{address:02X} did not acknowledge {where}")
        finally:
            self.stop()

    def read(self, address: int, count: int) -> bytes:
        """START, address + R, read ``count`` bytes, STOP."""
        if count < 1:
            raise ValueError("count must be >= 1")
        self.start()
        try:
            if not self.write_bytes(bytes([_addr_byte(address, read=True)]))[0]:
                raise NackError(f"0x{address:02X} did not acknowledge a read")
            # NACK the final byte to tell the target to release the bus.
            return bytes(self.read_byte(ack=(i < count - 1)) for i in range(count))
        finally:
            self.stop()

    def read_register(self, address: int, register: int, count: int = 1) -> bytes:
        """Point the target at ``register``, then read ``count`` bytes.

        Uses a repeated start, which is what almost every register-mapped chip
        expects, and works on every firmware version.
        """
        if count < 1:
            raise ValueError("count must be >= 1")
        self.start()
        try:
            acks = self.write_bytes(
                bytes([_addr_byte(address, read=False), register & 0xFF])
            )
            if not acks[0]:
                raise NackError(f"0x{address:02X} did not acknowledge its address")
            if not acks[1]:
                raise NackError(
                    f"0x{address:02X} did not acknowledge register 0x{register:02X}"
                )
            self.start()  # repeated start
            if not self.write_bytes(bytes([_addr_byte(address, read=True)]))[0]:
                raise NackError(f"0x{address:02X} did not acknowledge a read")
            return bytes(self.read_byte(ack=(i < count - 1)) for i in range(count))
        finally:
            self.stop()

    def read_after_write(self, address: int, pointer: bytes, count: int) -> bytes:
        """Write ``pointer``, repeated start, read ``count`` bytes.

        The 24Cxx EEPROM read: a one- or two-byte memory address, then read
        straight through. Raises :class:`NackError` if the address or the
        pointer is not acknowledged.
        """
        if count < 1:
            raise ValueError("count must be >= 1")
        self.start()
        try:
            acks = self.write_bytes(bytes([_addr_byte(address, read=False)]) + bytes(pointer))
            if not all(acks):
                raise NackError(f"0x{address:02X} did not acknowledge")
            self.start()  # repeated start
            self.write_bytes(bytes([_addr_byte(address, read=True)]))
            return bytes(self.read_byte(ack=(i < count - 1)) for i in range(count))
        finally:
            self.stop()

    def write_register(self, address: int, register: int, data: bytes) -> None:
        self.write(address, bytes([register & 0xFF]) + bytes(data))

    def write_then_read(self, write_data: bytes = b"", read_count: int = 0) -> bytes:
        """The firmware's buffered write-then-read (command ``0x08``).

        ``write_data`` is the exact byte stream to put on the bus **including
        the address byte** — the firmware adds nothing. It sends a start,
        writes those bytes, reads ``read_count`` bytes ACKing all but the
        last, then stops. Use :func:`address_byte` to build the address.

        Far faster than the primitives for bulk reads, but it needs firmware
        v5.1 or newer and there is no repeated start: to read a register, use
        :meth:`read_register` instead.
        """
        self._check_active()
        write_data = bytes(write_data)
        if len(write_data) > MAX_WRITE_THEN_READ or read_count > MAX_WRITE_THEN_READ:
            raise ValueError(
                f"write_then_read handles at most {MAX_WRITE_THEN_READ} bytes "
                "in each direction"
            )
        self.bp.write(
            bytes([CMD_WRITE_THEN_READ])
            + len(write_data).to_bytes(2, "big")
            + read_count.to_bytes(2, "big")
            + write_data
        )
        status = self.bp.read(1)[0]
        if status != 0x01:
            raise NackError(
                "write_then_read failed (the Bus Pirate returned "
                f"0x{status:02X}) — the target did not acknowledge, or the "
                "byte counts are out of range"
            )
        return self.bp.read(read_count) if read_count else b""

    # -- convenience -------------------------------------------------------

    def scan(self, addresses: Iterable[int] = SCAN_RANGE) -> List[int]:
        """Probe each 7-bit address and return those that acknowledge.

        The default range skips the reserved addresses at both ends of the map.
        """
        found = []
        for address in addresses:
            self.start()
            try:
                if self.write_bytes(bytes([_addr_byte(address, read=False)]))[0]:
                    found.append(address)
            finally:
                self.stop()
        return found

    def start_sniffer(self) -> None:
        """Start the passive bus sniffer. The device then streams until stopped.

        Nothing is read here: from this point the port carries sniffed traffic,
        not command replies. Call :meth:`~buspirate.base.BusPirate.stop_stream`
        to get back to a known state.
        """
        self._check_active()
        self.bp.write(bytes([CMD_SNIFFER]))
        self.bp.streaming = True

    # -- Bus Pirate v4 only ------------------------------------------------

    def set_pullup_voltage(self, selection: int) -> None:
        """Connect the VPU pin to an on-board rail: off, 3.3V or 5V.

        **Bus Pirate v4 only.** This switches what the *pull-ups* are pulled
        up to; it does not change the 3.3V and 5V supplies themselves, which
        are separate pins and always come on together (see
        :meth:`~buspirate.mode.Mode.configure_peripherals`).

        The firmware refuses to connect a rail if an external voltage is
        already present on VPU, which is a deliberate protection — feeding the
        Bus Pirate's rail into a target's supply would be a short.

        Note that the wiki marked this command "unimplemented" for a long
        time, so older v4 firmware may ignore it. If the pull-ups do not
        change, drive VPU from the target's own supply instead.
        """
        self._check_active()
        self.bp.profile.require(device_module.CAP_PULLUP_VOLTAGE)
        if selection not in (self.PULLUP_OFF, self.PULLUP_3V3, self.PULLUP_5V):
            raise ValueError("use I2C.PULLUP_OFF, PULLUP_3V3 or PULLUP_5V")
        self.bp.write(bytes([PULLUP_VOLTAGE_BASE | selection]))
        if self.bp.read(1)[0] != 0x01:
            raise ExternalVoltageError(
                "the Bus Pirate refused to connect its pull-up rail because a "
                "voltage is already present on the VPU pin. That is the "
                "protection working: disconnect VPU from the target's supply "
                "first, or leave VPU driven by the target and set the rail to "
                "off."
            )

    def extended_aux(self, command: int) -> int:
        """Drive or read AUX/CS directly. **BPv3 only.** Returns the reply byte.

        For ``AUX_READ`` the reply is the pin state, 0 or 1. Every other
        sub-command replies 0x01 to acknowledge.

        The firmware (Firmware/I2C.c, case 9) answers twice: 0x01 as soon as
        it knows the command, then the sub-command's result. So 0x09 goes out
        alone and is answered first. Firmware older than v6.1 does not know
        it and answers 0x00 — found on a real v4 on 6.0-a3. Sending the
        sub-command anyway would then start some other command (0x10 is a
        bulk write), so it is not sent.
        """
        self._check_active()
        self.bp.profile.require(device_module.CAP_EXTENDED_AUX)
        self.bp.write(bytes([CMD_EXTENDED_AUX]))
        if self.bp.read(1)[0] != ACK:
            raise UnsupportedFeatureError(
                "this Bus Pirate's firmware does not know the extended AUX "
                f"command ({self.bp.profile.describe()}). It needs firmware "
                "v6.1 or newer."
            )
        self.bp.write(bytes([command & 0xFF]))
        response = self.bp.read(1)[0]
        if command != AUX_READ and response != ACK:
            raise ProtocolError(
                f"extended AUX command: got 0x{response:02X}, want 0x01"
            )
        return response


def address_byte(address: int, read: bool) -> int:
    """Turn a 7-bit address into the byte that goes on the bus."""
    return _addr_byte(address, read)


def _addr_byte(address: int, read: bool) -> int:
    if not 0x00 <= address <= 0x7F:
        raise ValueError(
            f"0x{address:02X} is not a 7-bit address. Addresses here are 7-bit "
            "(0x00-0x7F); the read/write bit is added for you."
        )
    return (address << 1) | (1 if read else 0)
