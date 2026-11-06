# Digital I/O Mode

This mode allows full manual control of any GPIO pin on the ESP32.  
Use it to read, write, sniff, or generate PWM signals on individual pins.  
It’s useful for testing, probing and debugging.


## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.
| Command                        | Description                                                           |
|-------------------------------|-----------------------------------------------------------------------|
| `scan`                  | Monitor a group of pins to detect signal transitions and identify active lines          |
| `pins`                  | Show pin state for all available GPIOs          |
| `read <gpio>`                  | Read the current digital state of a gpio (returns 0 or 1)              |
| `set <gpio> <H/L/I/O>`         | Set the gpio mode or level: `H`=HIGH, `L`=LOW, `I`=INPUT, `O`=OUTPUT   |
| `pullup <gpio>`                | Configure the gpio as INPUT with internal pull-up resistor             |
| `pulldown <gpio>`              | Configure the gpio as INPUT with internal pull-down resistor             |
| `pulse <gpio> <us>`            | Pulse given gpio for us duration                       |
| `sniff <gpio>`                 | Monitor the pin and log level transitions until you press [ENTER]     |
| `pwm <gpio> [freq] [duty]`     | Generate a PWM signal on the gpio (freq hz, duty in %)                          |
| `servo <gpio <angle>`         | Move an RC servo connected to gpio to the given angle (0–180°)                             |
| `toggle <gpio> <ms>`           | Toggle the gpio state every ms until ENTER is pressed                   |
| `measure <gpio> [ms]`          | Count raising and falling edges to calculate frequency                 |
| `jam <gpio> [min_us] [max_us]`       | Randomly switch gpio state with randomized us delay                 |
| `reset <gpio>`                 | Reset the gpio: detach PWM, set to INPUT with no pull-up               |

## 🧪 Recipes

- [Measure a GPIO signal frequency](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/measure-gpio-frequency/)
- [Generate PWM or move a servo](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/generate-pwm-servo-signal/)
- [Pulse a GPIO in microseconds](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/pulse-gpio-microseconds/)
- [Sniff GPIO edges from the CLI](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/sniff-gpio-edges-cli/)
- [Detect an unknown GPIO signal with wizard](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/detect-unknown-pin-with-wizard/)
- [View GPIO logic on the device screen](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/view-logic-on-device-screen/)
- [View analog GPIO values on screen](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/view-analog-gpio-on-screen/)
- [Listen to GPIO activity as audio](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/listen-gpio-activity-as-audio/)
- [Check logic levels before wiring](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/check-logic-levels-before-wiring/)

## 📝 Notes

- All numbers must be valid and not protected GPIOs.
- `pwm` uses a lower resolution for very high frequency.
- `servo` uses 50 Hz PWM with 1–2 ms pulses.
- `sniff` will log every rising/falling edge of the pin.
- `reset` also detaches any PWM channel previously attached.
- `measure` can take the duration in ms as a paramaters (max 5000ms).


## 📌 Example Usage

```bash
mode dio
read 21           # Print digital level on GPIO 21
set 21 O          # Set GPIO 21 as OUTPUT
set 21 H          # Set GPIO 21 to HIGH
set 21 high       # Set GPIO 21 to HIGH
set 21 low        # Set GPIO 21 to LOW
pullup 19         # Enable internal pull-up on GPIO 19
pulse 1 50        # Set pin 1 to HIGH for 50 us
sniff 22          # Monitor GPIO 22 transitions
pwm 5 1000 75     # Output PWM at 1kHz, 75% duty on GPIO 5
servo 1 90        # Move servo on GPIO 1 at 90 degres angle
toggle 1 100      # Toggle GPIO 1 every 100ms
measure 5         # Calculate falling/raising edges for 1sec
measure 5 2000    # Calculate edges for 2 sec
jam 1             # Randomly switch pin state with 5-100us random delay
reset 5           # Reset GPIO 5 to neutral state
```

## ▶️ Demo
![dio](bitpirate-wiki/images/682b8777ca901057.png)
