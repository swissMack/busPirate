# The Bus Pirate terminal, in the dashboard — design

**Date:** 2026-09-22
**Status:** approved design, not yet implemented

## The problem

The dashboard speaks the **binary** protocol. It enters binary mode at connect
and holds it for the whole session. The Bus Pirate's own **terminal** — the
`HiZ>` prompt, the `?` menu, `i`, `m`, `v`, `W`, `~` — is a different mode, and
the board can only be in one at a time.

So there is currently no way to reach the terminal from the dashboard. The
Traffic pane shows every byte in both directions, but as binary hex: it is a
protocol log, not a console.

## Decisions taken

| Question | Decision |
|---|---|
| What can the terminal do? | A **full interactive console** — type any command, see the response, stay until you leave |
| Bench state across the switch | **Warn, then come back clean.** A confirmation names what will be lost; nothing is silently restored or re-energised |
| The rest of the dashboard | **The terminal takes over.** Other panels are unavailable until you return |
| Architecture | **Model the terminal as a stream** and add an input path, rather than building a parallel subsystem |

Rejected: a read-only transcript (the terminal almost never speaks unprompted,
so it would show nearly nothing); a one-shot command box (cannot drive `~` or
the `m` menus, and on a v3 every command would cost a reset); restoring pins
and supplies on return (power returning to a target without an explicit
request at that moment is how hardware gets damaged); and refusing the
terminal on v3 (withholds the feature for a cost a warning can explain).

## What already exists

This is a smaller build than it first appears. Already implemented and tested:

| Piece | Where |
|---|---|
| Terminal I/O — write, then drain until quiet | `base.py:219` `read_text()`, used by `identify()` at `base.py:262` |
| Leaving binary mode | `base.py:310` `reset_hardware()`, command `0x0F` |
| Returning to binary mode | `base.py:280` `enter_binary_mode()`, knocks with nulls, 25 retries |
| A stream that holds the port | `session.py:410` `_begin_stream`, `:427` `_read_stream`, `:473` `_finish_stream` |
| Rendering streamed text | `decoders.py:98` `TextDecoder` |
| **Locking out other panels while a stream holds the port** | `session.py:395` |
| An escape hatch for actions that must work anyway | `Action.allow_while_streaming` |

`identify()` already talks to the terminal before binary mode is entered, and
its output already reaches the Traffic pane through the same hook. What is
missing is session state, an input path, and a UI surface.

## The firmware behaviour this rests on

Leaving binary mode is command `0x0F` in bitbang mode. In `Firmware/binIO.c:150-158`:

```c
} else if (inByte == 0b1111) {   // return to terminal
    UART1TX(1);
    BP_LEDMODE = 0;
    WAITTXEmpty();
#ifndef BUSPIRATEV4
    asm("RESET");
#endif
```

So:

- **v3** performs a hardware reset. Supplies off, pins to input, everything
  forgotten. The board comes up in its terminal.
- **v4** does not reset. It falls out of the binary loop back into
  `serviceuser()`, the terminal.
- **Both** clear the MODE LED.

None of this is observed on hardware. See "Verification".

## Design

### 1. Port ownership — the load-bearing decision

`_read_stream`'s docstring states the current invariant: *"The only thing
touching the port while a stream runs."* A console needs writes, and a second
thread writing to the port would break it.

**It is not broken. `send_line` never touches the port.** It pushes onto a
`queue.Queue` carried on the stream state; the reader loop drains that queue
and writes before each read. The stream thread remains the sole owner of the
port, so there is no lock, no race, and no change to the existing invariant —
only a new source of work for the thread that already owns it.

Every other part of this design is downstream of that choice.

### 2. Session state

A `TerminalState`, extending `StreamState` with the input queue and
`kind = "terminal"`. It is stored in the existing `self.stream` slot, which
means the `session.py:395` lockout applies to it with **no new code** — the
takeover behaviour comes from the mechanism that is already there.

Entering: `open_terminal` is an `Action` with `stream=True`, so the existing
`run()` path at `session.py:404` calls `_begin_stream` for it, exactly as it
does for a sniffer. It is **not** `allow_while_streaming`, so starting it while
a sniffer is running is refused by the `session.py:395` gate with the existing
message — the dashboard never has to stop one stream to start another.

1. `reset_hardware()` — command `0x0F`.
2. Settle. On a v3 the board is rebooting; on a v4 it is not. The settle
   duration is an open item (see "Verification").
3. The handler returns `live(...)`, and `_begin_stream` starts the reader
   thread with a `TextDecoder`.

