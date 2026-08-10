"""Unified LLM client for DesignBridge.

Fallback chain for ``call_llm`` / ``call_llm_stream`` (each step is skipped if
the corresponding key is not set; on failure, the next step is tried):

  1. ``GEMINI_API_KEY`` → Google Generative AI SDK (direct)
  2. ``GROK_API_KEY`` / ``XAI_API_KEY`` → xAI Grok OpenAI-compatible API

If all configured backends fail, ``RuntimeError`` is raised with every error.
"""

from __future__ import annotations

import base64
import os
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

    api_key = Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 未設定。請在 .env 中設定 GEMINI_API_KEY。")

    client = genai.Client(api_key=api_key)
    cfg = types.GenerateContentConfig(
        temperature=temperature if temperature is not None else Config.GEMINI_TEMPERATURE,
        **({"max_output_tokens": max_tokens} if max_tokens is not None else {}),
        **({"system_instruction": system} if system else {}),
    )
    parts = _build_gemini_parts(prompt, images)

    if history:
        converted = _history_to_gemini(history)
        chat = client.chats.create(model=Config.GEMINI_MODEL, config=cfg, history=converted)
        response = chat.send_message(parts)
    else:
        response = client.models.generate_content(
            model=Config.GEMINI_MODEL, contents=parts, config=cfg
        )

    return response.text or ""


def _stream_via_gemini(
    prompt: str,
    *,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Iterator[str]:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise RuntimeError("google-genai 未安裝。請先執行: pip install google-genai") from exc

    api_key = Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 未設定。請在 .env 中設定 GEMINI_API_KEY。")

    client = genai.Client(api_key=api_key)
    cfg = types.GenerateContentConfig(
        temperature=temperature if temperature is not None else Config.GEMINI_TEMPERATURE,
        **({"max_output_tokens": max_tokens} if max_tokens is not None else {}),
        **({"system_instruction": system} if system else {}),
    )
    parts = _build_gemini_parts(prompt, images)

    if history:
        converted = _history_to_gemini(history)
        chat = client.chats.create(model=Config.GEMINI_MODEL, config=cfg, history=converted)
        for chunk in chat.send_message_stream(parts):
            if chunk.text:
                yield chunk.text
    else:
        for chunk in client.models.generate_content_stream(
            model=Config.GEMINI_MODEL, contents=parts, config=cfg
        ):
            if chunk.text:
                yield chunk.text


# ── Grok direct path ─────────────────────────────────────────────────────────

def _grok_model_for_fallback(model: str | None) -> str:
    """Use a plain Grok model id for the direct xAI OpenAI-compatible client."""
    raw = (model or Config.XAI_MODEL).strip()
    if raw.lower().startswith("xai/"):
        return raw.split("/", 1)[1]
    return raw


def _call_via_grok(
    prompt: str,
    *,
    model: str | None = None,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai 未安裝。請先執行: pip install openai") from exc

    api_key = Config.get_xai_api_key()
    if not api_key:
        raise RuntimeError("GROK_API_KEY / XAI_API_KEY 未設定。")

    client = OpenAI(api_key=api_key, base_url=Config.XAI_BASE_URL)
    completion_kwargs: dict[str, Any] = {
        "model": _grok_model_for_fallback(model),
        "messages": build_messages(prompt, images=images, system=system, history=history),
        "temperature": temperature if temperature is not None else Config.GEMINI_TEMPERATURE,
    }
    if max_tokens is not None:
        completion_kwargs["max_tokens"] = max_tokens

    response = client.chat.completions.create(**completion_kwargs)
    return response.choices[0].message.content or ""


def _stream_via_grok(
    prompt: str,
    *,
    model: str | None = None,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Iterator[str]:
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError("openai 未安裝。請先執行: pip install openai") from exc

    api_key = Config.get_xai_api_key()
    if not api_key:
        raise RuntimeError("GROK_API_KEY / XAI_API_KEY 未設定。")

    client = OpenAI(api_key=api_key, base_url=Config.XAI_BASE_URL)
    completion_kwargs: dict[str, Any] = {
        "model": _grok_model_for_fallback(model),
        "messages": build_messages(prompt, images=images, system=system, history=history),
        "temperature": temperature if temperature is not None else Config.GEMINI_TEMPERATURE,
        "stream": True,
    }
    if max_tokens is not None:
        completion_kwargs["max_tokens"] = max_tokens

    for chunk in client.chat.completions.create(**completion_kwargs):
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


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
    """Call an LLM and return the response text.

    Tries Gemini → Grok in order; see module docstring.
    """
    errors: list[str] = []

    has_gemini = bool(Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY"))
    has_xai = bool(Config.get_xai_api_key())

    if not (has_gemini or has_xai):
        raise RuntimeError(
            "未設定任何 LLM API key。請在 .env 至少設定其一："
            "GEMINI_API_KEY、或 GROK_API_KEY。"
        )

    if has_gemini:
        try:
            return _call_via_gemini(
                prompt,
                images=images,
                system=system,
                history=history,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"[1] Gemini ({Config.GEMINI_MODEL}): {e}")

    if has_xai:
        grok_model = _grok_model_for_fallback(model)
        try:
            return _call_via_grok(
                prompt,
                model=grok_model,
                images=images,
                system=system,
                history=history,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception as e:  # noqa: BLE001
            errors.append(f"[2] Grok ({grok_model}): {e}")

    raise RuntimeError(
        "所有已設定的 LLM 後端皆失敗（順序：Gemini → Grok）。\n"
        + "\n".join(errors)
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
    """Streaming variant — yields text chunks; same fallback order as ``call_llm``."""
    errors: list[str] = []

    has_gemini = bool(Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY"))
    has_xai = bool(Config.get_xai_api_key())

    if not (has_gemini or has_xai):
        raise RuntimeError(
            "未設定任何 LLM API key。請在 .env 至少設定其一："
            "GEMINI_API_KEY、或 GROK_API_KEY。"
        )

    if has_gemini:
        try:
            yield from _stream_via_gemini(
                prompt,
                images=images,
                system=system,
                history=history,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return
        except Exception as e:  # noqa: BLE001
            errors.append(f"[1] Gemini ({Config.GEMINI_MODEL}): {e}")

    if has_xai:
        grok_model = _grok_model_for_fallback(model)
        try:
            yield from _stream_via_grok(
                prompt,
                model=grok_model,
                images=images,
                system=system,
                history=history,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return
        except Exception as e:  # noqa: BLE001
            errors.append(f"[2] Grok ({grok_model}): {e}")

    raise RuntimeError(
        "所有已設定的 LLM 串流後端皆失敗（順序：Gemini → Grok）。\n"
        + "\n".join(errors)
    )
