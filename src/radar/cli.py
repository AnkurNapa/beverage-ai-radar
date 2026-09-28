from __future__ import annotations
import argparse
from pathlib import Path
from datetime import date
from radar import config
from radar.store import Store
from radar.http_cache import CachedFetcher
from radar.pipeline import run
from radar.outputs.json_export import export_json
from radar.outputs.report import render_report


def _live_sources():
    """The assembled source list for a live run.

    Discovery: curated seed (reliable, human-verified) + web search (best-effort)
    + trade press (no-op until per-site parsers are added).
    Enrichment: GitHub (keyless), Crunchbase + LinkedIn (degrade to no-op).
    """
    from radar.sources.curated_seed import CuratedSeedSource
    from radar.sources.curated_people import CuratedPeopleSource
    from radar.sources.web_search import WebSearchSource, default_search_fn
    from radar.sources.trade_press import TradePressSource, DEFAULT_FEEDS, default_parse_fn
    from radar.sources.github_product import GithubProductSource
    from radar.sources.crunchbase import CrunchbaseSource
    from radar.sources.linkedin import LinkedInSource
    from radar.live_adapters import gh_lookup, cb_lookup, li_lookup

    return [
        CuratedSeedSource(config.SEED_PATH),
        CuratedPeopleSource(config.PEOPLE_SEED_PATH),
        WebSearchSource(default_search_fn),
        TradePressSource(DEFAULT_FEEDS, default_parse_fn),
        GithubProductSource(gh_lookup),
        CrunchbaseSource(cb_lookup),
        LinkedInSource(li_lookup),
    ]


