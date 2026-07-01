import { connect } from "./ws.js";
import { renderTimings, renderClock } from "./panels/timings.js";
import { renderBuild } from "./panels/build.js";
import { initEnemies } from "./panels/enemies.js";
import { renderDraft } from "./panels/draft.js";
import { initAllies } from "./panels/allies.js";

// Single-process: engine serves this page (same host:port). Vite dev (5173) -> engine :3000.
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
  renderBuild(payload);
  renderDraft(payload);
}

initEnemies(ENGINE_HOST);
initAllies(ENGINE_HOST);
connect(WS_URL, onMessage, onStatus);
