"""The contract between the dependency scan and whatever answers "is this package version known to be
vulnerable?". The scan depends only on this interface. No network client exists yet: the OSV integration is a
separate step that is blocked until its privacy and licence review is finished, so tests use fakes.

The one rule built into the interface: a source that cannot answer says so (`unavailable`), and the scan then
reports the run as incomplete. "No answer" is never read as "no vulnerabilities"."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.appscan.manifests import Package


@dataclass(frozen=True, slots=True)
class Advisory:
    id: str
    summary: str = ""
    aliases: tuple[str, ...] = ()
    # As the source gives it: a word ("high", "moderate"), a CVSS score ("7.5") or empty.
    severity: str | None = None
    fixed_versions: tuple[str, ...] = ()
    references: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceInfo:
    name: str
    version: str = ""
    # When the source's data was last updated, if it says.
    data_timestamp: str | None = None
    # Credit shown with results when the data's licence asks for it.
    attribution: str = ""


@dataclass(slots=True)
class LookupResult:
    """Answers for a batch. `advisories[i]` belongs to `packages[i]`; None means no answer for that package."""

    advisories: list[list[Advisory] | None]
    info: SourceInfo = field(default_factory=lambda: SourceInfo("unknown"))


class SourceUnavailable(Exception):
    """The source could not answer (network error, timeout, rate limit, malformed reply). Carries no content."""


class VulnerabilitySource(Protocol):
    max_batch: int

    def lookup(self, packages: Sequence[Package]) -> LookupResult: ...


class UnavailableSource:
    """The source used until a real one is approved and built: it never answers. Every scan that reaches it ends
    as Failed (and is not charged), which is the honest result: nothing was checked."""

    max_batch = 1000

    def lookup(self, packages: Sequence[Package]) -> LookupResult:
        raise SourceUnavailable
