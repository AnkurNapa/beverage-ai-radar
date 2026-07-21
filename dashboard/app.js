// Beverage-AI Radar dashboard. Reads data.json (exported by `radar export`),
// renders breakdown bars + a filterable company grid. Vanilla, no deps.

const $ = (id) => document.getElementById(id);
const esc = (s) => (s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// only http(s) links are clickable; anything else (javascript:, data:) is dropped.
const safeUrl = (u) => /^https?:\/\//i.test(u || "") ? u : "";

let ALL = [];

// Where a company was discovered, derived from its evidence URLs + type.
function sourceOf(c) {
  const urls = (c.source_urls || []).join(" ").toLowerCase();
  if (/drinktec\.com|yontex/.test(urls)) return "Drinktec";
  if (/agfundernews/.test(urls)) return "AgFunder";
  if (c.company_type === "service") return "Service research";
  return "Web research";
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

function renderBars(el, pairs) {
  const max = Math.max(1, ...pairs.map((p) => p[1]));
  el.innerHTML = pairs.map(([label, n]) => `
    <div class="bar">
      <span class="bar__label">${esc(label)}</span><span>${n}</span>
      <span class="bar__track"><span class="bar__fill" style="width:${(n / max) * 100}%"></span></span>
    </div>`).join("");
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
  const chips = [
    c.vertical && `<span class="chip">${esc(c.vertical)}</span>`,
    c.company_type === "service" && `<span class="chip chip--muted">service</span>`,
    c.ai_use_case && `<span class="chip">${esc(c.ai_use_case)}</span>`,
    c.ai_maturity && `<span class="chip chip--muted">${esc(c.ai_maturity)}</span>`,
    c.status === "dormant" && `<span class="chip chip--dormant">dormant</span>`,
    c.funding_stage && `<span class="chip chip--muted">${esc(c.funding_stage)}${c.total_raised ? " · " + esc(c.total_raised) : ""}</span>`,
  ].filter(Boolean).join("");
  const srcs = (c.source_urls || []).map(safeUrl).filter(Boolean).map((u, i) =>
    `<a href="${esc(u)}" target="_blank" rel="noopener">source ${i + 1}</a>`).join(" · ");
  return `<article class="company" data-status="${esc(c.status)}">
    <h3>${esc(c.name)}</h3>
    ${c.hq_location ? `<span class="loc">${esc(c.hq_location)}${c.founded_year ? " · founded " + c.founded_year : ""}</span>` : ""}
    <div class="chips">${chips}</div>
    ${c.short_description ? `<p>${esc(c.short_description)}</p>` : ""}
    ${peopleHtml(c)}
    ${srcs ? `<div class="srcs">${srcs}</div>` : ""}
  </article>`;
}

function apply() {
  const q = $("q").value.trim().toLowerCase();
  const fv = $("f-vertical").value, fu = $("f-usecase").value,
    fm = $("f-maturity").value, fs = $("f-status").value,
    ft = $("f-type").value, fsrc = $("f-source").value, fp = $("f-people").value;
  const shown = ALL.filter((c) => {
    if (fv && c.vertical !== fv) return false;
    if (fu && c.ai_use_case !== fu) return false;
    if (fm && c.ai_maturity !== fm) return false;
    if (fs && c.status !== fs) return false;
    if (ft && (c.company_type || "product") !== ft) return false;
    if (fsrc && sourceOf(c) !== fsrc) return false;
    if (fp === "named" && !hasNamed(c)) return false;
    if (fp === "linkedin" && !hasLinkedin(c)) return false;
    if (q) {
      const hay = `${c.name} ${c.hq_location} ${c.short_description} ${c.key_people || ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
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
      });
    }
  }
  rows.sort((a, b) => a.name.localeCompare(b.name));
  return rows;
}

function personRow(p) {
  const nm = safeUrl(p.linkedin)
    ? `<a href="${esc(p.linkedin)}" target="_blank" rel="noopener">${esc(p.name)}</a>`
    : esc(p.name);
  return `<article class="person" data-status="${esc(p.status)}">
    <div class="person__name">${nm}${p.linkedin ? ' <span class="li">in</span>' : ""}</div>
    <div class="person__meta">${esc(p.role)}${p.role ? " · " : ""}<strong>${esc(p.company)}</strong>${p.vertical ? ` · ${esc(p.vertical)}` : ""}</div>
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

function showView(which) {
  const people = which === "people";
  $("view-companies").hidden = people;
  $("view-people").hidden = !people;
  $("tab-companies").classList.toggle("is-active", !people);
  $("tab-people").classList.toggle("is-active", people);
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
  $("meta").textContent = `${ALL.length} companies tracked`;

  renderBars($("bd-vertical"), counts(ALL, "vertical"));
  renderBars($("bd-usecase"), counts(ALL, "ai_use_case"));
  renderBars($("bd-maturity"), counts(ALL, "ai_maturity"));

  fillSelect($("f-vertical"), counts(ALL, "vertical").map((p) => p[0]));
  fillSelect($("f-usecase"), counts(ALL, "ai_use_case").map((p) => p[0]));
  fillSelect($("f-maturity"), counts(ALL, "ai_maturity").map((p) => p[0]));
  fillSelect($("f-type"), counts(ALL.map((c) => ({ company_type: c.company_type || "product" })), "company_type").map((p) => p[0]));
  fillSelect($("f-source"), counts(ALL.map((c) => ({ source: sourceOf(c) })), "source").map((p) => p[0]));

  for (const id of ["q", "f-vertical", "f-usecase", "f-maturity", "f-status", "f-type", "f-source", "f-people"]) {
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
}

main();
