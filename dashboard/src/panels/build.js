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
