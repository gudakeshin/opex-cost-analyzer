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

llm_tokens_total = Counter(
    "llm_tokens_total",
    "Total LLM tokens consumed, by provider, model, and token type (input/output)",
    ["provider", "model", "token_type"],
)

llm_cost_usd_total = Counter(
    "llm_cost_usd_total",
    "Estimated LLM cost in USD, by provider and model",
    ["provider", "model"],
)

# Pricing per 1M tokens (input, output) — for cost estimation only.
_LLM_PRICE_PER_1M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-8": (15.0, 75.0),
    "claude-haiku-4-5-20251001": (0.80, 4.0),
    "gemini-1.5-pro": (3.5, 10.5),
    "gemini-1.5-flash": (0.075, 0.30),
}
_DEFAULT_PRICE = (3.0, 15.0)


def record_llm_usage(provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
    """Record token counts and estimated cost to Prometheus metrics."""
    p_in, p_out = _LLM_PRICE_PER_1M.get(model, _DEFAULT_PRICE)
    cost = (input_tokens * p_in + output_tokens * p_out) / 1_000_000
    llm_tokens_total.labels(provider=provider, model=model, token_type="input").inc(input_tokens)
    llm_tokens_total.labels(provider=provider, model=model, token_type="output").inc(output_tokens)
    llm_cost_usd_total.labels(provider=provider, model=model).inc(cost)
