# Bus Pirate 6

The **Bus Pirate 6** is the current Bus Pirate: an RP2350B with a
programmable power supply, a current limit, onboard pull-ups and eight
buffered IO pins that work from 1.2 to 5 V. The dashboard drives it through
**BPIO2**, its binary interface, so every panel gets structured answers from
the board rather than reading its terminal's screen text.

This page is about using the BP6 with this app. The board's own manual is in
the guide too, under **Official Bus Pirate 5/6 manual**. Start with its
[quick setup](official/tutorial-basics/quick-setup.md) if the board is new to
you.

## What you need

- Firmware built on **2026-10-12 or later**. Older builds have BPIO2 but no
  UART in it. To see yours, type `i` in the board's terminal and read the
  `Firmware main branch @ … (date)` line.
- A USB-C lead. macOS needs no driver.

To try the dashboard without hardware, pick **simulated-bp6** from the port
list, or run `buspirate dashboard --demo --variant bp6`.

## The two ports

The BP6 appears as two serial ports. The app pairs them and shows one entry,
**Bus Pirate 5/6**, in the port list.

| Port (macOS) | What it is |
|---|---|
| `/dev/cu.usbmodem6buspirate1` | The board's own terminal, the `HiZ>` prompt |
| `/dev/cu.usbmodem6buspirate3` | The binary port, where BPIO2 runs |

Only one program can hold a port at a time. If you have the terminal open in
`screen`, quit it (Ctrl-A, then `k`, then `y`) before connecting.

## Connecting

Pick the board and press Connect. That is all.

After every unplug, the BP6 starts with its logic-analyzer binary mode, not
BPIO2. When the binary port does not answer, the app switches BPIO2 on
through the terminal port: it types `binmode`, picks 2, and answers **no** to
"Save setting?". Nothing is saved on the board, so it starts the same way
next time. If the terminal is asking "VT100 compatible color mode?", the app
answers that first.

## Updating the firmware

1. In the board's terminal, type `$` and press Enter. The board restarts into
   its bootloader and a disk named **RP2350** appears on the Mac.
2. Copy **`bus_pirate6.uf2`** onto that disk. The board restarts by itself
   with the new firmware, on the same port names.

Builds come from the forum's
[auto-build thread](https://forum.buspirate.com/t/bus-pirate-5-auto-build-main-branch/20)
or the firmware repository's CI artifacts (`firmware-rp2350-…`). Use the file
named `bus_pirate6.uf2`; the BP5 files will not work on a BP6. The official
[firmware update page](official/tutorial-basics/firmware-update.md) has more
detail.

## Power and the current limit

The **Power & pull-ups** panel controls the supply on the **VOUT** pin.

- **0.8 to 5.0 V**, up to 500 mA. It starts at 3.3 V.
- A **current limit** from 1 to 500 mA, 300 mA unless you change it. If the
  target draws more, the board cuts the power. The status bar and the panel
  say **Current limit tripped**; fix the fault, then press **Re-enable**.
  If the target already draws too much when you switch on, the board does
  not start the supply at all: the app says **The supply would not start**.
- The quick buttons switch the supply on at **1.8, 3.3 or 5.0 V** in one
  click. 5.0 V asks first, because it can damage a 3.3 V part.
- **Set voltage and current limit** takes any value. Going above 3.6 V, or
  choosing **no limit** (0 mA), needs the tick box "I have checked the target
  takes this".
- While you work, the status bar shows the measured voltage and current, for
  example `3.30 V / 12 mA`.

The I2C, SPI, UART and 1-Wire panels have **Switch on the supply** and
**Switch on the pull-ups** boxes too. Ticked, they switch them on at the
voltage and limit this panel last set (300 mA if none). Unticked, they leave
them as they are: only this panel switches the supply off, so running a scan
never cuts the power to your target.

More: [Programmable power supply](official/tutorial-basics/power-supply.md).

## Pull-ups

One switch turns on **10 kΩ pull-up resistors** from every IO pin to VOUT.
They need a voltage on VOUT to do anything: switch the supply on, or feed the
target's own supply into VOUT. I2C and 1-Wire need them.

More: [Pull-up resistors](official/tutorial-basics/pullup-resistors.md).

## Pins

| Bus | Pins |
|---|---|
| I2C | SDA **IO0**, SCL **IO1** |
| SPI | CLK **IO6**, MOSI **IO7**, MISO **IO4**, CS **IO5** |
| UART | TX **IO4**, RX **IO5** |
| 1-Wire | data **IO0** |

The header reads VOUT, IO0 to IO7, GND. The hook-up drawing on each panel
shows the pins that panel uses. **Read voltages and current** on the Power
panel lists the voltage on every IO pin, labelled with its job in the current
mode.

## What the dashboard does not do on the BP6, and why

- **Raw-wire (2-wire and 3-wire), DIO, infrared, JTAG, PS/2, USB, the LEDs
  and the logic analyzer.** BPIO2 has no data handler for them, or the
  dashboard has no panel. The Raw-wire panel is hidden. All of them work in
  the board's own terminal: open the **Terminal** panel.
- **UART with odd parity or 9 data bits.** BPIO2 offers 8 bits with no or
  even parity. The terminal offers the rest.
- **More than one 1-Wire device.** BPIO2 works in whole bytes, and listing
  several devices needs bit-level control, so **Find devices** finds the one
  device on the bus. With several, type `m 1wire` and then `scan` in the
  Terminal panel.
- **I2C ACKs per byte.** The BP6 reports one ACK or NACK for the whole
  transaction.

## The Terminal panel

It opens the BP6's terminal port. Nothing is reset, and the supply and mode
stay as they were. Type commands as you would in `screen`; only Enter (a
`\r`) ends a line. If the board asks "VT100 compatible color mode?", answer
`n`. When you close the terminal, the dashboard reads the board again, so a
mode or supply you changed by hand shows up in the panels.

Every command is in the [command reference](official/command-reference.md).

## Troubleshooting

**"The Bus Pirate 6 did not answer on its BPIO2 port."** Unplug the board,
plug it back in and connect again. Check that no `screen` session holds
either port. Check that the firmware is from 2026-10-12 or later (`i` in the
terminal).

**The supply keeps switching itself off.** That is the current limit
tripping. Look for a short, or raise the limit if the target really needs
more. **"The supply would not start"** is the same fault caught at switch-on.

**Nothing found on I2C.** Switch on the supply (or power the target), switch
on the pull-ups, and check SDA is on IO0 and SCL on IO1.

The full real-board checklist is in
[Troubleshooting](troubleshooting.md).
