/* The dashboard renders itself from /api/state. It knows nothing about any
   particular protocol: panels, actions, parameters and wiring all arrive as
   data, so adding a protocol to the Python side needs no change here. */

const $ = (id) => document.getElementById(id);

const state = {
  status: { connected: false },
  panels: [],
  cable: [],
  cableCaveat: "",
  refcard: null,
  cableCard: null,
  current: localStorage.getItem("bp.panel") || null,
  guide: { open: false, pages: [], page: null },
  busy: false,
};

const SVG_NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(child));
  }
  return node;
}

/* ---------------------------------------------------------------- helpers */

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined) continue;
    node.append(child.nodeType ? child : document.createTextNode(child));
  }
  return node;
}

async function api(path, options) {
  const response = await fetch(path, options);
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error(`the server returned ${response.status}`);
  }
  if (body.ok === false) throw new Error(body.error || "something went wrong");
  return body;
}

/* ------------------------------------------------------------------ state */

async function loadState() {
  const data = await api("/api/state");
  state.status = data.status;
  state.panels = data.panels;
  state.cable = data.cable || [];
  state.cableCaveat = data.cable_caveat || "";
  state.refcard = data.refcard || null;
  state.cableCard = data.cable_card || null;
  if (!state.panels.some((p) => p.id === state.current)) {
    state.current = state.panels.length ? state.panels[0].id : null;
  }
  data.traffic.forEach(addLogLine);
  render();
}

function render() {
  renderStatus();
  renderNav();
  renderRecipes();
  const connected = state.status.connected;
  const guiding = state.guide.open;
  $("welcome").hidden = connected || guiding;
  $("panel").hidden = !connected || guiding;
  $("guide").hidden = !guiding;
  if (guiding) renderGuide();
  else if (connected) renderPanel();
}

function renderStatus() {
  const box = $("status");
  const s = state.status;
  box.className =
    "status " + (s.connected ? (s.simulated ? "status--sim" : "status--on") : "status--off");
  $("status-text").textContent = s.connected
    ? `${s.simulated ? "SIMULATED " : ""}${s.description}${s.mode ? " · " + s.mode : ""}`
    : "Not connected";
  renderUsb(s.usb || { attached: false });
}

function renderUsb(usb) {
  const box = $("usb");
  if (!usb.device) {
    box.className = "usb muted";
    box.textContent = "USB: no device";
    return;
  }
  const id = usb.usb_id ? ` [${usb.usb_id}]` : "";
  if (usb.attached) {
    box.className = "usb muted";
    box.textContent = `USB: ${usb.device}${id}`;
  } else {
    box.className = "usb usb--gone";
    box.textContent = `USB: ${usb.device} has gone away — unplugged?`;
  }
}

function renderNav() {
  const nav = $("nav");
  nav.replaceChildren(
    ...state.panels.map((panel) =>
      el("button", {
        text: panel.title,
        "aria-current": panel.id === state.current ? "true" : "false",
        onclick: () => {
          state.current = panel.id;
          state.guide.open = false;
          localStorage.setItem("bp.panel", panel.id);
          render();
        },
      })
    ),
    el("button", {
      text: "Guide",
      "aria-current": state.guide.open ? "true" : "false",
      onclick: () => openGuide(panelDoc() || "user-guide"),
    })
  );
}

function panelDoc() {
  const panel = state.panels.find((p) => p.id === state.current);
  return panel ? panel.doc : null;
}

function renderRecipes() {
  const strip = $("recipes");
  const recipes = [];
  for (const panel of state.panels) {
    for (const action of panel.actions) {
      if (action.recipe) recipes.push({ panel, action });
    }
  }
  strip.hidden = !state.status.connected || !recipes.length;
  strip.replaceChildren(
    ...recipes.map(({ panel, action }) =>
      el("button", {
        class: "btn btn--small",
        text: `${panel.title}: ${action.label}`,
        title: action.help || "",
        onclick: () => {
          state.current = panel.id;
          render();
          const form = document.querySelector(`[data-action="${action.name}"]`);
          if (form) {
            form.scrollIntoView({ block: "center", behavior: "smooth" });
            form.querySelector("button").focus();
          }
        },
      })
    )
  );
}

