from radar.http_cache import CachedFetcher


def test_second_fetch_uses_cache(tmp_path):
    calls = []

    def transport(url):
        calls.append(url); return f"body:{url}"
    f = CachedFetcher(tmp_path, min_interval_s=0, transport=transport)
    assert f.fetch("https://x.com") == "body:https://x.com"
    assert f.fetch("https://x.com") == "body:https://x.com"
    assert calls == ["https://x.com"]  # only fetched once


def test_expired_cache_refetches(tmp_path):
    calls = []

    def transport(url):
        calls.append(url); return "b"
    f = CachedFetcher(tmp_path, min_interval_s=0, transport=transport)
    f.fetch("https://x.com", ttl_hours=0)
    f.fetch("https://x.com", ttl_hours=0)
    assert len(calls) == 2
