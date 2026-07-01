// Client-only objective alert: a short Web Audio beep + a tile flash when any
// timing enters the 1..5s window. Edge-detected so each event fires once; mute
// gates audio only (persisted); flash is gated independently by reduced-motion.
// No network, no engine change — reads the existing payload.timings.

let audioCtx = null;
let muted = false;
const active = new Set(); // event names currently inside the 1..5s window

function ensureCtx() {
  if (audioCtx) return audioCtx;
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC) audioCtx = new AC();
  } catch (e) {
    audioCtx = null;
  }
  return audioCtx;
}

function resumeCtx() {
  const ctx = ensureCtx();
  if (ctx && ctx.state === "suspended") {
    try {
      ctx.resume().catch(() => {});
    } catch (e) {
      /* ignore */
    }
  }
}

function beep() {
  if (muted) return;
  try {
    const ctx = ensureCtx();
    if (!ctx) return;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    const t0 = ctx.currentTime;
    gain.gain.setValueAtTime(0.0001, t0);
    gain.gain.exponentialRampToValueAtTime(0.2, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.25);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t0);
    osc.stop(t0 + 0.26);
  } catch (e) {
    /* silent — audio must never throw */
  }
}

function reduceMotion() {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

function flash() {
  if (reduceMotion()) return;
  const panel = document.getElementById("timings-panel");
  if (!panel) return;
  panel.classList.add("flash");
  setTimeout(() => panel.classList.remove("flash"), 900);
}

export function renderAlerts(payload) {
  const timings = (payload && payload.timings) || [];
  const inWindow = new Set();
  for (const t of timings) {
    const su = t.seconds_until;
    if (su != null && su >= 1 && su <= 5) inWindow.add(t.name);
  }
  for (const name of inWindow) {
    if (!active.has(name)) {
      beep();
      flash();
    }
  }
  active.clear();
  for (const name of inWindow) active.add(name);
}

function paintMute() {
  const btn = document.getElementById("mute-btn");
  if (!btn) return;
  btn.setAttribute("aria-pressed", muted ? "true" : "false");
  btn.textContent = muted ? "🔕" : "🔔";
  btn.setAttribute(
    "aria-label",
    muted ? "Unmute objective alerts" : "Mute objective alerts"
  );
}

export function initAlerts() {
  try {
    muted = localStorage.getItem("dlh-muted") === "1";
  } catch (e) {
    muted = false;
  }
  paintMute();
  const btn = document.getElementById("mute-btn");
  if (btn) {
    btn.addEventListener("click", () => {
      muted = !muted;
      try {
        localStorage.setItem("dlh-muted", muted ? "1" : "0");
      } catch (e) {
        /* ignore */
      }
      paintMute();
      if (!muted) resumeCtx(); // unmuting is a user gesture — unlock audio
    });
  }
  // Autoplay policy: unlock the AudioContext on the first user gesture.
  window.addEventListener("pointerdown", resumeCtx, { once: true });
}
