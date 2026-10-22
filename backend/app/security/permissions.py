"""Role-based access control. The matrix below is the single source of truth (see docs/SECURITY.md)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    SECURITY_ANALYST = "SECURITY_ANALYST"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class Permission(StrEnum):
    ORG_READ = "org:read"
    ORG_MANAGE_MEMBERS = "org:manage_members"
    SCAN_READ = "scan:read"
    SCAN_CREATE = "scan:create"
    REPORT_EXPORT = "report:export"
    TARGET_READ = "target:read"
    TARGET_MANAGE = "target:manage"
    FINDING_TRIAGE = "finding:triage"
    AUDIT_READ = "audit:read"
    CLIENT_READ = "client:read"
    CLIENT_MANAGE = "client:manage"
    REPORT_SHARE = "report:share"


_ALL = set(Permission)
MATRIX: dict[Role, set[Permission]] = {
    Role.OWNER: _ALL,
    Role.ADMIN: _ALL,
    Role.SECURITY_ANALYST: {
        Permission.ORG_READ,
        Permission.SCAN_READ,
        Permission.SCAN_CREATE,
        Permission.REPORT_EXPORT,
        Permission.TARGET_READ,
        Permission.TARGET_MANAGE,
        Permission.FINDING_TRIAGE,
        Permission.CLIENT_READ,
        Permission.REPORT_SHARE,
    },
    Role.MEMBER: {
        Permission.ORG_READ,
        Permission.SCAN_READ,
        Permission.SCAN_CREATE,
        Permission.REPORT_EXPORT,
        Permission.TARGET_READ,
        Permission.CLIENT_READ,
    },
    Role.VIEWER: {
        Permission.ORG_READ,
        Permission.SCAN_READ,
        Permission.REPORT_EXPORT,
        Permission.TARGET_READ,
    },
}

# Higher number = more authority. Used to stop an admin from touching an owner.
RANK = {Role.VIEWER: 1, Role.MEMBER: 2, Role.SECURITY_ANALYST: 3, Role.ADMIN: 4, Role.OWNER: 5}


def can(role: Role, permission: Permission) -> bool:
    return permission in MATRIX[role]


def may_assign(actor: Role, new_role: Role, current_role: Role | None = None) -> bool:
    """An actor may only grant or change roles strictly below their own, except owners."""
    if actor is Role.OWNER:
        return True
    if actor is not Role.ADMIN:
        return False
    if current_role is not None and RANK[current_role] >= RANK[Role.ADMIN]:
        return False
    return RANK[new_role] < RANK[Role.ADMIN]
