function svgChart(curve, moments) {
  const W = 600, H = 160;
  if (!curve || !curve.length) return "";
  const maxMin = curve[curve.length - 1].minute || 1;
  const x = (m) => (m / maxMin) * W;
  const y = (p) => (1 - p) * H;
  const pts = curve.map((c) => `${x(c.minute).toFixed(1)},${y(c.win_prob).toFixed(1)}`).join(" ");
  const base = y(0.5).toFixed(1);
  const dots = (moments || [])
    .map((m) => `<circle cx="${x(m.minute).toFixed(1)}" cy="${y(m.win_prob).toFixed(1)}" r="4" class="mom ${m.kind}"/>`)
    .join("");
  return `<svg viewBox="0 0 ${W} ${H}" class="wpchart" preserveAspectRatio="none">
    <line x1="0" y1="${base}" x2="${W}" y2="${base}" class="baseline"/>
    <polyline points="${pts}" class="wpline"/>${dots}</svg>`;
}

export function renderReview(report) {
  const el = document.getElementById("review-body");
  if (!report) {
    el.innerHTML = "<em>select a match…</em>";
    return;
  }
  const s = report.summary || {};
  const moments = (report.moments || [])
    .map((m) => `<li class="mom-row ${m.kind}"><span>${Math.floor(m.minute)}:00</span>
      <b>${m.kind}</b> ${m.delta > 0 ? "+" : ""}${Math.round(m.delta * 100)}% — ${m.label}</li>`)
    .join("");
  const peak = s.peak_win_prob == null ? "—" : `${Math.round(s.peak_win_prob * 100)}%`;
  el.innerHTML = `
    <div class="rev-sum">${report.you_won ? "WON" : "LOST"} · peak ${peak} @ ${s.peak_minute}:00 · threw ${s.threw_count ?? 0}</div>
    ${svgChart(report.curve, report.moments)}
    <ul class="moments">${moments}</ul>`;
}

export function populateReviews(list) {
  const sel = document.getElementById("review-select");
  sel.innerHTML =
    `<option value="">— select match —</option>` +
    (list || []).map((r) => `<option value="${r.match_id}">${r.match_id} (${r.you_won ? "W" : "L"})</option>`).join("");
}