def _prospects(args) -> int:
    """Private prospect verbs. Kept in one function so the public radar flow
    above stays readable, and so the private file path appears exactly once."""
    import json as _json
    from datetime import date as _date

    root = config.SEED_PATH.parent.parent
    path = config.DASHBOARD_DIR / "prospects.json"
    if not path.exists():
        print(f"no prospect list at {path} (it is gitignored by design)")
        return 1
    rows = _json.loads(path.read_text())

    if args.cmd == "prospect-gaps":
        from radar.prospects.gaps import compute, format_gaps

        print(format_gaps(compute(rows)))
    elif args.cmd == "prospect-brief":
        from radar.prospects.briefs import load_surfaces, render_briefs

        surfaces = load_surfaces(root / "data" / "prospect_surfaces.json")
        written = render_briefs(surfaces, rows, root, _date.today().isoformat())
        print(f"{len(written)} briefs in {root / '.prospects' / 'briefs'}")
        for p in written:
            print(f"  {p}")
    elif args.cmd == "prospect-merge":
        from radar.prospects.merge import load_finds, merge

        from radar.capabilities import of_prospect

        rows, added, quarantined = merge(rows, load_finds(args.files))
        # Stamped on every row, not just new ones, so a rule change takes
        # effect for the whole list on the next merge.
        for r in rows:
            r["capabilities"] = of_prospect(r)
        rows.sort(key=lambda r: (r["tier"], r["region"], r["company"]))
        path.write_text(_json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
        qdir = root / ".prospects"
        qdir.mkdir(parents=True, exist_ok=True)
        (qdir / "quarantine.json").write_text(_json.dumps(quarantined, indent=2))
        print(f"added {len(added)}")
        for r in added:
            print(f"  + [{r['tier']}] {r['company']} ({r['region']})")
        for state in ("duplicate", "rejected"):
            hits = [q for q in quarantined if q["state"] == state]
            if hits:
                print(f"{state} {len(hits)}:")
                for q in hits:
                    print(f"  - {q['company']} ({q['region']}): {q['reason']}")
        print(f"prospects now {len(rows)}")
    return 0


def _people(args) -> int:
    import json as _json
    from radar.scout.people import merge_people, render_people_briefs

    seed = _json.loads(config.PEOPLE_SEED_PATH.read_text())
    if args.cmd == "people-brief":
        surfaces = _json.loads(config.PEOPLE_SURFACES_PATH.read_text())
        written = render_people_briefs(surfaces, seed, config.SCOUT_DIR, date.today())
        print(f"{len(written)} briefs in {config.SCOUT_DIR / 'people_briefs'}")
        return 0
    from radar.coverage import record_sweep

    added, quarantined = [], []
    for f in args.files:
        data = _json.loads(open(f).read())
        found = data.get("people", []) if isinstance(data, dict) else data
        surface = Path(f).stem.removeprefix("find_")
        seed, a, q = merge_people(seed, found)
        added += a
        quarantined += q
        record_sweep(
            config.LEDGER_PATH, "people", surface, len(found), len(a), date.today().isoformat()
        )
    config.PEOPLE_SEED_PATH.write_text(_json.dumps(seed, indent=1, ensure_ascii=False) + "\n")
    (config.SCOUT_DIR / "people_quarantine.json").write_text(_json.dumps(quarantined, indent=2))
    print(f"added {len(added)}: {', '.join(p['name'] for p in added)}")
    for state in ("review", "duplicate", "rejected"):
        hits = [q for q in quarantined if q["state"] == state]
        if hits:
            print(
                f"{state} {len(hits)}: {'; '.join(q['name'] + ' (' + q['reason'] + ')' for q in hits)}"
            )
    print(f"people seed now {len(seed)}")
    return 0


def _coverage(args) -> int:
    """coverage: where every lane stands. frontier-brief: turn what the lanes
    know about each other into agent briefs, reusing the lane brief writers so
    the verification rules live in one place."""
    import json as _json
    from radar import coverage as cov
    from radar.scout.briefs import render_brief
    from radar.scout.people import render_people_brief

    companies = _json.loads(config.SEED_PATH.read_text())
    people = _json.loads(config.PEOPLE_SEED_PATH.read_text())
    jobs_path = config.DASHBOARD_DIR / "jobs.json"
    jobs = _json.loads(jobs_path.read_text()) if jobs_path.exists() else []
    front = cov.frontier(companies, people, jobs)
    today = date.today().isoformat()
    # Prospects are private: read from the gitignored list, reported to the
    # terminal, briefed and logged only under .prospects/. Never the public ledger.
    root = config.SEED_PATH.parent.parent
    p_path = config.DASHBOARD_DIR / "prospects.json"
    prospects = _json.loads(p_path.read_text()) if p_path.exists() else None
    p_ledger = root / ".prospects" / "coverage_ledger.json"
    p_front = cov.prospect_frontier(prospects, people, jobs) if prospects is not None else []

    if args.cmd == "coverage":
        grid = cov.country_grid(companies, people, jobs)
        print(f"{'country':<22}{'companies':>10}{'people':>8}{'jobs':>6}")
        for k, v in sorted(grid.items(), key=lambda kv: -kv[1]["companies"])[:30]:
            flag = "  <- thin" if v["thin"] else ""
            print(f"{k:<22}{v['companies']:>10}{v['people']:>8}{v['jobs']:>6}{flag}")
        print(f"\ncompanies with no people yet: {len(front['companies_without_people'])}")
        print(
            f"employers named by people or jobs but not tracked: {len(front['untracked_employers'])}"
        )
        if prospects is not None:
            hiring = sum(1 for r in p_front if r["hiring"])
            print(
                f"prospects (private): {len(prospects)} tracked; {len(p_front)} employers "
                f"known to the public lanes are not prospects yet, {hiring} of them hiring data roles"
            )
        for (lane, surface), r in sorted(cov.last_sweeps(config.LEDGER_PATH).items()):
            print(
                f"  last {lane}/{surface}: {r['date']} found {r.get('found', '-')} added {r.get('added', '-')}"
            )
        return 0

    skip = cov.recently_briefed(config.LEDGER_PATH, today, args.skip_days)
    todo_people = [n for n in front["companies_without_people"] if n not in skip]
    todo_orgs = [r for r in front["untracked_employers"] if r["name"] not in skip]
    people_names = sorted(f"{p['name']} | {p.get('company') or ''}" for p in people)
    (config.SCOUT_DIR / "people_skip.txt").write_text("\n".join(people_names) + "\n")
    written = []
    for i in range(args.max_briefs):
        chunk = todo_people[i * args.chunk : (i + 1) * args.chunk]
        if not chunk:
            break
        sid = f"frontier_people_{i + 1}"
        surface = {
            "id": sid,
            "label": "Frontier: tracked companies with nobody named yet",
            "hint": "Find the AI, data, analytics or digital leads AT these already-tracked "
            "companies (any country). Team pages, press, speaker lists and papers. Set "
            "company to the exact name below.\n\n" + "\n".join(f"- {n}" for n in chunk),
        }
        path = config.SCOUT_DIR / "people_briefs" / f"{sid}.md"
        path.write_text(render_people_brief(surface, people_names, config.SCOUT_DIR))
        cov.record_briefed(config.LEDGER_PATH, "frontier", sid, chunk, today)
        written.append(path)
    if todo_orgs:
        chunk = todo_orgs[: args.chunk]
        surface = {
            "id": "frontier_companies",
            "label": "Frontier: employers named by tracked people or open jobs",
            "hint": "Check each employer below against the scope rules. Include it only if it "
            "passes them; retailers, distributors and general IT firms usually do not.\n\n"
            + "\n".join(f"- {r['name']} ({'; '.join(r['evidence'][:3])})" for r in chunk),
        }
        existing = [f"{c['name']} | {c.get('domain') or ''}" for c in companies]
        path = config.SCOUT_DIR / "briefs" / "frontier_companies.md"
        path.write_text(render_brief(surface, [], existing, config.SCOUT_DIR, date.today()))
        cov.record_briefed(
            config.LEDGER_PATH, "frontier", "frontier_companies", [r["name"] for r in chunk], today
        )
        written.append(path)
    if p_front:
        from radar.prospects.briefs import render_brief as render_prospect_brief

        p_skip = cov.recently_briefed(p_ledger, today, args.skip_days)
        chunk = [r for r in p_front if r["name"] not in p_skip][: args.chunk]
        if chunk:
            surface = {
                "id": "frontier_prospects",
                "title": "Frontier: beverage employers the public lanes found",
                "regions": ["Global"],
                "scope": "Each employer below is hiring for a data role or employs someone on the "
                "public radar, but is not on the prospect list. Judge each against the tiers; "
                "vendors of beverage AI belong on the public radar, not here.\n\n"
                + "\n".join(
                    f"- {r['name']}{' [HIRING]' if r['hiring'] else ''} ({'; '.join(r['evidence'][:3])})"
                    for r in chunk
                ),
            }
            (root / ".prospects" / "briefs").mkdir(parents=True, exist_ok=True)
            written.append(
                render_prospect_brief(surface, prospects, root / ".prospects" / "briefs", today)
            )
            cov.record_briefed(
                p_ledger, "prospects", "frontier_prospects", [r["name"] for r in chunk], today
            )
    print(f"{len(todo_people)} companies need people, {len(todo_orgs)} employers need a check")
    for p in written:
        print(f"  {p}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="radar")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("export")
    sub.add_parser("report")
    sub.add_parser("gaps")
    sub.add_parser("scout-brief")
    p_merge = sub.add_parser("scout-merge")
    p_merge.add_argument("files", nargs="+")
    p_merge.add_argument("--check-domains", action="store_true")
    sub.add_parser("scout-liveness")
    sub.add_parser("coverage")
    p_front = sub.add_parser("frontier-brief")
    p_front.add_argument("--max-briefs", type=int, default=4)
    p_front.add_argument("--chunk", type=int, default=30)
    p_front.add_argument("--skip-days", type=int, default=60)
    sub.add_parser("people-brief")
    p_people = sub.add_parser("people-merge")
    p_people.add_argument("files", nargs="+")
    # Prospects: the PRIVATE outreach list. Separate verbs and a separate file
    # from the vendor seed, because this data must never reach the public site.
    sub.add_parser("prospect-gaps")
    sub.add_parser("prospect-brief")
    p_pmerge = sub.add_parser("prospect-merge")
    p_pmerge.add_argument("files", nargs="+")
    args = parser.parse_args(argv)

    store = Store(config.DB_PATH)
    if args.cmd == "run":
        fetcher = CachedFetcher(config.HTTP_CACHE_DIR)
        summary = run(
            store, fetcher, _live_sources(), config.DASHBOARD_DIR, config.VAULT_DIR, date.today()
        )
        print(summary)
    elif args.cmd == "export":
        export_json(store, config.DASHBOARD_DIR / "data.json")
        print("exported")
    elif args.cmd == "report":
        print(render_report(store))
    elif args.cmd == "gaps":
        from radar.scout.gaps import find_gaps

        for g in find_gaps(store.all(), date.today()):
            print(f"{g['axis']:>10}  {g['value']:<28} {g['count']:>4}  {g['reason']}")
    elif args.cmd == "scout-brief":
        import json as _json
        from radar.scout.briefs import load_surfaces, render_briefs
        from radar.scout.gaps import find_gaps

        gaps = find_gaps(store.all(), date.today())
        surfaces = load_surfaces(config.SCOUT_SURFACES_PATH)
        existing = [
            f"{c['name']} | {c.get('domain') or ''}"
            for c in _json.loads(config.SEED_PATH.read_text())
        ]
        written = render_briefs(surfaces, gaps, existing, config.SCOUT_DIR, date.today())
        print(f"{len(written)} briefs in {config.SCOUT_DIR / 'briefs'}")
        for p in written:
            print(f"  {p}")
    elif args.cmd == "scout-merge":
        import json as _json
        from radar.scout.merge import load_finds, merge
        from radar.scout.liveness import check

        seed = _json.loads(config.SEED_PATH.read_text())
        reachable = check if args.check_domains else None
        from radar.coverage import record_sweep

        added, quarantined = [], []
        for f in args.files:
            found = load_finds([f])
            seed, a, q = merge(seed, found, reachable)
            added += a
            quarantined += q
            surface = Path(f).stem.removeprefix("find_")
            record_sweep(
                config.LEDGER_PATH,
                "companies",
                surface,
                len(found),
                len(a),
                date.today().isoformat(),
            )
        config.SEED_PATH.write_text(_json.dumps(seed, indent=2, ensure_ascii=False) + "\n")
        config.SCOUT_DIR.mkdir(parents=True, exist_ok=True)
        (config.SCOUT_DIR / "quarantine.json").write_text(_json.dumps(quarantined, indent=2))
        print(f"added {len(added)}: {', '.join(c['name'] for c in added)}")
        for state in ("duplicate", "blocked", "rejected"):
            hits = [q for q in quarantined if q["state"] == state]
            if hits:
                print(f"{state} {len(hits)}: {'; '.join(q['name'] for q in hits)}")
        print(f"seed now {len(seed)}")
    elif args.cmd in ("coverage", "frontier-brief"):
        return _coverage(args)
    elif args.cmd in ("people-brief", "people-merge"):
        return _people(args)
    elif args.cmd in ("prospect-gaps", "prospect-brief", "prospect-merge"):
        return _prospects(args)
    elif args.cmd == "scout-liveness":
        import json as _json
        from radar.scout.liveness import recheck

        result = recheck(store.all(), today=date.today())
        config.SCOUT_DIR.mkdir(parents=True, exist_ok=True)
        (config.SCOUT_DIR / "liveness.json").write_text(_json.dumps(result, indent=2))
        print(f"dead {len(result['dead'])}, blocked {len(result['blocked'])}")
        for d in result["dead"]:
            print(f"  dead: {d['name']} ({d['domain']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
