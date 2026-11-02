/* Paper map: start from one paper and draw the research around it from OpenAlex.
   Similarity mixes shared references, direct citation and shared OpenAlex topics,
   so new papers whose references OpenAlex has not indexed still find neighbours. */
(function () {
  "use strict";
  const API = "https://api.openalex.org";
  const FIELDS = "id,doi,display_name,publication_year,cited_by_count,referenced_works,related_works,authorships,primary_location,abstract_inverted_index,topics,keywords";
  const LIGHT_FIELDS = "id,doi,display_name,publication_year,cited_by_count,authorships,primary_location,abstract_inverted_index";
  const TOPICS = [
    "non-alcoholic beer flavour stability", "beer staling Strecker aldehydes", "machine learning beer fermentation",
    "beer sensory prediction machine learning", "wine sensory machine learning", "whisky maturation chemistry",
    "hop aroma compounds", "brewing yeast genomics", "near infrared spectroscopy beer quality"
  ];
  const MAX_REFS = 100, MAX_CITERS = 50, BATCH = 50, NEIGHBOURS = 3, MIN_POOL = 15;
  const LABEL_ALL = 50, LABEL_MIN_R = 9, ABSTRACT_MAX = 1600;
  const DOI_RE = /10\.\d{4,9}\/[^\s?#]+/;

  const $ = (s) => document.querySelector(s);
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage blocked: this visit only */ } }
  };
  const short = (id) => String(id || "").split("/").pop();
  const doiOf = (s) => { const m = String(s || "").match(DOI_RE); return m ? m[0].toLowerCase().replace(/[.,;)]+$/, "") : ""; };
  const state = {
    nodes: [], links: [], prior: [], origin: null, sel: null, tab: "radar",
    radar: [], radarDois: new Map(), saved: store.get("pm-saved", [])
  };

  function status(msg, isErr) {
    const s = $("#pm-status"); s.textContent = msg; s.classList.toggle("is-err", Boolean(isErr));
  }

  async function api(path, params) {
    const url = new URL(API + path);
    Object.entries(params || {}).forEach(([k, v]) => url.searchParams.set(k, v));
    const key = store.get("pm-key", "");
    if (key) url.searchParams.set("api_key", key);
    const r = await fetch(url);
    if (r.status === 429) throw new Error("OpenAlex free budget is used up for today. Add a free API key at the bottom of the page or try tomorrow.");
    if (r.status === 404) throw new Error("OpenAlex has no record of that paper.");
    if (!r.ok) throw new Error("OpenAlex returned " + r.status + ".");
    return r.json();
  }

  async function byIds(ids, select) {
    const out = [];
    for (let i = 0; i < ids.length; i += BATCH) {
      const chunk = ids.slice(i, i + BATCH).map(short).join("|");
      const d = await api("/works", { filter: "openalex_id:" + chunk, "per-page": BATCH, select: select || FIELDS });
      out.push(...d.results);
    }
    return out;
  }

  function abstract(inv) {
    if (!inv) return "";
    const words = [];
    Object.entries(inv).forEach(([w, pos]) => pos.forEach((p) => { words[p] = w; }));
    return words.join(" ");
  }
  function authors(w) {
    const a = (w.authorships || []).map((x) => x.author && x.author.display_name).filter(Boolean);
    return a.length > 3 ? a.slice(0, 3).join(", ") + " et al." : a.join(", ");
  }
  const venue = (w) => (w.primary_location && w.primary_location.source && w.primary_location.source.display_name) || "";
  const onRadar = (w) => state.radarDois.get(doiOf(w.doi));

  async function loadRadar() {
    try {
      const r = await fetch("resources.json");
      if (!r.ok) throw new Error(String(r.status));
      const all = await r.json();
      state.radar = all.filter((x) => x.kind === "paper" && doiOf(x.url))
        .sort((a, b) => (b.year || 0) - (a.year || 0));
      state.radar.forEach((x) => state.radarDois.set(doiOf(x.url), x));
    } catch (e) {
      state.radar = [];
    }
    if (state.tab === "radar") renderList();
  }

  async function search(text) {
    text = String(text || "").trim();
    if (!text) return;
    const doi = doiOf(text);
    const wid = text.match(/^W\d+$/i);
    if (doi || wid) return build(doi ? "doi:" + doi : wid[0].toUpperCase());
    status("Searching OpenAlex...");
    try {
      const d = await api("/works", { search: text, "per-page": 12, select: "id,doi,display_name,publication_year,cited_by_count,authorships,primary_location" });
      setTab("graph", false);
      const ol = $("#pm-items"); ol.replaceChildren();
      if (!d.results.length) ol.append(empty("Nothing found. Try other words."));
      d.results.forEach((w) => ol.append(item(w.id, w.display_name,
        [w.publication_year || "n.d.", w.cited_by_count + " citations", venue(w)].filter(Boolean).join(" · "),
        () => build(short(w.id)))));
      status(d.results.length ? "Pick a starting paper from " + d.meta.count.toLocaleString() + " matches." : "Nothing found.");
    } catch (e) { status(e.message, true); }
  }

  function item(id, title, meta, onClick) {
    const li = document.createElement("li");
    li.tabIndex = 0; li.dataset.id = id || "";
    const t = document.createElement("div"); t.className = "t"; t.textContent = title || "Untitled";
    const m = document.createElement("div"); m.className = "m"; m.textContent = meta;
    li.append(t, m);
    li.addEventListener("click", onClick);
    li.addEventListener("keydown", (e) => { if (e.key === "Enter") onClick(); });
    return li;
  }
  function empty(text) { const li = document.createElement("li"); li.className = "is-empty"; li.textContent = text; return li; }
  function button(label, fn, solid) {
    const b = document.createElement("button");
    b.type = "button"; b.className = "ghint" + (solid ? " is-solid" : ""); b.textContent = label; b.onclick = fn;
    return b;
  }

  function sets(w) {
    return {
      refs: new Set(w.referenced_works || []),
      tags: new Set([...(w.topics || []).map((t) => t.id), ...(w.keywords || []).map((k) => k.id)])
    };
  }
  function jaccard(a, b) {
    if (!a.size || !b.size) return 0;
    let n = 0; a.forEach((x) => { if (b.has(x)) n++; });
    return n / (a.size + b.size - n);
  }
  function similarity(a, b) {
    const direct = a.s.refs.has(b.id) || b.s.refs.has(a.id) ? 0.5 : 0;
    return 2 * jaccard(a.s.refs, b.s.refs) + direct + 0.5 * jaccard(a.s.tags, b.s.tags);
  }

  async function build(id) {
    status("Building the map...");
    try {
      const origin = await api("/works/" + id, { select: FIELDS });
      const oid = short(origin.id);
      const citers = (await api("/works", { filter: "cites:" + oid, "per-page": MAX_CITERS, sort: "cited_by_count:desc", select: FIELDS })).results;
      const near = [...new Set([...(origin.referenced_works || []).slice(0, MAX_REFS), ...(origin.related_works || [])])];
      let pool = [origin, ...citers, ...(await byIds(near))];
      if (pool.length < MIN_POOL) {
        const words = origin.display_name.split(/\s+/).filter((x) => x.length > 3).slice(0, 8).join(" ");
        pool.push(...(await api("/works", { search: words, "per-page": 40, select: FIELDS })).results);
      }
      const seen = new Set();
      pool = pool.filter((w) => w && !seen.has(w.id) && seen.add(w.id));
      pool.forEach((w) => { w.s = sets(w); });
      graph(pool, origin.id);
      await priorWorks(pool);
      setTab("graph");
      status(state.nodes.length + " papers around: " + origin.display_name);
      select(state.nodes.find((n) => n.id === origin.id));
      try { history.replaceState(null, "", "?q=" + encodeURIComponent(oid)); } catch (e) { /* file:// may refuse */ }
    } catch (e) { status(e.message, true); }
  }

  function graph(pool, originId) {
    const origin = pool.find((w) => w.id === originId);
    const pairs = new Map();
    // ponytail: O(n^2) pair scoring, fine for the ~150 papers one map holds
    pool.forEach((a) => {
      pool.filter((b) => b !== a).map((b) => [b, similarity(a, b)]).filter((p) => p[1] > 0)
        .sort((x, y) => y[1] - x[1]).slice(0, NEIGHBOURS)
        .forEach(([b, s]) => pairs.set([a.id, b.id].sort().join(" "), { source: a.id, target: b.id, score: s }));
    });
    pool.forEach((w) => { w.toOrigin = w === origin ? Infinity : similarity(w, origin); });
    state.origin = originId;
    state.nodes = pool;
    state.links = [...pairs.values()];
    draw();
  }

  async function priorWorks(pool) {
    const ids = new Set(pool.map((w) => w.id)), count = new Map();
    pool.forEach((w) => w.s.refs.forEach((r) => { if (!ids.has(r)) count.set(r, (count.get(r) || 0) + 1); }));
    const top = [...count].filter((p) => p[1] >= 2).sort((a, b) => b[1] - a[1]).slice(0, 25);
    if (!top.length) { state.prior = []; return; }
    const works = await byIds(top.map((p) => p[0]), LIGHT_FIELDS);
    works.forEach((w) => { w.inMap = count.get(w.id); });
    state.prior = works.sort((a, b) => b.inMap - a.inMap);
  }

  function setTab(tab, render) {
    state.tab = tab;
    document.querySelectorAll(".pm-tabs .tab").forEach((b) => {
      const on = b.dataset.tab === tab;
      b.classList.toggle("is-active", on); b.setAttribute("aria-selected", String(on));
    });
    if (render !== false) renderList();
  }

  function renderList() {
    const ol = $("#pm-items"); ol.replaceChildren();
    if (state.tab === "radar") {
      if (!state.radar.length) { ol.append(empty("Radar papers load when the page is served from the Radar site.")); return; }
      state.radar.forEach((r) => ol.append(item("", r.title, [r.meta, r.theme].filter(Boolean).join(" · "), () => build("doi:" + doiOf(r.url)))));
    } else if (state.tab === "graph") {
      if (!state.nodes.length) { ol.append(empty("No map yet. Search above or start from a Radar paper.")); return; }
      [...state.nodes].sort((a, b) => b.toOrigin - a.toOrigin).forEach((w) => ol.append(item(w.id, w.display_name,
        [w.publication_year || "n.d.", w.cited_by_count + " citations", w.id === state.origin ? "starting paper" : "", onRadar(w) ? "on the Radar" : ""].filter(Boolean).join(" · "),
        () => select(w))));
    } else if (state.tab === "prior") {
      if (!state.prior.length) { ol.append(empty("No older paper is cited by two or more papers in this map.")); return; }
      state.prior.forEach((w) => ol.append(item(w.id, w.display_name, (w.publication_year || "n.d.") + " · cited by " + w.inMap + " papers in this map", () => select(w))));
    } else {
      if (!state.saved.length) { ol.append(empty("Add papers from the details panel.")); return; }
      state.saved.forEach((w) => ol.append(item(w.id, w.title, [w.year || "n.d.", w.authors].filter(Boolean).join(" · "), () => window.open(w.link, "_blank", "noopener"))));
      const li = document.createElement("li"); li.className = "pm-actions";
      li.append(button("Download list (.md)", exportList, true), button("Clear", () => { state.saved = []; store.set("pm-saved", []); renderList(); }));
      ol.append(li);
    }
    markSelected();
  }

  function select(w) {
    if (!w) return;
    state.sel = w.id;
    const p = $("#pm-panel"); p.replaceChildren();
    const tags = document.createElement("div"); tags.className = "res__tags";
    const kind = document.createElement("span"); kind.className = "chip chip--kind"; kind.textContent = w.id === state.origin ? "Starting paper" : "Paper";
    tags.append(kind);
    const r = onRadar(w);
    if (r) {
      const c = document.createElement("span");
      c.className = "chip chip--v chip--" + (r.vertical || "multiple"); c.textContent = "★ on the Radar";
      tags.append(c);
    }
    const h = document.createElement("h2"); h.textContent = w.display_name;
    const m = document.createElement("div"); m.className = "res__meta";
    m.textContent = [authors(w), w.publication_year, venue(w), w.cited_by_count != null ? w.cited_by_count + " citations" : ""].filter(Boolean).join(" · ");
    const row = document.createElement("div"); row.className = "pm-row";
    row.append(button("Open paper", () => window.open(w.doi || w.id, "_blank", "noopener"), true));
    if (w.id !== state.origin) row.append(button("Map from this paper", () => build(short(w.id))));
    row.append(button(isSaved(w) ? "In reading list" : "Add to reading list", () => { save(w); select(w); }));
    const a = document.createElement("p"); a.className = "pm-abs";
    const text = abstract(w.abstract_inverted_index);
    a.textContent = text ? (text.length > ABSTRACT_MAX ? text.slice(0, ABSTRACT_MAX) + "..." : text) : "OpenAlex has no abstract for this paper.";
    p.append(tags, h, m, row, a);
    if (r && r.summary) {
      const s = document.createElement("p"); s.className = "pm-hint";
      s.textContent = "Radar note: " + r.summary;
      p.append(s);
    }
    markSelected();
  }

  const isSaved = (w) => state.saved.some((s) => s.id === w.id);
  function save(w) {
    if (isSaved(w)) return;
    state.saved.push({ id: w.id, title: w.display_name, year: w.publication_year, authors: authors(w), venue: venue(w), link: w.doi || w.id });
    store.set("pm-saved", state.saved);
    if (state.tab === "saved") renderList();
  }

  function exportList() {
    const today = new Date().toISOString().slice(0, 10);
    const clean = (s) => String(s || "").replace(/\|/g, "/").replace(/\n/g, " ");
    const lines = [
      "---", "title: Reading list " + today, "date: " + today, "tags: [paper-map, reading-list]", "---", "",
      "# Reading list " + today, "", "From the Paper Map on Beverage-AI Radar.", "",
      "| Paper | Year | Authors | Venue | Why it matters |", "|---|---|---|---|---|",
      ...state.saved.map((s) => "| [" + clean(s.title) + "](" + s.link + ") | " + (s.year || "") + " | " + clean(s.authors) + " | " + clean(s.venue) + " |  |")
    ];
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([lines.join("\n") + "\n"], { type: "text/markdown" }));
    a.download = "Reading list " + today + ".md";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  function markSelected() {
    document.querySelectorAll("#pm-items li").forEach((li) => li.classList.toggle("is-on", Boolean(li.dataset.id) && li.dataset.id === state.sel));
    d3.selectAll("#pm-svg .node").classed("is-on", (d) => d.id === state.sel);
  }

  let sim;
  function draw() {
    $("#pm-empty").hidden = true;
    $("#pm-legend").hidden = false;
    const svg = d3.select("#pm-svg"); svg.selectAll("*").remove();
    if (sim) sim.stop();
    const box = $("#pm-svg").getBoundingClientRect();
    const years = state.nodes.map((n) => n.publication_year).filter(Boolean);
    const shade = d3.scaleLinear().domain([d3.min(years) || 2000, d3.max(years) || 2026]).range([0.25, 1]).clamp(true);
    const radius = d3.scaleSqrt().domain([0, d3.max(state.nodes, (n) => n.cited_by_count) || 1]).range([5, 26]);
    state.nodes.forEach((n) => { n.r = radius(n.cited_by_count || 0); });
    const root = svg.append("g");
    svg.call(d3.zoom().scaleExtent([0.2, 5]).on("zoom", (e) => root.attr("transform", e.transform)));
    const link = root.append("g").selectAll("line").data(state.links).join("line")
      .attr("class", "link").attr("stroke-width", (d) => 0.6 + Math.min(3, d.score * 3));
    const node = root.append("g").selectAll("g").data(state.nodes, (d) => d.id).join("g")
      .attr("class", (d) => "node" + (d.id === state.origin ? " is-origin" : "") + (onRadar(d) ? " is-radar" : ""))
      .on("click", (e, d) => select(d))
      .on("mouseenter", (e, d) => focus(d)).on("mouseleave", () => focus(null))
      .call(d3.drag()
        .on("start", (e, d) => { if (!e.active) sim.alphaTarget(0.2).restart(); d.fx = d.x; d.fy = d.y; })
        .on("drag", (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on("end", (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; }));
    node.append("circle").attr("r", (d) => d.r).attr("fill-opacity", (d) => d.publication_year ? shade(d.publication_year) : 0.3);
    node.append("title").text((d) => d.display_name + " (" + (d.publication_year || "n.d.") + ")");
    node.filter((d) => state.nodes.length <= LABEL_ALL || d.r >= LABEL_MIN_R || d.id === state.origin)
      .append("text").attr("dy", (d) => d.r + 11).attr("text-anchor", "middle")
      .text((d) => {
        const first = (d.authorships && d.authorships[0] && d.authorships[0].author && d.authorships[0].author.display_name) || "";
        return (first.split(" ").pop() + " " + (d.publication_year || "")).trim();
      });
    sim = d3.forceSimulation(state.nodes)
      .force("link", d3.forceLink(state.links).id((d) => d.id).distance((d) => 50 + 140 * (1 - Math.min(1, d.score))).strength(0.6))
      .force("charge", d3.forceManyBody().strength(-160))
      .force("collide", d3.forceCollide((d) => d.r + 3))
      .force("x", d3.forceX(box.width / 2).strength(0.05)).force("y", d3.forceY(box.height / 2).strength(0.05))
      .on("tick", () => {
        link.attr("x1", (d) => d.source.x).attr("y1", (d) => d.source.y).attr("x2", (d) => d.target.x).attr("y2", (d) => d.target.y);
        node.attr("transform", (d) => "translate(" + d.x + "," + d.y + ")");
      });
    function focus(d) {
      if (!d) { node.classed("is-dim", false); link.classed("is-dim", false); return; }
      const near = new Set([d.id]);
      state.links.forEach((l) => { if (l.source.id === d.id) near.add(l.target.id); if (l.target.id === d.id) near.add(l.source.id); });
      node.classed("is-dim", (n) => !near.has(n.id));
      link.classed("is-dim", (l) => l.source.id !== d.id && l.target.id !== d.id);
    }
  }

  // Drag handles set the side panel widths; the map keeps at least MAP_MIN pixels.
  function setupSplits() {
    const main = $(".pm-main");
    const DEF = { l: 330, r: 380 }, MIN = 220, MAP_MIN = 320;
    const cols = Object.assign({}, DEF, store.get("pm-cols", {}));
    const apply = () => {
      const room = main.clientWidth - MAP_MIN;
      ["l", "r"].forEach((k) => {
        const other = cols[k === "l" ? "r" : "l"];
        cols[k] = Math.round(Math.max(MIN, Math.min(cols[k], room - other)));
        main.style.setProperty("--pm-" + k, cols[k] + "px");
      });
      document.querySelectorAll(".pm-split").forEach((h) => h.setAttribute("aria-valuenow", cols[h.dataset.side]));
    };
    const save = () => store.set("pm-cols", cols);
    document.querySelectorAll(".pm-split").forEach((h) => {
      const k = h.dataset.side;
      h.addEventListener("pointerdown", (e) => {
        e.preventDefault(); h.setPointerCapture(e.pointerId);
        h.classList.add("is-drag"); main.classList.add("is-resizing");
        const box = main.getBoundingClientRect();
        const move = (ev) => { cols[k] = k === "l" ? ev.clientX - box.left : box.right - ev.clientX; apply(); };
        const up = () => { h.removeEventListener("pointermove", move); h.classList.remove("is-drag"); main.classList.remove("is-resizing"); save(); };
        h.addEventListener("pointermove", move);
        h.addEventListener("pointerup", up, { once: true });
      });
      h.addEventListener("dblclick", () => { cols[k] = DEF[k]; apply(); save(); });
      h.addEventListener("keydown", (e) => {
        const step = e.shiftKey ? 60 : 20;
        const grow = k === "l" ? { ArrowRight: step, ArrowLeft: -step } : { ArrowLeft: step, ArrowRight: -step };
        if (!(e.key in grow)) return;
        e.preventDefault(); cols[k] += grow[e.key]; apply(); save();
      });
    });
    apply();
    window.addEventListener("resize", apply);
    // Re-centre the map when its column changes width.
    new ResizeObserver(() => {
      if (!sim) return;
      const b = $("#pm-svg").getBoundingClientRect();
      sim.force("x", d3.forceX(b.width / 2).strength(0.05)).force("y", d3.forceY(b.height / 2).strength(0.05)).alpha(0.3).restart();
    }).observe($("#pm-graph"));
  }

  document.querySelectorAll(".pm-tabs .tab").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));
  $("#pm-form").addEventListener("submit", (e) => { e.preventDefault(); search($("#pm-q").value); });
  $("#pm-keyform").addEventListener("submit", (e) => { e.preventDefault(); store.set("pm-key", $("#pm-key").value.trim()); status("Key saved in this browser."); });
  TOPICS.forEach((t) => $("#pm-topics").append(button(t, () => { $("#pm-q").value = t; search(t); })));
  $("#pm-key").value = store.get("pm-key", "");
  setupSplits();
  renderList();
  loadRadar();
  const start = new URLSearchParams(location.search).get("q");
  if (start) { $("#pm-q").value = start; search(start); }
})();
