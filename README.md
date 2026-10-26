# Northstar access-request intake

Command-line application that sends each access-request message to a language model, validates the reply against `snapshot.schema.json`, applies the five routing rules of `materials/office-policy.md` in plain code, and writes a review queue. The original task text is in `docs/task.md`.

## Runtime and provider

| Item | Value |
|---|---|
| Language | Python 3 (developed and tested on 3.14.8, macOS) |
| Operating system | macOS or Linux. Uses `fcntl` file locks; Windows is not supported |
| Provider | Anthropic Messages API through the `anthropic` SDK 2.3.0 |
| Default model | `claude-sonnet-5-5` (set in `config/settings.json`) |
| Request shape | one forced tool call (`record_access_request`, input schema = `snapshot.schema.json`), `max_tokens` 1500, no `temperature` (not a parameter of `messages.create` in SDK 2.3.0) |
| Environment variable | `ANTHROPIC_API_KEY` (the only one). A missing key stops `run`, `retry` and `accuracy` before any document is touched |
| Development provider | `mock`: canned replies in `mock_replies/`, no network, no key |

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...        # live runs only
```

`requirements.txt` pins the installed versions of `anthropic`, `jsonschema`, `pytest` and their dependencies.

## Configuration: `config/settings.json`

| Key | Meaning | Default |
|---|---|---|
| `provider` | `anthropic` or `mock` | `anthropic` |
| `model` | model id sent to the API | `claude-sonnet-5-5` |
| `max_tokens` | reply limit | 1500 |
| `workers` | documents processed at the same time | 4 |
| `timeout_seconds` | per-request timeout | 60 |
| `max_retries` | SDK retries for 429, 5xx, timeouts and connection errors before an error record is written | 2 |

Changing `provider`, `model` or `max_tokens`, or editing the prompt or schema, makes every stored result stale; the next `run` extracts them again and keeps the old results in history. `workers`, `timeout_seconds` and `max_retries` do not.

The routing policy version is `rules-<ROUTING_REVISION>+policy-<12 hex of the sha256 of materials/office-policy.md>`. Editing the policy file or bumping `ROUTING_REVISION` in `intake/routing.py` makes stored routes stale; the next `run` re-routes them from the stored extraction without calling the model. `tests/test_routing_revision.py` fails if `routing.py` changes without a bump.

## Commands

Run from the repository root. `--provider mock` (or `anthropic`) may be given before or after the subcommand and overrides the config for that command.

| Command | Does |
|---|---|
| `python3 -m intake run` | Process every document in `materials/requests/` that is new, changed, failed or stale. Reuses the rest. Rewrites `deliverables/extractions.jsonl` and `deliverables/queue.json` |
| `python3 -m intake status` | List every document that is not done, with the reason, then a summary line |
| `python3 -m intake queue [--status needs-information] [--owner "Security Review"]` | Print the current queue |
| `python3 -m intake history IT-006.json` | List every attempt for one document, oldest first |
| `python3 -m intake retry IT-006.json [IT-007.json ...]` | Force a fresh attempt for the named documents |
| `python3 -m intake accuracy` | Compare current extractions with `expected/expected_fields.json`, write `deliverables/accuracy.md` |
| `python3 -m intake evidence [IT-001.json]` | Write `deliverables/request-evidence.json` (the request as built, key redacted) |
| `python3 -m pytest -q` | Run the tests. No key or network needed |

Without a key, add `--provider mock`, for example `python3 -m intake run --provider mock`.

## Intake procedure

1. Copy the exported JSON files into `materials/requests/`. To supply a corrected message, replace the file; a file that is no longer there is not withdrawn, its last result stays in the queue.
2. `python3 -m intake run`. Output starts with the provider and model in use, then outcome counts (`extracted`, `reused`, `rerouted`, `busy`), then one `FAILED` block per failure with its retry command.
3. From another terminal, `python3 -m intake queue` or `status` show finished documents while others are pending. The deliverable files are refreshed every 25 documents and at exit.
4. Run each printed retry command word for word. Failures never block other documents.

## Reading the queue

`deliverables/queue.json` has one entry per document, linked to `deliverables/extractions.jsonl` by `document_id` (the input filename, for example `IT-001.json`). The request id stated in the message is `request_id`; the two can differ.

| owner | status | next_action | Meaning |
|---|---|---|---|
| IT Service Desk | review | inspect-message | The message contains an instruction aimed at the system (rule 1). Nothing was acted on |
| IT Service Desk | review | confirm-withdrawal | Withdrawal with a request id and date (rule 2) |
| IT Service Desk | needs-information | clarify | Kind other or null, conflicting details, identifier mismatch, a missing required fact, or start date after end date (rule 3) |
| Security Review | review | review-risk-then-owner | Complete new or change request involving production, write or admin (rule 4) |
| System Owner | review | review-request | Complete staging, read request (rule 5) |
| IT Service Desk | error | retry-extraction | The attempt failed; `error` holds the code, message and retry command |

Every successful record awaits a human decision; the application approves nothing.

Queue entry fields: `document_id`, `request_id`, `requester`, `kind`, `owner`, `status`, `next_action`, `source_sha256`, `attempt`, `routing_signals`, `error` (code or null), `last_valid`.

`routing_signals` lists why a route was chosen: `instruction-override:pattern-scan`, `instruction-override:model-issue`, `conflict:model-issue`, `kind:null`, `kind:other`, `id-mismatch`, `missing:<field>`, `start-after-end`.

`extractions.jsonl` lines hold `document_id`, `source_sha256`, `extraction` (schema-conforming object, or null on error), `status`, `owner`, `next_action`, `error` (null on success), plus `attempt`, `attempted_at`, `provider`, `model`, `settings_fingerprint`, `policy_version`, `routing_signals`, `rerouted_from_attempt` and `last_valid`.

When a later attempt fails, the current record shows the failure and `last_valid` names the earlier valid attempt, its source hash and its route. The earlier result itself is in `state/history/`.

## Failures

| Error code | Cause | Action |
|---|---|---|
| `refusal` | model stop reason `refusal` | Retry; if it repeats, handle the message by hand |
| `truncated` | stop reason `max_tokens` | Retry; raise `max_tokens` if it repeats |
| `unexpected-stop`, `malformed`, `schema-invalid` | no single valid tool call | Retry |
| `ungrounded-quote`, `ungrounded-date`, `ungrounded-request-id` | a quote, date or request id is not in the message text | Retry |
| `timeout`, `connection-error`, `provider-unavailable` | service slow, unreachable or 5xx | Retry later |
| `rate-limited` | HTTP 429 | Retry later; lower `workers` if frequent |
| `provider-rejected` | other 4xx, for example 401 from a bad key | Fix the cause, then retry; every document fails the same way until then |
| `provider-error` | any other exception | Read the message, then retry |
| `invalid-input` | the input file is not JSON with a string `message` | Fix or remove the file |

`python3 -m intake status` lists failed documents with their retry commands. A failed document is retried automatically by the next plain `run`.

## Where things are

| Path | Holds |
|---|---|
| `materials/requests/` | input exports; `materials/office-policy.md` is the routing policy |
| `state/current/<id>.json` | latest attempt per document, replaced atomically |
| `state/history/<id>/NNNN_<sha12>.json` | every attempt, never edited |
| `state/claims/` | per-document lock files (not committed) |
| `state/paraphrase/` | the accuracy paraphrase, kept out of the queue |
| `deliverables/` | `extractions.jsonl`, `queue.json`, `accuracy.md`, `request-evidence.json`, `verification.md` |
| `expected/expected_fields.json` | hand-written expected facts and routes for 20 messages plus the paraphrase |
| `mock_replies/` | canned replies; IT-012 and IT-018 are deliberately wrong and labelled |
| `intake/` | the application; `tests/` the tests |

The repository ships with the state of one mock run (`provider: mock` on every record). A live `run` treats those results as stale, extracts again and keeps the mock results in history.

## Assumptions and limits

| Topic | Assumption | Limit |
|---|---|---|
| Workload | 200 to 400 messages on an ordinary day, about 2,000 on an onboarding morning | Not load-tested. Throughput is about `workers` divided by seconds per reply; with 4 workers and a reply time of N seconds, 2,000 messages take roughly 2,000 x N / 4 seconds (arithmetic, not measured). Rate limits are handled by SDK retries, then an error record, not by pacing |
| Reviewers start early | `queue` and `status` read the per-document files, so ready requests are visible while the rest is pending | The deliverable files lag by up to 25 documents during a run |
| Slow or failing provider | Each document is independent; a slow one occupies one worker, a failure becomes one error record | Documents wait for a free worker; a stalled request holds its worker for roughly `timeout_seconds` x (`max_retries` + 1) plus SDK backoff |
| Two operators | Both run `python3 -m intake run` on the same checkout. A per-document file lock means each document is processed by one of them; a document the other holds is reported `busy` and skipped. Writes are atomic and the deliverables are rebuilt under a lock | Locks are `flock` and need a local filesystem. Network shares and two machines are not supported. Run `run` again to pick up `busy` documents. Verified with two threads in one process, not two processes |
| Interruption | Ctrl-C finishes requests already in flight, writes the deliverables, prints how many documents have a result and exits with code 130. A killed process leaves only whole files and releases its locks. Rerun the same command; finished documents are reused | A document being processed at the moment of a kill has no new record, so it is processed again from the start |
| Updates | A changed file gets a new attempt with its new hash; the old result stays in history. An unchanged file is reused | One input folder; no export batch format beyond one JSON file per message |
| Conflicts and overrides | Conflicting details are routed to clarification when the model leaves the field null or starts an issue with `conflict:`; override attempts are found by a text pattern scan or an `instruction-override:` issue | A model that silently picks one of two conflicting values and writes no `conflict:` issue is not detected. The override patterns are a fixed list and can miss new wording |
| Model quality | Accuracy figures in `deliverables/accuracy.md` come from mock replies | They say nothing about the live model |
| Secrets | The key is read from the environment only and removed from stored error text and output | Keys in other formats than `sk-ant-...` are removed only if they equal `ANTHROPIC_API_KEY` |
