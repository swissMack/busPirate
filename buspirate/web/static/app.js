/* The dashboard renders itself from /api/state. It knows nothing about any
   particular protocol: panels, actions, parameters and wiring all arrive as
   data, so adding a protocol to the Python side needs no change here. */

const $ = (id) => document.getElementById(id);

const state = {
  status: { connected: false },
  panels: [],
  current: localStorage.getItem("bp.panel") || null,
  busy: false,
};

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
  $("welcome").hidden = connected;
  $("panel").hidden = !connected;
  if (connected) renderPanel();
}

function renderStatus() {
  const box = $("status");
  const s = state.status;
  box.className =
    "status " + (s.connected ? (s.simulated ? "status--sim" : "status--on") : "status--off");
  $("status-text").textContent = s.connected
    ? `${s.simulated ? "SIMULATED " : ""}${s.description} · ${s.port}${s.mode ? " · " + s.mode : ""}`
    : "Not connected";
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
          localStorage.setItem("bp.panel", panel.id);
          render();
        },
      })
    )
  );
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
    el("h2", { text: panel.wiring.length ? "Wiring" : "Before you start" }),
    rows.length ? el("table", { class: "wiring" }, ...rows) : null,
    panel.notes.length
      ? el("ul", { class: "notes" }, ...panel.notes.map((note) => el("li", { text: note })))
      : null
  );
}

function cssColour(name) {
  const map = { grey: "#9aa0ad", purple: "#8b5cd6", white: "#f2f4f8", black: "#1c1f27" };
  return map[name] || name || "transparent";
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
