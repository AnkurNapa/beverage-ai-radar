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

// ---- Theme toggle ---------------------------------------------------------
// Three states, not two: "system" is the default and must remain reachable,
// otherwise a user who tries the control can never get back to following
// their OS. Order is system -> light -> dark -> system.
(function () {
  var btn = document.getElementById("theme-toggle");
  if (!btn) return;
  var label = btn.querySelector(".theme-toggle__label");
  var icon = btn.querySelector(".theme-toggle__icon");
  var ORDER = ["system", "light", "dark"];
  var ICON = { system: "◐", light: "☀", dark: "☾" };
  var TEXT = { system: "System", light: "Light", dark: "Dark" };

  function current() {
    var t = document.documentElement.dataset.theme;
    return t === "light" || t === "dark" ? t : "system";
  }
  function paint(state) {
    if (state === "system") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = state;
    if (icon) icon.textContent = ICON[state];
    if (label) label.textContent = TEXT[state];
    btn.setAttribute("title", "Theme: " + TEXT[state] + " (click to change)");
    try {
      if (state === "system") localStorage.removeItem("radar-theme");
      else localStorage.setItem("radar-theme", state);
    } catch (e) { /* private mode: the choice just does not persist */ }
  }
  paint(current());
  btn.addEventListener("click", function () {
    paint(ORDER[(ORDER.indexOf(current()) + 1) % ORDER.length]);
  });
})();

// ---- Mobile paging --------------------------------------------------------
// 378 cards measured 103 screens of scroll on a phone. Rather than change how
// app.js renders (it re-renders the whole grid on every filter change), this
// caps what is *visible* and re-applies itself after each render via a
// MutationObserver. Desktop is untouched: the full list is the point there.
(function () {
  // Desktop shows three columns, so a page of 48 is the same number of rows a
  // phone gets from 24. Measured 44 screens of scroll at 1440 before this.
  var MOBILE = window.matchMedia("(max-width: 720px)");
  var step = function () { return MOBILE.matches ? 24 : 48; };
  var grid = document.getElementById("grid");
  if (!grid) return;

  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "mpager";
  grid.insertAdjacentElement("afterend", btn);

  var shown = step();

  function apply() {
    var cards = grid.children;
    var total = cards.length;
    for (var j = 0; j < total; j++) {
      cards[j].style.display = j < shown ? "" : "none";
    }
    var left = total - shown;
    if (left > 0) {
      btn.textContent = "Show " + Math.min(left, step()) + " more (" + left + " left)";
      btn.classList.add("is-on");
    } else {
      btn.classList.remove("is-on");
    }
  }

  btn.addEventListener("click", function () {
    shown += step();
    apply();
    // Keep the reading position: without this the button jumps up the page
    // as the list grows and the thumb lands somewhere unrelated.
    btn.scrollIntoView({ block: "nearest" });
  });

  // A filter change replaces the children, so the cap has to be re-applied and
  // the count reset, or the user lands mid-list with a stale "N left".
  var pending = false;
  new MutationObserver(function () {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () { pending = false; shown = step(); apply(); });
  }).observe(grid, { childList: true });

  // A resize across the breakpoint changes the page size, so reset the count
  // rather than leaving a desktop-sized page on a phone layout.
  MOBILE.addEventListener("change", function () { shown = step(); apply(); });
  apply();
})();

// ---- Filter hierarchy -----------------------------------------------------
// The companies view exposes 14 filters as one flat row, so a rarely-used
// provenance filter looks exactly as important as "Vertical". Three tiers:
// what you filter by daily stays visible, the rest fold away. Applied from
// here rather than app.js so the filtering logic itself is untouched.
(function () {
  var TIER = {
    // Primary: the three axes the dataset is actually about.
    "f-vertical": 1, "f-usecase": 1, "f-country": 1,
    // Secondary: refine a result set you already have.
    "f-capability": 2, "f-maturity": 2, "f-type": 2, "f-platform": 2, "f-scope": 2,
    // Provenance and housekeeping. Useful, but not what you reach for first.
    "f-status": 3, "f-source": 3, "f-funding": 3, "f-era": 3,
    "f-people": 3, "f-seen": 3
  };
  var ids = Object.keys(TIER);
  var wraps = [];
  ids.forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    // The control sits inside a label/wrapper; hide that, not just the select,
    // or the caption is left orphaned.
    var w = el.closest("label, .field, .filter") || el;
    w.dataset.tier = TIER[id];
    wraps.push(w);
  });
  if (!wraps.length) return;

  var host = wraps[0].parentElement;
  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = "filter-more";
  var open = false;

  function paint() {
    wraps.forEach(function (w) {
      if (w.dataset.tier !== "1") w.hidden = !open;
    });
    var n = wraps.filter(function (w) { return w.dataset.tier !== "1"; }).length;
    btn.textContent = open ? "Fewer filters" : "More filters (" + n + ")";
    btn.setAttribute("aria-expanded", String(open));
  }
  btn.addEventListener("click", function () { open = !open; paint(); });
  host.appendChild(btn);

  // If a hidden filter is already set (from a saved view or a shared URL),
  // reveal the group rather than silently applying an invisible constraint.
  var preset = wraps.some(function (w) {
    if (w.dataset.tier === "1") return false;
    var s = w.querySelector("select");
    return s && s.value;
  });
  open = preset;
  paint();
})();

