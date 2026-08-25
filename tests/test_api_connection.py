import json
import unittest
from unittest.mock import patch

from aura_flow.api_connection import (
    detect_provider_from_key,
    list_available_models,
    normalize_base_url,
    provider_preset,
)


class _Response:
    payload = {"data": [{"id": "model-z"}, {"id": "model-a"}]}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit):
        del limit
        return json.dumps(self.payload).encode()


class _GeminiResponse(_Response):
    payload = {"models": [{"name": "models/gemini-pro"}, {"name": "models/gemini-flash"}]}


class ApiConnectionTests(unittest.TestCase):
    def test_detects_common_provider_keys_without_network_calls(self):
        cases = {
            "sk-ant-test": "anthropic",
            "AIza-test": "gemini",
            "gsk_test": "groq",
            "sk-or-v1-test": "openrouter",
            "xai-test": "xai",
            "sk-proj-test": "openai",
        }
        for key, expected in cases.items():
            with self.subTest(key=key):
                preset, clean_key = detect_provider_from_key(key)
                self.assertEqual(preset.key, expected)
                self.assertEqual(clean_key, key)

    def test_explicit_provider_prefix_handles_ambiguous_keys(self):
        preset, clean_key = detect_provider_from_key("mistral:plain-random-key")
        self.assertEqual(preset.key, "mistral")
        self.assertEqual(clean_key, "plain-random-key")

    def test_registry_is_not_limited_to_openai(self):
        for name in ("anthropic", "gemini", "groq", "mistral", "cohere", "deepseek", "ollama"):
            self.assertIsNotNone(provider_preset(name))

    def test_normalizes_base_url(self):
        self.assertEqual(normalize_base_url("https://example.com/v1/"), "https://example.com/v1")

    def test_rejects_incomplete_url(self):
        with self.assertRaisesRegex(ValueError, "complete API base URL"):
            normalize_base_url("example.com/v1")

    def test_rejects_insecure_remote_url_but_allows_localhost(self):
        with self.assertRaisesRegex(ValueError, "require HTTPS"):
            normalize_base_url("http://example.com/v1")
        self.assertEqual(normalize_base_url("http://localhost:11434/v1"), "http://localhost:11434/v1")

    @patch("aura_flow.api_connection.urlopen", return_value=_Response())
    def test_discovers_and_sorts_models(self, mocked):
        models = list_available_models("https://example.com/v1", "secret")
        self.assertEqual(models, ["model-a", "model-z"])
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.com/v1/models")
        self.assertEqual(request.headers["Authorization"], "Bearer secret")

    @patch("aura_flow.api_connection.urlopen", return_value=_GeminiResponse())
    def test_custom_provider_schema_header_and_path(self, mocked):
        models = list_available_models(
            "https://generativelanguage.googleapis.com/v1beta",
            "secret",
            models_path="models",
            api_key_header="x-goog-api-key",
            api_key_prefix="",
        )
        self.assertEqual(models, ["models/gemini-flash", "models/gemini-pro"])
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "https://generativelanguage.googleapis.com/v1beta/models")
        self.assertEqual(request.headers["X-goog-api-key"], "secret")

    @patch("aura_flow.api_connection.urlopen", return_value=_Response())
    def test_local_provider_can_be_unauthenticated(self, mocked):
        list_available_models("http://localhost:11434/api", models_path="tags")
        request = mocked.call_args.args[0]
        self.assertNotIn("Authorization", request.headers)

    @patch("aura_flow.api_connection.urlopen", return_value=_Response())
    def test_provider_specific_headers_are_automatic(self, mocked):
        preset = provider_preset("anthropic")
        list_available_models(
            preset.base_url,
            "secret",
            api_key_header=preset.api_key_header,
            api_key_prefix=preset.api_key_prefix,
            provider=preset.name,
        )
        request = mocked.call_args.args[0]
        self.assertEqual(request.headers["X-api-key"], "secret")
        self.assertEqual(request.headers["Anthropic-version"], "2023-06-01")


if __name__ == "__main__":
    unittest.main()
