# Bus Pirate v4 support — design

**Date:** 2026-09-21
**Status:** approved design, not yet implemented

## The problem

Variant *detection* already works. `buspirate/device.py` parses the `i` banner
into `v3` / `v4` / `unknown`, and `capabilities_for()` gates actions on it, so
the dashboard already hides v3-only self-test on a v4 and offers the v4-only
pull-up rail command.

What does not exist is any *presentation* for v4:

- `wiring.py` holds a single `BOARD_V3` constant — one photo, one pin map.
- `/api/state` serves exactly that one board, whatever is plugged in.
- `app.js` can only apologise: *"Photo is a Bus Pirate v3.6. …"*
- `docs/bus-pirate-v4.md` is 49 lines of prose with no pinout and no LED table.
- The LED model shipped on 2026-09-21 is v3-only and is wrong for v4.

So a v4 owner gets a dashboard that shows them the wrong board.

## Decisions taken

| Question | Decision |
|---|---|
| What does the switch control? | Auto-detect from the banner, with a manual override |
| v4 board artwork | The owner's own v4.0 photograph (700×525, matching `board-v3.png`) |
| v3 board artwork | Unchanged — keep the v3.6 photograph, which matches the owner's board |
| Scope | Presentation, plus resolving the already-declared `CAP_EXTENDED_AUX` — which planning showed to be undeliverable, so it is removed rather than wired up (see section 5) |
| Guided LED verification UI | No — the existing markdown checklist is enough |

Rejected: shipping every variant's data to the client and switching there (bloats
every response and leaks protocol knowledge into `app.js`, which is deliberately
protocol-agnostic); and a reference-only switch in the Guide (splits the mental
model in two).

## What we established about v4

All of this is derived from the Dangerous Prototypes hardware and firmware
repository and from the board photograph — **none of it is observed on hardware
yet.** See "Verification" below.

### The I/O header is a 2×6, not a 2×5

Twelve pins, confirmed three independent ways: the `v4.0` board render
(`hardware/v4/BusPirate-v4.brd.png`, same revision as the owner's board —
2010 Jun, same R3/R4/R5/R6 silkscreen), the `v4.0e` render's annotation, and the
firmware's own pin list at `Firmware/procMenu.c:1692`.

| Left | Right |
|---|---|
| GND | +5V |
| +3V3 | VPU |
| ADC | AUX2 |
| AUX1 | AUX |
| CS | MISO |
| CLK | MOSI |

### The LEDs differ in kind, not just position

Same four in the same left-to-right order (PWR, USB, MODE, VREG), but on v4
**two** are firmware-driven rather than one:

| LED | v3 | v4 |
|---|---|---|
| PWR | Hardware: `VCC → R2 → LED → GND` | Hardware |
| USB | Hardware: FT232RL `RXLED#` — pulses on received traffic, dark at idle | **Firmware**: `BP_LEDUSB` = RB10 (`hardwarev4a.h:65`). `main.c:76` lights it while enumerating, `main.c:95` turns it **off** once configured |
| MODE | Firmware: `BP_LEDMODE` = RA1 (`hardwarev3.h:51`) | Firmware: `BP_LEDMODE` = RB8 (`hardwarev4a.h:59`) |
| VREG | Hardware: off regulator VR2's own switched output | Hardware |

The v4 USB rule is the inverse of v3's: **steady dark means enumerated
correctly.** This is the single most likely thing to look like a bug if the
reading of `main.c` is wrong, so it heads the verification list.

There is no FT232RL on a v4 at all — the PIC24FJ256GB106 does USB itself.

## Design

### 1. Data model (`buspirate/web/wiring.py`)

`BOARD_V3` becomes:

```python
BOARDS: Dict[str, Dict[str, Any]] = {"v3": {...}, "v4": {...}}
```

Each entry keeps today's shape — `image`, `width`, `height`, `gutter`,
`gutter_left`, `label`, `pins`, `side`, `leds` — and gains its own `caveat`
string, replacing the module-level `BOARD_CAVEAT`.

- `"v3"` is today's values, unchanged, including the LED coordinates already
  measured from `board-v3.png`.
- `"v4"` is the new photograph, twelve pins, and LED coordinates to be measured
  from the image the same way (see "Open items").

A sibling table captures the behaviour rules:

```python
LED_RULES: Dict[str, Dict[str, str]] = {...}
```

Keyed by variant then LED name, giving the driver (`hardware` / `firmware`), the
inference rule the session should apply, and the tooltip text. This is what lets
`session.leds()` stop hard-coding v3 semantics.

### 2. Session (`buspirate/web/session.py`)

One new field:

```python
self.display_variant: Optional[str] = None   # None = follow detection
```

And one new method:

```python
def effective_variant(self) -> str:
    """The override, else the detected variant, else the documented default."""
```

Precedence: explicit override → detected `profile.variant` → `"v3"`. The `"v3"`
fallback is for unidentified boards and for the disconnected state, and is
reported as `variant_source == "default"` so the UI can say so rather than
implying certainty.

`leds()` consults `LED_RULES[self.effective_variant()]` instead of its current
hard-coded v3 rules. Notably `USB` becomes variant-dependent: always `False` on
v3 (the client flashes it from the traffic feed), and on v4 `False` once
connected, since the firmware turns it off after enumeration.

`disconnect_blocking()` must reset `display_variant` to `None` alongside the
existing `last_pins` reset — otherwise an override set while inspecting a v4
silently persists onto the next v3 you plug in.

### 3. API (`buspirate/web/server.py`)

`board`, `board_caveat` and `led_note` resolve through `effective_variant()`.
New top-level fields on `/api/state`:

