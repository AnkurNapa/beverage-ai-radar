// Beverage-AI Radar dashboard. Reads data.json (exported by `radar export`),
// renders breakdown bars + a filterable company grid. Vanilla, no deps.

const $ = (id) => document.getElementById(id);
const esc = (s) => (s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// only http(s) links are clickable; anything else (javascript:, data:) is dropped.
const safeUrl = (u) => /^https?:\/\//i.test(u || "") ? u : "";

let ALL = [];

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

function card(c) {
  const chips = [
    c.vertical && `<span class="chip">${esc(c.vertical)}</span>`,
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
    ${srcs ? `<div class="srcs">${srcs}</div>` : ""}
  </article>`;
}

function apply() {
  const q = $("q").value.trim().toLowerCase();
  const fv = $("f-vertical").value, fu = $("f-usecase").value,
    fm = $("f-maturity").value, fs = $("f-status").value;
  const shown = ALL.filter((c) => {
    if (fv && c.vertical !== fv) return false;
    if (fu && c.ai_use_case !== fu) return false;
    if (fm && c.ai_maturity !== fm) return false;
    if (fs && c.status !== fs) return false;
    if (q) {
      const hay = `${c.name} ${c.hq_location} ${c.short_description}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  $("count").textContent = `${shown.length} of ${ALL.length}`;
  $("grid").innerHTML = shown.length
    ? shown.map(card).join("")
    : `<p class="empty">No companies match these filters.</p>`;
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

  for (const id of ["q", "f-vertical", "f-usecase", "f-maturity", "f-status"]) {
    $(id).addEventListener("input", apply);
  }
  apply();
}

main();
