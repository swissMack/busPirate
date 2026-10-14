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


# -- forms found in the real manual (efa4e5e) ----------------------------------


def test_percent_delimited_relref_and_localhost_links(repo):
    md, _, _, report = convert(repo, '[a]({{% relref "/docs/logic-analyzer/pulseview-sump/" %}}) '
                                     '[b]({{% relref "http://localhost:1313/docs/software/flashrom/"%}})')
    assert "[a](official/logic-analyzer/pulseview-sump.md)" in md
    assert "[b](official/software/flashrom.md)" in md
    assert report == []


def test_percent_delimited_buttons(repo):
    md, _, _, report = convert(repo, '{{% btn icon="🛒" context="danger" href="https://buspirate.com/get" %}}\n'
                                     'Get Bus Pirate & Accessories\n{{% /btn %}}\n')
    assert "[Get Bus Pirate & Accessories](https://buspirate.com/get)" in md
    assert report == []


def test_angle_delimited_alerts(repo):
    md, _, _, report = convert(repo, '{{< alert context="info" >}}\nHeads up.\n{{< /alert >}}\n')
    assert "> **Note:**\n> Heads up." in md
    assert report == []


def test_tabs_named_with_tabname(repo):
    md, _, _, report = convert(repo, '{{< tabs tabTotal="4">}}\n{{% tab tabName="Windows" %}}\nW\n{{% /tab %}}\n{{< /tabs >}}\n')
    assert "#### Windows\nW" in md
    assert report == []


def test_terminal_blocks_closed_with_a_space(repo):
    md, _, _, report = convert(repo, '{{< term>}}\nHiZ> i\n{{</ term>}}\n')
    assert "```text\nHiZ> i\n```" in md
    assert report == []


def test_the_year_is_filled_in(repo):
    md, _, _, report = convert(repo, 'Copyright (c) {{< year >}} Ian\n')
    assert "{{" not in md and "Copyright (c) 20" in md
    assert report == []


def test_relrefs_that_name_the_md_file(repo):
    md, *_ = convert(repo, '[led]({{< relref "/docs/tutorial-basics/leds-demo.md" >}})')
    assert "[led](official/tutorial-basics/leds-demo.md)" in md


def test_slug_keeps_a_leading_dash_like_hugo():
    assert tool.slug("`:` Repeat (e.g. r:10)") == "-repeat-eg-r10"
