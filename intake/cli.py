import argparse
import dataclasses
import hashlib
from collections import Counter

from .providers import make_provider
from .runner import decide, input_files, run_intake
from .settings import Paths, load_schema, load_settings, settings_fingerprint
from .store import Store


def main(argv=None, paths=None):
    paths = paths or Paths()
    args = _parser().parse_args(argv)
    settings = load_settings()
    if args.provider:
        settings = dataclasses.replace(settings, provider=args.provider)
    store = Store(paths)

    if args.command == "queue":
        return _show_queue(store, args)
    if args.command == "status":
        return _show_status(store, settings, paths)
    return _run(store, settings, paths, args)


def _parser():
    parser = argparse.ArgumentParser(prog="python3 -m intake")
    parser.add_argument("--provider", help="override the provider in config/settings.json (anthropic or mock)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="process every request that is new, changed, failed or stale")
    retry = sub.add_parser("retry", help="force a fresh attempt for named documents")
    retry.add_argument("documents", nargs="+", metavar="IT-001.json")
    sub.add_parser("status", help="count done / failed / pending and list retry commands")
    queue = sub.add_parser("queue", help="print the current review queue")
    queue.add_argument("--status")
    queue.add_argument("--owner")
    return parser


def _run(store, settings, paths, args):
    provider = make_provider(settings, paths)
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
    outcomes = run_intake(files, store, settings, provider, load_schema(), force)
    print("outcomes: " + ", ".join(f"{n} {a}" for a, n in sorted(Counter(outcomes.values()).items())))
    failed = [r for r in store.all_current() if r["status"] == "error"]
    for record in failed:
        print(f"FAILED {record['document_id']}: {record['error']['code']} - "
              f"{record['error']['message']}\n  retry: {record['error']['retry_command']}")
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


def _show_status(store, settings, paths):
    fingerprint = settings_fingerprint(settings, load_schema())
    counts = Counter()
    for path in input_files(paths.input_dir):
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        current = store.load_current(path.name)
        if current is None:
            counts["pending"] += 1
        elif current["status"] == "error":
            counts["failed"] += 1
            print(f"FAILED {path.name}: {current['error']['code']}\n  retry: {current['error']['retry_command']}")
        else:
            action = decide(current, sha, fingerprint, settings.policy_version, False)
            counts[{"reuse": "done", "extract": "stale", "reroute": "stale-policy"}[action]] += 1
    print(", ".join(f"{name} {n}" for name, n in sorted(counts.items())) or "no input files")
    return 0
