"""Thin wrapper around the OpenAI SDK pointed at the Replit AI Integrations proxy."""
from __future__ import annotations

import base64
import os
from typing import Any, Optional

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

MODEL = "gpt-5.4"
# Speech-to-speech / audio-output model. The proxy does not support the dedicated
# /audio/speech TTS endpoint, but gpt-audio chat-completions with an audio modality
# produces natural spoken audio, which we use for narration.
AUDIO_MODEL = "gpt-audio"
DEFAULT_VOICE = "alloy"

_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")

# Client-side timeouts (seconds) kept comfortably under the preview proxy's
# ~60s ceiling so a slow/unavailable upstream raises promptly and the caller can
# fall back to its heuristic builder instead of hanging until a 502.
CHAT_TIMEOUT = 30.0
AUDIO_TIMEOUT = 45.0

_client: Optional[Any] = None


def ai_available() -> bool:
    return bool(_BASE_URL and _API_KEY and OpenAI is not None)


def get_client() -> Optional[Any]:
    global _client
    if not ai_available():
        return None
    if _client is None:
        # max_retries=0 so a timeout is not silently multiplied by retry
        # attempts (which would blow past the proxy window).
        _client = OpenAI(
            base_url=_BASE_URL,
            api_key=_API_KEY,
            timeout=CHAT_TIMEOUT,
            max_retries=0,
        )
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


def speak(text: str, voice: Optional[str] = None, fmt: str = "mp3") -> bytes:
    """Synthesize spoken audio for the given text using the gpt-audio model.

    Returns raw audio bytes (mp3 by default). Raises if the AI client is
    unavailable or the model returns no audio.
    """
    client = get_client()
    if client is None:
        raise RuntimeError("AI client unavailable")
    resp = client.with_options(timeout=AUDIO_TIMEOUT).chat.completions.create(
        model=AUDIO_MODEL,
        modalities=["text", "audio"],
        audio={"voice": voice or DEFAULT_VOICE, "format": fmt},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a text-to-speech narrator. Read the user's text aloud "
                    "verbatim in a calm, natural, professional voice. Do not add, "
                    "remove, or comment on anything."
                ),
            },
            {"role": "user", "content": text},
        ],
    )
    audio = getattr(resp.choices[0].message, "audio", None)
    if not audio or not getattr(audio, "data", None):
        raise RuntimeError("no audio returned")
    return base64.b64decode(audio.data)
