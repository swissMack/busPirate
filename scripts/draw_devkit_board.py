"""Draw static/img/board-bitpirate.svg from the pin lists in web/wiring.py.

The dashboard rings pins at the positions wiring.py gives, so the picture is
generated from the same numbers rather than drawn by hand. Run it again after
changing DEVKIT_J1, DEVKIT_J3 or DEVKIT_GEOMETRY:

    .venv/bin/python scripts/draw_devkit_board.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from buspirate.web.wiring import (  # noqa: E402
    DEVKIT_GEOMETRY,
    DEVKIT_J1,
    DEVKIT_J3,
)

OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "buspirate", "web", "static", "img", "board-bitpirate.svg",
)


def draw() -> str:
    g = DEVKIT_GEOMETRY
    width, height = g["width"], g["height"]
    left, right = g["j1_x"] - 25, g["j3_x"] + 25
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="Helvetica, Arial, sans-serif">',
        # The board itself.
        f'<rect x="{left}" y="15" width="{right - left}" height="{height - 30}" rx="10" '
        'fill="#1d2b44" stroke="#0f1726" stroke-width="2"/>',
        # The WROOM module's shield and antenna.
        '<rect x="290" y="20" width="120" height="26" rx="3" fill="#2c3e5c"/>',
        '<text x="350" y="37" fill="#9fb3d1" font-size="9" text-anchor="middle">antenna</text>',
        '<rect x="290" y="48" width="120" height="150" rx="4" fill="#c8ccd2" stroke="#8a9099"/>',
        '<text x="350" y="115" fill="#3a3f47" font-size="12" text-anchor="middle" '
        'font-weight="bold">ESP32-S3</text>',
        '<text x="350" y="132" fill="#3a3f47" font-size="10" text-anchor="middle">WROOM-1</text>',
        # Two USB-C ports along the bottom edge.
        '<rect x="285" y="470" width="44" height="30" rx="6" fill="#b9bec6" stroke="#6d737c"/>',
        '<rect x="371" y="470" width="44" height="30" rx="6" fill="#b9bec6" stroke="#6d737c"/>',
        '<text x="350" y="462" fill="#e8edf5" font-size="10" text-anchor="middle">'
        'use the port marked USB</text>',
        '<text x="350" y="232" fill="#e8edf5" font-size="11" text-anchor="middle">'
        'ESP32-S3-DevKitC-1</text>',
        '<text x="350" y="250" fill="#9fb3d1" font-size="10" text-anchor="middle">'
        'running ESP32 Bit Pirate</text>',
        f'<text x="{g["j1_x"]}" y="32" fill="#e8edf5" font-size="10" text-anchor="middle">J1</text>',
        f'<text x="{g["j3_x"]}" y="32" fill="#e8edf5" font-size="10" text-anchor="middle">J3</text>',
    ]
    for column, x, anchor, label_x in (
        (DEVKIT_J1, g["j1_x"], "start", g["j1_x"] + 12),
        (DEVKIT_J3, g["j3_x"], "end", g["j3_x"] - 12),
    ):
        for index, name in enumerate(column):
            y = g["first_y"] + index * g["pitch"]
            parts.append(
                f'<rect x="{x - 7}" y="{y - 7}" width="14" height="14" fill="#11151c"/>'
                f'<circle cx="{x}" cy="{y}" r="4" fill="#d4af37"/>'
                f'<text x="{label_x}" y="{y + 3}" fill="#e8edf5" font-size="9" '
                f'text-anchor="{anchor}">{name}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    with open(OUT, "w") as handle:
        handle.write(draw())
    print(f"wrote {OUT}")
