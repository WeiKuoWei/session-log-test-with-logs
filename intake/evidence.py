import anthropic

from .providers import RESPONSE_CASES, build_request

COMMON_HANDLING = (
    "Every case below produces one error record: status error, owner IT Service Desk, "
    "next_action retry-extraction, extraction null, error.code as listed, and "
    "error.retry_command. Other documents keep processing. A later successful attempt replaces "
    "the error; the earlier valid result stays in state/history and is linked from last_valid."
)


def build_evidence(settings, schema, document_id, message):
    return {
        "observation": (
            "built, not sent: this is the request the application constructs for the document; "
            "no API key was available in development, so no live provider response is recorded."
        ),
        "document_id": document_id,
        "endpoint": "POST https://api.anthropic.com/v1/messages (anthropic SDK messages.create)",
        "headers": {"x-api-key": "[redacted] (read from the ANTHROPIC_API_KEY environment variable)"},
        "client": {
            "sdk_version": anthropic.__version__,
            "timeout_seconds": settings.timeout_seconds,
            "sdk_max_retries": settings.max_retries,
            "note": "The SDK retries 429, 5xx, timeouts and connection errors with backoff "
                    "before the error below is raised.",
        },
        "temperature": "not sent: messages.create in this SDK version has no temperature parameter",
        "request": build_request(settings, schema, document_id, message),
        "success_handling": (
            "stop_reason tool_use with exactly one record_access_request input, valid against "
            "snapshot.schema.json, quotes, dates and request_id found in the message; then "
            "routing is applied in code."
        ),
        "error_handling": COMMON_HANDLING,
        "response_cases": [
            {"case": case, "error_code": code} for case, code in RESPONSE_CASES.items()
        ],
    }
