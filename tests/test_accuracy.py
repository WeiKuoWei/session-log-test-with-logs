import json

from helpers import REPO
from intake.cli import main


def accuracy(workspace, capsys):
    main(["run", "--provider", "mock"], paths=workspace)
    capsys.readouterr()
    assert main(["accuracy", "--provider", "mock"], paths=workspace) == 0
    summary = capsys.readouterr().out
    return summary, (workspace.deliverables_dir / "accuracy.md").read_text()


def edit_reply(workspace, name, **changes):
    path = workspace.mock_replies_dir / name
    reply = json.loads(path.read_text())
    reply["tool_inputs"][0].update(changes)
    path.write_text(json.dumps(reply))


def test_mock_accuracy_catches_exactly_the_two_injected_errors(workspace, capsys):
    summary, report = accuracy(workspace, capsys)
    assert "exact-match fields: 229/231" in summary
    assert "business_purpose present and found in the message: 19/19" in summary
    assert "business_purpose null where no purpose is expected: 2/2" in summary
    assert "supporting quotes not found in the message: 0 of 76" in summary
    assert "expected-null fields with no issue: 0 of 23" in summary
    assert "route matches: 21/21" in summary
    assert "| IT-012.json | permission | admin | write | wrong value |" in report
    assert "| IT-018.json | end_date | 2026-11-03 | 2026-10-27 | wrong value |" in report
    assert "Counts by class: wrong value 2." in report


def test_report_says_mock_only_names_the_injected_errors_and_has_no_live_observation(
        workspace, capsys):
    _, report = accuracy(workspace, capsys)
    assert "| mock | mock | 21 |" in report
    assert "No model produced them." in report
    assert "- IT-012.json: permission is 'write'" in report
    assert "- IT-018.json: end_date is 2026-10-27" in report
    assert "Live observation: none." in report


def test_the_paraphrase_is_measured_but_never_enters_the_queue(workspace, capsys):
    _, report = accuracy(workspace, capsys)
    queue = json.loads((workspace.deliverables_dir / "queue.json").read_text())["entries"]
    extractions = (workspace.deliverables_dir / "extractions.jsonl").read_text().splitlines()
    assert len(queue) == 20 and len(extractions) == 20
    assert not (workspace.state_dir / "current" / "IT-021.json").exists()
    assert (workspace.state_dir / "paraphrase" / "current" / "IT-021.json").exists()
    assert "| IT-021.json (paraphrase) |" in report and "Tomas Rivera from Procurement" in report


def test_an_invented_value_a_missing_value_and_a_wrong_value_are_classified(workspace, capsys):
    edit_reply(workspace, "IT-009.json", manager="Priya Shah")        # expected null
    edit_reply(workspace, "IT-001.json", team=None)                   # expected a value
    edit_reply(workspace, "IT-002.json", requester="owen reed")       # case differs: exact match fails
    _, report = accuracy(workspace, capsys)
    assert "| IT-009.json | manager | null | Priya Shah | invented value |" in report
    assert "| IT-001.json | team | Analytics | null | missing value |" in report
    assert "| IT-002.json | requester | Owen Reed | owen reed | wrong value |" in report
    # the two injected errors plus the case-changed requester are the three wrong values
    assert "Counts by class: invented value 1, missing value 1, wrong value 3." in report


def test_a_document_with_no_valid_extraction_counts_all_eleven_fields_as_mismatches(
        workspace, capsys):
    (workspace.mock_replies_dir / "IT-003.json").unlink()
    summary, report = accuracy(workspace, capsys)
    assert "exact-match fields: 218/231" in summary and "route matches: 20/21" in summary
    assert report.count("| IT-003.json |") >= 11 and "no extraction" in report
    assert "error provider-error" in report


def test_purpose_quotes_and_missing_issue_checks_each_fail_when_they_should(workspace, capsys):
    edit_reply(workspace, "IT-001.json", business_purpose="a purpose the message never states")
    edit_reply(workspace, "IT-010.json", issues=[])
    edit_reply(workspace, "IT-017.json", business_purpose="Where can we find the access request form?")
    summary, report = accuracy(workspace, capsys)
    assert "business_purpose present and found in the message: 18/19" in summary
    assert "business_purpose null where no purpose is expected: 1/2" in summary
    assert "- IT-017.json: expected null, got a purpose" in report
    assert "expected-null fields with no issue: 1 of 23" in summary
    assert "- IT-001.json: purpose is not found in the message" in report
    assert "- IT-010.json: end_date" in report


def test_a_live_provider_record_changes_the_source_statement(workspace, capsys):
    main(["run", "--provider", "mock"], paths=workspace)
    path = workspace.state_dir / "current" / "IT-001.json"
    record = json.loads(path.read_text())
    record["provider"], record["model"] = "anthropic", "claude-sonnet-5-5"
    path.write_text(json.dumps(record))
    main(["accuracy", "--provider", "mock"], paths=workspace)
    report = (workspace.deliverables_dir / "accuracy.md").read_text()
    assert "| anthropic | claude-sonnet-5-5 | 1 |" in report
    assert "Live observation: 1 documents were processed by a live provider" in report
    assert "Live observation: none." not in report


def test_committed_expected_file_was_not_touched_by_the_run(workspace, capsys):
    accuracy(workspace, capsys)
    assert (workspace.expected_file.read_bytes() == (REPO / "expected" / "expected_fields.json").read_bytes())
