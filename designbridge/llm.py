"""Unified LLM client for DesignBridge, backed by LiteLLM.
用litellm的接口

"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from designbridge.config import Config


def _image_to_content_block(image: str | bytes | Path) -> dict:
    """Convert a local path, URL, or raw bytes to an OpenAI-style image content block."""
    # HTTP/HTTPS URL → pass directly
    if isinstance(image, str) and image.startswith(("http://", "https://")):
        return {"type": "image_url", "image_url": {"url": image}}

    # Raw bytes
    if isinstance(image, bytes):
        b64 = base64.b64encode(image).decode("ascii")
        return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}

    # Local file path
    path = Path(image)
    suffix = path.suffix.lower()
    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
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


def call_llm(
    prompt: str,
    *,
    model: str | None = None,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs: Any,
) -> str:
    """Call any LLM via LiteLLM and return the response text.

    Args:
        prompt:      User message text.
        model:       LiteLLM model string, e.g. "gemini/gemini-1.5-flash",
                     "gpt-4o", "claude-3-5-sonnet-20241022".
                     Defaults to Config.LITELLM_MODEL.
        images:      Optional list of local paths, HTTP URLs, or raw bytes.
        system:      Optional system prompt.
        history:     Optional prior conversation turns (OpenAI message dicts).
        temperature: Sampling temperature. Defaults to Config.GEMINI_TEMPERATURE.
        max_tokens:  Max output tokens.
        **kwargs:    Extra params forwarded to litellm.completion().

    Returns:
        The assistant's response as a plain string.
    """
    try:
        import litellm
    except ImportError as exc:
        raise RuntimeError(
            "litellm 未安裝。請先執行: pip install litellm"
        ) from exc

    resolved_model = model or Config.LITELLM_MODEL
    resolved_temp = temperature if temperature is not None else Config.GEMINI_TEMPERATURE

    messages = build_messages(prompt, images=images, system=system, history=history)

    completion_kwargs: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "temperature": resolved_temp,
        **kwargs,
    }
    if max_tokens is not None:
        completion_kwargs["max_tokens"] = max_tokens

    # Inject API keys from env so LiteLLM picks them up automatically
    _inject_api_keys(resolved_model)

    response = litellm.completion(**completion_kwargs)
    return response.choices[0].message.content or ""


def call_llm_stream(
    prompt: str,
    *,
    model: str | None = None,
    images: list[str | bytes | Path] | None = None,
    system: str | None = None,
    history: list[dict] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs: Any,
):
    """Streaming variant — yields text chunks as they arrive."""
    try:
        import litellm
    except ImportError as exc:
        raise RuntimeError("litellm 未安裝。請先執行: pip install litellm") from exc

    resolved_model = model or Config.LITELLM_MODEL
    resolved_temp = temperature if temperature is not None else Config.GEMINI_TEMPERATURE

    messages = build_messages(prompt, images=images, system=system, history=history)
    _inject_api_keys(resolved_model)

    completion_kwargs: dict[str, Any] = {
        "model": resolved_model,
        "messages": messages,
        "temperature": resolved_temp,
        "stream": True,
        **kwargs,
    }
    if max_tokens is not None:
        completion_kwargs["max_tokens"] = max_tokens

    for chunk in litellm.completion(**completion_kwargs):
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def _inject_api_keys(model: str) -> None:
    """Set LiteLLM API key / base URL based on env and provider."""
    import os
    import litellm

    # LiteLLM proxy key takes precedence over all provider-specific keys
    proxy_key = os.getenv("LITELLM_API_KEY", "")
    proxy_base = os.getenv("LITELLM_API_BASE", "")
    if proxy_key:
        litellm.api_key = proxy_key
        os.environ["LITELLM_API_KEY"] = proxy_key
    if proxy_base:
        litellm.api_base = proxy_base
        os.environ["LITELLM_API_BASE"] = proxy_base

    # Provider-specific keys (only applied when no proxy is configured)
    if not proxy_key:
        model_lower = model.lower()
        if model_lower.startswith("gemini/") or model_lower.startswith("google/"):
            key = Config.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
            if key:
                os.environ.setdefault("GEMINI_API_KEY", key)
        elif model_lower.startswith("gpt") or model_lower.startswith("openai/"):
            key = os.getenv("OPENAI_API_KEY", "")
            if key:
                os.environ.setdefault("OPENAI_API_KEY", key)
        elif model_lower.startswith("claude") or model_lower.startswith("anthropic/"):
            key = os.getenv("ANTHROPIC_API_KEY", "")
            if key:
                os.environ.setdefault("ANTHROPIC_API_KEY", key)
