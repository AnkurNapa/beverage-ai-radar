"""A resolver that blips under load must not be read as a dead company."""

import time

from radar.scout import liveness


def test_transient_dns_failure_retries_and_recovers(monkeypatch):
    calls = []

    class FakeExc(Exception):
        pass

    def fake_httpx_get(url, **kw):
        calls.append(url)
        if len(calls) == 1:
            raise FakeExc("nodename nor servname provided, or not known")
        return type("R", (), {"status_code": 200})()

    import httpx

    monkeypatch.setattr(httpx, "get", fake_httpx_get)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    assert liveness._default_get("https://gallo.com") == 200
    assert len(calls) == 2, "should retry once before believing the resolver"


def test_persistent_dns_failure_still_reads_dead(monkeypatch):
    class FakeExc(Exception):
        pass

    def always_fail(url, **kw):
        raise FakeExc("nodename nor servname provided, or not known")

    import httpx

    monkeypatch.setattr(httpx, "get", always_fail)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    assert liveness._default_get("https://gone.example") == liveness.DNS_MARKER
    assert liveness.check("gone.example") is False
