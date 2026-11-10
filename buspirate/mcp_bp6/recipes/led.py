"""LED recipes: an addressable strip on IO0, and the board's own LEDs (no target power)."""

from __future__ import annotations

from typing import Any, Dict, List

from ...bp6.modes import LED_SUBMODES
from . import Recipe, register

DOCS = "https://docs.buspirate.com/docs/"
MAX_PIXELS = 512
Options = Dict[str, Any]


def _color(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFFFFFF:
        raise ValueError("a colour is a whole number 0 to 0xFFFFFF (0xRRGGBB), not %r" % (value,))
    return value


def _pixels(opts: Options) -> List[int]:
    colors = opts.get("colors")
    if colors is not None:
        if not isinstance(colors, (list, tuple)) or not colors:
            raise ValueError("colors must be a non-empty list of 0xRRGGBB numbers")
        pixels = [_color(c) for c in colors]
    else:
        count = opts["count"]
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("count must be a whole number, 1 or more, not %r" % (count,))
        pixels = [_color(opts["color"])] * count
    if len(pixels) > MAX_PIXELS:
        raise ValueError("at most %d pixels, not %d" % (MAX_PIXELS, len(pixels)))
    return pixels


def _strip_check(bp: Any, opts: Options) -> Dict[str, Any]:
    try:
        if opts["kind"] not in LED_SUBMODES:
            raise ValueError("kind must be one of %s, not %r"
                             % (", ".join(sorted(LED_SUBMODES)), opts["kind"]))
        _pixels(opts)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def _strip_action(bp: Any, opts: Options) -> Dict[str, Any]:
    """Light the strip: every pixel the colour, or the list of colours in order."""
    pixels = _pixels(opts)
    with bp.led() as m:
        m.configure(opts["kind"])
        m.write_pixels(pixels)
    return {"kind": opts["kind"], "count": len(pixels),
            "colors": ["0x%06X" % c for c in pixels[:16]]}


register(Recipe(
    name="led-strip", title="Addressable LED strip (WS2812 / APA102)",
    words=("led-strip", "led", "ws2812", "neopixel", "apa102", "dotstar", "strip", "pixels"),
    bus="led", default_mv=5000, min_mv=3300, max_mv=5000, pullups=False, milliamps=300,
    wiring=(("DIN / DI", "IO0"), ("CI (APA102 clock)", "IO1"), ("GND", "GND"), ("5V", "VOUT")),
    check=_strip_check, action=_strip_action,
    options={"kind": "ws2812", "count": 8, "color": 0x101010, "colors": None},
    source=DOCS + "command-reference/",
    notes=("a long strip at full white draws far more than the 300 mA limit: keep the colour "
           "dim, or power a long strip from its own supply and join the grounds",)))


def _onboard_check(bp: Any, opts: Options) -> Dict[str, Any]:
    try:
        if opts["colors"] is not None:
            if not isinstance(opts["colors"], (list, tuple)) or not opts["colors"]:
                raise ValueError("colors must be a non-empty list of 0xRRGGBB numbers")
            for c in opts["colors"]:
                _color(c)
        _color(opts["color"])
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def _onboard_action(bp: Any, opts: Options) -> Dict[str, Any]:
    """Colour the board's own LEDs, or with resume=True give them back to the board."""
    if opts["resume"]:
        bp.resume_onboard_leds()
        return {"resumed": True}
    colors = opts["colors"]
    if colors is None:
        colors = [opts["color"]] * bp.status().led_count
    bp.set_onboard_leds([int(c) for c in colors])
    return {"resumed": False, "colors": ["0x%06X" % int(c) for c in colors]}


register(Recipe(
    name="onboard-leds", title="The Bus Pirate's own LEDs: colour them, or give them back",
    words=("onboard-leds", "onboard", "leds", "led", "light", "colour", "color", "resume"),
    bus="led", default_mv=0, min_mv=0, max_mv=0, pullups=False, wiring=(),
    check=_onboard_check, action=_onboard_action,
    options={"color": 0x001000, "colors": None, "resume": False},
    source=DOCS + "command-reference/",
    notes=("this needs no target and no wiring",)))
