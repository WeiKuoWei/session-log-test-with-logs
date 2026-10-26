"""The five routing rules of the office policy, applied in plain code.

The model only extracts. Nothing here reads a model-chosen status, owner or action.
"""

import re
from dataclasses import dataclass
from datetime import date

SERVICE_DESK = "IT Service Desk"
SECURITY = "Security Review"
SYSTEM_OWNER = "System Owner"

REQUIRED_FACTS = (
    "request_id", "request_date", "requester", "team", "system", "environment",
    "permission", "business_purpose", "start_date", "end_date", "manager",
)

OVERRIDE_PATTERNS = [re.compile(p) for p in (
    r"system override",
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|directions)",
    r"disregard (all |any |the )?(previous|prior|above|earlier) ",
    r"bypass (the |all )?(approval|review|security)",
    r"highest[- ]priority (system )?instruction",
    r"(mark|set|record) (this |the )?request as approved",
    r"(display|reveal|print|show|output|expose) (me )?(the |your )?(api[ -]?key|password|secret|credential)",
    r"grant (me )?(admin|root) access immediately",
)]


@dataclass(frozen=True)
class Route:
    owner: str
    status: str
    next_action: str
    signals: tuple  # which checks fired, e.g. "instruction-override:pattern-scan"


def route(extraction, document_id, message):
    signals = _override_signals(extraction, message)
    if signals:
        return Route(SERVICE_DESK, "review", "inspect-message", signals)

    if (extraction["kind"] == "withdrawal"
            and extraction["request_id"] and extraction["request_date"]):
        return Route(SERVICE_DESK, "review", "confirm-withdrawal", ())

    signals = _clarification_signals(extraction, document_id)
    if signals:
        return Route(SERVICE_DESK, "needs-information", "clarify", signals)

    if extraction["environment"] == "production" or extraction["permission"] in ("write", "admin"):
        return Route(SECURITY, "review", "review-risk-then-owner", ())
    return Route(SYSTEM_OWNER, "review", "review-request", ())


def _has_issue_prefix(extraction, prefix):
    return any(issue.strip().lower().startswith(prefix) for issue in extraction["issues"])


def _override_signals(extraction, message):
    signals = []
    text = " ".join(message.lower().split())
    if any(pattern.search(text) for pattern in OVERRIDE_PATTERNS):
        signals.append("instruction-override:pattern-scan")
    if _has_issue_prefix(extraction, "instruction-override:"):
        signals.append("instruction-override:model-issue")
    return tuple(signals)


def _clarification_signals(extraction, document_id):
    signals = []
    kind = extraction["kind"]
    if kind is None:
        signals.append("kind:null")
    elif kind == "other":
        signals.append("kind:other")

    if _has_issue_prefix(extraction, "conflict:"):
        signals.append("conflict:model-issue")

    stem = document_id.removesuffix(".json")
    request_id = extraction["request_id"]
    if request_id and request_id.strip() != stem:
        signals.append("id-mismatch")

    if kind in ("new", "change"):
        required = REQUIRED_FACTS
    elif kind == "withdrawal":
        required = ("request_id", "request_date")
    else:
        required = ()
    signals += [f"missing:{name}" for name in required if not _present(extraction[name])]

    if _start_after_end(extraction["start_date"], extraction["end_date"]):
        signals.append("start-after-end")
    return tuple(signals)


def _present(value):
    return value is not None and str(value).strip() != ""


def _start_after_end(start, end):
    try:
        return bool(start and end) and date.fromisoformat(start) > date.fromisoformat(end)
    except ValueError:
        return False
