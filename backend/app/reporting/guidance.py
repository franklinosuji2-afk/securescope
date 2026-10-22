"""Reviewed remediation guidance, keyed by scanner finding id.

The text lives in ``guidance.json`` and is static: it never contains scan data. The web app carries an
identical copy (``frontend/src/guidance.json``), and a test keeps the two equal. Anything observed about a
target comes from the scan itself, not from this file.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

_PATH = Path(__file__).with_name("guidance.json")


class FixExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    code: str = Field(min_length=1)


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    url: str = Field(pattern=r"^https://")


class Guidance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    impact: str = Field(min_length=1)
    detection: Literal["observed", "heuristic"]
    detectionNote: str = Field(min_length=1)  # noqa: N815 - shared with the web app's JSON
    fixes: list[FixExample]
    verify: list[str] = Field(min_length=1)
    references: list[Reference]
    limitations: str = Field(min_length=1)


@lru_cache(maxsize=1)
def all_guidance() -> dict[str, Guidance]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    return {key: Guidance.model_validate(value) for key, value in raw.items()}


def guidance_for(finding_id: str) -> Guidance | None:
    return all_guidance().get(finding_id)
