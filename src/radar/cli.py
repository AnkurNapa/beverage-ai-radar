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
    from radar.sources.web_search import WebSearchSource, default_search_fn
    from radar.sources.trade_press import TradePressSource, DEFAULT_FEEDS, default_parse_fn
    from radar.sources.github_product import GithubProductSource
    from radar.sources.crunchbase import CrunchbaseSource
    from radar.sources.linkedin import LinkedInSource
    from radar.live_adapters import gh_lookup, cb_lookup, li_lookup

    return [
        CuratedSeedSource(config.SEED_PATH),
        WebSearchSource(default_search_fn),
        TradePressSource(DEFAULT_FEEDS, default_parse_fn),
        GithubProductSource(gh_lookup),
        CrunchbaseSource(cb_lookup),
        LinkedInSource(li_lookup),
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="radar")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    sub.add_parser("export")
    sub.add_parser("report")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