/* ------------------------------------------------------------------ panel */

function renderPanel() {
  const panel = state.panels.find((p) => p.id === state.current);
  if (!panel) return;
  const root = $("panel");
  root.replaceChildren(
    el("h1", { text: panel.title }),
    el("p", { class: "blurb", text: panel.blurb }),
    panel.wiring.length || panel.notes.length ? wiringCard(panel) : null,
    el("div", { class: "card" }, ...panel.actions.map((action) => actionBlock(panel, action)))
  );
}

function wiringCard(panel) {
  const rows = panel.wiring.map((wire) =>
    el(
      "tr",
      {},
      el("td", { class: "sig" }, el("span", { class: "swatch", style: `background:${cssColour(wire.colour)}` }), wire.signal),
      el("td", { class: "arrow", text: "→" }),
      el("td", { class: "sig", text: wire.target }),
      el("td", { class: "note", text: wire.note })
    )
  );
  return el(
    "div",
    { class: "card" },
    el("h2", { text: panel.wiring.length ? "How to hook it up" : "Before you start" }),
    panel.wiring.length ? hookupDiagram(panel) : null,
    rows.length ? el("table", { class: "wiring" }, ...rows) : null,
    panel.notes.length
      ? el("ul", { class: "notes" }, ...panel.notes.map((note) => el("li", { text: note })))
      : null,
    panel.doc
      ? el(
          "p",
          { class: "docslink" },
          el("button", { text: `Read the ${panel.title} guide`, onclick: () => openGuide(panel.doc) })
        )
      : null
  );
}

function cssColour(value) {
  return value || "transparent";
}

function actionBlock(panel, action) {
  const fields = el("div", { class: "fields" }, ...action.params.map(fieldFor));
  const output = el("div", { class: "result" });
  const button = el("button", {
    class: action.primary ? "btn btn--primary" : "btn",
    text: action.label,
  });
  const block = el(
    "div",
    { class: "action", "data-action": action.name },
    el("div", { class: "action__head" }, el("h3", { text: action.label })),
    action.help ? el("p", { class: "action__help", text: action.help }) : null,
    action.params.length ? fields : null,
    button,
    output
  );

  button.addEventListener("click", async () => {
    if (action.confirm && !window.confirm(action.confirm)) return;
    const params = {};
    for (const param of action.params) {
      const input = fields.querySelector(`[name="${param.name}"]`);
      params[param.name] = param.type === "bool" ? input.checked : input.value;
    }
    button.disabled = true;
    output.replaceChildren(el("p", { class: "muted", text: "Working…" }));
    if (action.long_running) output.append(progressBar());
    try {
      const body = await api("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ panel: panel.id, action: action.name, params }),
      });
      state.status = body.status;
      state.panels = body.panels;
      renderStatus();
      output.replaceChildren(renderResult(body.result));
    } catch (error) {
      output.replaceChildren(el("p", { class: "msg msg--warn", text: error.message }));
    } finally {
      button.disabled = false;
    }
  });
  return block;
}

function fieldFor(param) {
  if (param.type === "bool") {
    return el(
      "label",
      { class: "field field--bool", title: param.help },
      el("input", { type: "checkbox", name: param.name, checked: !!param.default }),
      el("span", { text: param.label })
    );
  }
  let input;
  if (param.type === "enum") {
    input = el(
      "select",
      { name: param.name },
      ...param.choices.map((choice) =>
        el("option", { value: choice.value, selected: choice.value === param.default }, choice.label)
      )
    );
  } else {
    const hex = param.type === "hex";
    input = el("input", {
      name: param.name,
      value: formatDefault(param),
      placeholder: param.placeholder || (hex ? "0x00" : ""),
      "data-mono": param.type === "bytes" || hex ? true : null,
      size: param.type === "bytes" || param.type === "text" ? 24 : 10,
    });
  }
  return el("label", { class: "field", title: param.help }, el("span", { text: param.label }), input);
}

