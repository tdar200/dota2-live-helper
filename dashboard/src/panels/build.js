import { itemImg, heroImg } from "./icons.js";

// Herald (bracket 1) win% badge for the build-tile header. Quietly empty when
// the hero-meta cache is absent (herald_winrate null) — graceful degradation.
function heraldBadge(b) {
  if (b.herald_winrate == null) return "";
  const pct = (b.herald_winrate * 100).toFixed(1);
  const cls = b.herald_winrate >= 0.5 ? "wr-good" : "wr-bad";
  return ` <span class="herald-wr ${cls}" title="Herald pub win rate (OpenDota)">${pct}% Herald</span>`;
}

// Hide personal win-rates below this many games — tiny samples ("100% · 1g")
// are noise, not signal.
const MIN_PERSONAL_GAMES = 3;

// YOUR win% on this hero, for the header. Empty until the personal cache exists
// and you have a meaningful sample (scripts/refresh_personal_stats.py).
function personalHeroBadge(b) {
  if (b.personal_winrate == null || (b.personal_games || 0) < MIN_PERSONAL_GAMES) return "";
  const pct = (b.personal_winrate * 100).toFixed(0);
  const cls = b.personal_winrate >= 0.5 ? "wr-good" : "wr-bad";
  return ` <span class="you-wr ${cls}" title="Your win rate on this hero (${b.personal_games} of your games)">You ${pct}% · ${b.personal_games}g</span>`;
}

// YOUR win% with a single item on this hero, as a compact chip suffix.
function itemYouWr(c) {
  if (!c || c.personal_winrate == null || (c.personal_games || 0) < MIN_PERSONAL_GAMES) return "";
  const pct = (c.personal_winrate * 100).toFixed(0);
  const cls = c.personal_winrate >= 0.5 ? "wr-good" : "wr-bad";
  return ` <span class="you-chip ${cls}" title="Your win rate with this item on this hero (${c.personal_games} games)">${pct}%·${c.personal_games}g</span>`;
}

export function renderBuild(payload) {
  const el = document.getElementById("build-body");
  const b = payload.build;
  if (!b) {
    el.innerHTML = "<em>waiting for game…</em>";
    return;
  }
  if (!b.has_build) {
    el.innerHTML = `<em>No curated build for ${b.hero || "this hero"} yet — timings still active.</em>`;
    return;
  }

  if (b.source === "opendota") {
    // All-hero OpenDota fallback — compact phase sequence, ≤4 chips/phase
    const phaseKeys = ["start_game", "early_game", "mid_game", "late_game"];
    const phaseLabels = { start_game: "start", early_game: "early", mid_game: "mid", late_game: "late" };
    const parts = [];
    for (const ph of phaseKeys) {
      const items = (b.phases[ph] || []).slice(0, 4);
      if (!items.length) continue;
      const chips = items
        .map((c) => `<span class="core ${c.owned ? "owned" : ""}">${itemImg(c.item)}${c.owned ? "✓" : "•"} ${c.display}${itemYouWr(c)}</span>`)
        .join("");
      parts.push(`<span class="phase-label">${phaseLabels[ph]}</span>${chips}`);
    }
    const seqHtml = parts.join('<span class="phase-div">›</span>');
    const nextDisplay = b.suggested_next ? b.suggested_next.display : "build complete";
    const nextIcon = b.suggested_next ? itemImg(b.suggested_next.item) : "";
    el.innerHTML = `
    <div class="hero">${heroImg(b.hero)}<span class="hname">${b.hero_display || b.hero}</span>${heraldBadge(b)}${personalHeroBadge(b)}</div>
    <div class="next">NEXT: ${nextIcon}<strong>${nextDisplay}</strong>${itemYouWr(b.suggested_next)}</div>
    <div class="coreline">${seqHtml}</div>
    <div class="build-meta">(vs all-bracket meta)</div>`;
    return;
  }

  // Curated path (source === "curated") — unchanged
  const core = b.core
    .map((c) => `<span class="core ${c.owned ? "owned" : ""}">${itemImg(c.item)}${c.owned ? "✓" : "•"} ${c.display}${itemYouWr(c)}</span>`)
    .join(" ");
  const sit = b.situational
    .map((s) => {
      const on = s.triggered_by.length > 0;
      const who = on ? ` ← ${s.triggered_by.join(", ")}` : "";
      return `<li class="sit ${on ? "on" : ""}">${itemImg(s.item)}${on ? "⚠ " : "· "}${s.display}<span class="why">${who} (${s.note})</span></li>`;
    })
    .join("");
  el.innerHTML = `
    <div class="hero">${heroImg(b.hero)}<span class="hname">${b.hero_display}</span>${heraldBadge(b)}${personalHeroBadge(b)}</div>
    <div class="next">NEXT: ${b.next_core ? itemImg(b.next_core.item) : ""}<strong>${b.next_core ? b.next_core.display : "build complete"}</strong>${itemYouWr(b.next_core)}</div>
    <div class="coreline">${core}</div>
    <div class="skill">Skill: ${b.skill_next || ""}</div>
    <div class="talent">Talent: ${b.talent_next || ""}</div>
    <ul class="situational">${sit}</ul>`;
}
