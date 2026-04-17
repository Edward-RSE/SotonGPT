import logging
import os
import random
from dataclasses import dataclass
from typing import Any

from locust import HttpUser, between, run_single_user, task

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

SOTONGPT_TOKEN_USER = os.getenv("SOTONGPT_TOKEN_USER", "")
if not SOTONGPT_TOKEN_USER:
    raise EnvironmentError("SOTONGPT_TOKEN_USER environment variable is not set")

REQUEST_HEADERS = {"Authorization": f"Bearer {SOTONGPT_TOKEN_USER}"}
MAX_TIMEOUT = 1800  # 30 minutes for really long prompts
CHAT_COMPLETION_PROMPTS = [
    # Short / simple
    "What is 2+2?",
    "Name three primary colors.",
    "What's the capital of France?",
    "How many days are in a leap year?",
    "What is the chemical symbol for gold?",
    "Name the four seasons.",
    "What is the speed of light?",
    "Who wrote Romeo and Juliet?",
    "What is the largest planet in the solar system?",
    "How many sides does a hexagon have?",
    # Medium
    "Explain quantum computing in simple terms suitable for a 12-year-old, using clear analogies.",
    "Compare the advantages and disadvantages of remote work versus office work, with practical examples.",
    "Draft a concise, professional email requesting a project deadline extension due to unexpected technical issues.",
    "Summarise the key causes of the First World War in under 200 words.",
    "Describe three practical strategies for improving sleep quality.",
    "Explain the difference between machine learning and traditional programming.",
    "What are the main differences between a relational and a non-relational database?",
    "Outline the pros and cons of electric vehicles compared to petrol cars.",
    "Describe how the internet works in simple terms.",
    "Explain what inflation is and how it affects everyday consumers.",
    # Long / complex
    "Create a step-by-step plan to learn Python from beginner to intermediate level in three months.",
    "Write a short science fiction story set in a floating city where gravity occasionally fails.",
    "Analyze the economic impact of renewable energy adoption on traditional energy sectors.",
    "Design a beginner-friendly four-week workout programme that requires no gym equipment.",
    "Write a detailed recipe for a three-course dinner party menu suitable for vegetarians.",
    "Explain the ethical implications of artificial intelligence in healthcare decision-making.",
    "Propose a business plan for a sustainable, zero-waste coffee shop in a busy city centre.",
    "Discuss the long-term psychological effects of social media use on teenagers, citing relevant research areas.",
    "Write a short mystery story in which the detective realises they are the prime suspect.",
    "Analyze the geopolitical consequences of a major undersea internet cable being severed.",
]
CHAT_COMPLETION_FILES = [
    "example-files/gsl-readme.md",
    "example-files/interview1.txt",
    "example-files/interview2.txt",
    "example-files/paper1.pdf",
    "example-files/paper2.pdf",
]


@dataclass
class Model:
    name: str
    length: int
    base_model: str | None


