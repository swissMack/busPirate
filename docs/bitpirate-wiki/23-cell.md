# CELL Mode

The **CELL mode** interfaces with a **cellular modem module** to interact with GSM/LTE networks.  
It allows you to query modem status, dump the SIM card informations, send SMS messages, place calls, and execute USSD commands.


## 🧩 Commands
Arguments in `< >` are required, while arguments in `[ ]` are optional.


| Command        | Description |
|----------------|-------------|
| `modem`        | Show modem information and firmware details |
| `network`      | Display current network registration and signal information |
| `operator`     | List available cellular operators |
| `sim`          | Show SIM card status and identifiers |
| `unlock`       | Unlock the SIM card using the PIN code |
| `phonebook`    | Display contacts stored on the SIM |
| `sms`          | Perform SMS operations (list, send, read, delete) |
| `call`         | Perform call operations |
| `ussd [code]`  | Send a USSD command (balance, services, etc.) |
| `setmode`      | Change modem operating mode |
| `config`       | Configure modem settings and communication parameters |

## 🧪 Recipes

- [Check cellular modem status](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/check-cellular-modem-status/)
- [Dump SIM card information from a cellular modem](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/dump-sim-card-info-cellular-modem/)
- [Check GSM/LTE network registration](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/check-cellular-network-registration/)
- [Send a USSD request from a modem](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/send-ussd-cellular-modem/)
- [List SIM phonebook contacts](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/list-sim-phonebook-contacts/)
- [Send an SMS from a cellular modem](https://geo-tp.github.io/ESP32-Bit-Pirate/recipes/send-sms-from-cellular-modem/)

## 📝 Notes
- All SIMCom 2G, 3G, and 4G modem modules supporting the standard AT interface should be compatible.
- Cellular modules require a **valid SIM card** and **network coverage**.
- Some commands may require the **SIM to be unlocked first**.
- SMS, calls, and USSD operations may incur **charges depending on your mobile operator**.
- Always ensure the **antenna is connected** before powering the modem.
- **Connect UART TX/RX** to the ESP32 Bus Pirate and power the module:

![image](bitpirate-wiki/images/cd0ad1a0d0e9c23a.png)



## 🔧 Hardware

- [SIMCom cellular AT modem](https://geo-tp.github.io/ESP32-Bit-Pirate/modules/cellular-at-modem/) — UART AT, SIM, SMS, USSD and modem target.

![image](bitpirate-wiki/images/6573ea9e25e69f3f.png)
![image](bitpirate-wiki/images/5a905ed983844351.png)
