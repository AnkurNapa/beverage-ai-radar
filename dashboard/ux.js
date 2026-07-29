// Reading state, saved views and the command palette.
//
// Split out of app.js, which was already past this repo's 800-line guideline.
// Imported with a ?v= query that scripts/stamp_assets.py keeps in step with
// the file contents, for the same reason app.js itself carries one: a stale
// cached module is invisible and looks exactly like a feature that never
// shipped.
//
// Everything here is browser-local. The radar is a public page with no
// accounts, so reading history lives in localStorage and never leaves the
// device. That also means it does not follow you to another machine, which is
// the honest trade for having no backend at all.

const SEEN_KEY = "radar.seen";
const VISIT_KEY = "radar.lastVisit";
const STAR_KEY = "radar.stars";
const VIEW_KEY = "radar.views";
const SEEN_KEY_HINT = "radar.hintsDismissed";

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    // Private browsing, disabled storage, or corrupt JSON. Reading history is
    // a convenience: it must never take the page down with it.
    return fallback;
  }
}

function write(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* quota or blocked */ }
}

// --- reading state --------------------------------------------------------

let SEEN = read(SEEN_KEY, {});

// The previous visit's timestamp, captured once at load. Read before the
// current visit overwrites it, or "new since last visit" would always be zero.
export const PREVIOUS_VISIT = read(VISIT_KEY, 0);
write(VISIT_KEY, Date.now());

/** 'new' | 'seen' | 'revisit' — revisit means opened more than once. */
export function seenState(key) {
  const hit = SEEN[key];
  if (!hit) return "new";
  return hit.n > 1 ? "revisit" : "seen";
}

export function seenAt(key) {
  return SEEN[key]?.t || 0;
}

/** How many times a detail page was opened. Drives "frequently visited". */
export function seenCount(key) {
  return SEEN[key]?.n || 0;
}

/** Most recently opened first. Unopened entries are excluded, not sorted last. */
export function recentlyOpened(limit = 8) {
  return Object.entries(SEEN)
    .sort((a, b) => b[1].t - a[1].t)
    .slice(0, limit)
    .map(([key, v]) => ({ key, ...v }));
}

/** Called when a detail page opens. Scrolling past a card does not count. */
export function markSeen(key) {
  if (!key) return;
  const hit = SEEN[key] || { n: 0, t: 0 };
  SEEN[key] = { n: hit.n + 1, t: Date.now() };
  write(SEEN_KEY, SEEN);
}

export function seenCounts(keys) {
  const out = { new: 0, seen: 0, revisit: 0 };
  for (const k of keys) out[seenState(k)]++;
  return out;
}

export function clearSeen() {
  SEEN = {};
  write(SEEN_KEY, SEEN);
}

const DAY = 86400000;
export function agoLabel(ts) {
  if (!ts) return "";
  const d = Math.floor((Date.now() - ts) / DAY);
  if (d <= 0) return "today";
  if (d === 1) return "yesterday";
  if (d < 30) return `${d}d ago`;
  return `${Math.floor(d / 30)}mo ago`;
}

// --- stars (shortlist) ----------------------------------------------------

let STARS = new Set(read(STAR_KEY, []));

export const isStarred = (key) => STARS.has(key);
export const starCount = () => STARS.size;

export function toggleStar(key) {
  if (STARS.has(key)) STARS.delete(key); else STARS.add(key);
  write(STAR_KEY, [...STARS]);
  return STARS.has(key);
}

// --- saved views ----------------------------------------------------------
// A view is a name plus the values of every filter control in a section, so
// restoring it is just writing those values back and firing one input event.

export const savedViews = () => read(VIEW_KEY, []);

export function saveView(name, tab, values) {
  const views = savedViews().filter((v) => v.name !== name);
  views.push({ name, tab, values, t: Date.now() });
  write(VIEW_KEY, views);
  return views;
}

export function deleteView(name) {
  const views = savedViews().filter((v) => v.name !== name);
  write(VIEW_KEY, views);
  return views;
}

// --- first-run hints ------------------------------------------------------

export const hintDismissed = (id) => read(SEEN_KEY_HINT, []).includes(id);

export function dismissHint(id) {
  const all = read(SEEN_KEY_HINT, []);
  if (!all.includes(id)) { all.push(id); write(SEEN_KEY_HINT, all); }
}

// --- command palette ------------------------------------------------------
// Cmd/Ctrl+K. Sources are supplied by app.js so this file needs no knowledge
// of the data shapes; it only ranks and renders.

// Palette labels are company and person names that arrived from scraped
// sources, so they are escaped before going anywhere near innerHTML.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function score(item, q) {
  const label = item.label.toLowerCase();
  if (label === q) return 0;
  if (label.startsWith(q)) return 1;
  const i = label.indexOf(q);
  if (i >= 0) return 2 + i / 100;
  // Subsequence match, so "bra" finds "Bengaluru Radar" style gaps.
  let j = 0;
  for (const ch of label) if (ch === q[j]) j++;
  return j === q.length ? 40 : Infinity;
}

export function mountPalette({ getItems, onPick }) {
  const root = document.createElement("div");
  root.className = "cmdk";
  root.hidden = true;
  root.innerHTML = `
    <div class="cmdk__scrim"></div>
    <div class="cmdk__box" role="dialog" aria-modal="true" aria-label="Command palette">
      <input class="cmdk__q" type="search" placeholder="Jump to a tab, country, or entry…"
             aria-label="Search commands" autocomplete="off" />
      <ul class="cmdk__list" role="listbox"></ul>
      <div class="cmdk__foot"><kbd>↑</kbd><kbd>↓</kbd> move · <kbd>↵</kbd> open · <kbd>esc</kbd> close</div>
    </div>`;
  document.body.appendChild(root);

  const input = root.querySelector(".cmdk__q");
  const list = root.querySelector(".cmdk__list");
  let items = [], active = 0;

  function render() {
    const q = input.value.trim().toLowerCase();
    const pool = getItems();
    items = (q
      ? pool.map((it) => [score(it, q), it]).filter(([s]) => s !== Infinity)
          .sort((a, b) => a[0] - b[0]).map(([, it]) => it)
      : pool.filter((it) => it.always)).slice(0, 40);
    active = 0;
    list.innerHTML = items.length
      ? items.map((it, i) => `
          <li role="option" class="cmdk__i${i === 0 ? " is-active" : ""}" data-i="${i}">
            <span class="cmdk__k">${esc(it.kind)}</span>
            <span class="cmdk__l">${esc(it.label)}</span>
            ${it.hint ? `<span class="cmdk__h">${esc(it.hint)}</span>` : ""}
          </li>`).join("")
      : `<li class="cmdk__empty">No matches</li>`;
  }

  function move(delta) {
    if (!items.length) return;
    active = (active + delta + items.length) % items.length;
    [...list.children].forEach((li, i) => li.classList.toggle("is-active", i === active));
    list.children[active]?.scrollIntoView({ block: "nearest" });
  }

  function close() { root.hidden = true; input.value = ""; }

  function open() {
    root.hidden = false;
    render();
    input.focus();
  }

  input.addEventListener("input", render);
  list.addEventListener("click", (e) => {
    const li = e.target.closest("[data-i]");
    if (li) { onPick(items[+li.dataset.i]); close(); }
  });
  root.querySelector(".cmdk__scrim").addEventListener("click", close);
  root.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { close(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); move(1); }
    if (e.key === "ArrowUp") { e.preventDefault(); move(-1); }
    if (e.key === "Enter" && items[active]) { e.preventDefault(); onPick(items[active]); close(); }
  });
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); open(); }
  });

  return { open, close };
}
