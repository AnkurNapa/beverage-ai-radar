import {
  PREVIOUS_VISIT, agoLabel, clearSeen, deleteView, dismissHint, hintDismissed,
  isStarred, markSeen, mountPalette, recentlyOpened, saveView, savedViews, seenAt,
  seenCount, seenCounts,
  seenState, starCount, toggleStar,
} from "./ux.js?v=1baa4ae99b";

// Beverage-AI Radar dashboard. Reads data.json (exported by `radar export`),
// renders breakdown bars + a filterable company grid. Vanilla, no deps.

const $ = (id) => document.getElementById(id);
const esc = (s) => (s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// only http(s) links are clickable; anything else (javascript:, data:) is dropped.
const safeUrl = (u) => /^https?:\/\//i.test(u || "") ? u : "";

// Deterministic warm palette for initials avatars (hash name -> hue band).
const AVATAR_HUES = [18, 32, 44, 280, 200, 340, 150];
function initials(name) {
  const parts = (name || "?").trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] || "?") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}
function avatarHue(name) {
  let h = 0;
  for (const ch of name || "") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_HUES[h % AVATAR_HUES.length];
}
function avatarHtml(name, cls = "") {
  const hue = avatarHue(name);
  return `<span class="avatar ${cls}" style="--h:${hue}" aria-hidden="true">${esc(initials(name))}</span>`;
}
// Company logo via Clearbit (public, keyless). Falls back to an initials tile
// on load error (no domain, or Clearbit has none) with zero extra requests.
function logoHtml(c) {
  const fallback = avatarHtml(c.name, "avatar--logo");
  if (c.company_type === "individual") return avatarHtml(c.name, "avatar--logo avatar--person");
  if (!c.domain) return fallback;
  // Google's favicon service: public, reliable, returns real brand marks.
  // (Clearbit's logo API was discontinued after the HubSpot acquisition.)
  const src = `https://www.google.com/s2/favicons?domain=${esc(c.domain)}&sz=64`;
  return `<span class="logo"><img class="logo__fav" src="${src}" alt="" loading="lazy" width="28" height="28"
    onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" />${fallback}</span>`;
}

let ALL = [];

// ai_use_case is free text (~40 distinct strings), useless as a breakdown, so
// it gets bucketed into a handful of themes. The rules used to live here; they
// now live in src/radar/themes.py and the theme arrives precomputed on each row,
// so the gap analysis and this page cannot drift apart. Regenerate with
// `radar export` after changing a rule.
const themeOf = (c) => c.theme || "Other";

// Where a company was discovered. discovered_by is authoritative when present
// ("curated" or "scout:<surface>"); older rows fall back to the URL heuristic.
// Agent-found entries stay separable from hand-checked ones on purpose: if a
// sweep goes bad you need to know which rows to distrust.
function sourceOf(c) {
  if (c.discovered_by) {
    return c.discovered_by.startsWith("scout:")
      ? `Scout: ${c.discovered_by.slice(6)}`
      : "Hand-verified";
  }
  const urls = (c.source_urls || []).join(" ").toLowerCase();
  if (/drinktec\.com|yontex/.test(urls)) return "Drinktec";
  if (/agfundernews/.test(urls)) return "AgFunder";
  if (c.company_type === "service") return "Service research";
  return "Web research";
}

// Normalize free-text funding stage into a few clean buckets (seed/Seed -> Seed).
function fundingBucket(c) {
  const f = (c.funding_stage || "").toLowerCase();
  if (!f) return "";
  if (/public/.test(f)) return "Public";
  if (/acqui/.test(f)) return "Acquired";
  if (/bootstrap/.test(f)) return "Bootstrapped";
  if (/seed/.test(f)) return "Seed";
  if (/series\s*a/.test(f)) return "Series A";
  if (/series\s*b/.test(f)) return "Series B";
  if (/series\s*c/.test(f)) return "Series C";
  if (/series|vc/.test(f)) return "Later stage";
  return "Other";
}
const countryOf = (c) => c.country || (c.hq_location || "").split(",").pop().trim();

// Detect named tech platforms mentioned in free text (specific before generic).
const PLATFORM_RULES = [
  ["Microsoft Fabric", /microsoft fabric|ms fabric|\bfabric\b/i],
  ["Power BI", /power ?bi/i],
  ["Azure", /\bazure\b/i],
  ["Microsoft", /microsoft|dynamics 365|\bm365\b/i],
  ["Tableau", /tableau/i],
  ["Google Cloud", /google cloud|\bgcp\b|bigquery|vertex ai/i],
  ["AWS", /\baws\b|amazon web services|sagemaker/i],
  ["Snowflake", /snowflake/i],
  ["Databricks", /databricks/i],
  ["Qlik", /\bqlik\b/i],
  ["SAS", /\bSAS\b/],
  ["OSIsoft / PI", /osisoft|aveva|\bpi system\b/i],
  ["Streamlit", /streamlit/i],
  // industry bodies (so their resources are filterable too)
  ["MBAA", /\bMBAA\b|master brewers association/i],
  ["Brewers Association", /brewers association/i],
  ["ASBC", /\bASBC\b|society of brewing chemists/i],
  ["IBD", /institute of brewing/i],
];
function platformsOf(text) {
  const t = text || "";
  return PLATFORM_RULES.filter(([, re]) => re.test(t)).map(([name]) => name);
}

function hasNamed(c) {
  return (c.people && c.people.length) || !!c.key_people;
}
function hasLinkedin(c) {
  return (c.people || []).some((p) => p.linkedin);
}

