# Frontend test

`frontend.mjs` loads the real `index.html` and `app.js` in jsdom and drives
them against a running dashboard, with a real WebSocket. It covers the parts
the Python tests cannot: rendering, form building, the hook-up diagrams, the
live log, and the guide.

It needs Node and two packages, so it is deliberately **not** part of
`make test`.

```bash
npm install jsdom ws          # once, anywhere on the path
make demo &                   # the dashboard, against a simulated device
node tests/ui/frontend.mjs    # exits non-zero on any failure
```

It disconnects the device first, since the server keeps the connection across
page loads.
