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

ROOT = config.PROJECT_ROOT


def _git(*args):
    subprocess.run(["git", "-C", str(ROOT), *args], check=False)


def main() -> None:
    radar_main(["run"])
    # mirror report into the vault
    report = config.DASHBOARD_DIR / "report.md"
    if report.exists():
        config.VAULT_DIR.mkdir(parents=True, exist_ok=True)
        (config.VAULT_DIR / "Landscape Report.md").write_text(report.read_text())
    # publish dashboard (data.json is not gitignored, so it is included)
    _git("add", "dashboard")
    _git("commit", "-m", f"data: daily refresh {date.today().isoformat()}")
    _git("push")
    # digest to stdout (email wiring is manual/optional; send from napaankur@gmail.com)
    print(build_digest(Store(config.DB_PATH), date.today()))


if __name__ == "__main__":
    main()