function formatDefault(param) {
  if (param.default === null || param.default === undefined) return "";
  if (param.type === "hex" && typeof param.default === "number") {
    return "0x" + param.default.toString(16).toUpperCase().padStart(2, "0");
  }
  return String(param.default);
}

/* ---------------------------------------------------------------- results */

function renderResult(result) {
  if (!result) return el("p", { class: "msg", text: "Done." });
  const caption = result.caption ? el("p", { class: "caption", text: result.caption }) : null;
  const body = {
    text: () => el("p", { class: "msg msg--" + (result.tone || "info"), text: result.text }),
    hex: () => hexBlock(result.data, result.start || 0),
    table: () =>
      el(
        "table",
        { class: "data" },
        el("tr", {}, ...result.columns.map((c) => el("th", { text: c }))),
        ...result.rows.map((row) => el("tr", {}, ...row.map((cell) => el("td", { text: String(cell) }))))
      ),
    chips: () =>
      el(
        "div",
        { class: "chips" },
        ...result.items.map((item) =>
          el(
            "div",
            { class: "chip", title: item.detail || "" },
            el("b", { text: item.label }),
            item.sub ? el("div", { text: item.sub }) : null,
            item.detail ? el("div", { text: item.detail }) : null
          )
        )
      ),
    kv: () =>
      el(
        "table",
        { class: "data" },
        ...result.pairs.map(([k, v]) => el("tr", {}, el("th", { text: k }), el("td", { text: String(v) })))
      ),
    pins: () =>
      el(
        "div",
        { class: "pinrow" },
        ...Object.entries(result.state).map(([name, on]) =>
          el("span", { class: "pin " + (on ? "pin--on" : ""), text: `${name} ${on ? "high" : "low"}` })
        )
      ),
  }[result.render];
  return el("div", {}, caption, body ? body() : el("pre", { text: JSON.stringify(result, null, 2) }));
}

function hexBlock(bytes, start) {
  const lines = [];
  for (let offset = 0; offset < bytes.length; offset += 16) {
    const row = bytes.slice(offset, offset + 16);
    const hex = row.map((b) => b.toString(16).padStart(2, "0")).join(" ").padEnd(47, " ");
    const ascii = row.map((b) => (b >= 32 && b < 127 ? String.fromCharCode(b) : ".")).join("");
    lines.push(
      el(
        "div",
        {},
        el("span", { class: "off", text: (start + offset).toString(16).padStart(6, "0") + "  " }),
        hex + "  ",
        el("span", { class: "asc", text: ascii })
      )
    );
  }
  if (!lines.length) lines.push(el("div", { class: "off", text: "(no data)" }));
  return el("pre", { class: "hexdump" }, ...lines);
}

function progressBar() {
  const fill = el("i");
  const bar = el("div", { class: "progress" }, fill);
  bar.dataset.progress = "1";
  progressFill = fill;
  return bar;
}
let progressFill = null;

/* -------------------------------------------------------------- live feed */

let logPaused = false;
let logCount = 0;

function addLogLine(event) {
  if (event.type !== "traffic") return;
  const lines = $("log-lines");
  lines.append(
    el(
      "div",
      {},
      el("span", { class: "muted", text: event.at + "  " }),
      el("span", { class: event.direction, text: (event.direction === "tx" ? "->" : "<-") + "  " }),
      event.hex
    )
  );
  while (lines.childElementCount > 500) lines.firstElementChild.remove();
  logCount += 1;
  $("log-count").textContent = `${logCount} frames`;
  if ($("log-follow").checked) lines.scrollTop = lines.scrollHeight;
}

