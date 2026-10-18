"""Runs one scan end to end and persists the outcome."""

from __future__ import annotations

import asyncio
import logging
import time

from app.core.config import Settings
from app.core.logging import log_event
from app.repositories.scans import ScanRepository
from app.scanner.checks import run_checks
from app.scanner.fetcher import FetchError, fetch_target
from app.scanner.scoring import compute_score
from app.schemas.scan import TargetMetadata

logger = logging.getLogger("securescope.scan")


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
        await asyncio.to_thread(repo.mark_running, scan_id)
        try:
            result = await asyncio.wait_for(fetch_target(url, settings), timeout=settings.max_scan_seconds)
            findings, checks_run = run_checks(result)
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
                requests_made=result.requests_made,
                checks_run=checks_run,
            )
            await asyncio.to_thread(repo.complete_scan, scan_id, findings, score, grade, metadata)
            log_event(
                logger,
                "scan completed",
                scan_id=scan_id,
                host=host,
                score=score,
                findings=len(findings),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except FetchError as exc:
            await asyncio.to_thread(repo.fail_scan, scan_id, str(exc))
            log_event(logger, "scan failed", scan_id=scan_id, host=host, reason=str(exc))
        except TimeoutError:
            await asyncio.to_thread(repo.fail_scan, scan_id, "The scan exceeded its time limit.")
            log_event(logger, "scan timed out", scan_id=scan_id, host=host)
        except Exception:
            logger.exception("unexpected scan error", extra={"fields": {"scan_id": scan_id}})
            await asyncio.to_thread(repo.fail_scan, scan_id, "An unexpected error occurred.")
