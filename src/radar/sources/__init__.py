from __future__ import annotations
import logging
from radar.store import Store
from radar.sources.base import Source

log = logging.getLogger("radar.sources")


def run_source(source: Source, store: Store, fetcher) -> dict:
    found, errors = 0, []
    try:
        if source.kind == "discovery":
            for company in source.discover(fetcher):
                store.upsert(company)
                found += 1
        else:
            for company in store.all():
                store.upsert(source.enrich(company, fetcher))
                found += 1
    except Exception as exc:  # isolation: one source never aborts the run
        log.exception("source %s failed", source.name)
        errors.append(f"{type(exc).__name__}: {exc}")
    return {"source": source.name, "found": found, "errors": errors}
