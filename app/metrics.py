"""Prometheus metric objects shared across the application.

Import and record from any module — metrics are process-global singletons.
Exposed at GET /metrics in app/main.py.
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests by method, endpoint pattern, and status code",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds by method and endpoint pattern",
    ["method", "endpoint"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

opar_cycle_duration_seconds = Histogram(
    "opar_cycle_duration_seconds",
    "End-to-end OPAR loop duration in seconds",
    buckets=(1.0, 2.5, 5.0, 10.0, 20.0, 40.0, 60.0, 120.0),
)

skill_execution_duration_seconds = Histogram(
    "skill_execution_duration_seconds",
    "Time spent executing a single skill, labelled by skill name",
    ["skill_name"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

memory_hit_rate = Gauge(
    "memory_hit_rate",
    "Fraction of memory lookups satisfied from cache (rolling, updated per request)",
)
