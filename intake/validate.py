import re
from datetime import date

from jsonschema.validators import validator_for

from .models import ExtractionError

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATE_FIELDS = ("request_date", "start_date", "end_date")


def validate_reply(reply, message, schema):
    """Return the extraction dict, or raise ExtractionError. Checks run in this order:
    completion status, one tool call, schema, then grounding in the message text."""
    if reply.stop_reason == "refusal":
        raise ExtractionError("refusal", "The model refused to answer this message.")
    if reply.stop_reason == "max_tokens":
        raise ExtractionError("truncated", "The reply was cut off at the token limit.")
    if reply.stop_reason != "tool_use":
        raise ExtractionError("unexpected-stop", f"Unexpected stop reason: {reply.stop_reason!r}.")
    if len(reply.tool_inputs) != 1:
        raise ExtractionError(
            "malformed", f"Expected exactly one tool call, got {len(reply.tool_inputs)}."
        )
    extraction = reply.tool_inputs[0]
    _check_schema(extraction, schema)
    _check_grounding(extraction, message)
    return extraction


def _check_schema(extraction, schema):
    validator = validator_for(schema)(schema)
    problems = sorted(validator.iter_errors(extraction), key=lambda e: list(e.path))
    if problems:
        shown = "; ".join(
            f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}" for e in problems[:3]
        )
        raise ExtractionError("schema-invalid", f"Reply does not match the schema: {shown}")


def _check_grounding(extraction, message):
    for quote in extraction["supporting_quotes"]:
        if quote not in message:
            raise ExtractionError("ungrounded-quote", f"Quote is not in the message: {quote!r}")
    for name in DATE_FIELDS:
        value = extraction[name]
        if value is None:
            continue
        if not _is_real_iso_date(value):
            raise ExtractionError("ungrounded-date", f"{name} is not a YYYY-MM-DD date: {value!r}")
        if value not in message:
            raise ExtractionError("ungrounded-date", f"{name} {value!r} does not appear in the message.")
    request_id = extraction["request_id"]
    if request_id is not None and request_id not in message:
        raise ExtractionError(
            "ungrounded-request-id", f"request_id {request_id!r} does not appear in the message."
        )


def _is_real_iso_date(value):
    if not ISO_DATE.match(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True
