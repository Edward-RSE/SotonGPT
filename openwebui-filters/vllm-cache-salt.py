"""
title: vLLM Cache Salt
author: you
version: 0.1.0
description: >
    Adds a "cache_salt" field to outgoing chat completion requests, for use
    with vLLM's prefix-caching cache_salt parameter
    (https://docs.vllm.ai/en/latest/features/prefix_caching.html).
    Configure the salt strategy via the Valves below.
"""

import hashlib
from typing import Optional

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        salt_mode: str = Field(
            default="fixed",
            description=(
                "Strategy for generating the cache salt: "
                "'fixed' (same salt for every request), "
                "'per_user' (salt derived from the user's ID), or "
                "'per_chat' (salt derived from the chat ID)."
            ),
        )
        fixed_salt: str = Field(
            default="open-webui-cache-salt",
            description="Salt value used when salt_mode is 'fixed'.",
        )
        priority: int = Field(
            default=0, description="Priority of this filter relative to others."
        )

    def __init__(self):
        self.valves = self.Valves()

    def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
    ) -> dict:
        """Runs before the request is sent to the model, and injects cache_salt."""

        salt: Optional[str] = None
        mode = self.valves.salt_mode

        if mode == "fixed":
            salt = self.valves.fixed_salt

        elif mode == "per_user":
            user_id = (__user__ or {}).get("id")
            if user_id:
                salt = hashlib.sha256(user_id.encode()).hexdigest()

        elif mode == "per_chat":
            chat_id = (__metadata__ or {}).get("chat_id")
            if chat_id:
                salt = hashlib.sha256(chat_id.encode()).hexdigest()

        # Fall back to the fixed salt if a dynamic mode couldn't resolve one
        if not salt:
            salt = self.valves.fixed_salt

        body["cache_salt"] = salt
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        """No changes needed on the response path; returned unmodified."""
        return body
