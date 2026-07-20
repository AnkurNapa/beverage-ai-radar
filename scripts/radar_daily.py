#!/usr/bin/env python3
"""launchd entrypoint: run the pipeline, mirror the report into the vault,
publish the dashboard to GitHub Pages, print the digest.

Kept dependency-free beyond the package itself. Git push is best-effort: a
failed push logs (check=False) but never crashes the daily run.
"""

import subprocess
from datetime import date

from radar import config
from radar.cli import main as radar_main
from radar.store import Store
from radar.outputs.digest import build_digest
from radar.signals import collect as collect_signals

ROOT = config.PROJECT_ROOT


def _git(*args):
    subprocess.run(["git", "-C", str(ROOT), *args], check=False)


def main() -> None:
    radar_main(["run"])
    # pull fresh trade-press signals (leads to mine; separate from the store)
    try:
        sig = collect_signals()
    except Exception:
        sig = {"new": 0, "total": 0}
    # mirror report into the vault
    report = config.DASHBOARD_DIR / "report.md"
    if report.exists():
        config.VAULT_DIR.mkdir(parents=True, exist_ok=True)
        (config.VAULT_DIR / "Landscape Report.md").write_text(report.read_text())
    # publish dashboard (data.json + signals.json are not gitignored)
    _git("add", "dashboard", "SIGNALS.md")
    _git("commit", "-m", f"data: refresh {date.today().isoformat()} (+{sig['new']} signals)")
    _git("push")
    # digest to stdout (email wiring is manual/optional; send from napaankur@gmail.com)
    print(build_digest(Store(config.DB_PATH), date.today()))
    print(f"signals: {sig['new']} new, {sig['total']} total")


if __name__ == "__main__":
    main()
