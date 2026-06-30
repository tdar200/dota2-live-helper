import { connect } from "./ws.js";
import { renderTimings, renderClock } from "./panels/timings.js";

// Single-process: the engine serves this page, so the WS shares its host:port.
// Vite dev mode (port 5173) is the exception — the engine runs separately on :3000.
const ENGINE_HOST = location.port === "5173" ? `${location.hostname}:3000` : location.host;
const WS_URL = `ws://${ENGINE_HOST}/ws`;
const statusEl = document.getElementById("status");

function onStatus(up) {
  statusEl.textContent = up ? "connected" : "disconnected";
  statusEl.className = `status ${up ? "on" : "off"}`;
}

function onMessage(payload) {
  renderClock(payload);
  renderTimings(payload);
}

connect(WS_URL, onMessage, onStatus);
