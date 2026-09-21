# Image credits

## Reference cards

`refcard.png` and `seeed-cable.png` are the Bus Pirate reference cards from
the **Dangerous Prototypes** wiki (dangerousprototypes.com), retrieved from
the Internet Archive copy of *Common Bus Pirate cable pinouts*.

The wiki states: *Copyright Where Labs, LLC. CC BY-SA unless otherwise noted.*
They are redistributed here under **CC BY-SA** with that attribution, and the
dashboard shows the credit alongside the images.

They are the reference for the Seeed Studio / Adafruit probe cable, which is
the colour order the Bus Pirate firmware itself uses. SparkFun cables are
usually the reverse order, and the v2go differs again.

## Board photo

`board-v3.png` is a photograph of a **Bus Pirate v3.6**, supplied by the
repository owner. It looks like a product photograph — the sort Seeed Studio
and its resellers publish — but **its licence has not been established**.

That is fine while this repository is private. Before making the repository
public, either confirm the licence, replace it with your own photograph of
your own board, or remove it — `buspirate/web/wiring.py` holds the pin
coordinates, and the diagram degrades gracefully without the image.

The pin coordinates in `BOARDS["v3"]` (in `buspirate/web/wiring.py`) were
measured from this file and checked against the board's own silkscreen. If
you replace the photo, re-measure them.

`board-v4.jpg` is a photograph of a **Bus Pirate v4.0**, supplied by the
repository owner. Same situation as `board-v3.png`: it looks like a product
photograph, but **its licence has not been established**.

That is fine while this repository is private. Before making the repository
public, either confirm the licence, replace it with your own photograph of
your own board, or remove it — `buspirate/web/wiring.py` holds the pin
coordinates, and the diagram degrades gracefully without the image.

The pin and LED coordinates in `BOARDS["v4"]` (in `buspirate/web/wiring.py`)
were measured from this exact file. If you replace the photo, re-measure
them.
