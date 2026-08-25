from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .version import VERSION


OPENAI_BASE_URL = "https://api.openai.com/v1"
HEADER_NAME = re.compile(r"^[A-Za-z0-9-]+$")


@dataclass(frozen=True, slots=True)
class ProviderPreset:
    key: str
    name: str
    base_url: str
    models_path: str = "/models"
    api_key_header: str = "Authorization"
    api_key_prefix: str = "Bearer"
    extra_headers: tuple[tuple[str, str], ...] = ()


PROVIDER_PRESETS = (
    ProviderPreset("openai", "OpenAI", OPENAI_BASE_URL),
    ProviderPreset(
        "anthropic",
        "Anthropic",
        "https://api.anthropic.com/v1",
        api_key_header="x-api-key",
        api_key_prefix="",
        extra_headers=(("anthropic-version", "2023-06-01"),),
    ),
    ProviderPreset("gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta", api_key_header="x-goog-api-key", api_key_prefix=""),
    ProviderPreset("groq", "Groq", "https://api.groq.com/openai/v1"),
    ProviderPreset("openrouter", "OpenRouter", "https://openrouter.ai/api/v1"),
    ProviderPreset("mistral", "Mistral", "https://api.mistral.ai/v1"),
    ProviderPreset("cohere", "Cohere", "https://api.cohere.com/v2"),
    ProviderPreset("xai", "xAI", "https://api.x.ai/v1"),
    ProviderPreset("perplexity", "Perplexity", "https://api.perplexity.ai"),
    ProviderPreset("together", "Together AI", "https://api.together.xyz/v1"),
    ProviderPreset("deepseek", "DeepSeek", "https://api.deepseek.com/v1"),
    ProviderPreset("ollama", "Ollama (local)", "http://localhost:11434/api", models_path="/tags", api_key_header="", api_key_prefix=""),
)
_PRESETS_BY_KEY = {preset.key: preset for preset in PROVIDER_PRESETS}


def provider_preset(key: str) -> ProviderPreset | None:
    normalized = key.strip().casefold()
    return _PRESETS_BY_KEY.get(normalized) or next(
        (preset for preset in PROVIDER_PRESETS if preset.name.casefold() == normalized),
        None,
    )


def detect_provider_from_key(api_key: str) -> tuple[ProviderPreset | None, str]:
    """Identify common providers without sending the credential anywhere.

    Ambiguous providers can be specified as ``provider:key`` in the same key
    field, for example ``mistral:...`` or selected in the manual panel.
    """

    value = api_key.strip()
    if ":" in value:
        prefix, candidate = value.split(":", 1)
        explicit = provider_preset(prefix)
        if explicit and candidate.strip():
            return explicit, candidate.strip()
    lower = value.casefold()
    prefix_map = (
        ("sk-ant-", "anthropic"),
        ("sk-or-v1-", "openrouter"),
        ("gsk_", "groq"),
        ("aiza", "gemini"),
        ("xai-", "xai"),
        ("pplx-", "perplexity"),
        ("sk-proj-", "openai"),
        ("sk-svcacct-", "openai"),
        ("sk-", "openai"),
    )
    for prefix, preset_key in prefix_map:
        if lower.startswith(prefix):
            return provider_preset(preset_key), value
    return None, value


def normalize_base_url(value: str) -> str:
    base = value.strip().rstrip("/")
    if not base.startswith(("https://", "http://")):
        raise ValueError("Enter a complete API base URL beginning with https://")
    parsed = urlparse(base)
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("API keys require HTTPS except for a local endpoint")
    return base


def _models_url(base_url: str, models_path: str) -> str:
    path = models_path.strip() or "/models"
    if path.startswith(("https://", "http://")):
        return normalize_base_url(path)
    base = normalize_base_url(base_url) + "/"
    return urljoin(base, path.lstrip("/"))


def _model_ids(payload: object) -> list[str]:
    """Read common OpenAI, Anthropic, Gemini, Ollama, and array responses."""

    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        candidates = payload.get("data") or payload.get("models") or payload.get("results") or []
    else:
        candidates = []

    values: set[str] = set()
    for item in candidates if isinstance(candidates, list) else []:
        if isinstance(item, str):
            value = item.strip()
        elif isinstance(item, dict):
            value = str(
                item.get("id")
                or item.get("name")
                or item.get("model")
                or item.get("model_id")
                or ""
            ).strip()
        else:
            value = ""
        if value:
            values.add(value)
    return sorted(values, key=str.casefold)


def list_available_models(
    base_url: str,
    api_key: str = "",
    timeout: float = 10.0,
    *,
    models_path: str = "/models",
    api_key_header: str = "Authorization",
    api_key_prefix: str = "Bearer",
    provider: str = "",
) -> list[str]:
    """Discover models from a configurable provider endpoint.

    Providers that do not expose a model-list endpoint can still be configured
    in the UI by entering a model identifier manually.
    """

    headers = {
        "Accept": "application/json",
        "User-Agent": f"yapper/{VERSION}",
    }
    preset = provider_preset(provider)
    if preset:
        headers.update(dict(preset.extra_headers))
    key = api_key.strip()
    header_name = api_key_header.strip()
    if key:
        if not header_name or not HEADER_NAME.fullmatch(header_name):
            raise ValueError("Enter a valid API key header name")
        prefix = api_key_prefix.strip()
        headers[header_name] = f"{prefix} {key}".strip()

    request = Request(
        _models_url(base_url, models_path),
        method="GET",
        headers=headers,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(2_000_000).decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise RuntimeError("The API credentials were rejected") from exc
        raise RuntimeError(f"Model discovery failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach the API: {exc.reason}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("The API returned an unreadable model list") from exc
    models = _model_ids(payload)
    if not models:
        raise RuntimeError("No model IDs were found; enter the model manually")
    return models
