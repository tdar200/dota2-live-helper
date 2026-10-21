import { heroImg } from "./icons.js";

const pct = (x) => (x == null ? "—" : `${Math.round(x * 100)}%`);
const heroName = (k) => (k || "").replace("npc_dota_hero_", "").replace(/_/g, " ");

function wrClass(x) {
  if (x == null) return "";
  return x >= 0.5 ? "wr-good" : "wr-bad";
}

function heroRows(list) {
  return (list || [])
    .map(
      (h) => `<li class="tr-hero">
        ${heroImg(h.hero)}<span class="tr-hname">${heroName(h.hero)}</span>
        <span class="tr-hg">${h.games}g</span>
        <span class="tr-hwr ${wrClass(h.winrate)}">${pct(h.winrate)}</span>
      </li>`
    )
    .join("");
}

function monthlyBars(monthly) {
  if (!monthly || !monthly.length) return "";
  return monthly
    .map((b) => {
      const h = Math.round((b.winrate || 0) * 100);
      const cls = b.winrate >= 0.5 ? "up" : "down";
      return `<div class="mbar" title="${b.period}: ${b.games}g ${h}%">
        <div class="mbar-fill ${cls}" style="height:${Math.max(4, h)}%"></div>
        <span class="mbar-lbl">${b.period.slice(2)}</span>
      </div>`;
    })
    .join("");
}

function formPips(results) {
  // newest-first from the engine; show oldest->newest left to right
  return [...(results || [])]
    .reverse()
    .map((w) => `<span class="pip ${w ? "win" : "loss"}">${w ? "W" : "L"}</span>`)
    .join("");
}

function splitRow(splits) {
  return (splits || [])
    .map(
      (s) =>
        `<span class="tr-split"><span class="tr-sl">${s.label}</span> ${s.games}g <b class="${wrClass(s.winrate)}">${pct(s.winrate)}</b></span>`
    )
    .join("");
}

export function renderTrends(t) {
  const el = document.getElementById("trends-body");
  if (!t || !t.has_data) {
    el.innerHTML =
      "<em>No history yet. Run <code>scripts/refresh_personal_stats.py</code>, then restart the engine.</em>";
    return;
  }
  const streak =
    t.current_streak > 0
      ? `<span class="streak win">${t.current_streak}W streak</span>`
      : t.current_streak < 0
      ? `<span class="streak loss">${-t.current_streak}L streak</span>`
      : "";
  const bracket =
    t.rank_start && t.rank_now
      ? t.rank_start === t.rank_now
        ? `${t.rank_now} (flat)`
        : `${t.rank_start} → ${t.rank_now}`
      : t.rank_now || "—";

  el.innerHTML = `
    <div class="tr-head">
      <span class="tr-record ${wrClass(t.winrate)}">${t.total_wins}–${t.total_games - t.total_wins}</span>
      <span class="tr-wr">${pct(t.winrate)} all-time</span>
      ${streak}
    </div>
    <div class="tr-sub">
      recent 20: <b class="${wrClass(t.recent_winrate)}">${pct(t.recent_winrate)}</b> ·
      last 7d: <b>${t.games_last_7d}g</b> · 30d: <b>${t.games_last_30d}g</b> ·
      bracket: <b>${bracket}</b>
    </div>
    <div class="tr-form">${formPips(t.recent_results)}</div>
    <div class="tr-kda">
      KDA <b>${t.avg_kills ?? "—"}/${t.avg_deaths ?? "—"}/${t.avg_assists ?? "—"}</b>
      ratio <b>${t.kda_ratio ?? "—"}</b>
      <span class="tr-dim">(recent ${t.recent_kda_ratio ?? "—"})</span> ·
      best streaks <b>${t.longest_win_streak}W</b> / <b>${t.longest_loss_streak}L</b>
    </div>
    <div class="tr-splits">${splitRow(t.duration_split)} ${splitRow(t.party_split)}</div>
    <div class="tr-monthly"><div class="tr-cap">win% by month</div><div class="mbars">${monthlyBars(t.monthly)}</div></div>
    <div class="tr-cols">
      <div class="tr-col"><div class="tr-cap good">play more</div><ul class="tr-heroes">${heroRows(t.best_heroes)}</ul></div>
      <div class="tr-col"><div class="tr-cap bad">play less</div><ul class="tr-heroes">${heroRows(t.worst_heroes)}</ul></div>
    </div>`;
}

export function loadTrends(base) {
  fetch(`${base}/trends`)
    .then((r) => r.json())
    .then(renderTrends)
    .catch((e) => console.error("trends", e));
}
