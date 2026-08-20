"""Is a domain alive, dead, or just blocking us?

Three states, not two. Seven real companies were lost in the first sweep to
403s and Cloudflare, which is a fetching problem, not evidence that they do not
exist. Blocked entries are held for a browser pass rather than rejected.
"""

from __future__ import annotations

from datetime import date

BLOCKED_CODES = {401, 403, 405, 406, 429, 503}
# Only DNS having no record for a domain is evidence the domain is gone. A TLS
# handshake rejection, a refused connection or a timeout are all failures of
# *our* client, and mis-read live companies as dead: arryved.com and
# gastrograph.com both refuse this client's TLS and are plainly trading.
DNS_MARKER = "dns"


def check(domain: str, get=None) -> bool | None:
    """True alive, False dead, None blocked (retry with a real browser)."""
    if not domain:
        return False
    if get is None:
        get = _default_get
    try:
        status = get(f"https://{domain.removeprefix('https://').removeprefix('http://')}")
    except Exception:
        return None
    if status == DNS_MARKER:
        return False
    if status is None:
        return None  # TLS/connection/timeout: our problem, retry with a browser
    if status in BLOCKED_CODES:
        return None
    return 200 <= status < 400


def _default_get(url: str, _attempt: int = 0) -> int | None:
    import httpx

    try:
        resp = httpx.get(
            url,
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
        )
        return resp.status_code
    except Exception as exc:
        # httpx wraps the resolver error, so match on the OS message rather than
        # the exception class, which is ConnectError for every transport failure.
        if "nodename nor servname" in str(exc) or "Name or service not known" in str(exc):
            # A resolver that fails under burst load reports exactly the same
            # message as a domain that genuinely has no record. Sweeping 700+
            # domains produced 561 "dead" of which a serial recheck found ~80%
            # alive, so one retry before calling a company gone.
            if _attempt == 0:
                import time

                time.sleep(1.0)
                return _default_get(url, _attempt=1)
            return DNS_MARKER
        return None


def recheck(companies: list, get=None, today: date | None = None) -> dict:
    """Recheck existing entries so quiet deaths get noticed.

    A company that folds keeps its old last_seen and just ages out over 18
    months; nothing in the pipeline notices. This does, cheaply and with no LLM.
    """
    today = today or date.today()
    dead, blocked = [], []
    for c in companies:
        if not c.domain:
            continue
        state = check(c.domain, get)
        if state is False:
            dead.append({"name": c.name, "domain": c.domain})
        elif state is None:
            blocked.append({"name": c.name, "domain": c.domain})
    return {
        "checked": today.isoformat(),
        "dead": dead,
        "blocked": blocked,
        "note": "dead domains need a human call: mark dormant, correct the domain, or delete",
    }
