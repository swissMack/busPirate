# Bus Pirate 6 Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Bus Pirate 6 the fourth board in the app (driver over BPIO2, dashboard, CLI), and ship both our own BP6 guides and a bundled copy of the official Bus Pirate 5/6 manual in the in-app guide viewer.

**Architecture:** A new package `buspirate/bp6/` speaks BPIO2 (FlatBuffers in COBS frames) on the board's second USB port and exposes the same surface the dashboard already drives on the other boards (`profile`, `i2c()`, `spi()`, `uart()`, `onewire()`, `release_to_terminal`, `stop_stream`, …). The board's first USB port (its text terminal) is used only to switch BPIO2 on, and for the Terminal panel. The official manual is converted from its Hugo source by a script, committed under `docs/official/`, and served by an extended `web/docs.py` and Markdown renderer.

**Tech Stack:** Python 3.8+, pyserial, `flatbuffers` (new runtime dependency), FastAPI dashboard (`buspirate/web/`), vanilla JS frontend (`buspirate/web/static/app.js`), pytest, Pillow (new dev-only dependency, for the manual import).

**Spec:** `docs/superpowers/specs/2026-10-14-bus-pirate-6-support-design.md` — read it before starting. Every "established on the real board" fact below comes from it.

## Global Constraints

- USB ID of the board: VID `0x1209`, PID `0x7331`. Two CDC ports per board; on macOS `/dev/cu.usbmodem6buspirate1` (terminal) and `/dev/cu.usbmodem6buspirate3` (BPIO2). The USB serial number `6buspirate` is the same on every unit, and pyserial's `location` is the same for both ports of one board (`1-1`).
- BPIO2 requests always carry `version_major=2`, `minimum_version_minor=0`, and contents. **Never send a RequestPacket without contents** (it can crash the board).
- Frames: COBS-encoded FlatBuffer, terminated by one `0x00`, sent in a single `write()`.
- Limits from the board: `mode_max_write` 512, `mode_max_read` 512, packet 640.
- PSU: 800–5000 mV, current limit 0–500 mA (0 = no limit). Default 3300 mV / 300 mA. Asking above **3600 mV**, or for **no limit**, needs explicit confirmation.
- Terminal port: only `\r` is Enter. The colour prompt `VT100 compatible color mode? (Y/n)>` must be answered as `n\r` in **one write**. Select BPIO2 with `binmode\r`, `2\r`, then `n\r` (do **not** save).
- BPIO2 data handlers on current firmware: HiZ, 1WIRE, I2C, SPI, UART (+ unsolicited async RX frames with `is_async=true`), LED. No 2WIRE/3WIRE/DIO.
- Firmware identity: by `version_firmware_date` (e.g. `Oct 12 2026 09:05:15` → shown as `2026-10-12`); CI builds report git hash `unknown`.
- BP6 pin map (firmware `src/pirate.h`): 1-Wire OWD=IO0; I2C SDA=IO0, SCL=IO1; SPI CLK=IO6, MOSI(CDO)=IO7, MISO(CDI)=IO4, CS=IO5; UART TX=IO4, RX=IO5. Header order: VOUT, IO0–IO7, GND.
- UI rule (project memory): one-click controls that show their own state; a confirm step only where a mis-click could harm the target. Never make the user decode hex elsewhere.
- Official manual: `https://github.com/DangerousPrototypes/BusPirate-docs-hugo`, pinned at `efa4e5e3ec04561f581cc3771f36559b6031d191` (2026-09-01), MIT. Keep its LICENSE with the copy.
- Vendored BPIO2 generated code: `https://github.com/DangerousPrototypes/BusPirate-BPIO2-flatbuffer-interface` at `eb89844`, Apache-2.0.
- Version bump: `buspirate/__init__.py` `__version__` goes from `0.5.6` to `0.6.0` in the final task.
- Commit messages in this repo are plain sentences (no `feat:` prefixes), ending with the `Co-Authored-By` trailer the session supplies.

## Deviations from the spec (decided while planning, tell the owner)

1. **1-Wire search:** BPIO2's 1-Wire handler is byte-level only (reset, write bytes, read bytes), so the bit-level ROM search is impossible over BPIO2. On the BP6, `search_rom()` issues READ ROM (0x33) and returns the one device on the bus; with several devices the CRC fails and the error says to use the Terminal panel's `scan`.
2. **Board picture:** a generated SVG of the BP6's 10-pin header (like the Bit Pirate's DevKit drawing) instead of a photo, so the pin rings are exact. No photo licensing needed.
3. **No `buspirate/bp6/cli.py`:** the existing `buspirate/cli.py` commands switch to `connect.open_device()`, which serves every board.

## Review Focus

1. **Async UART frames arriving in the middle of another request's reply** (UART mode, target chattering) — the link must buffer them and still return the real reply. Pinned in Task 2 (`test_async_frames_are_set_aside_while_waiting_for_a_reply`).
2. **The board was replugged, so BPIO2 is off again** — Connect must switch it back on through the terminal port, including a pending colour prompt. Pinned in Task 5 (`test_connect_switches_bpio2_on_through_the_terminal_when_it_is_off`).
3. **I2C NACK leaves the bus mid-transaction** — every I2C error must be followed by a stop-only request so the next scan/read works. Pinned in Task 6 (`test_a_nack_is_followed_by_a_stop_only_request`).
4. **Current limit trips** — the status must show it and the UI must offer a one-click re-enable. Pinned in Task 9 (`test_a_tripped_supply_is_reported_with_a_re_enable_action`).
5. **A guide link or image path trying to leave `docs/`** (`../`, absolute paths, symlinks) — refused. Pinned in Task 11 (`test_doc_files_cannot_escape_the_docs_directory`).

---

## File Structure

| File | Responsibility |
|---|---|
| `buspirate/bp6/__init__.py` | Package export: `BusPirate6` |
| `buspirate/bp6/framing.py` | COBS encode/decode, frame delimiter, `FrameReader` |
| `buspirate/bp6/bpio/*.py`, `LICENSE`, `SOURCE.md` | Vendored generated FlatBuffers code (relative-import patched) |
| `buspirate/bp6/protocol.py` | Build requests, parse responses, describe frames for the traffic log; `ModeConfig`, `Status`, `Response` |
| `buspirate/bp6/link.py` | `BpioLink`: one request → one reply over a serial object; async frames set aside |
| `buspirate/bp6/terminal.py` | Talk to the text terminal port: answer the colour prompt, switch BPIO2 on |
| `buspirate/bp6/device.py` | `BusPirate6`: connect, status, power, pull-ups, HiZ, modes, streams |
| `buspirate/bp6/modes.py` | `Bp6I2C`, `Bp6SPI`, `Bp6UART`, `Bp6OneWire` |
| `buspirate/simulator_bp6.py` | `FakeBp6` with a fake BPIO2 port and a fake terminal port |
| `buspirate/device.py` | `bp6` variant, new capabilities, `parse_bp6_status()` |
| `buspirate/ports.py` | Know the BP6, pair its two ports, show one entry |
| `buspirate/connect.py` | Route `1209:7331` to `BusPirate6` |
| `buspirate/base.py` | `_make_serial(port=None)` so a second port can be opened |
| `buspirate/cli.py` | Commands use `open_device()`; `--demo` gains `bp6` |
| `buspirate/web/session.py` | Simulated `bp6`, HiZ, supplies, power refresh, terminal caption, traffic summaries |
| `buspirate/web/server.py` | Power refresh on `/api/state`; doc file route; doc search route |
| `buspirate/web/panels/power6.py` | BP6 "Power & pull-ups" panel |
| `buspirate/web/wiring.py` | `BOARDS["bp6"]`, LED rules/notes, wiring per panel |
| `scripts/draw_bp6_board.py`, `buspirate/web/static/img/board-bp6.svg` | Board drawing |
| `buspirate/web/static/app.js`, `app.css` | Status text, variant label, traffic summary, guide groups/search/images/anchors/banner |
| `buspirate/web/docs.py` | Sub-folders, groups, search, safe file serving |
| `scripts/import_official_docs.py` | Hugo → plain Markdown converter |
| `docs/official/**` | Imported manual (generated, committed) |
| `docs/bus-pirate-6.md` + edits to existing guides | Our own guides |
| `tests/test_bp6_*.py` | Tests per unit |

---

### Task 1: Framing and the vendored BPIO2 code

**Files:**
- Create: `buspirate/bp6/__init__.py`, `buspirate/bp6/framing.py`
- Create: `buspirate/bp6/bpio/` (copied, then patched), `buspirate/bp6/bpio/LICENSE`, `buspirate/bp6/bpio/SOURCE.md`
- Modify: `pyproject.toml` (dependency), `packaging/BusPirate.spec` (nothing to add if PyInstaller follows imports — verify in Step 9)
- Test: `tests/test_bp6_framing.py`

**Interfaces:**
- Produces: `cobs_encode(data: bytes) -> bytes`, `cobs_decode(data: bytes) -> bytes` (raises `ValueError` on a malformed frame), `frame(payload: bytes) -> bytes` (encoded + `b"\x00"`), `class FrameReader` with `feed(data: bytes) -> List[bytes]` returning **raw** complete frames *including* the trailing `0x00` (empty frames skipped). Package `buspirate.bp6.bpio` importable.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bp6_framing.py
"""COBS framing for the Bus Pirate 6's BPIO2 port."""

import pytest

from buspirate.bp6.framing import FrameReader, cobs_decode, cobs_encode, frame


@pytest.mark.parametrize(
    "data",
    [b"", b"\x00", b"\x00\x00", b"\x11\x22\x00\x33", bytes(range(1, 255)),
     bytes(range(1, 256)), bytes(254) + b"\x01", b"\x01" * 600, bytes(range(256)) * 3],
)
def test_round_trip(data):
    encoded = cobs_encode(data)
    assert b"\x00" not in encoded
    assert cobs_decode(encoded) == data


def test_known_vectors():
    # From the COBS paper / Wikipedia examples.
    assert cobs_encode(b"\x00") == b"\x01\x01"
    assert cobs_encode(b"\x11\x22\x00\x33") == b"\x03\x11\x22\x02\x33"
    assert cobs_encode(b"\x11\x00\x00\x00") == b"\x02\x11\x01\x01\x01"


def test_a_malformed_frame_is_refused():
    with pytest.raises(ValueError):
        cobs_decode(b"\x05\x11")  # claims 4 bytes, has 1
    with pytest.raises(ValueError):
        cobs_decode(b"\x02\x00")  # a zero inside a frame


def test_frame_adds_one_delimiter():
    assert frame(b"\x11") == b"\x02\x11\x00"


def test_reader_splits_frames_across_chunks():
    reader = FrameReader()
    one, two = frame(b"abc"), frame(b"\x00de")
    stream = one + two
    assert reader.feed(stream[:3]) == []
    assert reader.feed(stream[3:]) == [one, two]


def test_reader_skips_empty_frames():
    reader = FrameReader()
    assert reader.feed(b"\x00\x00" + frame(b"x")) == [frame(b"x")]


