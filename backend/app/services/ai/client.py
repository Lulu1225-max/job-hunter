from __future__ import annotations


class AIClient:
    def structured_completion(self, *, prompt_name: str, schema: type, payload: dict):
        raise NotImplementedError("Configure an LLM provider before enabling live AI mutations.")


ai_client = AIClient()
