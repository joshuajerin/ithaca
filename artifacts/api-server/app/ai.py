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
# Speech-to-text model (audio in, text out). Used by the /transcribe endpoint so
# browsers without the Web Speech API (Safari/Firefox) can still drive Voice Mode
# by uploading recorded mic audio for server-side recognition.
TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"

_BASE_URL = os.environ.get("AI_INTEGRATIONS_OPENAI_BASE_URL")
_API_KEY = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY")

# Client-side timeouts (seconds) kept comfortably under the preview proxy's
# ~60s ceiling so a slow/unavailable upstream raises promptly and the caller can
# fall back to its heuristic builder instead of hanging until a 502.
CHAT_TIMEOUT = 30.0
AUDIO_TIMEOUT = 45.0
TRANSCRIBE_TIMEOUT = 30.0

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


# gpt-audio voices exposed in the UI. Keep this list in sync with the frontend
# voice picker (artifacts/terminal/src/lib/voiceSettings.ts).
AVAILABLE_VOICES = ("alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse")

# Speaking-rate bounds. The gpt-audio chat-completions endpoint has no native
# speed knob, so we steer pacing through the narrator instruction and clamp the
# requested multiplier to a range that stays intelligible.
MIN_SPEED = 0.5
MAX_SPEED = 1.5
DEFAULT_SPEED = 1.0


def _pace_instruction(speed: float) -> str:
    """Translate a speaking-rate multiplier into a pacing directive for the narrator."""
    if speed <= 0.7:
        return "Speak slowly and deliberately, leaving clear pauses between sentences."
    if speed <= 0.9:
        return "Speak at a relaxed, slightly slower-than-normal pace."
    if speed >= 1.3:
        return "Speak briskly and energetically, at a noticeably faster pace, without rushing words together."
    if speed >= 1.1:
        return "Speak at a brisk, slightly faster-than-normal pace."
    return "Speak at a natural, even pace."


def speak(
    text: str,
    voice: Optional[str] = None,
    speed: Optional[float] = None,
    fmt: str = "mp3",
) -> bytes:
    """Synthesize spoken audio for the given text using the gpt-audio model.

    ``voice`` selects one of the gpt-audio voices (falls back to a default when
    unknown). ``speed`` is a speaking-rate multiplier (1.0 = normal) steered via
    the narrator instruction since the endpoint has no native speed parameter.

    Returns raw audio bytes (mp3 by default). Raises if the AI client is
    unavailable or the model returns no audio.
    """
    client = get_client()
    if client is None:
        raise RuntimeError("AI client unavailable")

    chosen_voice = voice if voice in AVAILABLE_VOICES else DEFAULT_VOICE
    rate = DEFAULT_SPEED if speed is None else max(MIN_SPEED, min(MAX_SPEED, speed))

    resp = client.with_options(timeout=AUDIO_TIMEOUT).chat.completions.create(
        model=AUDIO_MODEL,
        modalities=["text", "audio"],
        audio={"voice": chosen_voice, "format": fmt},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a text-to-speech narrator. Read the user's text aloud "
                    "verbatim in a calm, natural, professional voice. Do not add, "
                    "remove, or comment on anything. "
                    + _pace_instruction(rate)
                ),
            },
            {"role": "user", "content": text},
        ],
    )
    audio = getattr(resp.choices[0].message, "audio", None)
    if not audio or not getattr(audio, "data", None):
        raise RuntimeError("no audio returned")
    return base64.b64decode(audio.data)


def transcribe(audio_bytes: bytes, filename: str = "audio.webm") -> str:
    """Transcribe recorded mic audio to text using the STT model.

    `audio_bytes` is the raw recorded clip (webm/mp4/wav/etc.); `filename` carries
    the extension the model uses to infer the container. Returns the recognized
    text (possibly empty). Raises if the AI client is unavailable.
    """
    import io

    client = get_client()
    if client is None:
        raise RuntimeError("AI client unavailable")
    buffer = io.BytesIO(audio_bytes)
    buffer.name = filename
    resp = client.with_options(timeout=TRANSCRIBE_TIMEOUT).audio.transcriptions.create(
        model=TRANSCRIBE_MODEL,
        file=(filename, buffer),
    )
    return (getattr(resp, "text", None) or "").strip()
