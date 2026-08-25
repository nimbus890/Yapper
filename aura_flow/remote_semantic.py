from __future__ import annotations

import json
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .api_connection import normalize_base_url, provider_preset
from .semantic import (
    SMART_INSTRUCTION,
    verify_not_truncated,
    verify_preserved_intent,
    verify_protected_literals,
)
from .version import VERSION


def _endpoint(base_url: str, suffix: str) -> str:
    return f"{normalize_base_url(base_url).rstrip('/')}/{suffix.lstrip('/')}"


def _provider_kind(provider: str) -> str:
    preset = provider_preset(provider)
    return preset.key if preset else "openai-compatible"


def _headers(provider: str, key: str, header_name: str, prefix: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": f"yapper/{VERSION}",
    }
    preset = provider_preset(provider)
    if preset:
        headers.update(dict(preset.extra_headers))
    if key.strip() and header_name.strip():
        headers[header_name.strip()] = f"{prefix.strip()} {key.strip()}".strip()
    return headers


def _request_shape(
    provider: str,
    base_url: str,
    model: str,
    instruction: str,
    text: str,
) -> tuple[str, dict[str, object]]:
    kind = _provider_kind(provider)
    user_text = f"INPUT:\n{text}\n\nOUTPUT:"
    if kind == "anthropic":
        return _endpoint(base_url, "messages"), {
            "model": model,
            "max_tokens": 1_024,
            "system": instruction,
            "messages": [{"role": "user", "content": user_text}],
        }
    if kind == "gemini":
        model_path = model if model.startswith("models/") else f"models/{model}"
        return _endpoint(base_url, f"{model_path}:generateContent"), {
            "systemInstruction": {"parts": [{"text": instruction}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 1_024},
        }
    messages = [
        {"role": "system", "content": instruction},
        {"role": "user", "content": user_text},
    ]
    if kind == "cohere":
        return _endpoint(base_url, "chat"), {
            "model": model,
            "messages": messages,
            "stream": False,
        }
    if kind == "ollama":
        return _endpoint(base_url, "chat"), {
            "model": model,
            "messages": messages,
            "stream": False,
        }
    return _endpoint(base_url, "chat/completions"), {
        "model": model,
        "messages": messages,
        "stream": False,
    }


def _content_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
    candidates = payload.get("candidates")
    if isinstance(candidates, list) and candidates and isinstance(candidates[0], dict):
        content = candidates[0].get("content")
        if isinstance(content, dict):
            parts = content.get("parts")
            if isinstance(parts, list):
                return "".join(
                    str(part.get("text", ""))
                    for part in parts
                    if isinstance(part, dict)
                ).strip()
    message = payload.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and part.get("type", "text") == "text"
            ).strip()
    content = payload.get("content")
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type", "text") == "text"
        ).strip()
    for key in ("output_text", "text", "response"):
        if isinstance(payload.get(key), str):
            return str(payload[key]).strip()
    return ""


def request_completion(
    *,
    provider: str,
    base_url: str,
    model: str,
    api_key: str,
    api_key_header: str,
    api_key_prefix: str,
    instruction: str,
    text: str,
    timeout: float,
) -> str:
    url, body = _request_shape(provider, base_url, model, instruction, text)
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers=_headers(provider, api_key, api_key_header, api_key_prefix),
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(4_000_000).decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise RuntimeError("The online formatter rejected the API credentials") from exc
        raise RuntimeError(f"Online formatting failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach the online formatter: {exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("The online formatter returned unreadable data") from exc
    result = _content_text(payload)
    if not result:
        raise RuntimeError("The online formatter returned no text")
    return result


class RemoteSemanticFormatter:
    """Provider-aware cloud formatter using the same safety guards as local Gemma."""

    def __init__(self, config, api_key: str):
        self.config = config
        self.api_key = api_key.strip()
        self.error = ""

    @property
    def available(self) -> bool:
        local_endpoint = self.config.api_base_url.casefold().startswith(
            ("http://localhost", "http://127.0.0.1")
        )
        return bool(
            self.config.api_enabled
            and self.config.api_model.strip()
            and self.config.api_base_url.strip()
            and (self.api_key or local_endpoint)
        )

    @property
    def ready(self) -> bool:
        return self.available

    @property
    def display_name(self) -> str:
        return f"{self.config.api_provider} · {self.config.api_model}"

    def load_async(self, callback: Callable[[str, bool], None]) -> None:
        if self.available:
            callback(f"Online formatter ready · {self.display_name}", True)
        else:
            callback("Online formatter is not completely configured", False)

    def format(
        self,
        text: str,
        category: str,
        cleanup_level: str = "smart",
        style: str = "default",
        original_text: str | None = None,
    ) -> str:
        del category, cleanup_level, style
        result = request_completion(
            provider=self.config.api_provider,
            base_url=self.config.api_base_url,
            model=self.config.api_model,
            api_key=self.api_key,
            api_key_header=self.config.api_key_header,
            api_key_prefix=self.config.api_key_prefix,
            instruction=SMART_INSTRUCTION,
            text=text,
            timeout=self.config.formatter_timeout_seconds,
        )
        result = verify_protected_literals(text, result)
        result = verify_not_truncated(text, result)
        result = verify_preserved_intent(original_text or text, result)
        if text.rstrip().endswith((".", "!", "?")) and not result.endswith((".", "!", "?")):
            result += text.rstrip()[-1]
        return result
