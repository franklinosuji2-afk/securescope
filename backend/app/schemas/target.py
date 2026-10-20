from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

VerificationMethod = Literal["dns_txt", "http_file"]


class TargetCreate(BaseModel):
    hostname: str = Field(min_length=1, max_length=2048)


class TargetVerify(BaseModel):
    method: VerificationMethod


class TargetOut(BaseModel):
    id: str
    hostname: str
    status: Literal["pending", "verified", "expired", "reverify"]
    challenge_token: str
    challenge_expires_at: datetime
    verified_at: datetime | None = None
    verification_expires_at: datetime | None = None
    verification_method: VerificationMethod | None = None
    last_check_at: datetime | None = None
    last_check_error: str | None = None
    created_at: datetime
    dns_record_name: str = ""
    dns_record_value: str = ""
    http_file_url: str = ""
    http_file_content: str = ""


class TargetList(BaseModel):
    items: list[TargetOut]
