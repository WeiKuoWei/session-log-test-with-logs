"""The Anthropic provider, driven by a fake client. No network, no real key."""

import json

import anthropic
import httpx2
import pytest
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from helpers import expected_entry, message_of
from intake.cli import main
from intake.models import ProviderReply
from intake.prompt import TOOL_NAME
from intake.providers import RESPONSE_CASES, AnthropicProvider, make_provider
from intake.runner import input_files, run_intake
from intake.settings import load_settings

KEY = "sk-ant-secret-key-1"
REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
DOC = "IT-001.json"
QUOTE = "request IT-001 dated 2026-10-22"


def good_input(**overrides):
    return {**expected_entry(DOC)["fields"], "business_purpose": "checking the weekly conversion dashboard",
            "supporting_quotes": [QUOTE], "issues": [], **overrides}


def tool_block(tool_input):
    return ToolUseBlock(id="toolu_1", type="tool_use", name=TOOL_NAME, input=tool_input)


def response(stop_reason, *blocks):
    return Message(id="msg_1", type="message", role="assistant", model="m", content=list(blocks),
                   stop_reason=stop_reason, stop_sequence=None,
                   usage=Usage(input_tokens=1, output_tokens=1))


def http_error(status):
    cls = {429: anthropic.RateLimitError, 500: anthropic.InternalServerError}.get(
        status, anthropic.APIStatusError)
    return cls(f"upstream said no, key {KEY}", response=httpx2.Response(status, request=REQUEST), body=None)


# One scenario per entry in RESPONSE_CASES: what the fake client returns or raises.
SCENARIOS = {
    "stop_reason refusal": response("refusal", TextBlock(type="text", text="I can't help with that.")),
    "stop_reason max_tokens": response("max_tokens", tool_block(good_input())),
    "any other stop_reason": response("end_turn", tool_block(good_input())),
    "no tool call": response("tool_use", TextBlock(type="text", text="done")),
    "two tool calls": response("tool_use", tool_block(good_input()), tool_block(good_input())),
    "tool input does not match the schema": response("tool_use", tool_block({"request_id": 5})),
    "quote not found in the message": response(
        "tool_use", tool_block(good_input(supporting_quotes=["an invented quote"]))),
    "request timed out": anthropic.APITimeoutError(request=REQUEST),
    "HTTP 429": http_error(429),
    "HTTP 5xx": http_error(529),
    "other HTTP 4xx": http_error(401),
    "connection failed": anthropic.APIConnectionError(message=f"refused, key {KEY}", request=REQUEST),
}


class FakeClient:
    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []
        self.messages = self

    def create(self, **request):
        self.requests.append(request)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def run_one(workspace, store, settings, schema, outcome):
    """Run intake on IT-001 alone against a fake client that returns or raises `outcome`."""
    for other in workspace.input_dir.glob("*.json"):
        if other.name != DOC:
            other.unlink()
    client = FakeClient(outcome)
    provider = AnthropicProvider(settings, schema, client)
    run_intake(input_files(workspace.input_dir), store, settings, provider, schema, "policy-1",
               "anthropic", force=frozenset({DOC}))
    return client


def test_every_documented_response_case_has_a_scenario():
    assert set(SCENARIOS) == set(RESPONSE_CASES)


@pytest.mark.parametrize("case", list(RESPONSE_CASES))
def test_each_failure_case_becomes_a_retryable_error_record(
        case, workspace, store, settings, schema, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    run_one(workspace, store, settings, schema, SCENARIOS[case])
    record = store.load_current(DOC)
    assert (record["status"], record["owner"], record["next_action"], record["extraction"]) == (
        "error", "IT Service Desk", "retry-extraction", None)
    assert record["error"]["code"] == RESPONSE_CASES[case]
    assert record["error"]["retry_command"] == f"python3 -m intake retry {DOC}"
    assert record["provider"] == "anthropic"
    assert KEY not in json.dumps(record)


def test_a_good_reply_is_routed_and_the_request_has_the_documented_shape(
        workspace, store, settings, schema):
    client = run_one(workspace, store, settings, schema, response("tool_use", tool_block(good_input())))
    record = store.load_current(DOC)
    assert (record["owner"], record["status"], record["next_action"]) == (
        "System Owner", "review", "review-request")
    (request,) = client.requests
    assert request["model"] == settings.model and request["max_tokens"] == settings.max_tokens
    assert request["tool_choice"] == {"type": "tool", "name": TOOL_NAME, "disable_parallel_tool_use": True}
    assert request["tools"][0]["name"] == TOOL_NAME and request["tools"][0]["input_schema"] == schema
    assert "temperature" not in request
    assert message_of(DOC) in request["messages"][0]["content"]


def test_a_failing_attempt_never_stores_the_key_even_in_unexpected_exceptions(
        workspace, store, settings, schema, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    run_one(workspace, store, settings, schema, RuntimeError(f"weird failure carrying {KEY}"))
    record = store.load_current(DOC)
    assert record["error"]["code"] == "provider-error" and KEY not in json.dumps(record)


def test_a_missing_key_fails_before_any_document_is_touched(workspace, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as info:
        main(["run"], paths=workspace)
    assert "ANTHROPIC_API_KEY" in str(info.value)
    assert not list((workspace.state_dir / "current").glob("*.json"))
    assert not workspace.deliverables_dir.exists()


def test_make_provider_reads_the_key_from_the_environment(workspace, schema, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    provider = make_provider(load_settings(), workspace, schema)
    assert isinstance(provider, AnthropicProvider) and provider.model == load_settings().model


def test_reply_type_is_what_the_validator_expects(settings, schema):
    provider = AnthropicProvider(settings, schema, FakeClient(response("tool_use", tool_block(good_input()))))
    reply = provider.extract(DOC, message_of(DOC))
    assert isinstance(reply, ProviderReply) and reply.stop_reason == "tool_use" and len(reply.tool_inputs) == 1
