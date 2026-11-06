# Pirate Assistant

The **Pirate Assistant** is an integrated smart interface that translates human intent into executable commands for the firmware. It's simplify the usage of the Bus Pirate by allowing users to describe what they want to do, without needing to know exact commands.

## Example 1 - Monitor pins
![aibox6](bitpirate-wiki/images/6188a9cb72fb6394.png)

## Example 2 - Set PWMs
![aibox4](bitpirate-wiki/images/0d670230c7dc0c22.png)

## Example 3 - Monitor I2C registers
![aibox3](bitpirate-wiki/images/62f1b8caae6339c1.png)

## Example 4 - PWMs on mobile phone
![38455953-9CEE-4E4B-965B-B1AC43C3CAEC](bitpirate-wiki/images/a2d93f1bce7c66f9.png)


## 🔐 Gemini API Key

The Pirate Assistant uses the Gemini API for natural language translation. See [API Quickstart](https://ai.google.dev/gemini-api/docs/quickstart) to get a key (free).


### How to use it

1. Connect to the ESP32 Bus Pirate WEB interface
2. Open the **Pirate Assistant** with ✨ button
2. Click **API Key**
3. Paste your Gemini API key

Once saved, the assistant can start translating requests into firmware commands.


### Where the key is stored

- The API key is stored **locally in the browser**
- It is **not hardcoded in the firmware**
- It is **not embedded in the device**
- It remains available for future sessions on the same browser unless manually cleared

## ⚠️ Limitations

- Requires internet access
- Suggestions may need manual validation
- The Pirate Assistant can make errors
