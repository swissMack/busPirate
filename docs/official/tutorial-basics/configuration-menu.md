# Configuration Menu

[▶ Watch this as a recording on docs.buspirate.com](https://docs.buspirate.com/docs/tutorial-basics/configuration-menu/)    

```text
HiZ> c
Configuration options
 1. Language / Jezik / Lingua
 2. ANSI color mode
 3. ANSI toolbar mode
 4. LCD screensaver
 5. LED effect
 6. LED color
 7. LED brightness
 x. Exit
 >
```

Type ```c``` followed by ```enter``` to show the Bus Pirate configuration menu. These options control things like the language, live view statusbar and LEDs.

## Overview

|Command | Description |
|---|---|
|```c```|Enter the configuration menu.|

## Configuration

```text
 > 5

LED effect
 1. Disable
 2. Solid
 3. Angle wipe
 4. Center wipe
 5. Clockwise wipe
 6. Top side wipe
 7. Scanner
 8. Gentle glow
 9. Party mode
 x. Exit
 > 9
LED effect set to Party mode
```

Type a menu option number followed by ```enter```. Choose a configuration setting by typing the number followed by ```enter```.

## Exit and Save
```text
 x. Exit
 > x

Configuration file: Saved
```

Press ```x``` followed by ```enter``` at any prompt to exit the configuration menu. 

## Settings file

```text
HiZ> ls
       350 bpconfig.bp
0 dirs, 1 files
```

Settings are saved in bpconfig.bp and will load automatically when the Bus Pirate restarts.

```text
HiZ> cat bpconfig.bp
{
"terminal_language": 0,
"terminal_ansi_color": 1,
"terminal_ansi_statusbar": 0,
"display_format": 0,
"lcd_screensaver_active": 0,
"lcd_timeout": 0,
"led_effect": 8,
"led_color": "0xFF0000",
"led_brightness_divisor": 10,
}
```

All Bus Pirate config files contain simple JSON formatted data.
