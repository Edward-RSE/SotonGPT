import glob
import logging
import os
import random
from io import BytesIO
from pathlib import Path

import requests

from locust import HttpUser, between, task

SOTONGPT_TOKEN_USER = os.getenv("SOTONGPT_TOKEN_USER", "")
REQUEST_HEADERS = {"Authorization": f"Bearer {SOTONGPT_TOKEN_USER}"}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TOKENS_PER_WORD = 1.3
LARGE_CONTEXT_MIN_RATIO = 0.50
LARGE_CONTEXT_MAX_RATIO = 0.95


class APIUser(HttpUser):
    """
    Locust user class for load testing an Open WebUI-compatible chat completion API.

    On startup, available models are fetched from the API along with their maximum
    context lengths. If the model fetch fails, all tasks are skipped gracefully.

    The following tasks are executed at the weights shown:

        - create_chat_completion (10): single-turn completion with a random prompt
        - create_completion_with_history (5): multi-turn completion with a fixed history
        - upload_analyze_and_delete_file (3): upload a file, analyse it, delete it untracked
        - upload_and_analyze_file (3): upload a file, analyse it, delete it (all tracked)
        - large_context_window_completion (3): multi-turn completion targeting 90% of the
          selected model's maximum context length

    Each virtual user waits between 15 and 30 seconds between tasks.
    All requests time out after 300 seconds.
    """
    MAX_TIMEOUT = 300
    # wait_time = between(15, 30)
    wait_time = between(1, 5)

    def on_start(self) -> None:
        """Fetch available models and their context lengths from the API, skipping tasks if the call fails."""
        self.models = self._fetch_models()

    def _fetch_models(self) -> dict[str, int] | None:
        """Fetch all active models from the API and return a mapping of model ID to max context length."""
        try:
            response = requests.get(
                f"{self.host}/api/models",
                headers=REQUEST_HEADERS,
                timeout=self.MAX_TIMEOUT,
            )
            if response.status_code != 200:
                logger.error(f"Model fetch failed: {response.status_code}")
                return None

            data = response.json().get("data", [])
            models = {}
            for model in data:
                model_id = model.get("id")
                max_model_len = model.get("max_model_len")
                if model_id and max_model_len:
                    models[model_id] = max_model_len
                    logger.info(f"Registered model: {model_id} (max_model_len={max_model_len})")

            if not models:
                logger.error("No usable models found in API response")
                return None

            return models

        except Exception as e:
            logger.error(f"Model fetch error: {e}")
            return None

    def _pick_model(self) -> tuple[str, int] | None:
        """Return a randomly selected (model_id, max_model_len) tuple, or None if no models are available."""
        if not self.models:
            logger.warning("No models available, skipping task")
            return None
        model_id = random.choice(list(self.models.keys()))
        return model_id, self.models[model_id]

    def _get_example_file_paths(self) -> list[str]:
        """Return a list of file paths for all example files in the script's directory."""
        script_dir = Path(__file__).resolve().parent
        return glob.glob(f"{script_dir}/example-files/*")

    def _read_file_bytes(self, file_path: str) -> bytes:
        """Read and return the raw bytes of the file at the given path."""
        with open(file_path, "rb") as f:
            return f.read()

    def _extract_file_id(self, response: requests.Response) -> str | None:
        """Extract and return the file ID from an API response, or None if parsing fails."""
        try:
            data = response.json()
            return data.get("id") or data.get("file_id")
        except Exception:
            return None

    def _delete_file_untracked(self, file_id: str, filename: str) -> None:
        """Delete a file by its ID without Locust tracking the request."""
        try:
            response = requests.delete(
                f"{self.host}/api/v1/files/{file_id}",
                headers=REQUEST_HEADERS,
                timeout=self.MAX_TIMEOUT,
            )
            if response.status_code in [200, 204]:
                logger.info(f"Deleted (untracked): {filename} (ID: {file_id})")
            else:
                logger.warning(f"Delete failed: {filename} ({response.status_code})")
        except Exception as e:
            logger.error(f"Delete error: {filename} - {e}")

    def _analyze_file_tracked(self, file_id: str, filename: str) -> None:
        """Fetch uploaded file content and send a tracked chat completion request with it inlined."""
        model = self._pick_model()
        if not model:
            return
        model_id, _ = model

        # Fetch the file content back from the API
        try:
            content_response = requests.get(
                f"{self.host}/api/v1/files/{file_id}/content",
                headers=REQUEST_HEADERS,
                timeout=self.MAX_TIMEOUT,
            )
            if content_response.status_code != 200:
                logger.error(f"File content fetch failed: {filename} ({content_response.status_code})")
                return
            file_text = content_response.text
        except Exception as e:
            logger.error(f"File content fetch error: {filename} - {e}")
            return

        prompts = [
            f"Summarise the contents of the following file ({filename}):\n\n{{content}}",
            f"What are the key points in the following file ({filename})?\n\n{{content}}",
            f"Extract the main data from the following file ({filename}):\n\n{{content}}",
            f"Analyse the following file ({filename}) and provide insights:\n\n{{content}}",
        ]

        prompt = random.choice(prompts).format(content=file_text)

        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
        }

        with self.client.post(
            "/api/chat/completions",
            json=payload,
            headers={**REQUEST_HEADERS, "Content-Type": "application/json"},
            catch_response=True,
            timeout=self.MAX_TIMEOUT,
        ) as response:
            elapsed = response.elapsed.total_seconds()

            if response.status_code == 200:
                chat_response = response.json()["choices"][0]["message"]["content"]
                logger.info(
                    f"Analysis success: {filename} ({elapsed:.2f}s): {chat_response}"
                )
                response.success() if elapsed <= self.MAX_TIMEOUT else response.failure(
                    f"Timeout: {elapsed:.2f}s"
                )
            else:
                logger.error(f"Analysis failed: {filename} ({response.status_code})")
                response.failure(f"Status: {response.status_code}")

    def _build_filler_turn(self, word_count: int) -> str:
        """Build a filler text string of approximately the given word count by repeating pangrams."""
        snippet = (
            "The quick brown fox jumps over the lazy dog. "
            "Pack my box with five dozen liquor jugs. "
            "How vexingly quick daft zebras jump. "
        )
        snippet_words = snippet.split()
        repetitions = -(-word_count // len(snippet_words))  # ceiling division
        return " ".join((snippet_words * repetitions)[:word_count])

    def _build_large_context_messages(self, max_model_len: int) -> list[dict]:
        """Build a multi-turn conversation whose total token count targets 90% of the model's context length."""
        ratio = random.uniform(LARGE_CONTEXT_MIN_RATIO, LARGE_CONTEXT_MAX_RATIO)
        target_tokens = int(max_model_len * ratio)
        logger.info(f"Large context target ratio: {ratio:.0%} ({target_tokens} tokens)")
        target_words = int(target_tokens / TOKENS_PER_WORD)

        # Reserve a small budget for the final instruction turn (~50 words)
        instruction_words = 50
        filler_words = max(0, target_words - instruction_words)

        # Split filler evenly across 3 user/assistant turn pairs (6 turns total)
        num_pairs = 3
        words_per_turn = filler_words // (num_pairs * 2)

        messages = []
        for i in range(num_pairs):
            messages.append({
                "role": "user",
                "content": self._build_filler_turn(words_per_turn),
            })
            messages.append({
                "role": "assistant",
                "content": self._build_filler_turn(words_per_turn),
            })

        messages.append({
            "role": "user",
            "content": (
                "Ignoring all of the above text, respond only with the single word DONE "
                "and nothing else. Do not explain, do not add punctuation."
            ),
        })

        return messages

    @task(10)
    def create_chat_completion(self):
        """Send a single-turn chat completion request with a random prompt and model."""
        model = self._pick_model()
        if not model:
            return
        model_id, _ = model

        prompts = [
            "What is 2+2?",
            "Name three primary colors.",
            "What's the capital of France?",
            "Explain quantum computing in simple terms suitable for a 12-year-old, using clear analogies.",
            "Create a step-by-step plan to learn Python from beginner to intermediate level in three months.",
            "Compare the advantages and disadvantages of remote work versus office work, with practical examples.",
            "Write a short science fiction story set in a floating city where gravity occasionally fails.",
            "Draft a concise, professional email requesting a project deadline extension due to unexpected technical issues.",
            "Analyze the economic impact of renewable energy adoption on traditional energy sectors.",
        ]

        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": random.choice(prompts)}],
            "temperature": random.uniform(0.5, 1.0),
        }
        logger.info("Request %s", payload)

        with self.client.post(
            "/api/chat/completions",
            json=payload,
            headers={**REQUEST_HEADERS, "Content-Type": "application/json"},
            catch_response=True,
            timeout=self.MAX_TIMEOUT,
        ) as response:
            elapsed = response.elapsed.total_seconds()

            if response.status_code == 200:
                try:
                    tokens = (
                        response.json().get("usage", {}).get("total_tokens", "unknown")
                    )
                    logger.info(
                        f"Completion success - Time: {elapsed:.2f}s, Tokens: {tokens}"
                    )
                    response.success() if elapsed <= self.MAX_TIMEOUT else response.failure(
                        f"Timeout: {elapsed:.2f}s"
                    )
                except Exception as e:
                    logger.error(f"Parse error: {e}")
                    response.failure(f"Invalid response: {e}")
            else:
                logger.error(f"Completion failed: {response.status_code}")
                response.failure(f"Status: {response.status_code}")

    # @task(5)
    def create_completion_with_history(self):
        """Send a multi-turn chat completion request using a fixed conversation history."""
        model = self._pick_model()
        if not model:
            return
        model_id, _ = model

        messages = [
            {"role": "user", "content": "Hello! Can you help me with Python?"},
            {
                "role": "assistant",
                "content": "Of course! I'd be happy to help you with Python. What would you like to know?",
            },
            {"role": "user", "content": "How do I read a CSV file?"},
        ]

        with self.client.post(
            "/api/chat/completions",
            json={"model": model_id, "messages": messages},
            headers={**REQUEST_HEADERS, "Content-Type": "application/json"},
            catch_response=True,
            timeout=self.MAX_TIMEOUT,
        ) as response:
            elapsed = response.elapsed.total_seconds()

            if response.status_code == 200:
                logger.info(f"Multi-turn success - Time: {elapsed:.2f}s")
                response.success() if elapsed <= self.MAX_TIMEOUT else response.failure(
                    f"Timeout: {elapsed:.2f}s"
                )
            else:
                logger.error(f"Multi-turn failed: {response.status_code}")
                response.failure(f"Status: {response.status_code}")

    # @task(3)
    def upload_analyze_and_delete_file(self):
        """Upload a random example file, analyse it via a tracked request, then delete it untracked."""
        if not self.models:
            logger.warning("No models available, skipping task")
            return

        file_paths = self._get_example_file_paths()
        if not file_paths:
            logger.warning("No example files found")
            return

        file_path = random.choice(file_paths)
        filename = os.path.basename(file_path)

        with self.client.post(
            "/api/v1/files/",
            files={
                "file": (
                    filename,
                    BytesIO(self._read_file_bytes(file_path)),
                    "application/octet-stream",
                )
            },
            headers=REQUEST_HEADERS,
            catch_response=True,
            timeout=self.MAX_TIMEOUT,
        ) as upload_response:
            if upload_response.status_code in [200, 201]:
                file_id = self._extract_file_id(upload_response)
                if file_id:
                    logger.info(f"Uploaded: {filename} (ID: {file_id})")
                    upload_response.success()
                    self._analyze_file_tracked(file_id, filename)
                    self._delete_file_untracked(file_id, filename)
                else:
                    logger.error(f"No file_id for {filename}")
                    upload_response.failure("No file_id in response")
            else:
                logger.error(f"Upload failed: {upload_response.status_code}")
                upload_response.failure(f"Status: {upload_response.status_code}")

    # @task(3)
    def upload_and_analyze_file(self):
        """Upload a random example file, analyse it, and delete it — all tracked by Locust."""
        if not self.models:
            logger.warning("No models available, skipping task")
            return

        file_paths = self._get_example_file_paths()
        if not file_paths:
            logger.warning("No example files found")
            return

        file_path = random.choice(file_paths)
        filename = os.path.basename(file_path)

        with self.client.post(
            "/api/v1/files/",
            files={
                "file": (
                    filename,
                    BytesIO(self._read_file_bytes(file_path)),
                    "application/octet-stream",
                )
            },
            headers=REQUEST_HEADERS,
            catch_response=True,
            timeout=self.MAX_TIMEOUT,
        ) as upload_response:
            if upload_response.status_code in [200, 201]:
                try:
                    file_id = self._extract_file_id(upload_response)
                    if file_id:
                        logger.info(f"Uploaded: {filename} (ID: {file_id})")
                        upload_response.success()
                        self._analyze_file_tracked(file_id, filename)

                        delete_response = requests.delete(
                            f"{self.host}/api/v1/files/{file_id}",
                            headers=REQUEST_HEADERS,
                            timeout=self.MAX_TIMEOUT,
                        )

                        if delete_response.status_code in [200, 204]:
                            logger.info(f"Deleted: {filename} (ID: {file_id})")
                        else:
                            logger.warning(
                                f"Delete failed: {filename} ({delete_response.status_code})"
                            )
                except Exception as e:
                    logger.error(f"Parse error: {e}")
                    upload_response.failure(f"Invalid response: {e}")
            else:
                logger.error(f"Upload failed: {upload_response.status_code}")
                upload_response.failure(f"Status: {upload_response.status_code}")

    # @task(3)
    def large_context_window_completion(self):
        """Send a multi-turn completion request targeting 90% of the selected model's max context length."""
        model = self._pick_model()
        if not model:
            return
        model_id, max_model_len = model

        messages = self._build_large_context_messages(max_model_len)
        payload = {"model": model_id, "messages": messages}

        with self.client.post(
            "/api/chat/completions",
            json=payload,
            headers={**REQUEST_HEADERS, "Content-Type": "application/json"},
            catch_response=True,
            timeout=self.MAX_TIMEOUT,
        ) as response:
            elapsed = response.elapsed.total_seconds()

            if response.status_code == 200:
                try:
                    tokens = (
                        response.json().get("usage", {}).get("total_tokens", "unknown")
                    )
                    logger.info(
                        f"Large context success - Model: {model_id}, Time: {elapsed:.2f}s, Tokens: {tokens}"
                    )
                    response.success() if elapsed <= self.MAX_TIMEOUT else response.failure(
                        f"Timeout: {elapsed:.2f}s"
                    )
                except Exception as e:
                    logger.error(f"Parse error: {e}")
                    response.failure(f"Invalid response: {e}")
            else:
                logger.error(f"Large context failed: {response.status_code}")
                response.failure(f"Status: {response.status_code}")
