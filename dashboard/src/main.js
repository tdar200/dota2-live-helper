import { connect } from "./ws.js";
import { renderTimings, renderClock } from "./panels/timings.js";
import { renderBuild } from "./panels/build.js";
import { initEnemies } from "./panels/enemies.js";
import { renderDraft } from "./panels/draft.js";
import { initAllies } from "./panels/allies.js";
import { renderMacro, initMacroControls } from "./panels/macro.js";
import { renderFarm } from "./panels/farm.js";
import { renderAbilities } from "./panels/abilities.js";
import { initAlerts, renderAlerts } from "./panels/alerts.js";
import { renderReview, populateReviews } from "./panels/review.js";

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
  renderMacro(payload);
  renderFarm(payload);
  renderAbilities(payload);
  renderAlerts(payload);
}

initEnemies(ENGINE_HOST);
initAllies(ENGINE_HOST);
initMacroControls(ENGINE_HOST);
initAlerts();

const base = `http://${ENGINE_HOST}`;
const liveView = document.getElementById("live-view");
const reviewView = document.getElementById("review-view");
const tabLive = document.getElementById("tab-live");
const tabReview = document.getElementById("tab-review");

function showLive() {
  liveView.hidden = false;
  reviewView.hidden = true;
  tabLive.classList.add("active");
  tabReview.classList.remove("active");
}
function showReview() {
  liveView.hidden = true;
  reviewView.hidden = false;
  tabReview.classList.add("active");
  tabLive.classList.remove("active");
  fetch(`${base}/reviews`).then((r) => r.json()).then(populateReviews).catch((e) => console.error("reviews", e));
}
tabLive.addEventListener("click", showLive);
tabReview.addEventListener("click", showReview);
document.getElementById("review-select").addEventListener("change", (e) => {
  const id = e.target.value;
  if (!id) {
    renderReview(null);
    return;
  }
  fetch(`${base}/review/${id}`).then((r) => r.json()).then(renderReview).catch((e) => console.error("review", e));
});

connect(WS_URL, onMessage, onStatus);
