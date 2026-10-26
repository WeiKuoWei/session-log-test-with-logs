import argparse
import dataclasses
import hashlib
import json
from collections import Counter

from .accuracy import measure, mock_labels, render_report, summary_lines
from .evidence import build_evidence
from .providers import make_provider
from .runner import decide, input_files, read_message, run_intake
from .settings import (Paths, load_schema, load_settings, policy_version, retry_command,
                       settings_fingerprint)
from .store import Store, atomic_write

PROVIDER_HELP = "override the provider in config/settings.json (anthropic or mock)"


def main(argv=None, paths=None):
    paths = paths or Paths()
    args = _parser().parse_args(argv)
    settings = load_settings()
    configured = settings.provider
    if args.provider:
        settings = dataclasses.replace(settings, provider=args.provider)
    store = Store(paths)

    if args.command == "queue":
        return _show_queue(store, args)
    if args.command == "history":
        return _show_history(store, args.document)
    if args.command == "status":
        return _show_status(store, settings, paths, configured)
    if args.command == "evidence":
        return _write_evidence(settings, paths, args.document)
    if args.command == "accuracy":
        return _accuracy(store, settings, paths, configured)
    return _run(store, settings, paths, args, configured)


def _parser():
    # --provider is accepted before or after the subcommand; the copy on each subcommand
    # has no default so it cannot overwrite a value given before it.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--provider", default=argparse.SUPPRESS, help=PROVIDER_HELP)

    parser = argparse.ArgumentParser(prog="python3 -m intake")
    parser.add_argument("--provider", default=None, help=PROVIDER_HELP)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", parents=[common],
                   help="process every request that is new, changed, failed or stale")
    retry = sub.add_parser("retry", parents=[common], help="force a fresh attempt for named documents")
    retry.add_argument("documents", nargs="+", metavar="IT-001.json")
    sub.add_parser("status", parents=[common],
                   help="list every document that is not done, with the reason")
    queue = sub.add_parser("queue", help="print the current review queue")
    queue.add_argument("--status")
    queue.add_argument("--owner")
    history = sub.add_parser("history", help="list every attempt for one document")
    history.add_argument("document", metavar="IT-001.json")
    sub.add_parser("accuracy", parents=[common],
                   help="compare current extractions with expected/expected_fields.json "
                        "and write deliverables/accuracy.md")
    evidence = sub.add_parser("evidence", parents=[common],
                              help="write deliverables/request-evidence.json for one document")
    evidence.add_argument("document", nargs="?", default="IT-001.json", metavar="IT-001.json")
    return parser


def _run(store, settings, paths, args, configured):
    schema = load_schema()
    provider = make_provider(settings, paths, schema)
    files = input_files(paths.input_dir)
    force = frozenset()
    if args.command == "retry":
        force = frozenset(args.documents)
        files = [f for f in files if f.name in force]
        unknown = force - {f.name for f in files}
        if unknown:
            raise SystemExit(f"Not found in {paths.input_dir}: {', '.join(sorted(unknown))}")
    source = "from --provider" if args.provider else "from config/settings.json"
    print(f"provider: {settings.provider} ({source}), model: {provider.model}, documents: {len(files)}")
    try:
        outcomes = run_intake(files, store, settings, provider, schema, policy_version(paths),
                              configured, force)
    except KeyboardInterrupt:
        finished = sum(1 for f in files if store.load_current(f.name))
        print(f"interrupted: {finished} of {len(files)} documents have a current result; "
              "rerun the same command to process the rest (finished documents are reused)")
        return 130
    print("outcomes: " + ", ".join(f"{n} {a}" for a, n in sorted(Counter(outcomes.values()).items())))
    failed = [r for r in store.all_current() if r["status"] == "error"]
    for record in failed:
        print(f"FAILED {record['document_id']}: {record['error']['code']} - "
              f"{record['error']['message']}\n  retry: {_retry_for(record, configured)}")
    print(f"wrote {paths.deliverables_dir}/extractions.jsonl and queue.json")
    return 1 if failed else 0


def _show_queue(store, args):
    rows = store.all_current()
    for key in ("status", "owner"):
        wanted = getattr(args, key)
        if wanted:
            rows = [r for r in rows if r[key] == wanted]
    print(f"{'document_id':<14}{'owner':<17}{'status':<19}{'next_action':<24}error")
    for r in rows:
        code = r["error"]["code"] if r["error"] else ""
        print(f"{r['document_id']:<14}{r['owner']:<17}{r['status']:<19}{r['next_action']:<24}{code}")
    return 0


