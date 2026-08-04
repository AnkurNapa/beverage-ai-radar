from __future__ import annotations
from datetime import date
from pathlib import Path
from radar.store import Store
from radar.sources import run_source
from radar.outputs.json_export import export_json
from radar.outputs.report import render_report
from radar.outputs.seo import write_seo
from radar.outputs.vault_notes import write_vault_notes


def run(
    store: Store,
    fetcher,
    sources: list,
    outputs_dir: Path,
    vault_dir: Path,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    outputs_dir = Path(outputs_dir)
    per_source = []
    for src in [s for s in sources if s.kind == "discovery"]:
        per_source.append(run_source(src, store, fetcher))
    for src in [s for s in sources if s.kind == "enrichment"]:
        per_source.append(run_source(src, store, fetcher))

    export_json(store, outputs_dir / "data.json", today)
    (outputs_dir / "report.md").write_text(render_report(store, today))
    # Re-read what we just wrote rather than re-serialising: the crawlable page
    # is then incapable of disagreeing with data.json, which is the whole point
    # of having it.
    import json as _json
    write_seo(_json.loads((outputs_dir / "data.json").read_text()), outputs_dir, today)
    write_vault_notes(store, vault_dir, today)
    return {"per_source": per_source, "total_companies": len(store.all())}
