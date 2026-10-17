"""Instancias compartidas de limitadores (rate limit y concurrencia)."""

from __future__ import annotations

from .config import MAX_CONCURRENT_JOBS, RATE_LIMIT_PER_MINUTE
from .security import ConcurrencyLimiter, RateLimiter

rate_limiter = RateLimiter(RATE_LIMIT_PER_MINUTE)
job_limiter = ConcurrencyLimiter(MAX_CONCURRENT_JOBS)
