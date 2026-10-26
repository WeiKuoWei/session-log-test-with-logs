import pytest

from helpers import extraction_for, message_of
from intake.models import ExtractionError, ProviderReply
from intake.settings import load_schema
from intake.validate import validate_reply

MESSAGE = message_of("IT-001.json")
SCHEMA = load_schema()


def check(reply):
    return validate_reply(reply, MESSAGE, SCHEMA)


def good(**overrides):
    return ProviderReply("tool_use", [extraction_for("IT-001.json", **overrides)])


def code_of(reply):
    with pytest.raises(ExtractionError) as info:
        check(reply)
    return info.value.code


def test_valid_reply_returns_the_extraction():
    assert check(good(supporting_quotes=["request IT-001 dated 2026-10-22"]))["request_id"] == "IT-001"


def test_refusal_is_an_error():
    assert code_of(ProviderReply("refusal", [])) == "refusal"


def test_cut_off_reply_is_an_error_even_if_it_holds_a_tool_input():
    assert code_of(ProviderReply("max_tokens", [extraction_for("IT-001.json")])) == "truncated"


@pytest.mark.parametrize("stop", ["end_turn", "pause_turn", "stop_sequence"])
def test_other_stop_reasons_are_errors(stop):
    assert code_of(ProviderReply(stop, [extraction_for("IT-001.json")])) == "unexpected-stop"


@pytest.mark.parametrize("inputs", [[], [{}, {}]])
def test_not_exactly_one_tool_call_is_malformed(inputs):
    assert code_of(ProviderReply("tool_use", inputs)) == "malformed"


@pytest.mark.parametrize("broken", [
    {"extra_field": "x"},
    {"kind": "grant"},
    {"environment": "dev"},
    {"permission": "root"},
    {"issues": "none"},
])
def test_schema_violations_are_errors(broken):
    assert code_of(good(**broken)) == "schema-invalid"


def test_missing_required_property_is_a_schema_error():
    ex = extraction_for("IT-001.json")
    del ex["manager"]
    assert code_of(ProviderReply("tool_use", [ex])) == "schema-invalid"


def test_quote_that_is_not_in_the_message_is_an_error():
    assert code_of(good(supporting_quotes=["Maya asked for admin"])) == "ungrounded-quote"


@pytest.mark.parametrize("field,value", [
    ("start_date", "2026-10-30"),      # well-formed but not in the message
    ("end_date", "next Friday"),       # not a date
    ("start_date", "2026-02-30"),      # not a real date
])
def test_dates_must_be_real_iso_dates_that_appear_in_the_message(field, value):
    assert code_of(good(**{field: value})) == "ungrounded-date"


def test_request_id_must_appear_in_the_message():
    assert code_of(good(request_id="IT-999")) == "ungrounded-request-id"
