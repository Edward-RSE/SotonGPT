"""
title: API Usage Tracker
description: Logs user, model, message content, and token usage for every API request. Requires at least Open WebUI v0.11.0.
version: 0.3.1
"""

import json
import os
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, Field

try:
    import psycopg2
except ImportError:
    psycopg2 = None


# Creates the table on a fresh install; on an existing deployment this is a
# no-op and the ALTER below adds base_model if it isn't there yet. Both are
# idempotent, so it's safe to run on every startup.
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS api_usage_log (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id TEXT,
    user_email TEXT,
    model TEXT,
    base_model TEXT,
    interface TEXT,
    chat_id TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    messages JSONB
);
"""

ENSURE_SCHEMA_SQL = """
ALTER TABLE api_usage_log ADD COLUMN IF NOT EXISTS base_model TEXT;
"""

INSERT_SQL = """
INSERT INTO api_usage_log (
    user_id, user_email, model, base_model, interface, chat_id,
    prompt_tokens, completion_tokens, total_tokens, messages
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
"""


def _replace_dbname(dsn: str, new_dbname: str) -> str:
    """Return dsn pointed at new_dbname, keeping host/port/user/query intact."""
    parts = urlsplit(dsn)
    new_path = "/" + new_dbname
    return urlunsplit(
        (parts.scheme, parts.netloc, new_path, parts.query, parts.fragment)
    )


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=0, description="Execution order, lower runs first"
        )
        base_dsn: str = Field(
            default_factory=lambda: os.environ.get("DATABASE_URL", ""),
            description=(
                "Postgres connection string for the SAME server/instance as "
                "Open WebUI's own database, e.g. "
                "postgresql://user:password@host:5432/openwebui. "
                "Only host/port/credentials are used from this; the actual "
                "database name is taken from db_name below. Defaults to the "
                "container's DATABASE_URL env var if left blank."
            ),
        )
        db_name: str = Field(
            default="openwebui_api_tracking",
            description=(
                "Name of the dedicated database (separate from Open WebUI's "
                "own database) that usage rows are written to. Created "
                "automatically on first run if it doesn't already exist."
            ),
        )
        maintenance_db: str = Field(
            default="postgres",
            description=(
                "Database to connect to when db_name doesn't exist yet, so "
                "CREATE DATABASE can be issued. Almost always leave as "
                "'postgres'."
            ),
        )
        enabled: bool = Field(
            default=True,
            description="Set false to pause logging without removing the filter",
        )
        debug: bool = Field(
            default=False,
            description="Log the full body/user/metadata payload for each request",
        )

    def __init__(self):
        self.valves = self.Valves()
        self._schema_ready = False

    def _target_dsn(self) -> Optional[str]:
        if not self.valves.base_dsn:
            print("[api_usage_tracker] base_dsn valve is not set; cannot log usage")
            return None
        return _replace_dbname(self.valves.base_dsn, self.valves.db_name)

    def _create_database_if_missing(self) -> None:
        maintenance_dsn = _replace_dbname(
            self.valves.base_dsn, self.valves.maintenance_db
        )
        conn = psycopg2.connect(maintenance_dsn)
        try:
            conn.autocommit = True  # CREATE DATABASE can't run inside a transaction
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (self.valves.db_name,),
                )
                if cur.fetchone() is None:
                    # db_name is validated as a Postgres identifier below, so
                    # this is safe to interpolate directly into the DDL.
                    cur.execute(f'CREATE DATABASE "{self.valves.db_name}"')
                    print(
                        f"[api_usage_tracker] created database '{self.valves.db_name}'"
                    )
        finally:
            conn.close()

    def _get_conn(self):
        if not psycopg2:
            print("[api_usage_tracker] psycopg2 is not installed; cannot log usage")
            return None
        if not self.valves.base_dsn:
            print("[api_usage_tracker] base_dsn valve is not set; cannot log usage")
            return None

        target_dsn = self._target_dsn()
        try:
            return psycopg2.connect(target_dsn)
        except psycopg2.OperationalError as e:
            if "does not exist" not in str(e):
                print(f"[api_usage_tracker] failed to connect to Postgres: {e}")
                return None
            # The dedicated database doesn't exist yet - create it and retry once.
            try:
                self._create_database_if_missing()
                return psycopg2.connect(target_dsn)
            except Exception as create_err:
                print(
                    f"[api_usage_tracker] failed to create/connect to "
                    f"'{self.valves.db_name}': {create_err}"
                )
                return None
        except Exception as e:
            print(f"[api_usage_tracker] failed to connect to Postgres: {e}")
            return None

    def _ensure_schema(self, conn) -> None:
        if self._schema_ready:
            return
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(ENSURE_SCHEMA_SQL)
        conn.commit()
        self._schema_ready = True

    @staticmethod
    def _is_direct_api_call(metadata: dict) -> bool:
        """True for a plain API request, False for a WebUI chat session.

        Open WebUI doesn't label the caller directly, so this is inferred
        from chat context: a request routed through the web interface always
        carries both a chat_id and a session_id in __metadata__. A direct API
        call (hitting /api/chat/completions without going through the UI)
        gets an empty chat_id and a null session_id instead. Both keys are
        always present on the dict, so their values are checked rather than
        their presence.
        """
        metadata = metadata or {}
        return not (metadata.get("chat_id") and metadata.get("session_id"))

    @staticmethod
    def _extract_usage(body: dict) -> dict:
        # usage can sit at the top level, or on the last message, and key names
        # vary (prompt_tokens/completion_tokens vs input_tokens/output_tokens).
        messages = body.get("messages", [])
        last_message = messages[-1] if messages else {}
        usage = body.get("usage") or last_message.get("usage") or {}

        prompt_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
        completion_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
        total_tokens = usage.get("total_tokens")
        if (
            total_tokens is None
            and prompt_tokens is not None
            and completion_tokens is not None
        ):
            total_tokens = prompt_tokens + completion_tokens

        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }

    @staticmethod
    def _extract_base_model(metadata: dict) -> Optional[str]:
        """Resolve the underlying base model for a workspace model.

        __metadata__["model"] holds Open WebUI's resolved model info dict for
        the request. For a plain (non-workspace) model there's no wrapping, so
        this returns None and the caller should fall back to the top-level
        model id. Checked defensively across the couple of shapes this dict
        has taken in different Open WebUI versions.
        """
        model_info = (metadata or {}).get("model") or {}
        if not isinstance(model_info, dict):
            return None

        # Most common: workspace model's info carries base_model_id directly.
        base_model_id = model_info.get("base_model_id")
        if base_model_id:
            return base_model_id

        # Older/alternate shape: nested under "info".
        nested_info = model_info.get("info")
        if isinstance(nested_info, dict):
            base_model_id = nested_info.get("base_model_id")
            if base_model_id:
                return base_model_id

        return None

    async def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
    ) -> dict:
        if not self.valves.enabled:
            return body

        if self.valves.debug:
            print(
                f"[api_usage_tracker] body={body} user={__user__} metadata={__metadata__}"
            )

        # Only log direct API calls - skip requests that came from a WebUI
        # chat session (identified by a chat_id + session_id pair; see
        # _is_direct_api_call for how that's inferred).
        if not self._is_direct_api_call(__metadata__):
            if self.valves.debug:
                print("[api_usage_tracker] skipping WebUI chat request")
            return body

        conn = self._get_conn()
        if conn is None:
            return body

        try:
            self._ensure_schema(conn)

            usage = self._extract_usage(body)
            messages = body.get("messages", [])
            model = body.get("model")
            base_model = self._extract_base_model(__metadata__) or model

            with conn.cursor() as cur:
                cur.execute(
                    INSERT_SQL,
                    (
                        (__user__ or {}).get("id"),
                        (__user__ or {}).get("email"),
                        model,
                        base_model,
                        (__metadata__ or {}).get("interface"),
                        (__metadata__ or {}).get("chat_id") or None,
                        usage["prompt_tokens"],
                        usage["completion_tokens"],
                        usage["total_tokens"],
                        json.dumps(messages, default=str),
                    ),
                )
            conn.commit()
        except Exception as e:
            print(f"[api_usage_tracker] failed to write usage row: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            conn.close()

        return body
