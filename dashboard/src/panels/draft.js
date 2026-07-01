import { heroImg } from "./icons.js";

function pct(x) {
  return x == null ? "—" : `${Math.round(x * 100)}%`;
}

export function renderDraft(payload) {
  const el = document.getElementById("draft-body");
  const d = payload.draft;
  if (!d || !d.picks || d.picks.length === 0) {
    el.innerHTML = "<em>enter the enemy lineup…</em>";
    return;
  }
  const note = d.has_data ? "" : `<div class="draft-note">${d.note || ""}</div>`;
  const rows = d.picks
    .map((p, i) => {
      const best = i === 0 ? "best" : "";
      const badge = p.countered ? `<span class="countered">⚠ countered</span>` : "";
      const why = p.reasons.length ? ` — ${p.reasons.join("; ")}` : "";
      return `<li class="pick ${best}">
        <span class="rank">${i + 1}.</span>
        ${heroImg(p.hero)}<span class="pname">${p.display}</span> ${badge}
        <span class="pscore">${pct(p.score)}</span>
        <span class="pwhy">${why}</span>
      </li>`;
    })
    .join("");
  el.innerHTML = `${note}<ol class="picks">${rows}</ol>`;
}
