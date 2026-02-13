import glob
import logging
import os
import random
from io import BytesIO
from pathlib import Path

import requests

from locust import HttpUser, between, task

SOTONGPT_TOKEN_USER = os.getenv(
    "SOTONGPT_TOKEN_USER", "sk-d6c203c1c53f43eb91892627a028ac9a"
)
REQUEST_HEADERS = {"Authorization": f"Bearer {SOTONGPT_TOKEN_USER}"}

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class APIUser(HttpUser):
    wait_time = between(15, 60)
    MAX_TIMEOUT = 300

    def on_start(self) -> None:
        self.models = ("qwen3-32b", "qwen25-14b-instruct", "tiny-llama")

    # ============================================================================
    # Helper Methods - File Operations
    # ============================================================================

    def _get_example_file_paths(self) -> list[str]:
        script_dir = Path(__file__).resolve().parent
        return glob.glob(f"{script_dir}/example-files/*")

    def _read_file_bytes(self, file_path: str) -> bytes:
        with open(file_path, "rb") as f:
            return f.read()

    def _extract_file_id(self, response: requests.Response) -> str | None:
        try:
            data = response.json()
            return data.get("id") or data.get("file_id")
        except Exception:
            return None

    # ============================================================================
    # Helper Methods - Untracked Operations (not measured by Locust)
    # ============================================================================

    def _delete_file_untracked(self, file_id: str, filename: str) -> None:
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

    # ============================================================================
    # Helper Methods - Tracked Operations (measured by Locust)
    # ============================================================================

    def _analyze_file_tracked(self, file_id: str, filename: str) -> None:
        prompts = [
            f"Summarize the contents of {filename}",
            f"What are the key points in {filename}?",
            f"Extract the main data from {filename}",
            f"Analyze {filename} and provide insights",
        ]

        payload = {
            "model": random.choice(self.models),
            "messages": [
                {
                    "role": "user",
                    "content": random.choice(prompts),
                    "files": [file_id],
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

    # ============================================================================
    # Task: Simple Chat Completion
    # ============================================================================

    @task(10)
    def create_chat_completion(self):
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
            "model": random.choice(self.models),
            "messages": [{"role": "user", "content": random.choice(prompts)}],
            "temperature": random.uniform(0.5, 1.0),
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

    # ============================================================================
    # Task: Chat Completion with History
    # ============================================================================

    @task(5)
    def create_completion_with_history(self):
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
            json={"model": random.choice(self.models), "messages": messages},
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

    # ============================================================================
    # Task: Upload, Analyze, Delete (delete untracked)
    # ============================================================================

    @task(3)
    def upload_analyze_and_delete_file(self):
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

    # ============================================================================
    # Task: Upload, Analyze, Delete (all tracked)
    # ============================================================================

    @task(3)
    def upload_and_analyze_file(self):
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
