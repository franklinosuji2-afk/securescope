"""Passive DNS and email-policy checks for a domain the organization has verified.

These read public DNS records through the system resolver: SPF, DMARC, CAA and DNSSEC. Only the verified
domain itself is queried, and only when it is a main domain (example.com, not shop.example.com, which would
tell us about a parent domain nobody verified). Every lookup is bounded by a short timeout.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import dns.asyncresolver
import dns.exception
import dns.resolver

from app.schemas.scan import Finding, Severity

LOOKUP_SECONDS = 3.0

# A short list of two-part public suffixes, so example.co.uk counts as a main domain and shop.example.co.uk
# does not. A missing entry only means a domain is skipped with a clear reason, never wrongly reported.
TWO_PART_SUFFIXES: frozenset[str] = frozenset(
    {
        "co.uk", "org.uk", "ac.uk", "gov.uk", "me.uk", "ltd.uk", "plc.uk",
        "com.au", "net.au", "org.au", "edu.au", "gov.au",
        "co.nz", "org.nz", "net.nz",
        "co.jp", "or.jp", "ne.jp", "ac.jp",
        "co.za", "org.za",
        "com.br", "net.br", "org.br",
        "com.mx", "com.ar", "com.co", "com.pe", "com.ve",
        "co.in", "net.in", "org.in", "firm.in", "gen.in", "ind.in",
        "com.cn", "net.cn", "org.cn", "com.hk", "com.tw", "com.sg", "com.my", "com.ph", "com.vn",
        "co.kr", "or.kr", "com.tr", "com.ua", "com.pl", "com.ng", "com.eg", "co.il", "co.id", "co.th",
    }
)  # fmt: skip

Status = Literal["ok", "none", "error"]


@dataclass(frozen=True)
class DnsAnswer:
    """`ok`: records came back. `none`: the name exists or not, but has no such records. `error`: no usable
    answer (timeout, server failure), which is never treated as "missing"."""

    status: Status
    records: tuple[str, ...] = ()


@dataclass(frozen=True)
class DnsObservation:
    domain: str
    txt: DnsAnswer
    dmarc: DnsAnswer
    caa: DnsAnswer
    ds: DnsAnswer


Resolve = Callable[[str, str], Awaitable[DnsAnswer]]


def eligible_domain(host: str) -> str | None:
    """The main domain to check for this verified host, or None when it is a subdomain or not a domain name."""
    name = host.lower().rstrip(".")
    if name.startswith("www."):
        name = name[4:]
    if "." not in name:
        return None
    try:
        ipaddress.ip_address(name.strip("[]"))
        return None
    except ValueError:
        pass
    labels = name.split(".")
    suffix = 2 if ".".join(labels[-2:]) in TWO_PART_SUFFIXES else 1
    return name if len(labels) == suffix + 1 else None


async def _system_resolve(name: str, rdtype: str) -> DnsAnswer:
    resolver = dns.asyncresolver.Resolver()
    resolver.lifetime = LOOKUP_SECONDS
    resolver.timeout = LOOKUP_SECONDS
    try:
        answer = await resolver.resolve(name, rdtype, raise_on_no_answer=True)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return DnsAnswer("none")
    except (TimeoutError, dns.exception.DNSException, OSError):
        return DnsAnswer("error")
    records: list[str] = []
    for rdata in answer:
        if rdtype == "TXT":
            records.append(b"".join(rdata.strings).decode("utf-8", errors="replace"))
        else:
            records.append(rdata.to_text())
    return DnsAnswer("ok", tuple(records)) if records else DnsAnswer("none")


async def observe_dns(domain: str, resolve: Resolve | None = None) -> DnsObservation:
    lookup = resolve or _system_resolve
    txt, dmarc, caa, ds = await asyncio.gather(
        lookup(domain, "TXT"),
        lookup(f"_dmarc.{domain}", "TXT"),
        lookup(domain, "CAA"),
        lookup(domain, "DS"),
    )
    return DnsObservation(domain, txt, dmarc, caa, ds)


def _short(value: str, limit: int = 160) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def check_spf(obs: DnsObservation) -> list[Finding]:
    if obs.txt.status == "error":
        return []
    spf = [r for r in obs.txt.records if re.match(r"(?i)^v=spf1(\s|$)", r.strip())]
    if not spf:
        return [
            Finding(
                id="SS-DNS-SPF-001",
                title="No SPF record is published for the domain",
                severity=Severity.LOW,
                category="Email and DNS",
                description=(
                    "SPF tells mail servers which hosts may send email for this domain. Without it, anyone can "
                    "send mail that claims to come from you, and real mail is more likely to land in spam."
                ),
                evidence=f"{obs.domain} has no TXT record that starts with v=spf1.",
                remediation=(
                    "Publish one TXT record at the domain, for example v=spf1 include:_spf.your-mail-provider.com "
                    "~all. If the domain sends no email at all, publish v=spf1 -all."
                ),
            )
        ]
    if len(spf) > 1:
        return [
            Finding(
                id="SS-DNS-SPF-003",
                title="The domain has more than one SPF record",
                severity=Severity.LOW,
                category="Email and DNS",
                description=(
                    "A domain must have exactly one SPF record. With two, receiving servers treat SPF as broken "
                    "and ignore it."
                ),
                evidence=f"{obs.domain} has {len(spf)} TXT records that start with v=spf1.",
                remediation="Merge them into a single record and delete the others.",
            )
        ]
    record = spf[0].strip()
    ending = re.search(r"(?i)(?:^|\s)([+?~-]?)all\s*$", record)
    if ending and ending.group(1) in ("+", "?", ""):
        qualifier = ending.group(1) or "+"
        return [
            Finding(
                id="SS-DNS-SPF-002",
                title="The SPF record allows any server to send mail",
                severity=Severity.MEDIUM,
                category="Email and DNS",
                description=(
                    f"The record ends in {qualifier}all, which says that every server on the internet is allowed "
                    "or not judged. It gives no protection against someone sending mail as your domain."
                ),
                evidence=f"SPF record at {obs.domain}: {_short(record)}",
                remediation="End the record in ~all (soft fail) or -all (reject) once all real senders are listed.",
            )
        ]
    return []


def check_dmarc(obs: DnsObservation) -> list[Finding]:
    if obs.dmarc.status == "error":
        return []
    dmarc = [r for r in obs.dmarc.records if re.match(r"(?i)^\s*v=dmarc1\s*;", r)]
    if not dmarc:
        return [
            Finding(
                id="SS-DNS-DMARC-001",
                title="No DMARC policy is published for the domain",
                severity=Severity.LOW,
                category="Email and DNS",
                description=(
                    "DMARC tells receiving servers what to do with mail that fails SPF and DKIM checks, and sends "
                    "you reports about misuse. Without it, spoofed mail from your domain is delivered as normal."
                ),
                evidence=f"No v=DMARC1 record exists at _dmarc.{obs.domain}.",
                remediation=(
                    "Publish a TXT record at _dmarc.<your domain>, starting with v=DMARC1; p=none; "
                    "rua=mailto:you@your-domain to collect reports, then tighten it to quarantine or reject."
                ),
            )
        ]
    policy = re.search(r"(?i);\s*p\s*=\s*(none|quarantine|reject)", dmarc[0])
    if policy and policy.group(1).lower() == "none":
        return [
            Finding(
                id="SS-DNS-DMARC-002",
                title="The DMARC policy only monitors and does not block spoofed mail",
                severity=Severity.INFO,
                category="Email and DNS",
                description=(
                    "p=none is the right first step because it gathers reports without risking real mail. "
                    "It does not stop anyone from sending mail as your domain."
                ),
                evidence=f"DMARC record at _dmarc.{obs.domain}: {_short(dmarc[0])}",
                remediation="Once the reports show only your own senders, move to p=quarantine and then p=reject.",
            )
        ]
    return []


def check_caa(obs: DnsObservation) -> list[Finding]:
    if obs.caa.status != "none":
        return []
    return [
        Finding(
            id="SS-DNS-CAA-001",
            title="No CAA record limits which authorities may issue certificates",
            severity=Severity.INFO,
            category="Email and DNS",
            description=(
                "A CAA record names the certificate authorities allowed to issue certificates for the domain. "
                "Without one, any public authority can issue a certificate if it is tricked or compromised."
            ),
            evidence=f"{obs.domain} has no CAA record.",
            remediation=(
                'Add a CAA record for the authority you use, for example: 0 issue "letsencrypt.org". '
                "Check your host's documentation first, because some hosts issue from several authorities."
            ),
        )
    ]


def check_dnssec(obs: DnsObservation) -> list[Finding]:
    if obs.ds.status != "none":
        return []
    return [
        Finding(
            id="SS-DNS-DNSSEC-001",
            title="DNSSEC is not enabled for the domain",
            severity=Severity.INFO,
            category="Email and DNS",
            description=(
                "DNSSEC signs the domain's DNS answers so resolvers can detect forged ones. It is optional and "
                "adds some operating care, but it protects against DNS spoofing."
            ),
            evidence=f"The parent zone publishes no DS record for {obs.domain}.",
            remediation=(
                "Turn on DNSSEC at your DNS provider, then add the DS record it gives you at your registrar. "
                "Many providers, Cloudflare among them, do this in a few clicks."
            ),
        )
    ]
