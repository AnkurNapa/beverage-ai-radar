"""Import the reference list of a review paper as candidate papers.

A good review is a hand-screened bibliography. This pulls its references from
OpenAlex and runs each through the same relevance gate as sweep_papers.py, so
generic machine-learning classics cited for method drop out.

Writes data/resources/papers_review_refs.json, its own file so the scheduled
paper sweep (which rewrites papers_openalex.json) never touches it. Re-running
merges by url, so several reviews can feed the same file.

    .venv/bin/python scripts/import_review_refs.py 10.3390/beverages12100118
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sweep_papers import MAILTO, to_row  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "resources" / "papers_review_refs.json"
API = "https://api.openalex.org/works"


def get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": f"beverage-ai-radar ({MAILTO})"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def vertical_of(title: str) -> str:
    t = title.lower()
    if re.search(r"wine|grape|vinif|enolog|oenolog", t):
        return "wine"
    if re.search(r"whisk|spirit|distill|baijiu|liquor|brandy|rum\b|vodka|gin\b", t):
        return "whiskey"
    return "beer"


def main() -> int:
    doi = sys.argv[1]
    review = get(f"{API}/doi:{doi}")
    ids = [r.rsplit("/", 1)[1] for r in review.get("referenced_works", [])]
    works = []
    for i in range(0, len(ids), 50):
        works += get(f"{API}?per-page=50&filter=openalex:{'|'.join(ids[i:i + 50])}&mailto={MAILTO}")["results"]
        time.sleep(1)
    if len(works) < len(ids) * 0.5:
        print(f"only {len(works)} of {len(ids)} references came back; refusing to write", file=sys.stderr)
        return 1

    existing = json.loads(OUT.read_text()) if OUT.exists() else []
    by_url = {r["url"].lower().rstrip("/"): r for r in existing}
    for w in works:
        row = to_row(w, vertical_of(w.get("title") or ""))
        if row:
            row["via"] = f"https://doi.org/{doi}"
            by_url.setdefault(row["url"].lower().rstrip("/"), row)
    rows = sorted(by_url.values(), key=lambda r: (-(r.get("year") or 0), -(r.get("cited_by") or 0)))
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(works)} references, {len(rows) - len(existing)} new rows, {len(rows)} in file -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
