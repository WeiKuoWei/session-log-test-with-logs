"""The intake loop: reuse what is current, claim a document, extract, validate, route, save."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from .models import ExtractionError
from .redact import redact
from .routing import SERVICE_DESK, route
from .settings import retry_command, settings_fingerprint
from .validate import validate_reply

RENDER_EVERY = 25


def input_files(input_dir):
    return sorted(input_dir.glob("*.json"))


def decide(current, source_sha256, fingerprint, policy_version, force):
    """Return "extract", "reroute" or "reuse" for one document."""
    if force or current is None or current["status"] == "error":
        return "extract"
    if current["source_sha256"] != source_sha256 or current["settings_fingerprint"] != fingerprint:
        return "extract"
    if current["policy_version"] != policy_version:
        return "reroute"
    return "reuse"


def run_intake(files, store, settings, provider, schema, policy_version, configured_provider,
               force=frozenset()):
    """Process every file. Returns {document_id: action} where action is one of
    extracted, rerouted, reused, busy. `configured_provider` is the provider named in
    config/settings.json; it decides whether a retry command needs --provider."""
    fingerprint = settings_fingerprint(settings, schema)
    outcomes = {}
    finished = 0
    pool = ThreadPoolExecutor(max_workers=settings.workers)
    try:
        futures = [
            pool.submit(_process, path, store, settings, provider, schema, fingerprint,
                        policy_version, configured_provider, path.name in force)
            for path in files
        ]
        for future in as_completed(futures):
            document_id, action = future.result()
            outcomes[document_id] = action
            finished += 1
            if finished % RENDER_EVERY == 0:
                store.render()
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        store.render()
    return outcomes


def _process(path, store, settings, provider, schema, fingerprint, policy_version,
             configured_provider, force):
    document_id = path.name
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    current = store.load_current(document_id)
    if decide(current, sha, fingerprint, policy_version, force) == "reuse":
        return document_id, "reused"

    with store.claim(document_id) as owned:
        if not owned:
            return document_id, "busy"
        current = store.load_current(document_id)
        action = decide(current, sha, fingerprint, policy_version, force)
        if action == "reuse":
            return document_id, "reused"
        base = _base_record(document_id, sha, fingerprint, policy_version, provider)
        if action == "reroute":
            record = _rerouted_record(base, current, raw)
            store.save_attempt(record)
            return document_id, "rerouted"
        store.save_attempt(_extract_record(base, raw, provider, schema, configured_provider))
        return document_id, "extracted"


def _base_record(document_id, sha, fingerprint, policy_version, provider):
    return {
        "document_id": document_id,
        "source_sha256": sha,
        "extraction": None,
        "status": "error",
        "owner": SERVICE_DESK,
        "next_action": "retry-extraction",
        "error": None,
        "attempt": None,
        "attempted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider.name,
        "model": provider.model,
        "settings_fingerprint": fingerprint,
        "policy_version": policy_version,
        "routing_signals": [],
        "rerouted_from_attempt": None,
        "last_valid": None,
    }


def _extract_record(record, raw, provider, schema, configured_provider):
    document_id = record["document_id"]
    try:
        message = read_message(raw)
        extraction = validate_reply(provider.extract(document_id, message), message, schema)
    except ExtractionError as exc:
        return _failed(record, exc.code, redact(exc.message), configured_provider)
    except Exception as exc:  # provider or SDK failure of any kind
        return _failed(record, "provider-error", f"{type(exc).__name__}: {redact(str(exc))}",
                       configured_provider)
    return _routed(record, extraction, message)


def _rerouted_record(record, current, raw):
    record["rerouted_from_attempt"] = current["attempt"]
    for key in ("provider", "model", "settings_fingerprint"):
        record[key] = current[key]
    return _routed(record, current["extraction"], read_message(raw))


def _routed(record, extraction, message):
    decision = route(extraction, record["document_id"], message)
    record.update(
        extraction=extraction,
        status=decision.status,
        owner=decision.owner,
        next_action=decision.next_action,
        routing_signals=list(decision.signals),
    )
    return record


def _failed(record, code, message, configured_provider):
    record["error"] = {
        "code": code,
        "message": message,
        "retry_command": retry_command(record["document_id"], record["provider"], configured_provider),
    }
    return record


def read_message(raw):
    try:
        message = json.loads(raw.decode("utf-8"))["message"]
    except (UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        raise ExtractionError("invalid-input", f"Cannot read the message from the file: {exc}")
    if not isinstance(message, str):
        raise ExtractionError("invalid-input", "The message field is not a string.")
    return message

