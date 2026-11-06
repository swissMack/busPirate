# LED Mode

This mode allows full control of addressable RGB LEDs connected to the ESP32.  
Use it to configure the LED type, fill colors, run test animations, or manipulate individual pixels.  
Supports all major chipsets via FastLED (WS2812, APA102, SK6812, etc.).

⚠️ Warning: Connecting too many LEDs may overload your USB port or damage your battery. Ensure you don't exceed the power limitations to avoid potential harm.


## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.


| Command                          | Description                                                              |
|----------------------------------|--------------------------------------------------------------------------|
| `fill <color>`                  | Fill all LEDs with the specified color                                   |
| `set <index> <color>`          | Set a specific LED at index to the color (index starts at 0)                                 |
| `reset [index]`               | Turn off a specified LED or all LEDs (sets all pixels to black)                             |
| `blink`                          | Blink the whole LED strip with the white color                         |
| `rainbow`                        | Show a rainbow animation along the strip                                 |
| `chase`                          | Run a chasing dot animation                                              |
| `cycle`                          | Shift all LEDs color continuously                                              |
| `wave`                           | Display a wave-style sine animation                                      |
| `setprotocol`                    | Select the LED protocol manually (WS2812, APA102, etc.)                  |
| `config`                         | Configure LED pin, length and protocol                                   |

## 🧪 Recipes

- [Test an addressable LED strip](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/test-addressable-led-strip/)
- [Configure an addressable LED strip](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/configure-addressable-led-strip/)
- [Set one LED pixel by index](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/set-one-led-pixel-index/)

## 📝 Notes

- All protocols supported by FastLED are available (~50 protocols).
- `config` sets the pin, the brightness and the number of LEDs.
- `fill` and `set` support multiple formats for `<color>`:
  - HTML name: `red`, `blue`, `silver`, `darkblue`...
  - Hex: `#FF00FF`, `0x00FF00`
  - Decimal RGB: `255 0 255`
- `set` could also be used with `on` or `off`.
- `set` starts counting from 0, which means the first LED on the strip has index 0.
- `setprotocol` shows the massive list of supported LED protocols, type the index of the protocol to chose it
- If unsure about your LED model, use `scan` or try `setprotocol`.



## 📌 Example Usage

```bash
scan                 # Try to detect LEDs protocol
config               # Configure pin/protocol/length
fill green           # All LEDs to green
fill 0 255 0         # All LEDs to green
set 3 #0000ff        # Set LED 3 to blue
set 1 white          # Set LED 1 to white
set 2 0 255 255      # Set LED 2 to cyan
set 0 off            # Set the first LED to black (off)
set 0 on             # Set the first LED to white (on)
blink                # Blink all LEDs
chase                # Show chasing pattern
reset                # Turn off all LEDs
reset 1              # Turn of the LED 1
setprotocol          # Manually set protocol
```

## ▶️ Demo
![demo10](bitpirate-wiki/images/e163dad391ee6138.png)



## 🔧 Hardware
![led-strip-rgb-ws2812-5050-x-8-leds-53mm](bitpirate-wiki/images/72bef9c327779e5d.jpg)

![61TWrCVhq-L _UF1000,1000_QL80_](bitpirate-wiki/images/801bc2a6aba4c91f.jpg)
