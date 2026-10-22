"""Runs one scan end to end and persists the outcome."""

from __future__ import annotations

import asyncio
import logging
import time

from app.core.config import Settings
from app.core.logging import log_event
from app.repositories.scans import ScanRepository
from app.scanner.checks import PROBE_PATHS, assess
from app.scanner.dns_checks import DnsObservation, eligible_domain, observe_dns
from app.scanner.fetcher import FetchError, FetchResult, ProbeResponse, fetch_probe, fetch_target
from app.scanner.scoring import compute_score
from app.scanner.tls import TlsObservation, probe_tls
from app.schemas.scan import TargetMetadata

logger = logging.getLogger("securescope.scan")


NOT_A_MAIN_DOMAIN = (
    "DNS and email checks apply to a main domain such as example.com. This site is a subdomain or not a "
    "domain name, and the parent domain is not part of what was verified."
)


async def _dns(host: str, settings: Settings) -> DnsObservation | str:
    """DNS and email records for the verified main domain, or the reason they were not looked at."""
    domain = eligible_domain(host)
    if domain is None:
        return NOT_A_MAIN_DOMAIN
    try:
        return await asyncio.wait_for(observe_dns(domain), timeout=settings.request_timeout_seconds + 4)
    except Exception:  # a DNS problem must never fail the scan; the checks are reported as skipped
        return "The DNS lookup did not give a usable answer."


async def _collect(
    url: str, settings: Settings
) -> tuple[FetchResult, TlsObservation | None, dict[str, ProbeResponse] | None, DnsObservation | str]:
    """The page fetch, one TLS observation and the fixed-path probes, all on the validated target."""
    result = await fetch_target(url, settings)
    tls: TlsObservation | None = None
    if result.final_scheme == "https" and result.resolved_addresses:
        # One verified TLS connection to the address the fetcher already validated and pinned.
        tls = await asyncio.wait_for(
            asyncio.to_thread(
                probe_tls,
                result.host,
                result.resolved_addresses[0],
                result.port,
                settings.request_timeout_seconds,
            ),
            timeout=settings.request_timeout_seconds + 2,
        )
    responses, dns = await asyncio.gather(
        asyncio.gather(*(fetch_probe(result, path, settings) for path in PROBE_PATHS)),
        _dns(result.host, settings),
    )
    return result, tls, {r.path: r for r in responses}, dns


async def execute_scan(
    scan_id: str,
    url: str,
    host: str,
    settings: Settings,
    repo: ScanRepository,
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        started = time.monotonic()
        if not await asyncio.to_thread(repo.mark_running, scan_id):
            return  # cancelled while it was waiting for a free slot
        try:
            result, tls, probes, dns = await asyncio.wait_for(
                _collect(url, settings), timeout=settings.max_scan_seconds
            )
            assessment = assess(result, tls, probes, dns)
            findings = assessment.findings
            score, grade = compute_score(findings)
            metadata = TargetMetadata(
                requested_url=result.requested_url,
                final_url=result.final_url,
                host=result.host,
                resolved_addresses=result.resolved_addresses,
                status_code=result.status_code,
                content_type=result.headers.get("content-type"),
                redirect_chain=result.redirect_chain,
                off_origin_redirect=result.off_origin_redirect,
                response_time_ms=result.elapsed_ms,
                requests_made=result.requests_made + (len(probes) if probes else 0),
                checks_run=assessment.checks_run,
                checks_skipped=assessment.checks_skipped,
                tls=assessment.tls,
            )
            stored = await asyncio.to_thread(
                repo.complete_scan, scan_id, findings, score, grade, metadata, assessment.unverified_prefixes
            )
            if not stored:
                log_event(logger, "scan finished after it was cancelled; result discarded", scan_id=scan_id)
                return
            log_event(
                logger,
                "scan completed",
                scan_id=scan_id,
                host=host,
                score=score,
                findings=len(findings),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except asyncio.CancelledError:
            log_event(logger, "scan cancelled", scan_id=scan_id, host=host)
            raise
        except FetchError as exc:
            await asyncio.to_thread(repo.fail_scan, scan_id, str(exc))
            log_event(logger, "scan failed", scan_id=scan_id, host=host, reason=str(exc))
        except TimeoutError:
            await asyncio.to_thread(repo.fail_scan, scan_id, "The scan exceeded its time limit.")
            log_event(logger, "scan timed out", scan_id=scan_id, host=host)
        except Exception:
            logger.exception("unexpected scan error", extra={"fields": {"scan_id": scan_id}})
            await asyncio.to_thread(repo.fail_scan, scan_id, "An unexpected error occurred.")
