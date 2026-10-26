import json
import shutil
import threading
import time
from pathlib import Path

from intake.models import ProviderReply
from intake.settings import Paths

REPO = Path(__file__).resolve().parent.parent
MATERIALS = REPO / "materials" / "requests"
PARAPHRASE = REPO / "tests" / "fixtures" / "paraphrase"


def source_path(name):
    return MATERIALS / name if (MATERIALS / name).exists() else PARAPHRASE / name


def message_of(name):
    return json.loads(source_path(name).read_text(encoding="utf-8"))["message"]


def copy_request(inbox, name):
    shutil.copy(source_path(name), inbox / name)


def expected_entry(name):
    expected = json.loads(Paths().expected_file.read_text(encoding="utf-8"))
    return expected[name]


def extraction_for(name, **overrides):
    """A schema-valid extraction carrying the hand-written expected facts for `name`,
    with no quotes and no issues. Tests override whatever they exercise."""
    base = {
        **expected_entry(name)["fields"],
        "business_purpose": "stated purpose",
        "supporting_quotes": [],
        "issues": [],
    }
    base.update(overrides)
    return base


def tool_reply(extraction):
    return ProviderReply("tool_use", [extraction])


class ScriptedProvider:
    """Answers per document_id from a dict. A value may be a ProviderReply, an exception to
    raise, or a callable returning either. Records every call."""

    name = "mock"
    model = "mock"

    def __init__(self, replies, delay=0.0):
        self.replies = replies
        self.delay = delay
        self.calls = []
        self._lock = threading.Lock()

    def extract(self, document_id, message):
        with self._lock:
            self.calls.append(document_id)
        if self.delay:
            time.sleep(self.delay)
        reply = self.replies[document_id]
        if callable(reply):
            reply = reply()
        if isinstance(reply, BaseException):
            raise reply
        return reply


def all_good_replies(names):
    return {name: tool_reply(extraction_for(name)) for name in names}
