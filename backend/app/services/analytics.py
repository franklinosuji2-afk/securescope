"""Pure logic for the cookieless website analytics: classifying a visit and summarising page views.

Nothing here stores or returns an IP address or a browser string. A visit is reduced to a page name,
the referring *host* (never a path or query), a coarse device class and a one-way daily visitor hash.
"""

from __future__ import annotations

import hashlib
import hmac
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# The only pages that are ever counted. "home" is the signed-out landing view of the app.
TRACKED_PAGES = (
    "home",
    "login",
    "register",
    "forgot-password",
    "reset-password",
    "verify-email",
    "sample-report",
    "impressum",
    "privacy",
    "terms",
)

_BOT_MARKERS = (
    "bot",
    "crawl",
    "spider",
    "slurp",
    "headless",
    "curl/",
    "wget",
    "python-",
    "httpx",
    "go-http",
    "java/",
    "monitor",
    "uptime",
    "lighthouse",
    "preview",
    "facebookexternalhit",
    "scanner",
)


def is_bot(user_agent: str) -> bool:
    ua = user_agent.strip().lower()
    return not ua or any(marker in ua for marker in _BOT_MARKERS)


def device_class(user_agent: str) -> str:
    ua = user_agent.lower()
    if "ipad" in ua or "tablet" in ua or ("android" in ua and "mobile" not in ua):
        return "tablet"
    if "mobi" in ua or "iphone" in ua or "android" in ua:
        return "mobile"
    return "desktop"


def visitor_hash(salt: str, day: date, client: str, user_agent: str) -> str:
    """A hash of day, address and browser string that changes every UTC day and cannot be reversed."""
    message = f"{day.isoformat()}|{client}|{user_agent}".encode()
    return hmac.new(salt.encode(), message, hashlib.sha256).hexdigest()[:32]


def referrer_host(referrer: str | None, own_hosts: Sequence[str]) -> str | None:
    """The referring site's host name only, or None for direct visits and our own pages."""
    if not referrer:
        return None
    try:
        parts = urlsplit(referrer.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return None
    host = parts.hostname.lower().rstrip(".")[:255]
    if host in {h.lower() for h in own_hosts}:
        return None
    return host


@dataclass(frozen=True)
class View:
    occurred_at: datetime
    page: str
    referrer_host: str | None
    device: str
    visitor: str


def resolve_timezone(name: str | None) -> tzinfo:
    try:
        return ZoneInfo(name) if name else UTC
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return UTC


def _count(counter: Counter[str], limit: int = 10) -> list[dict[str, object]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _period(views: Sequence[View], tz: tzinfo, first: date, last: date) -> dict[str, object]:
    visitors_by_day: dict[date, set[str]] = defaultdict(set)
    views_by_day: Counter[date] = Counter()
    for view in views:
        day = view.occurred_at.astimezone(tz).date()
        if first <= day <= last:
            views_by_day[day] += 1
            visitors_by_day[day].add(view.visitor)
    series = []
    day = first
    while day <= last:
        series.append(
            {"date": day.isoformat(), "views": views_by_day[day], "visitors": len(visitors_by_day[day])}
        )
        day += timedelta(days=1)
    return {
        "views": sum(views_by_day.values()),
        "visitors": sum(len(v) for v in visitors_by_day.values()),
        "series": series,
    }


def summarise(views: Sequence[View], *, days: int, tz: tzinfo, now: datetime) -> dict[str, object]:
    """Builds the dashboard numbers. `views` must cover the previous and the current period."""
    today = now.astimezone(tz).date()
    first = today - timedelta(days=days - 1)
    prev_last = first - timedelta(days=1)
    prev_first = prev_last - timedelta(days=days - 1)

    current = _period(views, tz, first, today)
    previous = _period(views, tz, prev_first, prev_last)

    in_range = [v for v in views if first <= v.occurred_at.astimezone(tz).date() <= today]
    page_views: Counter[str] = Counter(v.page for v in in_range)
    page_visitors: dict[str, set[str]] = defaultdict(set)
    for v in in_range:
        page_visitors[v.page].add(v.visitor)

    # A visit's landing page, source and device come from that visitor's first view of the day.
    landing: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    devices: Counter[str] = Counter()
    seen: set[str] = set()
    for v in sorted(in_range, key=lambda item: item.occurred_at):
        if v.visitor in seen:
            continue
        seen.add(v.visitor)
        landing[v.page] += 1
        sources[v.referrer_host or "Direct"] += 1
        devices[v.device] += 1

    series_today = current["series"][-1]  # type: ignore[index]
    series_yesterday = current["series"][-2] if days > 1 else {"views": 0, "visitors": 0}  # type: ignore[index]
    return {
        "range_days": days,
        "timezone": getattr(tz, "key", "UTC"),
        "current": current,
        "previous": previous,
        "today": {"views": series_today["views"], "visitors": series_today["visitors"]},
        "yesterday": {"views": series_yesterday["views"], "visitors": series_yesterday["visitors"]},
        "top_pages": [
            {"name": name, "count": count, "visitors": len(page_visitors[name])}
            for name, count in page_views.most_common(10)
        ],
        "landing_pages": _count(landing),
        "sources": _count(sources),
        "devices": _count(devices),
    }
