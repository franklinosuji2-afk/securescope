"""Cookieless website analytics: a public collect endpoint and an operator-only summary."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, Query, Request, Response

from app.api.deps import AdminDep, StateDep, client_key
from app.schemas.analytics import AnalyticsSummary, CollectRequest
from app.services.analytics import (
    View,
    device_class,
    is_bot,
    referrer_host,
    resolve_timezone,
    summarise,
    visitor_hash,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _own_hosts(state: StateDep) -> list[str]:
    urls = [state.settings.public_base_url, *state.settings.cors_origins]
    return [h for h in (urlsplit(u).hostname for u in urls) if h]


@router.post("/collect", status_code=204)
async def collect(
    body: CollectRequest,
    request: Request,
    state: StateDep,
    user_agent: Annotated[str, Header()] = "",
    dnt: Annotated[str | None, Header()] = None,
    sec_gpc: Annotated[str | None, Header(alias="sec-gpc")] = None,
) -> Response:
    """Counts one page view of a public page. Always answers 204: a dropped view is not an error and the
    caller learns nothing about why (bot, rate limit, opt-out)."""
    settings = state.settings
    if not settings.analytics_enabled or dnt == "1" or sec_gpc == "1" or is_bot(user_agent):
        return Response(status_code=204)
    client = client_key(request, state)
    if not state.analytics_limiter.check(client):
        return Response(status_code=204)
    state.analytics_limiter.record(client)
    now = datetime.now(UTC)
    view = View(
        occurred_at=now,
        page=body.page,
        referrer_host=referrer_host(body.referrer, _own_hosts(state)),
        device=device_class(user_agent),
        visitor=visitor_hash(state.analytics_salt, now.date(), client, user_agent),
    )
    await asyncio.to_thread(state.analytics.add, view)
    return Response(status_code=204)


@router.get("/summary", response_model=AnalyticsSummary)
async def summary(
    _admin: AdminDep,
    state: StateDep,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    tz: Annotated[str | None, Query(max_length=64)] = None,
) -> AnalyticsSummary:
    zone = resolve_timezone(tz)
    now = datetime.now(UTC)
    # Two periods plus a day of slack either side so any time zone's midnight is covered.
    since = now - timedelta(days=2 * days + 2)
    views = await asyncio.to_thread(state.analytics.views_since, since)
    last = await asyncio.to_thread(state.analytics.last_view_at)
    data = summarise(views, days=days, tz=zone, now=now)
    return AnalyticsSummary(
        tracking_enabled=state.settings.analytics_enabled,
        last_event_at=last,
        **data,
    )
