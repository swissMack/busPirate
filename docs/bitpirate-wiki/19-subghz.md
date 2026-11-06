# SubGHz Mode

Sub-GHz refers to radio frequencies below 1 GHz—common bands including **315 MHz**, **433 MHz**, **868 MHz (EU)** and **902–928 MHz (US)**. This mode works with the **CC1101** sub‑GHz radio module.

---

## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.
| Command        | Description |
|----------------|-------------|
| `scan`         | Scan supported bands and report **RSSI peaks** to find and pick the most active frequency |
| `sweep`        | Sweep over a band; estimates **activity** + **confidence** per frequency |
| `trace`        | On‑device real‑time logic trace of GDO0 (oscilloscope‑style view on the screen) |
| `waterfall`        | Show real‑time frequency peaks on a specified range on the ESP32 screen |
| `send <payload> [te]`         | Send a specific payload (int/hex up to 64bits) with Princeton protocol and adjustable time base (te) 
| `receive`       | Receive raw or analyze captured frames and **guess encoding** (pulse‑length / Manchester / PWM), bitrate, and possible payload |
| `replay`       | Capture up to 1024 symbols and **play them back** |
| `record`       | Record up to 1024 symbols and save them to a file on the [LittleFS storage](https://github.com/geo-tp/ESP32-Bus-Pirate/wiki/99-LittleFS) |
| `bruteforce`   | Transmit bruteforce sequences for 12 bit keys protocols **(Nice/Came/Ansonic/Holtek/Linear/Chamberlain)** ⚠️ |
| `jam`          | Transmit **random bursts** at  band or specific frequency, prompts for frequence hold time and burst gap ⚠️ |
| `load`                          | Load and select `.sub` files from the [LittleFS storage](https://github.com/geo-tp/ESP32-Bus-Pirate/wiki/99-LittleFS)  ⚠️
| `ear`       | Convert real-time RSSI variations from the SubGHz radio into audible tones (choose frequency and threshold)
| `setfrequency` | Set the operating **frequency** (choose a band list or enter a **Custom** MHz value) |
| `config`       | Interactive setup of **SPI pins** and **GDO0**, then initializes CC1101 |


## 🧪 Recipes

- [Wire a CC1101 Sub-GHz module](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/wire-cc1101-subghz-module/)
- [Find active Sub-GHz frequencies](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/scan-subghz-frequency-cc1101/)
- [Receive and analyze a Sub-GHz frame](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/receive-subghz-frame/)
- [Sweep SubGHz frequency activity](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/sweep-subghz-frequency-activity/)
- [Record a SubGHz signal to LittleFS](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/record-subghz-signal-littlefs/)
- [Load a Flipper SubGHz .sub file](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/load-subghz-flipper-sub-file/)
- [Use the SubGHz Raw CDC adapter](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/use-subghz-raw-cdc-adapter/)

## ⚠️ Important Warning (Jamming / Transmission)

- Emitting RF energy may be **regulated or illegal** in your jurisdiction without a license or outside ISM limits.  
- **Jamming** can interfere with legitimate devices (alarms, remotes, sensors). Use **only in controlled lab environments** and ensure compliance with local laws.  
- Keep output power and duty cycle minimal when testing. You are responsible for how you use these features.



## ⚙️ `config`

**Configure the CC1101 pins/params:**
- **CS** (CSN, Chip Select)
- **SCK / MISO / MOSI**
- **GDO0** (data pin)
- **VCC** 3.3v
- **CC1101 Pinout**
### ![e9lninwf098d1](bitpirate-wiki/images/776f7ebb92a52c41.jpg)


## 📂 Load (`.sub` files)

The `load` command can play back Sub-GHz files from the [**Flipper Sub-GHz DB**](https://github.com/Zero-Sploit/FlipperZero-Subghz-DB).

### How it works (quick start)
1. **Upload the file(s)**  
   In the Web UI, open  [**Files → LittleFS**](https://github.com/geo-tp/ESP32-Bus-Pirate/wiki/99-LittleFS) and drop your `.sub` files.  

2. **Load from the device**  
   In SubGHz mode, run:
   ```bash
   load
   ```
   - Pick a `.sub` from the list.
   - You can send frames by selecting the index.

3. **Transmit**  
   Auto-configure the CC1101 from the file’s metadata (frequency, preset, protocol).  
   If multiple frames are present, you can iterate and replay as needed.


## 📝 Notes

- **TI CC1101** modules are inexpensive and widely available.  
- `scan` and `sweep` help discover active carriers; `sweep` gives a more nuanced **confidence** estimation by combining peak level and activity ratio.  
- A few **kHz offset** can degrade reception; fine‑tune around the discovered peak.  
- To discover a device’s frequency: run `scan`, repeatedly press the remote or listen the signal for a few seconds, then stop and pick the highest peak frequency.  
- `bruteforce` is an adapted version from the Bruce firmware (https://github.com/pr3y/Bruce).
- `ear` uses the I2S pins for audio output, which are configured by default if a speaker is present on the device.
- For better reliability, prefer **USB Serial** logging over Wi‑Fi (lower latency).


## 📌 Example Usage

```bash
config               # Configure SPI pins and GDO0, initialize CC1101
setfrequency         # Choose a band or enter a custom MHz value
scan                 # Scan band and print RSSI peaks (press ENTER to stop)
sweep                # Slow sweep with activity/confidence per frequency
sniff                # Raw pulse capture at current freq (press ENTER to stop)
trace                # Live logic trace of GDO0 on device screen
waterfall            # Live frequency peaks on a specified range
send 0x123456 150    # Send the payload with TE 150ms as base time
receive              # Raw or guess encoding/bitrate/protocol from a captured frame
replay               # Capture frame then replay it
record               # Capture frame and save it to the LittleFS
bruteforce           # Try fixed-code space for selected protocol (lab only)
jam                  # Choose a frequency/band and start jamming (lab only)
load                 # Load .sub files from LittleFS
ear               # RSSI variation to audio tone
```


## ▶️ Demo
![subghz](bitpirate-wiki/images/e2a22f2c27199624.png)


## 🔧 Hardware
- [CC1101 Sub-GHz module](https://geo-tp.github.io/ESP32-Bit-Pirate/modules/cc1101/) — Sub-GHz scan, receive and raw CDC target.

![61nc3Go5p6L](bitpirate-wiki/images/cda71a728e4ee8a7.jpg)
