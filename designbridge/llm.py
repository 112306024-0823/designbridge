"""Unified LLM client for DesignBridge.

``call_llm`` / ``call_llm_stream`` use ``GEMINI_API_KEY`` via the Google
Generative AI SDK (direct). ``RuntimeError`` is raised on failure.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Iterator

from designbridge.config import Config


# ── Shared helpers ───────────────────────────────────────────────────────────

def _image_to_content_block(image: str | bytes | Path) -> dict:
    """Convert a local path, URL, or raw bytes to an OpenAI-style image content block."""
    if isinstance(image, str) and image.startswith(("http://", "https://")):
        return {"type": "image_url", "image_url": {"url": image}}
    if isinstance(image, bytes):
        b64 = base64.b64encode(image).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
    path = Path(image)
    suffix = path.suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".webp": "image/webp", ".gif": "image/gif"}
    mime = mime_map.get(suffix, "image/jpeg")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def build_messages(
    prompt: str,
    *,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
) -> list[dict]:
    """Build an OpenAI-style messages list from prompt + optional images/history."""
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    if history:
        messages.extend(history)
    if images:
        content: list[dict] = [_image_to_content_block(img) for img in images]
        content.append({"type": "text", "text": prompt})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})
    return messages


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


# ── Gemini multi-key rotation ────────────────────────────────────────────────
# Shared by every Gemini call site in this project (main app + offline style_kb
# caption scripts). Advances past a key only on quota/rate-limit errors, and the
# index is process-global so a dead key stays skipped for the rest of the run.

_gemini_key_idx = 0


def _is_gemini_quota_error(e: Exception) -> bool:
    msg = str(e).lower()
    return ("429" in msg or "quota" in msg or "resourceexhausted" in type(e).__name__.lower()
            or "rate_limit" in msg or "ratelimit" in msg)


def call_with_gemini_key_rotation(fn):
    """Call ``fn(api_key)``, trying each configured Gemini key in order until one
    doesn't hit a quota error. Raises RuntimeError if none work."""
    global _gemini_key_idx
    keys = Config.get_gemini_api_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY 未設定。請在 .env 中設定 GEMINI_API_KEY 或 GEMINI_API_KEYS。")

    last_err: Exception | None = None
    while _gemini_key_idx < len(keys):
        try:
            return fn(keys[_gemini_key_idx])
        except Exception as e:
            if not _is_gemini_quota_error(e):
                raise
            print(f"[llm] Gemini key #{_gemini_key_idx + 1}/{len(keys)} quota 已滿，切換下一個...")
            last_err = e
            _gemini_key_idx += 1
    raise RuntimeError(f"所有 {len(keys)} 個 Gemini API key 均已達 quota 上限") from last_err


# ── Gemini direct path ───────────────────────────────────────────────────────

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


def _call_via_gemini(
    prompt: str,
    *,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai 未安裝。請先執行: pip install google-genai") from exc

    cfg = types.GenerateContentConfig(
        temperature=temperature if temperature is not None else Config.GEMINI_TEMPERATURE,
        **({"max_output_tokens": max_tokens} if max_tokens is not None else {}),
        **({"system_instruction": system} if system else {}),
    )
    parts = _build_gemini_parts(prompt, images)

    def _do(api_key: str) -> str:
        client = genai.Client(api_key=api_key)
        if history:
            converted = _history_to_gemini(history)
            chat = client.chats.create(model=Config.GEMINI_MODEL, config=cfg, history=converted)
            response = chat.send_message(parts)
        else:
            response = client.models.generate_content(
                model=Config.GEMINI_MODEL, contents=parts, config=cfg
            )
        return response.text or ""

    return call_with_gemini_key_rotation(_do)


def _stream_via_gemini(
    prompt: str,
    *,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Iterator[str]:
    global _gemini_key_idx
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai 未安裝。請先執行: pip install google-genai") from exc

    keys = Config.get_gemini_api_keys()
    if not keys:
        raise RuntimeError("GEMINI_API_KEY 未設定。請在 .env 中設定 GEMINI_API_KEY 或 GEMINI_API_KEYS。")

    cfg = types.GenerateContentConfig(
        temperature=temperature if temperature is not None else Config.GEMINI_TEMPERATURE,
        **({"max_output_tokens": max_tokens} if max_tokens is not None else {}),
        **({"system_instruction": system} if system else {}),
    )
    parts = _build_gemini_parts(prompt, images)

    last_err: Exception | None = None
    while _gemini_key_idx < len(keys):
        client = genai.Client(api_key=keys[_gemini_key_idx])
        yielded = False
        try:
            if history:
                converted = _history_to_gemini(history)
                chat = client.chats.create(model=Config.GEMINI_MODEL, config=cfg, history=converted)
                stream = chat.send_message_stream(parts)
            else:
                stream = client.models.generate_content_stream(
                    model=Config.GEMINI_MODEL, contents=parts, config=cfg
                )
            for chunk in stream:
                if chunk.text:
                    yielded = True
                    yield chunk.text
            return
        except Exception as e:
            # Once a chunk has already been yielded, the response is mid-flight —
            # switching keys now would silently drop/duplicate content, so just raise.
            if yielded or not _is_gemini_quota_error(e):
                raise
            print(f"[llm] Gemini key #{_gemini_key_idx + 1}/{len(keys)} quota 已滿，切換下一個...")
            last_err = e
            _gemini_key_idx += 1
    raise RuntimeError(f"所有 {len(keys)} 個 Gemini API key 均已達 quota 上限") from last_err


# ── Public API ───────────────────────────────────────────────────────────────

def call_llm(
    prompt: str,
    *,
    model: str | None = None,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Call the LLM (Gemini) and return the response text."""
    if not Config.get_gemini_api_keys():
        raise RuntimeError("GEMINI_API_KEY 未設定。請在 .env 中設定 GEMINI_API_KEY 或 GEMINI_API_KEYS。")

    return _call_via_gemini(
        prompt,
        images=images,
        system=system,
        history=history,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def call_llm_stream(
    prompt: str,
    *,
    model: str | None = None,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Iterator[str]:
    """Streaming variant of ``call_llm`` — yields text chunks."""
    if not Config.get_gemini_api_keys():
        raise RuntimeError("GEMINI_API_KEY 未設定。請在 .env 中設定 GEMINI_API_KEY 或 GEMINI_API_KEYS。")

    yield from _stream_via_gemini(
        prompt,
        images=images,
        system=system,
        history=history,
        temperature=temperature,
        max_tokens=max_tokens,
    )
