import json
from collections import Counter

import pytest

from helpers import MATERIALS, extraction_for, message_of
from intake.routing import OVERRIDE_PATTERNS, REQUIRED_FACTS, route
from intake.settings import Paths

SECURITY = ("Security Review", "review", "review-risk-then-owner")
OWNER = ("System Owner", "review", "review-request")
CLARIFY = ("IT Service Desk", "needs-information", "clarify")


def routed(name, **overrides):
    decision = route(extraction_for(name, **overrides), name, message_of("IT-001.json"))
    return (decision.owner, decision.status, decision.next_action), decision.signals


def test_complete_staging_read_goes_to_system_owner():
    assert routed("IT-001.json")[0] == OWNER


@pytest.mark.parametrize("overrides", [
    {"environment": "production"},
    {"permission": "write"},
    {"permission": "admin"},
])
def test_complete_production_write_or_admin_goes_to_security(overrides):
    assert routed("IT-001.json", **overrides)[0] == SECURITY


@pytest.mark.parametrize("name", [n for n in REQUIRED_FACTS])
def test_any_missing_required_fact_needs_information(name):
    result, signals = routed("IT-001.json", **{name: None})
    assert result == CLARIFY
    assert f"missing:{name}" in signals


def test_change_request_requires_the_same_facts():
    assert routed("IT-001.json", kind="change", end_date=None)[0] == CLARIFY


@pytest.mark.parametrize("kind", ["other", None])
def test_other_or_null_kind_needs_information(kind):
    assert routed("IT-001.json", kind=kind)[0] == CLARIFY


def test_start_after_end_needs_information():
    result, signals = routed("IT-001.json", start_date="2026-11-05", end_date="2026-11-02")
    assert result == CLARIFY and "start-after-end" in signals


def test_identifier_mismatch_needs_information():
    result, signals = routed("IT-016.json", request_id="IT-061")
    assert result == CLARIFY and "id-mismatch" in signals


def test_conflict_issue_prefix_forces_clarification_even_when_every_field_is_filled():
    result, signals = routed("IT-004.json", environment="staging",
                             issues=["Conflict: staging vs production"])
    assert result == CLARIFY and signals == ("conflict:model-issue",)


def test_withdrawal_with_id_and_date_goes_to_confirm_withdrawal():
    nulls = {k: None for k in ("team", "system", "environment", "permission", "start_date",
                               "end_date", "business_purpose")}
    result, _ = routed("IT-005.json", kind="withdrawal", **nulls)
    assert result == ("IT Service Desk", "review", "confirm-withdrawal")


def test_withdrawal_without_a_date_needs_information():
    result, signals = routed("IT-005.json", kind="withdrawal", request_date=None)
    assert result == CLARIFY and "missing:request_date" in signals


def test_override_found_by_pattern_scan_even_if_the_model_reports_nothing():
    decision = route(extraction_for("IT-006.json"), "IT-006.json", message_of("IT-006.json"))
    assert (decision.owner, decision.status, decision.next_action) == (
        "IT Service Desk", "review", "inspect-message")
    assert decision.signals == ("instruction-override:pattern-scan",)


def test_override_found_by_model_issue_on_a_clean_message():
    ex = extraction_for("IT-001.json", issues=["instruction-override: asks to skip approval"])
    decision = route(ex, "IT-001.json", message_of("IT-001.json"))
    assert decision.next_action == "inspect-message"
    assert decision.signals == ("instruction-override:model-issue",)


def test_both_override_signals_are_recorded():
    ex = extraction_for("IT-006.json", issues=["instruction-override: SYSTEM OVERRIDE"])
    decision = route(ex, "IT-006.json", message_of("IT-006.json"))
    assert decision.signals == ("instruction-override:pattern-scan",
                                "instruction-override:model-issue")


def test_override_wins_over_every_later_rule():
    ex = extraction_for("IT-006.json", environment="production", permission="admin", kind="other")
    assert route(ex, "IT-006.json", message_of("IT-006.json")).next_action == "inspect-message"


def test_pattern_scan_fires_on_only_the_override_message():
    hits = [
        path.name for path in sorted(MATERIALS.glob("*.json"))
        if any(p.search(" ".join(message_of(path.name).lower().split())) for p in OVERRIDE_PATTERNS)
    ]
    assert hits == ["IT-006.json"]


def test_routing_the_expected_facts_gives_the_expected_route():
    """Expected facts and routes were written from the messages and policy by hand; routing
    them in code must agree, and the sample must split 9 / 5 / 4 / 2."""
    expected = json.loads(Paths().expected_file.read_text(encoding="utf-8"))
    counts = Counter()
    for name, entry in expected.items():
        if name.startswith("_"):
            continue
        extraction = {
            **entry["fields"],
            "business_purpose": "stated" if entry["business_purpose"] == "present" else None,
            "supporting_quotes": [],
            "issues": [f"{prefix} see message" for prefix in entry["issue_prefixes"]],
        }
        decision = route(extraction, name, message_of(name))
        got = {"owner": decision.owner, "status": decision.status,
               "next_action": decision.next_action}
        assert got == entry["route"], name
        if name != "IT-021.json":
            counts[(decision.owner, decision.status)] += 1
    assert counts == {
        ("IT Service Desk", "needs-information"): 9,
        ("Security Review", "review"): 5,
        ("System Owner", "review"): 4,
        ("IT Service Desk", "review"): 2,
    }
