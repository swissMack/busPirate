"""DDR4 and DDR5 SPD (serial presence detect): read the module's ID EEPROM and decode it.

Read only. Writing SPD can stop a module from booting, so there is no writer here.
A reader, not a catalogue entry: ``DEVICES`` is empty.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..exceptions import BusPirateError, NackError

DEVICES: list = []

DDR4_SIZE = 512
DDR5_SIZE = 1024
_PAGE_SELECT = 0x36  # DDR4 SPA0 (page 0); 0x37 selects page 1


class SpdError(BusPirateError):
    """The module would not give up its SPD."""


def crc16(data: bytes) -> int:
    """CRC-16/XMODEM: polynomial 0x1021, initial value 0."""
    crc = 0
    for byte in bytes(data):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


# -- DDR4 ---------------------------------------------------------------------------

def _on_page(i2c, page: int) -> bool:
    """A read at 0x36 answers on page 0 and is NACKed on page 1."""
    try:
        i2c.read(_PAGE_SELECT, 1)
        answered = True
    except NackError:
        answered = False
    return answered == (page == 0)


def _select_page(i2c, page: int) -> None:
    # UNVERIFIED on hardware: the page-select addresses and the confirmation read.
    i2c.write(_PAGE_SELECT + page, b"")
    if _on_page(i2c, page):
        return
    try:
        i2c.write(_PAGE_SELECT + page, b"\x00")  # some modules want a dummy data byte
    except NackError:
        pass
    if not _on_page(i2c, page):
        raise SpdError("the module did not switch SPD pages")


def read_ddr4(i2c, address: int = 0x50) -> bytes:
    """The 512 bytes of a DDR4 SPD, as two 256-byte pages. Ends on page 0."""
    out = bytearray()
    try:
        for page in (0, 1):
            _select_page(i2c, page)
            out += i2c.read_after_write(address, b"\x00", 256)
    finally:
        try:
            _select_page(i2c, 0)
        except (SpdError, NackError):
            pass
    return bytes(out)


# -- DDR5 ---------------------------------------------------------------------------

def require_ddr5_hub(i2c, address: int = 0x50) -> None:
    """Raise SpdError unless an SPD5118 hub answers (MR0/MR1 read 0x51 0x18).

    A pointer-only read never writes data. On a DDR4 EEPROM an MR11 write would be a
    data write, so every DDR5 write is preceded by this.
    """
    ident = bytes(i2c.read_after_write(address, b"\x00", 2))
    if ident != b"\x51\x18":
        raise SpdError("not a DDR5 SPD hub (MR0/MR1 read %s); for a DDR4 module use ddr4-spd"
                       % ident.hex(" ").upper())


def read_ddr5(i2c, address: int = 0x50) -> bytes:
    """The 1024 bytes of a DDR5 SPD: eight 128-byte pages via MR11. Ends on page 0."""
    require_ddr5_hub(i2c, address)
    out = bytearray()
    try:
        for page in range(8):
            i2c.write(address, bytes([0x0B, page]))
            out += i2c.read_after_write(address, b"\x80", 128)
    finally:
        i2c.write(address, bytes([0x0B, 0]))
    return bytes(out)


# -- decoding -----------------------------------------------------------------------

_MEMORY_TYPES = {0x0C: "DDR4", 0x12: "DDR5"}
_MODULE_TYPES = {1: "RDIMM", 2: "UDIMM", 3: "SO-DIMM", 4: "LRDIMM"}


def _ascii(raw: bytes) -> str:
    return bytes(raw).decode("ascii", "replace").replace("\x00", " ").strip()


def _crc_ok(data: bytes, start: int, end: int) -> bool:
    """``data[start:end]`` against the little-endian CRC stored right after it."""
    stored = data[end:end + 2]
    return len(stored) == 2 and crc16(data[start:end]) == int.from_bytes(stored, "little")


# JEP106 (bank, code byte with its parity bit) -> name; bank is 1-based.
_MAKERS = {
    (1, 0x2C): "Micron", (1, 0xCE): "Samsung", (1, 0xAD): "SK hynix",
    (1, 0x20): "STMicroelectronics", (1, 0xFE): "Elpida",
    (2, 0x98): "Kingston", (3, 0x9E): "Corsair", (4, 0x0B): "Nanya",
    (5, 0xCD): "G.Skill", (5, 0xCB): "ADATA", (5, 0xEF): "Team Group",
    (6, 0x9B): "Crucial",
}


def _manufacturer(code_bank: int, code: int) -> str:
    bank = (code_bank & 0x7F) + 1
    text = "bank %d, 0x%02X" % (bank, code)
    name = _MAKERS.get((bank, code))
    return "%s (%s)" % (text, name) if name else text


def decode(data: bytes) -> Dict[str, Any]:
    """Name the module and check its CRCs. Works on a DDR4 or DDR5 image."""
    data = bytes(data)
    kind = data[2] if len(data) > 2 else -1
    out = {"memory_type": _MEMORY_TYPES.get(kind, "unknown 0x%02X" % max(kind, 0))}  # type: Dict[str, Any]
    if len(data) > 3:
        mod = data[3] & 0x0F
        out["module_type"] = _MODULE_TYPES.get(mod, "type 0x%02X" % mod)
    crc = []  # type: List[bool]
    if kind == 0x0C and len(data) >= DDR4_SIZE:
        out["manufacturer"] = _manufacturer(data[320], data[321])
        out["part_number"] = _ascii(data[329:349])
        out["serial"] = data[325:329].hex()
        crc = [_crc_ok(data, 0, 126), _crc_ok(data, 128, 254)]
    elif kind == 0x12 and len(data) >= DDR5_SIZE:
        out["manufacturer"] = _manufacturer(data[512], data[513])
        out["part_number"] = _ascii(data[521:551])
        out["serial"] = data[517:521].hex()
        crc = [_crc_ok(data, 0, 510)]
    out["crc_ok"] = crc
    if not all(crc):
        out["warning"] = ("a CRC does not match: the read is unreliable, or the SPD is damaged "
                          "or was edited" if crc else "not a complete DDR4 or DDR5 SPD image")
    return out
