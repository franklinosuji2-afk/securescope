"""In-process request metrics for the Platform Health page and the Prometheus endpoint.

Everything here is measured by this process since it started. It is not persisted, so it restarts from
zero whenever the API restarts or wakes from sleep (free hosting does this), and it covers one process
only. The health page says so. Route labels are the route *templates* (for example `/api/v1/scans/{scan_id}`),
never the raw path, so identifiers and tokens in URLs never become metric labels.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from dataclasses import dataclass

# Upper bounds, in seconds, of the latency histogram exposed to Prometheus.
BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
WINDOW_SECONDS = 3600.0
MAX_SAMPLES = 20_000
# Probes would drown the real traffic, and they are not what a visitor experiences.
EXCLUDED_ROUTES = frozenset({"/metrics", "/api/v1/health", "/api/v1/ready"})


@dataclass(frozen=True)
class Sample:
    at: float
    route: str
    status: int
    seconds: float


def percentile(sorted_values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile of an ascending list; None when there is nothing to measure."""
    if not sorted_values:
        return None
    rank = max(1, round(fraction * len(sorted_values) + 0.4999999))
    return sorted_values[min(rank, len(sorted_values)) - 1]


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._samples: deque[Sample] = deque(maxlen=MAX_SAMPLES)
        self.started_at = time.time()
        self._started_mono = time.monotonic()
        self._total: Counter[tuple[str, str, str]] = Counter()
        self._bucket_counts: Counter[float] = Counter()
        self._duration_sum = 0.0
        self._duration_count = 0

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._started_mono

    def record(self, route: str, method: str, status: int, seconds: float) -> None:
        if route in EXCLUDED_ROUTES:
            return
        with self._lock:
            self._samples.append(Sample(time.monotonic(), route, status, seconds))
            self._total[(method, route, f"{status // 100}xx")] += 1
            self._duration_sum += seconds
            self._duration_count += 1
            for bound in BUCKETS:
                if seconds <= bound:
                    self._bucket_counts[bound] += 1

    def window(self, seconds: float = WINDOW_SECONDS) -> dict[str, object]:
        now = time.monotonic()
        with self._lock:
            recent = [s for s in self._samples if now - s.at <= seconds]
            truncated = len(self._samples) == MAX_SAMPLES and bool(recent) and (
                now - self._samples[0].at <= seconds
            )
        durations = sorted(s.seconds for s in recent)
        errors = sum(1 for s in recent if s.status >= 500)
        client_errors = sum(1 for s in recent if 400 <= s.status < 500)
        by_route: dict[str, list[Sample]] = {}
        for s in recent:
            by_route.setdefault(s.route, []).append(s)
        routes = []
        for route, items in sorted(by_route.items(), key=lambda kv: -len(kv[1]))[:8]:
            times = sorted(i.seconds for i in items)
            p95 = percentile(times, 0.95)
            routes.append(
                {
                    "route": route,
                    "requests": len(items),
                    "errors": sum(1 for i in items if i.status >= 500),
                    "p95_ms": None if p95 is None else round(p95 * 1000),
                }
            )

        def ms(fraction: float) -> int | None:
            value = percentile(durations, fraction)
            return None if value is None else round(value * 1000)

        return {
            "window_seconds": min(seconds, self.uptime_seconds),
            "requests": len(recent),
            "server_errors": errors,
            "client_errors": client_errors,
            "error_rate": (errors / len(recent)) if recent else None,
            "p50_ms": ms(0.50),
            "p95_ms": ms(0.95),
            "p99_ms": ms(0.99),
            "routes": routes,
            "truncated": truncated,
        }

    def prometheus(self) -> list[str]:
        with self._lock:
            totals = dict(self._total)
            buckets = dict(self._bucket_counts)
            total_sum, total_count = self._duration_sum, self._duration_count
        lines = [
            "# HELP securescope_http_requests_total HTTP requests handled since process start.",
            "# TYPE securescope_http_requests_total counter",
        ]
        for (method, route, status), count in sorted(totals.items()):
            lines.append(
                f'securescope_http_requests_total{{method="{method}",route="{_esc(route)}",status="{status}"}} {count}'
            )
        lines += [
            "# HELP securescope_http_request_duration_seconds Request latency since process start.",
            "# TYPE securescope_http_request_duration_seconds histogram",
        ]
        for bound in BUCKETS:
            lines.append(
                f'securescope_http_request_duration_seconds_bucket{{le="{bound}"}} {buckets.get(bound, 0)}'
            )
        lines += [
            f'securescope_http_request_duration_seconds_bucket{{le="+Inf"}} {total_count}',
            f"securescope_http_request_duration_seconds_sum {total_sum:.6f}",
            f"securescope_http_request_duration_seconds_count {total_count}",
        ]
        return lines


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
