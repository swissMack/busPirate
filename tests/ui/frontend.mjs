/* Loads the real index.html + app.js in jsdom and drives it against the
   running demo server, so the rendering path is genuinely exercised. */
import fs from "node:fs";
import { JSDOM } from "jsdom";
import { WebSocket as RealWebSocket } from "ws";

// BUSPIRATE_UI_BASE lets `make ui-test` run its demo on a port of its own, so
// the suite can run while a real dashboard holds the default one.
const BASE = process.env.BUSPIRATE_UI_BASE || "http://127.0.0.1:8765";
const ROOT = new URL("../../buspirate/web/static/", import.meta.url).pathname;
const html = fs.readFileSync(`${ROOT}/index.html`, "utf8");
const js = fs.readFileSync(`${ROOT}/app.js`, "utf8");

// This suite disconnects, connects to the first port offered, and presses
// every button — against a real board that is a stranger driving the
// hardware. Before sending a single command, insist the server is a demo:
// a `--demo` server reports `simulated` even while disconnected, a real one
// does not.
const probe = await (await fetch(`${BASE}/api/state`)).json();
if (!probe.status.simulated) {
  console.error(
    `refusing to run: ${BASE} is a real dashboard, not a --demo one, and this ` +
      "suite would drive its hardware. Start a demo server (make ui-test does) " +
      "or point BUSPIRATE_UI_BASE at one."
  );
  process.exit(2);
}

// The server keeps the device connected across page loads, which is what we
// want in real use — so start from a known state.
await fetch(`${BASE}/api/run`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ panel: "connection", action: "disconnect", params: {} }),
});

const dom = new JSDOM(html, { url: BASE, runScripts: "outside-only", pretendToBeVisual: true });
const { window } = dom;
window.fetch = (path, options) => fetch(path.startsWith("http") ? path : BASE + path, options);
window.WebSocket = RealWebSocket;  // a real socket, so the live log is genuinely tested
window.confirm = () => true;  // jsdom has no confirm(); accept every confirming action
window.localStorage.clear();

