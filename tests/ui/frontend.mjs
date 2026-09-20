/* Loads the real index.html + app.js in jsdom and drives it against the
   running demo server, so the rendering path is genuinely exercised. */
import fs from "node:fs";
import { JSDOM } from "jsdom";
import { WebSocket as RealWebSocket } from "ws";

const BASE = "http://127.0.0.1:8765";
const ROOT = new URL("../../buspirate/web/static/", import.meta.url).pathname;
const html = fs.readFileSync(`${ROOT}/index.html`, "utf8");
const js = fs.readFileSync(`${ROOT}/app.js`, "utf8");

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
window.localStorage.clear();

const failures = [];
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${ok ? "" : "  <- " + detail}`);
  if (!ok) failures.push(name);
};
const settle = (ms = 400) => new Promise((r) => setTimeout(r, ms));

window.eval(js);
await settle();

const $ = (id) => window.document.getElementById(id);

// --- before connecting
check("welcome screen is shown", !$("welcome").hidden);
check("panel is hidden", $("panel").hidden);
check("status reads not connected", $("status-text").textContent === "Not connected");
const options = [...$("port-select").options].map((o) => o.textContent);
check("port picker offers the simulated device", options.some((o) => o.includes("fake")), options.join("|"));
check("nav lists every panel plus the guide", $("nav").children.length === 8, `${$("nav").children.length}`);

// --- connect
$("connect").click();
await settle(600);
check("welcome hidden after connecting", $("welcome").hidden);
check("panel visible after connecting", !$("panel").hidden);
check("status shows the device", /SIMULATED Bus Pirate v3/.test($("status-text").textContent), $("status-text").textContent);
check("recipe strip appeared", !$("recipes").hidden && $("recipes").children.length >= 8, `${$("recipes").children.length}`);

// --- USB indicator
check("USB indicator names the port", /USB: fake/.test($("usb").textContent), $("usb").textContent);

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

const cards = $("panel").querySelectorAll(".card-img:not(.card-img--board)");
check("both reference cards are drawn", cards.length === 2, `${cards.length}`);
const images = [...cards].map((c) => c.querySelector("image").getAttribute("href"));
check("cards use the bundled artwork", images.join(",") === "/static/img/refcard.png,/static/img/seeed-cable.png", images.join(","));
const marks = cards[0].querySelectorAll("rect");
check("the I2C column is marked on the card", marks.length >= 3, `${marks.length}`);
check("the credit is shown", $("panel").textContent.includes("Dangerous Prototypes"));
check("cable colours are the corrected ones",
  $("panel").querySelector(".swatch").getAttribute("style").includes("#ff85ff"),
  $("panel").querySelector(".swatch").getAttribute("style"));

const scan = $("panel").querySelector('[data-action="scan"]');
check("scan form has three inputs", scan.querySelectorAll("input,select").length === 3);
scan.querySelector("button").click();
await settle(800);
const scanText = scan.querySelector(".result").textContent;
check("scan found 0x50 and 0x68", scanText.includes("0x50") && scanText.includes("0x68"), scanText.slice(0, 80));
check("scan names the EEPROM", scanText.includes("24Cxx EEPROM"));

// --- hex rendering
const reg = $("panel").querySelector('[data-action="read_register"]');
reg.querySelector("button").click();
await settle(600);
const hex = reg.querySelector(".hexdump");
check("register read renders a hexdump", !!hex, reg.querySelector(".result").textContent.slice(0, 80));
check("hexdump has an offset column", hex && hex.textContent.startsWith("000000"), hex && hex.textContent.slice(0, 20));

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
const setPins = $("panel").querySelector('[data-action="set_pins"]');
setPins.querySelector('[name="power"]').checked = true;
setPins.querySelector("button").click();
await settle(600);
const pinTiles = setPins.querySelectorAll(".pin");
check("pins render as tiles", pinTiles.length === 7, `${pinTiles.length}`);
check("power reads high", [...pinTiles].some((p) => p.textContent === "power high"));

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
  /grey/.test($("guide").textContent) && /pink/.test($("guide").textContent),
  $("guide").textContent.slice(0, 80));
const picker = $("guide").querySelector("select");
check("guide lists every page", picker.options.length >= 13, `${picker.options.length}`);
$("guide").querySelector(".btn").click();
await settle(300);
check("back returns to the dashboard", $("guide").hidden && !$("panel").hidden);

console.log(failures.length ? `\n${failures.length} FAILED` : "\nall frontend checks passed");
process.exit(failures.length ? 1 : 0);
