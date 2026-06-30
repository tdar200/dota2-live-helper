import { connect } from "./ws.js";
import { renderTimings, renderClock } from "./panels/timings.js";

const WS_URL = `ws://${location.hostname || "127.0.0.1"}:3000/ws`;
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
