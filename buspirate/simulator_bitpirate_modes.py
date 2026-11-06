"""The simulated Bit Pirate's own modes: 1-Wire, DIO, JTAG, Wi-Fi, Bluetooth,
and the extra I2C and UART commands the menu offers (boards/bitpirate_modes).

Mixed into :class:`buspirate.simulator_bitpirate.FakeBitPirateSerial`. Every
string is copied from geo-tp/ESP32-Bit-Pirate v1.8, from the controller named
above each handler; anything else in these modes is ``Unknown command``.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

# Data/I2cKnownAdresses.h, the entries for the simulator's two parts.
I2C_KNOWN = {
    0x50: [("AT24Cxx / EDID", "EEPROM"), ("EDID EEPROM", "Display Identification")],
    0x68: [("MPU6050 / MPU9250", "6-Axis / 9-Axis IMU"), ("DS1307 / DS3231", "RTC"),
           ("AMG8833", "IR Thermal Camera")],
}


def crc8(data: Sequence[int]) -> int:
    """The Dallas/Maxim 1-Wire CRC (OneWireService crc8)."""
    crc = 0
    for byte in data:
        for _ in range(8):
            mix = (crc ^ byte) & 1
            crc >>= 1
            if mix:
                crc ^= 0x8C
            byte >>= 1
    return crc


def rom(family: int, serial: Sequence[int]) -> bytes:
    body = [family] + list(serial)
    return bytes(body + [crc8(body)])


#: A DS18B20 at 23.5 °C, the part the 1-Wire wiki page uses.
DS18B20 = rom(0x28, [0xFF, 0x64, 0x1E, 0x0F, 0x00, 0x00])

#: (ssid, security, bssid, channel, rssi)
WIFI_NETWORKS = [
    ("HomeNet", "WPA2", "A4:2B:B0:11:22:33", 6, -48),
    ("Cafe Guest", "OPEN", "F0:9F:C2:44:55:66", 11, -71),
]

#: (address, name, rssi, connectable)
BLUETOOTH_DEVICES = [
    ("e4:5f:01:aa:bb:cc", "Thermo-Hygro", -62, True),
    ("7c:2f:80:12:34:56", "(unknown)", -85, False),
]


def _hex(values: Sequence[int], sep: str = " ") -> str:
    return sep.join(f"{v:02X}" for v in values)


class ModesMixin:
    """The command handlers; state lives on the fake board itself."""

    def _init_modes(
        self,
        onewire_devices: Optional[List[bytes]] = None,
        wifi_networks: Optional[List[Tuple]] = None,
        bluetooth_devices: Optional[List[Tuple]] = None,
        swd_target: Optional[Tuple[int, int, int]] = (13, 12, 0x2BA01477),
    ) -> None:
        #: 1-Wire parts on the data pin, as 8-byte ROM codes.
        self.onewire_devices = list(onewire_devices) if onewire_devices is not None else [DS18B20]
        self.onewire_celsius = 23.5
        self.wifi_networks = list(wifi_networks) if wifi_networks is not None else list(WIFI_NETWORKS)
        self.wifi_connected: Optional[str] = None
        self.bluetooth_devices = (
            list(bluetooth_devices) if bluetooth_devices is not None else list(BLUETOOTH_DEVICES)
        )
        #: (SWDIO GPIO, SWCLK GPIO, IDCODE) of a target on the header, or None.
        self.swd_target = swd_target
        #: DIO: pin to level (0/1), and pin to (frequency, duty) while PWM runs.
        self.dio_levels: Dict[int, int] = {}
        self.dio_pwm: Dict[int, Tuple[int, int]] = {}
        # States/GlobalState.h defaults, ONEWIRE_PIN from [env:s3-devkit].
        self.settings["1WIRE"] = {"Data GPIO": "6"}
        self.settings["JTAG"] = {"GPIOs to scan (SWD/JTAG)": "1 3 5 7 9"}
        #: Lines printed when Enter ends the running stream.
        self._stream_stop: List[str] = []

    # -- shared --------------------------------------------------------------

    def _stream(self, stop: List[str]) -> None:
        """Run until Enter, then print ``stop`` (every 'Press [ENTER]' loop)."""
        self._stream_stop = stop
        self._state = "stream"

    def _stream_key(self, char: str) -> None:
        if char in "\r\n":
            for line in self._stream_stop:
                self._println(line)
            self._state = "prompt"
            self._prompt()

    def _unknown(self) -> None:
        self._println(f"\nUnknown command. Available {self.mode} commands:")

    def _mode_command(self, root: str, rest: str) -> bool:
        """Run a command of the modes here; False when it is not one of them."""
        handler = {
            "1WIRE": self._onewire, "DIO": self._dio, "JTAG": self._jtag,
            "WIFI": self._wifi, "BLUETOOTH": self._bluetooth,
        }.get(self.mode)
        if handler is not None:
            handler(root, rest)
            return True
        if self.mode == "I2C" and root in ("identify", "discovery", "dump", "recover", "sniff"):
            self._i2c_extra(root, rest)
            return True
        if self.mode == "UART" and root == "autobaud":
            self._autobaud()
            return True
        return False

    def _config_after(self, mode: str) -> List[str]:
        if mode == "1WIRE":
            return ["OneWire configured.", ""]
        if mode == "JTAG":
            pins = self.settings["JTAG"]["GPIOs to scan (SWD/JTAG)"].split()
            # JtagController.cpp handleConfig.
            return ["GPIOs set for the scan (SWD/JTAG): " + "".join(p + " " for p in pins),
                    "JTAG/SWD configured.\n"]
        return []

    # -- Controllers/OneWireController.cpp -------------------------------------

    def _onewire(self, root: str, rest: str) -> None:
        if root == "scan":
            self._println("OneWire Scan: in progress...")
            for number, code in enumerate(self.onewire_devices, start=1):
                self._println(f"Device {number}: " + "".join(f"{b:02X} " for b in code))
            if not self.onewire_devices:
                self._println("OneWire Scan: No devices found.")
        elif root == "ping":
            self._println("OneWire Ping: Device present." if self.onewire_devices
                          else "OneWire Ping: No device found.")
        elif root == "read":
            self._println("OneWire Read: Press [ENTER] to stop.\n")
            if not self.onewire_devices:
                # Loops until a part answers a reset, or Enter.
                self._stream(["", "OneWire Read: Stopped by user."])
                return
            code = self.onewire_devices[0]
            self._println("OneWire Read: in progress.")
            self._println("ROM ID: " + _hex(code))
            self._println("Scratchpad: " + _hex(self._scratchpad()[:8]))
            self._println("OneWire Read: Complete.")
            self._println("")
        elif root == "temp":
            self._println("OneWire Temp: Searching for DS18B20...")
            code = next((c for c in self.onewire_devices if c[0] == 0x28), None)
            if code is None:
                self._println("OneWire Temp: No DS18B20 device found.")
                return
            self._println("\nDS18B20 ROM: " + "".join(f"{b:02X} " for b in code))
            self._println(f"Temperature: {self.onewire_celsius:.2f} °C\n")
        elif root == "sniff":
            self._println("OneWire Sniff: Oberserving data line... Press [ENTER] to stop.\n")
            if self.onewire_devices:
                self._println("[Reset] LOW for 480 µs")
                self._println("[Presence] LOW for 120 µs")
            self._stream(["\n\nOneWire Sniff: Stopped by user."])
        elif root == "config":
            self._configure("1WIRE")
        else:
            self._unknown()

    def _scratchpad(self) -> List[int]:
        raw = int(round(self.onewire_celsius * 16)) & 0xFFFF
        data = [raw & 0xFF, raw >> 8, 0x4B, 0x46, 0x7F, 0xFF, 0x08, 0x10]
        return data + [crc8(data)]

    # -- Controllers/DioController.cpp -------------------------------------------

    _DIO_USAGE = {
        "read": "Usage: read <gpio>", "set": "Usage: set <gpio> <IN/OUT/HI/LOW>",
        "pullup": "Usage: pullup <gpio>", "pulldown": "Usage: pulldown <gpio>",
        "pwm": "Usage: pwm <gpio> [frequency] [duty]",
        "measure": "Usage: measure <gpio> [duration_ms]",
        "pulse": "Usage: pulse <gpio> <duration_us>", "servo": "Usage: servo <gpio> <angle>",
        "reset": "Usage: reset <gpio>",
    }

    def _dio(self, root: str, rest: str) -> None:
        if root not in self._DIO_USAGE:
            self._unknown()
            return
        args = rest.split()
        if not args or not args[0].isdigit():
            self._println(self._DIO_USAGE[root])
            return
        pin, more = int(args[0]), args[1:]
        if root == "read":
            value = self.dio_levels.get(pin, 0)
            self._println(f"GPIO {pin} = {value}" + (" (HIGH)" if value else " (LOW)"))
        elif root == "set":
            if not more:
                self._println("DIO Set: Missing mode (IN/OUT/HI/LOW).")
                return
            c = more[0][0].upper()
            if c == "I":
                self._println(f"DIO Set: GPIO {pin} set to INPUT")
            elif c == "O":
                self._println(f"DIO Set: GPIO {pin} set to OUTPUT")
            elif c in "H1":
                self.dio_levels[pin] = 1
                self._println(f"DIO Set: Pin {pin} set to HIGH")
            elif c in "L0":
                self.dio_levels[pin] = 0
                self._println(f"DIO Set: Pin {pin} set to LOW")
            else:
                self._println("Unknown command. Use I, O, H (1), or L (0).")
        elif root == "pullup":
            self.dio_levels[pin] = 1
            self._println(f"DIO Pullup: Set on GPIO {pin}")
        elif root == "pulldown":
            self.dio_levels[pin] = 0
            self._println(f"DIO Pulldown: Set on GPIO {pin}")
        elif root == "pwm":
            freq, duty = int(more[0]), int(more[1])
            self.dio_pwm[pin] = (freq, duty)
            self._println(f"\nDIO PWM: GPIO {pin} ({freq}Hz, {duty}% duty)... "
                          f"Use 'reset {pin}' to stop.\n")
        elif root == "measure":
            ms = min(int(more[0]) if more else 1000, 5000)
            if ms == 5000:
                self._println("Note: Duration limited to 5000 ms max.")
            self._println(f"DIO Measure: Sampling GPIO {pin} for {ms} ms...")
            freq, duty = self.dio_pwm.get(pin, (0, 0))
            edges = int(freq * ms / 1000) if 0 < duty < 100 else 0
            self._println("")
            self._println(" Results:")
            self._println(f"  • Rising edges:     {edges}")
            self._println(f"  • Falling edges:    {edges}")
            self._println(f"  • Approx. frequency: {edges / (ms / 1000):.2f} Hz\n")
        elif root == "pulse":
            level = "LOW" if self.dio_levels.get(pin, 0) else "HIGH"
            self._println(f"DIO Pulse: GPIO {pin} pulsed {level} for {int(more[0])} us.")
        elif root == "servo":
            self._println(f"DIO Servo: Set GPIO {pin} to angle {int(more[0])}... "
                          f"Use 'reset {pin}' to stop.")
        elif root == "reset":
            self.dio_pwm.pop(pin, None)
            self.dio_levels.pop(pin, None)
            self._println(f"DIO Reset: GPIO {pin} to INPUT (no pull-up, no PWM).")

    # -- Controllers/JtagController.cpp ------------------------------------------

    def _jtag(self, root: str, rest: str) -> None:
        if root == "config":
            self._configure("JTAG")
            return
        if root != "scan":
            self._unknown()
            return
        if not rest:
            self._println("Usage: 'scan swd' or 'scan jtag'.")
        elif rest[0] == "s":
            self._println("JTAG: Scanning for SWD devices...")
            pins = {int(p) for p in self.settings["JTAG"]["GPIOs to scan (SWD/JTAG)"].split()}
            target = self.swd_target
            if target and {target[0], target[1]} <= pins:
                self._println("\n SWD device found!")
                self._println(f"  • SWDIO  : GPIO {target[0]}")
                self._println(f"  • SWCLK  : GPIO {target[1]}")
                self._println(f"  • IDCODE : 0x{target[2]:08X}")
                self._println("  ✅ SWD scan done.\n")
            else:
                self._println("\nJTAG: No SWD device found on available GPIOs.")
        elif rest[0] == "j":
            self._println("JTAG: Scanning for JTAG devices...")
            self._println("\nJTAG: No device found on available GPIOs.")
        else:
            self._println("Usage: 'scan swd' or 'scan jtag'.")

    # -- Controllers/WifiController.cpp, Abstracts/ANetworkController.cpp ----------

    def _wifi(self, root: str, rest: str) -> None:
        if root == "scan":
            self._println("WiFi: Scanning for networks...")
            for ssid, security, bssid, channel, rssi in self.wifi_networks:
                line = (f"  SSID: {ssid} | Sec: {security} | BSSID: {bssid} | "
                        f"CH: {channel} | RSSI: {rssi} dBm")
                if security == "OPEN":
                    line += " [open]"
                self._println(line)
            if not self.wifi_networks:
                self._println("WiFi: No networks found.")
        elif root == "status":
            self._wifi_status()
        elif root == "connect":
            full = rest.strip()
            pos = full.rfind(" ")
            if pos <= 0 or pos == len(full) - 1:
                self._println("Usage: connect <ssid> <password>")
                return
            ssid = full[:pos]
            self._println(f"WiFi: Connecting to {ssid}...")
            if any(net[0] == ssid for net in self.wifi_networks):
                self.wifi_connected = ssid
                self._println("\nWiFi: ✅ Connected successfully.")
            else:
                self._println("WiFi: Connection failed.")
        elif root == "disconnect":
            self.wifi_connected = None
            self._println("WiFi: Disconnected.")
        elif root == "ping":
            if not self.wifi_connected:
                self._println("Ping: You must be connected to Wi-Fi or Ethernet. Use 'connect' first.")
                return
            host = rest.split()[0] if rest.split() else ""
            # Services/ICMPService.cpp, its five default pings.
            self._emit(f"--- {host} ping statistics ---\r\n"
                       "5 packets transmitted, 5 received, 0% packet loss, time 14 ms\r\n")
        else:
            self._unknown()

    def _wifi_status(self) -> None:
        net = next((n for n in self.wifi_networks if n[0] == self.wifi_connected), None)
        connected = net is not None
        rows = [
            ("Mode", "Station"), ("AP MAC", "34:85:18:AA:BB:CD"), ("STA MAC", "34:85:18:AA:BB:CC"),
            ("IP", "192.168.1.77" if connected else "0.0.0.0"),
            ("Subnet", "255.255.255.0" if connected else "0.0.0.0"),
            ("Gateway", "192.168.1.1" if connected else "0.0.0.0"),
            ("DNS1", "192.168.1.1" if connected else "0.0.0.0"), ("DNS2", "0.0.0.0"),
            ("Hostname", "bitpirate"), ("SSID", net[0] if connected else "N/A"),
            ("BSSID", net[2] if connected else "N/A"), ("Prov enabled", "No"),
            ("RSSI", f"{net[4]} dBm" if connected else "N/A"),
            ("Channel", str(net[3]) if connected else "N/A"),
            ("Mode", "STA"), ("Status", "CONNECTED" if connected else "DISCONNECTED"),
        ]
        self._println("\n=== Wi-Fi Status ===")
        for key, value in rows:
            self._println(f"{key:<13}: {value}")
        self._println("====================\n")

    # -- Controllers/BluetoothController.cpp ---------------------------------------

    def _bluetooth(self, root: str, rest: str) -> None:
        if root == "scan":
            self._println("Bluetooth Scan: In progress for 10 sec...\n")
            if not self.bluetooth_devices:
                self._println("Bluetooth Scan: No devices")
                return
            # Services/BluetoothService.cpp scanDevices.
            for addr, name, rssi, connectable in self.bluetooth_devices:
                kind = "Connectable" if connectable else "Non-Connectable"
                self._println(f"  {addr} | {name} | RSSI: {rssi} | Type: {kind}\n")
        elif root == "status":
            self._println("Bluetooth Status:")
            self._println("  Mode: Client")
            self._println("  Connected: No")
            self._println("  MAC Address: 34:85:18:aa:bb:ce")
        else:
            self._unknown()

    # -- Controllers/I2cController.cpp, the extra commands ---------------------------

    def _identify(self, address: int, header: bool) -> str:
        text = ""
        if header:
            text += f"\n\r \U0001f4df I2C 0x{address:02X} Identification Result\n"
        known = I2C_KNOWN.get(address, [])
        for component, kind in known:
            text += f"\r  ➤ Could be: - [{kind}] {component}\n"
        if not known:
            text += f"\r  ➤ No match found for address 0x{address:02X}\n"
        return text

    def _i2c_extra(self, root: str, rest: str) -> None:
        args = rest.split()
        address = _address(args[0]) if args else None
        if root == "identify":
            if address is None:
                self._println("Usage: identify <addr>")
                return
            self._println(self._identify(address, True))
        elif root == "discovery":
            self._println("I2C Discover: scanning bus... Press [ENTER] to stop.\n")
            found = sorted(a for a in self.i2c_devices if 1 <= a < 0x7F)
            if not found:
                self._println("No I2C device detected.\n")
                return
            self._println(f"Found {len(found)} device(s):")
            for a in found:
                self._println(f"  - 0x{a:02X}")
            self._println("")
            for index, a in enumerate(found, start=1):
                self._println(f"[{index}/{len(found)}] Device @ 0x{a:02X}")
                self._println(self._identify(a, False))
                self._println("  Ping timing (50x):")
                self._println("    Ok: 50  Nack: 0")
                self._println("    Min: 91 µs  Avg: 94 µs  Max: 102 µs")
                self._println("    Jitter: 11 µs")
                self._println("")
            self._println("I2C Discover: done.\n")
        elif root == "dump":
            if address is None:
                self._println("Usage: dump <addr> [length]")
                return
            memory = self.i2c_devices.get(address)
            if memory is None:
                self._println(f"I2C Dump: No device found at {args[0]}")
                return
            length = max(1, min(int(args[1], 0) if len(args) > 1 else 256, 256))
            self._println(f"I2C Dump: 0x{address:02X} from 0x00 for {length} bytes... "
                          "Press [ENTER] to stop.\n")
            for start in range(0, length, 16):
                row = [memory[i % len(memory)] for i in range(start, min(start + 16, length))]
                text = "".join(chr(b) if 32 <= b <= 126 else "." for b in row)
                self._println(f"{start:02X}:" + "".join(f" {b:02X}" for b in row)
                              + "   " * (16 - len(row)) + "  " + text.ljust(16, "."))
            self._println("")
        elif root == "recover":
            self._println("I2C Reset: Attempting to recover I2C bus...")
            self._println("\nI2C Reset: SDA released. Bus recovery successful.")
        elif root == "sniff":
            self._println("I2C Sniffer: Listening on SCL/SDA... Press [ENTER] to stop.\n")
            self._stream(["\n\nI2C Sniffer: Stopped."])

    # -- Controllers/UartController.cpp handleAutoBaud -------------------------------

    def _autobaud(self) -> None:
        rx = self.settings["UART"]["RX GPIO number"]
        self._println(f"UART Autobaud: Listening on RX GPIO {rx} until detected... "
                      "Press [ENTER] to stop\n")
        if not self.uart_rx:
            self._stream(["UART Autobaud: Stopped by user."])
            return
        self._println("UART Autobaud: Baudrate detected 115200")
        saved = self.settings["UART"]

        def store(answer: str) -> None:
            if answer.lower().startswith("y"):
                saved["Baud rate"] = "115200"

        self._ask([("Save baudrate to config?", "y", store)],
                  ["UART Autobaud: Baudrate saved to config.\n"])


def _address(text: str) -> Optional[int]:
    """I2cController tryParseAddress: decimal or 0x-prefixed hex, 0..0x7F."""
    if re.fullmatch(r"0[xX][0-9a-fA-F]+", text):
        value = int(text, 16)
    elif text.isdigit():
        value = int(text)
    else:
        return None
    return value if 0 <= value <= 0x7F else None
