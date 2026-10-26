import json

from .models import ExtractionError, ProviderReply


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


def make_provider(settings, paths):
    if settings.provider == "mock":
        return MockProvider(paths.mock_replies_dir)
    raise SystemExit(f"Provider {settings.provider!r} is not available yet; use --provider mock.")