def test_the_vendored_code_imports_as_a_package():
    from buspirate.bp6.bpio import ConfigurationRequest, ModeConfiguration  # noqa: F401
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_bp6_framing.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'buspirate.bp6'`

- [ ] **Step 3: Vendor the generated code**

```bash
mkdir -p buspirate/bp6
SRC=$(mktemp -d)/bpio2
git clone -q https://github.com/DangerousPrototypes/BusPirate-BPIO2-flatbuffer-interface "$SRC"
git -C "$SRC" checkout -q eb89844
cp -R "$SRC/python/tooling/bpio" buspirate/bp6/bpio
cp "$SRC/LICENSE" buspirate/bp6/bpio/LICENSE
# One generated import is absolute ("from bpio.ModeConfiguration import ...");
# inside our package it must be relative.
sed -i '' 's/from bpio\./from ./' buspirate/bp6/bpio/*.py
grep -rn "from bpio\." buspirate/bp6/bpio && echo "STILL ABSOLUTE" || echo ok
```

Expected: `ok`.

Create `buspirate/bp6/bpio/SOURCE.md`:

```markdown
# Vendored BPIO2 FlatBuffers code

Generated Python for the Bus Pirate's BPIO2 schema (`bpio.fbs`), copied from
<https://github.com/DangerousPrototypes/BusPirate-BPIO2-flatbuffer-interface>
at commit `eb89844` (`python/tooling/bpio/`). Apache-2.0, see `LICENSE`.

One change: the generated absolute import `from bpio.X import X` was made
relative (`from .X import X`) so the code works inside this package.

To update: re-copy that folder at a newer commit, re-apply the import fix, and
run `pytest tests/test_bp6_*.py`.
```

Add the dependency in `pyproject.toml`:

```toml
dependencies = ["pyserial>=3.4", "flatbuffers>=25.2.10"]
```

Run: `.venv/bin/pip install -q -e ".[dev,web]"`

- [ ] **Step 4: Write `framing.py` and the package init**

```python
# buspirate/bp6/__init__.py
"""The Bus Pirate 6, driven over its BPIO2 binary interface."""
```

```python
# buspirate/bp6/framing.py
"""COBS framing for BPIO2.

Every request and every response is one FlatBuffer, COBS-encoded so it holds
no zero bytes, and ended by a single ``0x00`` (firmware src/binmode/bpio.c,
nanocobs). There is no length prefix.
"""

from __future__ import annotations

from typing import List

DELIMITER = b"\x00"


def cobs_encode(data: bytes) -> bytes:
    out = bytearray()
    block = bytearray()
    for byte in bytes(data):
        if byte == 0:
            out.append(len(block) + 1)
            out += block
            block.clear()
        else:
            block.append(byte)
            if len(block) == 254:
                out.append(0xFF)
                out += block
                block.clear()
    out.append(len(block) + 1)
    out += block
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    data = bytes(data)
    out = bytearray()
    index = 0
    while index < len(data):
        code = data[index]
        if code == 0:
            raise ValueError("a zero byte inside a COBS frame")
        index += 1
        end = index + code - 1
        if end > len(data):
            raise ValueError("a COBS frame ends early")
        chunk = data[index:end]
        if 0 in chunk:
            raise ValueError("a zero byte inside a COBS frame")
        out += chunk
        index = end
        if code < 0xFF and index < len(data):
            out.append(0)
    return bytes(out)


def frame(payload: bytes) -> bytes:
    """``payload`` ready for the wire: encoded, then the delimiter."""
    return cobs_encode(payload) + DELIMITER


class FrameReader:
    """Collects bytes off the port and hands back whole frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> List[bytes]:
        """Every frame completed by ``data``, delimiter included."""
        self._buffer += data
        frames = []
        while True:
            end = self._buffer.find(0)
            if end < 0:
                return frames
            raw = bytes(self._buffer[: end + 1])
            del self._buffer[: end + 1]
            if len(raw) > 1:
                frames.append(raw)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_bp6_framing.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add buspirate/bp6 pyproject.toml tests/test_bp6_framing.py
git commit -m "Add COBS framing and the vendored BPIO2 FlatBuffers code for the Bus Pirate 6"
```

---

### Task 2: Protocol (requests, responses, descriptions) and the link

**Files:**
- Create: `buspirate/bp6/protocol.py`, `buspirate/bp6/link.py`
- Test: `tests/test_bp6_protocol.py`

**Interfaces:**
- Consumes: `frame`, `FrameReader`, `cobs_decode` (Task 1).
- Produces (all in `buspirate.bp6.protocol`):
  - `@dataclass(frozen=True) ModeConfig(speed=20000, data_bits=8, parity=False, stop_bits=1, flow_control=False, signal_inversion=False, clock_stretch=False, clock_polarity=False, clock_phase=False, chip_select_idle=True)`
  - `@dataclass(frozen=True) Status(hardware=(0,0), flatbuffers_version=(0,0), firmware_date="", firmware_hash="", modes_available=(), mode="", pin_labels=(), max_write=512, max_read=512, psu_enabled=False, psu_set_mv=0, psu_set_ma=0, psu_mv=0, psu_ma=0, psu_tripped=False, pullups=False, adc_mv=())`
  - `@dataclass(frozen=True) Response(kind: str, error: Optional[str]=None, status: Optional[Status]=None, data: bytes=b"", is_async: bool=False)` — `kind` is `"status"`, `"configuration"`, `"data"` or `"error"`.
  - `status_request() -> bytes`
  - `configuration_request(*, mode=None, mode_config=None, psu_enable=False, psu_mv=None, psu_ma=None, psu_disable=False, pullup_enable=False, pullup_disable=False, io_direction=None, io_value=None) -> bytes` (`io_*` are `(mask, value)` tuples)
  - `data_request(*, start=False, start_alt=False, write=b"", read=0, stop=False, stop_alt=False) -> bytes`
  - `parse_response(payload: bytes) -> Response` (raises `ProtocolError` if unreadable)
  - `describe_frame(direction: str, raw: bytes) -> str` — one human line for the traffic log, `""` if not decodable.
- Produces (`buspirate.bp6.link`): `class BpioLink(serial, notify, timeout=1.0)` with `request(payload: bytes, timeout: Optional[float]=None) -> Response` (raises `ProtocolError` on no answer), `poll_async(seconds: float) -> bytes` (collects async data for up to `seconds`, returns and clears the buffer), attribute `async_rx: bytearray`, attribute `serial`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bp6_protocol.py
"""BPIO2 requests and responses, and the link that carries them."""

import flatbuffers
import pytest

from buspirate.bp6 import protocol
from buspirate.bp6.bpio import ConfigurationRequest as CR
from buspirate.bp6.bpio import DataRequest as DR
from buspirate.bp6.bpio import DataResponse as DRS
from buspirate.bp6.bpio import RequestPacket as RP
from buspirate.bp6.bpio import ResponsePacket as RS
from buspirate.bp6.bpio.RequestPacketContents import RequestPacketContents
from buspirate.bp6.bpio.ResponsePacketContents import ResponsePacketContents
from buspirate.bp6.framing import cobs_decode, frame
from buspirate.bp6.link import BpioLink
from buspirate.exceptions import ProtocolError


def _root(payload):
    packet = RP.RequestPacket.GetRootAs(payload, 0)
    return packet, packet.Contents()


def test_every_request_has_version_two_and_contents():
    for payload in (
        protocol.status_request(),
        protocol.configuration_request(psu_disable=True),
        protocol.data_request(start=True),
    ):
        packet, table = _root(payload)
        assert packet.VersionMajor() == 2
        assert packet.MinimumVersionMinor() == 0
        assert packet.ContentsType() != RequestPacketContents.NONE
        assert table is not None


def test_configuration_request_carries_mode_and_power():
    payload = protocol.configuration_request(
        mode="I2C", mode_config=protocol.ModeConfig(speed=400_000, clock_stretch=True),
        psu_enable=True, psu_mv=3300, psu_ma=100, pullup_enable=True,
    )
    packet, table = _root(payload)
    assert packet.ContentsType() == RequestPacketContents.ConfigurationRequest
    request = CR.ConfigurationRequest()
    request.Init(table.Bytes, table.Pos)
    assert request.Mode() == b"I2C"
    assert request.ModeConfiguration().Speed() == 400_000
    assert request.ModeConfiguration().ClockStretch() is True
    assert request.PsuEnable() is True
    assert request.PsuSetMv() == 3300
    assert request.PsuSetMa() == 100
    assert request.PullupEnable() is True


def test_a_mode_without_a_configuration_gets_the_defaults():
    packet, table = _root(protocol.configuration_request(mode="HiZ"))
    request = CR.ConfigurationRequest()
    request.Init(table.Bytes, table.Pos)
    assert request.ModeConfiguration() is not None


def test_no_limit_is_sent_as_zero_milliamps():
    packet, table = _root(protocol.configuration_request(psu_enable=True, psu_mv=3300, psu_ma=0))
    request = CR.ConfigurationRequest()
    request.Init(table.Bytes, table.Pos)
    assert request.PsuSetMa() == 0


def test_data_request_fields():
    packet, table = _root(protocol.data_request(start=True, write=b"\xa0\x00", read=4, stop=True))
    request = DR.DataRequest()
    request.Init(table.Bytes, table.Pos)
    assert request.StartMain() and request.StopMain()
    assert bytes(request.DataWrite(i) for i in range(request.DataWriteLength())) == b"\xa0\x00"
    assert request.BytesRead() == 4


def _data_response(data=b"", error=None, is_async=False):
    b = flatbuffers.Builder(64)
    err = b.CreateString(error) if error else None
    vec = b.CreateByteVector(data) if data else None
    DRS.DataResponseStart(b)
    if err is not None:
        DRS.DataResponseAddError(b, err)
    if vec is not None:
        DRS.DataResponseAddDataRead(b, vec)
    if is_async:
        DRS.DataResponseAddIsAsync(b, True)
    contents = DRS.DataResponseEnd(b)
    RS.ResponsePacketStart(b)
    RS.ResponsePacketAddContentsType(b, ResponsePacketContents.DataResponse)
    RS.ResponsePacketAddContents(b, contents)
    b.Finish(RS.ResponsePacketEnd(b))
    return bytes(b.Output())


def _top_error(message):
    b = flatbuffers.Builder(64)
    err = b.CreateString(message)
    RS.ResponsePacketStart(b)
    RS.ResponsePacketAddError(b, err)
    b.Finish(RS.ResponsePacketEnd(b))
    return bytes(b.Output())


def test_parse_data_response():
    response = protocol.parse_response(_data_response(b"\x58"))
    assert response.kind == "data"
    assert response.data == b"\x58"
    assert response.error is None
    assert response.is_async is False


def test_parse_top_level_error():
    response = protocol.parse_response(_top_error("Timeout waiting for flatbuffer data"))
    assert response.kind == "error"
    assert response.error == "Timeout waiting for flatbuffer data"


def test_garbage_is_a_protocol_error():
    with pytest.raises(ProtocolError):
        protocol.parse_response(b"\x01\x02")


def test_describe_frames_for_the_traffic_log():
    request = frame(protocol.data_request(start=True, write=b"\xec", read=0, stop=True))
    assert protocol.describe_frame("tx", request) == "Data: start, write ec, stop"
    assert protocol.describe_frame("rx", frame(_data_response(b"\x01\x02"))) == "Data: read 01 02"
    assert protocol.describe_frame("rx", b"\x07junk\x00") == ""


class _Port:
    """A serial stand-in that answers each request with queued frames."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.pending = bytearray()
        self.written = bytearray()

    def write(self, data):
        self.written += data
        if self.replies:
            self.pending += self.replies.pop(0)

    def read(self, count):
        out = bytes(self.pending[:count])
        del self.pending[:count]
        return out


def test_link_returns_the_reply():
    port = _Port([frame(_data_response(b"\x58"))])
    seen = []
    link = BpioLink(port, lambda d, data: seen.append(d), timeout=0.2)
    assert link.request(protocol.data_request(read=1)).data == b"\x58"
    assert seen == ["tx", "rx"]
    assert cobs_decode(bytes(port.written[:-1]))  # one frame went out


def test_async_frames_are_set_aside_while_waiting_for_a_reply():
    chatter = frame(_data_response(b"hi", is_async=True))
    port = _Port([chatter + chatter + frame(_data_response(b"\x01"))])
    link = BpioLink(port, lambda *a: None, timeout=0.2)
    assert link.request(protocol.data_request(read=1)).data == b"\x01"
    assert bytes(link.async_rx) == b"hihi"
    assert link.poll_async(0.0) == b"hihi"
    assert bytes(link.async_rx) == b""


def test_no_answer_is_a_protocol_error():
    link = BpioLink(_Port([]), lambda *a: None, timeout=0.05)
    with pytest.raises(ProtocolError):
        link.request(protocol.status_request())
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_bp6_protocol.py -q`
Expected: FAIL with `ImportError` for `buspirate.bp6.protocol`.

- [ ] **Step 3: Write `protocol.py`**

```python
# buspirate/bp6/protocol.py
"""BPIO2 requests and responses, built and read with the vendored code.

Schema: bpio.fbs in DangerousPrototypes/BusPirate-BPIO2-flatbuffer-interface.
Every request is a RequestPacket{version_major=2, minimum_version_minor=0,
contents}. A packet with no contents is never built: the firmware's handler
table has a NULL entry for it (src/binmode/bpio.c) and can crash on one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import flatbuffers

from ..exceptions import ProtocolError
from .bpio import ConfigurationRequest as _CR
from .bpio import ConfigurationResponse as _CRS
from .bpio import DataRequest as _DR
from .bpio import DataResponse as _DRS
from .bpio import ModeConfiguration as _MC
from .bpio import RequestPacket as _RP
from .bpio import ResponsePacket as _RS
from .bpio import StatusRequest as _SR
from .bpio import StatusResponse as _ST
from .bpio.RequestPacketContents import RequestPacketContents
from .bpio.ResponsePacketContents import ResponsePacketContents
from .framing import cobs_decode

VERSION_MAJOR = 2


@dataclass(frozen=True)
class ModeConfig:
    speed: int = 20000
    data_bits: int = 8
    parity: bool = False
    stop_bits: int = 1
    flow_control: bool = False
    signal_inversion: bool = False
    clock_stretch: bool = False
    clock_polarity: bool = False
    clock_phase: bool = False
    chip_select_idle: bool = True


@dataclass(frozen=True)
class Status:
    hardware: Tuple[int, int] = (0, 0)
    flatbuffers_version: Tuple[int, int] = (0, 0)
    firmware_date: str = ""
    firmware_hash: str = ""
    modes_available: Tuple[str, ...] = ()
    mode: str = ""
    pin_labels: Tuple[str, ...] = ()
    max_write: int = 512
    max_read: int = 512
    psu_enabled: bool = False
    psu_set_mv: int = 0
    psu_set_ma: int = 0
    psu_mv: int = 0
    psu_ma: int = 0
    psu_tripped: bool = False
    pullups: bool = False
    adc_mv: Tuple[int, ...] = ()


@dataclass(frozen=True)
class Response:
    kind: str
    error: Optional[str] = None
    status: Optional[Status] = None
    data: bytes = b""
    is_async: bool = False


# -- requests ----------------------------------------------------------------


def _packet(builder, contents_type: int, contents: int) -> bytes:
    assert contents_type != RequestPacketContents.NONE
    _RP.RequestPacketStart(builder)
    _RP.RequestPacketAddVersionMajor(builder, VERSION_MAJOR)
    _RP.RequestPacketAddMinimumVersionMinor(builder, 0)
    _RP.RequestPacketAddContentsType(builder, contents_type)
    _RP.RequestPacketAddContents(builder, contents)
    builder.Finish(_RP.RequestPacketEnd(builder))
    return bytes(builder.Output())


def status_request() -> bytes:
    """Ask for everything: an empty query list means All."""
    builder = flatbuffers.Builder(64)
    _SR.StatusRequestStart(builder)
    return _packet(builder, RequestPacketContents.StatusRequest, _SR.StatusRequestEnd(builder))


def _mode_config(builder, config: ModeConfig) -> int:
    _MC.ModeConfigurationStart(builder)
    _MC.ModeConfigurationAddSpeed(builder, config.speed)
    _MC.ModeConfigurationAddDataBits(builder, config.data_bits)
    _MC.ModeConfigurationAddParity(builder, config.parity)
    _MC.ModeConfigurationAddStopBits(builder, config.stop_bits)
    _MC.ModeConfigurationAddFlowControl(builder, config.flow_control)
    _MC.ModeConfigurationAddSignalInversion(builder, config.signal_inversion)
    _MC.ModeConfigurationAddClockStretch(builder, config.clock_stretch)
    _MC.ModeConfigurationAddClockPolarity(builder, config.clock_polarity)
    _MC.ModeConfigurationAddClockPhase(builder, config.clock_phase)
    _MC.ModeConfigurationAddChipSelectIdle(builder, config.chip_select_idle)
    return _MC.ModeConfigurationEnd(builder)


def configuration_request(
    *,
    mode: Optional[str] = None,
    mode_config: Optional[ModeConfig] = None,
    psu_enable: bool = False,
    psu_mv: Optional[int] = None,
    psu_ma: Optional[int] = None,
    psu_disable: bool = False,
    pullup_enable: bool = False,
    pullup_disable: bool = False,
    io_direction: Optional[Tuple[int, int]] = None,
    io_value: Optional[Tuple[int, int]] = None,
) -> bytes:
    """One ConfigurationRequest. A mode always travels with its configuration:
    the firmware requires ``mode_configuration`` whenever ``mode`` is set."""
    builder = flatbuffers.Builder(128)
    mode_name = builder.CreateString(mode) if mode is not None else None
    mode_table = _mode_config(builder, mode_config or ModeConfig()) if mode is not None else None
    _CR.ConfigurationRequestStart(builder)
    if mode_name is not None:
        _CR.ConfigurationRequestAddMode(builder, mode_name)
        _CR.ConfigurationRequestAddModeConfiguration(builder, mode_table)
    if psu_enable:
        _CR.ConfigurationRequestAddPsuEnable(builder, True)
        _CR.ConfigurationRequestAddPsuSetMv(builder, int(psu_mv if psu_mv is not None else 3300))
        _CR.ConfigurationRequestAddPsuSetMa(builder, int(psu_ma if psu_ma is not None else 300))
    if psu_disable:
        _CR.ConfigurationRequestAddPsuDisable(builder, True)
    if pullup_enable:
        _CR.ConfigurationRequestAddPullupEnable(builder, True)
    if pullup_disable:
        _CR.ConfigurationRequestAddPullupDisable(builder, True)
    if io_direction is not None:
        _CR.ConfigurationRequestAddIoDirectionMask(builder, io_direction[0])
        _CR.ConfigurationRequestAddIoDirection(builder, io_direction[1])
    if io_value is not None:
        _CR.ConfigurationRequestAddIoValueMask(builder, io_value[0])
        _CR.ConfigurationRequestAddIoValue(builder, io_value[1])
    return _packet(
        builder, RequestPacketContents.ConfigurationRequest, _CR.ConfigurationRequestEnd(builder)
    )


def data_request(
    *,
    start: bool = False,
    start_alt: bool = False,
    write: bytes = b"",
    read: int = 0,
    stop: bool = False,
    stop_alt: bool = False,
) -> bytes:
    builder = flatbuffers.Builder(64 + len(write))
    vector = builder.CreateByteVector(bytes(write)) if write else None
    _DR.DataRequestStart(builder)
    if start:
        _DR.DataRequestAddStartMain(builder, True)
    if start_alt:
        _DR.DataRequestAddStartAlt(builder, True)
    if vector is not None:
        _DR.DataRequestAddDataWrite(builder, vector)
    if read:
        _DR.DataRequestAddBytesRead(builder, int(read))
    if stop:
        _DR.DataRequestAddStopMain(builder, True)
    if stop_alt:
        _DR.DataRequestAddStopAlt(builder, True)
    return _packet(builder, RequestPacketContents.DataRequest, _DR.DataRequestEnd(builder))


# -- responses ---------------------------------------------------------------


def _text(value) -> Optional[str]:
    if not value:
        return None
    return value.decode("utf-8", "replace")


def _strings(count: int, get) -> Tuple[str, ...]:
    return tuple(_text(get(index)) or "" for index in range(count))


def _status(table) -> Status:
    return Status(
        hardware=(table.VersionHardwareMajor(), table.VersionHardwareMinor()),
        flatbuffers_version=(table.VersionFlatbuffersMajor(), table.VersionFlatbuffersMinor()),
        firmware_date=_text(table.VersionFirmwareDate()) or "",
        firmware_hash=_text(table.VersionFirmwareGitHash()) or "",
        modes_available=_strings(table.ModesAvailableLength(), table.ModesAvailable),
        mode=_text(table.ModeCurrent()) or "",
        pin_labels=_strings(table.ModePinLabelsLength(), table.ModePinLabels),
        max_write=table.ModeMaxWrite(),
        max_read=table.ModeMaxRead(),
        psu_enabled=bool(table.PsuEnabled()),
        psu_set_mv=table.PsuSetMv(),
        psu_set_ma=table.PsuSetMa(),
        psu_mv=table.PsuMeasuredMv(),
        psu_ma=table.PsuMeasuredMa(),
        psu_tripped=bool(table.PsuCurrentError()),
        pullups=bool(table.PullupEnabled()),
        adc_mv=tuple(table.AdcMv(index) for index in range(table.AdcMvLength())),
    )


def parse_response(payload: bytes) -> Response:
    try:
        packet = _RS.ResponsePacket.GetRootAs(bytes(payload), 0)
        top_error = _text(packet.Error())
        kind = packet.ContentsType()
        table = packet.Contents()
        if kind == ResponsePacketContents.StatusResponse:
            status = _ST.StatusResponse()
            status.Init(table.Bytes, table.Pos)
            return Response("status", error=top_error or _text(status.Error()), status=_status(status))
        if kind == ResponsePacketContents.ConfigurationResponse:
            config = _CRS.ConfigurationResponse()
            config.Init(table.Bytes, table.Pos)
            return Response("configuration", error=top_error or _text(config.Error()))
        if kind == ResponsePacketContents.DataResponse:
            data = _DRS.DataResponse()
            data.Init(table.Bytes, table.Pos)
            read = bytes(data.DataRead(index) for index in range(data.DataReadLength()))
            return Response(
                "data", error=top_error or _text(data.Error()), data=read,
                is_async=bool(data.IsAsync()),
            )
    except Exception as exc:  # noqa: BLE001 - any decode failure is the same fault
        raise ProtocolError(f"the Bus Pirate 6 sent an unreadable BPIO2 reply: {exc}") from exc
    return Response("error", error=top_error or "the Bus Pirate 6 sent an empty reply")


# -- the traffic log ---------------------------------------------------------


def _hex(data: bytes) -> str:
    return data.hex(" ") if len(data) <= 16 else f"{data[:16].hex(' ')} … ({len(data)} bytes)"


def _describe_request(payload: bytes) -> str:
    packet = _RP.RequestPacket.GetRootAs(payload, 0)
    kind, table = packet.ContentsType(), packet.Contents()
    if kind == RequestPacketContents.StatusRequest:
        return "Status request"
    if kind == RequestPacketContents.ConfigurationRequest:
        request = _CR.ConfigurationRequest()
        request.Init(table.Bytes, table.Pos)
        parts = []
        if request.Mode():
            parts.append(f"mode {request.Mode().decode()}")
        if request.PsuEnable():
            limit = request.PsuSetMa()
            parts.append(f"power on {request.PsuSetMv()} mV / {limit or 'no limit'}"
                         f"{' mA' if limit else ''}")
        if request.PsuDisable():
            parts.append("power off")
        if request.PullupEnable():
            parts.append("pull-ups on")
        if request.PullupDisable():
            parts.append("pull-ups off")
        return "Config: " + (", ".join(parts) or "nothing")
    request = _DR.DataRequest()
    request.Init(table.Bytes, table.Pos)
    parts = []
    if request.StartMain() or request.StartAlt():
        parts.append("start")
    written = bytes(request.DataWrite(i) for i in range(request.DataWriteLength()))
    if written:
        parts.append(f"write {_hex(written)}")
    if request.BytesRead():
        parts.append(f"read {request.BytesRead()}")
    if request.StopMain() or request.StopAlt():
        parts.append("stop")
    return "Data: " + ", ".join(parts)


def _describe_response(payload: bytes) -> str:
    response = parse_response(payload)
    if response.error:
        return f"Error: {response.error}"
    if response.kind == "status":
        s = response.status
        return f"Status: {s.mode}, power {'on' if s.psu_enabled else 'off'} {s.psu_mv} mV {s.psu_ma} mA"
    if response.kind == "configuration":
        return "Config: OK"
    label = "UART in" if response.is_async else "Data"
    return f"{label}: read {_hex(response.data)}" if response.data else f"{label}: OK"


def describe_frame(direction: str, raw: bytes) -> str:
    """One line for the traffic log, or ``""`` if the frame cannot be read."""
    try:
        payload = cobs_decode(bytes(raw).rstrip(b"\x00"))
        return _describe_request(payload) if direction == "tx" else _describe_response(payload)
    except Exception:  # noqa: BLE001 - a log line must never break the bus
        return ""
```

- [ ] **Step 4: Write `link.py`**

```python
# buspirate/bp6/link.py
"""One BPIO2 request, one reply, over the board's binary port.

In UART mode the firmware also sends unsolicited DataResponses with
``is_async`` set, whenever the target transmits. They can arrive before the
reply to whatever was asked, so they are set aside in ``async_rx`` rather
than mistaken for it.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Callable, Deque, Optional

from ..exceptions import ProtocolError
from .framing import FrameReader, cobs_decode, frame
from .protocol import Response, parse_response


class BpioLink:
    def __init__(self, serial, notify: Callable[[str, bytes], None], timeout: float = 1.0) -> None:
        self.serial = serial
        self._notify = notify
        self.timeout = timeout
        self._reader = FrameReader()
        self._frames: Deque[bytes] = deque()
        self.async_rx = bytearray()

    def request(self, payload: bytes, timeout: Optional[float] = None) -> Response:
        raw = frame(payload)
        self.serial.write(raw)
        flush = getattr(self.serial, "flush", None)
        if flush is not None:
            flush()
        self._notify("tx", raw)
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while True:
            response = self._next(deadline)
            if response is None:
                raise ProtocolError(
                    "the Bus Pirate 6 did not answer on its BPIO2 port. Is BPIO2 "
                    "selected (binmode, option 2)?"
                )
            if response.is_async:
                self.async_rx += response.data
                continue
            return response

    def poll_async(self, seconds: float) -> bytes:
        """Gather async data for up to ``seconds``; return it and clear it."""
        deadline = time.monotonic() + seconds
        while True:
            response = self._next(deadline)
            if response is None:
                break
            if response.is_async:
                self.async_rx += response.data
        data = bytes(self.async_rx)
        self.async_rx.clear()
        return data

    def _next(self, deadline: float) -> Optional[Response]:
        while True:
            if self._frames:
                return parse_response(cobs_decode(self._frames.popleft()[:-1]))
            if time.monotonic() >= deadline:
                return None
            chunk = self.serial.read(256)
            if not chunk:
                time.sleep(0.002)
                continue
            for raw in self._reader.feed(chunk):
                self._notify("rx", raw)
                self._frames.append(raw)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_bp6_protocol.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add buspirate/bp6/protocol.py buspirate/bp6/link.py tests/test_bp6_protocol.py
git commit -m "Build and read BPIO2 packets, and carry them over the Bus Pirate 6's binary port"
```

---

### Task 3: The BP6 simulator

**Files:**
- Create: `buspirate/simulator_bp6.py`
- Test: `tests/test_bp6_simulator.py`

**Interfaces:**
- Consumes: `framing`, `protocol` (Tasks 1–2), `FakeFlash` from `buspirate.simulator`.
- Produces: `class FakeBp6(bpio_active=True, color_prompt=False, load_ma=12)` with
  - attributes `binary` and `terminal` (fake serial objects with `write`, `read`, `flush`, `reset_input_buffer`, `close`, `written`)
  - `factory(terminal_port: str, binary_port: str)` → a `serial_factory(port, baudrate, timeout)` returning the right fake by port name
  - state: `mode` (str), `psu_enabled`, `psu_mv`, `psu_ma`, `pullups`, `bpio_active`, `color_prompt`, `load_ma`, `requests` (list of decoded request kinds), `i2c_devices` (`{0x76: bytearray(256)}` with `[0xD0] = 0x58`, a BMP280 id), `flash` (`FakeFlash`), `onewire_rom` (8 bytes, DS18B20 family `0x28` with a valid CRC), `uart_echo` (True)
  - `uart_receive(data: bytes)` — the target transmits: queue an async DataResponse.
  - constants `TERMINAL = "/dev/cu.usbmodem6buspirate1"`, `BINARY = "/dev/cu.usbmodem6buspirate3"`.

Simulated behaviour (keep it to exactly this):
- Binary port: a write that ends a frame (`0x00`) is decoded with the vendored *request* readers; if `bpio_active` is False nothing is answered.
- Status: hardware (6, 2), flatbuffers (2, 0), date `Oct 12 2026 09:05:15`, hash `unknown`, modes `HiZ 1WIRE UART HDUART I2C SPI 2WIRE 3WIRE DIO LED INFRARED JTAG PS2 USB`, pin labels per mode (HiZ: `OFF` + 8 empty + `GND`; I2C: `VOUT SDA SCL - - - - - - GND`; SPI: `VOUT - - - - MISO CS CLK MOSI GND`; UART: `VOUT - - - - TX RX - - GND`; 1WIRE: `VOUT OWD - - - - - - - GND`), psu measured = set mV when on and `load_ma` mA, `adc_mv` = psu mv on IO pins when pull-ups are on else 0.
- Configuration: mode switch to one of `HiZ 1WIRE I2C SPI UART LED` (case-insensitive; else error `Invalid mode name`); PSU: enable with mV outside 800–5000 → error `PSU voltage out of range`; if `0 < psu_ma < load_ma` the PSU trips (`psu_enabled=False`, tripped=True); disable clears trip; pull-ups on/off.
- Data in I2C: `write[0] >> 1` is the address; unknown address → error `Protocol request failed`; `write[1]` (if any) sets the register pointer, further bytes are written; `read` bytes come from the pointer upward.
- Data in SPI: `start` begins a transaction; written bytes accumulate across requests until the next `start`, and reads are served from `FakeFlash.exchange(all_written, already_read + count)` so a read split over several requests continues where it left off.
- Data in 1WIRE: `start` with `onewire_rom` set → presence OK, else error `Protocol request failed`; write `[0x33]` + read 8 → the ROM.
- Data in UART: written bytes are echoed back as an async frame when `uart_echo`.
- Terminal port: `\x03` → `\r\nHiZ> `; when `color_prompt` and the first complete write is `n\r` → clears it and prints `HiZ> `; a write of `\r` alone while `color_prompt` → re-prints the prompt; `binmode\r` → menu ending `x to exit (1) > `; `2\r` → `Save setting?\r\ny/n > `; `n\r` after that → sets `bpio_active=True`, prints `HiZ> `; `i\r` → a 3-line info block ending `HiZ> `; anything else → `Invalid command`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bp6_simulator.py
"""The simulated Bus Pirate 6 answers BPIO2 the way the real board did."""

from buspirate.bp6 import protocol
from buspirate.bp6.link import BpioLink
from buspirate.simulator_bp6 import FakeBp6


def link_to(fake):
    return BpioLink(fake.binary, lambda *a: None, timeout=0.2)


def test_status_matches_the_real_board():
    status = link_to(FakeBp6()).request(protocol.status_request()).status
    assert status.hardware == (6, 2)
    assert status.firmware_date == "Oct 12 2026 09:05:15"
    assert status.firmware_hash == "unknown"
    assert "I2C" in status.modes_available and status.mode == "HiZ"
    assert len(status.adc_mv) == 8
    assert status.max_read == 512


def test_power_and_trip():
    fake = FakeBp6(load_ma=50)
    link = link_to(fake)
    link.request(protocol.configuration_request(psu_enable=True, psu_mv=3300, psu_ma=300))
    status = link.request(protocol.status_request()).status
    assert status.psu_enabled and status.psu_mv == 3300 and status.psu_ma == 50
    link.request(protocol.configuration_request(psu_enable=True, psu_mv=3300, psu_ma=20))
    status = link.request(protocol.status_request()).status
    assert status.psu_tripped and not status.psu_enabled


def test_i2c_register_read():
    fake = FakeBp6()
    link = link_to(fake)
    link.request(protocol.configuration_request(mode="I2C"))
    reply = link.request(protocol.data_request(start=True, write=b"\xec\xd0", read=1, stop=True))
    assert reply.data == b"\x58"
    missing = link.request(protocol.data_request(start=True, write=b"\x20", stop=True))
    assert missing.error == "Protocol request failed"


def test_spi_jedec_id():
    link = link_to(FakeBp6())
    link.request(protocol.configuration_request(mode="SPI"))
    reply = link.request(protocol.data_request(start=True, write=b"\x9f", read=3, stop=True))
    assert reply.data == b"\xef\x40\x18"


def test_uart_echo_is_async():
    fake = FakeBp6()
    link = link_to(fake)
    link.request(protocol.configuration_request(mode="UART"))
    link.request(protocol.data_request(write=b"hi"))
    assert link.poll_async(0.05) == b"hi"


def test_nothing_answers_while_bpio2_is_off():
    fake = FakeBp6(bpio_active=False)
    fake.binary.write(b"\x02\x11\x00")
    assert fake.binary.read(64) == b""


def test_the_terminal_switches_bpio2_on():
    fake = FakeBp6(bpio_active=False, color_prompt=True)
    for keys in (b"\x03", b"n\r", b"binmode\r", b"2\r", b"n\r"):
        fake.terminal.write(keys)
    assert fake.bpio_active
    assert fake.terminal.read(4096).endswith(b"HiZ> ")
```

(If `FakeFlash`'s JEDEC ID differs from `ef 40 18`, use whatever `buspirate/simulator.py` `FakeFlash` returns for `0x9F` and change the assertion to match — check it in Step 3.)

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_bp6_simulator.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'buspirate.simulator_bp6'`.

- [ ] **Step 3: Write `simulator_bp6.py`**

```python
# buspirate/simulator_bp6.py
"""A simulated Bus Pirate 6: its BPIO2 port and its terminal port.

Built from what the real board did on 2026-10-14 (see the design spec), so
the dashboard and the tests can run with no hardware. It answers only what
the driver asks; it is not a firmware emulator.
"""

from __future__ import annotations

import flatbuffers

from .bp6.bpio import ConfigurationRequest as _CR
from .bp6.bpio import ConfigurationResponse as _CRS
from .bp6.bpio import DataRequest as _DR
from .bp6.bpio import DataResponse as _DRS
from .bp6.bpio import RequestPacket as _RP
from .bp6.bpio import ResponsePacket as _RS
from .bp6.bpio import StatusResponse as _ST
from .bp6.bpio.RequestPacketContents import RequestPacketContents
from .bp6.bpio.ResponsePacketContents import ResponsePacketContents
from .bp6.framing import FrameReader, cobs_decode, frame
from .simulator import FakeFlash

MODES = ("HiZ", "1WIRE", "UART", "HDUART", "I2C", "SPI", "2WIRE", "3WIRE",
         "DIO", "LED", "INFRARED", "JTAG", "PS2", "USB")
BPIO_MODES = ("HiZ", "1WIRE", "I2C", "SPI", "UART", "LED")
PIN_LABELS = {
    "HiZ": ["OFF"] + [""] * 8 + ["GND"],
    "I2C": ["VOUT", "SDA", "SCL", "", "", "", "", "", "", "GND"],
    "SPI": ["VOUT", "", "", "", "", "MISO", "CS", "CLK", "MOSI", "GND"],
    "UART": ["VOUT", "", "", "", "", "TX", "RX", "", "", "GND"],
    "1WIRE": ["VOUT", "OWD", "", "", "", "", "", "", "", "GND"],
    "LED": ["VOUT", "SDO", "", "", "", "", "", "", "", "GND"],
}


def _crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        for _ in range(8):
            mix = (crc ^ byte) & 1
            crc >>= 1
            if mix:
                crc ^= 0x8C
            byte >>= 1
    return crc


_ROM7 = bytes([0x28, 0xFF, 0x4C, 0x1A, 0x61, 0x16, 0x04])
DS18B20_ROM = _ROM7 + bytes([_crc8(_ROM7)])


class _Port:
    def __init__(self, on_write) -> None:
        self._on_write = on_write
        self.out = bytearray()
        self.written = bytearray()
        self.is_open = True

    def write(self, data: bytes) -> int:
        self.written += data
        self._on_write(bytes(data))
        return len(data)

    def read(self, count: int) -> bytes:
        data = bytes(self.out[:count])
        del self.out[:count]
        return data

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        self.out.clear()

    def close(self) -> None:
        self.is_open = False


class FakeBp6:
    TERMINAL = "/dev/cu.usbmodem6buspirate1"
    BINARY = "/dev/cu.usbmodem6buspirate3"

    def __init__(self, bpio_active: bool = True, color_prompt: bool = False, load_ma: int = 12) -> None:
        self.bpio_active = bpio_active
        self.color_prompt = color_prompt
        self.load_ma = load_ma
        self.mode = "HiZ"
        self.psu_enabled = False
        self.psu_tripped = False
        self.psu_mv = 0
        self.psu_ma = 0
        self.pullups = False
        self.requests = []
        device = bytearray(256)
        device[0xD0] = 0x58
        self.i2c_devices = {0x76: device}
        self._pointer = {0x76: 0}
        self.flash = FakeFlash()
        self.onewire_rom = DS18B20_ROM
        self.uart_echo = True
        self._spi_written, self._spi_read = bytearray(), 0
        self._reader = FrameReader()
        self._terminal_state = "prompt"
        self.binary = _Port(self._on_binary)
        self.terminal = _Port(self._on_terminal)

    def factory(self, terminal_port: str = TERMINAL, binary_port: str = BINARY):
        def make(port, baudrate, timeout):
            if port == terminal_port:
                self.terminal.is_open = True
                return self.terminal
            self.binary.is_open = True
            return self.binary
        return make

    # -- the target ----------------------------------------------------------

    def uart_receive(self, data: bytes) -> None:
        self.binary.out += frame(self._data_response(bytes(data), is_async=True))

    # -- BPIO2 ---------------------------------------------------------------

    def _on_binary(self, data: bytes) -> None:
        for raw in self._reader.feed(data):
            if not self.bpio_active:
                continue
            packet = _RP.RequestPacket.GetRootAs(cobs_decode(raw[:-1]), 0)
            kind, table = packet.ContentsType(), packet.Contents()
            if kind == RequestPacketContents.StatusRequest:
                self.requests.append("status")
                reply = self._status_response()
            elif kind == RequestPacketContents.ConfigurationRequest:
                self.requests.append("configuration")
                request = _CR.ConfigurationRequest()
                request.Init(table.Bytes, table.Pos)
                reply = self._configure(request)
            elif kind == RequestPacketContents.DataRequest:
                self.requests.append("data")
                request = _DR.DataRequest()
                request.Init(table.Bytes, table.Pos)
                reply = self._data(request)
            else:
                raise AssertionError("a RequestPacket with no contents was sent")
            self.binary.out += frame(reply)

    def _status_response(self) -> bytes:
        b = flatbuffers.Builder(512)
        strings = lambda items: [b.CreateString(s) for s in items]  # noqa: E731

        def vector(start, offsets):
            start(b, len(offsets))
            for offset in reversed(offsets):
                b.PrependUOffsetTRelative(offset)
            return b.EndVector()

        modes = vector(_ST.StatusResponseStartModesAvailableVector, strings(MODES))
        labels = vector(_ST.StatusResponseStartModePinLabelsVector, strings(PIN_LABELS[self.mode]))
        adc = [self.psu_mv if (self.pullups and self.psu_enabled) else 0] * 8
        _ST.StatusResponseStartAdcMvVector(b, 8)
        for value in reversed(adc):
            b.PrependUint32(value)
        adc_vec = b.EndVector()
        date, git, mode = (b.CreateString("Oct 12 2026 09:05:15"), b.CreateString("unknown"),
                           b.CreateString(self.mode))
        _ST.StatusResponseStart(b)
        _ST.StatusResponseAddVersionFlatbuffersMajor(b, 2)
        _ST.StatusResponseAddVersionHardwareMajor(b, 6)
        _ST.StatusResponseAddVersionHardwareMinor(b, 2)
        _ST.StatusResponseAddVersionFirmwareGitHash(b, git)
        _ST.StatusResponseAddVersionFirmwareDate(b, date)
        _ST.StatusResponseAddModesAvailable(b, modes)
        _ST.StatusResponseAddModeCurrent(b, mode)
        _ST.StatusResponseAddModePinLabels(b, labels)
        _ST.StatusResponseAddModeBitorderMsb(b, True)
        _ST.StatusResponseAddModeMaxPacketSize(b, 640)
        _ST.StatusResponseAddModeMaxWrite(b, 512)
        _ST.StatusResponseAddModeMaxRead(b, 512)
        _ST.StatusResponseAddPsuEnabled(b, self.psu_enabled)
        _ST.StatusResponseAddPsuSetMv(b, self.psu_mv)
        _ST.StatusResponseAddPsuSetMa(b, self.psu_ma)
        _ST.StatusResponseAddPsuMeasuredMv(b, self.psu_mv if self.psu_enabled else 22)
        _ST.StatusResponseAddPsuMeasuredMa(b, self.load_ma if self.psu_enabled else 1)
        _ST.StatusResponseAddPsuCurrentError(b, self.psu_tripped)
        _ST.StatusResponseAddPullupEnabled(b, self.pullups)
        _ST.StatusResponseAddAdcMv(b, adc_vec)
        _ST.StatusResponseAddLedCount(b, 18)
        return self._packet(b, ResponsePacketContents.StatusResponse, _ST.StatusResponseEnd(b))

    def _configure(self, request) -> bytes:
        error = None
        if request.Mode():
            name = request.Mode().decode()
            match = next((m for m in BPIO_MODES if m.lower() == name.lower()), None)
            if match is None:
                error = "Invalid mode name"
            else:
                self.mode = match
        if error is None and request.PsuEnable():
            if not 800 <= request.PsuSetMv() <= 5000:
                error = "PSU voltage out of range"
            else:
                self.psu_mv, self.psu_ma = request.PsuSetMv(), request.PsuSetMa()
                self.psu_tripped = 0 < self.psu_ma < self.load_ma
                self.psu_enabled = not self.psu_tripped
        if request.PsuDisable():
            self.psu_enabled = False
            self.psu_tripped = False
        if request.PullupEnable():
            self.pullups = True
        if request.PullupDisable():
            self.pullups = False
        b = flatbuffers.Builder(64)
        err = b.CreateString(error) if error else None
        _CRS.ConfigurationResponseStart(b)
        if err is not None:
            _CRS.ConfigurationResponseAddError(b, err)
        return self._packet(b, ResponsePacketContents.ConfigurationResponse,
                            _CRS.ConfigurationResponseEnd(b))

    def _data(self, request) -> bytes:
        written = bytes(request.DataWrite(i) for i in range(request.DataWriteLength()))
        count = request.BytesRead()
        if self.mode == "I2C":
            if not written:
                return self._data_response(b"")  # a stop-only request
            address = written[0] >> 1
            device = self.i2c_devices.get(address)
            if device is None:
                return self._data_response(b"", error="Protocol request failed")
            if len(written) > 1:
                self._pointer[address] = written[1]
                for offset, byte in enumerate(written[2:]):
                    device[(written[1] + 1 + offset) & 0xFF] = byte
            start = self._pointer[address]
            return self._data_response(bytes(device[(start + i) & 0xFF] for i in range(count)))
        if self.mode == "SPI":
            # One CS-low transaction can span several requests (long reads are
            # split at 512 bytes), so keep what was written since start and how
            # much has been read, and replay it through FakeFlash.
            if request.StartMain() or request.StartAlt():
                self._spi_written, self._spi_read = bytearray(), 0
            self._spi_written += written
            data = b""
            if count:
                whole = self.flash.exchange(bytes(self._spi_written), self._spi_read + count)
                data = whole[self._spi_read:]
                self._spi_read += count
            return self._data_response(data)
        if self.mode == "1WIRE":
            if (request.StartMain() or request.StartAlt()) and not self.onewire_rom:
                return self._data_response(b"", error="Protocol request failed")
            if written[:1] == b"\x33":
                return self._data_response(self.onewire_rom[:count])
            return self._data_response(bytes(count))
        if self.mode == "UART":
            if written and self.uart_echo:
                self.uart_receive(written)
            return self._data_response(b"")
        return self._data_response(b"", error="Invalid mode")

    def _data_response(self, data: bytes, error=None, is_async=False) -> bytes:
        b = flatbuffers.Builder(64 + len(data))
        err = b.CreateString(error) if error else None
        vec = b.CreateByteVector(data) if data else None
        _DRS.DataResponseStart(b)
        if err is not None:
            _DRS.DataResponseAddError(b, err)
        if vec is not None:
            _DRS.DataResponseAddDataRead(b, vec)
        if is_async:
            _DRS.DataResponseAddIsAsync(b, True)
        return self._packet(b, ResponsePacketContents.DataResponse, _DRS.DataResponseEnd(b))

    @staticmethod
    def _packet(b, kind, contents) -> bytes:
        _RS.ResponsePacketStart(b)
        _RS.ResponsePacketAddContentsType(b, kind)
        _RS.ResponsePacketAddContents(b, contents)
        b.Finish(_RS.ResponsePacketEnd(b))
        return bytes(b.Output())

    # -- the text terminal ----------------------------------------------------

    def _say(self, text: str) -> None:
        self.terminal.out += text.encode()

    def _on_terminal(self, keys: bytes) -> None:
        if keys == b"\x03":
            self._say("^C\r\n" + ("VT100 compatible color mode? (Y/n)> " if self.color_prompt else "HiZ> "))
            return
        if self.color_prompt:
            if keys in (b"n\r", b"y\r"):
                self.color_prompt = False
                self._say(keys.decode()[0] + "\n\r\n\r\nHiZ> ")
            else:
                self._say("\n\r\n\r\nVT100 compatible color mode? (Y/n)> ")
            return
        line = keys.decode("ascii", "replace")
        if self._terminal_state == "binmode-menu" and line == "2\r":
            self._terminal_state = "binmode-save"
            self._say("2\n\r\n\r\nBinmode selected: BPIO2 flatbuffer interface\r\nSave setting?\r\ny/n > ")
        elif self._terminal_state == "binmode-save" and line in ("n\r", "y\r"):
            self._terminal_state = "prompt"
            self.bpio_active = True
            self._say(line[0] + "\n\r\n\r\nHiZ> ")
        elif line == "binmode\r":
            self._terminal_state = "binmode-menu"
            self._say("binmode\n\r\n 1. SUMP logic analyzer\r\n 2. BPIO2 flatbuffer interface\r\n"
                      "Select binary mode\r\nx to exit (1) > ")
        elif line == "i\r":
            self._say("i\n\r\nBus Pirate 6\r\nFirmware main branch @ unknown (Oct 12 2026 09:04:39)\r\n"
                      "RP2350B with 512KB RAM, 128Mbit FLASH\r\n\r\nHiZ> ")
        elif line == "\r":
            self._say("\n\r\nHiZ> ")
        else:
            self._say(f"{line.strip()}\n\r\nInvalid command: {line.strip()}. Type ? for help.\r\nHiZ> ")
```

Check `FakeFlash` in `buspirate/simulator.py` (lines 35–100): confirm `exchange(written, read_count)` returns the JEDEC ID for `b"\x9f"` and what that ID is; fix the test's expected bytes if it differs. If `EndVector` in the installed flatbuffers needs a length argument (`b.EndVector(len)` on old versions), use the form the installed version wants — `python -c "import flatbuffers, inspect; print(inspect.signature(flatbuffers.Builder.EndVector))"`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_bp6_simulator.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add buspirate/simulator_bp6.py tests/test_bp6_simulator.py
git commit -m "Simulate a Bus Pirate 6's BPIO2 and terminal ports for tests and the demo"
```

---

### Task 4: Profile and capabilities for the BP6

**Files:**
- Modify: `buspirate/device.py`
- Test: `tests/test_bp6_profile.py`

**Interfaces:**
- Consumes: `Status` (Task 2).
- Produces: constants `CAP_PSU_PROGRAMMABLE = "psu_programmable"`, `CAP_PSU_READOUT = "psu_current_readout"`; `capabilities_for("bp6")`; `parse_bp6_status(status: Optional[Status]) -> DeviceProfile` with `variant="bp6"`, `firmware` like `"2026-10-12"` (plus ` (abc1234)` when the hash is not `unknown`), `devid` like `"hw 6.2"`, `banner` a one-line summary; `DeviceProfile.describe()` → `"Bus Pirate 6, firmware 2026-10-12"`, or `"Bus Pirate 5 (untested), firmware …"` for hardware major 5.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bp6_profile.py
from buspirate import device as d
from buspirate.bp6.protocol import Status


def status(**kw):
    base = dict(hardware=(6, 2), firmware_date="Oct 12 2026 09:05:15", firmware_hash="unknown",
                flatbuffers_version=(2, 0))
    base.update(kw)
    return Status(**base)


def test_profile_from_status():
    profile = d.parse_bp6_status(status())
    assert profile.variant == "bp6"
    assert profile.firmware == "2026-10-12"
    assert profile.devid == "hw 6.2"
    assert profile.describe() == "Bus Pirate 6, firmware 2026-10-12"


def test_a_real_git_hash_is_kept():
    assert d.parse_bp6_status(status(firmware_hash="322c452")).firmware == "2026-10-12 (322c452)"


def test_a_bus_pirate_5_is_named_and_marked_untested():
    assert d.parse_bp6_status(status(hardware=(5, 10))).describe().startswith("Bus Pirate 5 (untested)")


def test_capabilities():
    caps = d.capabilities_for("bp6")
    for present in (d.CAP_SUPPLIES, d.CAP_ONEWIRE, d.CAP_SPI_MODES, d.CAP_UART_BUFFERED,
                    d.CAP_SPI_FLASH_PROGRAM, d.CAP_PSU_PROGRAMMABLE, d.CAP_PSU_READOUT):
        assert present in caps
    for absent in (d.CAP_BITBANG_PINS, d.CAP_RAWWIRE, d.CAP_SNIFFER, d.CAP_UART_BRIDGE,
                   d.CAP_PWM, d.CAP_FREQUENCY, d.CAP_PULLUP_VOLTAGE, d.CAP_SELF_TEST,
                   d.CAP_EXTENDED_AUX, d.CAP_ADC):
        assert absent not in caps


def test_missing_psu_capability_names_the_bp6():
    import pytest
    from buspirate.exceptions import UnsupportedFeatureError
    with pytest.raises(UnsupportedFeatureError, match="Bus Pirate 6"):
        d.parse_banner("Bus Pirate v4").require(d.CAP_PSU_PROGRAMMABLE)


def test_an_unknown_date_is_kept_as_is():
    assert d.parse_bp6_status(status(firmware_date="someday")).firmware == "someday"


def test_no_status_still_gives_a_bp6_profile():
    assert d.parse_bp6_status(None).variant == "bp6"
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_bp6_profile.py -q`
Expected: FAIL with `AttributeError: module 'buspirate.device' has no attribute 'parse_bp6_status'`.

- [ ] **Step 3: Implement in `buspirate/device.py`**

After `CAP_SPI_FLASH_PROGRAM = ...` add:

```python
# The Bus Pirate 6's programmable supply: set volts and a current limit, and
# read back what the target draws.
CAP_PSU_PROGRAMMABLE = "psu_programmable"
CAP_PSU_READOUT = "psu_current_readout"
```

In `_CAPABILITY_HOME` add:

```python
    CAP_PSU_PROGRAMMABLE: "Bus Pirate 6",
    CAP_PSU_READOUT: "Bus Pirate 6",
```

Change `DeviceProfile.variant`'s comment to `# "v3", "v4", "bitpirate", "bp6" or "unknown"`, and in `describe()` replace the mapping with:

```python
        if self.variant == "bp6":
            parts = (
                "Bus Pirate 5 (untested)" if (self.devid or "").startswith("hw 5.") else "Bus Pirate 6"
            )
        else:
            parts = {
                "v3": "Bus Pirate v3",
                "v4": "Bus Pirate v4",
                "bitpirate": "ESP32 Bit Pirate",
            }.get(self.variant, "unidentified Bus Pirate")
```

In `capabilities_for()` add before `if variant == "v4":`:

```python
    if variant == "bp6":
        # BPIO2: I2C, SPI (any mode, page writes fit in 512 bytes), UART with
        # its async receive, 1-Wire, and the programmable supply. No bitbang,
        # raw-wire, sniffers or bridge — see buspirate.bp6.
        return frozenset(
            {CAP_SUPPLIES, CAP_ONEWIRE, CAP_SPI_MODES, CAP_UART_BUFFERED,
             CAP_SPI_FLASH_PROGRAM, CAP_PSU_PROGRAMMABLE, CAP_PSU_READOUT}
        )
```

At the end of the file add:

```python
def _bp6_firmware(date: str, git_hash: str) -> Optional[str]:
    """``Oct 12 2026 09:05:15`` to ``2026-10-12``; CI builds say hash ``unknown``."""
    import datetime

    if not date:
        return None
    try:
        shown = datetime.datetime.strptime(date, "%b %d %Y %H:%M:%S").strftime("%Y-%m-%d")
    except ValueError:
        shown = date
    if git_hash and git_hash != "unknown":
        shown += f" ({git_hash})"
    return shown


def parse_bp6_status(status) -> DeviceProfile:
    """A Bus Pirate 6 profile from a BPIO2 StatusResponse (or None)."""
    if status is None:
        return DeviceProfile(variant="bp6", capabilities=capabilities_for("bp6"))
    major, minor = status.hardware
    return DeviceProfile(
        variant="bp6",
        firmware=_bp6_firmware(status.firmware_date, status.firmware_hash),
        devid=f"hw {major}.{minor}",
        capabilities=capabilities_for("bp6"),
        banner=(f"Bus Pirate hardware {major}.{minor}, firmware built "
                f"{status.firmware_date}, BPIO2 {status.flatbuffers_version[0]}."
                f"{status.flatbuffers_version[1]}"),
    )
```

- [ ] **Step 4: Run the tests (and the old ones)**

Run: `.venv/bin/python -m pytest tests/test_bp6_profile.py tests/test_device.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add buspirate/device.py tests/test_bp6_profile.py
git commit -m "Give the Bus Pirate 6 a profile and its own capabilities"
```

---

### Task 5: `BusPirate6` — connect, status, power, pull-ups, HiZ, streams

**Files:**
- Modify: `buspirate/base.py` (`_make_serial(port=None)`)
- Create: `buspirate/bp6/terminal.py`, `buspirate/bp6/device.py`
- Modify: `buspirate/bp6/__init__.py` (export)
- Test: `tests/test_bp6_driver.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces `buspirate.bp6.terminal`: `select_bpio2(serial, notify, timeout=3.0) -> None` (raises `ModeError` with what the terminal last said).
- Produces `buspirate.bp6.BusPirate6(port, terminal_port=None, baudrate=115200, timeout=0.05, serial_factory=None, on_traffic=None, reply_timeout=1.0, connect_timeout=0.6)`:
  - class attrs `device_name = "Bus Pirate 6"`, `protocol_label = "BPIO2"`, `bitbang_version = None`
  - `open() -> BusPirate6`, `close()`, `__enter__/__exit__`
  - `status() -> Status` (also refreshes `last_status`), `last_status: Optional[Status]`
  - `configure(**configuration_request_kwargs) -> None` (raises `ModeError` naming the board's error)
  - `set_power(on: bool, millivolts: Optional[int]=None, milliamps: Optional[int]=None) -> Status` — remembers `psu_mv`/`psu_ma` (defaults 3300/300); validates 800–5000 and 0–500, raising `ValueError`
  - `set_pullups(on: bool) -> Status`
  - `hiz() -> None` — leave any mode object, mode HiZ, power off, pull-ups off
  - `mode` property, `_enter_mode(cls)`, `_mode_closed(mode)`, `i2c()`, `spi()`, `uart()`, `onewire()` (the mode classes come in Task 6; import lazily)
  - `release_to_terminal(settle: float)`, `stop_stream()`, `resync()`, `streaming`
  - `summarize_traffic(direction: str, data: bytes) -> str` (delegates to `protocol.describe_frame`)
  - `link: BpioLink`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bp6_driver.py
"""The Bus Pirate 6 driver against the simulated board."""

import pytest

from buspirate.bp6 import BusPirate6
from buspirate.exceptions import ModeError
from buspirate.simulator_bp6 import FakeBp6


def make(fake, **kw):
    kw.setdefault("reply_timeout", 0.2)
    kw.setdefault("connect_timeout", 0.1)
    return BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                      serial_factory=fake.factory(), **kw)


def test_connect_reads_the_status():
    fake = FakeBp6()
    bp = make(fake).open()
    assert bp.profile.describe() == "Bus Pirate 6, firmware 2026-10-12"
    assert bp.last_status.mode == "HiZ"
    assert fake.terminal.written == b""  # BPIO2 was on, the terminal was left alone


def test_connect_switches_bpio2_on_through_the_terminal_when_it_is_off():
    fake = FakeBp6(bpio_active=False, color_prompt=True)
    bp = make(fake).open()
    assert fake.bpio_active
    assert b"n\r" in fake.terminal.written and b"binmode\r" in fake.terminal.written
    assert bp.profile.variant == "bp6"
    assert not fake.terminal.is_open  # handed back after use


def test_connect_fails_clearly_without_a_terminal_port():
    fake = FakeBp6(bpio_active=False)
    with pytest.raises(ModeError, match="BPIO2"):
        BusPirate6(FakeBp6.BINARY, serial_factory=fake.factory(), connect_timeout=0.05).open()


def test_power_on_off_and_limits():
    fake = FakeBp6()
    bp = make(fake).open()
    status = bp.set_power(True, millivolts=1800, milliamps=100)
    assert status.psu_enabled and status.psu_mv == 1800
    assert (bp.psu_mv, bp.psu_ma) == (1800, 100)
    assert not bp.set_power(False).psu_enabled
    with pytest.raises(ValueError):
        bp.set_power(True, millivolts=5500)
    with pytest.raises(ValueError):
        bp.set_power(True, milliamps=600)


def test_a_board_error_is_a_mode_error():
    bp = make(FakeBp6()).open()
    with pytest.raises(ModeError, match="Invalid mode name"):
        bp.configure(mode="JTAG")


def test_pullups():
    bp = make(FakeBp6()).open()
    assert bp.set_pullups(True).pullups
    assert not bp.set_pullups(False).pullups


def test_hiz_releases_everything():
    fake = FakeBp6()
    bp = make(fake).open()
    bp.set_power(True)
    bp.set_pullups(True)
    bp.configure(mode="I2C")
    bp.hiz()
    assert (fake.mode, fake.psu_enabled, fake.pullups) == ("HiZ", False, False)


def test_close_leaves_the_board_in_hiz():
    fake = FakeBp6()
    bp = make(fake).open()
    bp.set_power(True)
    bp.close()
    assert fake.mode == "HiZ" and not fake.psu_enabled
    assert bp.serial is None


def test_the_terminal_borrows_the_port_and_gives_it_back():
    fake = FakeBp6()
    bp = make(fake).open()
    bp.release_to_terminal(0)
    assert bp.serial is fake.terminal
    bp.write(b"i\r")
    assert b"Bus Pirate 6" in fake.terminal.read(4096)
    bp.stop_stream()
    assert bp.serial is fake.binary
    assert not fake.terminal.is_open
    assert fake.requests[-1] == "status"  # re-read what the terminal may have changed


def test_traffic_is_summarised():
    bp = make(FakeBp6()).open()
    seen = []
    bp.add_traffic_hook(lambda direction, data: seen.append(bp.summarize_traffic(direction, data)))
    bp.status()
    assert seen[0] == "Status request"
    assert seen[1].startswith("Status: HiZ")


def test_an_old_bpio_version_is_refused(monkeypatch):
    from dataclasses import replace
    import buspirate.bp6.link as link_module

    original = link_module.parse_response

    def older(payload):
        response = original(payload)
        if response.status is not None:
            response = replace(response, status=replace(response.status, flatbuffers_version=(1, 0)))
        return response

    monkeypatch.setattr(link_module, "parse_response", older)
    with pytest.raises(ModeError, match="update"):
        make(FakeBp6()).open()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_bp6_driver.py -q`
Expected: FAIL with `ImportError: cannot import name 'BusPirate6'`.

- [ ] **Step 3: Let `SerialLink` open a second port**

In `buspirate/base.py`, change `def _make_serial(self):` to:

```python
    def _make_serial(self, port: Optional[str] = None):
        port = port or self.port
        if self._serial_factory is not None:
            return self._serial_factory(port, self.baudrate, self.timeout)
```

and replace every later `self.port` inside that method with `port` (four places: the `startswith`, both `os.path.exists`, the two error messages, and the `serial.Serial(...)` call). Behaviour for existing callers is unchanged.

Run: `.venv/bin/python -m pytest -q -x` → still 619 passed (plus the new ones you have passing so far).

- [ ] **Step 4: Write `terminal.py`**

```python
# buspirate/bp6/terminal.py
"""The Bus Pirate 6's text terminal, used only to switch BPIO2 on.

What the real board does (2026-10-14, firmware built 2026-10-12): only "\\r"
is Enter; the first key after boot gets "VT100 compatible color mode? (Y/n)>",
which takes its answer only as "n\\r" in one write; ``binmode`` lists the
binary modes, "2" picks BPIO2 and "n" declines to save it, so nothing on the
board changes beyond this boot.
"""

from __future__ import annotations

import time

from ..exceptions import ModeError

COLOR_PROMPT = "VT100 compatible color mode?"


def _read_until(serial, notify, marks, timeout: float) -> str:
    seen = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        chunk = serial.read(256)
        if chunk:
            seen += chunk
            notify("rx", bytes(chunk))
            text = seen.decode("utf-8", "replace")
            if any(mark in text for mark in marks):
                return text
        else:
            time.sleep(0.01)
    return seen.decode("utf-8", "replace")


def _send(serial, notify, keys: bytes) -> None:
    serial.write(keys)
    notify("tx", keys)


def select_bpio2(serial, notify, timeout: float = 3.0) -> None:
    _send(serial, notify, b"\x03")
    text = _read_until(serial, notify, ("> ", COLOR_PROMPT), timeout)
    if COLOR_PROMPT in text:
        _send(serial, notify, b"n\r")
        text = _read_until(serial, notify, ("> ",), timeout)
    _send(serial, notify, b"binmode\r")
    text = _read_until(serial, notify, ("x to exit",), timeout)
    if "BPIO2" not in text:
        raise ModeError(
            "this Bus Pirate's firmware has no BPIO2 binary mode. Update it: type "
            "$ in its terminal, then copy bus_pirate6.uf2 onto the RP2350 disk "
            "(see the Bus Pirate 6 guide). It said: " + text.strip()[-160:]
        )
    _send(serial, notify, b"2\r")
    text = _read_until(serial, notify, ("y/n",), timeout)
    _send(serial, notify, b"n\r")
    _read_until(serial, notify, ("> ",), timeout)
```

(The real menu text is `" 2. BPIO2 flatbuffer interface"`, so `"BPIO2" in text` is the check.)

- [ ] **Step 5: Write `device.py`**

```python
# buspirate/bp6/device.py
"""The Bus Pirate 6 as a device the dashboard can drive."""

from __future__ import annotations

import logging
from typing import Optional

from ..base import SerialLink, TrafficHook
from ..device import parse_bp6_status
from ..exceptions import BusPirateError, ModeError, ProtocolError
from . import protocol
from .link import BpioLink
from .protocol import Status
from .terminal import select_bpio2

log = logging.getLogger(__name__)

MIN_MV, MAX_MV = 800, 5000
MAX_MA = 500


class BusPirate6(SerialLink):
    """A Bus Pirate 6 on its two USB ports.

    ``port`` is the BPIO2 port (the board's second CDC interface) and
    ``terminal_port`` its text terminal. Everything runs over BPIO2; the
    terminal is opened only to switch BPIO2 on and for the Terminal panel.
    """

    device_name = "Bus Pirate 6"
    protocol_label = "BPIO2"
    bitbang_version = None

    def __init__(
        self,
        port: str,
        terminal_port: Optional[str] = None,
        baudrate: int = 115200,
        timeout: float = 0.05,
        serial_factory=None,
        on_traffic: Optional[TrafficHook] = None,
        reply_timeout: float = 1.0,
        connect_timeout: float = 0.6,
    ) -> None:
        super().__init__(port, baudrate, timeout, serial_factory, on_traffic)
        self.terminal_port = terminal_port
        self.reply_timeout = reply_timeout
        self.connect_timeout = connect_timeout
        self.profile = parse_bp6_status(None)
        self.link: Optional[BpioLink] = None
        self.last_status: Optional[Status] = None
        #: The supply the dashboard asks for whenever it switches power on.
        self.psu_mv = 3300
        self.psu_ma = 300
        self._mode = None
        #: The BPIO2 serial while a stream has lent ``self.serial`` elsewhere.
        self._binary = None
        self._terminal_open = False

    # -- connection --------------------------------------------------------

    def open(self) -> "BusPirate6":
        if self.serial is None:
            self.serial = self._make_serial()
        self.link = BpioLink(self.serial, self._notify, self.reply_timeout)
        try:
            status = self._status(self.connect_timeout)
        except ProtocolError:
            self._switch_bpio2_on()
            try:
                status = self._status(self.connect_timeout * 3)
            except ProtocolError as exc:
                raise ModeError(
                    "the Bus Pirate 6 did not answer on its BPIO2 port, even after "
                    "BPIO2 was selected in its terminal. Unplug it, plug it back "
                    "in, and connect again."
                ) from exc
        if status.flatbuffers_version[0] != protocol.VERSION_MAJOR:
            raise ModeError(
                f"this firmware speaks BPIO {status.flatbuffers_version[0]}."
                f"{status.flatbuffers_version[1]}; the app needs 2.x. Please update "
                "the Bus Pirate's firmware (see the Bus Pirate 6 guide)."
            )
        return self

    def _switch_bpio2_on(self) -> None:
        if not self.terminal_port:
            raise ModeError(
                "the Bus Pirate 6 is not in BPIO2 mode and its terminal port is "
                "unknown. Type binmode, then 2, in its terminal, or connect by "
                "picking the board in the port list."
            )
        terminal = self._make_serial(self.terminal_port)
        try:
            select_bpio2(terminal, self._notify)
        finally:
            terminal.close()

    def _status(self, timeout: Optional[float] = None) -> Status:
        response = self.link.request(protocol.status_request(), timeout)
        if response.status is None:
            raise ProtocolError(f"the Bus Pirate 6 did not send its status: {response.error}")
        self.last_status = response.status
        self.profile = parse_bp6_status(response.status)
        return response.status

    def status(self) -> Status:
        return self._status()

    def close(self) -> None:
        if self.serial is None:
            return
        try:
            self.stop_stream()
            self.hiz()
        except (BusPirateError, OSError):
            log.debug("could not leave the Bus Pirate 6 in HiZ; closing anyway", exc_info=True)
        finally:
            self.serial.close()
            self.serial = None

    def __enter__(self) -> "BusPirate6":
        return self.open()

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- configuration -----------------------------------------------------

    def configure(self, **fields) -> None:
        response = self.link.request(protocol.configuration_request(**fields))
        if response.error:
            raise ModeError(f"the Bus Pirate 6 refused that: {response.error}")

    def set_power(self, on: bool, millivolts: Optional[int] = None,
                  milliamps: Optional[int] = None) -> Status:
        if millivolts is not None:
            if not MIN_MV <= millivolts <= MAX_MV:
                raise ValueError(f"the supply goes from {MIN_MV} to {MAX_MV} mV")
            self.psu_mv = int(millivolts)
        if milliamps is not None:
            if not 0 <= milliamps <= MAX_MA:
                raise ValueError(f"the current limit goes from 0 (no limit) to {MAX_MA} mA")
            self.psu_ma = int(milliamps)
        if on:
            self.configure(psu_enable=True, psu_mv=self.psu_mv, psu_ma=self.psu_ma)
        else:
            self.configure(psu_disable=True)
        return self.status()

    def set_pullups(self, on: bool) -> Status:
        self.configure(pullup_enable=on, pullup_disable=not on)
        return self.status()

    def hiz(self) -> None:
        if self._mode is not None:
            self._mode.close()
        self.configure(mode="HiZ", psu_disable=True, pullup_disable=True)
        self.status()

    # -- modes -------------------------------------------------------------

    @property
    def mode(self):
        return self._mode

    def _enter_mode(self, mode_cls):
        if self._mode is not None:
            raise ModeError(f"already in {type(self._mode).__name__}; close it first")
        self._mode = mode_cls(self)
        return self._mode

    def _mode_closed(self, mode) -> None:
        if self._mode is mode:
            self._mode = None

    def i2c(self):
        from .modes import Bp6I2C

        return self._enter_mode(Bp6I2C)

    def spi(self):
        from .modes import Bp6SPI

        return self._enter_mode(Bp6SPI)

    def uart(self):
        from .modes import Bp6UART

        return self._enter_mode(Bp6UART)

    def onewire(self):
        from .modes import Bp6OneWire

        return self._enter_mode(Bp6OneWire)

    # -- streams and the terminal -----------------------------------------

    def lend_serial(self, stand_in) -> None:
        """Let a stream read ``stand_in`` through ``self.serial``."""
        if self._binary is None:
            self._binary = self.serial
        self.serial = stand_in
        self.streaming = True

    def release_to_terminal(self, settle: float) -> None:
        """Open the terminal port in place of BPIO2. Nothing is reset."""
        if not self.terminal_port:
            raise ModeError("this Bus Pirate 6's terminal port is unknown")
        self._mode = None
        terminal = self._make_serial(self.terminal_port)
        self.lend_serial(terminal)
        self._terminal_open = True
        self.write(b"\r")  # a fresh prompt (or the colour question, re-asked)

    def stop_stream(self) -> None:
        if self._binary is None:
            self.streaming = False
            return
        lent, self.serial, self._binary = self.serial, self._binary, None
        self.streaming = False
        if self._terminal_open:
            self._terminal_open = False
            lent.close()
        self._mode = None
        # The terminal may have changed the mode, the supply or the pull-ups.
        self.status()

    def resync(self) -> None:
        self._mode = None
        self.status()

    # -- traffic -----------------------------------------------------------

    def summarize_traffic(self, direction: str, data: bytes) -> str:
        if self._terminal_open:
            return ""
        return protocol.describe_frame(direction, data)

    def __repr__(self) -> str:
        state = "open" if self.serial is not None else "closed"
        mode = type(self._mode).__name__ if self._mode else None
        return f"<BusPirate6 {self.port} {state} mode={mode}>"
```

Update `buspirate/bp6/__init__.py`:

```python
"""The Bus Pirate 6, driven over its BPIO2 binary interface."""

from .device import BusPirate6

__all__ = ["BusPirate6"]
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_bp6_driver.py -q`
Expected: all PASS except tests that need Task 6 (none here use modes beyond `configure`).

- [ ] **Step 7: Commit**

```bash
git add buspirate/base.py buspirate/bp6 tests/test_bp6_driver.py
git commit -m "Connect to a Bus Pirate 6 over BPIO2, switching it on through the terminal when needed"
```

---

### Task 6: I2C, SPI, UART and 1-Wire over BPIO2

**Files:**
- Create: `buspirate/bp6/modes.py`
- Test: `tests/test_bp6_modes.py`

**Interfaces:**
- Consumes: `BusPirate6` (`configure`, `link`, `set_power`, `set_pullups`, `lend_serial`, `_mode_closed`, `last_status`, `psu_mv`, `psu_ma`) from Task 5.
- Produces: `Bp6I2C`, `Bp6SPI`, `Bp6UART`, `Bp6OneWire`, each answering the same calls as their v3/v4 namesakes that the panels make:
  - all: `peripherals` dict, `configure_peripherals(power=False, pullups=False, aux=False, cs=False)`, `close()`, `is_active`, context manager.
  - `Bp6I2C`: `reports_byte_acks = False`, `set_speed(index)`, `scan(addresses=SCAN_RANGE) -> List[int]`, `write(address, data=b"")`, `read(address, count)`, `read_after_write(address, pointer, count)`, `read_register(address, register, count=1)`, `write_register(address, register, data)`, `write_then_read(write_data=b"", read_count=0)`.
  - `Bp6SPI`: `set_speed(index)`, `set_mode(mode, push_pull=True)`, `configure(push_pull=True, clock_idle_high=False, clock_edge_active_to_idle=True, sample_at_end=False)`, `cs_low()`, `cs_high()`, `write_then_read(data=b"", read_count=0, assert_cs=True)`.
  - `Bp6UART`: `listening = True`, `set_baudrate(index)`, `configure(push_pull=True, databits_parity=0, stop_bits=1, rx_idle_low=False)`, `write(data)`, `read_available(max_bytes=256)`, `start_receive()`, `stop_receive()`.
  - `Bp6OneWire`: `reset()`, `write(data)`, `read(count)`, `read_byte()`, `read_rom()`, `search_rom(alarm=False) -> List[bytes]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bp6_modes.py
"""The four bus modes over BPIO2, against the simulated board."""

import pytest

from buspirate.bp6 import BusPirate6
from buspirate.exceptions import NackError, UnsupportedFeatureError
from buspirate.simulator_bp6 import FakeBp6
from buspirate.spiflash import SPIFlash
from buspirate.uart import UART


@pytest.fixture
def fake():
    return FakeBp6()


@pytest.fixture
def bp(fake):
    with BusPirate6(FakeBp6.BINARY, terminal_port=FakeBp6.TERMINAL,
                    serial_factory=fake.factory(), reply_timeout=0.2) as device:
        yield device


# -- I2C ---------------------------------------------------------------------

def test_i2c_scan_and_register_read(bp, fake):
    with bp.i2c() as i2c:
        i2c.configure_peripherals(power=True, pullups=True)
        assert fake.mode == "I2C" and fake.psu_enabled and fake.pullups
        assert i2c.scan() == [0x76]
        assert i2c.read_register(0x76, 0xD0) == b"\x58"


def test_a_nack_is_followed_by_a_stop_only_request(bp, fake):
    with bp.i2c() as i2c:
        before = len(fake.requests)
        with pytest.raises(NackError, match="0x20"):
            i2c.read_register(0x20, 0x00)
        assert fake.requests[before:] == ["data", "data"]  # the read, then the stop


def test_i2c_write_then_read_uses_the_address_byte(bp):
    with bp.i2c() as i2c:
        assert i2c.write_then_read(b"\xec\xd0", 1) == b"\x58"


def test_i2c_speed_is_sent_in_hz(bp, fake):
    with bp.i2c() as i2c:
        i2c.set_speed(3)
    assert fake.mode == "I2C"


def test_aux_is_refused(bp):
    with bp.i2c() as i2c:
        with pytest.raises(UnsupportedFeatureError):
            i2c.configure_peripherals(aux=True)


# -- SPI ---------------------------------------------------------------------

def test_spi_flash_identifies_itself(bp):
    with bp.spi() as spi:
        spi.set_mode(0)
        assert SPIFlash(spi).jedec_id() == FakeBp6().flash.exchange(b"\x9f", 3)


def test_long_spi_reads_are_split_with_cs_held(bp, fake):
    with bp.spi() as spi:
        data = spi.write_then_read(b"\x03\x00\x00\x00", 1200)
    assert len(data) == 1200


# -- UART --------------------------------------------------------------------

def test_uart_write_and_read_back(bp, fake):
    with bp.uart() as uart:
        uart.set_baudrate(UART.BAUD_115200)
        uart.configure()
        uart.write(b"hello")
        assert uart.read_available(64) == b"hello"


def test_odd_parity_and_nine_bits_are_refused(bp):
    with bp.uart() as uart:
        with pytest.raises(UnsupportedFeatureError):
            uart.configure(databits_parity=2)
        with pytest.raises(UnsupportedFeatureError):
            uart.configure(databits_parity=3)


def test_uart_receive_stream_reads_async_data(bp, fake):
    uart = bp.uart()
    uart.start_receive()
    fake.uart_receive(b"boot ok\r\n")
    got = b""
    for _ in range(20):
        got += bp.serial.read(256)
    assert got == b"boot ok\r\n"
    bp.stop_stream()
    assert bp.serial is fake.binary


# -- 1-Wire ------------------------------------------------------------------

def test_onewire_finds_the_one_device(bp, fake):
    with bp.onewire() as ow:
        assert ow.search_rom() == [fake.onewire_rom]


def test_onewire_with_nothing_on_the_bus(bp, fake):
    fake.onewire_rom = b""
    with bp.onewire() as ow:
        with pytest.raises(NackError, match="no 1-Wire device"):
            ow.reset()
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_bp6_modes.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'buspirate.bp6.modes'`.

- [ ] **Step 3: Write `modes.py`**

```python
# buspirate/bp6/modes.py
"""I2C, SPI, UART and 1-Wire on the Bus Pirate 6, over BPIO2.

Each class answers to the same calls as its namesake in buspirate.i2c,
buspirate.spi, buspirate.uart and buspirate.onewire — the calls the
dashboard's panels make — so a panel never needs to know which board it is
driving.

Firmware behaviour relied on (src/binmode/bpio_*.c, firmware built 2026-10-12):
* I2C: data_write[0] is the 8-bit address byte; a write followed by a read
  gets a repeated start; an error returns early and skips STOP, so every
  error here is followed by a stop-only request.
* SPI: start/stop drive CS.
* UART: whatever the target sends arrives as unsolicited async frames.
* 1-Wire: byte-level only — start is a reset, which fails with no device.
"""

from __future__ import annotations

from typing import Dict, Iterable, List

from ..device import I2C_SPEEDS_MODERN, SPI_SPEEDS
from ..exceptions import ModeError, NackError, ProtocolError, UnsupportedFeatureError
from ..i2c import SCAN_RANGE
from ..uart import UART
from . import protocol
from .protocol import ModeConfig


class _Bp6Mode:
    title = ""
    #: The mode's name in BPIO2.
    name = ""

    def __init__(self, bp) -> None:
        self.bp = bp
        self._active = True
        self.config = self.default_config()
        self.peripherals: Dict[str, bool] = {
            "power": bool(bp.last_status and bp.last_status.psu_enabled),
            "pullups": bool(bp.last_status and bp.last_status.pullups),
            "aux": False, "cs": False,
        }
        self._apply()

    def default_config(self) -> ModeConfig:
        return ModeConfig()

    def _apply(self) -> None:
        self.bp.configure(mode=self.name, mode_config=self.config)

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        """Nothing to send: the next mode replaces this one."""
        if not self._active:
            return
        self._active = False
        self.bp._mode_closed(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    @property
    def is_active(self) -> bool:
        return self._active

    def _check_active(self) -> None:
        if not self._active:
            raise ModeError(f"{type(self).__name__} has been closed")

    # -- shared ------------------------------------------------------------

    def configure_peripherals(self, power: bool = False, pullups: bool = False,
                              aux: bool = False, cs: bool = False) -> None:
        """Power at the voltage and limit set on the Power panel, and pull-ups."""
        self._check_active()
        if aux or cs:
            raise UnsupportedFeatureError(
                "the Bus Pirate 6 has no AUX or CS peripheral pins to drive. It is "
                "a Bus Pirate v3 and v4 feature."
            )
        fields = dict(pullup_enable=pullups, pullup_disable=not pullups)
        if power:
            fields.update(psu_enable=True, psu_mv=self.bp.psu_mv, psu_ma=self.bp.psu_ma)
        else:
            fields.update(psu_disable=True)
        self.bp.configure(**fields)
        self.peripherals = dict(self.peripherals, power=power, pullups=pullups)

    def _data(self, **fields) -> protocol.Response:
        self._check_active()
        return self.bp.link.request(protocol.data_request(**fields))


class Bp6I2C(_Bp6Mode):
    title = "I2C"
    name = "I2C"
    #: BPIO2 reports one ACK/NACK for the whole transaction, not per byte.
    reports_byte_acks = False

    def set_speed(self, speed: int) -> None:
        if speed not in I2C_SPEEDS_MODERN:
            raise ValueError(f"speed must be one of {sorted(I2C_SPEEDS_MODERN)}")
        self.config = ModeConfig(speed=I2C_SPEEDS_MODERN[speed], clock_stretch=True)
        self._apply()

    def default_config(self) -> ModeConfig:
        return ModeConfig(speed=100_000, clock_stretch=True)

    def write_then_read(self, write_data: bytes = b"", read_count: int = 0) -> bytes:
        """START, ``write_data`` (address byte first), [RESTART, read], STOP."""
        write_data = bytes(write_data)
        if not write_data:
            raise ValueError("the first byte written is the address byte")
        response = self._data(start=True, write=write_data, read=read_count, stop=True)
        if response.error:
            self._data(stop=True)  # the firmware skipped STOP on its way out
            raise NackError(
                f"0x{write_data[0] >> 1:02X} did not answer. Check the address, the "
                "wiring and that the bus has pull-ups."
            )
        if len(response.data) != read_count:
            raise ProtocolError(f"asked for {read_count} bytes, got {len(response.data)}")
        return response.data

    def scan(self, addresses: Iterable[int] = SCAN_RANGE) -> List[int]:
        found = []
        for address in addresses:
            try:
                self.write_then_read(bytes([address << 1]), 0)
            except NackError:
                continue
            found.append(address)
        return found

    def write(self, address: int, data: bytes = b"") -> None:
        self.write_then_read(bytes([_address(address) << 1]) + bytes(data), 0)

    def read(self, address: int, count: int) -> bytes:
        return self._chunked(address, b"", count)

    def read_after_write(self, address: int, pointer: bytes, count: int) -> bytes:
        return self._chunked(address, bytes(pointer), count)

    def read_register(self, address: int, register: int, count: int = 1) -> bytes:
        return self.read_after_write(address, bytes([register & 0xFF]), count)

    def write_register(self, address: int, register: int, data: bytes) -> None:
        self.write(address, bytes([register & 0xFF]) + bytes(data))

    def _chunked(self, address: int, pointer: bytes, count: int) -> bytes:
        if count < 1:
            raise ValueError("count must be >= 1")
        limit = self.bp.last_status.max_read if self.bp.last_status else 512
        width = len(pointer)
        base = int.from_bytes(pointer, "big") if width else 0
        out = bytearray()
        for offset in range(0, count, limit):
            size = min(limit, count - offset)
            where = ((base + offset) & ((1 << (8 * width)) - 1)).to_bytes(width, "big") if width else b""
            out += self.write_then_read(bytes([_address(address) << 1]) + where, size)
        return bytes(out)


class Bp6SPI(_Bp6Mode):
    title = "SPI"
    name = "SPI"

    def default_config(self) -> ModeConfig:
        return ModeConfig(speed=1_000_000)

    def set_speed(self, speed: int) -> None:
        if speed not in SPI_SPEEDS:
            raise ValueError(f"speed must be one of {sorted(SPI_SPEEDS)}")
        self.config = ModeConfig(speed=SPI_SPEEDS[speed], clock_polarity=self.config.clock_polarity,
                                 clock_phase=self.config.clock_phase)
        self._apply()

    def set_mode(self, mode: int, push_pull: bool = True) -> None:
        if mode not in (0, 1, 2, 3):
            raise ValueError("SPI mode must be 0, 1, 2 or 3")
        self.config = ModeConfig(speed=self.config.speed, clock_polarity=bool(mode & 0b10),
                                 clock_phase=bool(mode & 0b01))
        self._apply()

    def configure(self, push_pull: bool = True, clock_idle_high: bool = False,
                  clock_edge_active_to_idle: bool = True, sample_at_end: bool = False) -> None:
        mode = (0b10 if clock_idle_high else 0) | (0 if clock_edge_active_to_idle else 0b01)
        self.set_mode(mode, push_pull)

    def cs_low(self) -> None:
        self._data(start=True)

    def cs_high(self) -> None:
        self._data(stop=True)

    def write_then_read(self, data: bytes = b"", read_count: int = 0, assert_cs: bool = True) -> bytes:
        """Write ``data``, then clock in ``read_count``; CS low throughout.

        Anything over the board's 512-byte limits goes in several requests,
        with CS raised only after the last.
        """
        data = bytes(data)
        if not data and not read_count:
            return b""
        limit_w = self.bp.last_status.max_write if self.bp.last_status else 512
        limit_r = self.bp.last_status.max_read if self.bp.last_status else 512
        steps = [("w", data[i:i + limit_w]) for i in range(0, len(data), limit_w)]
        steps += [("r", min(limit_r, read_count - i)) for i in range(0, read_count, limit_r)]
        out = bytearray()
        for index, (kind, value) in enumerate(steps):
            first, last = index == 0, index == len(steps) - 1
            fields = dict(start=assert_cs and first, stop=assert_cs and last)
            if kind == "w":
                fields["write"] = value
            else:
                fields["read"] = value
            response = self._data(**fields)
            if response.error:
                raise ModeError(f"the Bus Pirate 6 said: {response.error}")
            out += response.data
        if len(out) != read_count:
            raise ProtocolError(f"asked for {read_count} SPI bytes, got {len(out)}")
        return bytes(out)


class _AsyncUartStream:
    """``self.serial`` for the UART monitor: reads give the target's bytes."""

    def __init__(self, link) -> None:
        self.link = link

    def read(self, count: int) -> bytes:
        data = self.link.poll_async(0.02)
        if len(data) > count:
            self.link.async_rx[:0] = data[count:]
            data = data[:count]
        return data

    def write(self, data: bytes) -> int:
        raise ModeError("the UART monitor only listens; use Send in the UART panel")

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class Bp6UART(_Bp6Mode):
    title = "UART"
    name = "UART"
    #: The firmware forwards what the target sends at all times in UART mode.
    listening = True
    #: databits_parity index → (data bits, even parity). Odd parity and 9 bits
    #: have no field in BPIO2's ModeConfiguration.
    FRAMING = {0: (8, False), 1: (8, True)}

    def default_config(self) -> ModeConfig:
        return ModeConfig(speed=115200)

    def set_baudrate(self, baud: int) -> None:
        if baud not in UART._BAUDS:
            raise ValueError("baud must be one of UART.BAUD_300..BAUD_115200")
        self.config = ModeConfig(speed=UART._BAUDS[baud], data_bits=self.config.data_bits,
                                 parity=self.config.parity, stop_bits=self.config.stop_bits,
                                 signal_inversion=self.config.signal_inversion)
        self._apply()

    def configure(self, push_pull: bool = True, databits_parity: int = 0, stop_bits: int = 1,
                  rx_idle_low: bool = False) -> None:
        if databits_parity not in self.FRAMING:
            raise UnsupportedFeatureError(
                "the Bus Pirate 6's binary interface offers 8 data bits with no or "
                "even parity. Odd parity and 9-bit framing are in its own terminal "
                "(the Terminal panel), or on a Bus Pirate v3 or v4."
            )
        bits, parity = self.FRAMING[databits_parity]
        self.config = ModeConfig(speed=self.config.speed, data_bits=bits, parity=parity,
                                 stop_bits=stop_bits, signal_inversion=rx_idle_low)
        self._apply()

    def write(self, data: bytes) -> None:
        data = bytes(data)
        limit = self.bp.last_status.max_write if self.bp.last_status else 512
        for start in range(0, len(data), limit):
            response = self._data(write=data[start:start + limit])
            if response.error:
                raise ModeError(f"the Bus Pirate 6 said: {response.error}")

    def read_available(self, max_bytes: int = 256) -> bytes:
        data = self.bp.link.poll_async(0.05)
        if len(data) > max_bytes:
            self.bp.link.async_rx[:0] = data[max_bytes:]
            data = data[:max_bytes]
        return data

    def start_receive(self) -> None:
        """Hand ``bp.serial`` to the monitor stream; stop_stream gives it back."""
        self._check_active()
        self.bp.lend_serial(_AsyncUartStream(self.bp.link))

    def stop_receive(self) -> None:
        self.bp.stop_stream()


class Bp6OneWire(_Bp6Mode):
    title = "1-Wire"
    name = "1WIRE"

    def _transfer(self, **fields) -> bytes:
        response = self._data(**fields)
        if response.error:
            raise NackError(
                "no 1-Wire device answered the reset. Check the data line (IO0), "
                "ground, and a pull-up (switch the pull-ups on)."
            )
        return response.data

    def reset(self) -> None:
        self._transfer(start=True)

    def write(self, data: bytes) -> None:
        self._transfer(write=bytes(data))

    def read(self, count: int) -> bytes:
        return self._transfer(read=count)

    def read_byte(self) -> int:
        return self.read(1)[0]

    def read_rom(self) -> bytes:
        """READ ROM (0x33): only valid with exactly one device on the bus."""
        return self._transfer(start=True, write=b"\x33", read=8)

    def search_rom(self, alarm: bool = False) -> List[bytes]:
        """BPIO2 cannot do the bit-level search, so this is READ ROM.

        With one device that is the same answer. With several, their ROMs
        collide, the CRC fails, and the error says what to do instead.
        """
        if alarm:
            raise UnsupportedFeatureError(
                "the Bus Pirate 6's binary interface cannot run an alarm search; "
                "type 'scan' in the Terminal panel's 1-Wire mode instead."
            )
        rom = self.read_rom()
        if _crc8(rom[:7]) != rom[7]:
            raise ProtocolError(
                "the ROM read back fails its CRC — usually more than one device is "
                "on the bus. The Bus Pirate 6's binary interface can only list one; "
                "type 'scan' in the Terminal panel's 1-Wire mode to list them all."
            )
        return [rom]


def _crc8(data: bytes) -> int:
    crc = 0
    for byte in data:
        for _ in range(8):
            mix = (crc ^ byte) & 1
            crc >>= 1
            if mix:
                crc ^= 0x8C
            byte >>= 1
    return crc


def _address(address: int) -> int:
    if not 0 <= address <= 0x7F:
        raise ValueError(f"0x{address:X} is not a 7-bit I2C address")
    return address
```

Check `buspirate/onewire.py` for an existing CRC helper; if one exists (e.g. `crc8`), import and use it instead of the local `_crc8` here and in the simulator.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_bp6_modes.py tests/test_bp6_driver.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add buspirate/bp6/modes.py tests/test_bp6_modes.py
git commit -m "Drive I2C, SPI, UART and 1-Wire on the Bus Pirate 6 over BPIO2"
```

---

### Task 7: Finding the board — port pairing, connect, CLI

**Files:**
- Modify: `buspirate/ports.py`, `buspirate/connect.py`, `buspirate/cli.py`
- Test: `tests/test_bp6_ports.py`

**Interfaces:**
- Produces in `buspirate.ports`: `BP6_ID = (0x1209, 0x7331)`; `PortCandidate.partner: Optional[str] = None`; `pair_bp6(infos) -> Dict[str, Tuple[str, str]]` (maps **each** port of a BP6 to `(terminal, binary)`); `discover()` shows one candidate per BP6 (the terminal port, `partner` = binary port, note `"Bus Pirate 5/6 (terminal + BPIO2 ports)"`); `usb_id_for(device: str) -> Optional[str]`; `bp6_ports_for(device: str) -> Tuple[str, Optional[str]]` (live lookup: `(terminal, binary)`; falls back to swapping a trailing `1`↔`3` in the device name when pyserial gives nothing).
- Produces in `buspirate.connect`: `BP6_VID = 0x1209`, `BP6_PID = 0x7331`; `open_device(...)` gains `bp6_options: Optional[Dict]=None` and returns an opened `BusPirate6` for that USB ID.
- Produces in `buspirate.cli`: every device command opens through `_open(port_arg)` → `open_device(...)`; `--demo` choices gain `"bp6"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bp6_ports.py
from types import SimpleNamespace

from buspirate import connect, ports
from buspirate.bp6 import BusPirate6
from buspirate.simulator_bp6 import FakeBp6


def info(device, location="1-1", vid=0x1209, pid=0x7331):
    return SimpleNamespace(device=device, location=location, vid=vid, pid=pid,
                           description="Bus Pirate 6", hwid="", manufacturer="Bus Pirate",
                           serial_number="6buspirate")


def test_the_two_ports_of_one_board_are_paired():
    pairs = ports.pair_bp6([info("/dev/cu.usbmodem6buspirate3"), info("/dev/cu.usbmodem6buspirate1")])
    expected = ("/dev/cu.usbmodem6buspirate1", "/dev/cu.usbmodem6buspirate3")
    assert pairs["/dev/cu.usbmodem6buspirate1"] == expected
    assert pairs["/dev/cu.usbmodem6buspirate3"] == expected


def test_two_boards_are_kept_apart_by_location():
    pairs = ports.pair_bp6([
        info("/dev/ttyACM0", "1-1"), info("/dev/ttyACM1", "1-1"),
        info("/dev/ttyACM2", "1-2"), info("/dev/ttyACM3", "1-2"),
    ])
    assert pairs["/dev/ttyACM3"] == ("/dev/ttyACM2", "/dev/ttyACM3")


def test_discover_shows_one_entry(monkeypatch):
    from serial.tools import list_ports
    monkeypatch.setattr(list_ports, "comports", lambda: [
        info("/dev/cu.usbmodem6buspirate1"), info("/dev/cu.usbmodem6buspirate3")])
    found = ports.discover()
    assert [c.device for c in found] == ["/dev/cu.usbmodem6buspirate1"]
    assert found[0].partner == "/dev/cu.usbmodem6buspirate3"
    assert found[0].likely_bus_pirate
    assert "Bus Pirate 5/6" in found[0].note


def test_fallback_pairing_by_name(monkeypatch):
    from serial.tools import list_ports
    monkeypatch.setattr(list_ports, "comports", lambda: [])
    assert ports.bp6_ports_for("/dev/cu.usbmodem6buspirate1") == (
        "/dev/cu.usbmodem6buspirate1", "/dev/cu.usbmodem6buspirate3")


def test_open_device_routes_the_usb_id_to_the_bp6(monkeypatch):
    fake = FakeBp6()
    monkeypatch.setattr(ports, "bp6_ports_for", lambda device: (FakeBp6.TERMINAL, FakeBp6.BINARY))
    device = connect.open_device(FakeBp6.TERMINAL, usb_id="1209:7331",
                                 serial_factory=fake.factory())
    assert isinstance(device, BusPirate6)
    assert fake.terminal.written == b""  # never the v3/v4 nulls or BBIO reset
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_bp6_ports.py -q`
Expected: FAIL with `AttributeError: module 'buspirate.ports' has no attribute 'pair_bp6'`.

- [ ] **Step 3: Implement in `ports.py`**

Add to `KNOWN_ADAPTERS`: `(0x1209, 0x7331): "Bus Pirate 5/6 (terminal + BPIO2 ports)",`.

Add to `PortCandidate` (after `note`): `partner: Optional[str] = None` and in `describe()` after the note: `if self.partner: bits.append(f"(BPIO2 on {self.partner})")`.

Add below `_score`:

```python
BP6_ID = (0x1209, 0x7331)


def _natural(device: str):
    import re

    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", device)]


def pair_bp6(infos) -> Dict[str, Tuple[str, str]]:
    """Each Bus Pirate 5/6 port mapped to (terminal port, BPIO2 port).

    Its two CDC ports share a USB location (pyserial's ``location``); the
    lower-numbered one is the terminal. The USB serial number is the same
    on every unit ("6buspirate"), so it cannot tell two boards apart.
    """
    groups: Dict[str, List[str]] = {}
    for item in infos:
        if (item.vid, item.pid) == BP6_ID:
            groups.setdefault(item.location or item.device, []).append(item.device)
    pairs: Dict[str, Tuple[str, str]] = {}
    for devices in groups.values():
        devices.sort(key=_natural)
        if len(devices) >= 2:
            pair = (devices[0], devices[-1])
            for device in devices:
                pairs[device] = pair
    return pairs


def bp6_ports_for(device: str) -> Tuple[str, Optional[str]]:
    """``(terminal, binary)`` for a port of a plugged-in Bus Pirate 5/6."""
    from serial.tools import list_ports

    pair = pair_bp6(list_ports.comports()).get(device)
    if pair:
        return pair
    if device.endswith("1"):
        return device, device[:-1] + "3"
    if device.endswith("3"):
        return device[:-1] + "1", device
    return device, None


def usb_id_for(device: str) -> Optional[str]:
    for candidate in discover(include_unlikely=True):
        if candidate.device == device or candidate.partner == device:
            return candidate.usb_id
    return None
```

In `discover()`, replace the loop body so BP6 pairs collapse:

```python
    infos = list(list_ports.comports())
    pairs = pair_bp6(infos)
    candidates = []
    for info in infos:
        pair = pairs.get(info.device)
        if pair and info.device != pair[0]:
            continue  # shown once, under its terminal port
        candidate = _score(info)
        if pair:
            candidate.partner = pair[1]
        if candidate.score < 0 and not include_unlikely:
            continue
        candidates.append(candidate)
```

Add `Dict, Tuple` to the `typing` import.

- [ ] **Step 4: Route the USB ID in `connect.py`**

Add after `ESPRESSIF_VID = 0x303A`:

```python
BP6_VID, BP6_PID = 0x1209, 0x7331


def _pid(usb_id: Optional[str]) -> Optional[int]:
    if not usb_id or ":" not in usb_id:
        return None
    try:
        return int(usb_id.split(":", 1)[1], 16)
    except ValueError:
        return None
```

Add the parameter `bp6_options: Optional[Dict[str, Any]] = None` to `open_device`, update the docstring's list with "3. VID 0x1209 / PID 0x7331 is a Bus Pirate 5/6, driven over BPIO2 on its second port.", and before the Espressif check:

```python
    if (_vid(usb_id), _pid(usb_id)) == (BP6_VID, BP6_PID):
        from .bp6 import BusPirate6
        from .ports import bp6_ports_for

        terminal, binary = bp6_ports_for(port)
        return BusPirate6(
            binary or port, terminal_port=terminal, serial_factory=serial_factory,
            on_traffic=on_traffic, **(bp6_options or {}),
        ).open()
```

Update the return annotation docstring: "Return an opened BusPirate, BitPirate or BusPirate6."

- [ ] **Step 5: Use `open_device` in the CLI**

In `buspirate/cli.py`:
- import: `from .connect import open_device` and `from .ports import discover, resolve, usb_id_for`.
- add:

```python
def _open(port_arg):
    """Open whatever board is on the port, with the driver it needs."""
    port = resolve(port_arg)
    return open_device(port, usb_id=usb_id_for(port))
```

- in `cmd_ping`, `cmd_i2c_scan`, `cmd_spi_id`: replace `with BusPirate(resolve(args.port)) as bp:` with `with _open(args.port) as bp:`.
- in `cmd_ping` replace the BBIO line with:

```python
        if bp.bitbang_version is not None:
            print(f"  bitbang protocol BBIO{bp.bitbang_version}")
        else:
            print(f"  protocol {bp.protocol_label}")
```

- add `"bp6"` to the `--demo` `choices` and say "or a Bus Pirate 6" in its help.

Run `grep -n "BusPirate(" buspirate/cli.py` — nothing should remain except imports used elsewhere; drop an unused `BusPirate` import if flake would flag it.

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_bp6_ports.py tests/test_ports.py tests/test_connect.py -q`
Expected: all PASS. If an existing `tests/test_ports.py` fake `comports` entry lacks `location`, give `pair_bp6` a `getattr(item, "location", None)`.

- [ ] **Step 7: Commit**

```bash
git add buspirate/ports.py buspirate/connect.py buspirate/cli.py tests/test_bp6_ports.py
git commit -m "Find a Bus Pirate 6 by its USB ID, pair its two ports, and open it from the CLI"
```

---

### Task 8: The dashboard session knows the BP6

**Files:**
- Modify: `buspirate/web/session.py`, `buspirate/web/server.py`, `buspirate/web/static/app.js`
- Test: `tests/test_dashboard_bp6.py`

**Interfaces:**
- Consumes: `BusPirate6`, `FakeBp6`, `capabilities_for("bp6")`.
- Produces: simulated port `simulated-bp6` (name `"simulated Bus Pirate 6"`); `session.status()` gains `"power"` (for `bp6`: `{"on", "set_mv", "set_ma", "mv", "ma", "tripped", "pullups"}`, else `None`) and `"pullups"` (bool); `_supplies_on()` follows the BP6's measured status; `hiz_blocking()` calls `bp.hiz()` when the device has one; `refresh_power_blocking()` (≤ once per 0.8 s, skipped while streaming); traffic entries gain `"summary"`; terminal caption for the BP6.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_bp6.py
"""The dashboard against a simulated Bus Pirate 6."""

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")

from buspirate.web.server import create_app  # noqa: E402


@pytest.fixture
def client():
    app = create_app(use_fake=True, fake_variant="bp6")
    with fastapi_testclient.TestClient(app) as client:
        yield client


def run(client, panel, action, **params):
    response = client.post("/api/run", json={"panel": panel, "action": action, "params": params})
    return response.status_code, response.json()


def connect(client):
    status, body = run(client, "connection", "connect", port="")
    assert status == 200, body
    return body


def state(client):
    return client.get("/api/state").json()


def test_the_demo_offers_the_bp6_first(client):
    ports = client.get("/api/ports").json()["ports"]
    assert ports[0]["device"] == "simulated-bp6"
    assert ports[0]["note"] == "simulated Bus Pirate 6, no hardware"


def test_connecting_shows_the_board_and_its_power(client):
    connect(client)
    data = state(client)
    assert data["status"]["description"] == "Bus Pirate 6, firmware 2026-10-12"
    assert data["variant"] == "bp6"
    assert data["status"]["power"]["on"] is False


def test_rawwire_and_bitbang_pins_are_hidden(client):
    connect(client)
    caps = state(client)["status"]["capabilities"]
    assert "rawwire" not in caps and "bitbang_pins" not in caps


def test_i2c_scan_finds_the_simulated_sensor(client):
    connect(client)
    status, body = run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    assert status == 200, body
    assert "0x76" in str(body)


def test_traffic_carries_a_summary(client):
    connect(client)
    traffic = state(client)["traffic"]
    assert any(entry.get("summary") == "Status request" for entry in traffic)


def test_hiz_releases_the_bp6(client):
    connect(client)
    run(client, "i2c", "scan", power=True, pullups=True, speed=2)
    response = client.post("/api/run", json={"panel": "connection", "action": "hiz", "params": {}})
    assert response.status_code == 200, response.json()
    assert state(client)["status"]["live"] == []


def test_the_terminal_opens_on_the_bp6_without_a_reset_warning(client):
    connect(client)
    panels = {p["id"]: p for p in state(client)["panels"]}
    open_terminal = {a["name"]: a for a in panels["terminal"]["actions"]}["open_terminal"]
    assert open_terminal["confirm"] == ""
```

Before writing these, check how the HiZ button is invoked in `tests/test_dashboard.py` (search `hiz`) and the exact i2c scan action name/params in `buspirate/web/panels/i2c.py`; adjust the two `run(...)` calls to match those names exactly.

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_dashboard_bp6.py -q`
Expected: FAIL (`fake_variant="bp6"` unknown / no `simulated-bp6`).

- [ ] **Step 3: Session changes (`buspirate/web/session.py`)**

1. `SIMULATED_VARIANTS = ("v3", "v4", "bitpirate", "bp6")` and `SIMULATED_NAMES["bp6"] = "simulated Bus Pirate 6"`.
2. In `_open_device`, before `if variant is not None:` add:

```python
        if variant == "bp6":
            from ..bp6 import BusPirate6
            from ..simulator_bp6 import FakeBp6

            fake = FakeBp6()
            return BusPirate6(
                FakeBp6.BINARY,
                terminal_port=FakeBp6.TERMINAL,
                serial_factory=fake.factory(),
                on_traffic=self._on_traffic,
                connect_timeout=0.2,
            ).open()
```

3. Traffic summaries. `self.bp` is still `None` while the board is being opened (connect_blocking assigns it afterwards), and the status request sent during `open()` should be summarised too, so the session keeps its own flag:
   - in `__init__`: `self._bpio2_traffic = False`
   - in `connect_blocking`, right after `self.port_info = self._describe_port(resolved)`:

```python
        self._bpio2_traffic = (
            simulated_variant(resolved) == "bp6"
            or (self.port_info or {}).get("usb_id") == "1209:7331"
        )
```

   - in `disconnect_blocking` and `_drop_connection`: `self._bpio2_traffic = False`
   - in `_on_traffic`, after building `entry`:

```python
        if self._bpio2_traffic and not isinstance(self.stream, TerminalState):
            from ..bp6.protocol import describe_frame

            entry["summary"] = describe_frame(direction, data)
```

   (Check that `_describe_port()` puts `usb_id` in `port_info` for real ports — it is what `_open_device` already passes to `open_device`.)

4. Replace `_supplies_on`:

```python
    def _supplies_on(self) -> bool:
        status = getattr(self.bp, "last_status", None)
        if status is not None:
            return bool(status.psu_enabled)  # the Bus Pirate 6 says, so ask it
        if self._mode is not None:
            return bool(self._mode.peripherals.get("power"))
        return bool(self.last_pins.get("power"))
```

5. In `live()`, read pull-ups from the BP6 too: replace the pull-ups block start with

```python
        status = getattr(self.bp, "last_status", None)
        if status is not None:
            pullups = status.pullups
        elif self._mode is not None:
```

6. In `hiz_blocking`, replace the `else:` branch with:

```python
        elif hasattr(self.bp, "hiz"):
            self.bp.hiz()  # a Bus Pirate 6: one BPIO2 request releases everything
        else:
            # A Bit Pirate has no bitbang: its own HiZ mode releases the pins.
            self.bp.cli.command("m hiz")
```

7. Add the power refresh and status fields:

```python
    POWER_REFRESH_SECONDS = 0.8

    def wants_power_refresh(self) -> bool:
        return (
            self.bp is not None and self.bp.is_open and self.stream is None
            and getattr(self.bp, "last_status", None) is not None
            and time.monotonic() - self._power_read_at >= self.POWER_REFRESH_SECONDS
        )

    def refresh_power_blocking(self) -> None:
        if not self.wants_power_refresh():
            return
        self._power_read_at = time.monotonic()
        try:
            self.bp.status()
        except (BusPirateError, OSError):
            pass  # the next poll tries again; a dead port shows as USB detached
```

Initialise `self._power_read_at = 0.0` in `__init__`. In `status()` (connected branch) add:

```python
            "power": self._power(),
            "pullups": bool(self._pullups_on()),
```

with

```python
    def _power(self) -> Optional[Dict[str, Any]]:
        status = getattr(self.bp, "last_status", None)
        if status is None or isinstance(self.stream, TerminalState):
            return None
        return {"on": status.psu_enabled, "set_mv": self.bp.psu_mv, "set_ma": self.bp.psu_ma,
                "mv": status.psu_mv, "ma": status.psu_ma, "tripped": status.psu_tripped,
                "pullups": status.pullups}

    def _pullups_on(self) -> bool:
        status = getattr(self.bp, "last_status", None)
        if status is not None:
            return status.pullups
        if self._mode is not None:
            return bool(self._mode.peripherals.get("pullups"))
        return bool(self.last_pins.get("pullups"))
```

8. In `enter_terminal`, make the caption three-way:

```python
        variant = self.bp.profile.variant
        if variant == "bitpirate":
            caption = "The Bit Pirate's own command line. Type a command; 'help' lists them."
        elif variant == "bp6":
            caption = ("The Bus Pirate 6's own terminal. Type a command; '?' lists them. "
                       "If it asks 'VT100 compatible color mode?', answer n.")
        else:
            caption = "The Bus Pirate's own terminal. Type a command; '?' lists them."
```

- [ ] **Step 4: Server: refresh power on each poll**

In `buspirate/web/server.py` `state()`, at the top:

```python
        if session.wants_power_refresh():
            await session.call(session.refresh_power_blocking)
```

- [ ] **Step 5: Frontend: name the variant, show power and summaries**

In `app.js`:
- `VARIANT_LABELS` gains `bp6: "Bus Pirate 6"`.
- In `renderStatus()`, after the stream/mode suffix, append power:

```javascript
  const power = s.connected && s.power
    ? ` · ${(s.power.mv / 1000).toFixed(2)} V / ${s.power.ma} mA` + (s.power.tripped ? " · CURRENT LIMIT TRIPPED" : "")
    : "";
```

and use it: `` `${...}${s.description}` + (...) + power ``.
- In `addLogLine`, show the summary before the hex:

```javascript
      event.summary ? el("span", { class: "summary", text: event.summary + "  " }) : null,
      event.hex
```

and in `app.css` add `.summary { color: var(--accent, #6cf); }` next to the existing log line styles.

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_dashboard_bp6.py tests/test_dashboard.py tests/test_dashboard_bitpirate.py -q`
Expected: all PASS. (The `open_terminal` confirm test passes only after Task 9 adds the board's panel override; mark it `xfail(strict=True)` now and remove the mark in Task 9 — or move that one test into Task 9.)

- [ ] **Step 7: Commit**

```bash
git add buspirate/web/session.py buspirate/web/server.py buspirate/web/static/app.js buspirate/web/static/app.css tests/test_dashboard_bp6.py
git commit -m "Run the dashboard on a Bus Pirate 6, with its power, pull-ups and traffic in plain words"
```

---

### Task 9: Power & pull-ups panel, board drawing and wiring

**Files:**
- Create: `buspirate/web/panels/power6.py`, `scripts/draw_bp6_board.py`, `buspirate/web/static/img/board-bp6.svg` (generated)
- Modify: `buspirate/web/wiring.py`, `buspirate/web/static/img/CREDITS.md` (one line: "board-bp6.svg is drawn by scripts/draw_bp6_board.py from the firmware's pin map")
- Test: `tests/test_dashboard_bp6.py` (extend)

**Interfaces:**
- Consumes: `BusPirate6.set_power`, `set_pullups`, `status`; session `status()["power"]`, `["supplies"]`, `["pullups"]`.
- Produces: panel id `power6` (requires `CAP_PSU_PROGRAMMABLE`, `mode=None`, `order=60`, `doc="bus-pirate-6"`); actions `supplies` (switch, `on`), `pullups` (switch on `"pullups"`, `on`), `quick_1v8`, `quick_3v3`, `quick_5v0` (5 V has a static confirm), `set_supply` (params `millivolts` 800–5000, `limit_ma` 0–500, `confirm_high` bool), `reenable`, `readings`; `BOARDS["bp6"]`, `LED_RULES["bp6"] = {}`, `LED_NOTES["bp6"]`; constants `BP6_HEADER = ["VOUT", "IO0", ..., "IO7", "GND"]`.

- [ ] **Step 1: Write the failing tests (append to `tests/test_dashboard_bp6.py`)**

```python
def panels(client):
    return {p["id"]: p for p in state(client)["panels"]}


def test_the_power_panel_is_offered_and_the_bitbang_one_is_not(client):
    connect(client)
    ids = panels(client)
    assert "power6" in ids
    status, body = run(client, "pins", "set_pins", pullups=False, aux=False, mosi=False,
                       clk=False, miso=False, cs=False)
    assert status != 200


def test_quick_voltage_buttons_switch_power_on(client):
    connect(client)
    status, body = run(client, "power6", "quick_3v3")
    assert status == 200, body
    power = state(client)["status"]["power"]
    assert power["on"] and power["set_mv"] == 3300 and power["mv"] == 3300


def test_high_voltage_needs_the_tick(client):
    connect(client)
    status, body = run(client, "power6", "set_supply", millivolts=5000, limit_ma=300, confirm_high=False)
    assert status == 200
    assert state(client)["status"]["power"]["on"] is False
    assert "tick" in str(body).lower()
    status, body = run(client, "power6", "set_supply", millivolts=5000, limit_ma=300, confirm_high=True)
    assert state(client)["status"]["power"]["mv"] == 5000


def test_no_limit_needs_the_tick_too(client):
    connect(client)
    run(client, "power6", "set_supply", millivolts=3300, limit_ma=0, confirm_high=False)
    assert state(client)["status"]["power"]["on"] is False


def test_a_tripped_supply_is_reported_with_a_re_enable_action(client):
    connect(client)
    run(client, "power6", "set_supply", millivolts=3300, limit_ma=5, confirm_high=False)
    power = state(client)["status"]["power"]
    assert power["tripped"] and not power["on"]
    status, body = run(client, "power6", "readings")
    assert "Current limit tripped" in str(body)
    actions = {a["name"] for a in panels(client)["power6"]["actions"]}
    assert "reenable" in actions


def test_the_pullups_switch_shows_its_state(client):
    connect(client)
    run(client, "power6", "pullups", on=True)
    assert state(client)["status"]["pullups"] is True


def test_the_board_is_the_bp6_header(client):
    connect(client)
    board = state(client)["board"]
    assert board["image"] == "/static/img/board-bp6.svg"
    assert list(board["pins"]) == ["VOUT"] + [f"IO{i}" for i in range(8)] + ["GND"]
    i2c = {w["target"]: w["signal"] for w in panels(client)["i2c"]["wiring"]}
    assert i2c["SDA"] == "IO0" and i2c["SCL"] == "IO1"
```

(`FakeBp6` defaults to `load_ma=12`, so a 5 mA limit trips it. If `run()` for an action the profile refuses returns 200 with an error body in this codebase rather than a 4xx, change the `status != 200` assertion to whatever `tests/test_dashboard_bitpirate.py` asserts for a refused capability.)

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_dashboard_bp6.py -q`
Expected: the new tests FAIL (`no panel 'power6'`, wrong board).

- [ ] **Step 3: Write the panel**

```python
# buspirate/web/panels/power6.py
"""The Bus Pirate 6's programmable supply and pull-ups, in one-click controls."""

from __future__ import annotations

from ... import device as device_module
from ..registry import Action, Panel, Param, keyvalue, text

HIGH_MV = 3600
_TICK = ("Tick 'I have checked the target' first: above 3.6 V, or with no current "
         "limit, a mistake can damage a 3.3 V part.")


def _report(ctx, message: str, tone: str = "good"):
    status = ctx.bp.status()
    if status.psu_tripped:
        return text(
            "Current limit tripped — power cut. The target drew more than "
            f"{ctx.bp.psu_ma} mA. Check the wiring for a short, then press Re-enable.",
            tone="warn",
        )
    return text(message, tone=tone)


def _supplies(ctx, on):
    ctx.bp.set_power(on)
    if not on:
        return text("The supply is off.", tone="info")
    return _report(ctx, f"The supply is on: {ctx.bp.psu_mv / 1000:.2f} V, limit "
                        f"{ctx.bp.psu_ma or 'none'}{' mA' if ctx.bp.psu_ma else ''}.")


def _quick(millivolts):
    def handler(ctx):
        ctx.bp.set_power(True, millivolts=millivolts)
        return _report(ctx, f"The supply is on at {millivolts / 1000:.1f} V, limit {ctx.bp.psu_ma} mA.")
    return handler


def _set_supply(ctx, millivolts, limit_ma, confirm_high):
    if (millivolts > HIGH_MV or limit_ma == 0) and not confirm_high:
        return text(_TICK, tone="warn")
    ctx.bp.set_power(True, millivolts=millivolts, milliamps=limit_ma)
    return _report(ctx, f"The supply is on at {millivolts / 1000:.2f} V, limit "
                        f"{limit_ma or 'none'}{' mA' if limit_ma else ''}.")


def _reenable(ctx):
    ctx.bp.set_power(False)
    ctx.bp.set_power(True)
    return _report(ctx, "The supply is back on.")


def _pullups(ctx, on):
    ctx.bp.set_pullups(on)
    return text("Pull-ups on: 10 kΩ from every IO pin to the supply." if on
                else "Pull-ups off.", tone="info")


def _readings(ctx):
    status = ctx.bp.status()
    rows = [
        ["Supply", "on" if status.psu_enabled else "off"],
        ["Set to", f"{status.psu_set_mv / 1000:.2f} V, limit "
                   f"{status.psu_set_ma or 'none'}{' mA' if status.psu_set_ma else ''}"],
        ["Measured", f"{status.psu_mv / 1000:.2f} V, {status.psu_ma} mA"],
        ["Pull-ups", "on" if status.pullups else "off"],
    ]
    labels = list(status.pin_labels[1:9]) or [""] * 8
    for index, millivolts in enumerate(status.adc_mv):
        name = f"IO{index}" + (f" ({labels[index]})" if index < len(labels) and labels[index] else "")
        rows.append([name, f"{millivolts / 1000:.2f} V"])
    caption = ("Current limit tripped — power cut. Press Re-enable once the fault is fixed."
               if status.psu_tripped else "Read from the board just now.")
    return keyvalue(rows, caption=caption)


PANEL = Panel(
    id="power6",
    requires=device_module.CAP_PSU_PROGRAMMABLE,
    doc="bus-pirate-6",
    title="Power & pull-ups",
    blurb="The Bus Pirate 6's adjustable supply on VOUT, its current limit, and the pull-ups.",
    mode=None,
    order=60,
    notes=[
        "VOUT powers the target: 0.8 to 5.0 V, up to 500 mA, cut off at the "
        "current limit you set (300 mA unless you change it).",
        "The pull-ups are 10 kΩ from each IO pin to the supply, so they need the "
        "supply on (or an external voltage on VOUT) to do anything.",
        "The status bar shows the measured voltage and current while you work.",
    ],
    actions=[
        Action(name="supplies", label="Supply on VOUT", switch="supplies",
               params=[Param("on", "bool", "On", default=False)], handler=_supplies,
               help="On at the voltage and limit below."),
        Action(name="pullups", label="Pull-ups", switch="pullups",
               params=[Param("on", "bool", "On", default=False)], handler=_pullups),
        Action(name="quick_1v8", label="1.8 V", button="1.8 V", handler=_quick(1800)),
        Action(name="quick_3v3", label="3.3 V", button="3.3 V", primary=True, handler=_quick(3300)),
        Action(name="quick_5v0", label="5.0 V", button="5.0 V", handler=_quick(5000),
               confirm="5 V can damage a 3.3 V part. Is the target a 5 V device?"),
        Action(
            name="set_supply", label="Set voltage and current limit", button="Switch on",
            params=[
                Param("millivolts", "int", "Voltage (mV)", default=3300, minimum=800, maximum=5000),
                Param("limit_ma", "int", "Current limit (mA, 0 = none)", default=300,
                      minimum=0, maximum=500),
                Param("confirm_high", "bool", "I have checked the target takes this", default=False,
                      help="Needed above 3.6 V, or with no current limit."),
            ],
            handler=_set_supply,
        ),
        Action(name="reenable", label="Re-enable after a trip", button="Re-enable",
               handler=_reenable, help="Switches the supply back on after the limit cut it."),
        Action(name="readings", label="Read voltages and current", recipe=True, handler=_readings),
    ],
)
```

Check how `/api/state` decides a `switch` action is on: it reads `state.status[action.switch]`. `status["supplies"]` already exists; `status["pullups"]` was added in Task 8.

- [ ] **Step 4: Board, wiring, LEDs (`buspirate/web/wiring.py`)**

Add after `_BOARD_BITPIRATE`:

```python
# The Bus Pirate 6's 10-pin header, as drawn in static/img/board-bp6.svg by
# scripts/draw_bp6_board.py from this same list. Pin map from the firmware's
# src/pirate.h (M_I2C_SDA BIO0, M_SPI_CLK BIO6, ...).
BP6_HEADER = ["VOUT", "IO0", "IO1", "IO2", "IO3", "IO4", "IO5", "IO6", "IO7", "GND"]
BP6_GEOMETRY = {"width": 700, "height": 525, "x": 350, "first_y": 110, "pitch": 34}


def _bp6_pins():
    g = BP6_GEOMETRY
    pins = {name: [g["x"], g["first_y"] + i * g["pitch"]] for i, name in enumerate(BP6_HEADER)}
    side = {name: ("left" if i % 2 == 0 else "right") for i, name in enumerate(BP6_HEADER)}
    return pins, side


_BP6_PINS, _BP6_SIDE = _bp6_pins()
_BP6_GND = _wire("GND", "GND", "always connect this first")
_BP6_VOUT = _wire("VOUT", "VCC", "the adjustable supply — set it on Power & pull-ups")
_BP6_NOTE = ("Every IO pin is buffered and works from 1.2 to 5 V, following VOUT. "
             "Switch the supply on, or feed the target's own voltage into VOUT.")

_BOARD_BP6 = {
    "image": "/static/img/board-bp6.svg",
    "width": BP6_GEOMETRY["width"],
    "height": BP6_GEOMETRY["height"],
    "gutter": 290,
    "gutter_left": 290,
    "label": "Bus Pirate 6",
    "pins": _BP6_PINS,
    "side": _BP6_SIDE,
    "leds": {},
    "cable": False,
    "caveat": ("Drawn from the firmware's pin map. Your probe cable's colours may "
               "differ — follow the labels printed on the Bus Pirate 6's case."),
    "panels": {
        "terminal": {
            "blurb": "The Bus Pirate 6's own terminal — the `HiZ>` prompt, on its first USB port.",
            "actions": {
                "open_terminal": {
                    "confirm": "",
                    "help": "Opens the Bus Pirate 6's terminal port. Nothing is "
                    "reset. Everything else in the dashboard is unavailable until you "
                    "close it; when you do, the dashboard re-reads the board.",
                },
            },
        },
        "i2c": {"wiring": [_wire("IO0", "SDA", "data, both directions"),
                           _wire("IO1", "SCL", "clock"), _BP6_GND, _BP6_VOUT],
                "notes": ["I2C needs pull-ups: switch them on (10 kΩ) on Power & pull-ups.",
                          _BP6_NOTE]},
        "spi": {"wiring": [_wire("IO6", "SCK / CLK", "clock"),
                           _wire("IO7", "DI / MOSI", "Bus Pirate out, chip in"),
                           _wire("IO4", "DO / MISO", "chip out, Bus Pirate in"),
                           _wire("IO5", "CS / SS", "active low"), _BP6_GND, _BP6_VOUT],
                "notes": ["Tie a flash chip's WP and HOLD pins high.",
                          "A reply of all 0x00 or 0xFF almost always means MISO is not connected.",
                          _BP6_NOTE]},
        "uart": {"wiring": [_wire("IO4", "RX", "the Bus Pirate's TX drives the target's receive pin"),
                            _wire("IO5", "TX", "the Bus Pirate's RX listens to the target's transmit pin"),
                            _BP6_GND],
                 "notes": ["TX and RX cross over. If you see nothing, swap IO4 and IO5.",
                           "8 data bits with no or even parity. Odd parity and 9 bits are "
                           "only in the board's own terminal.", _BP6_NOTE]},
        "onewire": {"wiring": [_wire("IO0", "DQ", "data"), _BP6_GND, _BP6_VOUT],
                    "notes": ["Switch the pull-ups on: 1-Wire needs one on the data line.",
                              "The dashboard finds one device. With several on the bus, type "
                              "'scan' in the Terminal panel after 'm 1wire'.", _BP6_NOTE]},
    },
}
```

Add `"bp6": _BOARD_BP6,` to `BOARDS` (after `bitpirate`), `"bp6": {},` to `LED_RULES`, and to `LED_NOTES`:

```python
    "bp6": "The Bus Pirate 6's 18 RGB LEDs belong to its firmware, and the "
    "dashboard does not know what they show. Its status bar shows the supply "
    "and current instead.",
```

Check `server._panels_json` (lines ~120–140) merges `board["panels"][id]["wiring"]` as a list of dicts with `signal/colour/target/note` — the same shape `_wire()` produces; it already handles the Bit Pirate, so no server change should be needed. If `onewire` overrides are not applied because the Bit Pirate never needed one, it is the same code path; verify with the test.

- [ ] **Step 5: Draw the board**

```python
# scripts/draw_bp6_board.py
"""Draw static/img/board-bp6.svg from wiring.BP6_HEADER and BP6_GEOMETRY.

Run: .venv/bin/python scripts/draw_bp6_board.py
"""

from pathlib import Path

from buspirate.web.wiring import BP6_GEOMETRY, BP6_HEADER

g = BP6_GEOMETRY
out = Path(__file__).resolve().parent.parent / "buspirate/web/static/img/board-bp6.svg"
top = g["first_y"] - 40
bottom = g["first_y"] + (len(BP6_HEADER) - 1) * g["pitch"] + 40
parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {g["width"]} {g["height"]}" '
    f'width="{g["width"]}" height="{g["height"]}" font-family="Helvetica, Arial, sans-serif">',
    f'<rect x="230" y="20" width="240" height="{g["height"] - 40}" rx="24" fill="#1d1f24" stroke="#555"/>',
    '<text x="350" y="60" fill="#ddd" font-size="22" text-anchor="middle">Bus Pirate 6</text>',
    f'<rect x="{g["x"] - 22}" y="{top}" width="44" height="{bottom - top}" rx="4" fill="#111" stroke="#777"/>',
]
for index, name in enumerate(BP6_HEADER):
    y = g["first_y"] + index * g["pitch"]
    parts.append(f'<circle cx="{g["x"]}" cy="{y}" r="9" fill="#c9a227" stroke="#7a5c00"/>')
    anchor, x = ("end", g["x"] - 34) if index % 2 == 0 else ("start", g["x"] + 34)
    parts.append(f'<text x="{x}" y="{y + 6}" fill="#eee" font-size="16" text-anchor="{anchor}">{name}</text>')
parts.append(f'<text x="350" y="{g["height"] - 40}" fill="#999" font-size="14" '
             'text-anchor="middle">USB-C on top · header viewed from the front</text>')
parts.append("</svg>")
out.write_text("\n".join(parts) + "\n", encoding="utf-8")
print(f"wrote {out}")
```

Run: `.venv/bin/python scripts/draw_bp6_board.py`
Expected: `wrote …/board-bp6.svg`.

- [ ] **Step 6: Run the tests (remove the Task 8 xfail on the terminal-confirm test)**

Run: `.venv/bin/python -m pytest tests/test_dashboard_bp6.py tests/test_dashboard.py tests/test_dashboard_bitpirate.py -q`
Expected: all PASS.

- [ ] **Step 7: Look at it**

Run `make demo`, pick "simulated Bus Pirate 6", connect, and check: the board drawing shows 10 labelled pins; I2C's hook-up highlights IO0/IO1; Power & pull-ups shows the two switches with their state, the three quick buttons (5.0 V asks first), and the status bar shows `· 3.30 V / 12 mA` after 3.3 V. Stop the server.

- [ ] **Step 8: Commit**

```bash
git add buspirate/web/panels/power6.py buspirate/web/wiring.py scripts/draw_bp6_board.py buspirate/web/static/img/board-bp6.svg buspirate/web/static/img/CREDITS.md tests/test_dashboard_bp6.py
git commit -m "Add the Bus Pirate 6's power and pull-up controls, its header drawing and its wiring"
```

---

### Task 10: The guide viewer — groups, sub-folders, files, search

**Files:**
- Modify: `buspirate/web/docs.py`, `buspirate/web/server.py`
- Test: `tests/test_docs_viewer.py`

**Interfaces:**
- Produces in `buspirate.web.docs`: page names may be `name`, `official/name` or `official/section/name` (each segment `_SAFE_NAME`); `available()` returns dicts `{"name", "title", "group"}` where `group` is `"This app"` or `"Official Bus Pirate 5/6 manual"` (official order from `docs/official/order.json`: a list of page names); `read(name)` accepts those names; `file_path(relative: str) -> Optional[str]` (an image under `docs/`, extensions `.png .jpg .jpeg .gif .svg .webp` only, resolved path must stay inside `DOCS_DIR`); `search(query: str, limit: int = 20) -> List[Dict]` returning `{"name", "title", "group", "snippet"}`, title matches first, then by number of text matches.
- Produces routes: `GET /api/docs-file/{path:path}` (FileResponse or 404) and `GET /api/docs-search?q=...` → `{"results": [...]}`. Keep `GET /api/docs/{name}` but declare it as `{name:path}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_docs_viewer.py
"""The in-app guide: our pages, the official manual, its images, and search."""

import json

import pytest

from buspirate.web import docs


@pytest.fixture
def tree(tmp_path, monkeypatch):
    (tmp_path / "official" / "devices").mkdir(parents=True)
    (tmp_path / "official" / "images" / "fw").mkdir(parents=True)
    (tmp_path / "user-guide.md").write_text("# User guide\n\nStart here.\n")
    (tmp_path / "i2c.md").write_text("# I2C\n\nScan the bus.\n")
    (tmp_path / "official" / "index.md").write_text("# Bus Pirate manual\n")
    (tmp_path / "official" / "devices" / "24c02.md").write_text("# 24C02 EEPROM\n\nAn I2C eeprom. I2C I2C.\n")
    (tmp_path / "official" / "order.json").write_text(json.dumps(["official/index", "official/devices/24c02"]))
    (tmp_path / "official" / "images" / "fw" / "a.png").write_bytes(b"\x89PNG")
    (tmp_path / "secret.txt").write_text("no")
    monkeypatch.setattr(docs, "DOCS_DIR", str(tmp_path))
    return tmp_path


def test_pages_are_grouped(tree):
    pages = docs.available()
    assert [p["name"] for p in pages] == ["user-guide", "i2c", "official/index", "official/devices/24c02"]
    assert pages[0]["group"] == "This app"
    assert pages[-1]["group"] == "Official Bus Pirate 5/6 manual"
    assert pages[-1]["title"] == "24C02 EEPROM"


def test_nested_pages_are_read(tree):
    assert docs.read("official/devices/24c02").startswith("# 24C02")


@pytest.mark.parametrize("name", ["../secret", "official/../../x", "/etc/passwd", "official//x", "a/b/c/d"])
def test_bad_names_are_refused(tree, name):
    assert docs.read(name) is None


def test_images_are_served(tree):
    assert docs.file_path("official/images/fw/a.png").endswith("a.png")


@pytest.mark.parametrize("path", ["secret.txt", "../x.png", "official/images/../../secret.txt", "/etc/hosts"])
def test_doc_files_cannot_escape_the_docs_directory(tree, path):
    assert docs.file_path(path) is None


def test_doc_files_refuse_symlinks_out(tree, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "x.png"
    outside.write_bytes(b"\x89PNG")
    (tree / "official" / "images" / "link.png").symlink_to(outside)
    assert docs.file_path("official/images/link.png") is None


def test_search_puts_title_matches_first(tree):
    results = docs.search("i2c")
    assert results[0]["name"] == "i2c"
    assert {r["name"] for r in results} == {"i2c", "official/devices/24c02"}
    assert "I2C" in results[1]["snippet"]


def test_empty_search(tree):
    assert docs.search("  ") == []
```

Also add to `tests/test_dashboard.py` (next to the other guide tests):

```python
def test_doc_file_route_refuses_traversal(client):
    assert client.get("/api/docs-file/..%2F..%2Fpyproject.toml").status_code == 404


def test_doc_search_route(client):
    body = client.get("/api/docs-search", params={"q": "terminal"}).json()
    assert body["results"]
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_docs_viewer.py -q`
Expected: FAIL (`group` key missing / `file_path` not defined).

- [ ] **Step 3: Implement in `buspirate/web/docs.py`**

Replace the module's functions below `_SAFE_NAME` with:

```python
APP_GROUP = "This app"
OFFICIAL_GROUP = "Official Bus Pirate 5/6 manual"
OFFICIAL = "official"
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
MAX_DEPTH = 3


def _segments(name: str) -> Optional[List[str]]:
    """A page or file name split safely, or None. No '..', no empty parts."""
    if not name or name.startswith("/") or "\\" in name:
        return None
    parts = name.split("/")
    if len(parts) > MAX_DEPTH or any(not _SAFE_NAME.match(p) or p in (".", "..") for p in parts):
        return None
    return parts


def _inside(path: str) -> bool:
    real, root = os.path.realpath(path), os.path.realpath(DOCS_DIR)
    return os.path.commonpath([real, root]) == root


def _title_of(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def _page(name: str) -> Optional[Dict[str, str]]:
    path = os.path.join(DOCS_DIR, *name.split("/")) + ".md"
    try:
        with open(path, encoding="utf-8") as handle:
            head = handle.read(600)
    except OSError:
        return None
    group = OFFICIAL_GROUP if name.startswith(OFFICIAL + "/") else APP_GROUP
    return {"name": name, "title": _title_of(head, name.rsplit("/", 1)[-1]), "group": group}


def _official_order() -> List[str]:
    try:
        with open(os.path.join(DOCS_DIR, OFFICIAL, "order.json"), encoding="utf-8") as handle:
            return [n for n in json.load(handle) if _segments(n)]
    except (OSError, ValueError):
        return []


def available() -> List[Dict[str, str]]:
    """Our pages in reading order, then the official manual in its own order."""
    if not os.path.isdir(DOCS_DIR):
        return []
    names = sorted(
        entry[:-3] for entry in os.listdir(DOCS_DIR)
        if entry.endswith(".md") and _SAFE_NAME.match(entry)
    )
    ordered = [n for n in ORDER if n in names] + [n for n in names if n not in ORDER]
    ordered += _official_order()
    return [page for page in (_page(n) for n in ordered) if page is not None]


def read(name: str) -> Optional[str]:
    """One page's Markdown, or None. Names cannot walk out of docs/."""
    parts = _segments(name)
    if parts is None:
        return None
    path = os.path.join(DOCS_DIR, *parts) + ".md"
    if not os.path.isfile(path) or not _inside(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def file_path(relative: str) -> Optional[str]:
    """An image under docs/, or None for anything else."""
    parts = (relative or "").split("/")
    if (not relative or relative.startswith("/") or "\\" in relative or len(parts) > 6
            or any(not _SAFE_NAME.match(p) or p in (".", "..") for p in parts)):
        return None
    path = os.path.join(DOCS_DIR, *parts)
    if os.path.splitext(path)[1].lower() not in IMAGE_TYPES:
        return None
    if not os.path.isfile(path) or not _inside(path):
        return None
    return path


def search(query: str, limit: int = 20) -> List[Dict[str, str]]:
    """Pages matching ``query``: title matches first, then by how often."""
    words = query.lower().split()
    if not words:
        return []
    scored = []
    for page in available():
        text = read(page["name"]) or ""
        lower = text.lower()
        hits = sum(lower.count(w) for w in words)
        in_title = all(w in page["title"].lower() for w in words)
        if not hits and not in_title:
            continue
        first = min((lower.find(w) for w in words if w in lower), default=0)
        snippet = " ".join(text[max(0, first - 60): first + 100].split())
        scored.append(((0 if in_title else 1, -hits), dict(page, snippet=snippet)))
    scored.sort(key=lambda item: item[0])
    return [page for _, page in scored[:limit]]
```

Add `import json` at the top. Add `"bus-pirate-6"` to `ORDER` after `"bus-pirate-v4"` (the page arrives in Task 13; `available()` skips missing names).

- [ ] **Step 4: Routes in `buspirate/web/server.py`**

Change `@app.get("/api/docs/{name}")` to `@app.get("/api/docs/{name:path}")`, and add:

```python
    @app.get("/api/docs-file/{path:path}")
    async def doc_file(path: str):
        found = docs_module.file_path(path)
        if found is None:
            return _error(f"no guide file called {path!r}", status=404)
        return FileResponse(found)

    @app.get("/api/docs-search")
    async def doc_search(q: str = "") -> Dict[str, Any]:
        return {"results": docs_module.search(q)}
```

with `from fastapi.responses import FileResponse` added to the imports (next to `JSONResponse`). Make sure the search route is declared **before** any catch-all that could shadow it.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_docs_viewer.py tests/test_dashboard.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add buspirate/web/docs.py buspirate/web/server.py tests/test_docs_viewer.py tests/test_dashboard.py
git commit -m "Let the guide hold the official manual: grouped pages, sub-folders, images and search"
```

---

### Task 11: The guide in the browser — groups, search box, images, callouts, anchors, banner

**Files:**
- Modify: `buspirate/web/static/app.js` (`openGuide`, `renderGuide`, `markdownToHtml`), `buspirate/web/static/app.css`
- Test: `tests/ui/frontend.mjs` (extend the guide section)

**Interfaces:**
- Consumes: `/api/docs` (pages with `group`), `/api/docs/{name}`, `/api/docs-file/{path}`, `/api/docs-search?q=`.
- Produces: `openGuide(name, anchor?)`; links `foo.md#bar` and `official/x/y.md#bar` open inside the guide and scroll to `#bar`; headings get `id` = `slug(text)`; images `![alt](p)` → `<img src="/api/docs-file/p" alt="alt" loading="lazy">` (http(s) sources untouched); blockquotes keep line breaks and render a first `**Note:**`/`**Warning:**`/`**Danger:**`/`**Tip:**` as a coloured callout (`class="callout callout--note"` etc.); official pages show the banner *"This is the official manual for the Bus Pirate's built-in terminal. You can type these commands in the Terminal panel."*

- [ ] **Step 1: Write the failing UI checks**

Open `tests/ui/frontend.mjs`, find the existing guide checks (search for `guide`), and add after them (same helper style the file already uses for `check`/`assert` and for waiting on the DOM):

```javascript
// The official manual is grouped, searchable, and renders images, callouts and anchors.
{
  const md = window.markdownToHtml(
    "# Title\n\n## The `c` menu\n\n> **Warning:**\n> Mind the voltage.\n\n![chip](official/images/fw/a.png)\n\n[jump](official/command-reference.md#the-c-menu)"
  );
  check("heading ids are slugged like Hugo's", md.includes('id="the-c-menu"'));
  check("callouts are classed", md.includes('class="callout callout--warning"'));
  check("images go through the docs-file route", md.includes('src="/api/docs-file/official/images/fw/a.png"'));
  check("links keep their anchor", md.includes('data-doc="official/command-reference"') && md.includes('data-anchor="the-c-menu"'));
  check("remote images are left alone", window.markdownToHtml("![x](https://e.com/a.png)").includes('src="https://e.com/a.png"'));
}
```

If `markdownToHtml` is not reachable as `window.markdownToHtml` in jsdom (functions declared at top level of a classic script are globals, so it should be), expose it with `window.markdownToHtml = markdownToHtml;` at the end of `app.js`.

- [ ] **Step 2: Run them to make sure they fail**

```bash
make demo &   # wait for it to start
node tests/ui/frontend.mjs
```

Expected: the five new checks FAIL. Stop the demo server.

- [ ] **Step 3: Implement in `app.js`**

Add a slug helper above `markdownToHtml` (same rule as Hugo/goldmark: lowercase, drop everything that is not a letter, digit, space, `-` or `_`, spaces to `-`):

```javascript
function slug(text) {
  return text
    .toLowerCase()
    .replace(/<[^>]+>/g, "")
    .replace(/&[a-z]+;/g, "")
    .replace(/[^\p{L}\p{N}\s_-]/gu, "")
    .trim()
    .replace(/\s/g, "-");
}
```

In `markdownToHtml`:
- in `inline`, **before** the link rule, add images:

```javascript
      .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (match, alt, src) =>
        /^https?:\/\//.test(src)
          ? `<img src="${src}" alt="${alt}" loading="lazy">`
          : `<img src="/api/docs-file/${src.replace(/^\/+/, "")}" alt="${alt}" loading="lazy">`
      )
```

- replace the link rule with:

```javascript
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, label, href) => {
        const doc = href.match(/^([^#:]+)\.md(?:#(.*))?$/);
        if (doc) {
          return `<a href="#" data-doc="${doc[1]}" data-anchor="${doc[2] || ""}">${label}</a>`;
        }
        if (href.startsWith("#")) return `<a href="#" data-anchor="${href.slice(1)}">${label}</a>`;
        return `<a href="${href}" target="_blank" rel="noreferrer">${label}</a>`;
      })
```

- headings: `blocks.push(`<h${level} id="${slug(heading[2])}">${inline(heading[2])}</h${level}>`);`
- blockquote: replace the existing block with:

```javascript
    if (line.startsWith("&gt;")) {
      const quote = [];
      while (index < lines.length && lines[index].startsWith("&gt;")) {
        quote.push(lines[index++].replace(/^&gt;\s?/, ""));
      }
      const kind = (quote[0] || "").match(/^\*\*(Note|Warning|Danger|Tip):\*\*/);
      const cls = kind ? ` class="callout callout--${kind[1].toLowerCase()}"` : "";
      blocks.push(`<blockquote${cls}>${quote.map(inline).join("<br>")}</blockquote>`);
      continue;
    }
