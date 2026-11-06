# Build the Project

This guide explains how to set up PlatformIO and build the project. It works on Windows, macOS, and Linux.

---

## 1) Install PlatformIO

You can use **either** the VS Code extension (recommended) **or** the command-line tools.

### Option A — PlatformIO IDE (VS Code)
1. Install **Visual Studio Code**.
2. In VS Code, open the **Extensions** panel and install **“PlatformIO IDE”**.
3. Restart VS Code if prompted.

### Option B — PlatformIO Core (CLI)
- Install **PlatformIO Core** (`pio`) using your system’s package manager or the official installer.
- Verify installation:
  ```bash
  pio --version
  ```

---

## 2) Get the Source

```bash
git clone https://github.com/geo-tp/ESP32-Bus-Pirate.git
```

---

## 3) Understand Environments

PlatformIO uses **environments** defined in `platformio.ini`.  
Each environment appears as a section:

```ini
[env:cardputer]
platform = espressif32
board    = m5stack-stamps3
framework = arduino
...

[env:stamps3]
platform = espressif32
board    = m5stack-stamps3
framework = arduino
...
```

- The text after `env:` (e.g., `cardputer`, `stamps3`) is the **environment name**.
- Environments select toolchains, boards, frameworks, flags, and upload settings.

**How to see available environments:**
- **Open `platformio.ini`** and read the `[env:...]` sections.
- Or run (CLI):
  ```bash
  pio project config
  ```
  (Look for the `[env:...]` headers in the output.)

---

## 4) Choose the Right Environment

Pick the environment that matches your target board or build profile. Common patterns:

- `env:stamps3` → ESP32-S3 Stamp / M5StampS3
- `env:cardputer` → M5Stack Cardputer
- `env:release` / `env:debug` → Different optimization/logging levels

> If unsure, check the comments in `platformio.ini` or your hardware’s README notes.

---

## 5) Build

### VS Code (PlatformIO IDE)
- Open the project folder in VS Code.
- In the lower **Status Bar**, pick the environment from the **PlatformIO (checkmark) selector**.
- Click **Build** (✔️) in the PlatformIO toolbar or press **⌘/Ctrl + Alt + B**.

### CLI
```bash
# Build the default environment (if one is set)
pio run

# Build a specific environment
pio run -e <env_name>
```

Build artifacts are placed in `.pio/build/<env_name>/`.

---
