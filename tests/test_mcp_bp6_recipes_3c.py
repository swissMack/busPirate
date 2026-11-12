"""The phase 3c recipes (smart card, USB-PD, disk) on the simulated Bus Pirate 6."""

import pytest

from buspirate.mcp.confirm import ConfirmStore
from buspirate.mcp.session import BoardSession
from buspirate.mcp_bp6 import engine
from buspirate.mcp_bp6.recipes import REGISTRY


@pytest.fixture
def session():
    s = BoardSession(simulated="bp6")
    s.connect()
    yield s
    s.disconnect()


@pytest.fixture
def confirm():
    return ConfirmStore()


def _fake(session):
    return session.board.serial.owner


def _plan(session, confirm, name, options):
    return engine.plan_recipe(session, confirm, name, options)


def _run(session, confirm, name, options):
    plan = _plan(session, confirm, name, options)
    assert "error" not in plan, plan
    return plan, engine.run_recipe(session, confirm, plan["token"], {})


def test_smartcard_recipe_registered():
    r = REGISTRY["smartcard-atr"]
    assert (r.bus, r.transport, r.terminal_mode) == ("uart", "terminal", "hduart")
    assert r.terminal_flags == "-b 9600 -d 8 -p even -s 2 -l listen"
    assert (r.default_mv, r.min_mv, r.max_mv, r.milliamps) == (3000, 1800, 5000, 100)
    assert r.pullups is True and r.target_powered_ok is False and r.risk == "none"
    assert r.options == {"clock_hz": 3_571_200, "wait_s": 1.0}
    assert ("C3 CLK", "IO1") in r.wiring and ("C7 I/O", "IO0") in r.wiring


def test_smartcard_atr_runs(session, confirm):
    fake = _fake(session)
    fake.card_atr = bytes.fromhex("3B9F96801FC78031E073FE211B6407689A00820190")
    _, out = _run(session, confirm, "smartcard-atr", {"millivolts": 3000, "wait_s": 0.3})
    assert out["result"]["atr"]["convention"] == "direct", out
    assert b"m hduart -b 9600 -d 8 -p even -s 2 -l listen\r" in fake.lines_received()
    assert fake.pwm == {}


@pytest.mark.parametrize("clock_hz", [3_000_000, 900_000, 5_500_000, "3571200", True])
def test_smartcard_atr_refuses_bad_clock(session, confirm, clock_hz):
    _, out = _run(session, confirm, "smartcard-atr",
                  {"millivolts": 3000, "clock_hz": clock_hz, "wait_s": 0.3})
    assert out["check"]["ok"] is False and "clock_hz" in out["check"]["error"], out
    assert b"G 1\r" not in _fake(session).lines_received()


# -- USB-PD plank -------------------------------------------------------------

PDOS = [{"type": "Fixed", "mv": 5000, "ma": 3000},
        {"type": "Fixed", "mv": 9000, "ma": 3000},
        {"type": "PPS", "min": ">=3300 mV", "mv": 21000, "ma": 3000}]


@pytest.fixture
def plank(session):
    fake = _fake(session)
    fake.usbpd_pdos = [dict(p) for p in PDOS]
    return fake


def _requests(fake):
    return [ln for ln in fake.lines_received() if ln.startswith(b"usbpd request")]


@pytest.mark.parametrize("name", ["usbpd-status", "usbpd-request", "usbpd-reset"])
def test_usbpd_recipes_registered(name):
    from buspirate.mcp_bp6.recipes.i2c import I2C_WIRING
    r = REGISTRY[name]
    assert (r.bus, r.transport, r.terminal_mode, r.terminal_flags) == (
        "i2c", "terminal", "i2c", "-s 400")
    assert (r.default_mv, r.min_mv, r.max_mv, r.milliamps) == (3300, 3000, 3600, 100)
    assert r.pullups is True and r.wiring == I2C_WIRING
    assert r.source == "https://docs.buspirate.com/docs/overview/usbpd-adapter/"
    assert any("28 V" in n and "hiz" in n for n in r.notes)
    assert r.risk == ("destructive" if name == "usbpd-request" else "none")


def test_usbpd_request_options_and_change_note(session, confirm, plank):
    assert REGISTRY["usbpd-request"].options == {"pdo": None, "pd_mv": None, "pd_ma": None}
    plan = _plan(session, confirm, "usbpd-request", {"pdo": 2})
    assert engine.CHANGE_NOTE in plan["warnings"]


def test_usbpd_status_runs(session, confirm, plank):
    _, out = _run(session, confirm, "usbpd-status", {})
    assert len(out["result"]["pdos"]) == 3, out
    assert out["result"]["source"] == "PD source connected"
    assert b"m i2c -s 400\r" in plank.lines_received()


def test_usbpd_status_no_source(session, confirm, plank):
    plank.usbpd_pdos = []
    _, out = _run(session, confirm, "usbpd-status", {})
    assert out["check"]["ok"] is False and "No source" in out["check"]["error"], out
    assert "USB-C" in out["hint"] and "plank" in out["hint"]


