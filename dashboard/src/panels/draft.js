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
  // Show the STRATZ nudge whenever the engine emits it (matchups absent) —
  // independent of has_data, which is now True on hero_meta alone.
  const note = d.note ? `<div class="draft-note">${d.note}</div>` : "";
  const rows = d.picks
    .map((p, i) => {
      const best = i === 0 ? "best" : "";
      const badge = p.countered ? `<span class="countered">⚠ countered</span>` : "";
      const comfort =
        p.personal_winrate != null
          ? ` <span class="you-comfort ${p.personal_winrate >= 0.5 ? "wr-good" : "wr-bad"}" title="Your win rate on this hero (${p.personal_games} games)">you ${Math.round(p.personal_winrate * 100)}%</span>`
          : "";
      // The personal reason is already in reasons[]; drop it here to avoid duplication.
      const why = p.reasons.filter((r) => !r.startsWith("you ")).join("; ");
      const whyHtml = why ? ` — ${why}` : "";
      // Show the hero's real Herald win-rate (a true probability) — NOT the
      // composite ranking score, which blends counter/synergy/comfort and can
      // exceed 100%. Ordering + reasons convey the rest.
      return `<li class="pick ${best}">
        <span class="rank">${i + 1}.</span>
        ${heroImg(p.hero)}<span class="pname">${p.display}</span>${comfort} ${badge}
        <span class="pscore" title="Herald win rate">${pct(p.base_winrate)}</span>
        <span class="pwhy">${whyHtml}</span>
      </li>`;
    })
    .join("");
  el.innerHTML = `${note}<ol class="picks">${rows}</ol>`;
}
