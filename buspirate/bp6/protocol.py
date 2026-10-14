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
