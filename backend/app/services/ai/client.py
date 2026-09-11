from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from app.core.config import settings


SchemaT = TypeVar("SchemaT", bound=BaseModel)


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
    ) -> SchemaT:
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


ai_client = AIClient()
