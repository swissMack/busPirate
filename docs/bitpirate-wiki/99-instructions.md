# Instruction Syntax

The instruction system follows the **Bus Pirate** syntax and is **partially supported**.

## 🧠 Overview

Instructions are sequences enclosed in brackets (e.g., `[0xAA r:8]`) and parsed into byte-level actions called ByteCodes.  
They allow you to directly express sequences of read/write/start/stop/delay in a compact and flexible form.

## ✅ Supported Syntax Examples

| Syntax              | Meaning                                |
|---------------------|----------------------------------------|
| `[0xAA 0xBB]`       | Write two bytes 0xAA 0xBB              |
| `[r:4]`             | Read 4 bytes                           |
| `[0xA1 r]`          | Write 0xA1 → Read 1 bytes              |
| `['A']`             | Write ASCII 'A' (char literal)         |
| `["ABC"]`           | Write ASCII string ABC                 |
| `[d:10]`            | Delay 10 microseconds                  |
| `[D:1]`             | Delay 1 millisecond                    |

## ⛔ Unsupported Features (for now)

- Loops and nested brackets
- Inline macros or expressions
- Bit-level operations (like `.1`, `.0`)
- Block `{}` and macro `>` prefixes

## ⚙️ Notes

- Hex values (`0xAA`) and decimal numbers (`123`) are supported.
- Repeats like `r:10`, `rrrrr` are parsed correctly.
- Strings in `"quotes"` are written as ASCII.


## 🔗 Parser Behavior

- Anything inside `[]` is considered an instruction.
- Special characters like `r`, `d`, `D` map to specific bytecode actions.

## 🧪 Example Usages

- `[0xA0 r:1 0xB1 r]` → Write 0xA0, Read, Write 0xB1, Read
- `[d:100 D:2]`       → Delay 100µs then 2ms
- `["AT" d:10 r:255]` → Write AT, Delay 10µs, then read 255 bytes

> This syntax is parsed but not all instructions are currently executed in all modes.