def test_usbpd_request_fixed(session, confirm, plank):
    _, out = _run(session, confirm, "usbpd-request", {"pdo": 2})
    summary = out["commit"]["summary"]
    assert "9000 mV" in summary and "3000 mA" in summary and "PDO 2" in summary, out
    assert out["commit"]["chip"] == "USB-PD source" and out["commit"]["operation"] == "request"
    assert out["commit"]["start"] == 2 and out["commit"]["length"] == 0
    assert out["commit"]["backup"] is None
    assert _requests(plank) == []
    mark = len(plank.lines_received())
    done = engine.commit_recipe(session, confirm, out["commit"]["token"])
    assert done["committed"] is True and done["result"]["vbus_mv"] == 9000, done
    assert done["result"]["verified"] is True
    assert _requests(plank) == [b"usbpd request -p 2 -i 3000\r"]
    # The commit never touches the supply, the pull-ups or the mode.
    sent = [ln.split()[0] for ln in plank.lines_received()[mark:] if ln.strip()]
    assert not set(sent) & {b"W", b"w", b"P", b"p", b"m"}, sent


def test_usbpd_request_pps(session, confirm, plank):
    _, out = _run(session, confirm, "usbpd-request", {"pdo": 3, "pd_mv": 12000})
    assert "12000 mV" in out["commit"]["summary"], out
    done = engine.commit_recipe(session, confirm, out["commit"]["token"])
    assert done["committed"] is True, done
    assert _requests(plank) == [b"usbpd request -p 3 -v 12000 -i 3000\r"]


@pytest.mark.parametrize("options,word", [
    ({"pdo": 3}, "pd_mv"), ({"pdo": 3, "pd_mv": 22000}, "pd_mv"),
    ({"pdo": 2, "pd_ma": 4000}, "pd_ma"), ({"pdo": None}, "pdo"), ({"pdo": True}, "pdo")])
def test_usbpd_request_bad_options(session, confirm, plank, options, word):
    _, out = _run(session, confirm, "usbpd-request", options)
    assert out["check"]["ok"] is False and word in out["check"]["error"], out
    assert "commit" not in out


def test_usbpd_request_unknown_pdo_names_offers(session, confirm, plank):
    _, out = _run(session, confirm, "usbpd-request", {"pdo": 9})
    err = out["check"]["error"]
    assert out["check"]["ok"] is False and "commit" not in out, out
    assert "5000 mV" in err and "9000 mV" in err and "21000 mV" in err, err


def test_usbpd_request_refused_when_offers_change(session, confirm, plank):
    _, out = _run(session, confirm, "usbpd-request", {"pdo": 2})
    plank.usbpd_pdos[1] = {"type": "Fixed", "mv": 12000, "ma": 3000}
    done = engine.commit_recipe(session, confirm, out["commit"]["token"])
    assert done["error"].startswith("plan again"), done
    assert _requests(plank) == []


def test_usbpd_request_rejected(session, confirm, plank):
    plank.usbpd_result = "rejected"
    _, out = _run(session, confirm, "usbpd-request", {"pdo": 2})
    done = engine.commit_recipe(session, confirm, out["commit"]["token"])
    assert done["committed"] is False and done["result"]["accepted"] is False, done


def test_usbpd_reset_runs(session, confirm, plank):
    _, out = _run(session, confirm, "usbpd-reset", {})
    assert out["result"]["sent"] is True, out
    assert b"usbpd reset\r" in plank.lines_received()


# -- the Bus Pirate's disk ----------------------------------------------------

DISK = {"bpconfig.bp": b'{"a":1}\n', "dumps/flash.bin": bytes(range(40))}
DISK_RECIPES = ["disk-list", "disk-show", "disk-hex", "disk-delete"]


@pytest.fixture
def drive(session):
    fake = _fake(session)
    fake.disk = dict(DISK)
    return fake


def _no_power_lines(lines, mode=True):
    """No supply or pull-up line; with ``mode``, no mode switch either."""
    sent = [ln.split()[0] for ln in lines if ln.strip()]
    banned = {b"W", b"w", b"P", b"p"} | ({b"m"} if mode else set())
    assert not set(sent) & banned, sent


@pytest.mark.parametrize("name", DISK_RECIPES)
def test_disk_recipes_registered(name):
    r = REGISTRY[name]
    assert (r.bus, r.transport, r.terminal_mode, r.terminal_flags) == (
        "board", "terminal", None, "")
    assert (r.default_mv, r.min_mv, r.max_mv, r.milliamps) == (0, 0, 0, 0)
    assert r.pullups is False and r.wiring == ()
    assert r.source == "https://docs.buspirate.com/docs/command-reference/"
    assert any("read-only" in n for n in r.notes)
    assert r.risk == ("destructive" if name == "disk-delete" else "none")


