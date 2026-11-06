# General Commands

These commands are available globally, regardless of the active mode.  
They are used to manage the firmware, control settings, or switch modes.

## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.



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

## ⚙️ System shell



- **📊 System summary**: High-level snapshot: model, firmware version, uptime, memory size.
- **📟 Hardware info**: Static details: chip family/revision, cores/clock,  capabilities (Wi-Fi/BT), flash.
- **🗄️ Memory**: Live RAM view: total/free heap, PSRAM stats (if present).
- **🧩 Partitions**: Flash layout: partition table and partition usage.
- **🗂️ LittleFS**: Filesystem tools: total/used bytes.
- **🧰 NVS stats**: Non-Volatile Storage overview.
- **📒 NVS entries**: Inspect actual keys: namespaces, types.
- **🌐 Network**: Connectivity status: Wi-Fi mode/SSID/RSSI/IP, DHCP, gateway/DNS.
- **🔄 Reboot**: Reboot the device after confirmation
- **🚪 Exit**: Leave the System Shell and return to the previous menu.


## 📝 Notes

- You can type `mode` or `m` without arguments to select the current mode. You can also type `m uart` or `mode I2C`.



- The `P` and `p` commands **enable or disable pull-up resistors intelligently**, based on the currently active mode.
- The behavior is context-sensitive and applies only to relevant GPIOs:

| Mode      | Affected Pins            | Description                             |
|-----------|--------------------------|-----------------------------------------|
| `UART`    | RX                       | Enables/disables pull-up on receive pin |
| `HDUART`  | IO                       | Enables/disables pull-up on shared I/O  |
| `1WIRE`   | DQ                       | Controls pull-up on 1-Wire data line     |
| `I2C`     | SDA, SCL                 | Enables/disables pull-ups on both lines |
| `SPI`     | MISO                     | Controls pull-up on MISO input line      |
| Others    | —                        | Pull-ups are not applicable              |


## 📌 Example Usage

```bash
help
man
profile
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


![ezgif-5150930da7efa5d6](bitpirate-wiki/images/5d75edd028e09a6f.png)
