import pytest

from buspirate.mcp.confirm import ConfirmError, ConfirmStore


def test_redeem_once():
    s = ConfirmStore(); t = s.issue("power", {"mv": 3300})
    assert s.redeem(t, "power") == {"mv": 3300}
    with pytest.raises(ConfirmError):
        s.redeem(t, "power")


def test_wrong_action_consumes():
    s = ConfirmStore(); t = s.issue("power", 1)
    with pytest.raises(ConfirmError):
        s.redeem(t, "erase")
    with pytest.raises(ConfirmError):
        s.redeem(t, "power")


def test_expiry():
    now = [0.0]; s = ConfirmStore(ttl=300, clock=lambda: now[0]); t = s.issue("power", 1)
    now[0] = 301
    with pytest.raises(ConfirmError, match="expired"):
        s.redeem(t, "power")


def test_unknown_token():
    with pytest.raises(ConfirmError, match="unknown"):
        ConfirmStore().redeem("nope", "power")


def test_valid_just_inside_ttl():
    now = [0.0]; s = ConfirmStore(ttl=300, clock=lambda: now[0]); t = s.issue("power", 7)
    now[0] = 300
    assert s.redeem(t, "power") == 7


def test_tokens_unique():
    s = ConfirmStore()
    assert s.issue("a", 1) != s.issue("a", 1)