function counts(list, field) {
  const m = new Map();
  for (const c of list) {
    const k = c[field] || "unknown";
    m.set(k, (m.get(k) || 0) + 1);
  }
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

// Palettes are validated, not eyeballed: every set below passes the lightness
// band, chroma floor, CVD separation and normal-vision floor in BOTH modes
// (adjacent pairlist, which is what a stacked bar uses).
const PAL = {
  // Verticals keep their semantic hues so the panel matches the card bands.
  vertical: { multiple: ["#2E5BFF", "#5C82FF"], beer: ["#D99A22", "#C98500"],
              wine: ["#9B3FB5", "#A96BD8"], whiskey: ["#C25A1E", "#D95926"] },
  // Themes have no inherent colour, so they take a fixed categorical order.
  // Assigned by rank and never cycled; past seven slots the tail folds to Other.
  theme: [["#2a78d6", "#3987e5"], ["#eb6834", "#d95926"], ["#1baf7a", "#199e70"],
          ["#eda100", "#c98500"], ["#e87ba4", "#d55181"], ["#008300", "#008300"],
          ["#4a3aa7", "#9085e9"], ["#e34948", "#e66767"]],
  // Maturity is ordinal (research -> pilot -> shipping), so one hue, light to dark.
  maturity: { research: ["#A9BEEE", "#33447A"], pilot: ["#6E8FE0", "#4A67B8"],
              shipping: ["#1E3FCC", "#7C95F0"] },
  other: ["#8A8A8A", "#7C7C7C"],
};
const MAX_SLOTS = 8;   // the validated palette tops out at 8; a 9th would be invented

function paintOf(kind, label, i) {
  const key = String(label).toLowerCase();
  if (kind === "theme") return (PAL.theme[i] || PAL.other);
  return (PAL[kind] && PAL[kind][key]) || PAL.other;
}

// One stacked proportion bar per panel plus a legend, rather than a row per
// category. Ten categories used to run ~700px tall; this is about 90px and
// still shows the whole composition at a glance.
function renderBars(el, pairs, filterId, kind) {
  const total = pairs.reduce((sum, p) => sum + p[1], 0) || 1;
  // Fold the tail so no slot ever needs an invented hue.
  let rows = pairs.slice(0, MAX_SLOTS).map(([l, n], i) => ({ label: l, n, paint: paintOf(kind, l, i), real: true }));
  const tail = pairs.slice(MAX_SLOTS);
  if (tail.length) {
    const merged = rows.find((r) => String(r.label).toLowerCase() === "other");
    const tailSum = tail.reduce((sum, p) => sum + p[1], 0);
    const names = tail.map(([l, n]) => `${l} ${n}`).join(", ");
    if (merged) { merged.n += tailSum; merged.folded = names; }
    else rows.push({ label: "Other", n: tailSum, paint: PAL.other, real: false, folded: names });
    rows = rows.sort((a, b) => b.n - a.n);
  }
  const pct = (n) => Math.round((n / total) * 100);
  const seg = (r) => `<span class="seg" style="flex:${r.n};--paint:${r.paint[0]};--paint-dark:${r.paint[1]}"
      title="${esc(r.label)} · ${r.n} of ${total} · ${pct(r.n)}%${r.folded ? ` — includes ${esc(r.folded)}` : ""}"
      ${filterId && r.real ? `data-filter="${esc(filterId)}" data-value="${esc(r.label)}"` : ""}></span>`;
  const key = (r) => `
    <button class="key" type="button" aria-pressed="false"
      style="--paint:${r.paint[0]};--paint-dark:${r.paint[1]}"
      title="${r.folded ? `includes ${esc(r.folded)}` : esc(r.label)}"
      ${filterId && r.real ? `data-filter="${esc(filterId)}" data-value="${esc(r.label)}"` : ""}>
      <span class="key__dot" aria-hidden="true"></span><span class="key__label">${esc(r.label)}</span>
      <span class="key__n">${r.n}</span><span class="key__pct">${pct(r.n)}%</span>
    </button>`;
  el.innerHTML = `
    <div class="stack" role="img" aria-label="${esc(rows.map((r) => `${r.label} ${r.n}`).join(", "))}">${rows.map(seg).join("")}</div>
    <div class="keys">${rows.map(key).join("")}</div>`;

  if (!filterId) return;
  const current = $(filterId)?.value || "";
  el.querySelectorAll("[data-filter]").forEach((node) => {
    const on = node.dataset.value === current;
    node.classList.toggle("is-on", on);
    if (node.hasAttribute("aria-pressed")) node.setAttribute("aria-pressed", String(on));
    node.addEventListener("click", () => {
      const sel = $(node.dataset.filter);
      sel.value = sel.value === node.dataset.value ? "" : node.dataset.value;
      sel.dispatchEvent(new Event("input"));  // repaints bars, KPIs and grid together
      $("grid").scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

function fillSelect(el, values, tally) {
  for (const v of values) {
    // Accept plain strings or [value, count] pairs. Showing the count means you
    // pick a filter knowing what it will return, instead of selecting into an
    // empty grid and backing out again.
    const [val, n] = Array.isArray(v) ? v : [v, tally ? tally[v] : undefined];
    const o = document.createElement("option");
    o.value = val;
    o.textContent = n == null ? val : `${val} (${n})`;
    el.appendChild(o);
  }
}

function peopleHtml(c) {
  // Prefer structured people (name + LinkedIn link); fall back to the plain string.
  if (Array.isArray(c.people) && c.people.length) {
    const items = c.people.map((p) => {
      const nm = esc(p.name);
      const link = safeUrl(p.linkedin);
      const named = link ? `<a href="${esc(link)}" target="_blank" rel="noopener">${nm}</a>` : nm;
      return p.role ? `${named} <span class="role">(${esc(p.role)})</span>` : named;
    }).join(", ");
    return `<p class="people"><span aria-hidden="true">👤</span> ${items}</p>`;
  }
  return c.key_people ? `<p class="people"><span aria-hidden="true">👤</span> ${esc(c.key_people)}</p>` : "";
}

function seenChip(key) {
  const s = seenState(key);
  if (s === "new") {
    return `<span class="chip chip--seen chip--seen-new" title="not opened yet">new</span>`;
  }
  // Show WHEN and HOW OFTEN on the chip itself. Both were already stored and
  // only visible in a tooltip, which is the same as not being there.
  const n = seenCount(key);
  const label = `${agoLabel(seenAt(key))}${n > 1 ? ` · ${n}\u00d7` : ""}`;
  const title = `opened ${n} time${n === 1 ? "" : "s"}, last ${agoLabel(seenAt(key))}`;
  return `<span class="chip chip--seen chip--seen-${s}" title="${esc(title)}">${esc(label)}</span>`;
}
const starBtn = (key) =>
  `<button class="starb${isStarred(key) ? " is-on" : ""}" data-star="${esc(key)}"
     type="button" aria-pressed="${isStarred(key)}" title="Shortlist this">★</button>`;

function card(c) {
  const individual = c.company_type === "individual";
  const chips = [
    c.vertical && `<span class="chip chip--v chip--${esc(c.vertical)}">${esc(c.vertical)}</span>`,
    individual && `<span class="chip chip--indiv">individual</span>`,
    c.company_type === "service" && `<span class="chip chip--muted">service</span>`,
    c.ai_maturity && `<span class="chip chip--mat chip--${esc(c.ai_maturity)}">${esc(c.ai_maturity)}</span>`,
    c.status === "dormant" && `<span class="chip chip--dormant">dormant</span>`,
    c.funding_stage && `<span class="chip chip--muted">${esc(c.funding_stage)}${c.total_raised ? " · " + esc(c.total_raised) : ""}</span>`,
    ...(c.capabilities || []).map(capChip),
    c.scope === "horizontal" && `<span class="chip chip--muted" title="Serves several industries, not built for drinks">horizontal</span>`,
    seenChip(c.key),
  ].filter(Boolean).join("");
  const srcs = (c.source_urls || []).map(safeUrl).filter(Boolean).map((u, i) =>
    `<a href="${esc(u)}" target="_blank" rel="noopener">source ${i + 1}</a>`).join(" · ");
  const site = safeUrl(c.domain ? `https://${c.domain}` : "");
  return `<article class="company is-clickable" data-status="${esc(c.status)}" data-route="c/${esc(encodeURIComponent(c.key))}">
    <div class="company__head">
      ${logoHtml(c)}
      <div class="company__id">
        <h3>${esc(c.name)}</h3>
        ${c.hq_location ? `<span class="loc">${esc(c.hq_location)}${c.founded_year ? " · " + c.founded_year : ""}</span>` : ""}
      </div>
      ${starBtn(c.key)}
    </div>
    ${c.ai_use_case ? `<p class="usecase">${esc(c.ai_use_case)}</p>` : ""}
    <div class="chips">${chips}</div>
    ${c.short_description ? `<p>${esc(c.short_description)}</p>` : ""}
    ${peopleHtml(c)}
    <div class="srcs">${site ? `<a href="${esc(site)}" target="_blank" rel="noopener">website ↗</a>${srcs ? " · " : ""}` : ""}${srcs}</div>
  </article>`;
}

let LAST_SHOWN = null;
function apply() {
  const q = $("q").value.trim().toLowerCase();
  const fv = $("f-vertical").value, fu = $("f-usecase").value,
    fm = $("f-maturity").value, fs = $("f-status").value,
    ft = $("f-type").value, fsrc = $("f-source").value, fp = $("f-people").value,
    ffund = $("f-funding").value, fcty = $("f-country").value, sort = $("s-sort").value,
    fplat = $("f-platform").value, fcap = $("f-capability").value, fseen = $("f-seen").value, fscope = $("f-scope").value,
    fera = $("f-era").value;
  const shown = ALL.filter((c) => {
    if (fplat && !c._platforms.includes(fplat)) return false;
    if (!inEra(c.founded_year, fera)) return false;
    if (fv && c.vertical !== fv) return false;
    if (fu && c._theme !== fu) return false;
    if (fcap && !(c.capabilities || []).includes(fcap)) return false;
    if (fscope && c.scope !== fscope) return false;
    if (fseen === "star" && !isStarred(c.key)) return false;
    if (fseen === "new" && seenState(c.key) !== "new") return false;
    if (fseen === "seen" && seenState(c.key) === "new") return false;
    if (fseen === "recent7" && (Date.now() - seenAt(c.key)) > 7 * 86400000) return false;
    if (fseen === "frequent" && seenCount(c.key) < 2) return false;
    if (fm && c.ai_maturity !== fm) return false;
    if (fs && c.status !== fs) return false;
    if (ft && (c.company_type || "product") !== ft) return false;
    if (ffund && fundingBucket(c) !== ffund) return false;
    if (fcty && countryOf(c) !== fcty) return false;
    if (fsrc && sourceOf(c) !== fsrc) return false;
    if (fp === "named" && !hasNamed(c)) return false;
    if (fp === "linkedin" && !hasLinkedin(c)) return false;
    if (q) {
      const hay = `${c.name} ${c.hq_location} ${c.short_description} ${c.ai_use_case || ""} ${c.key_people || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  const yr = (c) => c.founded_year || 0;
  const seen = (c) => c.last_seen || "";
  shown.sort((a, b) => {
    if (sort === "recent") return seen(b).localeCompare(seen(a)) || a.name.localeCompare(b.name);
    if (sort === "founded-new") return yr(b) - yr(a) || a.name.localeCompare(b.name);
    if (sort === "founded-old") return (yr(a) || 9999) - (yr(b) || 9999) || a.name.localeCompare(b.name);
    // These two order by MY reading history, not by the company's activity.
    // Unopened entries sort last in both rather than colliding at zero.
    if (sort === "last-opened") return (seenAt(b.key) || 0) - (seenAt(a.key) || 0) || a.name.localeCompare(b.name);
    if (sort === "most-opened") return (seenCount(b.key) || 0) - (seenCount(a.key) || 0) || a.name.localeCompare(b.name);
    return a.name.localeCompare(b.name);
  });
  renderKpis(shown);
  renderBreakdowns(shown);
  LAST_SHOWN = shown;
  // Drawn from the FULL set, not the filtered one: a map that erases every
  // country you did not pick cannot be used to pick a different one.
  renderWorldMap($("world-companies"), ALL, countryOf, (place) => {
    const sel = $("f-country");
    sel.value = place || "";            // null = back to world
    sel.dispatchEvent(new Event("input", { bubbles: true }));
  }, $("f-country").value, { unit: "countries", noun: "companies", label: "Companies by country" });
  $("count").textContent = `${shown.length} of ${ALL.length}`;
  $("grid").innerHTML = shown.length
    ? shown.map(card).join("")
    : `<p class="empty">No companies match these filters.</p>`;
}

// --- People view ---------------------------------------------------------
let PEOPLE = [];

function buildPeople() {
  const rows = [];
  for (const c of ALL) {
    for (const p of c.people || []) {
      if (!p.name) continue;
      rows.push({
        name: p.name, role: p.role || "", linkedin: p.linkedin || "",
        company: c.name, vertical: c.vertical || "", status: c.status,
        // A person inherits their company's category and discovery surface, so
        // the People tab can be narrowed the same way the Companies tab is
        // ("who works in ESG?", "who did the logistics sweep turn up?").
        theme: c._theme || themeOf(c), source: sourceOf(c),
        // A person has no location of their own in the data, so they inherit
        // their company's. Honest for a map: it says where the WORK is, not
        // necessarily where the person sits.
        country: c.country || countryOf(c), hq_location: c.hq_location || "",
        // individuals carry their bio + evidence on the company row itself
        desc: c.company_type === "individual" ? c.short_description || "" : "",
        sources: c.company_type === "individual" ? (c.source_urls || []) : [],
      });
    }
  }
  // Reachable-first: people with a LinkedIn link sort above the rest, then by name.
  rows.sort((a, b) => (!!b.linkedin - !!a.linkedin) || a.name.localeCompare(b.name));
  return rows;
}

function personRow(p) {
  const nm = safeUrl(p.linkedin)
    ? `<a href="${esc(p.linkedin)}" target="_blank" rel="noopener">${esc(p.name)}</a>`
    : esc(p.name);
  return `<article class="person is-clickable" data-status="${esc(p.status)}" data-route="p/${esc(slug(p.name))}">
    ${avatarHtml(p.name, "avatar--person")}
    <div class="person__body">
      <div class="person__name">${nm}${p.linkedin ? ' <span class="li">in</span>' : ""}</div>
      <div class="person__meta">${esc(p.role)}${p.role ? " · " : ""}<strong>${esc(p.company)}</strong>${p.vertical ? ` · ${esc(p.vertical)}` : ""}</div>
    </div>
  </article>`;
}

function applyPeople() {
  const fpc = $("fp-country").value;
  const q = $("pq").value.trim().toLowerCase();
  const fv = $("fp-vertical").value, fl = $("fp-linkedin").value;
  const fth = $("fp-theme").value, fsrc = $("fp-source").value;
  const shown = PEOPLE.filter((p) => {
    if (fpc && p.country !== fpc) return false;
    if (fv && p.vertical !== fv) return false;
    if (fth && p.theme !== fth) return false;
    if (fsrc && p.source !== fsrc) return false;
    if (fl && !p.linkedin) return false;
    if (q && !`${p.name} ${p.role} ${p.company}`.toLowerCase().includes(q)) return false;
    return true;
  });
  const withLi = shown.filter((p) => p.linkedin).length;
  renderWorldMap($("world-people"), PEOPLE, (p) => p.country, (place) => {
    const sel = $("fp-country");
    sel.value = place || "";
    sel.dispatchEvent(new Event("input", { bubbles: true }));
  }, $("fp-country").value, { unit: "countries", noun: "people", label: "People by country" });
  kpisFor("people", shown, PEOPLE);
  $("pcount").textContent = `${shown.length} people · ${withLi} with LinkedIn`;
  $("people-list").innerHTML = shown.length
    ? shown.map(personRow).join("")
    : `<p class="empty">No people match.</p>`;
}

const VIEWS = ["companies", "people", "resources", "jobs", "prospects", "about"];
let CURRENT_TAB = "companies";
function showView(which) {
  CURRENT_TAB = which;
  track("tab_view", { tab: which });
  document.body.dataset.view = which;      // drives the ambient geometry
  location.hash = "";
  for (const v of VIEWS) {
    $("view-" + v).hidden = which !== v;
    const tab = $("tab-" + v);
    tab.classList.toggle("is-active", which === v);
    // Screen readers announce the selected tab from this, not from a CSS class.
    tab.setAttribute("aria-selected", String(which === v));
  }
  $("view-detail").hidden = true;
  $("tabs").hidden = false;
  $("kpis").hidden = which === "about";
  renderHint(which);
  if (which === "companies") renderKpis(LAST_SHOWN || ALL);
  else kpisFor(which);
  window.scrollTo(0, 0);
}

const slug = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

// --- Detail pages (hash-routed, deep-linkable) ---------------------------
function showDetail(html, key) {
  // Only a detail view counts as read. Scrolling a card past the viewport is
  // not evidence that anyone looked at it.
  markSeen(key);
  if (key) track("detail_view", { tab: CURRENT_TAB, label: key, opened: seenCount(key) });
  if (key) setTimeout(() => { try { renderWhatsNew(); } catch { /* pre-init */ } }, 0);
  for (const v of VIEWS) $("view-" + v).hidden = true;
  $("tabs").hidden = true;
  $("detail").innerHTML = html;
  $("view-detail").hidden = false;
  window.scrollTo(0, 0);
}

function row(label, value) {
  return value ? `<div class="drow"><dt>${esc(label)}</dt><dd>${value}</dd></div>` : "";
}

function companyDetail(c) {
  const link = (u, t) => safeUrl(u) ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t || u)}</a>` : "";
  const people = (c.people || []).map((p) => {
    const nm = safeUrl(p.linkedin) ? link(p.linkedin, p.name) : esc(p.name);
    return `<li>${nm}${p.role ? ` <span class="muted">(${esc(p.role)})</span>` : ""}</li>`;
  }).join("");
  const sources = (c.source_urls || []).map(safeUrl).filter(Boolean)
    .map((u, i) => `<li>${link(u, `Source ${i + 1}: ${u.replace(/^https?:\/\/(www\.)?/, "").slice(0, 48)}`)}</li>`).join("");
  const fund = [c.funding_stage, c.total_raised].filter(Boolean).join(" · ");
  return `<article class="detail">
    <div class="detail__head">
      ${logoHtml(c)}
      <div>
        <div class="detail__kind">${c.company_type === "individual" ? "Individual" : "Company / venture"}</div>
        <h1>${esc(c.name)}</h1>
        ${c.ai_use_case ? `<p class="usecase">${esc(c.ai_use_case)}</p>` : ""}
      </div>
    </div>
    <div class="chips">
      ${c.vertical ? `<span class="chip chip--v chip--${esc(c.vertical)}">${esc(c.vertical)}</span>` : ""}
      ${c.ai_maturity ? `<span class="chip chip--mat chip--${esc(c.ai_maturity)}">${esc(c.ai_maturity)}</span>` : ""}
      <span class="chip ${c.status === "dormant" ? "chip--dormant" : "chip--shipping"}">${esc(c.status || "")}</span>
    </div>
    ${c.short_description ? `<p class="detail__desc">${esc(c.short_description)}</p>` : ""}
    <dl class="detail__facts">
      ${row("Headquarters", esc(c.hq_location))}
      ${row("Founded", c.founded_year)}
      ${row("Vertical", esc(c.vertical))}
      ${row("AI maturity", esc(c.ai_maturity))}
      ${row("Status", esc(c.status))}
      ${row("Funding", esc(fund))}
      ${row("Website", link(c.domain ? `https://${c.domain}` : "", c.domain))}
      ${row("GitHub", link(c.github_url))}
      ${row("Product", link(c.product_url))}
      ${row("First seen", esc(c.first_seen))}
      ${row("Last seen", esc(c.last_seen))}
    </dl>
    ${people ? `<h2>People</h2><ul class="detail__list">${people}</ul>` : ""}
    ${sources ? `<h2>Sources &amp; evidence</h2><ul class="detail__list">${sources}</ul>` : ""}
  </article>`;
}

function personDetail(p) {
  const link = (u, t) => safeUrl(u) ? `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(t || u)}</a>` : "";
  return `<article class="detail">
    <div class="detail__head">
      ${avatarHtml(p.name, "avatar--person")}
      <div>
        <div class="detail__kind">Person</div>
        <h1>${esc(p.name)}</h1>
        ${p.role ? `<p class="usecase">${esc(p.role)}</p>` : ""}
      </div>
    </div>
    <div class="chips">${p.vertical ? `<span class="chip chip--v chip--${esc(p.vertical)}">${esc(p.vertical)}</span>` : ""}</div>
    ${p.desc ? `<p class="detail__desc">${esc(p.desc)}</p>` : ""}
    <dl class="detail__facts">
      ${row("Company", esc(p.company))}
      ${row("Vertical", esc(p.vertical))}
      ${row("LinkedIn", link(p.linkedin))}
    </dl>
    ${p.sources?.length ? `<h2>Sources</h2><ul class="detail__list">${p.sources.map((u) => `<li>${link(u)}</li>`).join("")}</ul>` : ""}
  </article>`;
}

let WAS_DETAIL = false;
function route() {
  const m = (location.hash || "").match(/^#\/(c|p)\/(.+)$/);
  if (!m) {
    // Coming back from a detail page: that visit changed the entry's reading
    // state, and the cards behind it still carry the badge from before it was
    // opened. Re-render so "new" becomes "seen" without a manual refresh.
    if (WAS_DETAIL) { WAS_DETAIL = false; try { apply(); renderWhatsNew(); } catch { /* pre-init */ } }
    showView(CURRENT_TAB);
    return;
  }
  WAS_DETAIL = true;
  const [, kind, id] = m;
  const key = decodeURIComponent(id);
  if (kind === "c") {
    const c = ALL.find((x) => x.key === key);
    if (c) return showDetail(companyDetail(c), c.key);
  } else if (kind === "p") {
    const p = PEOPLE.find((x) => slug(x.name) === key);
    if (p) return showDetail(personDetail(p), "p:" + slug(p.name));
  }
  showView(CURRENT_TAB);
}

// --- Resources view (papers, news, repos, videos) ------------------------
let RES = [];
const KIND_LABEL = { paper: "Paper", news: "News", blog: "Blog", repo: "Repo", video: "Video", podcast: "Podcast" };

function resCard(r) {
  const url = safeUrl(r.url);
  const title = url
    ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(r.title)}</a>`
    : esc(r.title);
  const label = r.kind === "news" && r.label ? r.label : KIND_LABEL[r.kind] || r.kind;
  const media = r.kind === "video" && r.thumb
    ? `<a class="res__thumb" href="${esc(url)}" target="_blank" rel="noopener">
         <img src="${esc(safeUrl(r.thumb))}" alt="" loading="lazy" width="480" height="360" />
         <span class="res__play" aria-hidden="true">▶</span></a>`
    : "";
  return `<article class="res res--${esc(r.kind)}">
    ${media}
    <div class="res__body">
      <div class="res__tags">
        <span class="chip chip--kind chip--${esc(r.kind)}">${esc(label)}</span>
        ${r.vertical ? `<span class="chip chip--v chip--${esc(r.vertical)}">${esc(r.vertical)}</span>` : ""}
        ${r.featured ? `<span class="chip chip--featured">★ by Ankur Napa</span>` : ""}
      </div>
      <h3 class="res__title">${title}</h3>
      ${r.meta ? `<div class="res__meta">${esc(r.meta)}</div>` : ""}
      ${r.summary ? `<p class="res__sum">${esc(r.summary)}</p>` : ""}
    </div>
  </article>`;
}

function applyRes() {
  const q = $("rq").value.trim().toLowerCase();
  const fk = $("fr-kind").value, fv = $("fr-vertical").value, fp = $("fr-platform").value;
  const fera = $("fr-era").value, fth = $("fr-theme").value;
  const shown = RES.filter((r) => {
    if (fk && r.kind !== fk) return false;
    if (fv && r.vertical !== fv) return false;
    if (fth && r.theme !== fth) return false;
    if (fp && !r._platforms.includes(fp)) return false;
    // year filter: exclude only dated items outside the range; undated items
    // (e.g. repos, videos with no year) stay visible so content is not emptied.
    if (!inEra(r.year, fera)) return false;
    if (q && !`${r.title} ${r.summary} ${r.meta}`.toLowerCase().includes(q)) return false;
    return true;
  });
  // Optional recency sort. Dated items order by their real publish date; the
  // undated ones (repos, some videos) sink to the end rather than jump around.
  const sortMode = $("fr-sort").value;
  if (sortMode === "newest" || sortMode === "oldest") {
    // Recency keys off the real date string when present (news/blogs carry a
    // full YYYY-MM-DD in `sort`; papers carry a year). Repos sort by stars,
    // which is not a date, so key on `year` to decide dated-ness and sink the
    // undated to the bottom in both directions.
    const dated = (r) => r.year != null && r.year !== "";
    const key = (r) => (`${r.sort}`.match(/^\d/) ? `${r.sort}` : `${r.year || ""}`);
    shown.sort((a, b) => {
      if (dated(a) !== dated(b)) return dated(a) ? -1 : 1;
      if (!dated(a)) return 0;
      const av = key(a), bv = key(b);
      return sortMode === "newest" ? bv.localeCompare(av) : av.localeCompare(bv);
    });
  }
  kpisFor("resources", shown, RES);
  $("rcount").textContent = `${shown.length} of ${RES.length}`;
  $("res-grid").innerHTML = shown.length
    ? shown.map(resCard).join("")
    : `<p class="empty">No resources match these filters.</p>`;
}

async function loadResources() {
  try {
    RES = await (await fetch("resources.json")).json();
  } catch { RES = []; }
  for (const r of RES) r._platforms = platformsOf(`${r.title || ""} ${r.summary || ""} ${r.meta || ""}`);
  // kind order paper/news/repo/video, featured first within a kind, then sort desc
  const order = { paper: 0, news: 1, blog: 2, repo: 3, video: 4, podcast: 5 };
  RES.sort((a, b) => (order[a.kind] - order[b.kind])
    || ((b.featured ? 1 : 0) - (a.featured ? 1 : 0))
    || (`${b.sort}`).localeCompare(`${a.sort}`));
  if (!RES.length) { $("tab-resources").hidden = true; return; }
  fillSelect($("fr-vertical"), [...new Set(RES.map((r) => r.vertical).filter(Boolean))].sort());
  fillSelect($("fr-platform"), counts(RES.flatMap((r) => r._platforms).map((p) => ({ p })), "p").map((x) => x[0]));
  // theme is precomputed in build_resources.py with the same classifier the
  // companies use, so the two taxonomies stay identical.
  fillSelect($("fr-theme"), counts(RES.filter((r) => r.theme), "theme").map((x) => x[0]));
  // Papers reach back to 1994 but 188 of 259 dated items are 2020s, so the
  // recent buckets are the ones that earn a place here.
  fillEras($("fr-era"), RES, (r) => r.year);
  for (const id of ["rq", "fr-kind", "fr-vertical", "fr-platform", "fr-era", "fr-sort", "fr-theme"]) $(id).addEventListener("input", applyRes);
  applyRes();

}

// --- Jobs view (open roles in the same field) ----------------------------
let JOBS = [];

function jobCard(j) {
  const url = safeUrl(j.url);
  const title = url
    ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(j.title)}</a>`
    : esc(j.title);
  const meta = [j.location, j.posted ? `posted ${j.posted}` : ""].filter(Boolean).join(" · ");
  return `<article class="res res--job">
    <div class="res__body">
      <div class="res__tags">
        <span class="chip chip--kind">Job</span>
        ${j.vertical ? `<span class="chip chip--v chip--${esc(j.vertical)}">${esc(j.vertical)}</span>` : ""}
        ${j.tracked_company ? `<span class="chip chip--featured">★ on the radar</span>` : ""}
      </div>
      <h3 class="res__title">${title}</h3>
      <div class="res__meta">${esc(j.company)}${meta ? " · " + esc(meta) : ""}</div>
    </div>
  </article>`;
}

async function loadJobs() {
  try { JOBS = await (await fetch("jobs.json")).json(); } catch { JOBS = []; }
  if (!JOBS.length) { $("tab-jobs").hidden = true; return; }
  const latest = JOBS.map((j) => j.posted).filter(Boolean).sort().pop();
  if (latest) $("jobs-stamp").textContent = `Latest posting ${latest}.`;
  // Join each role to its tracked company so roles can be narrowed by category
  // the same way companies and people are. Only some roles are at a tracked
  // company, so j._theme is often empty; the filter handles that explicitly.
  const byName = new Map(ALL.map((c) => [c.name.toLowerCase(), c]));
  for (const j of JOBS) {
    const c = j.tracked_company ? byName.get(j.tracked_company.toLowerCase()) : null;
    j._theme = c ? (c._theme || themeOf(c)) : "";
  }
  fillSelect($("fj-vertical"), [...new Set(JOBS.map((j) => j.vertical).filter(Boolean))].sort());
  fillSelect($("fj-theme"), counts(JOBS.filter((j) => j._theme), "_theme").map((x) => x[0]));
  // countries by volume, so the places actually hiring sit at the top
  fillSelect($("fj-country"), counts(JOBS, "country").filter(([c]) => c !== "unknown"));
  const applyJobs = () => {
    const q = $("jq").value.trim().toLowerCase();
    const fv = $("fj-vertical").value, ft = $("fj-tracked").value, fc = $("fj-country").value;
    const fth = $("fj-theme").value;
    const shown = JOBS.filter((j) =>
      (!fv || j.vertical === fv) && (!ft || j.tracked_company) && (!fc || j.country === fc)
      && (!fth || j._theme === fth)
      && (!q || `${j.title} ${j.company} ${j.location}`.toLowerCase().includes(q)));
    renderWorldMap($("world-jobs"), JOBS, (j) => j.country, (place) => {
      const sel = $("fj-country");
      sel.value = place || "";
      sel.dispatchEvent(new Event("input", { bubbles: true }));
    }, $("fj-country").value, { unit: "countries", noun: "roles", label: "Open roles by country" });
    kpisFor("jobs", shown, JOBS);
    $("jcount").textContent = `${shown.length} of ${JOBS.length}`;
    $("jobs-grid").innerHTML = shown.length
      ? shown.map(jobCard).join("")
      : `<p class="empty">No open roles match these filters.</p>`;
  };
  for (const id of ["jq", "fj-vertical", "fj-country", "fj-tracked", "fj-theme"]) $(id).addEventListener("input", applyJobs);
  applyJobs();
}

// --- Prospects view (PRIVATE: who to pitch) ------------------------------
// prospects.json is gitignored, so on the published site the fetch 404s, this
// returns early, and the tab stays hidden. The data never ships. Do not
// "fix" that by committing the file: this repo is public.
let PROSPECTS = [];
const TIER_LABEL = {
  1: "Best fit, will pay",
  2: "Corporate, long cycle",
  3: "Volume SaaS play",
  4: "Channel multiplier",
  5: "Adjacent buyer",
};

function prospectCard(p) {
  const url = safeUrl(p.url);
  const name = url
    ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(p.company)}</a>`
    : esc(p.company);
  const field = (label, val) =>
    val ? `<div class="res__meta"><strong>${label}:</strong> ${esc(val)}</div>` : "";
  return `<article class="res res--job">
    <div class="res__body">
      <div class="res__tags">
        <span class="chip chip--kind">Tier ${esc(String(p.tier))}</span>
        ${p.vertical ? `<span class="chip chip--v chip--${esc(p.vertical)}">${esc(p.vertical)}</span>` : ""}
        ${p.region ? `<span class="chip">${esc(p.region)}</span>` : ""}
        ${(p.capabilities || []).map(capChip).join("")}
      </div>
      <h3 class="res__title">${name}</h3>
      <div class="res__meta">${esc([p.segment, p.hq].filter(Boolean).join(" · "))}</div>
      ${field("Pain", p.pain)}
      ${field("Wedge", p.wedge)}
      ${field("Entry", p.entry)}
    </div>
  </article>`;
}

async function loadProspects() {
  try {
    const r = await fetch("prospects.json");
    if (!r.ok) throw new Error("absent");
    PROSPECTS = await r.json();
  } catch { PROSPECTS = []; }
  if (!PROSPECTS.length) return;          // published site: tab stays hidden
  $("tab-prospects").hidden = false;

  const regions = counts(PROSPECTS, "region");
  $("prospects-stamp").textContent =
    `${PROSPECTS.length} targets across ${regions.length} region${regions.length === 1 ? "" : "s"}.`;
  fillSelect($("fpr-region"), regions);
  fillSelect($("fpr-vertical"), [...new Set(PROSPECTS.map((p) => p.vertical).filter(Boolean))].sort());
  fillSelect($("fpr-tier"), [...new Set(PROSPECTS.map((p) => p.tier))].sort()
    .map((t) => `${t} — ${TIER_LABEL[t] || ""}`));
  const pcap = {};
  for (const p of PROSPECTS) for (const c of p.capabilities || []) pcap[c] = (pcap[c] || 0) + 1;
  fillSelect($("fpr-capability"),
    Object.entries(pcap).sort((a, b) => b[1] - a[1]));

  const applyProspects = () => {
    const q = $("prq").value.trim().toLowerCase();
    const fr = $("fpr-region").value, fv = $("fpr-vertical").value;
    const ft = $("fpr-tier").value ? Number($("fpr-tier").value.split(" ")[0]) : 0;
    const fc = $("fpr-capability").value;
    const shown = PROSPECTS.filter((p) =>
      (!fr || p.region === fr) && (!fv || p.vertical === fv) && (!ft || p.tier === ft)
      && (!fc || (p.capabilities || []).includes(fc))
      && (!q || `${p.company} ${p.segment} ${p.hq} ${p.pain} ${p.wedge} ${p.entry}`.toLowerCase().includes(q)));
    renderWorldMap($("world-prospects"), PROSPECTS, (p) => p.region, (place) => {
      const sel = $("fpr-region");
      sel.value = place || "";          // null = back to world
      sel.dispatchEvent(new Event("input", { bubbles: true }));
    }, $("fpr-region").value, { unit: "regions", noun: "targets", label: "Targets by region" });
    kpisFor("prospects", shown, PROSPECTS);
    $("prcount").textContent = `${shown.length} of ${PROSPECTS.length}`;
    $("prospects-grid").innerHTML = shown.length
      ? shown.map(prospectCard).join("")
      : `<p class="empty">No prospects match these filters.</p>`;
  };
  for (const id of ["prq", "fpr-region", "fpr-vertical", "fpr-tier", "fpr-capability"]) $(id).addEventListener("input", applyProspects);
  applyProspects();
}

// Headline figures follow the active filters, so the strip, the breakdown bars
// and the grid below always describe the same set of companies.
function renderBreakdowns(rows = ALL) {
  renderBars($("bd-vertical"), counts(rows, "vertical"), "f-vertical", "vertical");
  renderBars($("bd-usecase"), counts(rows, "_theme"), "f-usecase", "theme");
  renderBars($("bd-maturity"), counts(rows, "ai_maturity"), "f-maturity", "maturity");
}


// --- KPI strip, per tab --------------------------------------------------
// The strip lives outside the view containers, so it must be told which tab
// it is describing. Before this it always showed company figures, which meant
// the Jobs and Prospects tabs displayed numbers about something else entirely.
// Every tab's filter function calls kpisFor(), so the strip tracks filters.
function paintKpis(cards) {
  $("kpis").innerHTML = cards.map(([num, label, sub]) => `
    <div class="kpi">
      <span class="kpi__num">${num}</span>
      <span class="kpi__label">${esc(label)}</span>
      <span class="kpi__sub">${esc(sub)}</span>
    </div>`).join("");
}

const uniq = (rows, f) => new Set(rows.map(f).filter(Boolean)).size;
// "1 regions" reads as a bug even when the number is right. Naive s-stripping
// is not enough: it turns "companies" into "companie".
const plural = (n, word) => {
  if (n === 1) return word.replace(/ies$/, "y").replace(/([^s])s$/, "$1");
  return word;
};
const sub = (shown, total, noun) =>
  shown === total ? noun : `of ${total} ${noun}`;

const KPI_BUILDERS = {
  people: (rows, all) => [
    [rows.length, rows.length === all.length ? "people" : "matching", sub(rows.length, all.length, "named people")],
    [rows.filter((p) => p.linkedin).length, "with LinkedIn", "directly reachable"],
    [uniq(rows, (p) => p.company), plural(uniq(rows, (p) => p.company), "companies"), "they work across"],
    [uniq(rows, (p) => p.vertical), plural(uniq(rows, (p) => p.vertical), "verticals"), "beer · whiskey · wine"],
  ],
  resources: (rows, all) => [
    [rows.length, rows.length === all.length ? "resources" : "matching", sub(rows.length, all.length, "resources")],
    [rows.filter((r) => r.kind === "paper").length, plural(rows.filter((r) => r.kind === "paper").length, "papers"), "peer-reviewed research"],
    [rows.filter((r) => r.kind === "repo").length, plural(rows.filter((r) => r.kind === "repo").length, "repositories"), "open-source code"],
    [uniq(rows, (r) => r.vertical), plural(uniq(rows, (r) => r.vertical), "verticals"), "covered"],
  ],
  jobs: (rows, all) => [
    [rows.length, rows.length === all.length ? "open roles" : "matching", sub(rows.length, all.length, "open roles")],
    [rows.filter((j) => j.tracked_company).length, "on the radar", "employer already tracked"],
    [uniq(rows, (j) => j.company), plural(uniq(rows, (j) => j.company), "employers"), "hiring right now"],
    [uniq(rows, (j) => j.country), plural(uniq(rows, (j) => j.country), "countries"), "where the roles are"],
  ],
  prospects: (rows, all) => [
    [rows.length, rows.length === all.length ? "targets" : "matching", sub(rows.length, all.length, "targets")],
    [rows.filter((p) => p.tier <= 2).length, "actionable", "tier 1-2, named and sourced"],
    [uniq(rows, (p) => p.region), plural(uniq(rows, (p) => p.region), "regions"), "covered"],
    [rows.filter((p) => p.tier === 4).length, "channel", "events, bodies, partners"],
  ],
};

// Last filtered set per tab, so switching tabs repaints the right figures
// without re-running that tab's filter.
const KPI_STATE = {};
function kpisFor(tab, rows, all) {
  if (rows) KPI_STATE[tab] = [rows, all];
  const state = KPI_STATE[tab];
  if (CURRENT_TAB !== tab || !state) return;
  const build = KPI_BUILDERS[tab];
  if (build) paintKpis(build(state[0], state[1]));
}

function renderKpis(rows = ALL) {
  const n = rows.length;
  const filtered = n !== ALL.length;
  const active = rows.filter((c) => c.status === "active").length;
  const shipping = rows.filter((c) => c.ai_maturity === "shipping").length;
  const individuals = rows.filter((c) => c.company_type === "individual").length;
  const peopleCount = rows.reduce((s, c) => s + (c.people?.length || 0), 0);
  const verticals = new Set(rows.map((c) => c.vertical).filter(Boolean)).size;
  const cards = [
    [n, filtered ? "matching" : "tracked", filtered ? `of ${ALL.length} companies & ventures` : "companies & ventures"],
    [active, "active", "seen in the last 18 months"],
    [shipping, "shipping", "product in market, not just research"],
    [verticals, plural(verticals, "verticals"), "beer · whiskey · wine · multiple"],
    [peopleCount, "people", `named across the landscape`],
    [individuals, "individuals", "solo builders, not just companies"],
  ];
  $("kpis").innerHTML = cards.map(([num, label, sub]) => `
    <div class="kpi">
      <span class="kpi__num">${num}</span>
      <span class="kpi__label">${esc(label)}</span>
      <span class="kpi__sub">${esc(sub)}</span>
    </div>`).join("");
  if (!filtered) $("meta").textContent = `${n} entries · ${active} active · ${peopleCount} people.`;
}


// --- Period buckets --------------------------------------------------------
// The year filters were two selects each, listing every distinct year in the
// data: 1847, 1857, 1864, one company apiece, 36 options to pick a range from.
// Nobody wants "founded between 1857 and 1903". These are the periods people
// actually think in, each carrying its own count so the choice is informed,
// and each derived from the data rather than hard-coded.
const NOW = new Date().getFullYear();
const ERAS = [
  { id: "recent2", label: "Last 2 years", lo: NOW - 2, hi: 9999 },
  { id: "recent5", label: "Last 5 years", lo: NOW - 5, hi: 9999 },
  { id: "2020s", label: "2020s", lo: 2020, hi: 2029 },
  { id: "2010s", label: "2010s", lo: 2010, hi: 2019 },
  { id: "2000s", label: "2000s", lo: 2000, hi: 2009 },
  { id: "pre2000", label: "Before 2000", lo: 0, hi: 1999 },
];
const eraById = (id) => ERAS.find((e) => e.id === id);

/** Build the options for a period select, dropping empty buckets.
 *  Undated rows get an option of their own rather than being folded into every
 *  bucket: a large share of this data has no year, and hiding that inside the
 *  other choices made "2010s (52)" return 159. */
function fillEras(el, rows, yearOf, only) {
  const pool = only ? ERAS.filter((e) => only.includes(e.id)) : ERAS;
  for (const e of pool) {
    const n = rows.filter((r) => { const y = yearOf(r); return y && y >= e.lo && y <= e.hi; }).length;
    if (!n) continue;
    const o = document.createElement("option");
    o.value = e.id;
    o.textContent = `${e.label} (${n})`;
    el.appendChild(o);
  }
  const undated = rows.filter((r) => !yearOf(r)).length;
  if (undated) {
    const o = document.createElement("option");
    o.value = "undated";
    o.textContent = `No year recorded (${undated})`;
    el.appendChild(o);
  }
}

/** True when the row passes. Every option's count now matches the number of
 *  results it produces, which is the property that makes a count worth
 *  showing at all. */
function inEra(year, eraId) {
  if (!eraId) return true;
  if (eraId === "undated") return !year;
  if (!year) return false;
  const e = eraById(eraId);
  return !!e && year >= e.lo && year <= e.hi;
}

// --- Icons ---------------------------------------------------------------
// Inline SVG rather than emoji: emoji render as a different glyph on every
// platform (and in colour), which fights the line-art look and makes the UI
// inconsistent between machines. One stroke weight, one viewBox, currentColor.
const ICON_ATTRS = 'viewBox="0 0 16 16" fill="none" stroke="currentColor" ' +
  'stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';

// Capability marks are deliberately generic, not vendor logos: real product
// logos are trademarked artwork and there is no CDN to serve them from.
const CAP_ICONS = {
  "IoT & sensing": `<svg ${ICON_ATTRS}><circle cx="8" cy="8" r="1.6"/><path d="M5.2 5.2a4 4 0 0 0 0 5.6M10.8 10.8a4 4 0 0 0 0-5.6"/><path d="M3.1 3.1a7 7 0 0 0 0 9.8M12.9 12.9a7 7 0 0 0 0-9.8"/></svg>`,
  "AI & ML": `<svg ${ICON_ATTRS}><rect x="5" y="5" width="6" height="6" rx="1.2"/><path d="M6.6 2.6v2.4M9.4 2.6v2.4M6.6 11v2.4M9.4 11v2.4"/><path d="M2.6 6.6h2.4M2.6 9.4h2.4M11 6.6h2.4M11 9.4h2.4"/></svg>`,
  "ERP & systems of record": `<svg ${ICON_ATTRS}><ellipse cx="8" cy="4" rx="4.6" ry="1.8"/><path d="M3.4 4v8c0 1 2.1 1.8 4.6 1.8s4.6-.8 4.6-1.8V4"/><path d="M3.4 8c0 1 2.1 1.8 4.6 1.8s4.6-.8 4.6-1.8"/></svg>`,
  "BI & analytics": `<svg ${ICON_ATTRS}><path d="M2.8 13.2h10.4"/><rect x="4" y="8.4" width="2" height="4.2" rx=".4"/><rect x="7" y="5.6" width="2" height="7" rx=".4"/><rect x="10" y="3.2" width="2" height="9.4" rx=".4"/></svg>`,
  "ESG & sustainability": `<svg ${ICON_ATTRS}><path d="M8 13.4c0-4.4 1.8-7.4 5.2-8.4.6 4.8-1.4 8-5.2 8.4Z"/><path d="M8 13.4C8 9.8 6.5 7.4 3.6 6.6 3 10.6 4.8 13 8 13.4Z"/><path d="M8 13.4v-2.2"/></svg>`,
  "Consultancy & services": `<svg ${ICON_ATTRS}><rect x="2.6" y="5.4" width="10.8" height="7.2" rx="1.2"/><path d="M6 5.4V4.2a1.2 1.2 0 0 1 1.2-1.2h1.6A1.2 1.2 0 0 1 10 4.2v1.2"/><path d="M2.6 8.6h10.8"/></svg>`,
};
const capChip = (name) =>
  `<span class="chip chip--cap">${CAP_ICONS[name] || ""}${esc(name)}</span>`;

// --- World map -----------------------------------------------------------
// A real projected choropleth. world-paths.json is built once by
// scripts/build_worldmap.py from a downloaded GeoJSON and committed, so the
// page still fetches nothing external at runtime.
let WORLD_PATHS = null;

// Prospect rows carry a region, not a country, so a region paints every
// country inside it. Only countries that appear in the data need listing.
const REGION_COUNTRIES = {
  "North America": ["United States", "Canada", "Mexico"],
  "Latin America": ["Brazil", "Chile", "Argentina", "Peru", "Colombia", "Dominican Republic", "Uruguay"],
  "UK & Ireland": ["United Kingdom", "Ireland"],
  "Germany & DACH": ["Germany", "Austria", "Switzerland"],
  "Nordics": ["Sweden", "Norway", "Denmark", "Finland", "Iceland"],
  "Europe (other)": ["France", "Italy", "Spain", "Portugal", "Netherlands", "Belgium",
    "Luxembourg", "Poland", "Czechia", "Slovakia", "Greece", "Hungary", "Romania", "Estonia"],
  "Africa": ["South Africa", "Kenya", "Nigeria", "Tanzania", "Namibia", "Morocco", "Egypt", "Ethiopia"],
  "Middle East": ["Israel", "United Arab Emirates", "Saudi Arabia", "Turkey", "Lebanon", "Jordan"],
  "India": ["India"],
  "Southeast Asia": ["Vietnam", "Thailand", "Singapore", "Malaysia", "Indonesia", "Philippines", "Cambodia"],
  "Greater China": ["China", "Taiwan"],
  "Japan": ["Japan"],
  "Korea": ["Korea"],
  "Australia & NZ": ["Australia", "New Zealand"],
};

const VERT_LABEL = { beer: "beer", whiskey: "whiskey", whisky: "whisky", wine: "wine",
                     multiple: "multiple" };

// Dominant SPECIFIC vertical: "multiple" is the largest bucket overall, so
// letting it win would make most of the map say nothing about the drink.
function topVertical(rows) {
  const tally = {};
  for (const r of rows) tally[r.vertical] = (tally[r.vertical] || 0) + 1;
  const specific = Object.entries(tally)
    .filter(([k]) => k && k !== "multiple").sort((a, b) => b[1] - a[1])[0];
  return specific ? specific[0] : "multiple";
}

async function loadWorldPaths() {
  if (WORLD_PATHS) return WORLD_PATHS;
  try { WORLD_PATHS = await (await fetch("world-paths.json")).json(); }
  catch { WORLD_PATHS = { paths: {}, points: {} }; }
  return WORLD_PATHS;
}

// Synchronous by design. It runs on every filter change, and an async
// innerHTML swap there flickers and drops keyboard focus mid-render. The
// geometry is fetched once in main() before the first paint instead.
function renderWorldMap(el, rows, keyOf, onPick, activeKey, opts = {}) {
  const world = WORLD_PATHS || { paths: {}, points: {} };
  const paths = world.paths || {};
  // City-states have no drawable polygon, so they render as a marker. Without
  // them a country holding data would simply not appear.
  const points = world.points || {};
  if (!Object.keys(paths).length) { el.innerHTML = ""; return; }
  const byKey = {};
  for (const r of rows) {
    const k = keyOf(r);
    if (!k || k === "unknown") continue;
    (byKey[k] = byKey[k] || []).push(r);
  }
  // A key is either a country itself, or a region covering several.
  const countriesFor = (k) => REGION_COUNTRIES[k] || [k];
  const paint = {};                       // country -> {key, n, vertical}
  for (const [k, list] of Object.entries(byKey)) {
    for (const c of countriesFor(k)) {
      if (paths[c] || points[c])
        paint[c] = { key: k, n: list.length, vertical: topVertical(list), rows: list };
    }
  }
  const max = Math.max(1, ...Object.values(byKey).map((v) => v.length));

  const body = Object.entries(paths).map(([name, d]) => {
    const hit = paint[name];
    if (!hit) return `<path d="${d}" class="wc" />`;
    // sqrt so a 67-company US does not flatten everything else to invisible
    const w = (0.2 + 0.8 * Math.sqrt(hit.n / max)).toFixed(2);
    const on = activeKey && hit.key === activeKey ? " is-on" : "";
    return `<path d="${d}" class="wc wc--has${on}" style="--w:${w}"
      data-place="${esc(hit.key)}" data-n="${hit.n}" data-v="${esc(VERT_LABEL[hit.vertical] || "")}"
      tabindex="0" role="button" aria-label="${esc(hit.key)}: ${hit.n}"><title>${esc(hit.key)}: ${hit.n}</title></path>`;
  }).join("");

  // Inline count labels, but only where the landmass can actually hold text.
  // Below this the label spills into neighbouring countries; dense Europe is
  // covered by the tooltip instead of a pile of overlapping numbers.
  const LABEL_MIN_AREA = 260;
  const labels = world.labels || {};
  const nums = Object.entries(paint).map(([name, hit]) => {
    const l = labels[name];
    if (!l || l[2] < LABEL_MIN_AREA) return "";
    return `<text class="wc__num" x="${l[0]}" y="${l[1]}">${hit.n}</text>`;
  }).join("");

  const dots = Object.entries(points).filter(([name]) => paint[name]).map(([name, [x, y]]) => {
    const hit = paint[name];
    const w = (0.2 + 0.8 * Math.sqrt(hit.n / max)).toFixed(2);
    const on = activeKey && hit.key === activeKey ? " is-on" : "";
    return `<circle cx="${x}" cy="${y}" r="3.2" class="wc wc--has wc--dot${on}" style="--w:${w}"
      data-place="${esc(hit.key)}" data-n="${hit.n}" tabindex="0" role="button"
      aria-label="${esc(hit.key)}: ${hit.n}" data-name="${esc(name)}"></circle>`;
  }).join("");

  el.innerHTML =
    `<svg class="wmap" viewBox="0 0 1000 500" preserveAspectRatio="xMidYMid meet"
       role="group" aria-label="${esc(opts.label || "World map")}">${body}${dots}${nums}</svg>
     <button class="wmap__back" type="button">← Back to world</button>
     <div class="wtip" hidden></div>
     <div class="wdetail"></div>
     <div class="wmap__legend">
       <span class="wmap__scale"><i style="--w:.25"></i><i style="--w:.5"></i><i style="--w:.75"></i><i style="--w:1"></i></span>
       <span>few</span><span class="wmap__spacer"></span><span>many</span>
       <span class="wmap__note">${Object.keys(byKey).length} ${opts.unit || "places"} · click to filter</span>
     </div>`;
  // --- zoom -------------------------------------------------------------
  // viewBox cannot be CSS-transitioned reliably, so tween it by hand. Zooming
  // to a bbox rather than a fixed scale means a small country fills the frame
  // as usefully as a large one.
  const svgEl = el.querySelector("svg.wmap");
  const HOME = [0, 0, 1000, 500];
  function tweenViewBox(to, ms = 420) {
    // ms of 0 is the re-render restore path. Without this guard the first
    // frame computes (now - t0) / 0 === 0/0 === NaN and writes "NaN NaN NaN NaN"
    // into viewBox, which the browser rejects and the map silently stops
    // zooming.
    if (!ms) { svgEl.setAttribute("viewBox", to.join(" ")); return; }
    const from = (svgEl.getAttribute("viewBox") || HOME.join(" ")).split(/\s+/).map(Number);
    const t0 = performance.now();
    const ease = (u) => (u < .5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2);
    (function step(now) {
      const u = Math.min(1, (now - t0) / ms), k = ease(u);
      svgEl.setAttribute("viewBox", from.map((v, i) => v + (to[i] - v) * k).join(" "));
      if (u < 1) requestAnimationFrame(step);
    })(t0);
  }
  function zoomTo(placeKey, ms) {
    const parts = [...svgEl.querySelectorAll(`[data-place="${CSS.escape(placeKey)}"]`)];
    if (!parts.length) return;
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const n of parts) {
      const b = n.getBBox();
      x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y);
      x1 = Math.max(x1, b.x + b.width); y1 = Math.max(y1, b.y + b.height);
    }
    // Pad, and never zoom tighter than this: a city-state at its own bbox
    // would be a 3px dot filling the screen with no surrounding context.
    const MIN = 90;
    let w = Math.max(x1 - x0, MIN), h = Math.max(y1 - y0, MIN * 0.5);
    const pad = Math.max(w, h * 2) * 0.35;
    w += pad; h += pad / 2;
    const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    // keep the 2:1 aspect of the viewBox so nothing distorts
    if (w / h < 2) w = h * 2; else h = w / 2;
    tweenViewBox([cx - w / 2, cy - h / 2, w, h], ms === undefined ? 420 : ms);
    el.classList.add("is-zoomed");
  }
  function zoomHome() {
    tweenViewBox(HOME);
    el.classList.remove("is-zoomed");
    el.querySelector(".wdetail").innerHTML = "";
  }
  el.querySelector(".wmap__back").addEventListener("click", () => {
    zoomHome();
    onPick(null);                      // also clears the filter
  });

  // --- granular detail for the selected place ----------------------------
  function showPlaceDetail(placeKey) {
    const hit = Object.values(paint).find((h) => h.key === placeKey);
    const box = el.querySelector(".wdetail");
    if (!hit) { box.innerHTML = ""; return; }
    const rows = hit.rows.slice().sort((a, b) =>
      (b.people?.length || 0) - (a.people?.length || 0));
    box.innerHTML = `
      <div class="wdetail__h">${esc(placeKey)} · ${hit.n} ${plural(hit.n, opts.noun || "entries")}</div>
      <ul class="wdetail__list">${rows.slice(0, 40).map((r) => `
        <li>
          <span class="wdetail__n">${esc(r.name || r.company || "")}</span>
          ${r.vertical ? `<span class="chip chip--v chip--${esc(r.vertical)}">${esc(r.vertical)}</span>` : ""}
          <span class="wdetail__m">${esc(r.hq_location || r.hq || r.segment || "")}</span>
        </li>`).join("")}</ul>
      ${rows.length > 40 ? `<div class="wdetail__more">+${rows.length - 40} more in the list below</div>` : ""}`;
  }

  const tip = el.querySelector(".wtip");
  const summarise = (hit, placeName) => {
    const byV = {};
    for (const r of hit.rows) byV[r.vertical || "?"] = (byV[r.vertical || "?"] || 0) + 1;
    const verticals = Object.entries(byV).sort((a, b) => b[1] - a[1])
      .map(([v, c]) => `<span class="wtip__v">${esc(v)} ${c}</span>`).join("");
    // Name a few so the tooltip answers "who?", not just "how many?"
    const names = hit.rows.slice(0, 3)
      .map((r) => esc(r.name || r.company || "")).filter(Boolean);
    const more = hit.rows.length - names.length;
    return `<div class="wtip__h">${esc(placeName || hit.key)}</div>
      <div class="wtip__n">${hit.n} ${plural(hit.n, opts.noun || "entries")}</div>
      <div class="wtip__vs">${verticals}</div>
      ${names.length ? `<div class="wtip__list">${names.join(", ")}${more > 0 ? ` +${more} more` : ""}</div>` : ""}`;
  };
  const show = (node, e) => {
    const hit = paint[node.dataset.name || ""] ||
      Object.values(paint).find((h) => h.key === node.dataset.place);
    if (!hit) return;
    tip.innerHTML = summarise(hit, node.dataset.name || node.dataset.place);
    tip.hidden = false;
    const box = el.getBoundingClientRect();
    // Flip to the left near the right edge so the tooltip never leaves the card.
    const x = e.clientX - box.left, y = e.clientY - box.top;
    tip.style.left = `${Math.min(x + 14, box.width - tip.offsetWidth - 8)}px`;
    tip.style.top = `${Math.max(y - tip.offsetHeight - 12, 4)}px`;
  };
  el.querySelectorAll("[data-place]").forEach((n) => {
    n.addEventListener("click", () => {
      const place = n.dataset.place;
      const reselect = activeKey === place;      // clicking the active one exits
      track("map_select", { tab: CURRENT_TAB, place, entries: paint[place]?.n });
      if (reselect) { zoomHome(); } else { zoomTo(place); showPlaceDetail(place); }
      onPick(reselect ? null : place);
    });
    n.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onPick(n.dataset.place); } });
    n.addEventListener("mousemove", (e) => show(n, e));
    n.addEventListener("mouseleave", () => { tip.hidden = true; });
    n.addEventListener("focus", (e) => show(n, { clientX: box(n).left, clientY: box(n).top }));
    n.addEventListener("blur", () => { tip.hidden = true; });
  });
  function box(n) { return n.getBoundingClientRect(); }

  // apply() re-renders this element on every filter change, which would throw
  // away the zoom the user just triggered. Restore it instantly (no tween, or
  // the map would visibly re-fly on each keystroke in the search box).
  if (activeKey && paint && Object.values(paint).some((h) => h.key === activeKey)) {
    zoomTo(activeKey, 0);
    showPlaceDetail(activeKey);
  }
}

// --- Analytics ------------------------------------------------------------
// GA4 is already configured in index.html (same property as the blog) and
// honours Do Not Track there. This adds interaction events on top of pageviews.
//
// PRIVACY RULE, load-bearing: nothing identifying a PROSPECT ever leaves this
// machine. prospects.json is gitignored precisely so the buyer list stays
// private, and shipping those company names to Google would hand over exactly
// what the gitignore protects. Prospect events therefore report the action and
// a count only, never a name, region or tier.
const PRIVATE_TABS = new Set(["prospects"]);

function track(event, params = {}) {
  if (typeof window.gtag !== "function") return;   // DNT, blocker, or no GA id
  const safe = { ...params };
  if (PRIVATE_TABS.has(safe.tab) || PRIVATE_TABS.has(CURRENT_TAB)) {
    // Strip every free-text field; keep only the shape of what happened.
    for (const k of ["label", "place", "value", "name", "query"]) delete safe[k];
    safe.private = true;
  }
  try { window.gtag("event", event, safe); } catch { /* never break the UI for a metric */ }
}

// --- Filter visibility ---------------------------------------------------
// Fourteen identical underlined selects give no signal about which are set.
// This marks active controls, and renders them as removable chips with a
// clear-all, so the current filter state is readable at a glance on every tab.
function controlsOf(section) {
  // Sort is not a filter. The codebase already separates them by id prefix
  // (f- filters, s- sort), so honour that: showing "Sort: A-Z" as a removable
  // chip invites you to clear it, which would reset ordering, not narrow rows.
  return [...section.querySelectorAll("select, input[type=search]")]
    .filter((el) => !el.id.startsWith("s-"));
}

function labelFor(el) {
  if (el.tagName === "INPUT") return `"${el.value}"`;
  const opt = el.selectedOptions[0];
  return opt ? opt.textContent.replace(/\s*\(\d+\)$/, "") : el.value;
}

function refreshChips(section) {
  const bar = section._chipbar;
  const active = controlsOf(section).filter((el) => el.value);
  for (const el of controlsOf(section)) el.classList.toggle("is-active", !!el.value);
  if (!active.length) { bar.hidden = true; bar.innerHTML = ""; return; }
  bar.hidden = false;
  bar.innerHTML =
    active.map((el, i) =>
      `<button class="fchip" data-i="${i}" type="button" title="Remove this filter">
         <span class="fchip__k">${esc(el.getAttribute("aria-label") || "filter")}</span>
         <span class="fchip__v">${esc(labelFor(el))}</span><span class="fchip__x">×</span>
       </button>`).join("") +
    `<button class="fchip fchip--clear" data-clear="1" type="button">Clear all</button>`;
  bar.querySelectorAll("[data-i]").forEach((b) => b.addEventListener("click", () => {
    const el = active[+b.dataset.i];
    el.value = "";
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }));
  bar.querySelector("[data-clear]").addEventListener("click", () => {
    for (const el of controlsOf(section)) el.value = "";
    controlsOf(section)[0].dispatchEvent(new Event("input", { bubbles: true }));
    for (const el of controlsOf(section)) el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

// A view is the value of every filter control in a section. Storing values
// rather than a URL keeps it working when the filter set changes: an unknown
// id is simply skipped on restore instead of breaking the whole view.
function captureView(section) {
  const out = {};
  for (const el of controlsOf(section)) if (el.value) out[el.id] = el.value;
  return out;
}

function restoreView(section, values) {
  for (const el of controlsOf(section)) el.value = values[el.id] || "";
  controlsOf(section)[0]?.dispatchEvent(new Event("input", { bubbles: true }));
  for (const el of controlsOf(section)) el.dispatchEvent(new Event("input", { bubbles: true }));
}

function renderViews(section, tab) {
  const bar = section._viewbar;
  const views = savedViews().filter((v) => v.tab === tab);
  bar.innerHTML =
    views.map((v) => `<span class="vchip"><button data-load="${esc(v.name)}" type="button">${esc(v.name)}</button>
       <button class="vchip__x" data-del="${esc(v.name)}" type="button" aria-label="Delete view">×</button></span>`).join("") +
    `<button class="vchip vchip--add" data-save="1" type="button">+ Save this view</button>`;
  bar.querySelectorAll("[data-load]").forEach((b) => b.addEventListener("click", () =>
    restoreView(section, views.find((v) => v.name === b.dataset.load).values)));
  bar.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", () => {
    deleteView(b.dataset.del); renderViews(section, tab);
  }));
  bar.querySelector("[data-save]").addEventListener("click", () => {
    const values = captureView(section);
    if (!Object.keys(values).length) { alert("Set at least one filter before saving a view."); return; }
    const name = prompt("Name this view", "");
    if (!name) return;
    track("view_save", { tab, filters: Object.keys(values).length });
    saveView(name.trim(), tab, values);
    renderViews(section, tab);
  });
}

// On a phone the filter row is 16 stacked controls, 818px tall, taller than
// the screen itself, and the map adds another. Between the hero, the KPI strip
// and both, the first actual result sat 4.3 screens down: the page opened on
// its own chrome rather than on its content. Both collapse behind a toggle
// below 720px and stay open on desktop, where there is room for them.
function makeCollapsible(el, label, openByDefault) {
  const bar = document.createElement("button");
  bar.type = "button";
  bar.className = "disclose";
  bar.setAttribute("aria-expanded", String(openByDefault));
  bar.innerHTML = `<span>${esc(label)}</span><span class="disclose__c"></span>`;
  el.insertAdjacentElement("beforebegin", bar);
  el.classList.add("collapsible");
  const set = (open) => {
    el.classList.toggle("is-open", open);
    bar.setAttribute("aria-expanded", String(open));
  };
  set(openByDefault);
  bar.addEventListener("click", () => set(bar.getAttribute("aria-expanded") !== "true"));
  return { bar, set };
}

function wireCollapsibles() {
  const phone = window.matchMedia("(max-width: 720px)");
  const made = [];
  for (const section of document.querySelectorAll(".controls")) {
    const n = section.querySelectorAll("select, input").length;
    made.push(makeCollapsible(section, `Filters & search (${n})`, !phone.matches));
  }
  for (const card of document.querySelectorAll(".wmap-card")) {
    made.push(makeCollapsible(card, "Map", !phone.matches));
  }
  // Breakdown bars are secondary analysis, and 646px of it on a phone sits
  // between the reader and every result.
  for (const bd of document.querySelectorAll(".breakdowns")) {
    made.push(makeCollapsible(bd, "Breakdowns", !phone.matches));
  }
  // Follow the breakpoint live rather than only at load, so rotating a phone
  // or resizing a window does not leave the page in the wrong mode.
  phone.addEventListener("change", (e) => made.forEach((m) => m.set(!e.matches)));
}

function wireFilterVisibility() {
  for (const section of document.querySelectorAll(".controls")) {
    const bar = document.createElement("div");
    bar.className = "chipbar";
    bar.hidden = true;
    section.insertAdjacentElement("afterend", bar);
    section._chipbar = bar;
    const vbar = document.createElement("div");
    vbar.className = "viewbar";
    bar.insertAdjacentElement("afterend", vbar);
    section._viewbar = vbar;
    const tab = section.closest("main")?.id.replace("view-", "") || "companies";
    renderViews(section, tab);
    section.addEventListener("input", (e) => {
      refreshChips(section);
      const el = e.target;
      if (el && el.id) track("filter_change", { tab, filter: el.id, set: !!el.value, value: el.value });
    });
    refreshChips(section);
  }
}

// --- What is new since the previous visit --------------------------------
// first_seen is the date an entry entered the radar. Comparing it to the
// timestamp of the LAST visit (captured before this one overwrote it) answers
// "what changed while I was away", which a plain count never can.
function newSincePrevious() {
  if (!PREVIOUS_VISIT) return [];        // first ever visit: everything is new, which is not news
  return ALL.filter((c) => c.first_seen && Date.parse(c.first_seen) > PREVIOUS_VISIT);
}

function renderWhatsNew() {
  const box = $("whatsnew");
  const fresh = newSincePrevious();
  const counts = seenCounts(ALL.map((c) => c.key));
  const stars = starCount();
  const bits = [];
  if (fresh.length) bits.push(`<strong>${fresh.length}</strong> added since your last visit`);
  if (counts.new) bits.push(`<strong>${counts.new}</strong> you have not opened`);
  if (stars) bits.push(`<strong>${stars}</strong> shortlisted`);
  if (!bits.length) { box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML = `<div class="wnew">
    <span class="wnew__t">${bits.join(" · ")}</span>
    ${counts.new ? `<button class="wnew__b" data-act="unread" type="button">Show unopened</button>` : ""}
    ${stars ? `<button class="wnew__b" data-act="stars" type="button">Show shortlist</button>` : ""}
    <button class="wnew__b wnew__b--q" data-act="reset" type="button" title="Forget what I have read">Reset reading history</button>
  </div>`;
  box.querySelectorAll("[data-act]").forEach((b) => b.addEventListener("click", () => {
    const act = b.dataset.act;
    if (act === "reset") {
      if (!confirm("Forget which entries you have opened? Shortlist and saved views are kept.")) return;
      clearSeen();
    } else {
      showView("companies");
      $("f-seen").value = act === "stars" ? "star" : "new";
      $("f-seen").dispatchEvent(new Event("input", { bubbles: true }));
    }
    apply();
    renderWhatsNew();
  }));
}

// --- First-run guidance ---------------------------------------------------
const HINTS = {
  companies: "Companies &amp; ventures are who <em>builds</em> beverage AI. Click any country on the map to filter, or press <kbd>⌘K</kbd> to jump anywhere.",
  prospects: "Prospects are who might <em>buy</em> it — the opposite list. Tier 1-2 are named and sourced; tier 3-5 are curated categories.",
  jobs: "Open roles applying AI and data in drinks. Every row links to the original posting.",
  resources: "Papers, news, case studies, repositories and talks, each with a source.",
};
function renderHint(tab) {
  const bar = $("hintbar");
  const text = HINTS[tab];
  if (!text || hintDismissed(tab)) { bar.hidden = true; return; }
  bar.hidden = false;
  bar.innerHTML = `<div class="hint"><span>${text}</span>
    <button class="hint__x" type="button" aria-label="Dismiss">Got it</button></div>`;
  bar.querySelector(".hint__x").addEventListener("click", () => {
    dismissHint(tab);
    bar.hidden = true;
  });
}

async function main() {
  let data;
  try {
    data = await (await fetch("data.json")).json();
    // Fetched here, before the first apply(): renderWorldMap is synchronous and
    // apply() paints the map, so the geometry has to already be in hand.
    await loadWorldPaths();
  } catch {
    $("grid").innerHTML = `<p class="empty">Could not load data.json. Run <code>radar export</code> first.</p>`;
    return;
  }
  ALL = Array.isArray(data) ? data : data.companies || [];
  for (const c of ALL) {
    c._theme = themeOf(c);
    c._platforms = platformsOf(`${c.short_description || ""} ${c.ai_use_case || ""}`);
  }

  renderKpis();

  renderBreakdowns();

  fillSelect($("f-vertical"), counts(ALL, "vertical"));
  fillSelect($("f-usecase"), counts(ALL, "_theme").map((p) => p[0]));
  fillSelect($("f-maturity"), counts(ALL, "ai_maturity"));
  // Multi-valued, so counts() (which reads one field) does not apply here.
  const capTally = {};
  for (const c of ALL) for (const k of c.capabilities || []) capTally[k] = (capTally[k] || 0) + 1;
  fillSelect($("f-capability"),
    Object.entries(capTally).sort((a, b) => b[1] - a[1]));
  fillSelect($("f-type"), counts(ALL.map((c) => ({ company_type: c.company_type || "product" })), "company_type").map((p) => p[0]));
  fillSelect($("f-platform"), counts(ALL.flatMap((c) => c._platforms).map((p) => ({ p })), "p").map((x) => x[0]));
  fillSelect($("f-funding"), counts(ALL.map((c) => ({ f: fundingBucket(c) })).filter((x) => x.f), "f").map((p) => p[0]));
  fillSelect($("f-country"), counts(ALL.filter((c) => countryOf(c)).map((c) => ({ c: countryOf(c) })), "c").map((p) => p[0]));
  fillSelect($("f-source"), counts(ALL.map((c) => ({ source: sourceOf(c) })), "source").map((p) => p[0]));
  // A company founded last year is not "recent" the way a paper is, so the
  // rolling buckets are dropped here and the decades kept.
  fillEras($("f-era"), ALL, (c) => c.founded_year, ["2020s", "2010s", "2000s", "pre2000"]);
  // The tooltip quotes how many rows lack a founding year. It was hand-written
  // and had drifted to "107 of 189" against a 270-row store, so derive it.
  const noYear = ALL.filter((c) => !c.founded_year).length;
  $("f-era").title =
    `When the company was founded. ${noYear} of ${ALL.length} entries carry no founding year; ` +
    `those stay visible whichever period you pick, so this narrows rather than empties.`;

  for (const id of ["q", "f-vertical", "f-usecase", "f-capability", "f-scope", "f-seen", "f-maturity", "f-status", "f-type",
    "f-platform", "f-funding", "f-country", "f-source", "f-era", "f-people", "s-sort"]) {
    $(id).addEventListener("input", apply);
  }
  apply();

  // People view
  PEOPLE = buildPeople();
  fillSelect($("fp-vertical"), [...new Set(PEOPLE.map((p) => p.vertical).filter(Boolean))].sort());
  fillSelect($("fp-country"), counts(PEOPLE.filter((p) => p.country && p.country !== "unknown"), "country"));
  fillSelect($("fp-theme"), counts(PEOPLE, "theme").map((x) => x[0]));
  fillSelect($("fp-source"), counts(PEOPLE, "source").map((x) => x[0]));
  for (const id of ["pq", "fp-vertical", "fp-country", "fp-linkedin", "fp-theme", "fp-source"]) $(id).addEventListener("input", applyPeople);
  applyPeople();
  $("tab-companies").addEventListener("click", () => showView("companies"));
  $("tab-people").addEventListener("click", () => showView("people"));
  $("tab-resources").addEventListener("click", () => showView("resources"));
  $("tab-jobs").addEventListener("click", () => showView("jobs"));
  $("tab-prospects").addEventListener("click", () => showView("prospects"));
  $("tab-about").addEventListener("click", () => showView("about"));

  // card click -> detail route (but let inner links behave normally)
  const cardNav = (e) => {
    if (e.target.closest("a")) return;
    const el = e.target.closest("[data-route]");
    if (el) location.hash = "#/" + el.dataset.route;
  };
  $("grid").addEventListener("click", (e) => {
    const b = e.target.closest("[data-star]");
    if (!b) return;
    e.stopPropagation();                 // starring must not open the detail page
    track("star_toggle", { tab: "companies", label: b.dataset.star, on: !isStarred(b.dataset.star) });
    toggleStar(b.dataset.star);
    apply();
    renderWhatsNew();
  });
  $("grid").addEventListener("click", cardNav);
  $("people-list").addEventListener("click", cardNav);
  $("detail-back").addEventListener("click", (e) => { e.preventDefault(); location.hash = ""; });

  await loadResources();
  await loadJobs();
  await loadProspects();

  // global search: one box drives every tab + shows where matches are
  const gq = $("globalq");
  const globalSearch = () => {
    const v = gq.value;
    for (const id of ["q", "pq", "rq", "jq", "prq"]) { const el = $(id); if (el) { el.value = v; el.dispatchEvent(new Event("input")); } }
    const q = v.trim().toLowerCase();
    if (!q) { $("global-hint").innerHTML = ""; return; }
    const nC = ALL.filter((c) => `${c.name} ${c.hq_location} ${c.short_description} ${c.ai_use_case || ""} ${c.key_people || ""}`.toLowerCase().includes(q)).length;
    const nP = PEOPLE.filter((p) => `${p.name} ${p.role} ${p.company}`.toLowerCase().includes(q)).length;
    const nR = RES.filter((r) => `${r.title} ${r.summary} ${r.meta}`.toLowerCase().includes(q)).length;
    const nJ = JOBS.filter((j) => `${j.title} ${j.company} ${j.location}`.toLowerCase().includes(q)).length;
    const nPr = PROSPECTS.filter((p) => `${p.company} ${p.segment} ${p.hq} ${p.entry}`.toLowerCase().includes(q)).length;
    const seg = (n, label, view) => `<button class="ghint ${n ? "" : "is-empty"}" data-view="${view}">${n} ${label}</button>`;
    $("global-hint").innerHTML = `Found: ${seg(nC, "companies", "companies")}${seg(nP, "people", "people")}${seg(nR, "resources", "resources")}${seg(nJ, "jobs", "jobs")}${PROSPECTS.length ? seg(nPr, "prospects", "prospects") : ""}`;
    $("global-hint").querySelectorAll(".ghint").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  };
  gq.addEventListener("input", globalSearch);

  wireFilterVisibility();
  wireCollapsibles();
  renderWhatsNew();
  renderHint(CURRENT_TAB);

  // Command palette: one keystroke to any tab, country, company or person.
  // Items are built fresh on each open so they track the loaded data.
  mountPalette({
    getItems() {
      // With an empty query the palette shows `always` items: recently opened
      // entries first, then the tabs. "Where was I?" is the most common reason
      // to open it, and it should not require typing a name you half-remember.
      const recents = recentlyOpened(6).map((r) => {
        const c = ALL.find((x) => x.key === r.key);
        return c && {
          kind: "recent", label: c.name, always: true,
          hint: `${agoLabel(r.t)}${r.n > 1 ? ` · ${r.n}\u00d7` : ""}`,
          go: () => { location.hash = "#/c/" + encodeURIComponent(c.key); },
        };
      }).filter(Boolean);
      const tabs = VIEWS.filter((v) => !$("tab-" + v).hidden).map((v) => ({
        kind: "tab", label: $("tab-" + v).textContent.trim(), always: true, go: () => showView(v),
      }));
      const countries = [...new Set(ALL.map(countryOf))].filter((c) => c && c !== "unknown")
        .map((c) => ({ kind: "country", label: c, hint: "filter companies", go: () => {
          showView("companies"); $("f-country").value = c;
          $("f-country").dispatchEvent(new Event("input", { bubbles: true }));
        } }));
      const companies = ALL.map((c) => ({
        kind: "company", label: c.name, hint: c.hq_location || "",
        go: () => { location.hash = "#/c/" + encodeURIComponent(c.key); },
      }));
      const people = PEOPLE.map((pp) => ({
        kind: "person", label: pp.name, hint: pp.company || "",
        go: () => { location.hash = "#/p/" + slug(pp.name); },
      }));
      const prospects = PROSPECTS.map((pr) => ({
        kind: "target", label: pr.company, hint: `${pr.region} · tier ${pr.tier}`,
        go: () => { showView("prospects"); $("prq").value = pr.company;
                    $("prq").dispatchEvent(new Event("input", { bubbles: true })); },
      }));
      return [...recents, ...tabs, ...countries, ...companies, ...people, ...prospects];
    },
    onPick: (item) => { track("palette_pick", { kind: item.kind, label: item.label }); item.go(); },
  });
  window.addEventListener("hashchange", route);
  route();
}

main();
