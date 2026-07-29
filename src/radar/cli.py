from __future__ import annotations
import argparse
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
        seed, added, quarantined = merge(seed, load_finds(args.files), reachable)
        config.SEED_PATH.write_text(_json.dumps(seed, indent=2, ensure_ascii=False) + "\n")
        config.SCOUT_DIR.mkdir(parents=True, exist_ok=True)
        (config.SCOUT_DIR / "quarantine.json").write_text(_json.dumps(quarantined, indent=2))
        print(f"added {len(added)}: {', '.join(c['name'] for c in added)}")
        for state in ("duplicate", "blocked", "rejected"):
            hits = [q for q in quarantined if q["state"] == state]
            if hits:
                print(f"{state} {len(hits)}: {'; '.join(q['name'] for q in hits)}")
        print(f"seed now {len(seed)}")
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
