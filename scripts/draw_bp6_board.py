"""Draw static/img/board-bp6.svg from wiring.BP6_HEADER and BP6_GEOMETRY.

Run: .venv/bin/python scripts/draw_bp6_board.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buspirate.web.wiring import BP6_GEOMETRY, BP6_HEADER  # noqa: E402

g = BP6_GEOMETRY
out = Path(__file__).resolve().parent.parent / "buspirate/web/static/img/board-bp6.svg"
top = g["first_y"] - 40
bottom = g["first_y"] + (len(BP6_HEADER) - 1) * g["pitch"] + 40
parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {g["width"]} {g["height"]}" '
    f'width="{g["width"]}" height="{g["height"]}" font-family="Helvetica, Arial, sans-serif">',
    f'<rect x="230" y="20" width="240" height="{g["height"] - 40}" rx="24" fill="#1d1f24" stroke="#555"/>',
    '<text x="350" y="60" fill="#ddd" font-size="22" text-anchor="middle">Bus Pirate 6</text>',
    f'<rect x="{g["x"] - 22}" y="{top}" width="44" height="{bottom - top}" rx="4" fill="#111" stroke="#777"/>',
]
for index, name in enumerate(BP6_HEADER):
    y = g["first_y"] + index * g["pitch"]
    parts.append(f'<circle cx="{g["x"]}" cy="{y}" r="9" fill="#c9a227" stroke="#7a5c00"/>')
    anchor, x = ("end", g["x"] - 34) if index % 2 == 0 else ("start", g["x"] + 34)
    parts.append(f'<text x="{x}" y="{y + 6}" fill="#eee" font-size="16" text-anchor="{anchor}">{name}</text>')
parts.append(f'<text x="350" y="{g["height"] - 40}" fill="#999" font-size="14" '
             'text-anchor="middle">USB-C on top · header viewed from the front</text>')
parts.append("</svg>")
out.write_text("\n".join(parts) + "\n", encoding="utf-8")
print(f"wrote {out}")
