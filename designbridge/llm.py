"""Gemini LLM client for DesignBridge.

``call_llm`` / ``call_llm_stream`` call the Google Generative AI SDK directly.
Tries ``GEMINI_API_KEY`` first; if that key fails, it walks through the
comma-separated extra keys in ``GEMINI_API_KEYS`` in order until one works.
Raises ``RuntimeError`` if no key is set or every key fails.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from designbridge.config import Config


# ── Shared helpers ───────────────────────────────────────────────────────────

def _resolve_gemini_api_keys() -> list[str]:
    """Ordered, deduplicated list of Gemini API keys to try.

    ``GEMINI_API_KEY`` is tried first, then each entry of ``GEMINI_API_KEYS``
    (comma-separated) in order.
    """
    keys: list[str] = []
    primary = (Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY") or "").strip()
    if primary:
        keys.append(primary)

    extra_raw = Config.GEMINI_API_KEYS or os.getenv("GEMINI_API_KEYS", "")
    for k in extra_raw.split(","):
        k = k.strip()
        if k and k not in keys:
            keys.append(k)

    return keys


def _image_to_gemini_blob(image: str | bytes | Path) -> dict:
    """Convert image to a Gemini inline blob dict {mime_type, data}."""
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".webp": "image/webp", ".gif": "image/gif"}

    if isinstance(image, str) and image.startswith(("http://", "https://")):
        import httpx
        resp = httpx.get(image, timeout=15, follow_redirects=True)
        resp.raise_for_status()
        suffix = Path(image.split("?")[0]).suffix.lower()
        mime = mime_map.get(suffix, "image/jpeg")
        return {"mime_type": mime, "data": resp.content}

    if isinstance(image, bytes):
        return {"mime_type": "image/jpeg", "data": image}

    path = Path(image)
    mime = mime_map.get(path.suffix.lower(), "image/jpeg")
    return {"mime_type": mime, "data": path.read_bytes()}


def _history_to_gemini(history: list[dict]) -> list[dict]:
    """Convert OpenAI-style history to Gemini chat history format."""
    result = []
    for msg in history:
        role = msg.get("role", "user")
        if role == "assistant":
            role = "model"
        elif role == "system":
            continue  # system handled via system_instruction
        content = msg.get("content", "")
        parts = [content] if isinstance(content, str) else [p.get("text", "") for p in content if p.get("type") == "text"]
        result.append({"role": role, "parts": parts})
    return result


def _build_gemini_parts(
    prompt: str,
    images: list[str | bytes | Path] | None,
) -> list:
    """Build a list of google.genai Part objects from images + text."""
    from google.genai import types
    parts: list = []
    for img in (images or []):
        blob = _image_to_gemini_blob(img)
        parts.append(types.Part.from_bytes(data=blob["data"], mime_type=blob["mime_type"]))
    parts.append(prompt)
    return parts


def _gemini_client_and_config(
    api_key: str,
    system: str | None,
    temperature: float | None,
    max_tokens: int | None,
):
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai 未安裝。請先執行: pip install google-genai") from exc

    client = genai.Client(api_key=api_key)
    cfg = types.GenerateContentConfig(
        temperature=temperature if temperature is not None else Config.GEMINI_TEMPERATURE,
        **({"max_output_tokens": max_tokens} if max_tokens is not None else {}),
        **({"system_instruction": system} if system else {}),
    )
    return client, cfg


def _no_key_error() -> RuntimeError:
    return RuntimeError("GEMINI_API_KEY 未設定。請在 .env 中設定 GEMINI_API_KEY（可選：GEMINI_API_KEYS 作為備援）。")


# ── Public API ───────────────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    *,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
   
    keys = _resolve_gemini_api_keys()
    if not keys:
        raise _no_key_error()

    parts = _build_gemini_parts(prompt, images)
    converted = _history_to_gemini(history) if history else None

    errors: list[str] = []
    for i, api_key in enumerate(keys):
        try:
            client, cfg = _gemini_client_and_config(api_key, system, temperature, max_tokens)
            if converted is not None:
                chat = client.chats.create(model=Config.GEMINI_MODEL, config=cfg, history=converted)
                response = chat.send_message(parts)
            else:
                response = client.models.generate_content(
                    model=Config.GEMINI_MODEL, contents=parts, config=cfg
                )
            return response.text or ""
        except Exception as e:  # noqa: BLE001
            errors.append(f"[key {i + 1}/{len(keys)}] {e}")

    raise RuntimeError("所有 Gemini API key 皆失敗：\n" + "\n".join(errors))


def call_llm_stream(
    prompt: str,
    *,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Iterator[str]:
    """Streaming variant — yields text chunks.

    Tries ``GEMINI_API_KEY``, then each key in ``GEMINI_API_KEYS`` in order.
    A key is only skipped in favor of the next if it fails before yielding
    any content; once a chunk has been streamed out, further errors just
    propagate (retrying would duplicate output already sent to the caller).
    """
    keys = _resolve_gemini_api_keys()
    if not keys:
        raise _no_key_error()

    parts = _build_gemini_parts(prompt, images)
    converted = _history_to_gemini(history) if history else None

    errors: list[str] = []
    for i, api_key in enumerate(keys):
        yielded_any = False
        try:
            client, cfg = _gemini_client_and_config(api_key, system, temperature, max_tokens)
            if converted is not None:
                chat = client.chats.create(model=Config.GEMINI_MODEL, config=cfg, history=converted)
                stream = chat.send_message_stream(parts)
            else:
                stream = client.models.generate_content_stream(
                    model=Config.GEMINI_MODEL, contents=parts, config=cfg
                )
            for chunk in stream:
                if chunk.text:
                    yielded_any = True
                    yield chunk.text
            return
        except Exception as e:  # noqa: BLE001
            if yielded_any:
                raise RuntimeError(f"Gemini 串流中途失敗（key {i + 1}/{len(keys)}）：{e}") from e
            errors.append(f"[key {i + 1}/{len(keys)}] {e}")

    raise RuntimeError("所有 Gemini API key 皆失敗：\n" + "\n".join(errors))
