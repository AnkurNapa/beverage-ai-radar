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

// ai_use_case is free text (~36 distinct strings), useless as a breakdown.
// Bucket it into a handful of themes; first matching rule wins, specific first.
// ponytail: keyword heuristic, ~9 buckets / 0 "Other" on current data —
// add a rule (or a per-company override field) when a new use case lands in "Other".
const THEME_RULES = [
  [/vineyard|disease|yield|robot|germination|malting|barley/, "Agriculture & crop"],
  [/quality|computer vision|inspection|traceability/, "Quality & inspection"],
  [/sensory|flavor|recipe|taste|preference/, "Sensory & recipe"],
  [/consumer|trend|recommendation|personaliz|insight/, "Consumer & personalization"],
  [/demand|forecast|pricing|sales/, "Demand & pricing"],
  [/supply chain|logistics|container|deposit return/, "Supply chain"],
  [/genai|marketing/, "GenAI & marketing"],
  [/consult/, "Consulting"],
  [/fermentation|production|digital twin|cip\b|process|batch|maintenance|iiot|iot|line|draft|operating system|worker|knowledge|workflow|data platform|assistant|agent|sensor/, "Process & operations"],
];
const themeOf = (c) => {
  const t = (c.ai_use_case || "").toLowerCase();
  for (const [re, name] of THEME_RULES) if (re.test(t)) return name;
  return "Other";
};

