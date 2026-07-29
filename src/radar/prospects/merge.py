"""Validate and merge prospect findings into the private prospect list.

Mirrors `radar.scout.merge` and reuses its helpers rather than forking them:
the name normaliser and near-duplicate matcher were tuned against real sweep
output and there is no reason for two copies to drift apart.

Two things differ from the vendor gate:

1. **Identity is (company, region), not company alone.** Diageo is a genuine
   separate target in Scotland and in East Africa, with different pain, a
   different wedge and a different person to email.
2. **Tiers 3-5 are exempt from the source gate.** They are curated judgement
   calls about categories of buyer ("Australian independent craft brewers"),
   not factual claims about a named organisation, so demanding two citations
   would reject them for being what they are. Tiers 1-2 name real companies
   and often real people, which is where a fabrication would actually cost
   money, so those are gated hard.
"""

from __future__ import annotations

import json
from pathlib import Path

from radar.scout.merge import _near_duplicate, norm_domain, norm_name

REQUIRED = ("company", "region", "tier", "vertical", "pain", "wedge", "entry")
# Tiers at or below this are treated as curated judgement and skip the source
# gate. Above it, a row must cite itself. See the module docstring.
GRANDFATHER_MIN_TIER = 3
GRANDFATHER_MAX_TIER = 2
VALID_TIERS = (1, 2, 3, 4, 5)


def _key(row: dict) -> tuple:
    return (norm_name(row.get("company")), (row.get("region") or "").strip().lower())


def _sources_support_url(row: dict) -> bool:
    """At least two sources, one of them on the row's own claimed domain.

    Lifted deliberately from the vendor gate, where it is the single strongest
    anti-hallucination check: an invented target rarely survives having to name
    its own site among its evidence.
    """
    urls = row.get("source_urls") or []
    if len(urls) < 2:
        return False
    domain = norm_domain(row.get("url"))
    if not domain:
        return False
    return any(norm_domain(u) == domain for u in urls)


def _find(rows: list[dict], key: tuple):
    for r in rows:
        if _key(r) == key:
            return r
    return None


def _is_reverification(incoming: dict, existing: dict) -> bool:
    """Incoming carries sources, the row it matches does not.

    Deliberately one-directional: an already-sourced row is never overwritten,
    so re-running a sweep does not churn good data, and an unsourced row can
    never clobber a sourced one.
    """
    return bool(incoming.get("source_urls")) and not existing.get("source_urls")


def merge(rows: list[dict], incoming: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Returns (rows, added, quarantined).

    Nothing is ever dropped silently: every rejection carries a reason and a
    state, so a real target lost to a typo stays visible in the quarantine file.
    """
    known = {_key(r) for r in rows}
    known_names = [norm_name(r.get("company")) for r in rows]
    added: list[dict] = []
    quarantined: list[dict] = []

    def reject(row, reason, state="rejected"):
        quarantined.append({
            "company": row.get("company", "?"),
            "region": row.get("region", "?"),
            "reason": reason,
            "state": state,
        })

    for row in incoming:
        missing = [f for f in REQUIRED if not row.get(f)]
        if missing:
            reject(row, f"missing required fields: {', '.join(missing)}")
            continue

        tier = row.get("tier")
        if tier not in VALID_TIERS:
            reject(row, f"tier {tier!r} is not one of {VALID_TIERS}")
            continue

        key = _key(row)
        if key in known:
            # Re-verification, not a duplicate. A row that arrives WITH sources
            # against an existing row that has NONE is the answer to a re-verify
            # request, and it must replace its predecessor. Treating it as a
            # duplicate silently discards the corrections that make re-verifying
            # worth doing at all: the first sweep lost "this company is in
            # administration" exactly this way.
            existing = _find(rows, key)
            if existing is not None and _is_reverification(row, existing):
                rows[rows.index(existing)] = {**row, "discovered_by": "reverified"}
                quarantined.append({
                    "company": row.get("company", "?"),
                    "region": row.get("region", "?"),
                    "reason": "re-verified: replaced the unsourced original",
                    "state": "updated",
                })
                continue
            reject(row, f"duplicate in region {row['region']}", "duplicate")
            continue

        # Near-duplicate only inside the same region: "Diageo" in UK and in
        # Africa are different rows, but "Piccadily" and "Piccadily (Indri)"
        # in India are the same target twice.
        same_region = [
            norm_name(r["company"]) for r in rows + added
            if (r.get("region") or "").strip().lower() == key[1]
        ]
        match = _near_duplicate(row["company"], same_region)
        if match:
            # Same re-verification rule as the exact-key path above. This branch
            # matters more, not less: a sweep returns the full legal name
            # ("BrewDog plc", "Heineken Beverages SA (Pty) Ltd") against a row
            # written under the short one, so corrections arrive here.
            existing = next(
                (r for r in rows
                 if norm_name(r["company"]) == match
                 and (r.get("region") or "").strip().lower() == key[1]),
                None,
            )
            if existing is not None and _is_reverification(row, existing):
                rows[rows.index(existing)] = {**row, "discovered_by": "reverified"}
                quarantined.append({
                    "company": row.get("company", "?"),
                    "region": row.get("region", "?"),
                    "reason": f"re-verified: replaced '{existing['company']}'",
                    "state": "updated",
                })
                continue
            reject(row, f"near-duplicate of an existing {row['region']} row", "duplicate")
            continue

        if tier >= GRANDFATHER_MIN_TIER:
            row = {**row, "discovered_by": row.get("discovered_by") or "curated"}
        else:
            if len(row.get("source_urls") or []) < 2:
                reject(row, "tier 1-2 needs two sources")
                continue
            if not _sources_support_url(row):
                reject(row, "no source on the row's own domain")
                continue
            row = {**row, "discovered_by": row.get("discovered_by") or "scout"}

        rows.append(row)
        added.append(row)
        known.add(key)
        known_names.append(norm_name(row["company"]))

    return rows, added, quarantined


def load_finds(paths) -> list[dict]:
    """Read agent output files, tolerating one bad file without losing the rest."""
    out: list[dict] = []
    for p in paths:
        try:
            data = json.loads(Path(p).read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"  ! skipped {p}: {e}")
            continue
        out.extend(data if isinstance(data, list) else data.get("prospects", []))
    return out