```

In `openGuide`, take an anchor and scroll to it after rendering:

```javascript
async function openGuide(name, anchor = "") {
  ...existing body...
  renderGuide();
  if (anchor) {
    const target = document.getElementById(anchor);
    if (target) target.scrollIntoView();
  }
}
```

In `renderGuide`:
- build the picker with `<optgroup>` per `group`:

```javascript
  const groups = [];
  for (const p of state.guide.pages) {
    let group = groups.find((g) => g.label === p.group);
    if (!group) groups.push((group = { label: p.group, pages: [] }));
    group.pages.push(p);
  }
  const picker = el(
    "select",
    { onchange: (event) => openGuide(event.target.value) },
    ...groups.map((g) =>
      el("optgroup", { label: g.label },
        ...g.pages.map((p) => el("option", { value: p.name, selected: page && p.name === page.name }, p.title)))
    )
  );
```

- a search box under the bar:

```javascript
  const results = el("div", { class: "guide__results" });
  const search = el("input", {
    type: "search",
    class: "guide__search",
    placeholder: "Search the guides and the manual…",
    oninput: async (event) => {
      const q = event.target.value.trim();
      if (q.length < 2) return results.replaceChildren();
      const { results: found } = await api(`/api/docs-search?q=${encodeURIComponent(q)}`);
      results.replaceChildren(
        ...found.map((r) =>
          el("a", { href: "#", class: "guide__result", onclick: (e) => { e.preventDefault(); openGuide(r.name); } },
            el("strong", { text: r.title }), el("span", { class: "muted", text: ` — ${r.group}` }),
            el("div", { class: "muted", text: r.snippet }))
        )
      );
    },
  });