// Where a company was discovered, derived from its evidence URLs + type.
function sourceOf(c) {
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
const countryOf = (c) => (c.hq_location || "").split(",").pop().trim();

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

function renderBars(el, pairs, filterId) {
  // Bars are sized against the largest row so the shape stays readable, but the
  // number people actually want is the share of the whole, so show both.
  const max = Math.max(1, ...pairs.map((p) => p[1]));
  const total = pairs.reduce((sum, p) => sum + p[1], 0) || 1;
  el.innerHTML = pairs.map(([label, n]) => {
    const pct = Math.round((n / total) * 100);
    return `
    <button class="bar" type="button" aria-pressed="false" data-key="${esc(String(label).toLowerCase())}"
      ${filterId ? `data-filter="${esc(filterId)}" data-value="${esc(label)}"` : ""}>
      <span class="bar__label">${esc(label)}</span>
      <span class="bar__n">${n}<span class="bar__sep" aria-hidden="true"> · </span><span class="bar__pct">${pct}% of ${total}</span></span>
      <span class="bar__track"><span class="bar__fill" style="width:${(n / max) * 100}%"></span></span>
    </button>`;
  }).join("");
  if (filterId) el.querySelectorAll(".bar").forEach((b) => b.addEventListener("click", () => {
    const sel = $(b.dataset.filter);
    const turningOn = sel.value !== b.dataset.value;
    sel.value = turningOn ? b.dataset.value : "";
    sel.dispatchEvent(new Event("input"));
    // one active row per panel, so the panel always shows what is filtering
    el.querySelectorAll(".bar").forEach((o) => {
      o.classList.toggle("is-on", o === b && turningOn);
      o.setAttribute("aria-pressed", String(o === b && turningOn));
    });
    $("grid").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
}

function fillSelect(el, values) {
  for (const v of values) {
    const o = document.createElement("option");
    o.value = v; o.textContent = v;
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

function card(c) {
  const individual = c.company_type === "individual";
  const chips = [
    c.vertical && `<span class="chip chip--v chip--${esc(c.vertical)}">${esc(c.vertical)}</span>`,
    individual && `<span class="chip chip--indiv">individual</span>`,
    c.company_type === "service" && `<span class="chip chip--muted">service</span>`,
    c.ai_maturity && `<span class="chip chip--mat chip--${esc(c.ai_maturity)}">${esc(c.ai_maturity)}</span>`,
    c.status === "dormant" && `<span class="chip chip--dormant">dormant</span>`,
    c.funding_stage && `<span class="chip chip--muted">${esc(c.funding_stage)}${c.total_raised ? " · " + esc(c.total_raised) : ""}</span>`,
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
    </div>
    ${c.ai_use_case ? `<p class="usecase">${esc(c.ai_use_case)}</p>` : ""}
    <div class="chips">${chips}</div>
    ${c.short_description ? `<p>${esc(c.short_description)}</p>` : ""}
    ${peopleHtml(c)}
    <div class="srcs">${site ? `<a href="${esc(site)}" target="_blank" rel="noopener">website ↗</a>${srcs ? " · " : ""}` : ""}${srcs}</div>
  </article>`;
}

function apply() {
  const q = $("q").value.trim().toLowerCase();
  const fv = $("f-vertical").value, fu = $("f-usecase").value,
    fm = $("f-maturity").value, fs = $("f-status").value,
    ft = $("f-type").value, fsrc = $("f-source").value, fp = $("f-people").value,
    ffund = $("f-funding").value, fcty = $("f-country").value, sort = $("s-sort").value,
    fplat = $("f-platform").value,
    yFrom = +$("f-from").value || 0, yTo = +$("f-to").value || 9999;
  const shown = ALL.filter((c) => {
    if (fplat && !c._platforms.includes(fplat)) return false;
    // timeline: exclude only entries whose known founded_year falls outside the
    // range. Undated entries stay visible so the filter narrows, not empties.
    if (($("f-from").value || $("f-to").value) && c.founded_year
        && (c.founded_year < yFrom || c.founded_year > yTo)) return false;
    if (fv && c.vertical !== fv) return false;
    if (fu && c._theme !== fu) return false;
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
    return a.name.localeCompare(b.name);
  });
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
  const q = $("pq").value.trim().toLowerCase();
  const fv = $("fp-vertical").value, fl = $("fp-linkedin").value;
  const shown = PEOPLE.filter((p) => {
    if (fv && p.vertical !== fv) return false;
    if (fl && !p.linkedin) return false;
    if (q && !`${p.name} ${p.role} ${p.company}`.toLowerCase().includes(q)) return false;
    return true;
  });
  const withLi = shown.filter((p) => p.linkedin).length;
  $("pcount").textContent = `${shown.length} people · ${withLi} with LinkedIn`;
  $("people-list").innerHTML = shown.length
    ? shown.map(personRow).join("")
    : `<p class="empty">No people match.</p>`;
}

let CURRENT_TAB = "companies";
function showView(which) {
  CURRENT_TAB = which;
  location.hash = "";
  for (const v of ["companies", "people", "resources", "podcasts", "about"]) {
    $("view-" + v).hidden = which !== v;
    $("tab-" + v).classList.toggle("is-active", which === v);
  }
  $("view-detail").hidden = true;
  $("tabs").hidden = false;
  window.scrollTo(0, 0);
}

const slug = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

// --- Detail pages (hash-routed, deep-linkable) ---------------------------
function showDetail(html) {
  for (const v of ["companies", "people", "resources", "podcasts", "about"]) $("view-" + v).hidden = true;
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

function route() {
  const m = (location.hash || "").match(/^#\/(c|p)\/(.+)$/);
  if (!m) { showView(CURRENT_TAB); return; }
  const [, kind, id] = m;
  const key = decodeURIComponent(id);
  if (kind === "c") {
    const c = ALL.find((x) => x.key === key);
    if (c) return showDetail(companyDetail(c));
  } else if (kind === "p") {
    const p = PEOPLE.find((x) => slug(x.name) === key);
    if (p) return showDetail(personDetail(p));
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
         <img src="${esc(safeUrl(r.thumb))}" alt="" loading="lazy" />
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
  const yFrom = +$("fr-from").value || 0, yTo = +$("fr-to").value || 9999;
  const yBound = $("fr-from").value || $("fr-to").value;
  const shown = RES.filter((r) => {
    if (fk && r.kind !== fk) return false;
    if (fv && r.vertical !== fv) return false;
    if (fp && !r._platforms.includes(fp)) return false;
    // year filter: exclude only dated items outside the range; undated items
    // (e.g. repos, videos with no year) stay visible so content is not emptied.
    if (yBound && r.year && (r.year < yFrom || r.year > yTo)) return false;
    if (q && !`${r.title} ${r.summary} ${r.meta}`.toLowerCase().includes(q)) return false;
    return true;
  });
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
  const resYears = [...new Set(RES.map((r) => r.year).filter(Boolean))].sort((a, b) => a - b);
  fillSelect($("fr-from"), resYears.map(String));
  fillSelect($("fr-to"), resYears.map(String));
  for (const id of ["rq", "fr-kind", "fr-vertical", "fr-platform", "fr-from", "fr-to"]) $(id).addEventListener("input", applyRes);
  applyRes();

  // dedicated Podcasts page
  const pods = RES.filter((r) => r.kind === "podcast");
  fillSelect($("fpod-vertical"), [...new Set(pods.map((p) => p.vertical).filter(Boolean))].sort());
  const applyPods = () => {
    const q = $("podq").value.trim().toLowerCase(), fv = $("fpod-vertical").value;
    const shown = pods.filter((p) =>
      (!fv || p.vertical === fv) && (!q || `${p.title} ${p.summary} ${p.meta}`.toLowerCase().includes(q)));
    $("podcount").textContent = `${shown.length} podcast${shown.length === 1 ? "" : "s"}`;
    $("pod-grid").innerHTML = shown.length ? shown.map(resCard).join("") : `<p class="empty">No podcasts match.</p>`;
  };
  for (const id of ["podq", "fpod-vertical"]) $(id).addEventListener("input", applyPods);
  applyPods();
  if (!pods.length) $("tab-podcasts").hidden = true;
}

function renderKpis() {
  const n = ALL.length;
  const active = ALL.filter((c) => c.status === "active").length;
  const shipping = ALL.filter((c) => c.ai_maturity === "shipping").length;
  const individuals = ALL.filter((c) => c.company_type === "individual").length;
  const peopleCount = ALL.reduce((s, c) => s + (c.people?.length || 0), 0);
  const verticals = new Set(ALL.map((c) => c.vertical).filter(Boolean)).size;
  const cards = [
    [n, "tracked", "companies & ventures"],
    [active, "active", "seen in the last 18 months"],
    [shipping, "shipping", "product in market, not just research"],
    [verticals, "verticals", "beer · whiskey · wine · multiple"],
    [peopleCount, "people", `named across the landscape`],
    [individuals, "individuals", "solo builders, not just companies"],
  ];
  $("kpis").innerHTML = cards.map(([num, label, sub]) => `
    <div class="kpi">
      <span class="kpi__num">${num}</span>
      <span class="kpi__label">${esc(label)}</span>
      <span class="kpi__sub">${esc(sub)}</span>
    </div>`).join("");
  $("meta").textContent = `${n} entries · ${active} active · ${peopleCount} people.`;
}

async function main() {
  let data;
  try {
    data = await (await fetch("data.json")).json();
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

  renderBars($("bd-vertical"), counts(ALL, "vertical"), "f-vertical");
  renderBars($("bd-usecase"), counts(ALL, "_theme"), "f-usecase");
  renderBars($("bd-maturity"), counts(ALL, "ai_maturity"), "f-maturity");

  fillSelect($("f-vertical"), counts(ALL, "vertical").map((p) => p[0]));
  fillSelect($("f-usecase"), counts(ALL, "_theme").map((p) => p[0]));
  fillSelect($("f-maturity"), counts(ALL, "ai_maturity").map((p) => p[0]));
  fillSelect($("f-type"), counts(ALL.map((c) => ({ company_type: c.company_type || "product" })), "company_type").map((p) => p[0]));
  fillSelect($("f-platform"), counts(ALL.flatMap((c) => c._platforms).map((p) => ({ p })), "p").map((x) => x[0]));
  fillSelect($("f-funding"), counts(ALL.map((c) => ({ f: fundingBucket(c) })).filter((x) => x.f), "f").map((p) => p[0]));
  fillSelect($("f-country"), counts(ALL.filter((c) => countryOf(c)).map((c) => ({ c: countryOf(c) })), "c").map((p) => p[0]));
  fillSelect($("f-source"), counts(ALL.map((c) => ({ source: sourceOf(c) })), "source").map((p) => p[0]));
  const years = [...new Set(ALL.map((c) => c.founded_year).filter(Boolean))].sort((a, b) => a - b);
  fillSelect($("f-from"), years.map(String));
  fillSelect($("f-to"), years.map(String));

  for (const id of ["q", "f-vertical", "f-usecase", "f-maturity", "f-status", "f-type",
    "f-platform", "f-funding", "f-country", "f-source", "f-from", "f-to", "f-people", "s-sort"]) {
    $(id).addEventListener("input", apply);
  }
  apply();

  // People view
  PEOPLE = buildPeople();
  fillSelect($("fp-vertical"), [...new Set(PEOPLE.map((p) => p.vertical).filter(Boolean))].sort());
  for (const id of ["pq", "fp-vertical", "fp-linkedin"]) $(id).addEventListener("input", applyPeople);
  applyPeople();
  $("tab-companies").addEventListener("click", () => showView("companies"));
  $("tab-people").addEventListener("click", () => showView("people"));
  $("tab-resources").addEventListener("click", () => showView("resources"));
  $("tab-podcasts").addEventListener("click", () => showView("podcasts"));
  $("tab-about").addEventListener("click", () => showView("about"));

  // card click -> detail route (but let inner links behave normally)
  const cardNav = (e) => {
    if (e.target.closest("a")) return;
    const el = e.target.closest("[data-route]");
    if (el) location.hash = "#/" + el.dataset.route;
  };
  $("grid").addEventListener("click", cardNav);
  $("people-list").addEventListener("click", cardNav);
  $("detail-back").addEventListener("click", (e) => { e.preventDefault(); location.hash = ""; });

  await loadResources();

  // global search: one box drives every tab + shows where matches are
  const gq = $("globalq");
  const globalSearch = () => {
    const v = gq.value;
    for (const id of ["q", "pq", "rq", "podq"]) { const el = $(id); if (el) { el.value = v; el.dispatchEvent(new Event("input")); } }
    const q = v.trim().toLowerCase();
    if (!q) { $("global-hint").innerHTML = ""; return; }
    const nC = ALL.filter((c) => `${c.name} ${c.hq_location} ${c.short_description} ${c.ai_use_case || ""} ${c.key_people || ""}`.toLowerCase().includes(q)).length;
    const nP = PEOPLE.filter((p) => `${p.name} ${p.role} ${p.company}`.toLowerCase().includes(q)).length;
    const nR = RES.filter((r) => `${r.title} ${r.summary} ${r.meta}`.toLowerCase().includes(q)).length;
    const seg = (n, label, view) => `<button class="ghint ${n ? "" : "is-empty"}" data-view="${view}">${n} ${label}</button>`;
    $("global-hint").innerHTML = `Found: ${seg(nC, "companies", "companies")}${seg(nP, "people", "people")}${seg(nR, "resources", "resources")}`;
    $("global-hint").querySelectorAll(".ghint").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
  };
  gq.addEventListener("input", globalSearch);

  window.addEventListener("hashchange", route);
  route();
}

main();
