from __future__ import annotations
import json
import sqlite3
from datetime import date
from pathlib import Path
from dataclasses import fields
from radar.model import Company, BeverageVertical, AIMaturity, Status

_ENUM_FIELDS = {"vertical": BeverageVertical, "ai_maturity": AIMaturity, "status": Status}
_DATE_FIELDS = {"first_seen", "last_seen"}
_LIST_FIELDS = {"source_urls", "people", "links", "verticals"}
# Any bool field MUST be registered here. The sqlite round-trip otherwise
# falls through to str(v), so True becomes the string "True" and every
# `=== false` check downstream silently fails. That is exactly how a
# former role rendered as current employment.
_BOOL_FIELDS = {"verified", "affiliated_company_current"}


class Store:
    def __init__(self, path: Path):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._migrate()

    def _migrate(self) -> None:
        cols = ", ".join(f"{f.name} TEXT" for f in fields(Company) if f.name != "name")
        self.conn.execute(
            f"CREATE TABLE IF NOT EXISTS companies (key TEXT PRIMARY KEY, name TEXT, {cols})"
        )
        # add columns for any dataclass field missing from an older DB, so new
        # fields work on unattended (cron) runs that never drop the sqlite file.
        have = {r[1] for r in self.conn.execute("PRAGMA table_info(companies)")}
        for f in fields(Company):
            if f.name not in have:
                self.conn.execute(f"ALTER TABLE companies ADD COLUMN {f.name} TEXT")
        self.conn.commit()

    def _to_row(self, c: Company) -> dict:
        row = {"key": c.key}
        for f in fields(Company):
            v = getattr(c, f.name)
            if v is None:
                row[f.name] = None
            elif f.name in _LIST_FIELDS:
                row[f.name] = json.dumps(v)
            elif f.name in _DATE_FIELDS:
                row[f.name] = v.isoformat()
            elif f.name in _BOOL_FIELDS:
                row[f.name] = "1" if v else "0"
            elif isinstance(v, (BeverageVertical, AIMaturity, Status)):
                row[f.name] = v.value
            elif isinstance(v, str):
                row[f.name] = v
            elif isinstance(v, int) and not isinstance(v, bool):
                row[f.name] = str(v)
            else:
                # Refuse rather than str() it. Every silent-corruption bug in
                # this store landed here: a bool became "False", a list would
                # have become "[{'label': ...}]", and the export looked fine.
                # A new field now fails on first write instead of shipping
                # wrong data to a public dashboard.
                raise TypeError(
                    f"Company.{f.name} is {type(v).__name__}, which Store cannot "
                    f"serialise. Register it in _LIST_FIELDS, _BOOL_FIELDS, "
                    f"_DATE_FIELDS or _ENUM_FIELDS, and add it to "
                    f"tests/test_store_roundtrip.py."
                )
        return row

    def _from_row(self, row: sqlite3.Row) -> Company:
        data = {}
        for f in fields(Company):
            v = row[f.name]
            if v is None:
                data[f.name] = None
            elif f.name in _LIST_FIELDS:
                data[f.name] = json.loads(v)
            elif f.name in _DATE_FIELDS:
                data[f.name] = date.fromisoformat(v)
            elif f.name in _BOOL_FIELDS:
                data[f.name] = v in ("1", "True", "true", 1, True)
            elif f.name in _ENUM_FIELDS:
                data[f.name] = _ENUM_FIELDS[f.name](v)
            elif f.name in {"founded_year"}:
                data[f.name] = int(v)
            else:
                data[f.name] = v
        return Company(**data)

    def get(self, key: str) -> Company | None:
        r = self.conn.execute("SELECT * FROM companies WHERE key=?", (key,)).fetchone()
        return self._from_row(r) if r else None

    def all(self) -> list[Company]:
        return [self._from_row(r) for r in self.conn.execute("SELECT * FROM companies")]

    def upsert(self, company: Company, authoritative: bool = False) -> None:
        """authoritative: the caller is a curated source and is correcting the
        record, so its non-null values replace what is stored. Enrichment must
        never pass this, or a scraped guess would overwrite a checked fact."""
        existing = self.get(company.key)
        merged = self._merge(existing, company, authoritative) if existing else company
        row = self._to_row(merged)
        cols = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        updates = ", ".join(f"{k}=excluded.{k}" for k in row if k != "key")
        self.conn.execute(
            f"INSERT INTO companies ({cols}) VALUES ({placeholders}) "
            f"ON CONFLICT(key) DO UPDATE SET {updates}",
            list(row.values()),
        )
        self.conn.commit()

    @staticmethod
    def _merge(old: Company, new: Company, authoritative: bool = False) -> Company:
        """Default is fill-the-blanks: a new value lands only where the stored
        one is null, so enrichment can add but never overwrite.

        That default silently made the curated seed read-only for any field
        that already had a value: correcting a person's employer or location in
        people_seed.json changed nothing, because the old value was not null.
        Curated lanes therefore pass authoritative=True."""
        merged = Company(**{f.name: getattr(old, f.name) for f in fields(Company)})
        for f in fields(Company):
            nv = getattr(new, f.name)
            if nv is None:
                continue
            if f.name == "source_urls":
                merged.source_urls = sorted(set(old.source_urls) | set(nv))
            elif f.name == "people":
                # curated lanes are authoritative for people; a non-empty new
                # list replaces (so seed corrections propagate). Enrichment emits
                # [], which is falsy here, so it can never clobber curated people.
                if nv:
                    merged.people = nv
            elif f.name == "first_seen":
                merged.first_seen = min(x for x in (old.first_seen, nv) if x)
            elif f.name == "last_seen":
                merged.last_seen = max(x for x in (old.last_seen, nv) if x)
            elif authoritative or getattr(old, f.name) is None:
                setattr(merged, f.name, nv)
        return merged

    def drop_renamed(self, emitted: list) -> list[str]:
        """Remove stored rows superseded by a re-keyed version of themselves.

        Rows without a domain are keyed slug(name)::country, so correcting
        somebody's location mints a NEW key and leaves the old row behind: the
        export then carries the person twice, once stale.

        Deliberately narrow. An earlier attempt deleted every row the source
        did not emit this run, which removed 130 legitimate companies, so this
        only ever touches rows that share a name with something just written
        under a different key.
        """
        gone: list[str] = []
        for company in emitted:
            rows = [
                r["key"] for r in self.conn.execute(
                    "SELECT key FROM companies WHERE name = ? AND key != ?",
                    (company.name, company.key),
                )
            ]
            for key in rows:
                self.conn.execute("DELETE FROM companies WHERE key = ?", (key,))
                gone.append(key)
        if gone:
            self.conn.commit()
        return gone

    def close(self) -> None:
        self.conn.close()
