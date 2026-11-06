# Python Scripts for ESP32 Bit Pirate

![bit pirate scripts](bitpirate-wiki/images/65cb7274eb5fc1ee.png)




https://github.com/geo-tp/ESP32-Bit-Pirate-Scripts

This repository provides a collection of ready-to-use Python scripts to **interact**, **log**, and **automate hardware actions** using the ESP32 Bus Pirate via serial communication.

https://github.com/geo-tp/Bit-Pirate-Python

This repository provides the `bit-pirate` python package used with the scripts.

## Use the Web Python Lab

![The ESP32 Bit Pirate Python Lab interface](bitpirate-wiki/images/678bcf9fb07efbee.png)

[Open ESP32 Bit Pirate Python Lab](https://geo-tp.github.io/ESP32-Bit-Pirate/web-tools/python-lab/)


## Create Your Script

`python -m pip install bit-pirate`

```python
from bitpirate import BitPirate

bp = BitPirate.auto_connect()
bp.start()
bp.change_mode("i2c")
bp.send("scan")
bp.wait()
print(bp.receive())
bp.stop()


```

Additional `Helper`, `bpio2` class to parse, bit bang and manipulate response from the ESP32 Bit Pirate.
