"""Thin wrapper around the OpenAI SDK pointed at the Replit AI Integrations proxy."""
from __future__ import annotations

import os
from typing import Any, Optional

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

MODEL = "gpt-5.4"

_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")

_client: Optional[Any] = None


def ai_available() -> bool:
    return bool(_BASE_URL and _API_KEY and OpenAI is not None)


def get_client() -> Optional[Any]:
    global _client
    if not ai_available():
        return None
    if _client is None:
        _client = OpenAI(base_url=_BASE_URL, api_key=_API_KEY)
    return _client


def chat(messages: list, tools: Optional[list] = None, tool_choice: Optional[Any] = None,
         response_format: Optional[dict] = None):
    """Single chat-completions call. Returns the message object or raises."""
    client = get_client()
    if client is None:
        raise RuntimeError("AI client unavailable")
    kwargs: dict = {
        "model": MODEL,
        "messages": messages,
        "max_completion_tokens": 8192,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"
    if response_format:
        kwargs["response_format"] = response_format
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message
