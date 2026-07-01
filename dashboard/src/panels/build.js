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
        .map((c) => `<span class="core ${c.owned ? "owned" : ""}">${c.owned ? "✓" : "•"} ${c.display}</span>`)
        .join("");
      parts.push(`<span class="phase-label">${phaseLabels[ph]}</span>${chips}`);
    }
    const seqHtml = parts.join('<span class="phase-div">›</span>');
    const nextDisplay = b.suggested_next ? b.suggested_next.display : "build complete";
    el.innerHTML = `
    <div class="hero">${b.hero_display || b.hero}</div>
    <div class="next">NEXT: <strong>${nextDisplay}</strong></div>
    <div class="coreline">${seqHtml}</div>
    <div class="build-meta">(vs all-bracket meta)</div>`;
    return;
  }

  // Curated path (source === "curated") — unchanged
  const core = b.core
    .map((c) => `<span class="core ${c.owned ? "owned" : ""}">${c.owned ? "✓" : "•"} ${c.display}</span>`)
    .join(" ");
  const sit = b.situational
    .map((s) => {
      const on = s.triggered_by.length > 0;
      const who = on ? ` ← ${s.triggered_by.join(", ")}` : "";
      return `<li class="sit ${on ? "on" : ""}">${on ? "⚠ " : "· "}${s.display}<span class="why">${who} (${s.note})</span></li>`;
    })
    .join("");
  el.innerHTML = `
    <div class="hero">${b.hero_display}</div>
    <div class="next">NEXT: <strong>${b.next_core ? b.next_core.display : "build complete"}</strong></div>
    <div class="coreline">${core}</div>
    <div class="skill">Skill: ${b.skill_next || ""}</div>
    <div class="talent">Talent: ${b.talent_next || ""}</div>
    <ul class="situational">${sit}</ul>`;
}