def _show_history(store, document_id):
    attempts = store.history(document_id)
    if not attempts:
        print(f"No attempts recorded for {document_id}.")
        return 1
    print(f"{document_id}: {len(attempts)} attempt(s), oldest first")
    for a in attempts:
        outcome = a["error"]["code"] if a["error"] else f"{a['owner']} / {a['status']} / {a['next_action']}"
        note = f" (re-routed from attempt {a['rerouted_from_attempt']})" if a["rerouted_from_attempt"] else ""
        print(f"  #{a['attempt']} {a['attempted_at']} source {a['source_sha256'][:12]} "
              f"{a['provider']}/{a['model']} settings {a['settings_fingerprint'][:8]} "
              f"policy {a['policy_version']}: {outcome}{note}")
    return 0


def _retry_for(record, configured):
    """Recomputed at display time: the configured provider may have changed since the attempt."""
    return retry_command(record["document_id"], record["provider"], configured)


def _show_status(store, settings, paths, configured):
    schema = load_schema()
    fingerprint = settings_fingerprint(settings, schema)
    policy = policy_version(paths)
    counts = Counter()
    for path in input_files(paths.input_dir):
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        current = store.load_current(path.name)
        kind, lines = _classify(current, sha, fingerprint, policy, settings, configured)
        counts[kind] += 1
        if kind != "done":
            print(f"{kind.upper():<8}{path.name}")
            for line in lines:
                print(f"        {line}")
    print("summary: " + (", ".join(f"{n} {k}" for k, n in sorted(counts.items())) or "no input files"))
    return 0


def _classify(current, sha, fingerprint, policy, settings, configured):
    """Return (kind, reason lines) where kind is done, pending, failed or stale."""
    if current is None:
        return "pending", ["no result yet", "run: python3 -m intake run"]
    if current["status"] == "error":
        error = current["error"]
        lines = [f"{error['code']}: {error['message']}", f"retry: {_retry_for(current, configured)}"]
        if current["last_valid"]:
            old = current["last_valid"]
            lines.append(f"older result kept: attempt {old['attempt']}, source {old['source_sha256'][:12]}, "
                         f"{old['status']} / {old['owner']} (see: python3 -m intake history {current['document_id']})")
        return "failed", lines
    if decide(current, sha, fingerprint, policy, False) == "reuse":
        return "done", []
    lines = []
    if current["source_sha256"] != sha:
        lines.append(f"source file changed since attempt {current['attempt']} "
                     f"(was {current['source_sha256'][:12]}, now {sha[:12]})")
    if current["settings_fingerprint"] != fingerprint:
        if current["provider"] != settings.provider:
            lines.append(f"made by provider {current['provider']}, configured provider is {settings.provider}")
        else:
            lines.append(f"made with provider {current['provider']}, model {current['model']}; the "
                         "request settings (model, max_tokens, prompt or schema) have changed since")
    if current["policy_version"] != policy and not lines:
        lines.append(f"routing policy changed: {current['policy_version']} -> {policy}; "
                     "run re-routes it without calling the model")
    lines.append("run: python3 -m intake run")
    return "stale", lines


def _write_evidence(settings, paths, document_id):
    path = paths.input_dir / document_id
    if not path.exists():
        raise SystemExit(f"Not found: {path}")
    evidence = build_evidence(settings, load_schema(), document_id, read_message(path.read_bytes()))
    target = paths.deliverables_dir / "request-evidence.json"
    atomic_write(target, json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {target}")
    return 0


def _accuracy(store, settings, paths, configured):
    """Process the paraphrase into its own store, then measure all 21 documents."""
    schema = load_schema()
    provider = make_provider(settings, paths, schema)
    paraphrase_store = Store(paths, scope="paraphrase")
    run_intake(input_files(paths.paraphrase_dir), paraphrase_store, settings, provider, schema,
               policy_version(paths), configured)
    result = measure(paths, store, paraphrase_store)
    report = render_report(result, settings, policy_version(paths), mock_labels(paths.mock_replies_dir))
    target = paths.deliverables_dir / "accuracy.md"
    atomic_write(target, report)
    print("\n".join(summary_lines(result)))
    print(f"wrote {target}")
    return 0
