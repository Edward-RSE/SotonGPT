import time
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Optional, Tuple

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=0, description="Priority level for the filter operations."
        )
        requests_per_minute: Optional[int] = Field(
            default=10,
            description="Maximum number of requests allowed per minute, across all models.",
        )
        requests_per_hour: Optional[int] = Field(
            default=50,
            description="Maximum number of requests allowed per hour, across all models.",
        )
        sliding_window_limit: Optional[int] = Field(
            default=100,
            description="Maximum number of requests allowed within the sliding window, across all models.",
        )
        sliding_window_minutes: Optional[int] = Field(
            default=180, description="Duration of the sliding window in minutes."
        )
        enabled_for_admins: bool = Field(
            default=True,
            description="Whether rate limiting is enabled for admin users.",
        )

    def __init__(self):
        self.file_handler = False
        self.valves = self.Valves()
        # Flat per-user request log: user_id -> list of request timestamps.
        # No per-model breakdown, since the limit applies globally per user.
        self.user_requests = {}

    def prune_requests(self, user_id: str):
        now = time.time()
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
            return
        max_window_seconds = max(
            60 if self.valves.requests_per_minute is not None else 0,
            3600 if self.valves.requests_per_hour is not None else 0,
            self.valves.sliding_window_minutes * 60,
        )
        self.user_requests[user_id] = [
            req for req in self.user_requests[user_id] if now - req < max_window_seconds
        ]

    def rate_limited(self, user_id: str) -> Tuple[bool, Optional[int], int]:
        self.prune_requests(user_id)
        user_reqs = self.user_requests.get(user_id, [])
        now = time.time()

        if self.valves.requests_per_minute is not None:
            requests_last_minute = sum(1 for req in user_reqs if now - req < 60)
            if requests_last_minute >= self.valves.requests_per_minute:
                earliest_request = min(req for req in user_reqs if now - req < 60)
                return (
                    True,
                    int(60 - (now - earliest_request)),
                    requests_last_minute,
                )

        if self.valves.requests_per_hour is not None:
            requests_last_hour = sum(1 for req in user_reqs if now - req < 3600)
            if requests_last_hour >= self.valves.requests_per_hour:
                earliest_request = min(req for req in user_reqs if now - req < 3600)
                return (
                    True,
                    int(3600 - (now - earliest_request)),
                    requests_last_hour,
                )

        sliding_window_seconds = self.valves.sliding_window_minutes * 60
        requests_in_window = sum(
            1 for req in user_reqs if now - req < sliding_window_seconds
        )
        if requests_in_window >= self.valves.sliding_window_limit:
            earliest_request = min(
                req for req in user_reqs if now - req < sliding_window_seconds
            )
            return (
                True,
                int(sliding_window_seconds - (now - earliest_request)),
                requests_in_window,
            )

        return False, None, len(user_reqs)

    def log_request(self, user_id: str):
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        self.user_requests[user_id].append(time.time())

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __model__: Optional[dict] = None,
        __event_emitter__: Optional[Callable[[Any], Awaitable[None]]] = None,
    ) -> dict:
        print(f"inlet:{__name__}")
        print(f"inlet:body:{body}")
        print(f"inlet:user:{__user__}")
        if __user__ is not None and (
            __user__.get("role") != "admin" or self.valves.enabled_for_admins
        ):
            user_id = __user__["id"]
            rate_limited, wait_time, request_count = self.rate_limited(user_id)
            if rate_limited:
                current_time = datetime.now()
                future_time = current_time + timedelta(seconds=wait_time)
                future_time_str = future_time.strftime("%H:%M")
                error_message = (
                    f"You've reached your usage cap. "
                    f"Please try again after {future_time_str}."
                )
                # Notify the user via the event emitter before the request is rejected.
                if __event_emitter__:
                    await __event_emitter__(
                        {
                            "type": "status",
                            "data": {
                                "description": error_message,
                                "done": True,
                            },
                        }
                    )
                print(
                    f"Global rate limit exceeded for user {user_id}. Rejecting request. "
                    f"Next request window opens at {future_time_str}."
                )
                # Reject the request outright rather than falling back to another model.
                raise Exception(error_message)
            self.log_request(user_id)
        return body