// ---- Country granularity --------------------------------------------------
// 35 countries as one alphabetical list means scrolling past Argentina to
// reach the United States. Grouping into regions gives the control a shape
// that matches how anyone actually thinks about this dataset ("who is doing
// this in Europe?"). Pure presentation: option values are untouched, so the
// filtering logic and any saved views keep working.
(function () {
  var REGION = {
    "North America": ["United States", "Canada", "Mexico"],
    "Latin America": ["Argentina", "Brazil", "Chile", "Peru", "Uruguay", "Colombia", "Ecuador"],
    "United Kingdom & Ireland": ["United Kingdom", "Ireland", "Scotland"],
    "Western Europe": ["Germany", "France", "Netherlands", "Belgium", "Austria",
                       "Switzerland", "Luxembourg"],
    "Southern Europe": ["Spain", "Italy", "Portugal", "Greece"],
    "Nordics": ["Sweden", "Denmark", "Norway", "Finland", "Iceland"],
    "Central & Eastern Europe": ["Poland", "Czechia", "Czech Republic", "Hungary",
                                  "Romania", "Ukraine", "Slovenia", "Croatia", "Estonia"],
    "Asia Pacific": ["India", "China", "Japan", "Singapore", "South Korea", "Taiwan",
                      "Hong Kong", "Thailand", "Malaysia", "Vietnam", "Indonesia",
                      "Philippines", "Sri Lanka"],
    "Australia & New Zealand": ["Australia", "New Zealand"],
    "Middle East & Africa": ["Israel", "United Arab Emirates", "Turkey",
                              "South Africa", "Kenya", "Nigeria", "Egypt"]
  };
  var LOOKUP = {};
  Object.keys(REGION).forEach(function (r) {
    REGION[r].forEach(function (c) { LOOKUP[c.toLowerCase()] = r; });
  });

  function group(sel) {
    if (!sel || sel.dataset.grouped === "1") return;
    var opts = [...sel.options];
    if (opts.length < 8) return;
    var head = opts[0];                       // the "All countries" entry
    var buckets = {}, other = [];
    opts.slice(1).forEach(function (o) {
      var r = LOOKUP[(o.textContent || "").trim().toLowerCase().replace(/\s*\(\d+\)$/, "")];
      if (r) { (buckets[r] = buckets[r] || []).push(o); } else { other.push(o); }
    });
    // Nothing recognised means the label format changed; leave it alone rather
    // than shuffling the list into a worse order.
    if (!Object.keys(buckets).length) return;
    var frag = document.createDocumentFragment();
    frag.appendChild(head);
    Object.keys(REGION).forEach(function (r) {
      if (!buckets[r]) return;
      var g = document.createElement("optgroup");
      g.label = r;
      buckets[r].forEach(function (o) { g.appendChild(o); });
      frag.appendChild(g);
    });
    if (other.length) {
      var g2 = document.createElement("optgroup");
      g2.label = "Other";
      other.forEach(function (o) { g2.appendChild(o); });
      frag.appendChild(g2);
    }
    var keep = sel.value;
    sel.innerHTML = "";
    sel.appendChild(frag);
    sel.value = keep;
    sel.dataset.grouped = "1";
  }

  ["f-country", "fp-country", "fj-country"].forEach(function (id) {
    var sel = document.getElementById(id);
    if (!sel) return;
    group(sel);
    // app.js repopulates these when the dataset loads, which wipes the groups.
    new MutationObserver(function () {
      if (sel.dataset.grouped !== "1") group(sel);
    }).observe(sel, { childList: true });
  });
})();

// ---- Icon set -------------------------------------------------------------
// One stroke system instead of a mix of emoji (radar dish, bust silhouette)
// and bare text. Inline SVG rather than an icon font or a CDN package: six
// glyphs do not justify a dependency, and inline paths inherit currentColor
// so they theme themselves in light and dark for free. 1.5 stroke, 24-grid,
// round caps: consistency here is mostly about picking one and holding it.
(function () {
  var P = {
    companies: '<path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-5h6v5"/>',
    people:    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/>',
    research:  '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
    jobs:      '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
    prospects: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    about:     '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>'
  };
  function svg(name) {
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" ' +
           'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false" ' +
           'class="ico">' + P[name] + '</svg>';
  }
  var MAP = { Companies: "companies", People: "people", Research: "research",
              Jobs: "jobs", Prospects: "prospects", About: "about" };
  document.querySelectorAll(".topnav .tab").forEach(function (tab) {
    var key = MAP[tab.dataset.short];
    if (!key || tab.querySelector(".ico")) return;
    tab.insertAdjacentHTML("afterbegin", svg(key));
  });
})();