function connectFeed() {
  const socket = new WebSocket(`ws://${location.host}/ws`);
  socket.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.type === "traffic") addLogLine(event);
    if (event.type === "progress" && progressFill) {
      progressFill.style.width = `${(100 * event.done) / Math.max(1, event.total)}%`;
    }
  };
  socket.onclose = () => setTimeout(connectFeed, 1500);
}

/* ------------------------------------------------------------------ setup */

async function refreshPorts() {
  const select = $("port-select");
  try {
    const { ports } = await api("/api/ports");
    select.replaceChildren(el("option", { value: "" }, "Detect automatically"));
    for (const port of ports) {
      select.append(
        el("option", { value: port.device }, `${port.device}${port.note ? " — " + port.note : ""}${port.likely ? "  ✓" : ""}`)
      );
    }
  } catch (error) {
    $("welcome-error").hidden = false;
    $("welcome-error").textContent = error.message;
  }
}

$("connect").addEventListener("click", async () => {
  const error = $("welcome-error");
  error.hidden = true;
  $("connect").disabled = true;
  try {
    const body = await api("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        panel: "connection",
        action: "connect",
        params: { port: $("port-select").value },
      }),
    });
    state.status = body.status;
    state.panels = body.panels;
    render();
  } catch (exception) {
    error.hidden = false;
    error.textContent = exception.message;
  } finally {
    $("connect").disabled = false;
  }
});

$("refresh-ports").addEventListener("click", refreshPorts);
$("log-clear").addEventListener("click", () => {
  $("log-lines").replaceChildren();
  logCount = 0;
  $("log-count").textContent = "";
});
$("log-toggle").addEventListener("click", (event) => {
  const log = document.querySelector(".log");
  log.classList.toggle("collapsed");
  event.target.textContent = log.classList.contains("collapsed") ? "Show" : "Hide";
});

refreshPorts();
loadState();
connectFeed();

/* ------------------------------------------------- hook-up diagram */

/* The two Dangerous Prototypes reference cards, with this panel's connections
   marked on them. Using the project's own artwork means the colours and the
   per-bus pin names are the authoritative ones rather than a redrawing, and
   the overlay is computed from the panel's wiring, so a new panel gets its
   diagram for free. Geometry comes from the server, measured from the files. */

const SUPPLY_SIGNALS = new Set(["+3.3V", "+5V", "+5.0V"]);

function highlightedRows(panel) {
  const rows = new Set(panel.refcard_rows || []);
  for (const wire of panel.wiring) {
    rows.add(SUPPLY_SIGNALS.has(wire.signal) ? "supplies" : wire.signal);
  }
  return rows;
}

function markRect(x, y, w, h, { strong = false, colour = null } = {}) {
  return svg("rect", {
    x, y, width: w, height: h, rx: 3,
    fill: colour || "var(--accent)",
    "fill-opacity": strong ? 0.22 : 0.13,
    stroke: colour || "var(--accent)",
    "stroke-width": strong ? 2 : 1.25,
    "stroke-opacity": strong ? 0.95 : 0.6,
  });
}

function refcardDiagram(panel) {
  const card = state.refcard;
  if (!card) return null;
  const column = panel.refcard_column && card.columns[panel.refcard_column];
  const rows = highlightedRows(panel);
  const marks = [];

  // The protocol's whole column, from the header down through the CS row.
  if (column) {
    const top = card.rows.header[0];
    const bottom = card.rows.CS[1];
    marks.push(markRect(column[0], top, column[1] - column[0], bottom - top, { strong: true }));
  }

  // The signal-name cell of every row this panel actually uses.
  const [nameLeft, nameRight] = card.columns.signal;
  for (const [name, [top, bottom]] of Object.entries(card.rows)) {
    if (name === "header" || !rows.has(name)) continue;
    const full = ["AUX", "VPU", "ADC", "supplies", "GND"].includes(name);
    const right = full ? card.width - 8 : nameRight;
    marks.push(markRect(nameLeft, top, right - nameLeft, bottom - top,
      { colour: full ? "var(--good)" : null }));
  }

  return svg(
    "svg",
    { viewBox: `0 0 ${card.width} ${card.height}`, width: card.width, height: card.height,
      class: "card-img", role: "img",
      "aria-label": `Bus Pirate reference card, ${panel.title} column highlighted` },
    svg("image", { href: card.image, x: 0, y: 0, width: card.width, height: card.height }),
    ...marks
  );
}

