from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import settings
from app.core.runtime_logging import get_server_logger


SchemaT = TypeVar("SchemaT", bound=BaseModel)
logger = get_server_logger()


def _safe_identifier(value: object | None) -> str | None:
    if value is None: return None
    text = str(value)[:100]
    return text if re.fullmatch(r"[A-Za-z0-9_.-]+", text) else "redacted"


def _error_details(exc: Exception, flow: str, question_type: str | None) -> dict:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    error = body.get("error", body) if isinstance(body, dict) else {}
    code = getattr(exc, "code", None) or (error.get("code") if isinstance(error, dict) else None)
    error_type = getattr(exc, "type", None) or (error.get("type") if isinstance(error, dict) else None)
    if status == 400: safe_message = "OpenAI rejected the request"
    elif status in (401, 403): safe_message = "OpenAI authentication or permission failed"
    elif status == 429: safe_message = "OpenAI rate limit exceeded"
    elif isinstance(status, int) and status >= 500: safe_message = "OpenAI service error"
    elif status: safe_message = "OpenAI API request failed"
    elif isinstance(exc, RuntimeError) and "configured" in str(exc).casefold(): safe_message = "OpenAI client is not configured"
    else: safe_message = "OpenAI request failed before receiving a response"
    return {
        "event": "openai_call_failed",
        "flow": _safe_identifier(flow) or "unknown",
        "question_type": _safe_identifier(question_type) if question_type else None,
        "exception_type": type(exc).__name__,
        "status_code": status if isinstance(status, int) else None,
        "openai_error_code": _safe_identifier(code),
        "openai_error_type": _safe_identifier(error_type),
        "safe_message": safe_message,
    }


def _log_openai_failure(exc: Exception, flow: str, question_type: str | None = None) -> None:
    # Do not log exc, traceback, request payload, prompt, headers, or SDK response body.
    logger.error("openai_call_failed %s", json.dumps(_error_details(exc, flow, question_type), separators=(",", ":")))


class AIClient:
    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        normalized = [text[: settings.embedding_max_characters] for text in texts]
        response = OpenAI(api_key=settings.openai_api_key).embeddings.create(
            model=settings.openai_embedding_model,
            input=normalized,
            dimensions=settings.openai_embedding_dimension,
        )
        return [item.embedding for item in sorted(response.data, key=lambda item: item.index)]

    def get_embedding(self, text: str) -> list[float]:
        return self.get_embeddings([text])[0]

    def structured_completion(
        self,
        *,
        prompt_name: str,
        schema: type[SchemaT],
        payload: dict,
        diagnostic_context: dict[str, str] | None = None,
    ) -> SchemaT:
        context = diagnostic_context or {}
        flow = context.get("flow", prompt_name)
        try:
            if not settings.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY is not configured")
            prompt_path = Path(__file__).resolve().parents[2] / "prompts" / f"{prompt_name}.txt"
            instructions = prompt_path.read_text(encoding="utf-8")
            response = OpenAI(api_key=settings.openai_api_key).responses.parse(
                model=settings.openai_model,
                instructions=instructions,
                input=json.dumps(payload, ensure_ascii=False),
                text_format=schema,
            )
            if response.output_parsed is None:
                raise RuntimeError("OpenAI did not return a structured result")
            return response.output_parsed
        except Exception as exc:
            _log_openai_failure(exc, flow, context.get("question_type"))
            raise


ai_client = AIClient()
