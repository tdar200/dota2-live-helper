// Header ability strip: glanceable ult/cooldown pips + aghs pills.
// Pure render of payload.spells (server-side advisor already filtered
// passives/talents). Quietly empty when spells is absent or unavailable.

export function renderAbilities(payload) {
  const strip = document.getElementById("ability-strip");
  if (!strip) return;
  const s = payload && payload.spells;
  if (!s || !s.available) {
    strip.innerHTML = "";
    return;
  }
  const parts = [];
  if (s.ultimate) parts.push(pip(s.ultimate, true));
  for (const sr of (s.key_spells || []).slice(0, 3)) parts.push(pip(sr, false));
  parts.push(aghsPill("AGH", s.aghanims_scepter));
  parts.push(aghsPill("SHD", s.aghanims_shard));
  strip.innerHTML = parts.join("");
}

// npc_dota_hero_sniper ability key "sniper_shrapnel" -> "shrapnel"
function shortName(name) {
  return String(name || "").replace(/^[a-z0-9]+_/, "").replace(/_/g, " ");
}

function pip(sr, isUlt) {
  let label, state;
  if (sr.ready) {
    label = isUlt ? "ULT" : "✓";
    state = "ready";
  } else if (sr.cooldown != null) {
    label = `${sr.cooldown}s`;
    state = "cd";
  } else {
    label = isUlt ? "ULT" : "•";
    state = "cd";
  }
  const cls = `abil-pip ${state}${isUlt ? " ult" : ""}`;
  const nm = isUlt ? "Ultimate" : shortName(sr.name);
  const status = sr.ready
    ? "ready"
    : sr.cooldown != null
    ? `${sr.cooldown} seconds`
    : "on cooldown";
  const aria = `${nm} ${status}`;
  return `<span class="${cls}" role="img" aria-label="${aria}">${label}</span>`;
}

function aghsPill(kind, owned) {
  const on = owned === true;
  const full = kind === "AGH" ? "Aghanim's Scepter" : "Aghanim's Shard";
  const aria = `${full} ${on ? "owned" : "not owned"}`;
  return `<span class="aghs-pill ${on ? "on" : "off"}" role="img" aria-label="${aria}">${kind}</span>`;
}
