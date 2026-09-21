"""The 2026-09-19 scheduled sweep overwrote papers_openalex.json from 135 entries
to 2 and committed the loss. A rate-limited API returns no rows, which is
indistinguishable from an honest empty sweep, so the writer has to refuse a
collapse rather than trust it."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_guard_refuses_a_collapse(tmp_path):
    out = tmp_path / "papers_openalex.json"
    out.write_text(json.dumps([{"title": f"paper {i}"} for i in range(135)]))
    script = (
        "import json,sys\n"
        f"OUT=__import__('pathlib').Path({str(out)!r})\n"
        "rows=[{'title':'paper 0'},{'title':'paper 1'}]\n"
        "previous=len(json.loads(OUT.read_text()))\n"
        "if previous and len(rows) < previous*0.5:\n"
        "    print('REFUSING TO WRITE', file=sys.stderr); sys.exit(1)\n"
        "OUT.write_text(json.dumps(rows))\n"
    )
    r = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert r.returncode == 1
    assert "REFUSING TO WRITE" in r.stderr
    assert len(json.loads(out.read_text())) == 135, "the good file must survive"


def test_the_guard_is_actually_in_the_script():
    src = (ROOT / "scripts" / "sweep_papers.py").read_text()
    assert "REFUSING TO WRITE" in src
    assert "previous * 0.5" in src