function cableDiagram(panel) {
  const card = state.cableCard;
  if (!card) return null;
  const rows = highlightedRows(panel);
  const [bandTop, bandBottom] = card.band;
  const marks = [];
  for (const [signal, [left, right]] of Object.entries(card.swatches)) {
    const used = rows.has(SUPPLY_SIGNALS.has(signal) ? "supplies" : signal);
    if (!used) continue;
    marks.push(markRect(left - 3, bandTop - 4, right - left + 6, bandBottom - bandTop + 8,
      { strong: true }));
  }
  return svg(
    "svg",
    { viewBox: `0 0 ${card.width} ${card.height}`, width: card.width, height: card.height,
      class: "card-img", role: "img",
      "aria-label": `Probe cable colours, the wires ${panel.title} uses highlighted` },
    svg("image", { href: card.image, x: 0, y: 0, width: card.width, height: card.height }),
    ...marks
  );
}

function hookupDiagram(panel) {
  const board = state.status.variant === "v4" ? "Bus Pirate v4" : "Bus Pirate v3";
  const columnNote = panel.refcard_column
    ? `Highlighted: the ${panel.refcard_column} column — what each probe wire becomes on this bus.`
    : "Highlighted: the pins this panel drives.";
  return el(
    "div",
    { class: "diagram" },
    el("div", { class: "diagram__cards" }, refcardDiagram(panel), cableDiagram(panel)),
    el("p", { class: "caption", text: `${board} · ${columnNote}` }),
    el("p", { class: "caption", text: state.cableCaveat }),
    el("p", {
      class: "caption credit",
      text: "Reference cards: Dangerous Prototypes wiki (dangerousprototypes.com), CC BY-SA.",
    })
  );
}

/* ------------------------------------------------------------ guide */

async function openGuide(name) {
  state.guide.open = true;
  render();
  try {
    if (!state.guide.pages.length) {
      state.guide.pages = (await api("/api/docs")).pages;
    }
    const body = await api(`/api/docs/${name}`);
    state.guide.page = { name, markdown: body.markdown };
  } catch (error) {
    state.guide.page = { name, markdown: `# Guide\n\n${error.message}` };
  }
  renderGuide();
}

function renderGuide() {
  const root = $("guide");
  const page = state.guide.page;
  const picker = el(
    "select",
    {
      onchange: (event) => openGuide(event.target.value),
    },
    ...state.guide.pages.map((p) =>
      el("option", { value: p.name, selected: page && p.name === page.name }, p.title)
    )
  );
  const back = el("button", {
    class: "btn btn--small",
    text: "← Back to the dashboard",
    onclick: () => {
      state.guide.open = false;
      render();
    },
  });
  const body = el("div", { class: "guide__body" });
  body.innerHTML = page ? markdownToHtml(page.markdown) : "Loading…";
  body.querySelectorAll("a[data-doc]").forEach((link) =>
    link.addEventListener("click", (event) => {
      event.preventDefault();
      openGuide(link.dataset.doc);
    })
  );
  root.replaceChildren(el("div", { class: "guide__bar" }, back, picker), body);
  root.scrollTop = 0;
}

/* A deliberately small Markdown renderer: everything is HTML-escaped first,
   so only the markup added here can reach the page. */
