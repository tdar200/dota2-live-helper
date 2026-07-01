// Client-side Dota art helpers. URLs are built from the item/hero KEY alone,
// so the keyless engine never touches the network — the browser loads these
// official Valve CDN assets at render time. A missing/blocked icon fires
// onerror and hides the <img>, leaving the existing text chip untouched.

const ITEM_CDN = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/items/";
const HERO_CDN = "https://cdn.cloudflare.steamstatic.com/apps/dota2/images/dota_react/heroes/";

// item_force_staff -> https://…/items/force_staff.png
export function itemIconUrl(key) {
  return key ? ITEM_CDN + String(key).replace(/^item_/, "") + ".png" : "";
}

// npc_dota_hero_juggernaut -> https://…/heroes/juggernaut.png
export function heroIconUrl(key) {
  return key ? HERO_CDN + String(key).replace(/^npc_dota_hero_/, "") + ".png" : "";
}

// Decorative <img>: adjacent text is the accessible label (alt=""), lazy-loaded,
// self-hides on error so a broken asset never renders a broken-image box.
export function itemImg(key) {
  return key
    ? `<img class="i-item" src="${itemIconUrl(key)}" alt="" loading="lazy" onerror="this.style.display='none'">`
    : "";
}

export function heroImg(key) {
  return key
    ? `<img class="i-hero" src="${heroIconUrl(key)}" alt="" loading="lazy" onerror="this.style.display='none'">`
    : "";
}