const failures = [];
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : "  <- " + detail}`);
  if (!ok) failures.push(name);
};
const settle = (ms = 400) => new Promise((r) => setTimeout(r, ms));

window.eval(js);
await settle();

// The USB LED is a pulse, not a state, so watch for it rather than sampling.
let usbFlashes = 0;
new window.MutationObserver((records) => {
  for (const r of records) {
    if (r.target.dataset?.led === "USB" && r.target.classList.contains("led--flash")) usbFlashes++;
  }
}).observe(window.document.body, {
  subtree: true, attributes: true, attributeFilter: ["class"],
});

const $ = (id) => window.document.getElementById(id);

// --- before connecting
check("welcome screen is shown", !$("welcome").hidden);
check("panel is hidden", $("panel").hidden);
check("status reads not connected", $("status-text").textContent === "Not connected");
const options = [...$("port-select").options].map((o) => o.textContent);
check("port picker offers the simulated device", options.some((o) => o.includes("simulated-v3")), options.join("|"));
check("welcome offers a simulated board", !!$("connect-simulated"));
check("nav lists every panel plus the guide", $("nav").children.length === 9, `${$("nav").children.length}`);

// --- connect
$("connect").click();
await settle(600);
check("welcome hidden after connecting", $("welcome").hidden);
check("panel visible after connecting", !$("panel").hidden);
check("status shows the device", /SIMULATED Bus Pirate v3/.test($("status-text").textContent), $("status-text").textContent);
check("recipe strip appeared", !$("recipes").hidden && $("recipes").children.length >= 8, `${$("recipes").children.length}`);

// --- USB indicator
check("USB indicator names the port", /USB: simulated-v3/.test($("usb").textContent), $("usb").textContent);

// --- the indicator LEDs, inferred from what we have asked the board to do
const leds = () => [...$("leds").children]
  .map((n) => `${n.dataset.led}:${n.classList.contains("led--on") ? "on" : "off"}`)
  .join(" ");
check("LED strip names all four LEDs",
  $("leds") && [...$("leds").children].map((n) => n.dataset.led).join(",") === "PWR,USB,MODE,VREG",
  $("leds") ? leds() : "no #leds element");
check("PWR and MODE light up once connected", /PWR:on/.test(leds()) && /MODE:on/.test(leds()), leds());
check("VREG stays dark until the supplies are switched on", /VREG:off/.test(leds()), leds());
check("USB is not steadily lit — it only flashes on traffic", /USB:off/.test(leds()), leds());

// --- the variant switch
check("variant selector offers every board",
  $("variant") && [...$("variant").options].map((o) => o.value).join(",") === "auto,v3,v4,bitpirate",
  $("variant") ? [...$("variant").options].map((o) => o.value).join(",") : "no #variant");
check("no mismatch warning while following detection", $("variant-warning").hidden);

// --- I2C panel
const navButtons = [...$("nav").children];
navButtons.find((b) => b.textContent === "I2C").click();
await settle(200);
const panelText = $("panel").textContent;
check("I2C panel renders its blurb", panelText.includes("Two wires, many devices"));
check("wiring block names SDA", panelText.includes("SDA"));
check("cable caveat is shown", panelText.includes("SparkFun"));
check("wiring swatch has a colour", $("panel").querySelector(".swatch").getAttribute("style").includes("background"));

// --- hook-up diagram: the board photo with this panel's pins ringed
const boardSvg = $("panel").querySelector(".card-img--board");
check("the board photo is drawn", boardSvg !== null);
check("board photo is the bundled one",
  boardSvg && boardSvg.querySelector("image").getAttribute("href") === "/static/img/board-v3.png");
const rings = boardSvg ? [...boardSvg.querySelectorAll("circle")] : [];
check("all ten header pins are marked", rings.length === 10, `${rings.length}`);
const callouts = boardSvg ? [...boardSvg.querySelectorAll(".boardlabel")].map((t) => t.textContent) : [];
check("I2C callouts name the target pins",
  callouts.includes("MOSI → SDA") && callouts.includes("CLK → SCL"), callouts.join(" | "));
check("only the pins this panel uses are called out",
  callouts.length === $("panel").querySelectorAll(".wiring tr").length,
  `${callouts.length} callouts vs ${$("panel").querySelectorAll(".wiring tr").length} wires`);
check("callouts sit outside the photo",
  boardSvg && boardSvg.getAttribute("viewBox").startsWith("-"),
  boardSvg && boardSvg.getAttribute("viewBox"));
const ledMarks = boardSvg ? [...boardSvg.querySelectorAll("rect.led")] : [];
check("all four LEDs are drawn on the board photo", ledMarks.length === 4, `${ledMarks.length}`);
check("the LEDs sit along the top edge of the photo",
  ledMarks.every((r) => Number(r.getAttribute("y")) < 120), ledMarks.map((r) => r.getAttribute("y")).join(","));
check("the board photo says the LED states are inferred",
  $("panel").textContent.includes("no command that reads the LEDs back"));

$("variant").value = "v4";
$("variant").dispatchEvent(new window.Event("change"));
await settle(600);
check("switching to v4 redraws the diagram with the v4 board",
  $("panel").querySelector(".card-img--board image").getAttribute("href") === "/static/img/board-v4.jpg",
  $("panel").querySelector(".card-img--board image").getAttribute("href"));
check("the v4 header shows twelve pins",
  $("panel").querySelectorAll(".card-img--board circle").length === 12,
  `${$("panel").querySelectorAll(".card-img--board circle").length}`);
// Regression check: the caption used to read the DETECTED variant rather
// than the effective one, so it kept saying "Bus Pirate v3" under a v4
// photo whenever an override was active.
const v4Captions = [...$("panel").querySelectorAll(".caption")].map((p) => p.textContent).join(" | ");
check("the caption under the v4 photo names the v4 board, not v3",
  v4Captions.includes("Bus Pirate v4.0") && !v4Captions.includes("Bus Pirate v3.6"),
  v4Captions);
check("overriding onto the wrong board warns", !$("variant-warning").hidden);
$("variant").value = "v3";
$("variant").dispatchEvent(new window.Event("change"));
await settle(600);
check("an override that agrees with the hardware does not warn",
  $("variant-warning").hidden, `warning text: ${$("variant-warning").textContent}`);
$("variant").value = "auto";
$("variant").dispatchEvent(new window.Event("change"));
await settle(600);
check("returning to auto clears the warning", $("variant-warning").hidden);

const cards = $("panel").querySelectorAll(".card-img:not(.card-img--board)");
check("both reference cards are drawn", cards.length === 2, `${cards.length}`);
const images = [...cards].map((c) => c.querySelector("image").getAttribute("href"));
check("cards use the bundled artwork", images.join(",") === "/static/img/refcard.png,/static/img/seeed-cable.png", images.join(","));
const marks = cards[0].querySelectorAll("rect");
check("the I2C column is marked on the card", marks.length >= 3, `${marks.length}`);
check("the credit is shown", $("panel").textContent.includes("Dangerous Prototypes"));
// CLK is purple: the firmware's own pin table calls it PU, and a real
// cable's CLK lead is purple — the pink once sampled from the cable card
// image was the scan, not the wire.
check("cable colours are the corrected ones",
  $("panel").querySelector(".swatch").getAttribute("style").includes("#9b59d6"),
  $("panel").querySelector(".swatch").getAttribute("style"));

const scan = $("panel").querySelector('[data-action="scan"]');
check("scan form has three inputs", scan.querySelectorAll("input,select").length === 3);
check("power and pull-ups start unticked",
  !scan.querySelector('[name="power"]').checked && !scan.querySelector('[name="pullups"]').checked);
scan.querySelector('[name="power"]').checked = true;
scan.querySelector("button").click();
await settle(800);
const scanText = scan.querySelector(".result").textContent;
check("scan found 0x50 and 0x68", scanText.includes("0x50") && scanText.includes("0x68"), scanText.slice(0, 80));
check("scan names the EEPROM", scanText.includes("24Cxx EEPROM"));
check("the MODE LED is still lit in a bus mode", /MODE:on/.test(leds()), leds());
check("the VREG LED follows the supplies the scan switched on", /VREG:on/.test(leds()), leds());
check("the USB LED flashed while the scan was talking to the board",
  usbFlashes > 0, `${usbFlashes} flashes seen`);
const boardLitCount = () =>
  [...$("panel").querySelectorAll(".card-img--board rect.led")]
    .filter((r) => r.classList.contains("led--on")).length;
check("the LEDs on the board photo keep up with the status strip",
  boardLitCount() === 3, `${boardLitCount()} of 3 lit on the photo`);

// --- Read the sensors: one click, raw bytes beside their translation
const sensorsForm = $("panel").querySelector('[data-action="read_sensors"]');
check("there is a one-click Read the sensors button", !!sensorsForm);
sensorsForm.querySelector("button").click();
await settle(800);
const sensorsTable = sensorsForm.querySelector(".result table");
check("Read the sensors lists raw bytes and what they mean",
  !!sensorsTable && sensorsTable.textContent.includes("Raw bytes") && sensorsTable.textContent.includes("What it means"),
  sensorsForm.querySelector(".result").textContent.slice(0, 120));
check("chips it does not know are called not recognised, not guessed at",
  sensorsTable && sensorsTable.textContent.includes("not recognised"));

// --- hex rendering
const reg = $("panel").querySelector('[data-action="read_register"]');
reg.querySelector("button").click();
await settle(600);
const hex = reg.querySelector(".hexdump");
check("register read renders a hexdump", !!hex, reg.querySelector(".result").textContent.slice(0, 80));
check("hexdump has an offset column", hex && hex.textContent.startsWith("000000"), hex && hex.textContent.slice(0, 20));
reg.querySelector('[name="show"]').value = "dec";
reg.querySelector("button").click();
await settle(600);
const decTable = reg.querySelector(".result table");
check("Show as decimal renders a table", !!decTable && decTable.textContent.includes("Decimal"),
  reg.querySelector(".result").textContent.slice(0, 80));
reg.querySelector('[name="show"]').value = "hex";

// --- an error must be a sentence, not a traceback
const write = $("panel").querySelector('[data-action="write"]');
write.querySelector('[name="address"]').value = "0x11";
write.querySelector("button").click();
await settle(600);
const writeMsg = write.querySelector(".result").textContent;
check("a NACK renders as a plain sentence", writeMsg.includes("did not acknowledge"), writeMsg.slice(0, 80));
check("no traceback leaks to the UI", !writeMsg.includes("Traceback"));

// --- traffic log
check("traffic log received frames", $("log-lines").children.length > 0, `${$("log-lines").children.length}`);
check("log counts frames", /frames/.test($("log-count").textContent), $("log-count").textContent);

// --- SPI panel + table/kv rendering
navButtons.find((b) => b.textContent === "SPI").click();
await settle(200);
const jedec = $("panel").querySelector('[data-action="jedec_id"]');
jedec.querySelector("button").click();
await settle(600);
check("SPI identify renders a key/value table", jedec.querySelector("table.data") !== null);
check("SPI identify shows the raw id", jedec.querySelector(".result").textContent.includes("a5 a5 a5"));

// --- pins panel renders pin tiles
navButtons.find((b) => b.textContent === "Pins & power").click();
await settle(200);
// The supplies get a switch of their own: one click, and it says which way
// it is. Found on a real v3 — the only control used to be a checkbox that did
// nothing until a separate "Set the pins" button was pressed.
const switchButton = () =>
  $("panel").querySelector('[data-action="supplies"] button');
const actionOrder = [...$("panel").querySelectorAll("[data-action]")].map((a) => a.dataset.action);
check("the supplies switch comes first on Pins & power", actionOrder[0] === "supplies", actionOrder.join(","));
const vregLit = () => $("leds").querySelector('[data-led="VREG"]').classList.contains("led--on");
const saysOn = () => /^On — switch off$/.test(switchButton().textContent);
const saysOff = () => /^Off — switch on$/.test(switchButton().textContent);
check("the switch says which way the supplies are, and agrees with VREG",
  (saysOn() && vregLit()) || (saysOff() && !vregLit()), switchButton().textContent);
const wasOn = saysOn();
switchButton().click();
await settle(600);
check("one click flips the supplies, and the switch and VREG both follow",
  wasOn ? saysOff() && !vregLit() : saysOn() && vregLit(), switchButton().textContent);
if (!saysOn()) {
  switchButton().click();
  await settle(600);
}
check("the switch can turn the supplies on", saysOn() && vregLit(), switchButton().textContent);

const setPins = $("panel").querySelector('[data-action="set_pins"]');
check("the pin card has no supplies box — the switch owns them",
  setPins.querySelector('[name="power"]') === null);
check("the pin card's button says what it does",
  setPins.querySelector("button").textContent === "Apply to the board",
  setPins.querySelector("button").textContent);
check("the pin card says nothing happens until Apply",
  /nothing changes/i.test(setPins.textContent));
setPins.querySelector("button").click();
await settle(600);
const pinTiles = setPins.querySelectorAll(".pin");
check("pins render as tiles", pinTiles.length === 7, `${pinTiles.length}`);
check("applying the pins leaves the supplies on",
  [...pinTiles].some((p) => p.textContent === "power high"));

switchButton().click();
await settle(600);
check("and one more click switches them off", saysOff() && !vregLit(), switchButton().textContent);

// --- a live sniffer takes the port and streams decoded events
navButtons.find((b) => b.textContent === "I2C").click();
await settle(200);
const sniff = $("panel").querySelector('[data-action="sniff"]');
sniff.querySelector("button").click();
await settle(1200);
const pane = sniff.querySelector(".stream");
check("sniffer opens a live pane", pane !== null);
check("sniffer pane explains the notation", /START|start/.test(pane.textContent), pane.textContent.slice(0, 60));
check("sniffer decodes events", pane.querySelectorAll(".tok").length > 0, `${pane ? pane.querySelectorAll(".tok").length : 0}`);
check("decoded tokens include a START", [...pane.querySelectorAll(".tok")].some((t) => t.textContent === "START"));
check("header says a sniffer is running", /sniffer running/.test($("status-text").textContent), $("status-text").textContent);

// other actions must be refused while it holds the port
const scanAgain = $("panel").querySelector('[data-action="scan"]');
scanAgain.querySelector("button").click();
await settle(600);
check("other actions are refused while sniffing",
  /has the port/.test(scanAgain.querySelector(".result").textContent),
  scanAgain.querySelector(".result").textContent.slice(0, 60));

pane.querySelector("button").click();
await settle(1500);
check("stopping reports the totals", /events in/.test(pane.textContent), pane.textContent.slice(0, 80));
check("header clears after stopping", !/sniffer running/.test($("status-text").textContent));
scanAgain.querySelector("button").click();
await settle(900);
check("the device works again after a sniff",
  scanAgain.querySelector(".result").textContent.includes("0x50"),
  scanAgain.querySelector(".result").textContent.slice(0, 60));

// --- the board's own terminal, opened as an input-carrying stream, now on
// its own Terminal panel (moved off Connection so open/type/stop are one
// group in one place)
navButtons.find((b) => b.textContent === "Terminal").click();
await settle(200);
check("send_keys has no automatic form on the Terminal panel — only the "
  + "console's typing surface drives it",
  $("panel").querySelector('[data-action="send_keys"]') === null);
const term = $("panel").querySelector('[data-action="open_terminal"]');
term.querySelector("button").click();
await settle(900);
// Opening it re-renders the whole panel from state (see app.js renderPanel):
// the pane is the panel's only content now, so re-query from #panel rather
// than the (possibly now-detached) `term` node.
const termPane = $("panel").querySelector(".stream");
check("opening the terminal starts a live pane", termPane !== null);
check("the terminal pane offers an input line",
  termPane && termPane.querySelector(".stream__input") !== null);
check("Stop is the first control in the pane — nothing else on this panel",
  termPane && termPane.querySelector("button").textContent === "Stop");

// While the board's own terminal is open its commands drive MODE and VREG,
// which the dashboard cannot see: the strip must say "unknown", not guess.
const stripLed = (name) => $("leds").querySelector(`[data-led="${name}"]`);
check("MODE and VREG read as unknown while the terminal is open",
  ["MODE", "VREG"].every((n) => stripLed(n).classList.contains("led--unknown")
    && !stripLed(n).classList.contains("led--on")
    && /unknown/.test(stripLed(n).title)),
  ["MODE", "VREG"].map((n) => `${n}: ${stripLed(n).className} / ${stripLed(n).title}`).join(" | "));
check("PWR is still shown as known and lit",
  stripLed("PWR").classList.contains("led--on") && !stripLed("PWR").classList.contains("led--unknown"));

// A panel with no wiring card used to hand `null` to replaceChildren(), which,
// unlike el(), prints it: the Terminal panel read "null" under its blurb.
const strayNull = () =>
  [...$("panel").childNodes].some((n) => n.nodeType === 3 && n.textContent.trim() === "null");
check("nothing on the Terminal panel reads a stray 'null'", !strayNull());

const line = termPane.querySelector(".stream__input");
const consoleText = () => {
  const out = $("panel").querySelector(".stream__console");
  return out ? out.textContent : "";
};
const prompts = () => (consoleText().match(/HiZ>/g) || []).length;

// Every key goes to the board as it is typed, the way `screen` does it —
// nothing is batched into a line and nothing is appended. Record what the
// page sends so each check can see the exact keys.
const sent = [];
const realFetch = window.fetch;
window.fetch = (path, options) => {
  if (options && options.body && options.body.includes('"send_keys"')) {
    sent.push(JSON.parse(options.body).params.keys);
  }
  return realFetch(path, options);
};
const sentSince = (mark) => sent.slice(mark).join("");
// What typing a printable key does to a text field: the character lands,
// then an input event says so.
const typeKeys = (field, text) => {
  for (const ch of text) {
    field.value += ch;
    field.dispatchEvent(new window.InputEvent("input", { data: ch, inputType: "insertText", bubbles: true }));
  }
};
const pressKey = (field, init) =>
  field.dispatchEvent(new window.KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init }));
const enter = (field) => pressKey(field, { key: "Enter", code: "Enter" });

check("there is no Send button — keys go as they are typed",
  ![...termPane.querySelectorAll("button")].some((b) => b.textContent === "Send"));

let mark = sent.length;
typeKeys(line, "?");
enter(line);
await settle(900);
check("typing ? then Return sends exactly those two keys",
  sentSince(mark) === "?\r", JSON.stringify(sentSince(mark)));
check("the board's reply is shown as text, the way a terminal shows it",
  consoleText().includes("General commands"), JSON.stringify(consoleText().slice(0, 120)));
check("what you type appears through the board's own echo",
  consoleText().includes("?\nGeneral commands"), JSON.stringify(consoleText().slice(0, 120)));
check("the console shows no hex tokens",
  termPane.querySelectorAll(".tok").length === 0, `${termPane.querySelectorAll(".tok").length}`);
check("the typing surface stays empty — the console is the display",
  line.value === "", JSON.stringify(line.value));
check("the field is not disabled while idle", !line.disabled);

// Found on a real v3: a line-based input answered "Space to continue" AND
// "Any key to exit" with one line, because Enter was appended. A lone key
// must go alone.
mark = sent.length;
typeKeys(line, " ");
await settle(600);
check("a single space goes out as a single space, with no Enter after it",
  sentSince(mark) === " ", JSON.stringify(sentSince(mark)));

// Return on its own is how you ask a Bus Pirate for a fresh prompt.
const promptsBefore = prompts();
mark = sent.length;
enter(line);
await settle(900);
check("Return alone sends a CR and gets a fresh prompt",
  sentSince(mark) === "\r" && prompts() > promptsBefore,
  `${JSON.stringify(sentSince(mark))}, prompts ${promptsBefore} -> ${prompts()}`);

// Backspace goes to the board, whose BS-space-BS echo the pane applies.
mark = sent.length;
typeKeys(line, "ab");
pressKey(line, { key: "Backspace", code: "Backspace" });
await settle(900);
check("Backspace is sent as a backspace",
  sentSince(mark) === "ab\b", JSON.stringify(sentSince(mark)));
check("the pane applies the board's backspace echo",
  consoleText().endsWith("a") && !consoleText().includes("\b"),
  JSON.stringify(consoleText().slice(-20)));
enter(line);  // finish the half-typed line on the board
await settle(600);

// ⌘ shortcuts belong to the window — copy must never type into the board.
mark = sent.length;
pressKey(line, { key: "c", code: "KeyC", metaKey: true });
await settle(300);
check("⌘C sends nothing to the board", sentSince(mark) === "", JSON.stringify(sentSince(mark)));

// A dead key (the ~ on a Swiss or German layout) is composed: nothing may go
// out until the character lands, and one Return must then send it and the
// CR. WebKit's order — the app's own window, recorded on a Swiss layout
// (⌥N, then Return): the composing input events, compositionend, then a
// Return whose `key` is the committed text glued to a CR ("~\r"), keyCode
// 192. Only `code` still says Enter.
mark = sent.length;
line.dispatchEvent(new window.CompositionEvent("compositionstart", { data: "", bubbles: true }));
line.value = "~";
line.dispatchEvent(new window.InputEvent("input",
  { data: "~", inputType: "insertCompositionText", isComposing: true, bubbles: true }));
check("nothing is sent while the dead key is still composing",
  sentSince(mark) === "", JSON.stringify(sentSince(mark)));
line.dispatchEvent(new window.InputEvent("input",
  { data: "~", inputType: "insertFromComposition", isComposing: true, bubbles: true }));
line.dispatchEvent(new window.CompositionEvent("compositionend", { data: "~", bubbles: true }));
pressKey(line, { key: "~\r", code: "Enter", keyCode: 192 });
await settle(900);
check("⌥N then one Return sends ~ and a CR (WebKit's order)",
  sentSince(mark) === "~\r", JSON.stringify(sentSince(mark)));
check("the field is empty again after the composed key", line.value === "", JSON.stringify(line.value));

// Chrome's order: the Return arrives while still composing, then the
// composition ends.
mark = sent.length;
line.dispatchEvent(new window.CompositionEvent("compositionstart", { data: "", bubbles: true }));
line.value = "~";
line.dispatchEvent(new window.InputEvent("input",
  { data: "~", inputType: "insertCompositionText", isComposing: true, bubbles: true }));
pressKey(line, { key: "Enter", code: "Enter", isComposing: true });
check("a Return during composition sends nothing yet",
  sentSince(mark) === "", JSON.stringify(sentSince(mark)));
line.dispatchEvent(new window.CompositionEvent("compositionend", { data: "~", bubbles: true }));
await settle(900);
check("once the ~ lands, it and the CR go out (Chrome's order)",
  sentSince(mark) === "~\r", JSON.stringify(sentSince(mark)));

// Keys typed faster than the board is written to must arrive in order.
mark = sent.length;
typeKeys(line, "abc");
enter(line);
await settle(900);
check("keys typed in a burst arrive in order", sentSince(mark) === "abc\r", JSON.stringify(sentSince(mark)));

check("the field does not autocorrect, autocapitalise or spellcheck commands",
  line.getAttribute("autocapitalize") === "off"
    && line.getAttribute("autocorrect") === "off"
    && line.getAttribute("spellcheck") === "false",
  `${line.getAttribute("autocapitalize")}/${line.getAttribute("autocorrect")}/${line.getAttribute("spellcheck")}`);

// --- the regression this fix exists for: leaving the Terminal panel used to
// destroy the live pane outright — the header still said "running", but the
// Stop button and console were gone with no way back. The pane must be
// derivable from state, not just from the action result that first created
// it.
navButtons.find((b) => b.textContent === "I2C").click();
await settle(200);
check("navigating away leaves the stream running (header still says so)",
  /Board terminal running/.test($("status-text").textContent), $("status-text").textContent);
check("the pane is gone from the DOM while looking at another panel",
  $("panel").querySelector(".stream") === null);
navButtons.find((b) => b.textContent === "Terminal").click();
await settle(200);
const revivedPane = $("panel").querySelector(".stream");
check("returning to the Terminal panel shows the live pane again", revivedPane !== null);
const revivedStop = revivedPane && revivedPane.querySelector("button");
check("the revived pane has a working Stop button",
  revivedStop !== null && revivedStop.textContent === "Stop" && !revivedStop.disabled);
check("the revived pane still offers the input line",
  revivedPane && revivedPane.querySelector(".stream__input") !== null);

// The revived pane must be live, not a static leftover: typing into it
// still reaches the board.
const revivedLine = revivedPane.querySelector(".stream__input");
const revivedPromptsBefore = prompts();
typeKeys(revivedLine, "?");
enter(revivedLine);
await settle(900);
check("the revived pane keeps receiving output, as text",
  prompts() > revivedPromptsBefore, `${revivedPromptsBefore} -> ${prompts()}`);
check("the revived pane reads no stray 'null' either", !strayNull());

window.fetch = realFetch;
revivedPane.querySelector("button").click();  // Stop — first button, same as the sniffer pane
await settle(900);
check("the input line goes away when the stream stops",
  $("panel").querySelector(".stream__input") === null);
check("navigating back after stopping shows no stale pane",
  (() => {
    navButtons.find((b) => b.textContent === "I2C").click();
    navButtons.find((b) => b.textContent === "Terminal").click();
    return $("panel").querySelector(".stream") === null;
  })());

// --- the guide, rendered in the UI
// Open it from the I2C panel: the guide follows whichever panel you are on.
navButtons.find((b) => b.textContent === "I2C").click();
await settle(200);
const guideButton = [...$("nav").children].find((b) => b.textContent === "Guide");
guideButton.click();
await settle(700);
check("guide replaces the panel", !$("guide").hidden && $("panel").hidden);
check("guide renders a heading", $("guide").querySelector("h1") !== null);
check("guide renders the I2C page for the I2C panel",
  /I2C/.test($("guide").querySelector("h1").textContent), $("guide").textContent.slice(0, 60));
check("guide renders tables", $("guide").querySelector("table") !== null);
check("guide shows the corrected cable colours",
  /grey/.test($("guide").textContent) && /purple/.test($("guide").textContent),
  $("guide").textContent.slice(0, 80));
const picker = $("guide").querySelector("select");
check("guide lists every page", picker.options.length >= 13, `${picker.options.length}`);
$("guide").querySelector(".btn").click();
await settle(300);
check("back returns to the dashboard", $("guide").hidden && !$("panel").hidden);

// --- a connection changed somewhere else. Found with a real v4: another
// client connected the board, and a window showing "Not connected" never
// looked again — its status check only ran while it thought it was connected,
// and only repainted the header.
const serverSide = (action, params = {}) =>
  fetch(`${BASE}/api/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ panel: "connection", action, params }),
  });
