"""A bare domain that fails must not be read as dead before www is tried.

On 2026-10-26 the gate rejected Yili, Nongshim and Kagome as unreachable:
nongshim.com returns 404 and yili.com has no record, while the www hosts serve
the real corporate sites.
"""

from radar.scout import liveness


def _fake(responses):
    calls = []

    def get(url):
        calls.append(url)
        return responses[url]

    return get, calls


def test_bare_404_falls_back_to_www():
    get, calls = _fake({"https://nongshim.com": 404, "https://www.nongshim.com": 200})
    assert liveness.check("nongshim.com", get) is True
    assert calls == ["https://nongshim.com", "https://www.nongshim.com"]


def test_bare_dns_failure_falls_back_to_www():
    get, _ = _fake({"https://yili.com": liveness.DNS_MARKER, "https://www.yili.com": 200})
    assert liveness.check("yili.com", get) is True


def test_bare_connection_refused_falls_back_to_www():
    # fonterra.com refuses the connection; www.fonterra.com serves the site.
    get, _ = _fake({"https://fonterra.com": None, "https://www.fonterra.com": 200})
    assert liveness.check("fonterra.com", get) is True


def test_bare_dead_but_www_blocked_reads_blocked():
    # yili.com has no record; www.yili.com exists but refuses our TLS client.
    get, _ = _fake({"https://yili.com": liveness.DNS_MARKER, "https://www.yili.com": None})
    assert liveness.check("yili.com", get) is None


def test_blocked_on_both_hosts_stays_blocked():
    get, _ = _fake({"https://cf.example": 403, "https://www.cf.example": 403})
    assert liveness.check("cf.example", get) is None


def test_dead_on_both_hosts_still_reads_dead():
    get, _ = _fake({"https://gone.example": 404, "https://www.gone.example": liveness.DNS_MARKER})
    assert liveness.check("gone.example", get) is False


def test_live_bare_domain_makes_one_request():
    get, calls = _fake({"https://gallo.com": 200})
    assert liveness.check("gallo.com", get) is True
    assert calls == ["https://gallo.com"]


def test_www_domain_is_not_doubled():
    get, calls = _fake({"https://www.gone.example": 404})
    assert liveness.check("www.gone.example", get) is False
    assert calls == ["https://www.gone.example"]
