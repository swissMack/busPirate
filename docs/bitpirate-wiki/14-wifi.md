# Wi-Fi Mode

This mode provides control over Wi-Fi connectivity, scanning, spoofing, and sniffing.  
Supports both **client** and **access point (AP)** modes.

The credentials will be **saved automatically** to enable future use of the Web CLI mode.

⚠️ Wi-Fi Warning: Avoid using Wi-Fi commands (like disconnect, sniff, or reset) while connected via Web CLI, it will break the connection.

## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.


| Command                      | Description                                                                 |
|------------------------------|-----------------------------------------------------------------------------|
| `scan`                      | Lists all nearby Wi-Fi networks, with details                               |
| `connect`     | Scans and select a Wi-Fi Network to connect with        |
| `disconnect`                | Disconnects from the current Wi-Fi network                                  |
| `status`                    | Shows current Wi-Fi connection status, IP, and MAC addresses                |
| `probe`                     | Scan networks to find open ones and try if a web access is available        |
| `discovery [timeout_ms]`    | Discovers devices on the connected local network and list them (optional timeout for request)                 |
| `ping <host>`               | Sends a ping to a given host (e.g., 8.8.8.8 or google.com)                  |
| `sniff`                     | Starts a passive Wi-Fi sniffer across all channels                          |
| `repeater`          | Forward and relay Wi-Fi traffic, allowing the ESP32 to operate as a lightweight repeater                    |
| `spam`                   | Spams access points creation with random SSID                               |
| `flood [channel]`                   | Flood access points creation on a channel                               |
| `waterfall`                   | Show WiFi channel acitivity on the ESP32 screen                              |
| `ap <ssid> <pass>`          | Starts a Wi-Fi Access Point with optional STA fallback                      |
| `deauth [ssid]`     | Sends a deauthentication frames targeting the specified SSID, scan networks and select ssid if not provided   | 
| `ssh`|Start an interactive SSH session with the given host, using optional port (default: 22) |
| `telnet <host> [port]`|Start an interactive Telnet session with the given host, using optional port (default: 23) |
| `nc <host> <port>` | Start a raw TCP connection to the given host and port using Netcat |
| `nmap <host> [-p ports]` | Check ports on <host> and tell if it’s open, closed, or filtered. Check common 100 ports if no port specified |
| `modbus <host> [port]` | Opens an interactive Modbus session with the given host, using optional port (default: 522) |
| `http get <url>` | Performs an HTTP(s) GET to the specified URL, returning headers and the JSON body (if response content type is json) |
| `http analyze <url>`                  | Performs an in-depth analysis of a given URL using public APIs (urlscan, W3C validator, etc.) |
| `lookup mac <mac addr>`                    | Lookup vendor and details for a given MAC address                           |
| `lookup ip <ip addr>`                      | Lookup geolocation and details for a given IP address or url                      |
| `spoof sta <mac>`           | Changes MAC address of station interface                                    |
| `spoof ap <mac>`            | Changes MAC address of access point interface                               |                      
| `webui`                     | Displays the current Web UI URL if connected                                |
| `reset`                     | Resets the Wi-Fi interface                                                  |


## 🧪 Recipes

- [Scan Wi-Fi and find local devices](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/scan-wifi-find-local-devices/)
- [Check an HTTP endpoint](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/check-http-endpoint/)
- [Open a Modbus TCP session](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/open-modbus-tcp-session/)
- [Test a raw TCP service with nc or telnet](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/test-raw-tcp-nc-telnet/)
- [Check open ports with nmap mode](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/check-open-ports-nmap/)
- [Start the Web CLI through Wi-Fi hotspot](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/start-web-cli-hotspot/)
- [Run a passive Wi-Fi sniffer session](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/run-passive-wifi-sniffer-session/)
- [Look up a MAC address vendor](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/lookup-mac-address-vendor/)
- [Look up IP address details](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/lookup-ip-address-details/)
- [Start a Wi-Fi access point](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/start-wifi-access-point-mode/)
- [Analyze a URL with HTTP APIs](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/analyze-url-with-http-apis/)

## 📝 Notes

- **connect** stores credentials in NVS for auto-reconnect after reboot.
- **ap** will fallback to dual mode (AP + STA) if existing credentials are saved.
- **spoof** only works before starting Wi-Fi. Use `reset` first.
- **discover** will send a ping request across all network local adresses to list devices
- **scan** displays encryption type, BSSID, channel, RSSI, and flags like `[open]`, `[vulnerable]`, `[hidden]`.
- **sniff** cycles through Wi-Fi channels (1–13) and logs packets in real time.
- **modbus** opens an interactive shell with read, write monitor operations on holding, coils and inputs.
- **webui** URL is shown if connected via Wi-Fi STA.
- **nc** debugs raw protocols, testing server responses, or communicating with custom services directly over TCP.
- **nmap** to check the state of the given port on the specified hosts. Use `-p 22,80,223`, `-p 10-50` to specify multiples ports.
- **http** works with both http and https, example: `http://www.google/com` `google.com` `https://example.com` (default to https if no prefix provided)
- **lookup** uses a online database, if the given url was never scanned before, it will return no results
- **deauth** Works on most 2.4 GHz Wi-Fi devices up to WPA2, though some modern clients may resist.
- **probe** continuously scans for open Wi-Fi networks, attempts to connect to each one, and checks internet access is available.
- See https://github.com/geo-tp/ESP32-Bus-Pirate-Scripts to log WiFi data in a file.
- ⚠️ *Running Wi-Fi commands while using Web CLI may disconnect your session. Prefer USB serial in that case.*


## 📌 Example Usage

```bash
mode wifi
scan                             # List networks
connect MyWiFi mypassword        # Connect to a Wi-Fi network
connect                          # Scan networks, ask to select, ask the password
status                           # Show connection and IP info
sniff                            # Passive monitor of Wi-Fi packets
probe                            # Start probing open networks
deauth                           # Select SSID and send deauth frames
spoof sta AA:BB:CC:DD:EE:FF      # Spoof STA MAC address
ping 8.8.8.8                     # Ping google DNS
ping google.com                  # Ping google website
ssh myssh.com user password      # Connect to myssh.com via SSH
ssh myssh.com user pass 2022     # Connect to myssh.com via SSH with port 2022
telnet telehack.com              # Telnet on url default port 23
telnet 64.13.139.230 23          # Telnet on ip with port 23
modbus 45.8.248.56               # Modbus session with default port 522
ap spam                          # Spams beacons
ap MyHotspot 12345678            # Start AP with optional STA fallback
nc 192.168.1.12 80               # Start Netcat to given host and port
lookup ip 8.8.8.8                # Get infos about ip address
lookup ip github.com             # Get infos about url
lookup mac 44:38:39:ff:ef:57     # Get infos about mac address
disconnect                       # Disconnect from network
webui                            # Print URL for Web UI if connected
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


## ▶️ Demo
![demo14](bitpirate-wiki/images/333ba9ac86f0a329.png)