Leaving:

1. Stop the stream — `POST /api/stream/stop` (`server.py:130`), which is the
   existing control; there is no stop *action*.
2. `enter_binary_mode()`.
3. Reset `mode_name`, `_mode` and `last_pins` — the board genuinely is blank,
   and `leds()` reads `last_pins` through `_supplies_on()`, so leaving them
   stale would light VREG over a board with its supplies off.

### 3. Actions

Two, both on the **Connection** panel:

- `open_terminal` — carries `confirm=` text naming exactly what is lost, worded
  per variant. On a v3 it says the board resets and the supplies go off; on a
  v4 it says the protocol mode is dropped. The `Action.confirm` field already
  exists and is already used by `self_test`.
- `send_line` — `allow_while_streaming=True`, the same escape hatch the
  stop-stream endpoint's callers rely on. Takes one `text` param, appends the newline,
  enqueues it. It must also refuse when the running stream is *not* the
  terminal: typing into a sniffer is meaningless, and the `allow_while_streaming`
  flag alone does not distinguish which stream is running.

Closing reuses the **existing stop-stream control**. A second, parallel "leave"
control would be a second way to express one thing.

### 4. Frontend

The live pane already renders streams. It gains an input line.

**It is not selected by `kind`.** `stream["kind"]` is a human display label —
the existing values are `"I2C sniffer"` and `"UART bridge"` — so branching on
it would be both fragile and protocol knowledge in `app.js`, which the
constraints forbid. Instead `live()` gains an `input: bool` flag, and the pane
renders a console when that flag is set. The terminal is then just the first
stream that happens to accept input.

Panels are already disabled while a stream holds the port, so the takeover
needs no new logic — only a banner naming the mode and the way back.

### 5. LEDs

MODE goes dark in the terminal on both variants, because the firmware clears
it on the way out. This is a new `inference` value in the `LED_RULES` table
built in the v4 work — a data change, not a special case in `leds()`. PWR and
USB are unaffected. VREG follows the supplies, which on a v3 are now off.

### 6. Failure paths

Each must leave the dashboard's belief about the board true, or say plainly
that it does not know:

- **Unplugged mid-session.** The reader thread's read fails; the stream ends;
  the session must not then claim to be in binary mode.
- **`enter_binary_mode()` fails on the way back.** It already retries 25 times
  and raises `ModeError` with a useful message. The session must surface that
  and mark itself disconnected rather than pretending the return worked.
- **The v3 settle.** If the stream starts reading before the board has finished
  rebooting, the first output is garbage or missing.

### 7. Testing

- `tests/fake_serial.py` gains a terminal mode: it already models enough of the
  terminal for `identify()` to parse a banner, so this extends that rather than
  inventing it. It should answer `?`, `i` and `v`, echo input, and — for the v3
  variant — model the reset on `0x0F`.
- Round trip: binary → terminal → binary, asserting the mode each way and that
  `last_pins` and `mode_name` are cleared.
- The lockout: another panel's action is refused while the terminal holds the
  port, and `send_line` is not.
- `enter_binary_mode()` failing on return leaves an honest state.
- jsdom: the input line appears only for `kind == "terminal"`, panels grey out,
  the banner names the way back.

## Verification

Everything here about firmware behaviour is read from source, not observed.
Add to the checklist at the end of `docs/troubleshooting.md`:

- [ ] v3: entering the terminal really does reset the board — supplies off,
      pins to input
- [ ] v4: entering the terminal does **not** reset the board
- [ ] Both: MODE goes dark in the terminal
- [ ] The settle time after a v3 reset is long enough that the first prompt is
      not truncated
- [ ] Returning to binary mode works reliably, including straight after a reset
- [ ] `~` self-test runs to completion through the console, including the
      stages that expect input

## Out of scope

- Restoring pins or supplies on return — explicitly rejected above.
- A terminal for the UART **bridge** mode. That is a different thing:
  `uart.py`'s `start_bridge()` has no software exit at all and needs a power
  cycle.
- Scripting or macros over the console.
- Turning the dashboard into a desktop app. That is the separate piece of work
  the terminal question came bundled with, and it gets its own spec.

## Open items

1. **The v3 settle duration after `reset_hardware()`** cannot be derived from
   source. Start conservative, make it a named constant, and tune it against
   real hardware.
2. **`~` self-test is interactive** — it prints in stages and waits for input.
   The input queue must let a line reach the board mid-command, not only at a
   prompt. Worth an explicit test once hardware is available.
