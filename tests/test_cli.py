import hashlib
import json

import pytest

import intake.settings as settings_module
from helpers import REPO
from intake.cli import main
from intake.providers import RESPONSE_CASES
from intake.settings import policy_version


def run_mock(workspace, *args):
    return main(["run", "--provider", "mock", *args], paths=workspace)


def output_of(capsys, argv, workspace):
    capsys.readouterr()
    main(argv, paths=workspace)
    return capsys.readouterr().out


def test_status_is_quiet_when_everything_is_done(workspace, capsys):
    run_mock(workspace)
    out = output_of(capsys, ["status", "--provider", "mock"], workspace)
    assert out.strip() == "summary: 20 done"


def test_provider_flag_works_before_and_after_the_subcommand(workspace, capsys):
    assert main(["--provider", "mock", "run"], paths=workspace) == 0
    assert "provider: mock (from --provider)" in output_of(
        capsys, ["run", "--provider", "mock"], workspace)
    assert "summary: 20 done" in output_of(capsys, ["status", "--provider", "mock"], workspace)


def test_status_says_which_provider_made_a_stale_result(workspace, capsys):
    run_mock(workspace)
    out = output_of(capsys, ["status"], workspace)  # config says anthropic
    assert out.count("STALE") == 20
    assert "IT-001.json" in out and "made by provider mock, configured provider is anthropic" in out
    assert "run: python3 -m intake run" in out and "summary: 20 stale" in out


def test_status_lists_failed_pending_and_changed_documents_with_reasons(workspace, capsys):
    (workspace.mock_replies_dir / "IT-003.json").unlink()   # IT-003 will fail
    run_mock(workspace)
    changed = workspace.input_dir / "IT-001.json"
    data = json.loads(changed.read_text())
    data["message"] += " Update: still the same request."
    changed.write_text(json.dumps(data))
    (workspace.input_dir / "IT-099.json").write_text(json.dumps({"message": "new one"}))

    out = output_of(capsys, ["status", "--provider", "mock"], workspace)
    assert "FAILED  IT-003.json" in out
    assert "provider-error: No canned mock reply for IT-003.json." in out
    assert "retry: python3 -m intake retry IT-003.json" in out
    assert "STALE   IT-001.json" in out and "source file changed since attempt 1" in out
    assert "PENDING IT-099.json" in out and "no result yet" in out
    assert "summary: 18 done, 1 failed, 1 pending, 1 stale" in out


def test_status_shows_the_older_result_kept_behind_a_failed_retry(workspace, capsys):
    run_mock(workspace)
    (workspace.mock_replies_dir / "IT-002.json").unlink()
    main(["retry", "--provider", "mock", "IT-002.json"], paths=workspace)
    out = output_of(capsys, ["status", "--provider", "mock"], workspace)
    assert "older result kept: attempt 1" in out and "Security Review" in out
    assert "history IT-002.json" in out


def test_editing_the_policy_text_reroutes_everything_without_the_model(workspace, capsys):
    run_mock(workspace)
    workspace.policy_file.write_text(workspace.policy_file.read_text() + "\nA new sentence.\n")
    out = output_of(capsys, ["status", "--provider", "mock"], workspace)
    assert "routing policy changed" in out and "summary: 20 stale" in out
    out = output_of(capsys, ["run", "--provider", "mock"], workspace)
    assert "outcomes: 20 rerouted" in out
    assert "summary: 20 done" in output_of(capsys, ["status", "--provider", "mock"], workspace)


def test_policy_version_changes_with_the_policy_text_and_the_rules_revision(
        workspace, monkeypatch):
    first = policy_version(workspace)
    assert policy_version(workspace) == first
    monkeypatch.setattr(settings_module, "ROUTING_REVISION", 2)
    assert policy_version(workspace) != first
    monkeypatch.undo()
    workspace.policy_file.write_text(workspace.policy_file.read_text() + " ")
    assert policy_version(workspace) != first


def test_history_lists_every_attempt_oldest_first(workspace, capsys):
    run_mock(workspace)
    workspace.policy_file.write_text(workspace.policy_file.read_text() + "\nChange.\n")
    run_mock(workspace)
    out = output_of(capsys, ["history", "IT-006.json"], workspace)
    assert "IT-006.json: 2 attempt(s), oldest first" in out
    lines = [l for l in out.splitlines() if l.strip().startswith("#")]
    assert lines[0].startswith("  #1") and lines[1].startswith("  #2")
    assert "IT Service Desk / review / inspect-message" in lines[0]
    assert "re-routed from attempt 1" in lines[1]
    assert main(["history", "IT-404.json"], paths=workspace) == 1


def test_evidence_file_shows_the_exact_request_with_the_key_redacted(workspace, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-key-1")
    assert main(["evidence", "IT-001.json"], paths=workspace) == 0
    text = (workspace.deliverables_dir / "request-evidence.json").read_text()
    evidence = json.loads(text)
    request = evidence["request"]
    assert "sk-ant-secret-key-1" not in text and "[redacted]" in evidence["headers"]["x-api-key"]
    assert request["model"] == "claude-sonnet-5-5" and request["max_tokens"] == 1500
    assert request["tool_choice"] == {"type": "tool", "name": "record_access_request",
                                      "disable_parallel_tool_use": True}
    assert request["tools"][0]["input_schema"] == json.loads((REPO / "snapshot.schema.json").read_text())
    assert "temperature" not in request and "temperature" in evidence
    assert [c["case"] for c in evidence["response_cases"]] == list(RESPONSE_CASES)
