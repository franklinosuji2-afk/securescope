"""Private feedback from signed-in people. Nothing here is public, and nothing else depends on it."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import AdminDep, PrincipalDep, StateDep, request_id
from app.repositories.feedback import FeedbackRecord

router = APIRouter(prefix="/feedback", tags=["feedback"])

Category = Literal["general", "ease_of_use", "reports", "accuracy", "pricing", "other"]
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class FeedbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: int = Field(ge=1, le=5)
    category: Category | None = None
    message: str | None = Field(default=None, max_length=2000)

    @field_validator("message")
    @classmethod
    def _clean(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = _CONTROL.sub("", value).strip()
        return text or None


class FeedbackOut(BaseModel):
    rating: int
    category: str | None
    message: str | None
    created_at: datetime
    updated_at: datetime


class FeedbackEntryOut(FeedbackOut):
    # The plan of the workspace the author owns; None for someone who only belongs to other workspaces.
    plan: str | None = None


class PlanStat(BaseModel):
    count: int
    average: float


class FeedbackSummaryOut(BaseModel):
    count: int
    average: float | None
    by_rating: dict[int, int]
    by_plan: dict[str, PlanStat] = {}
    latest: list[FeedbackEntryOut]


def _out(record: FeedbackRecord) -> FeedbackOut:
    return FeedbackOut(
        rating=record.rating,
        category=record.category,
        message=record.message,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("", response_model=FeedbackOut | None)
async def get_feedback(principal: PrincipalDep, state: StateDep) -> FeedbackOut | None:
    """The signed-in person's own entry, or null."""
    record = await asyncio.to_thread(state.feedback.get, principal.user.id)
    return _out(record) if record else None


@router.put("", response_model=FeedbackOut)
async def save_feedback(
    body: FeedbackIn, request: Request, principal: PrincipalDep, state: StateDep
) -> FeedbackOut:
    """Saves the person's entry (a new one, or a replacement of their earlier one)."""
    key = principal.user.id
    if not state.feedback_limiter.check(key):
        raise HTTPException(status_code=429, detail="Too many changes. Try again in an hour.")
    state.feedback_limiter.record(key)
    record = await asyncio.to_thread(state.feedback.save, key, body.rating, body.category, body.message)
    await asyncio.to_thread(
        state.audit.record,
        "feedback.saved",
        actor_user_id=key,
        resource_type="feedback",
        request_id=request_id(request),
    )
    return _out(record)


@router.delete("", status_code=204)
async def withdraw_feedback(request: Request, principal: PrincipalDep, state: StateDep) -> Response:
    """Deletes the person's entry for good. Never required for anything else."""
    removed = await asyncio.to_thread(state.feedback.delete, principal.user.id)
    if removed:
        await asyncio.to_thread(
            state.audit.record,
            "feedback.withdrawn",
            actor_user_id=principal.user.id,
            resource_type="feedback",
            request_id=request_id(request),
        )
    return Response(status_code=204)


@router.get("/summary", response_model=FeedbackSummaryOut)
async def feedback_summary(_admin: AdminDep, state: StateDep) -> FeedbackSummaryOut:
    """Operator only: totals, an average per plan and the newest entries, without names or email addresses."""
    summary = await asyncio.to_thread(state.feedback.summary)
    entries = await asyncio.to_thread(state.feedback.entries)
    plan_names: dict[str, str] = {}
    out: list[FeedbackEntryOut] = []
    ratings: dict[str, list[int]] = {}
    for record, org_id in entries:
        name = None
        if org_id is not None:
            if org_id not in plan_names:
                plan_names[org_id] = (await state.entitlements.plan_for_async(org_id)).name
            name = plan_names[org_id]
        out.append(FeedbackEntryOut(**_out(record).model_dump(), plan=name))
        ratings.setdefault(name or "Team member", []).append(record.rating)
    return FeedbackSummaryOut(
        count=summary.count,
        average=summary.average,
        by_rating=summary.by_rating,
        by_plan={
            k: PlanStat(count=len(v), average=round(sum(v) / len(v), 2)) for k, v in sorted(ratings.items())
        },
        latest=out[:50],
    )
