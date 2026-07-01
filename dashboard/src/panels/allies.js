// Ally picker: same UX as the enemy picker, posts to /allies.
export function initAllies(engineHost) {
  const base = `http://${engineHost}`;
  const chips = document.getElementById("ally-chips");
  const search = document.getElementById("ally-search");
  let heroes = [];
  let selected = [];

  const displayToKey = () => Object.fromEntries(heroes.map((h) => [h.display, h.key]));
  const keyToDisplay = () => Object.fromEntries(heroes.map((h) => [h.key, h.display]));

  function render() {
    const names = keyToDisplay();
    chips.innerHTML = selected
      .map((k) => `<span class="chip ally" data-key="${k}">${names[k] || k} ✕</span>`)
      .join("");
    chips.querySelectorAll(".chip").forEach((c) =>
      c.addEventListener("click", () => {
        selected = selected.filter((k) => k !== c.dataset.key);
        push();
        render();
      })
    );
  }

  async function push() {
    await fetch(`${base}/allies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ heroes: selected }),
    }).catch((e) => console.error("allies POST failed", e));
  }

  search.addEventListener("change", () => {
    const key = displayToKey()[search.value];
    if (key && !selected.includes(key)) {
      selected.push(key);
      push();
      render();
    }
    search.value = "";
  });

  fetch(`${base}/heroes`)
    .then((r) => r.json())
    .then((list) => { heroes = list; })
    .catch((e) => console.error("heroes fetch failed", e));
}
