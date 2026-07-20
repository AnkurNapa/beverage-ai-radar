from __future__ import annotations
import json
import sqlite3
from datetime import date
from pathlib import Path
from dataclasses import fields
from radar.model import Company, BeverageVertical, AIMaturity, Status

_ENUM_FIELDS = {"vertical": BeverageVertical, "ai_maturity": AIMaturity, "status": Status}
_DATE_FIELDS = {"first_seen", "last_seen"}
_LIST_FIELDS = {"source_urls", "people"}


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
            elif isinstance(v, (BeverageVertical, AIMaturity, Status)):
                row[f.name] = v.value
            else:
                row[f.name] = str(v) if not isinstance(v, str) else v
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

    def upsert(self, company: Company) -> None:
        existing = self.get(company.key)
        merged = self._merge(existing, company) if existing else company
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
    def _merge(old: Company, new: Company) -> Company:
        merged = Company(**{f.name: getattr(old, f.name) for f in fields(Company)})
        for f in fields(Company):
            nv = getattr(new, f.name)
            if nv is None:
                continue
            if f.name == "source_urls":
                merged.source_urls = sorted(set(old.source_urls) | set(nv))
            elif f.name == "first_seen":
                merged.first_seen = min(x for x in (old.first_seen, nv) if x)
            elif f.name == "last_seen":
                merged.last_seen = max(x for x in (old.last_seen, nv) if x)
            elif getattr(old, f.name) is None:
                setattr(merged, f.name, nv)
        return merged

    def close(self) -> None:
        self.conn.close()
