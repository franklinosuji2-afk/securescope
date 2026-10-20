from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.security.passwords import MAX_LENGTH, MIN_LENGTH
from app.security.permissions import Role


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_password(value: str) -> str:
    if len(value) < MIN_LENGTH:
        raise ValueError(f"Password must be at least {MIN_LENGTH} characters long.")
    if len(value) > MAX_LENGTH:
        raise ValueError(f"Password must be at most {MAX_LENGTH} characters long.")
    return value


class RegisterRequest(_Strict):
    email: EmailStr
    password: str
    organization_name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _check_password(value)


class LoginRequest(_Strict):
    email: EmailStr
    password: str = Field(max_length=MAX_LENGTH)


class ForgotPasswordRequest(_Strict):
    email: EmailStr


class ResetPasswordRequest(_Strict):
    token: str = Field(min_length=10, max_length=200)
    password: str

    @field_validator("password")
    @classmethod
    def _password(cls, value: str) -> str:
        return _check_password(value)


class VerifyEmailRequest(_Strict):
    token: str = Field(min_length=10, max_length=200)


class OrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    role: Role


class UserOut(BaseModel):
    id: str
    email: str
    email_verified: bool
    is_admin: bool = False
    organizations: list[OrganizationOut]


class OrganizationCreate(_Strict):
    name: str = Field(min_length=1, max_length=120)


class MemberOut(BaseModel):
    user_id: str
    email: str
    role: Role
    joined_at: datetime


class MemberAdd(_Strict):
    email: EmailStr
    role: Role = Role.MEMBER


class MemberUpdate(_Strict):
    role: Role


class OrganizationDetail(OrganizationOut):
    members: list[MemberOut]
