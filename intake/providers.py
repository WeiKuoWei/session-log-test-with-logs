import json
import os

import anthropic

from .models import ExtractionError, ProviderReply
from .prompt import SYSTEM_PROMPT, TOOL_CHOICE, TOOL_NAME, tool_definition, user_content
from .redact import redact

# Every way a response can go wrong, and the error code the record carries. One list feeds
# request-evidence.json and the tests, so the document cannot drift from the behaviour.
RESPONSE_CASES = {
    "stop_reason refusal": "refusal",
    "stop_reason max_tokens": "truncated",
    "any other stop_reason": "unexpected-stop",
    "no tool call": "malformed",
    "two tool calls": "malformed",
    "tool input does not match the schema": "schema-invalid",
    "quote not found in the message": "ungrounded-quote",
    "request timed out": "timeout",
    "HTTP 429": "rate-limited",
    "HTTP 5xx": "provider-unavailable",
    "other HTTP 4xx": "provider-rejected",
    "connection failed": "connection-error",
}


def build_request(settings, schema, document_id, message):
    """The exact keyword arguments sent to messages.create. No temperature: the installed
    SDK's messages.create has no such parameter."""
    return {
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "system": SYSTEM_PROMPT,
        "tools": [tool_definition(schema)],
        "tool_choice": TOOL_CHOICE,
        "messages": [{"role": "user", "content": user_content(document_id, message)}],
    }


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings, schema, client):
        self.settings = settings
        self.schema = schema
        self.model = settings.model
        self._client = client

    def extract(self, document_id, message):
        request = build_request(self.settings, self.schema, document_id, message)
        try:
            response = self._client.messages.create(**request)
        except anthropic.APITimeoutError:
            raise ExtractionError(
                "timeout", f"No reply within {self.settings.timeout_seconds} seconds.")
        except anthropic.APIConnectionError as exc:
            raise ExtractionError("connection-error", redact(f"Could not reach the API: {exc}"))
        except anthropic.APIStatusError as exc:
            raise _status_error(exc)
        tool_inputs = [
            block.input for block in response.content
            if block.type == "tool_use" and block.name == TOOL_NAME
        ]
        return ProviderReply(response.stop_reason, tool_inputs)


def _status_error(exc):
    status = exc.status_code
    text = redact(f"HTTP {status}: {exc.message}")
    if status == 429:
        return ExtractionError("rate-limited", text)
    if status >= 500:
        return ExtractionError("provider-unavailable", text)
    return ExtractionError("provider-rejected", text)


class MockProvider:
    """Replays a canned reply per document from mock_replies/<document_id>. No network, no key."""

    name = "mock"
    model = "mock"

    def __init__(self, replies_dir):
        self.replies_dir = replies_dir

    def extract(self, document_id, message):
        path = self.replies_dir / document_id
        if not path.exists():
            raise ExtractionError("provider-error", f"No canned mock reply for {document_id}.")
        canned = json.loads(path.read_text(encoding="utf-8"))
        return ProviderReply(canned["stop_reason"], canned["tool_inputs"])


def make_provider(settings, paths, schema):
    """Build the provider, failing before any document is touched if it cannot work."""
    if settings.provider == "mock":
        return MockProvider(paths.mock_replies_dir)
    if settings.provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise SystemExit("ANTHROPIC_API_KEY is not set. Export it, or run with --provider mock.")
        client = anthropic.Anthropic(
            api_key=key, timeout=settings.timeout_seconds, max_retries=settings.max_retries)
        return AnthropicProvider(settings, schema, client)
    raise SystemExit(f"Unknown provider {settings.provider!r}; use anthropic or mock.")