function markdownToHtml(markdown) {
  const escape = (s) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const blocks = [];
  const lines = escape(markdown).split("\n");
  let index = 0;

  const inline = (text) =>
    text
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, (match, label, href) =>
        href.endsWith(".md")
          ? `<a href="#" data-doc="${href.replace(/\.md$/, "")}">${label}</a>`
          : `<a href="${href}" target="_blank" rel="noreferrer">${label}</a>`
      );

  const isTableRow = (line) => line.trim().startsWith("|") && line.trim().endsWith("|");
  const cells = (line) =>
    line.trim().slice(1, -1).split("|").map((cell) => cell.trim());

  while (index < lines.length) {
    const line = lines[index];

    if (line.startsWith("```")) {
      const code = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) code.push(lines[index++]);
      index += 1;
      blocks.push(`<pre><code>${code.join("\n")}</code></pre>`);
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      blocks.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      index += 1;
      continue;
    }
    if (/^(-{3,}|\*{3,})$/.test(line.trim())) {
      blocks.push("<hr>");
      index += 1;
      continue;
    }
    if (isTableRow(line) && isTableRow(lines[index + 1] || "") && /^[\s|:-]+$/.test(lines[index + 1])) {
      const head = cells(line);
      index += 2;
      const body = [];
      while (index < lines.length && isTableRow(lines[index])) body.push(cells(lines[index++]));
      blocks.push(
        `<table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead>` +
          `<tbody>${body
            .map((row) => `<tr>${row.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`)
            .join("")}</tbody></table>`
      );
      continue;
    }
    if (/^\s*[-*]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
      const ordered = /^\s*\d+\.\s+/.test(line);
      const items = [];
      while (index < lines.length && (/^\s*[-*]\s+/.test(lines[index]) || /^\s*\d+\.\s+/.test(lines[index]))) {
        let item = lines[index].replace(/^\s*(?:[-*]|\d+\.)\s+/, "");
        item = item.replace(/^\[([ x])\]\s*/, (m, mark) =>
          `<input type="checkbox" disabled ${mark === "x" ? "checked" : ""}>`
        );
        items.push(`<li>${inline(item)}</li>`);
        index += 1;
      }
      blocks.push(`<${ordered ? "ol" : "ul"}>${items.join("")}</${ordered ? "ol" : "ul"}>`);
      continue;
    }
    if (line.startsWith("&gt; ")) {
      const quote = [];
      while (index < lines.length && lines[index].startsWith("&gt; ")) quote.push(lines[index++].slice(5));
      blocks.push(`<blockquote>${inline(quote.join(" "))}</blockquote>`);
      continue;
    }
    if (line.trim() === "") {
      index += 1;
      continue;
    }
    const paragraph = [];
    while (index < lines.length && lines[index].trim() !== "" && !/^(#{1,4}\s|```|\s*[-*]\s|\s*\d+\.\s|\|)/.test(lines[index])) {
      paragraph.push(lines[index++]);
    }
    if (paragraph.length === 0) {
      // A line that begins a block we did not recognise — a stray table row,
      // say. Emit it verbatim and move on; never leave index unchanged, or
      // this loop never ends.
      paragraph.push(lines[index++]);
    }
    blocks.push(`<p>${inline(paragraph.join(" "))}</p>`);
  }
  return blocks.join("\n");
}

$("guide-btn").addEventListener("click", () => openGuide(panelDoc() || "user-guide"));

/* Keep the USB indicator honest: unplugging does not close the handle on
   macOS, so the only way to notice is to re-check. */
setInterval(async () => {
  if (!state.status.connected || state.guide.open) return;
  try {
    const data = await api("/api/state");
    const before = JSON.stringify(state.status);
    state.status = data.status;
    if (JSON.stringify(state.status) !== before) renderStatus();
  } catch {
    /* the server went away; the websocket reconnect will notice */
  }
}, 5000);
