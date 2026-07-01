// Enemy picker: loads the hero list, lets the user add/remove enemies,
// and POSTs the current lineup to the engine.
export function initEnemies(engineHost) {
  const base = `http://${engineHost}`;
  const chips = document.getElementById("enemy-chips");
  const search = document.getElementById("enemy-search");
  const datalist = document.getElementById("hero-list");
  let heroes = [];
  let selected = [];

  const displayToKey = () => Object.fromEntries(heroes.map((h) => [h.display, h.key]));
  const keyToDisplay = () => Object.fromEntries(heroes.map((h) => [h.key, h.display]));

  function render() {
    const names = keyToDisplay();
    chips.innerHTML = selected
      .map((k) => `<span class="chip" data-key="${k}">${names[k] || k} ✕</span>`)
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
    await fetch(`${base}/enemies`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ heroes: selected }),
    });
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
    .then((list) => {
      heroes = list;
      datalist.innerHTML = list.map((h) => `<option value="${h.display}"></option>`).join("");
    });
}