class User(HttpUser):
    """Locust user class for load testing SotonGPT.

    On startup, available models are fetched from the API along with their
    maximum context lengths. Each virtual user waits between 5 and 60 seconds
    between tasks to simulate realistic human interaction. All requests time
    out after 300 seconds.

    Uses the OpenAI compatible endpoints, which will also cover the 'regular'
    Open WebUI endpoints.
    """

    # Simulate realistic human think-time between tasks
    wait_time = between(5, 60)

    def _fetch_models(self) -> list[Model]:
        """Fetch available models from the API endpoint.

        Returns
        -------
        list[Model]
            A list of models available on the API to normal users.

        """
        response = self.client.get(
            "/api/v1/models",
            headers={**REQUEST_HEADERS, "Content-Type": "application/json"},
            timeout=MAX_TIMEOUT,
        )
        response_data = response.json()
        logger.debug(
            f"/api/v1/models[response]: {response.status_code} {response_data}"
        )
        if response.status_code != 200:
            raise ValueError("Unable to access API to query available models")

        model_data = response_data.get("data", [])
        if len(model_data) == 0:
            raise ValueError("No models available in SotonGPT")

        base_models = {}
        pending_models = []

        # Get all the models in the API. Some models will not have a max_model_len
        # as they are not "base" models, e.g. they are thin wrappers, created
        # in the OpenWeb UI interface, around a "base" models served by vLLM.
        # These "thin models" tend to have easier to use model ids or have a limited
        # set of features compared to the base model. These are the "pending_models".
        # We need to first find the base models they are based on, so we can determine
        # the max model length. This is not returned by the API for some reason for
        # the thin models.
        for model in model_data:
            logger.debug("Populating model: %s", model)
            if model["owned_by"] != "openai" or model["connection_type"] != "local":
                continue
            info = model["info"]
            if model.get("preset", False):
                pending_models.append(
                    Model(name=model["id"], length=0, base_model=info["base_model_id"])
                )
            else:
                base_models[info["id"]] = Model(
                    name=info["id"],
                    length=int(model["max_model_len"]),
                    base_model=None,
                )

        if len(base_models) == 0:
            raise ValueError(
                "There are no base models in the API return for some reason"
            )

        logger.debug("Base models: %s", base_models)
        logger.debug("Pending models: %s", pending_models)

        avail_models = [
            Model(model.name, base_models[model.base_model].length, model.base_model)
            for model in pending_models
        ] + list(base_models.values())
        if len(avail_models) == 0:
            raise ValueError("There are no available LLMs")

        logger.info(f"Available models: {avail_models}")

        return avail_models

    def _pick_model(self) -> Model:
        """Return a randomly selected model.

        Returns
        -------
        Model
            A Model dataclass describing the model picked

        """
        return random.choice(self.models)

    def _pick_file(self) -> str:
        """Returns a randomly selected file.

        Returns
        -------
        str
            The file path to the file.
        """
        return random.choice(CHAT_COMPLETION_FILES)

    def _post_chat_completion(self, payload: dict) -> dict[str, Any]:
        """Send a chat completion request to the API.

        Parameters
        ----------
        payload : dict
            The request body to send to /api/v1/chat/completions.

        Returns
        -------
        dict[str, str]
            The response from the API as a JSON.

        """
        logger.debug(f"Sending request to Chat Completion with payload: {payload}")
        response = self.client.post(
            "/api/v1/chat/completions",
            json=payload,
            headers={**REQUEST_HEADERS, "Content-Type": "application/json"},
            timeout=MAX_TIMEOUT,
            name=f"/api/v1/chat/completions[{payload['model']}]",
        )

        response_json = response.json()
        logger.debug(f"Chat Completions response: {response_json['choices']}")
        tokens = response_json.get("usage", {}).get("total_tokens", "unknown")
        time = response.elapsed.total_seconds()
        logger.info(
            f"Response success from /api/v1/chat/completions - time: {time:.2f}s, tokens: {tokens}"
        )

        return response_json

    def _reset_long_conversation(self) -> None:
        """Reset long conversation variables."""
        self._long_conv = [
            {
                "role": "user",
                "content": random.choice(CHAT_COMPLETION_PROMPTS),
            }
        ]
        self._conv_model = self._pick_model()
        self._conv_cut_length = max(
            random.randint(1024, self._conv_model.length - 1024), 1024
        )

    def _upload_file(self, file_path: str) -> str:
        """Upload a file and return its ID.

        Parameters
        ----------
        file_path : str
            Path to the file to upload.

        Returns
        -------
        str
            The ID of the file.

        """
        with open(file_path, "rb") as f:
            filename = os.path.basename(file_path)

            response = self.client.post(
                "/api/v1/files/",
                headers=REQUEST_HEADERS,
                files={"file": (filename, f, "application/octet-stream")},
                timeout=MAX_TIMEOUT,
            )

        file_id = response.json().get("id")
        if not file_id:
            raise ValueError("File upload response did not contain a file ID")

        logger.debug("Uploaded file %s with ID %s", filename, file_id)

        return file_id

    def _delete_file(self, file_id: str) -> None:
        """Delete a previously uploaded file.

        Parameters
        ----------
        file_id : str
            The ID of the file to delete.

        """
        self.client.delete(
            f"/api/v1/files/{file_id}",
            headers=REQUEST_HEADERS,
            timeout=MAX_TIMEOUT,
            name="/api/v1/files/[file_id]",
        )

        logger.debug("Deleted file with ID %s", file_id)

    ############################################################################

    def on_start(self) -> None:
        """Start-up tasks.

        1. Fetch available user-facing models.

        If model fetching fails, the runner is stopped to surface the error
        clearly rather than allowing the user to proceed with no models.
        """
        try:
            self.models = self._fetch_models()
        except Exception as e:
            logger.error(f"Failed to fetch models on start-up: {e}")
            self.environment.runner.quit()

        self._reset_long_conversation()

    ############################################################################
    # Low weight tasks

    @task(1)
    def check_health_status(self) -> None:
        """Check the health endpoint."""
        self.client.get("/health", headers=REQUEST_HEADERS)

    ############################################################################
    # Medium weight tasks

    @task(5)
    def check_models(self) -> None:
        """Check the models endpoint."""
        self.client.get(
            "/api/v1/models",
            headers={**REQUEST_HEADERS, "Content-Type": "application/json"},
        )

    ############################################################################
    # High weight tasks - most representative of actual usage

    @task(10)
    def send_single_chat_completion(self) -> None:
        """Send a single-turn chat completion request with a random prompt and model."""
        model = self._pick_model()
        model_id = model.name
        payload = {
            "model": model_id,
            "messages": [
                {"role": "user", "content": random.choice(CHAT_COMPLETION_PROMPTS)}
            ],
            "temperature": random.uniform(0.1, 1.0),
        }
        self._post_chat_completion(payload)

    @task(10)
    def send_conversation_chat_completion(self) -> None:
        """Send a multi-turn chat completion, which keeps increasing in size."""
        payload = {
            "model": self._conv_model.name,
            "messages": self._long_conv,
            "temperature": random.uniform(0.1, 1.0),
        }

        response = self._post_chat_completion(payload)
        message = response["choices"][0]["message"]
        usage = response["usage"]["total_tokens"]

        # subtract 1024 from the model length as a safety margin
        if usage < self._conv_model.length - self._conv_cut_length:
            self._long_conv.append(message)
        else:
            self._reset_long_conversation()

    @task(10)
    def send_file_chat_completion(self) -> None:
        """Send a chat completion which uses a file in the context."""
        model = self._pick_model()
        file_path = self._pick_file()

        file_id = self._upload_file(file_path)
        payload = {
            "model": model.name,
            "messages": [
                {"role": "user", "content": "Summarise the contents of this file."}
            ],
            "temperature": random.uniform(0.1, 1.0),
            "files": [{"type": "file", "id": file_id}],
        }
        try:
            self._post_chat_completion(payload)
        finally:
            self._delete_file(file_id)


if __name__ == "__main__":
    run_single_user(User)
