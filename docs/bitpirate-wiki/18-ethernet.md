# Ethernet Mode

Commands to configure and use the **Ethernet (W5500)** interface on ESP32.


## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.

| Command                    | Description                                                       |
|---------------------------|-------------------------------------------------------------------|
| `connect`                 | Connect via **DHCP**                                              |
| `status`                  | Show interface status (Link, IP, Mask, GW, DNS, MAC, speed/duplex)|
| `ping <host>`             | Ping an IP address or hostname                                    |
| `discovery [timeout_ms]`    | Discovers devices on the connected local network and list them (optional timeout for request)                 |
| `ssh <host> <user> <pass> [port]` | Open an **SSH** session (optional `port`, default 22)      |
| `telnet <host> [port]`|Start an interactive Telnet session with the given host, using optional port (default: 23) |
| `nc <host> <port>`        | Open a **netcat** TCP session                                     |
| `nmap <host> [-p ports]`  | TCP/UDP port scan on the target host with options                            |
| `modbus <host> [port]` | Opens an interactive Modbus session with the given host, using optional port (default: 522) |
| `http get <url>` | Performs an HTTP(s) GET to the specified URL, returning headers and the JSON body (if response content type is json) |
| `http analyze <url>`                  | Performs an in-depth analysis of a given URL using public APIs (urlscan, W3C validator, etc.) |
| `lookup mac <mac addr>`                    | Lookup vendor and details for a given MAC address                           |
| `lookup ip <ip addr>`                      | Lookup geolocation and details for a given IP address or url                      |
| `reset`                   | Hardware reset of the Ethernet module                             |
| `config`                  | Configure SPI pins, IRQ, SPI speed, and MAC address               |

## 🧪 Recipes

- [Wire a W5500 Ethernet module](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/wire-w5500-ethernet-module/)
- [Connect a W5500 Ethernet module](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/connect-w5500-ethernet/)
- [Check an HTTP endpoint](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/check-http-endpoint/)
- [Open a Modbus TCP session](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/open-modbus-tcp-session/)
- [Test a raw TCP service with nc or telnet](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/test-raw-tcp-nc-telnet/)
- [Check open ports with nmap mode](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/check-open-ports-nmap/)

## 📝 Notes

- Uses a **W5500** over SPI with the official ESP-IDF Ethernet driver and the **lwIP** TCP/IP stack.
- Currently **DHCP only** (static IP not exposed yet in the CLI).
- `ping` supports either raw IPs (e.g., `8.8.8.8`) or hostnames (e.g., `example.com`).
- `ssh`, `nc`, and `nmap` commands are the same as WiFi mode.
- `http` works with both http and https.
- On **M5Stick (ESP32)** the Ethernet stack is **disabled** to avoid IRAM overflow.


## ⚙️ `config`

Configure the SPI bus pins/params and the MAC used by the Ethernet interface.

**Supported parameters:**

- **CS** (Chip Select) — `pinCS`
- **SCK / MISO / MOSI** — `pinSCK`, `pinMISO`, `pinMOSI`
- **IRQ** (W5500 INT, open-drain) — `pinIRQ` (required)
- **RST** (W5500 Reset) — `pinRST` (optional)
- **SPI Freq** — `spiHz` (e.g., `8000000` for 8 MHz)
- **MAC** — default or custom MAC, e.g., `DE:AD:BE:EF:00:42`
- W5500 Pinout
- ![ethernet-module-pinout](bitpirate-wiki/images/d24b11ceb938538c.jpg)

---

## 📌 Example Usage

```bash
mode ethernet                  # Switch to Ethernet mode
config                         # Configure SPI pins, IRQ, MAC and SPI speed
connect                        # Acquire IP via DHCP
status                         # Show link & IP details
ping 8.8.8.8                   # Ping Google DNS
ssh host user pass             # SSH on default port 22
ssh host user pass 2222        # SSH on custom port
telnet telehack.com            # Telnet on url default port 23
telnet 64.13.139.230 23        # Telnet on ip with port 23 
modbus 45.8.248.56             # Modbus session with default port 522
nc example.com 80              # Open a TCP connection (netcat)
lookup ip 8.8.8.8              # Get loc and infos about ip
lookup mac 44:38:39:ff:ef:57   # Get infos about mac addr
reset                          # Hardware reset via RST of the W5500
```

```bash
# Nmap
nmap example.com                  # Default scan (100 most common TCP ports)
nmap 192.168.1.1                  # Default scan using ip (100 most common TCP ports)
nmap 192.168.1.10 -p 22           # TCP Scan on port 22
nmap example.com -p 22,80         # TCP scan ports 22 and 80
nmap example.com -p 1-100         # TPC scan ports 1 to 100
nmap example.com -sU -p 53,123    # UDP scan on DNS (53) and NTP (123) ports
```

```bash
# HTTP
http get google.com              # HTTPS get on https://google.com
http get https//exmpl.com        # HTTPS get on host
http get http://8.8.8.8          # HTTP get on google DNS
http analyze google.com          # HTTPS analyze on https://google.com
http analyze https//exmpl.com    # HTTPS analyze on url
```


## 🔧 Hardware
- [W5500 Ethernet module](https://geo-tp.github.io/ESP32-Bit-Pirate/modules/w5500/) — wired TCP, HTTP, nmap and Modbus target.

![w5500-ethernet-netzwerk-internet-modul-192960](bitpirate-wiki/images/42f8b9808fb9df49.jpg)