await serverSide("disconnect");
await settle(6000);
check("a window notices a disconnect made elsewhere",
  !$("welcome").hidden && $("panel").hidden, $("status-text").textContent);
await serverSide("connect", { port: "simulated-v4" });
await settle(6000);
check("a window showing Not connected notices a connect made elsewhere",
  $("welcome").hidden && !$("panel").hidden && /v4/.test($("status-text").textContent),
  $("status-text").textContent);

// --- an ESP32 Bit Pirate: no probe cable, no supplies, DevKit pins
await serverSide("connect", { port: "simulated-bitpirate" });
await settle(6000);
check("the Bit Pirate is named in the status",
  /ESP32 Bit Pirate/.test($("status-text").textContent), $("status-text").textContent);
const bitNav = [...$("nav").children].map((b) => b.textContent);
check("panels a Bit Pirate cannot drive are not in the nav",
  bitNav.includes("I2C") && !bitNav.includes("1-Wire") && !bitNav.includes("Pins & power"),
  bitNav.join("|"));
[...$("nav").children].find((b) => b.textContent === "I2C").click();
await settle(300);
const bitBoard = $("panel").querySelector(".card-img--board");
check("the I2C diagram is the DevKit",
  bitBoard && bitBoard.querySelector("image").getAttribute("href") === "/static/img/board-bitpirate.svg",
  bitBoard ? bitBoard.querySelector("image").getAttribute("href") : "no board");
