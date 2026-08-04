from __future__ import annotations
import logging
from radar.store import Store
from radar.sources.base import Source

log = logging.getLogger("radar.sources")


def run_source(source: Source, store: Store, fetcher) -> dict:
    found, errors = 0, []
    try:
        # The curated lanes are the hand-checked source of truth, so they are
        # allowed to correct stored values. Everything else fills blanks only.
        authoritative = source.kind == "discovery" and source.name.startswith("curated")
        if source.kind == "discovery":
            # Dedupe on identity change only. Keys for domainless rows are
            # slug(name)::country, so relocating a person mints a new key and
            # strands the old row. Removing same-name siblings of what we just
            # emitted fixes exactly that, without the collateral damage of
            # pruning everything the source did not emit this run.
            emitted: list = []
            for company in source.discover(fetcher):
                store.upsert(company, authoritative=authoritative)
                emitted.append(company)
                found += 1
            if authoritative:
                for key in store.drop_renamed(emitted):
                    log.info("dropped superseded %s row: %s", source.name, key)
        else:
            for company in store.all():
                store.upsert(source.enrich(company, fetcher))
                found += 1
    except Exception as exc:  # isolation: one source never aborts the run
        log.exception("source %s failed", source.name)
        errors.append(f"{type(exc).__name__}: {exc}")
    return {"source": source.name, "found": found, "errors": errors}
