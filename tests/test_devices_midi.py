"""MIDI stream decoding."""

from buspirate.devices import midi


def test_note_names():
    assert midi.note_name(60) == "C4"
    assert midi.note_name(61) == "C#4"
    assert midi.note_name(21) == "A0"


def test_parse_note_on_off_running_status():
    out = midi.parse(bytes.fromhex("903C643E643C00"))
    kinds = [(m["type"], m["note"]) for m in out["messages"]]
    assert kinds == [("note on", "C4"), ("note on", "D4"), ("note off", "C4")]
    assert out["messages"][0]["channel"] == 1 and out["messages"][0]["velocity"] == 100


def test_parse_realtime_inside_message():
    out = midi.parse(bytes.fromhex("90F83C64"))
    assert [m["type"] for m in out["messages"]] == ["note on"]
    assert out["clock_ticks"] == 1


def test_parse_cc_program_bend():
    out = midi.parse(bytes.fromhex("B10764C105E10040"))
    cc, prog, bend = out["messages"]
    assert (cc["type"], cc["channel"], cc["controller"], cc["value"]) == ("control change", 2, 7, 100)
    assert (prog["type"], prog["program"]) == ("program change", 5)
    assert (bend["type"], bend["value"]) == ("pitch bend", 0)


def test_parse_sysex_and_incomplete_tail():
    out = midi.parse(bytes.fromhex("F0 7E 7F 06 01 F7 FE 90 3C".replace(" ", "")))
    assert out["messages"] == [{"type": "sysex", "channel": None, "length": 4}]
    assert out["active_sensing"] == 1
