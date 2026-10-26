# Verification

Observed results are labelled by what produced them: scripted provider (a test double that returns or raises what the test says), mock replies (hand-written canned replies in `mock_replies/`), fake client (a stand-in for the Anthropic SDK client that returns or raises real SDK response and exception types), or operator (a person running the commands in a scratch copy). No live provider call was made in any observation below.

## Commands

| Command | Asserts | Compared against |
|---|---|---|
| `python3 -m pytest -q` | 108 tests pass (table below) | expected values written in the tests, `expected/expected_fields.json`, `snapshot.schema.json`, `materials/office-policy.md` |
| `python3 -m intake run --provider mock` | one extraction and one queue entry per input file | 20 files in `materials/requests/`; route split 9 needs-information, 5 Security Review, 4 System Owner, 2 IT Service Desk review |
| `python3 -m intake run --provider mock` (second time) | every document reused, queue unchanged | the first run's records |
| `python3 -m intake accuracy --provider mock` | 5 measurements (table below) | `expected/expected_fields.json`, message text |
| `python3 -m intake status --provider mock` | `summary: 20 done` after a run | stored hashes, settings fingerprint, policy version |

### What the test files check

| File | Tests | Asserts | Compared against |
|---|---|---|---|
| `tests/test_routing.py` | 29 | each of the five rules; each missing required fact; `conflict:` prefix alone sends a fully filled record to clarification; override found by pattern scan and by model issue, both recorded; the pattern scan fires on IT-006 only among the 20 messages; routing the expected facts gives the expected route for all 21 documents and a 9 / 5 / 4 / 2 split | route table in `materials/office-policy.md`; `expected/expected_fields.json` |
| `tests/test_validate.py` | 19 | refusal, `max_tokens`, other stop reasons, zero or two tool calls, schema violations, quote not in message, invented or malformed dates, request id not in message | `snapshot.schema.json`; message text |
| `tests/test_intake.py` | 17 | complete request (IT-001); missing dates (IT-010); conflicting details (IT-004, IT-020); embedded instruction (IT-006); provider failure with the key absent from the stored record; unchanged rerun reuses everything; changed source keeps both hashes and one current entry; refusal and cut-off; failed retry after an earlier success keeps the older result named in `last_valid`; settings change refreshes; policy change re-routes without a model call; partial run resumes with only the rest; interrupted run (provider raises `KeyboardInterrupt`) keeps finished records, leaves no lock held, renders them, and a rerun processes only the rest; history without a current file is reprocessed; two threads never process one document twice; unreadable input becomes an error record | hand-written expectations in each test |
| `tests/test_mock_intake.py` | 4 | 20 files give 20 extractions and 20 queue entries with the 9 / 5 / 4 / 2 split and each route equal to its expected route; IT-009 is needs-information for a missing manager; a second run changes nothing; the mock replies differ from the expected facts only in the two labelled places | `expected/expected_fields.json` |
| `tests/test_anthropic_provider.py` | 18 | one scenario per response case (12): each becomes an error record with owner IT Service Desk, next action retry-extraction, null extraction, retry command, no key in the record; request has the documented model, `max_tokens`, forced tool, schema, no `temperature`; missing key fails before any document is touched | the case list in `intake/providers.py` (same list feeds `request-evidence.json`) |
| `tests/test_cli.py` | 12 | `status` lists failed, pending and stale documents with reasons; `--provider` works before and after the subcommand; the printed retry command works word for word with no key; Ctrl-C message and exit code 130; policy version changes with the policy text and with the rules revision; `history`; `evidence` file has the key redacted | strings the commands print; files they write |
| `tests/test_accuracy.py` | 8 | the 229/231 result and its two named mismatches; mock-only wording; paraphrase outside the queue; wrong, invented and missing values classed; a document with no extraction counts 11 mismatches; purpose, quote and missing-issue checks each fail when they should; wording changes for a live record | the figures printed by `accuracy` |
| `tests/test_routing_revision.py` | 1 | `intake/routing.py` hash equals the pinned hash for `ROUTING_REVISION` | pinned hash |

Observed: `108 passed` (scripted providers, mock replies, fake client).

### Accuracy measurements

Observed on mock replies (provider `mock`, 21 documents including the paraphrase). Not a live observation.

| Check | Result |
|---|---|
| 11 fields, exact match, 21 documents (231) | 229/231 |
| `business_purpose` present and found in the message | 19/19 |
| `business_purpose` null where no purpose is expected | 2/2 |
| Supporting quotes not found in the message | 0 of 76 |
| Expected-null fields with no issue naming them | 0 of 23 |
| Route matches | 21/21 |

The two mismatches are the injected errors: IT-012 `permission` (expected `admin`, got `write`) and IT-018 `end_date` (expected `2026-11-03`, got `2026-10-27`). Full listing: `deliverables/accuracy.md`.

### Mock intake