| Field | Meaning |
|---|---|
| `variant` | The effective variant driving the UI |
| `variant_detected` | What the banner actually said, or `null` |
| `variant_source` | `"detected"` \| `"override"` \| `"default"` |
| `variants` | `["v3", "v4"]` — what can be selected |

The switch is a `set_variant` action on the **Connection** panel taking one
param (`v3` / `v4` / `auto`), so it flows through the existing `Action` registry,
parameter coercion and error handling rather than needing a bespoke endpoint.

### 4. Frontend (`app.js`, `index.html`, `app.css`)

- A `v3 | v4 | auto` selector in the status block, beside the LED strip.
- `boardDiagram()` needs no change in kind — it already renders whatever board
  it is served. It gains nothing protocol-specific.
- `flashUsbLed()` becomes conditional: only wired up when the served rules say
  USB is traffic-driven, so a v4 does not flicker a LED that its firmware holds
  steady.
- A visible badge whenever `variant_source == "override"` **and** the override
  disagrees with `variant_detected`, so nobody silently reads v4 documentation
  with a v3 plugged in. This is the safety property that makes a manual override
  acceptable at all.

### 5. AUX2 — not drivable, and the capability is a lie

**Finding, 2026-09-21 during planning: AUX2 is unreachable over the binary
protocol on a v4.** The spec previously assumed it needed confirming; it is now
confirmed, negatively:

- `Firmware/binIOhelpers.c:20-25` — `BP_AUX2_HI/LOW` is wrapped in
  `#if defined(BUSPIRATEV1A)`. On every other board that bit is the pull-ups.
- `Firmware/binIO.c:268` and `:308` — `binBBpindirectionset` and `binBBpinset`
  cover exactly five pins: AUX0, MOSI, CLK, MISO, CS. There is no AUX2 bit.
- `Firmware/binIO.c:261-265` — `binReset` touches `BP_AUX2_IN()` only under
  `BUSPIRATEV1A`.
- The AUX2 handling in `AUXpin.c` is reached from `procMenu.c`, the **terminal**
  menu. The dashboard speaks binary and never enters it.

So `CAP_EXTENDED_AUX`, declared for v4 at `device.py:111`, describes something no
binary-mode client can use. It is dead, and worse, it is misleading.

**Revised plan:** draw AUX2 on the v4 diagram, because it is physically on the
header and people will look for it, but label it as terminal-mode only and
unreachable from here. Delete `CAP_EXTENDED_AUX` rather than leave a capability
that promises something the transport cannot deliver.

Implementing AUX2 properly would mean leaving binary mode, driving the text
menu, and returning — a different piece of work with its own risks, and out of
scope here.

### 6. Documentation

| File | Change |
|---|---|
| `docs/bus-pirate-v4.md` | The 2×6 pinout, its own LED table, and the "no FT232RL" consequence |
| `docs/pins-and-power.md` | The LED section becomes explicitly per-variant rather than v3-with-a-footnote |
| `docs/user-guide.md` | The ASCII header diagram gains a v4 form |
| `docs/troubleshooting.md` | A v4 block in the existing "Not yet verified against hardware" checklist |
| `buspirate/web/static/img/CREDITS.md` | `board-v4.png` provenance, recorded the same way as the v3 photo |

### 7. Testing

The `client` fixture in `tests/test_dashboard.py` is **already parametrised over
`["v3", "v4"]`**, so the existing 280 tests exercise both paths for free the
moment the state API becomes variant-aware. New tests:

- The served board matches the connected variant, for each variant
- v4 serves twelve pins including AUX1/AUX2; v3 serves ten
- LED rules differ per variant — in particular v4's USB is never flashed
- Override precedence: override beats detection; `auto` restores detection
- Disconnecting clears the override
- `variant_source` reports the right one of the three cases
- AUX2 is offered on v4 and absent on v3
- jsdom: switching redraws the diagram, and the mismatch badge appears when the
  override disagrees with detection

## Verification

Everything v4 here is derived from documentation, schematic and firmware source.
The owner has a v4 to test against. Add to the existing checklist at the end of
`docs/troubleshooting.md`:

- [ ] v4: MODE lit from the moment the dashboard connects, not from entering a
      protocol
- [ ] v4: USB LED **dark** once enumerated — the inverse of v3
- [ ] v4: the 2×6 header order against your own silkscreen
- [ ] v4: the measured LED pixel coordinates land on the real LEDs
- [ ] v4: confirm AUX2 really is inert over the binary protocol — the
      Pins panel should leave it alone, and nothing should move it
- [ ] v3: the LED model shipped 2026-09-21 — MODE lit from connect, USB
      flickering on traffic, VREG following the supplies

The v3 line belongs there too. That model is equally firmware-derived and was
never added to the list when it shipped.

## Out of scope

- Other v4 binary-protocol features (e.g. whether onboard supply voltage
  selection is reachable outside terminal mode) — open-ended, and not needed to
  make the dashboard correct for v4
- Replacing the board photographs with licence-clean renders. Considered and
  rejected: the only v3 render available is a v3.8, which would trade a
  licensing question for an accuracy one on the owner's actual v3.6 board
- A guided in-dashboard LED verification flow — the markdown checklist is enough
- v2go, and board revisions other than the two photographed

## Open items

1. **The v4 photograph must be saved to
   `buspirate/web/static/img/board-v4.png`** before the geometry can be
   measured. It was supplied in conversation, not as a file.
2. **Its licence is unestablished**, exactly as `board-v3.png`'s is. Record it in
   `CREDITS.md` as a pre-public action; do not assert a licence.
3. ~~The AUX2 binary command needs confirming.~~ **Resolved 2026-09-21:**
   it does not exist for v4. See section 5.
