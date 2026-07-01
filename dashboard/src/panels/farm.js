export function renderFarm(payload) {
  const el = document.getElementById("farm-body");
  const f = payload.farm;
  if (!f || !f.has_data) {
    el.innerHTML = "";
    return;
  }
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
  const summary = f.summary
    ? `<div class="farm-summary">${f.summary}</div>`
    : "";
  el.innerHTML = rows + summary;
}
