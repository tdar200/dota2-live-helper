export function renderFarm(payload) {
  const el = document.getElementById("farm-body");
  const f = payload.farm;
  if (!f || !f.has_data) {
    el.innerHTML = "";
    return;
  }
  // Percentile rate bars (GPM/XPM/LH, plus HeroDmg/Kills once benchmarks re-pulled)
  const rows = (f.metrics || [])
    .map(
      (m) => `
    <div class="farm-row">
      <span class="farm-label">${m.metric}</span>
      <div class="farm-track"><div class="farm-fill" style="width:${m.percentile}%"></div></div>
      <span class="farm-band farm-band-${m.label.replace(/\s+/g, "-")}">${m.label}</span>
    </div>`
    )
    .join("");
  // Raw live scorecard chips (K/D/A, LH/DN, HeroDmg, Net Worth) — the Dota-Plus
  // "how am I doing" readout. Empty until GSI carries these fields mid-game.
  const chips = (f.combat || [])
    .map(
      (c) => `<span class="score-chip"><span class="sc-k">${c.metric}</span> ${c.display}</span>`
    )
    .join("");
  const chipRow = chips ? `<div class="score-row">${chips}</div>` : "";
  const verdict = f.verdict ? `<div class="score-verdict">${f.verdict}</div>` : "";
  const summary = f.summary ? `<div class="farm-summary">${f.summary}</div>` : "";
  el.innerHTML = chipRow + verdict + rows + summary;
}
