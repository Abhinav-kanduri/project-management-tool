from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import Settings


class OpenAIConfigurationError(RuntimeError):
    pass


class OpenAIResponseError(RuntimeError):
    pass


class OpenAIResponsesClient:
    """Small direct client for the OpenAI Responses API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate_structured(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: dict[str, Any],
    ) -> dict[str, Any]:
        if not self._settings.openai_api_key:
            raise OpenAIConfigurationError(
                "OPENAI_API_KEY is required to generate an AI repository summary"
            )

        request_payload = {
            "model": self._settings.openai_model,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": self._settings.openai_max_output_tokens,
            "store": False,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": json_schema,
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {self._settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self._settings.openai_base_url.rstrip('/')}/responses"

        try:
            async with httpx.AsyncClient(
                timeout=self._settings.openai_request_timeout_seconds
            ) as client:
                response = await client.post(url, headers=headers, json=request_payload)
        except httpx.HTTPError as exc:
            raise OpenAIResponseError("Could not reach the OpenAI Responses API") from exc

        if response.is_error:
            message = self._safe_error_message(response)
            raise OpenAIResponseError(message)

        payload = response.json()
        output_text = self._extract_output_text(payload)
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise OpenAIResponseError("OpenAI returned invalid structured JSON") from exc
        if not isinstance(parsed, dict):
            raise OpenAIResponseError("OpenAI returned an unexpected result shape")
        return parsed

    @staticmethod
    def _extract_output_text(payload: dict[str, Any]) -> str:
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return str(content["text"])
        output_text = payload.get("output_text")
        if output_text:
            return str(output_text)
        raise OpenAIResponseError("OpenAI response did not contain output text")

    @staticmethod
    def _safe_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error", {})
            message = error.get("message")
            if message:
                return f"OpenAI request failed: {message}"
        except (ValueError, AttributeError):
            pass
        return f"OpenAI request failed with status {response.status_code}"
