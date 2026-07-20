from __future__ import annotations
from typing import Protocol
from radar.model import Company


class Source(Protocol):
    name: str
    kind: str

    def discover(self, fetcher) -> list[Company]: ...
    def enrich(self, company: Company, fetcher) -> Company: ...
