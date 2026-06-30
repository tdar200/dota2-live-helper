function mmss(total) {
  const s = Math.max(0, total);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${String(r).padStart(2, "0")}`;
}

export function renderTimings(payload) {
  const list = document.getElementById("timings-list");
  list.innerHTML = "";
  for (const t of payload.timings || []) {
    const li = document.createElement("li");
    li.className = `timing cat-${t.category}`;
    li.innerHTML = `<span class="name">${t.name}</span>
                    <span class="eta">${mmss(t.seconds_until)}</span>`;
    list.appendChild(li);
  }
}

export function renderClock(payload) {
  const clock = document.getElementById("clock");
  clock.textContent = payload.clock_time == null ? "--:--" : mmss(payload.clock_time);
}
