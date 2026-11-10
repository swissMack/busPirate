"""`buspirate mcp`: parsing, and the message when the SDK is not there."""

import sys

from buspirate.cli import build_parser, main


def test_mcp_subcommand_parses():
    args = build_parser().parse_args(["mcp", "--demo", "--variant", "bp6"])
    assert args.demo and args.variant == "bp6"


def test_mcp_defaults_to_a_real_board():
    args = build_parser().parse_args(["mcp"])
    assert not args.demo


def test_mcp_without_sdk_explains(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "buspirate.mcp.server", None)
    assert main(["mcp", "--demo"]) == 2
    assert "buspirate[mcp]" in capsys.readouterr().err


def test_mcp_on_old_python_explains(monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", (3, 9, 0))
    assert main(["mcp", "--demo"]) == 2
    assert "Python 3.10+" in capsys.readouterr().err


def test_mcp_demo_passes_the_variant_to_the_server(monkeypatch):
    import pytest
    server = pytest.importorskip("buspirate.mcp.server")
    seen = []
    monkeypatch.setattr(server, "run_stdio", lambda simulated=None: seen.append(simulated))
    assert main(["mcp", "--demo", "--variant", "v4"]) == 0
    assert main(["mcp"]) == 0
    assert seen == ["v4", None]


def test_mcp_bp6_subcommand_parses(capsys):
    import pytest
    assert build_parser().parse_args(["mcp-bp6", "--demo"]).demo
    assert not build_parser().parse_args(["mcp-bp6"]).demo
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["mcp-bp6", "--help"])
    assert exc.value.code == 0
    assert "--demo" in capsys.readouterr().out


def test_mcp_bp6_on_old_python_explains(monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", (3, 9, 0))
    assert main(["mcp-bp6", "--demo"]) == 2
    assert "Python 3.10+" in capsys.readouterr().err


def test_mcp_bp6_without_sdk_explains(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "buspirate.mcp_bp6.server", None)
    assert main(["mcp-bp6", "--demo"]) == 2
    assert "buspirate[mcp]" in capsys.readouterr().err


def test_mcp_bp6_passes_demo_to_the_server(monkeypatch):
    import pytest
    server = pytest.importorskip("buspirate.mcp_bp6.server")
    seen = []
    monkeypatch.setattr(server, "run_stdio", lambda demo=False: seen.append(demo))
    assert main(["mcp-bp6", "--demo"]) == 0
    assert main(["mcp-bp6"]) == 0
    assert seen == [True, False]