Observed on mock replies: 20 extracted on the first run, 20 reused on the second. Queue: 9 needs-information, 5 Security Review, 4 System Owner, 2 IT Service Desk review. Files: `deliverables/queue.json`, `deliverables/extractions.jsonl`.

### Checks that a test can fail

Observed by removing the guarded code, running the test, restoring the code:

| Removed | Result |
|---|---|
| key redaction in the provider and runner | 3 tests red (HTTP 429, 5xx, other 4xx cases) |
| deliverable render after an interrupted run | the interrupted-run test red |

### Checks by the operator (Wei Kuo)

Done by hand, outside the test suite:

- worked out the 11 non-free-text fields for all 20 messages independently; all 220 values agree with `expected/expected_fields.json`
- all 20 `source_sha256` values match the input file bytes
- every supporting quote is a substring of its message
- `expected/expected_fields.json` was committed before the mock replies
- in a scratch copy: 20 extracted from empty state, 20 reused on rerun; IT-013's mock reply set to refusal, then `retry` gave FAILED in `status` with attempt 1 named; changing IT-001's bytes gave a new attempt with the new hash, kept the old one, and left one queue entry; after the retry-command repair the printed command, run word for word with no key, recovered the document (20 done)
- the paraphrase and its expected fields match its text

## Repairs made in this session

| Problem | Found by | Repair | Test |
|---|---|---|---|
| Conflicts routed on a null value alone; a model that picked one value but noted the conflict would reach System Owner. Override found only by pattern scan | Wei Kuo | Prompt requires issues to start with `conflict:` and `instruction-override:`; rule 3 also fires on `conflict:`; override accepts the pattern scan or the model issue; the signals that fired are stored in `routing_signals` | `tests/test_routing.py`, `tests/test_intake.py` (conflict and override cases) |
| `status` printed only a count; `--provider` was rejected after the subcommand | Wei Kuo | `status` lists each document that is not done with a reason; `--provider` accepted before or after the subcommand | `tests/test_cli.py` |
| Policy version was a string typed into the config; editing the policy or routing code without changing it left old routes in the queue | Wei Kuo | Version derived from the sha256 of `office-policy.md` plus `ROUTING_REVISION`; stored routes re-route without the model. `routing.py` is not hashed automatically (a comment edit would otherwise create a new attempt for every document); a pin test fails instead | `tests/test_cli.py`, `tests/test_routing_revision.py` |
| Retry command omitted `--provider` for a mock run and failed with "ANTHROPIC_API_KEY is not set" | Wei Kuo | Command built from the provider recorded on the failed attempt; `--provider` added when it differs from the configured one; recomputed when printed | `tests/test_cli.py` (runs the printed command) |
| Purpose line counted IT-005 and IT-017, where no purpose is expected, in "present and found" | Wei Kuo | Split into present and found (19/19) and null where absent (2/2) | `tests/test_accuracy.py` |
| No test interrupted a run; the resume test only processed 3 documents first | Wei Kuo | Interrupted-run test added; Ctrl-C now prints how many documents finished and exits with code 130 instead of a traceback | `tests/test_intake.py`, `tests/test_cli.py` |

Defects found and fixed by the coding agent during the build, all in its own tests or helpers: the test helper's default dates were not in the messages and the grounding check rejected them (helper now builds from the expected facts); two test assertions had wrong expected counts or wording and were corrected. No application defect was found this way.

## Operating limits

- The two-operator test runs two threads in one process. Two processes, two machines or two checkouts were not tested.
- File locks use `flock` and need a local filesystem. Network shares are not supported. POSIX only.
- No live provider call was made. The Anthropic provider was tested with a fake client. Whether the live API accepts the schema's `["string", "null"]` types in a tool `input_schema` is untested.
- No load test. The 2,000-message morning was not run; the mock provider answers instantly, so no timing, rate-limit or throughput figure was observed.
- The accuracy figures describe mock replies, not a model.
- A model that picks one of two conflicting values and writes no `conflict:` issue is not caught by routing. Accuracy checks catch it only for the 21 known documents.
- The override pattern list is fixed text and can miss other wording.
- Deliverable files are rebuilt every 25 completed documents and at exit; during a run `queue` and `status` are current, the files can lag.
- The repository carries the state of one mock run (`state/`); a live run re-extracts every document and keeps the mock results in history.

## Who did what

| Who | Work |
|---|---|
| Claude Code (model `claude-sonnet-5-5`) | Wrote the code, tests, mock replies, `expected/expected_fields.json`, the paraphrase message, and these documents. Checked the model id and the missing `temperature` parameter against the installed SDK. Ran the tests and the mutation checks above |
| Wei Kuo | Set the scope and acceptance checks. Chose the provider, model, output format and the file-based design (JSON files and a CLI, no web UI, no database). Decided what to leave out: web UI, database, live run, a real multi-process race. Set the IT-009 route (needs-information, no manager named) and the `business_purpose` rule (verbatim excerpt, whitespace-normalised substring) before any code. Caught the issues listed under repairs. Checked the 220 expected values, the hashes, the quotes and the operator flow in a scratch copy |