```

- the banner for official pages, and anchor-aware links:

```javascript
  const banner = page && page.name.startsWith("official/")
    ? el("p", { class: "guide__banner", text: "This is the official manual for the Bus Pirate's built-in terminal. You can type these commands in the Terminal panel." })
    : null;
  ...
  body.querySelectorAll("a[data-doc], a[data-anchor]").forEach((link) =>
    link.addEventListener("click", (event) => {
      event.preventDefault();
      if (link.dataset.doc) return openGuide(link.dataset.doc, link.dataset.anchor);
      const target = document.getElementById(link.dataset.anchor);
      if (target) target.scrollIntoView();
    })
  );
  root.replaceChildren(el("div", { class: "guide__bar" }, back, picker, search), results, banner, body);
```

- [ ] **Step 4: Styles in `app.css`**

```css
.guide__body img { max-width: 100%; height: auto; border-radius: 4px; }
.guide__search { flex: 1; min-width: 12rem; }
.guide__results { display: grid; gap: .4rem; margin: .5rem 0; }
.guide__result { display: block; padding: .4rem .6rem; border-radius: 4px; background: var(--panel, #1c1f26); text-decoration: none; }
.guide__banner { padding: .5rem .75rem; border-left: 4px solid #6cf; background: rgba(102, 204, 255, .08); }
.callout { border-left: 4px solid #6cf; padding: .5rem .75rem; background: rgba(102, 204, 255, .06); }
.callout--warning { border-color: #e0a800; background: rgba(224, 168, 0, .08); }
.callout--danger { border-color: #e5484d; background: rgba(229, 72, 77, .08); }
.callout--tip { border-color: #46a758; background: rgba(70, 167, 88, .08); }
```

(Use the variables `app.css` already defines for panel background and accent if the names differ — check the top of `app.css`.)

- [ ] **Step 5: Run the UI test and the Python tests**

```bash
make demo &
node tests/ui/frontend.mjs     # expected: all checks pass
kill %1
.venv/bin/python -m pytest -q  # expected: all pass
```

- [ ] **Step 6: Commit**

```bash
git add buspirate/web/static/app.js buspirate/web/static/app.css tests/ui/frontend.mjs
git commit -m "Show the guide in groups with a search box, and render images, callouts and section links"
```

---

### Task 12: Import the official manual

**Files:**
- Create: `scripts/import_official_docs.py`
- Create (generated): `docs/official/**` (pages, `images/`, `LICENSE`, `SOURCE.md`, `order.json`)
- Modify: `pyproject.toml` (`Pillow` in the `dev` extra)
- Test: `tests/test_import_official_docs.py`

**Interfaces:**
- Produces: `convert_page(text: str, page_path: str, repo: Path, report: List[str]) -> Tuple[str, str, int]` returning `(markdown, title, weight)`; `slug(text) -> str` (same rule as the JS one); `KEEP` sections; CLI `python scripts/import_official_docs.py --ref <sha> [--out docs/official]`.

Conversion rules (exactly these):

| Input | Output |
|---|---|
| TOML front matter `+++ … +++` | removed; `title = '…'` → `# …` first line; `weight = N` kept for ordering |
| `{{% alert context="info" %}}…{{% /alert %}}` | `> **Note:**` + each inner line prefixed `> ` (`warning`→Warning, `danger`→Danger, `success`→Tip, anything else→Note) |
| `{{< term "X" >}}…{{< /term >}}` | a ```` ```text ```` block of the inner HTML with tags stripped and entities decoded |
| `{{< termfile source="static/snippets/F.html" >}}` | the same, from that file (missing file → report + drop) |
| `{{% readfile "/_common/F.md" %}}` | that file's text, converted recursively (front matter dropped) |
| `{{< relref "/docs/a/b/#x" >}}` inside `(...)` | `official/a/b.md#x`; `/docs/a/` (a section) → `official/a/index.md`; a page not bundled → `https://docs.buspirate.com/docs/a/b/#x` |
| `{{< tabs … >}}` / `{{< /tabs >}}` | removed |
| `{{< tab "X" >}}` or `{{% tab name="X" %}}` | `#### X`; `{{< /tab >}}` removed |
| `{{< asciicast … >}}` | `[▶ Watch this as a recording on docs.buspirate.com](https://docs.buspirate.com/docs/<page path>/)` |
| `{{< btn … href="U" … >}}T{{< /btn >}}` | `[T](U)` |
| any other `{{< … >}}` / `{{% … %}}` | removed, and named in the report |
| `![a](/images/docs/P)` | `![a](official/images/P)`; the file copied from `assets/images/docs/P`, resized to ≤1200 px wide |
| `_index.md` | written as `index.md` |

Kept: `content/docs/_index.md`, `command-reference.md`, `license.md`, and the folders `tutorial-basics`, `devices`, `overview`, `logic-analyzer`, `binmode-reference`, `software`, `cables`. Everything else dropped.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_import_official_docs.py
"""The Hugo-to-Markdown conversion of the official manual, on small fixtures."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "import_official_docs.py"
spec = importlib.util.spec_from_file_location("import_official_docs", SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "static" / "snippets").mkdir(parents=True)
    (tmp_path / "static" / "snippets" / "info.html").write_text(
        '<span style="color:rgb(150,203,89)">HiZ></span>&nbsp;i\n<span>Bus&nbsp;Pirate&nbsp;6</span>')
    (tmp_path / "_common").mkdir()
    (tmp_path / "_common" / "more.md").write_text("Shared text.\n")
    return tmp_path


def convert(repo, text, path="content/docs/tutorial-basics/power-supply.md"):
    report = []
    markdown, title, weight = tool.convert_page(text, path, repo, report)
    return markdown, title, weight, report


def test_front_matter_becomes_a_title(repo):
    md, title, weight, _ = convert(repo, "+++\nweight = 30400\ntitle = 'Programmable Power Supply'\n+++\n\nBody.\n")
    assert md.startswith("# Programmable Power Supply\n")
    assert (title, weight) == ("Programmable Power Supply", 30400)


def test_alerts_become_callouts(repo):
    md, *_ = convert(repo, '{{% alert context="warning" %}}\nMind the volts.\n{{% /alert %}}\n')
    assert "> **Warning:**\n> Mind the volts." in md


def test_terminal_html_becomes_a_text_block(repo):
    md, *_ = convert(repo, '{{< term "Bus Pirate [/dev/ttyS0]" >}}\n<span style="color:#96cb59">I2C></span> W\n{{< /term >}}\n')
    assert "```text\nI2C> W\n```" in md


def test_termfile_is_inlined(repo):
    md, *_ = convert(repo, '{{< termfile source="static/snippets/info.html" >}}\n')
    assert "HiZ> i\nBus Pirate 6" in md


def test_readfile_is_inlined(repo):
    md, *_ = convert(repo, '{{% readfile "/_common/more.md" %}}\n')
    assert "Shared text." in md


def test_relref_becomes_an_in_app_link(repo):
    md, *_ = convert(repo, '[menu]({{< relref "/docs/command-reference/#c-configuration-options-menu" >}}) '
                           '[basics]({{< relref "/docs/tutorial-basics/" >}})')
    assert "[menu](official/command-reference.md#c-configuration-options-menu)" in md
    assert "[basics](official/tutorial-basics/index.md)" in md


def test_links_to_pages_left_out_go_to_the_website(repo):
    md, *_ = convert(repo, '[dl]({{< relref "/docs/downloads" >}})')
    assert "[dl](https://docs.buspirate.com/docs/downloads/)" in md


def test_tabs_become_headings(repo):
    md, *_ = convert(repo, '{{< tabs tabTotal="2" >}}\n{{% tab name="Linux" %}}\nA\n{{% /tab %}}\n{{< /tabs >}}\n')
    assert "#### Linux\nA" in md and "tab" not in md


def test_asciicast_becomes_a_link(repo):
    md, *_ = convert(repo, '{{< asciicast src="/screencast/x.json" >}}\n')
    assert "https://docs.buspirate.com/docs/tutorial-basics/power-supply/" in md


def test_images_are_rewritten(repo):
    md, *_ = convert(repo, "![](/images/docs/fw/psu.png)\n")
    assert "![](official/images/fw/psu.png)" in md


def test_unknown_shortcodes_are_reported(repo):
    md, _, _, report = convert(repo, '{{< mystery a="b" >}}\n')
    assert "mystery" not in md
    assert any("mystery" in line for line in report)


def test_slug_matches_hugo():
    assert tool.slug("`c` Configuration options menu") == "c-configuration-options-menu"
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_import_official_docs.py -q`
Expected: FAIL (`No such file or directory: scripts/import_official_docs.py`).

- [ ] **Step 3: Write the script**

```python
# scripts/import_official_docs.py
"""Import the official Bus Pirate 5/6 manual into docs/official/ as plain Markdown.

The manual (docs.buspirate.com) is a Hugo site in
DangerousPrototypes/BusPirate-docs-hugo, MIT-licensed. Its pages use Hugo
shortcodes the app's viewer cannot render, so they are converted here once,
and the result is committed. Re-run with a newer --ref to update.

    .venv/bin/python scripts/import_official_docs.py --ref <commit sha>
"""

from __future__ import annotations

import argparse
import html
import io
import json
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import List, Tuple

REPO = "DangerousPrototypes/BusPirate-docs-hugo"
SITE = "https://docs.buspirate.com"
KEEP_FILES = {"_index.md", "command-reference.md", "license.md"}
KEEP_DIRS = {"tutorial-basics", "devices", "overview", "logic-analyzer",
             "binmode-reference", "software", "cables"}
MAX_WIDTH = 1200
ALERT_KINDS = {"info": "Note", "warning": "Warning", "danger": "Danger", "success": "Tip"}

_FRONT = re.compile(r"\A\+\+\+\n(.*?)\n\+\+\+\n?", re.S)
_TITLE = re.compile(r"""^title\s*=\s*['"](.*)['"]\s*$""", re.M)
_WEIGHT = re.compile(r"^weight\s*=\s*(\d+)\s*$", re.M)
_ALERT = re.compile(r'\{\{%\s*alert\s+context="(\w+)"\s*%\}\}(.*?)\{\{%\s*/alert\s*%\}\}', re.S)
_TERM = re.compile(r"\{\{<\s*term\b[^>]*>\}\}(.*?)\{\{<\s*/term\s*>\}\}", re.S)
_TERMFILE = re.compile(r'\{\{<\s*termfile\s+source="([^"]+)"\s*>\}\}')
_READFILE = re.compile(r'\{\{%\s*readfile\s+"([^"]+)"\s*%\}\}')
_RELREF = re.compile(r'\{\{<\s*relref\s+"([^"]+)"\s*>\}\}')
_TAB = re.compile(r'\{\{[<%]\s*tab\s+(?:name=)?"([^"]+)"\s*[>%]\}\}')
_TABS_OR_END = re.compile(r"\{\{[<%]\s*/?tabs\b[^}]*[>%]\}\}|\{\{[<%]\s*/tab\s*[>%]\}\}")
_ASCIICAST = re.compile(r"\{\{<\s*asciicast\b[^}]*>\}\}")
_BTN = re.compile(r'\{\{<\s*btn\b[^}]*href="([^"]+)"[^}]*>\}\}(.*?)\{\{<\s*/btn\s*>\}\}', re.S)
_ANY = re.compile(r"\{\{[<%]\s*(/?[\w-]+)[^}]*[>%]\}\}")
_IMAGE = re.compile(r"(!\[[^\]]*\]\()/images/docs/([^)\s]+)\)")


def slug(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text.lower())
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return re.sub(r"\s", "-", text.strip())


def _plain(markup: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", markup)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    return "\n".join(line.rstrip() for line in text.strip("\n").splitlines())


def _relref(target: str) -> str:
    path, _, anchor = target.partition("#")
    path = path.strip("/")
    if path.startswith("docs/"):
        path = path[len("docs/"):]
    path = path.strip("/")
    suffix = f"#{anchor}" if anchor else ""
    first = path.split("/")[0] if path else ""
    if path and first not in KEEP_DIRS and f"{path}.md" not in KEEP_FILES:
        # A page that is not bundled (hardware, downloads, ...): the website.
        return f"{SITE}/docs/{path}/{suffix}"
    if not path:
        name = "official/index"
    elif path in KEEP_DIRS:
        name = f"official/{path}/index"
    else:
        name = f"official/{path}"
    return f"{name}.md{suffix}"


def convert_page(text: str, page_path: str, repo: Path, report: List[str]) -> Tuple[str, str, int]:
    title, weight = Path(page_path).stem, 0
    front = _FRONT.match(text)
    if front:
        found = _TITLE.search(front.group(1))
        title = found.group(1) if found else title
        found = _WEIGHT.search(front.group(1))
        weight = int(found.group(1)) if found else 0
        text = text[front.end():]

    def readfile(match):
        path = repo / match.group(1).lstrip("/")
        if not path.is_file():
            report.append(f"{page_path}: readfile {match.group(1)} not found")
            return ""
        inner = _FRONT.sub("", path.read_text(encoding="utf-8"))
        return convert_page(inner, page_path, repo, report)[0].split("\n", 2)[-1]

    def alert(match):
        kind = ALERT_KINDS.get(match.group(1), "Note")
        lines = match.group(2).strip("\n").splitlines()
        return "\n".join([f"> **{kind}:**"] + [f"> {line}".rstrip() for line in lines])

    def termfile(match):
        path = repo / match.group(1)
        if not path.is_file():
            report.append(f"{page_path}: termfile {match.group(1)} not found")
            return ""
        return "```text\n" + _plain(path.read_text(encoding="utf-8")) + "\n```"

    page_url = page_path.replace("content/", "").removesuffix(".md").removesuffix("/_index") + "/"
    text = _READFILE.sub(readfile, text)
    text = _ALERT.sub(alert, text)
    text = _TERM.sub(lambda m: "```text\n" + _plain(m.group(1)) + "\n```", text)
    text = _TERMFILE.sub(termfile, text)
    text = _RELREF.sub(lambda m: _relref(m.group(1)), text)
    text = _TAB.sub(lambda m: f"#### {m.group(1)}", text)
    text = _TABS_OR_END.sub("", text)
    text = _ASCIICAST.sub(f"[▶ Watch this as a recording on docs.buspirate.com]({SITE}/{page_url})", text)
    text = _BTN.sub(lambda m: f"[{m.group(2).strip()}]({m.group(1)})", text)

    def unknown(match):
        report.append(f"{page_path}: dropped shortcode {match.group(1)}")
        return ""

    text = _ANY.sub(unknown, text)
    text = _IMAGE.sub(lambda m: f"{m.group(1)}official/images/{m.group(2)})", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
    return f"# {title}\n\n{text}\n", title, weight


def _fetch(ref: str, into: Path) -> Path:
    url = f"https://codeload.github.com/{REPO}/tar.gz/{ref}"
    with urllib.request.urlopen(url) as response:  # noqa: S310 - fixed https URL
        data = response.read()
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        try:
            archive.extractall(into, filter="data")
        except TypeError:  # Python < 3.12 without the filter argument
            archive.extractall(into)
    return next(into.iterdir())


def _copy_image(source: Path, target: Path, report: List[str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        from PIL import Image
    except ImportError:
        report.append("Pillow missing: images copied at full size")
        shutil.copyfile(source, target)
        return
    if source.suffix.lower() in {".svg", ".gif"}:
        shutil.copyfile(source, target)
        return
    with Image.open(source) as image:
        if image.width > MAX_WIDTH:
            image = image.resize((MAX_WIDTH, round(image.height * MAX_WIDTH / image.width)))
        image.save(target, optimize=True, **({"quality": 85} if target.suffix.lower() in {".jpg", ".jpeg"} else {}))


def _kept(rel: Path) -> bool:
    if len(rel.parts) == 1:
        return rel.name in KEEP_FILES
    return rel.parts[0] in KEEP_DIRS


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ref", required=True, help="commit SHA of BusPirate-docs-hugo")
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "official"))
    args = parser.parse_args(argv)
    out = Path(args.out)
    report: List[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        repo = _fetch(args.ref, Path(tmp))
        content = repo / "content" / "docs"
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        pages = []
        for source in sorted(content.rglob("*.md")):
            rel = source.relative_to(content)
            if not _kept(rel):
                continue
            markdown, title, weight = convert_page(
                source.read_text(encoding="utf-8"), f"content/docs/{rel.as_posix()}", repo, report)
            name = rel.with_name("index.md") if rel.name == "_index.md" else rel
            target = out / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(markdown, encoding="utf-8")
            for image in re.findall(r"\]\(official/images/([^)\s]+)\)", markdown):
                found = repo / "assets" / "images" / "docs" / image
                if found.is_file():
                    if not (out / "images" / image).exists():
                        _copy_image(found, out / "images" / image, report)
                else:
                    report.append(f"{rel}: image {image} not found")
            section = name.parts[0] if len(name.parts) > 1 else ""
            is_index = name.name == "index.md"
            pages.append(((section, 0 if is_index else 1, weight, str(name)),
                          "official/" + name.with_suffix("").as_posix()))
        pages.sort()
        top = [p for p in pages if p[0][0] == ""]
        rest = [p for p in pages if p[0][0] != ""]
        (out / "order.json").write_text(json.dumps([n for _, n in top + rest], indent=1) + "\n")
        shutil.copyfile(repo / "LICENSE", out / "LICENSE")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    (out / "SOURCE.md").write_text(
        "# Source of the official manual\n\n"
        f"Converted from <https://github.com/{REPO}> at commit `{args.ref}` by "
        "`scripts/import_official_docs.py`. MIT licence: see `LICENSE` in this folder.\n\n"
        "Do not edit these files by hand; re-run the script with a newer `--ref`.\n",
        encoding="utf-8")
    print(f"{len(pages)} pages, {size / 1e6:.1f} MB in {out}")
    for line in report:
        print("  " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note on Python 3.8: `str.removesuffix` needs 3.9. The script is dev-only and the venv is 3.11, so that is fine; say "needs Python 3.9+" in its docstring.

Add `"Pillow>=10"` to the `dev` list in `pyproject.toml`'s `[project.optional-dependencies]`, then `.venv/bin/pip install -q -e ".[dev,web]"`.

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_import_official_docs.py -q`
Expected: all PASS.

- [ ] **Step 5: Run the import for real**

Run: `.venv/bin/python scripts/import_official_docs.py --ref efa4e5e3ec04561f581cc3771f36559b6031d191`
Expected: a line like `70 pages, N MB in …/docs/official`, followed by the report.

Then:
- `du -sh docs/official` — **if over 25 MB, stop and ask the owner** before committing (options: drop `devices/` images, lower `MAX_WIDTH` to 900).
- Read the report. For each "dropped shortcode" kind that appears more than a handful of times, add a rule + test in Steps 1–3 and re-run.
- `grep -rn "{{" docs/official | head` — expect nothing.
- `make demo`, open the Guide, pick "Programmable Power Supply" and "Command reference", check images, callouts, terminal blocks, and that a link into `command-reference.md#…` lands on its section.

- [ ] **Step 6: Commit**

```bash
git add scripts/import_official_docs.py tests/test_import_official_docs.py pyproject.toml docs/official
git commit -m "Bundle the official Bus Pirate 5/6 manual, converted from its Hugo source at efa4e5e"
```

---

### Task 13: Our own Bus Pirate 6 guides

**Files:**
- Create: `docs/bus-pirate-6.md`
- Modify: `docs/i2c.md`, `docs/spi.md`, `docs/uart.md`, `docs/onewire.md`, `docs/pins-and-power.md`, `docs/cli.md`, `docs/user-guide.md`, `docs/troubleshooting.md`, `docs/dashboard.md` (the board list), `README.md` (supported boards)
- Test: `tests/test_dashboard.py` (guide checks)

**Interfaces:**
- Consumes: the facts in the spec and Global Constraints; manual pages under `official/…` for links.

- [ ] **Step 1: Write the failing tests (append to `tests/test_dashboard.py`)**

```python
def test_the_bp6_guide_covers_setup_power_and_firmware(client):
    text = client.get("/api/docs/bus-pirate-6").json()["markdown"]
    for must in ("BPIO2", "usbmodem6buspirate1", "usbmodem6buspirate3", "$", "RP2350",
                 "bus_pirate6.uf2", "current limit", "10 kΩ", "Raw-wire", "official/"):
        assert must in text, must


def test_each_bus_guide_has_a_bp6_section(client):
    for name in ("i2c", "spi", "uart", "onewire", "pins-and-power", "cli", "user-guide"):
        text = client.get(f"/api/docs/{name}").json()["markdown"]
        assert "## Bus Pirate 6" in text, name
        assert "official/" in text, name


def test_troubleshooting_has_the_bp6_checklist(client):
    text = client.get("/api/docs/troubleshooting").json()["markdown"]
    assert "## Bus Pirate 6" in text
    assert "- [ ]" in text.split("## Bus Pirate 6", 1)[1]


def test_every_official_link_in_our_guides_resolves(client):
    import re
    from buspirate.web import docs
    for page in docs.available():
        if page["group"] != docs.APP_GROUP:
            continue
        for target in re.findall(r"\]\((official/[^)#]+)\.md", docs.read(page["name"])):
            assert docs.read(target) is not None, (page["name"], target)
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -q -k "bp6 or official_link"`
Expected: FAIL (no `bus-pirate-6` page).

- [ ] **Step 3: Write `docs/bus-pirate-6.md`**

Follow the voice and structure of `docs/bus-pirate-v4.md` and `docs/bitpirate.md` (plain sentences, short sections, tables for pins). Required sections and content:

1. `# Bus Pirate 6` — one paragraph: what it is (RP2350B, programmable supply, buffered IO 1.2–5 V), and that the app drives it over **BPIO2**, its binary interface.
2. `## What you need` — firmware built **2026-10-12 or later** (BPIO2 with UART); the USB-C lead; nothing else (no driver on macOS).
3. `## The two ports` — table: `/dev/cu.usbmodem6buspirate1` terminal (`HiZ>`), `/dev/cu.usbmodem6buspirate3` BPIO2; the app shows one entry and uses both; only one program can hold a port (quit `screen` first).
4. `## Connecting` — one click; if BPIO2 is off (after every replug), the app switches it on in the terminal (`binmode` → 2 → *don't save*) and nothing is saved on the board.
5. `## Updating the firmware` — numbered steps: type `$` in the terminal; a disk named `RP2350` appears; copy `bus_pirate6.uf2` onto it; the board restarts. Where builds come from: the forum's auto-build thread (`https://forum.buspirate.com/t/bus-pirate-5-auto-build-main-branch/20`) or the firmware repo's CI artifacts (`firmware-rp2350-…`, file `bus_pirate6.uf2`). Link: [the official firmware update page](official/tutorial-basics/firmware-update.md).
6. `## Power and the current limit` — VOUT 0.8–5.0 V, limit 0–500 mA (0 = none, 300 default); the quick buttons; the tick above 3.6 V or with no limit; what a trip looks like and Re-enable; the status bar readout. Link: [Programmable power supply](official/tutorial-basics/power-supply.md).
7. `## Pull-ups` — onboard 10 kΩ to VOUT on every IO pin; need the supply (or external VOUT). Link: [Pull-up resistors](official/tutorial-basics/pullup-resistors.md).
8. `## Pins` — table of the pin map from Global Constraints (I2C, SPI, UART, 1-Wire).
9. `## What the dashboard does not do on the BP6, and why` — Raw-wire (2-wire/3-wire), DIO, IR, JTAG, PS/2, USB, LEDs, logic analyzer: not in BPIO2 or not in the dashboard — use the Terminal panel; UART odd parity and 9 bits; 1-Wire finds one device (several → `scan` in the terminal); I2C errors are per transaction, not per byte.
10. `## The Terminal panel` — opens the terminal port, nothing reset; only `\r` is Enter; if asked "VT100 compatible color mode?", answer `n`; after closing it the dashboard re-reads the board. Link: [Command reference](official/command-reference.md).
11. `## Troubleshooting` — three short entries: "Connect fails: not answering on BPIO2" (replug; check firmware date with `i`; quit `screen`); "The supply switches itself off" (current limit tripped); "Nothing on I2C" (pull-ups, VOUT, SDA/SCL on IO0/IO1).

- [ ] **Step 4: Add the `## Bus Pirate 6` sections**

Each existing guide gets a `## Bus Pirate 6` section near its end, 3–8 lines, with the BP6 pins for that bus, the one or two BP6 differences, and one link into the manual:
- `i2c.md`: SDA IO0 / SCL IO1; pull-ups via Power & pull-ups; NACKs are per transaction. Link `official/command-reference.md#i2c` (check the real anchor in the imported page: `grep -n "^## .*I2C" docs/official/command-reference.md`, then use `slug()` of that heading).
- `spi.md`: CLK IO6 / MOSI IO7 / MISO IO4 / CS IO5; any SPI mode; long reads split with CS held. Link the manual's SPI section and `official/devices/spi-flash-chips.md`.
- `uart.md`: TX IO4 / RX IO5; 8N1 or 8E1; the monitor shows what the target sends. Link the manual's UART section.
- `onewire.md`: data IO0, pull-ups on; finds one device. Link `official/devices/ds18b20.md`.
- `pins-and-power.md`: points to the Power & pull-ups panel and `bus-pirate-6.md`. Link `official/tutorial-basics/power-supply.md`.
- `cli.md`: `buspirate ping`, `i2c-scan`, `spi-id` work on the BP6; `--demo bp6`. Link `official/command-reference.md`.
- `user-guide.md`: the BP6 in the list of supported boards; link `bus-pirate-6.md` and `official/index.md`.

`troubleshooting.md`: a `## Bus Pirate 6` section with the real-board checklist (as `- [ ]` items): connect after a fresh replug (BPIO2 switched on); status shows `Bus Pirate 6, firmware 2026-10-12`; 3.3 V on with a current reading; a deliberate trip with a 1 mA limit and a load, then Re-enable; pull-ups on (IO readings rise); I2C scan with a real chip; SPI flash JEDEC ID; UART loopback (IO4↔IO5) shows what was sent; 1-Wire with a DS18B20; Terminal panel opens, `i` works, closing re-reads the board; `buspirate ping` from the CLI.

`dashboard.md` and `README.md`: add the Bus Pirate 6 wherever the supported boards are listed.

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_dashboard.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/*.md README.md tests/test_dashboard.py
git commit -m "Write the Bus Pirate 6 guide and add BP6 sections to every bus guide, linked into the manual"
```

---

### Task 14: On the real board

**Files:**
- Modify: whatever the checklist shows to be wrong (driver, simulator, docs), plus `docs/troubleshooting.md` (tick the checklist with the date), `buspirate/__init__.py` (`__version__ = "0.6.0"`)

This task runs against the owner's BP6 (plugged in, firmware built 2026-10-12). **Ask the owner before each step that needs wiring** (a chip on I2C, a flash on SPI, a loopback lead, a DS18B20); skip any they do not have and say so in the summary.

- [ ] **Step 1:** `ls /dev/cu.usbmodem*` and `.venv/bin/python -m buspirate ports` — one "Bus Pirate 5/6" entry, BPIO2 partner shown.
- [ ] **Step 2:** Ask the owner to unplug and replug the BP6 (so BPIO2 is off), then `.venv/bin/python -m buspirate ping` — expect `Bus Pirate 6, firmware 2026-10-12` and `protocol BPIO2`.
- [ ] **Step 3:** `make dash`, connect, and walk the `troubleshooting.md` BP6 checklist with the owner. For each failure, write a failing test against `FakeBp6` that reproduces what the real board did, fix the driver (and the simulator, if the simulator was wrong), and re-run `pytest -q`.
- [ ] **Step 4:** Tick the checklist items that passed, with the date (`2026-10-…`), and note any skipped.
- [ ] **Step 5:** Bump `__version__` to `0.6.0`; run the whole suite and the UI test:

```bash
.venv/bin/python -m pytest -q
make ui-test
```

Expected: everything passes.

- [ ] **Step 6: Commit**

```bash
git add -A buspirate docs tests
git commit -m "Check the Bus Pirate 6 support on the real board, and version 0.6.0"
```

---

## Self-review notes

- Spec §1 (detection, pairing, one-click connect, package, terminal, workarounds) → Tasks 1–8. §2 (power panel, readout, pull-ups, pins, board, status bar, gating) → Tasks 4, 8, 9. §3a (import) → Task 12; §3b (viewer) → Tasks 10–11; §3c (our guides) → Task 13. §4 (testing) → every task + Task 14. Risks: BPIO version check → Task 5 test; size → Task 12 Step 5; two boards → Task 7 test.
- Deviations from the spec are listed at the top and must be reported to the owner.
