from __future__ import annotations
from datetime import date
from pathlib import Path
from radar.config import DASHBOARD_DIR, JOBS_MAX_AGE_DAYS
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
    # Share card and jobs feed touch the real dashboard and the network, so
    # they only fire for a genuine run against the configured dashboard dir.
    # test_pipeline passes a temp dir: without this guard it launched Chrome
    # and started a 35-minute LinkedIn sweep on every test run.
    if outputs_dir.resolve() == DASHBOARD_DIR.resolve():
        try:
            import sys as _sys
            _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
            import build_og as _og
            _og.build(today)
        except Exception as _e:  # noqa: BLE001 - never let the card break a run
            print(f"og card skipped: {_e}")
        _refresh_jobs(outputs_dir, today)
    write_vault_notes(store, vault_dir, today)
    return {"per_source": per_source, "total_companies": len(store.all())}


def _refresh_jobs(outputs_dir: Path, today: date) -> None:
    """Re-sweep the jobs feed, but only when it has gone stale.

    It was not wired into anything at all, which is why it sat six days old
    behind a dashboard tab that reads as live. It is also the slowest thing
    here by far, so it is age-gated rather than run every time.
    """
    import os
    mode = os.environ.get("RADAR_JOBS", "auto").lower()
    if mode == "never":
        return
    path = outputs_dir / "jobs.json"
    if not path.exists():
        # Nothing here to refresh. A missing feed means this is not the managed
        # dashboard, not an invitation to run a 35-minute sweep.
        return
    if mode != "always":
        age = (today - date.fromtimestamp(path.stat().st_mtime)).days
        if age < JOBS_MAX_AGE_DAYS:
            print(f"jobs feed is {age}d old, skipping refresh "
                  f"(RADAR_JOBS=always to force)")
            return
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
        import build_jobs as _jobs
        _jobs.build()
    except Exception as exc:  # noqa: BLE001 - a rate limit must not fail a run
        print(f"jobs refresh skipped: {exc}")
