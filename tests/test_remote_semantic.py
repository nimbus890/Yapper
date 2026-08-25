import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from aura_flow.remote_semantic import RemoteSemanticFormatter, request_completion


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self, limit):
        del limit
        return json.dumps(self.payload).encode("utf-8")


def _call(provider, base_url, model="model-a"):
    return request_completion(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key="secret",
        api_key_header="Authorization",
        api_key_prefix="Bearer",
        instruction="Format only.",
        text="um hello",
        timeout=2,
    )


class RemoteSemanticTests(unittest.TestCase):
    @patch(
        "aura_flow.remote_semantic.urlopen",
        return_value=_Response({"choices": [{"message": {"content": "Hello."}}]}),
    )
    def test_openai_compatible_chat_request(self, mocked):
        self.assertEqual(_call("OpenAI", "https://api.openai.com/v1"), "Hello.")
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
        body = json.loads(request.data)
        self.assertEqual(body["model"], "model-a")
        self.assertEqual(body["messages"][0]["role"], "system")

    @patch(
        "aura_flow.remote_semantic.urlopen",
        return_value=_Response({"content": [{"type": "text", "text": "Hello."}]}),
    )
    def test_anthropic_messages_request(self, mocked):
        self.assertEqual(_call("Anthropic", "https://api.anthropic.com/v1"), "Hello.")
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(request.headers["Anthropic-version"], "2023-06-01")

    @patch(
        "aura_flow.remote_semantic.urlopen",
        return_value=_Response(
            {"candidates": [{"content": {"parts": [{"text": "Hello."}]}}]}
        ),
    )
    def test_gemini_generate_content_request(self, mocked):
        self.assertEqual(
            _call(
                "Google Gemini",
                "https://generativelanguage.googleapis.com/v1beta",
                "models/gemini-flash",
            ),
            "Hello.",
        )
        request = mocked.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash:generateContent",
        )

    @patch(
        "aura_flow.remote_semantic.urlopen",
        return_value=_Response(
            {"message": {"content": [{"type": "text", "text": "Hello."}]}}
        ),
    )
    def test_cohere_v2_response(self, mocked):
        self.assertEqual(_call("Cohere", "https://api.cohere.com/v2"), "Hello.")
        self.assertEqual(mocked.call_args.args[0].full_url, "https://api.cohere.com/v2/chat")

    def test_remote_formatter_requires_an_active_complete_profile(self):
        config = SimpleNamespace(
            api_enabled=True,
            api_model="model-a",
            api_base_url="https://example.com/v1",
            api_provider="Custom",
            api_key_header="Authorization",
            api_key_prefix="Bearer",
            formatter_timeout_seconds=2,
        )
        self.assertTrue(RemoteSemanticFormatter(config, "secret").available)
        config.api_enabled = False
        self.assertFalse(RemoteSemanticFormatter(config, "secret").available)


if __name__ == "__main__":
    unittest.main()