const bitCallouts = bitBoard ? [...bitBoard.querySelectorAll(".boardlabel")].map((t) => t.textContent) : [];
check("its callouts name the GPIOs", bitCallouts.includes("GPIO7 → SCL") && bitCallouts.includes("GPIO6 → SDA"),
  bitCallouts.join("|"));
check("no Bus Pirate reference cards or cable caveat for it",
  $("panel").querySelectorAll(".card-img").length === 1 && !$("panel").textContent.includes("SparkFun"),
  `${$("panel").querySelectorAll(".card-img").length}`);
check("no colour swatches in its wiring table", $("panel").querySelector(".wiring .swatch") === null);
check("the scan form has no power switch",
  $("panel").querySelector('[data-action="scan"] [name="power"]') === null);

// Its terminal redraws the line on every key: "\r<prompt><line>ESC[K". Found
// in the simulator on 2026-09-28 — the pane printed each redraw after the
// last, with ESC as U+FFFD: "HIZ> m�[KHIZ> mo�[K…".
[...$("nav").children].find((b) => b.textContent === "Terminal").click();
await settle(300);
$("panel").querySelector('[data-action="open_terminal"] button').click();
await settle(900);
const bitLine = $("panel").querySelector(".stream__input");
typeKeys(bitLine, "mode");
enter(bitLine);
await settle(1200);
check("the Bit Pirate's line redraw shows as one clean line",
  consoleText().includes("HIZ> mode\n") && !consoleText().includes("HIZ> HIZ>")
    && !consoleText().includes("\ufffd") && !consoleText().includes("[K"),
  JSON.stringify(consoleText().slice(0, 160)));
check("mode on its own shows the numbered menu",
  consoleText().includes("Select mode:") && consoleText().trimEnd().endsWith("Mode Number >"),
  JSON.stringify(consoleText().slice(-80)));
typeKeys(bitLine, "2");
enter(bitLine);
await settle(900);
$("panel").querySelector(".stream button").click();  // Stop
await settle(1500);

console.log(failures.length ? `\n${failures.length} FAILED` : "\nall frontend checks passed");
process.exit(failures.length ? 1 : 0);
