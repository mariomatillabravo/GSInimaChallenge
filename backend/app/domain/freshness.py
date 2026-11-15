"""When a cached month can be served and when it must be fetched again (pure rules).

A month can still change upstream while it is in progress and for a while after it ends, as
late observations are published. Once it has been fetched ``grace`` after its end, it is final
and served from the cache forever. Until then, a cached copy is served for ``ttl``.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from app.domain.chunks import CachedChunk, MonthChunk

CacheStatus = Literal["hit", "miss", "partial"]


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    ttl: timedelta
    """How long a month that can still change is served from the cache before fetching it again."""
    grace: timedelta
    """How long after a month ends its data may still change upstream."""


@dataclass(frozen=True, slots=True)
class MonthState:
    """A month used to answer a request: what the cache holds for it after the request."""

    chunk: MonthChunk
    cached: CachedChunk
    fetched_now: bool
    """Whether it was fetched from the source for this request."""


@dataclass(frozen=True, slots=True)
class CacheReport:
    """How a request was served, as reported in the response."""

    status: CacheStatus
    """``hit``: nothing had to be fetched; ``miss``: every month was fetched; ``partial``: a mix."""
    last_updated: datetime | None
    """Oldest fetch time among the months that can still change; ``None`` if all are final."""


def is_final(chunk: MonthChunk, cached: CachedChunk, policy: FreshnessPolicy) -> bool:
    """Whether the cached month was fetched late enough to never change again."""
    month_end = chunk.end + timedelta(seconds=1)
    return cached.fetched_at >= month_end + policy.grace


def needs_fetch(
    chunk: MonthChunk, cached: CachedChunk | None, now: datetime, policy: FreshnessPolicy
) -> bool:
    """Whether the month must be fetched from the source before answering at ``now``."""
    if cached is None:
        return True
    if is_final(chunk, cached, policy):
        return False
    return now - cached.fetched_at >= policy.ttl


def summarize(months: Sequence[MonthState], policy: FreshnessPolicy) -> CacheReport:
    """Build the cache report of a request from the months it used."""
    fetched = sum(month.fetched_now for month in months)
    status: CacheStatus
    if fetched == 0:
        status = "hit"
    elif fetched == len(months):
        status = "miss"
    else:
        status = "partial"
    changing = [
        month.cached.fetched_at
        for month in months
        if not is_final(month.chunk, month.cached, policy)
    ]
    return CacheReport(status=status, last_updated=min(changing, default=None))
