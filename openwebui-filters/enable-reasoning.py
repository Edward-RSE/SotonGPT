"""
title: Enable Reasoning
author: Edard Parkinson
version: 2.0.0
description: Toggle the ability for the model to reason on and off.
"""

import logging
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("reasoning_toggle_filter")
logger.setLevel(logging.INFO)


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=0, description="Priority level for the filter operations."
        )
        reasoning_kwarg_name: str = Field(
            default="enable_thinking",
            description=(
                "The chat_template_kwargs key used to toggle reasoning. "
                "Qwen3-style templates use 'enable_thinking'. Change this "
                "if your model's chat template uses a different flag."
            ),
        )

    def __init__(self):
        self.valves = self.Valves()
        # When the user switches this filter ON for a message, inlet()
        # runs and reasoning is enabled. When switched OFF, inlet() is
        # skipped entirely by Open WebUI, so the model keeps its default
        # (reasoning off).
        self.toggle = True
        self.icon = """data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJjdXJyZW50Q29sb3IiIHN0cm9rZS13aWR0aD0iMS41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwYXRoIGQ9Ik05LjUgMmExIDEgMCAwMS0uOTk3LjA4OEw3IDIuMDM0IDUuNSAyLjA4OEExIDEgMCAwMSA0LjUgMkwzIDN2Nmw0LjUgOSA0LjUtOVYzTDkuNSAyeiIvPjwvc3ZnPg=="""

    def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> dict:
        """
        Only runs when the user has switched this filter ON for the
        message. Its being called at all is the signal to enable
        reasoning - no separate valve needed.
        """
        logger.info("Reasoning Toggle is ON for this message - enabling reasoning")

        body.setdefault("chat_template_kwargs", {})
        body["chat_template_kwargs"][self.valves.reasoning_kwarg_name] = True

        logger.info(f"Final chat_template_kwargs: {body['chat_template_kwargs']}")

        return body

    def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
    ) -> dict:
        return body
