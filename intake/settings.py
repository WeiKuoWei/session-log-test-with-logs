import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .prompt import SYSTEM_PROMPT, TOOL_CHOICE, TOOL_NAME
from .routing import ROUTING_REVISION

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "snapshot.schema.json"
CONFIG_PATH = ROOT / "config" / "settings.json"


@dataclass(frozen=True)
class Paths:
    """Every location the application reads or writes, resolved from one root."""

    root: Path = ROOT

    @property
    def input_dir(self):
        return self.root / "materials" / "requests"

    @property
    def state_dir(self):
        return self.root / "state"

    @property
    def deliverables_dir(self):
        return self.root / "deliverables"

    @property
    def policy_file(self):
        return self.root / "materials" / "office-policy.md"

    @property
    def mock_replies_dir(self):
        return self.root / "mock_replies"

    @property
    def expected_file(self):
        return self.root / "expected" / "expected_fields.json"


@dataclass(frozen=True)
class Settings:
    provider: str
    model: str
    max_tokens: int
    workers: int
    timeout_seconds: float
    max_retries: int


def load_settings(path=CONFIG_PATH):
    return Settings(**json.loads(Path(path).read_text(encoding="utf-8")))


def load_schema(path=SCHEMA_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def settings_fingerprint(settings, schema):
    """Hash of everything that changes what the model is asked or how it answers.

    Workers, timeout and retries are left out (they do not change results); the
    policy version is left out because routing is code and is re-run without the model.
    """
    payload = {
        "provider": settings.provider,
        "model": settings.model,
        "max_tokens": settings.max_tokens,
        "prompt": SYSTEM_PROMPT,
        "tool": TOOL_NAME,
        "tool_choice": TOOL_CHOICE,
        "schema": schema,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def policy_version(paths):
    """Identify the routing policy: the rules-revision constant plus a hash of the policy text.
    Editing either one makes stored routes stale, and `run` re-routes them without the model."""
    digest = hashlib.sha256(paths.policy_file.read_bytes()).hexdigest()
    return f"rules-{ROUTING_REVISION}+policy-{digest[:12]}"
