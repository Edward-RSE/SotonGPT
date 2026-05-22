import logging
import os
import time
from typing import List, Optional

from fastapi import HTTPException, status
from pydantic import BaseModel
from schemas import OpenAIChatMessage

# ---------------------------------------------------------------------------
# Module-level logger
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


class Pipeline:
    class Valves(BaseModel):
        # List target pipeline ids (models) that this filter will be connected to.
        # Use ["*"] to connect to all pipelines.
        pipelines: List[str] = []

        # Lower number = higher priority when multiple filters are active.
        priority: int = 0

        # Rate-limit valves (None = disabled for that check).
        requests_per_minute: Optional[int] = None
        requests_per_hour: Optional[int] = None
        sliding_window_limit: Optional[int] = None
        sliding_window_minutes: Optional[int] = None

    def __init__(self):
        self.type = "filter"
        self.name = "Rate Limit Filter"

        self.valves = self.Valves(
            **{
                "pipelines": os.getenv("RATE_LIMIT_PIPELINES", "*").split(","),
                "requests_per_minute": int(
                    os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", 1)
                ),
                "requests_per_hour": int(
                    os.getenv("RATE_LIMIT_REQUESTS_PER_HOUR", 1000)
                ),
                "sliding_window_limit": int(
                    os.getenv("RATE_LIMIT_SLIDING_WINDOW_LIMIT", 100)
                ),
                "sliding_window_minutes": int(
                    os.getenv("RATE_LIMIT_SLIDING_WINDOW_MINUTES", 15)
                ),
            }
        )

        # Per-user request timestamp log: user_id -> list[float]
        self.user_requests: dict[str, list[float]] = {}

        logger.info(
            "Pipeline '%s' initialised — limits: %d req/min | %d req/hr | "
            "%d req per %d-min window | connected to: %s",
            self.name,
            self.valves.requests_per_minute or 0,
            self.valves.requests_per_hour or 0,
            self.valves.sliding_window_limit or 0,
            self.valves.sliding_window_minutes or 0,
            self.valves.pipelines,
        )

    async def on_startup(self):
        logger.info("on_startup: %s", __name__)

    async def on_shutdown(self):
        logger.info(
            "on_shutdown: %s — flushing %d user records",
            __name__,
            len(self.user_requests),
        )
        self.user_requests.clear()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _max_retention_seconds(self) -> float:
        """Return the longest window we need to retain timestamps for."""
        windows = []
        if self.valves.requests_per_minute is not None:
            windows.append(60.0)
        if self.valves.requests_per_hour is not None:
            windows.append(3600.0)
        if (
            self.valves.sliding_window_limit is not None
            and self.valves.sliding_window_minutes is not None
        ):
            windows.append(self.valves.sliding_window_minutes * 60.0)
        # Keep at least 1 hour if nothing is configured so we don't prune
        # data we might still need.
        return max(windows, default=3600.0)

    def prune_requests(self, user_id: str) -> None:
        """Remove timestamps that fall outside every active window."""
        if user_id not in self.user_requests:
            return

        now = time.time()
        cutoff = now - self._max_retention_seconds()
        before = len(self.user_requests[user_id])
        self.user_requests[user_id] = [
            ts for ts in self.user_requests[user_id] if ts > cutoff
        ]
        after = len(self.user_requests[user_id])

        if before != after:
            logger.debug(
                "prune_requests: pruned %d stale timestamp(s) for user '%s' (%d remaining)",
                before - after,
                user_id,
                after,
            )

    def log_request(self, user_id: str) -> None:
        """Record the current timestamp for a user."""
        now = time.time()
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
            logger.debug("log_request: first request seen for user '%s'", user_id)
        self.user_requests[user_id].append(now)
        logger.debug(
            "log_request: recorded request for user '%s' (total in memory: %d)",
            user_id,
            len(self.user_requests[user_id]),
        )

    def rate_limited(self, user_id: str) -> bool:
        """
        Return True if the user has exceeded any active rate limit.

        Prunes old timestamps first so counts are accurate, then takes a
        single `now` snapshot to avoid drift across the three checks.
        """
        self.prune_requests(user_id)

        now = time.time()
        user_reqs = self.user_requests.get(user_id, [])

        if self.valves.requests_per_minute is not None:
            count = sum(1 for ts in user_reqs if now - ts < 60)
            logger.debug(
                "rate_limited: user '%s' — %d/%d requests in last minute",
                user_id,
                count,
                self.valves.requests_per_minute,
            )
            if count >= self.valves.requests_per_minute:
                logger.warning(
                    "rate_limited: BLOCKED user '%s' — per-minute limit reached (%d/%d)",
                    user_id,
                    count,
                    self.valves.requests_per_minute,
                )
                return True

        if self.valves.requests_per_hour is not None:
            count = sum(1 for ts in user_reqs if now - ts < 3600)
            logger.debug(
                "rate_limited: user '%s' — %d/%d requests in last hour",
                user_id,
                count,
                self.valves.requests_per_hour,
            )
            if count >= self.valves.requests_per_hour:
                logger.warning(
                    "rate_limited: BLOCKED user '%s' — per-hour limit reached (%d/%d)",
                    user_id,
                    count,
                    self.valves.requests_per_hour,
                )
                return True

        if (
            self.valves.sliding_window_limit is not None
            and self.valves.sliding_window_minutes is not None
        ):
            window_seconds = self.valves.sliding_window_minutes * 60
            count = sum(1 for ts in user_reqs if now - ts < window_seconds)
            logger.debug(
                "rate_limited: user '%s' — %d/%d requests in sliding %d-min window",
                user_id,
                count,
                self.valves.sliding_window_limit,
                self.valves.sliding_window_minutes,
            )
            if count >= self.valves.sliding_window_limit:
                logger.warning(
                    "rate_limited: BLOCKED user '%s' — sliding-window limit reached (%d/%d in %d min)",
                    user_id,
                    count,
                    self.valves.sliding_window_limit,
                    self.valves.sliding_window_minutes,
                )
                return True

        logger.debug("rate_limited: user '%s' is within all limits", user_id)
        return False

    # ------------------------------------------------------------------
    # Filter entry-point
    # ------------------------------------------------------------------

    async def inlet(self, body: dict, user: Optional[dict] = None) -> dict:
        # Guard against a missing/None user dict before any attribute access.
        if user is None:
            logger.warning(
                "inlet: received request with no user context — passing through"
            )
            return body

        role = user.get("role", "admin")
        user_id = user.get("id", "default_user")

        logger.debug("inlet: request from user '%s' (role=%s)", user_id, role)

        # Rate limiting only applies to non-admin users.
        if role != "user":
            logger.debug(
                "inlet: skipping rate-limit check for user '%s' with role '%s'",
                user_id,
                role,
            )
            return body

        if self.rate_limited(user_id):
            logger.warning(
                "inlet: rejecting request from user '%s' — rate limit exceeded",
                user_id,
            )
            raise Exception("Rate limit exceeded. Please try again later.")

        self.log_request(user_id)
        logger.info("inlet: request from user '%s' accepted and logged", user_id)
        return body
