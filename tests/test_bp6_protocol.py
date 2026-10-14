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
