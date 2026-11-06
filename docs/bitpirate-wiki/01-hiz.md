# HiZ Mode (High Impedance)

This is the **default mode** when the firmware starts, it disables all lines.


## 🧩 Commands

There are **no specific commands** available in HiZ mode.

You can still use global commands like:

| Command         | Description                        |
|-----------------|------------------------------------|
| `mode <name>`   | Switch to another mode             |
| `system`        | Opens an interactive shell for system commands       |
| `man`           | Opens a firmware guide (quick start, examples, etc) |
| `profile`           | Opens a shell to load and save pins configuration |
| `alias`         | Create shortcuts for a command or multiple commands
| `repeat <count> <cmd>`         | Repeat a command or multiple commands
| `wizard <gpio>`           | Monitor a GPIO and detect signal type |
| `listen <gpio>`           | GPIO activity to audio, using I2S configured output |
| `logic <gpio>`   | Display a logic analyzer on the ESP32 screen         |
| `analogic <gpio>`  | Read and display analog values of the given GPIO on the ESP32 screen                 |
| `help`          | Display available commands         |
| `P`, `p`        | Pull-up management (has no effect in HiZ mode) |


## 🧪 Recipes

- [Open a Web Serial terminal](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/open-web-serial-terminal/)
- [Make the first serial connection](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/first-serial-connection-firmware/)
- [Select a protocol mode quickly](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/select-protocol-mode-cli/)
- [Use help and man before a workflow](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-help-and-man-firmware/)
- [Open the system status shell](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/open-system-status-shell/)
- [Use Bus Pirate-style bytecode instructions](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-bytecode-instructions/)
- [Choose the right GPIO pinout](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/choose-gpio-pinout-before-wiring/)
- [Save pin profiles and aliases](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/save-pin-profiles-and-aliases/)
- [Create command aliases for common tasks](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/create-command-alias-shortcuts/)
- [Repeat commands for quick testing](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/repeat-commands-for-testing/)
- [Chain commands with delays](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/chain-commands-with-delays-cli/)
- [Enable smart pull-ups per mode](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/enable-smart-pullups-per-mode/)
- [Manage LittleFS files from the Web UI](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/manage-littlefs-files-webui/)
- [Open Python Scripting Lab](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/open-python-scripting-lab/)
- [Use Python automation over serial](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-python-automation-over-serial/)

## 📝 Notes

> ⚠️ **Note on ESP32 hardware limitations**:
> The term **HiZ** comes from the original Bus Pirate, where GPIOs could be fully tri-stated.  
> On the ESP32, there is **no true "disconnected" state** — instead, we configure all GPIOS as inputs with no pull-up or pull-down resistors.



## 📌 Example Usage

```bash
mode         # open mode selector
logic 1
analogic 1
wizard 1
repeat 5 scan
repeat 10 set 1 L || delayms 10 || set 1 H || delayms 100
listen 1
alias
help
system
P
p
```

## ▶️ Demo

![system](bitpirate-wiki/images/360fd83599c6461c.png)
