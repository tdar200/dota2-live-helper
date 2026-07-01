function mmss(total) {
  const s = Math.max(0, Math.floor(total));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function renderMacro(payload) {
  const m = payload.macro;
  const rec = document.getElementById("macro-rec");
  const fill = document.getElementById("win-fill");
  const pct = document.getElementById("win-pct");
  const reasons = document.getElementById("macro-reasons");
  const roshInfo = document.getElementById("rosh-info");
  if (!m) {
    rec.textContent = "—";
    return;
  }
  rec.textContent = m.recommendation;
  rec.className = `rec-${m.recommendation}`;
  if (m.win_prob == null) {
    fill.style.width = "0%";
    pct.textContent = "—";
  } else {
    const p = Math.round(m.win_prob * 100);
    fill.style.width = `${p}%`;
    pct.textContent = `${p}%`;
  }
  reasons.innerHTML = (m.reasons || []).map((r) => `<li>${r}</li>`).join("");
  if (m.roshan && payload.clock_time != null) {
    const until = m.roshan.window_start_s - payload.clock_time;
    roshInfo.textContent =
      m.roshan.status === "counting"
        ? `Rosh window in ${mmss(until)}`
        : `Rosh ${m.roshan.status}`;
  } else {
    roshInfo.textContent = "";
  }
}

export function initMacroControls(engineHost) {
  const base = `http://${engineHost}`;
  const input = document.getElementById("nwl-input");
  const post = (path, body) =>
    fetch(`${base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch((e) => console.error(path, e));

  input.addEventListener("change", () => {
    const lead = input.value === "" ? null : parseInt(input.value, 10);
    post("/networth", { lead });
  });
  document.getElementById("rosh-btn").addEventListener("click", () => post("/roshan", {}));
  document.getElementById("rosh-clear").addEventListener("click", () => post("/roshan", { clear: true }));
}
