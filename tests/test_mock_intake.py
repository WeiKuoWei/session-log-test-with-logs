import json
from collections import Counter

from helpers import REPO, expected_entry
from intake.cli import main

NAMES = [f"IT-{n:03d}.json" for n in range(1, 21)]
FIELDS = ("request_id", "request_date", "kind", "requester", "team", "system", "environment",
          "permission", "start_date", "end_date", "manager")


def canned(name):
    path = REPO / "mock_replies" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_one_intake_command_writes_one_extraction_and_one_queue_entry_per_file(
        workspace, capsys):
    assert main(["--provider", "mock", "run"], paths=workspace) == 0
    out = workspace.deliverables_dir
    rows = [json.loads(line) for line in (out / "extractions.jsonl").read_text().splitlines()]
    queue = json.loads((out / "queue.json").read_text())["entries"]
    assert [r["document_id"] for r in rows] == NAMES
    assert [e["document_id"] for e in queue] == NAMES
    assert all(r["error"] is None and r["extraction"] is not None for r in rows)
    assert all(r["provider"] == "mock" for r in rows)

    by_owner_status = Counter((e["owner"], e["status"]) for e in queue)
    assert by_owner_status == {
        ("IT Service Desk", "needs-information"): 9,
        ("Security Review", "review"): 5,
        ("System Owner", "review"): 4,
        ("IT Service Desk", "review"): 2,
    }
    for entry in queue:
        want = expected_entry(entry["document_id"])["route"]
        assert (entry["owner"], entry["status"], entry["next_action"]) == (
            want["owner"], want["status"], want["next_action"]), entry["document_id"]


def test_it_009_is_needs_information_because_no_manager_is_named(workspace):
    main(["--provider", "mock", "run"], paths=workspace)
    queue = {e["document_id"]: e for e in json.loads(
        (workspace.deliverables_dir / "queue.json").read_text())["entries"]}
    assert queue["IT-009.json"]["status"] == "needs-information"
    assert "missing:manager" in queue["IT-009.json"]["routing_signals"]
    assert [n for n, e in queue.items() if e["owner"] == "IT Service Desk" and e["status"] == "review"] == [
        "IT-005.json", "IT-006.json"]


def test_a_second_run_changes_nothing(workspace, capsys):
    main(["--provider", "mock", "run"], paths=workspace)
    before = (workspace.deliverables_dir / "queue.json").read_text()
    capsys.readouterr()
    main(["--provider", "mock", "run"], paths=workspace)
    assert "outcomes: 20 reused" in capsys.readouterr().out
    assert (workspace.deliverables_dir / "queue.json").read_text() == before


def test_the_mock_replies_differ_from_the_expected_facts_only_where_labelled():
    """The expected facts were written first, from the messages. The canned replies were
    written separately, and may disagree with them only in the two labelled places."""
    misses = set()
    labelled = set()
    for name in NAMES + ["IT-021.json"]:
        reply = canned(name)
        got = reply["tool_inputs"][0]
        want = expected_entry(name)["fields"]
        misses |= {(name, f) for f in FIELDS if got[f] != want[f]}
        if "_deliberate_error" in reply:
            labelled.add(name)
    assert misses == {("IT-012.json", "permission"), ("IT-018.json", "end_date")}
    assert labelled == {"IT-012.json", "IT-018.json"}