def test_disk_recipe_options():
    assert REGISTRY["disk-list"].options == {"path": "/"}
    assert REGISTRY["disk-show"].options == {"path": None, "max_chars": 16384}
    assert REGISTRY["disk-hex"].options == {"path": None, "start": 0, "length": 256}
    assert REGISTRY["disk-delete"].options == {"path": None}
    assert any("disk-hex" in n for n in REGISTRY["disk-show"].notes)
    assert any("%" in n for n in REGISTRY["disk-show"].notes)


@pytest.mark.parametrize("query", ["disk", "files", "delete file"])
def test_disk_recipes_found(query):
    from buspirate.mcp_bp6.recipes import find_recipes
    found = {r["name"] for r in find_recipes(query)}
    want = {"disk-delete"} if query == "delete file" else set(DISK_RECIPES)
    assert want <= found, found


def test_disk_list_runs(session, confirm, drive):
    plan, out = _run(session, confirm, "disk-list", {})
    assert plan["power"] is None and plan["wiring"] == [], plan
    assert out["result"]["dirs"] == ["dumps"], out
    assert out["result"]["files"] == [
        {"name": "bpconfig.bp", "size": 8, "date": "2020-01-01 00:00"}]
    assert b"ls -l /\r" in drive.lines_received() and b"m hiz\r" in drive.lines_received()
    _no_power_lines(drive.lines_received(), mode=False)


def test_disk_list_missing_dir(session, confirm, drive):
    _, out = _run(session, confirm, "disk-list", {"path": "nothere"})
    assert out["check"]["ok"] is False and "no such directory" in out["check"]["error"], out


def test_disk_show_and_hex_run(session, confirm, drive):
    _, out = _run(session, confirm, "disk-show", {"path": "bpconfig.bp"})
    assert out["result"] == {"text": '{"a":1}', "truncated": False}, out
    _, out = _run(session, confirm, "disk-hex", {"path": "dumps/flash.bin", "start": 16,
                                                 "length": 16})
    assert out["result"]["data_hex"] == bytes(range(16, 32)).hex(), out
    _no_power_lines(drive.lines_received(), mode=False)


@pytest.mark.parametrize("name,options,word", [
    ("disk-show", {"path": None}, "path"), ("disk-show", {"path": "a b.txt"}, "path"),
    ("disk-show", {"path": "gone.txt"}, "no file"),
    ("disk-show", {"path": "dumps"}, "directory"),
    ("disk-show", {"path": "bpconfig.bp", "max_chars": 0}, "max_chars"),
    ("disk-show", {"path": "dumps/flash.bin", "max_chars": 39}, "disk-hex"),
    ("disk-hex", {"path": "dumps/flash.bin", "length": 5000}, "length"),
    ("disk-hex", {"path": "dumps/flash.bin", "start": -1}, "start"),
    ("disk-list", {"path": "x;rm y"}, "path")])
def test_disk_read_recipes_refuse(session, confirm, drive, name, options, word):
    _, out = _run(session, confirm, name, options)
    assert out["check"]["ok"] is False and word in out["check"]["error"], out
    assert not [ln for ln in drive.lines_received()
                if ln.split()[:1] in ([b"cat"], [b"hex"], [b"rm"])]


def test_disk_delete(session, confirm, drive):
    plan, out = _run(session, confirm, "disk-delete", {"path": "bpconfig.bp"})
    assert engine.CHANGE_NOTE in plan["warnings"]
    commit = out["commit"]
    assert "/bpconfig.bp" in commit["summary"] and "8 bytes" in commit["summary"], out
    assert commit["summary"].startswith("Delete /bpconfig.bp (8 bytes) from the Bus Pirate's")
    assert (commit["chip"], commit["operation"], commit["start"], commit["length"],
            commit["backup"]) == ("Bus Pirate disk", "delete", 0, 8, None)
    assert "bpconfig.bp" in drive.disk
    assert not [ln for ln in drive.lines_received() if ln.startswith(b"rm")]
    mark = len(drive.lines_received())
    done = engine.commit_recipe(session, confirm, commit["token"])
    assert done["committed"] is True and done["result"]["deleted"] is True, done
    assert "bpconfig.bp" not in drive.disk
    assert b"rm /bpconfig.bp\r" in drive.lines_received()[mark:]
    _no_power_lines(drive.lines_received()[mark:])


def test_disk_delete_refused_when_file_changes(session, confirm, drive):
    _, out = _run(session, confirm, "disk-delete", {"path": "bpconfig.bp"})
    drive.disk["bpconfig.bp"] = b'{"a":12}\n'
    done = engine.commit_recipe(session, confirm, out["commit"]["token"])
    assert done["error"].startswith("plan again"), done
    assert "bpconfig.bp" in drive.disk


@pytest.mark.parametrize("path,word", [("dumps", "directory"), ("gone.txt", "no file"),
                                       ("dumps/", "path"), ("nothere/a.txt", "no such")])
def test_disk_delete_refuses(session, confirm, drive, path, word):
    _, out = _run(session, confirm, "disk-delete", {"path": path})
    assert out["check"]["ok"] is False and word in out["check"]["error"], out
    assert "commit" not in out
    assert not [ln for ln in drive.lines_received() if ln.startswith(b"rm")]
