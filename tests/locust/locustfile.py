import logging
import os
from dataclasses import dataclass

from locust import HttpUser, between, task

SOTONGPT_TOKEN_USER = os.getenv("SOTONGPT_TOKEN_USER", "")
REQUEST_HEADERS = {"Authorization": f"Bearer {SOTONGPT_TOKEN_USER}"}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class BaseModel:
    name: str
    max_model_len: int


class User(HttpUser):
    """Locust user class for load testing SotonGPT.

    On startup, available models are fetched from the API along with their
    maximum context lengths. Each virtual user waits between 5 and 60 seconds
    between tasks to simulate how a human would likely interact. All requests
    time out after 300 seconds.
    """

    MAX_TIMEOUT = 300
    wait_time = between(5, 60)

    def _fetch_models(self):
        """Fetch available models from the API endpoint."""

        response = self.client.get(
            "/v1/models",
            headers={**REQUEST_HEADERS, "Content-Type": "application/json"},
            timeout=self.MAX_TIMEOUT,
        )
        if response.status_code != 200:
            raise ValueError("Unable to access API to query available models")

        model_data = response.json().get("data", [])
        if len(model_data) == 0:
            raise ValueError("No models available in SotonGPT")

        pending = []
        base_models = {}

        for model in model_data:
            info = model["info"]
            if info["base_model_id"] is None:
                base_models[info["id"]] = int(model["max_model_len"])
            else:
                pending.append(info["base_model_id"])

        user_facing_models = {mid: base_models[mid] for mid in pending}

        return user_facing_models

    def on_start(self) -> None:
        """Fetch available models and their context lengths from the API, skipping tasks if the call fails."""
        self.models = self._fetch_models()
