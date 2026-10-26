"""File-backed records: one current file and an append-only history per document.

state/current/<stem>.json          latest attempt (replaced atomically)
state/history/<stem>/NNNN_<sha>.json  every attempt, never edited
state/claims/<stem>.lock           per-document flock held while one operator works on it
deliverables/extractions.jsonl, queue.json  rendered from state/current, never edited
"""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


def stem_of(document_id):
    return document_id.removesuffix(".json")


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class Store:
    def __init__(self, paths, scope=None):
        """`scope` names a separate store under state/ (the accuracy paraphrase), which renders
        into its own folder and never touches deliverables/."""
        self.paths = paths
        self.state_dir = paths.state_dir / scope if scope else paths.state_dir
        self.output_dir = self.state_dir / "rendered" if scope else paths.deliverables_dir
        self.current_dir = self.state_dir / "current"
        self.history_dir = self.state_dir / "history"
        self.claims_dir = self.state_dir / "claims"
        for directory in (self.current_dir, self.history_dir, self.claims_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def load_current(self, document_id):
        path = self.current_dir / f"{stem_of(document_id)}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def all_current(self):
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(self.current_dir.glob("*.json"))
        ]

    def history_files(self, document_id):
        return sorted((self.history_dir / stem_of(document_id)).glob("*.json"))

    def history(self, document_id):
        return [json.loads(p.read_text(encoding="utf-8")) for p in self.history_files(document_id)]

    @contextmanager
    def claim(self, document_id):
        """Yield True if this process now owns the document, False if another operator does.
        The lock belongs to the open file, so the OS releases it if the process dies."""
        handle = open(self.claims_dir / f"{stem_of(document_id)}.lock", "a")
        try:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            handle.close()

    def save_attempt(self, record):
        """Number the attempt, link an older valid result if this one failed, then write the
        immutable history file first and the current file second. Caller holds the claim."""
        document_id = record["document_id"]
        past = self.history(document_id)
        record["attempt"] = len(past) + 1
        if record["status"] == "error":
            record["last_valid"] = _last_valid(past, self.history_files(document_id))
        name = f"{record['attempt']:04d}_{record['source_sha256'][:12]}.json"
        text = json.dumps(record, indent=2, ensure_ascii=False) + "\n"
        atomic_write(self.history_dir / stem_of(document_id) / name, text)
        atomic_write(self.current_dir / f"{stem_of(document_id)}.json", text)
        return record

    def render(self):
        """Rebuild the two deliverable views from state/current under a global lock."""
        out = self.output_dir
        out.mkdir(parents=True, exist_ok=True)
        with open(self.state_dir / "render.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            records = self.all_current()
            lines = [json.dumps(r, ensure_ascii=False) for r in records]
            atomic_write(out / "extractions.jsonl", "".join(line + "\n" for line in lines))
            queue = {"entries": [_queue_entry(r) for r in records]}
            atomic_write(out / "queue.json", json.dumps(queue, indent=2, ensure_ascii=False) + "\n")


def _last_valid(past, files):
    for record, path in reversed(list(zip(past, files))):
        if record["status"] != "error":
            return {
                "attempt": record["attempt"],
                "source_sha256": record["source_sha256"],
                "settings_fingerprint": record["settings_fingerprint"],
                "status": record["status"],
                "owner": record["owner"],
                "next_action": record["next_action"],
                "history_file": f"{path.parent.name}/{path.name}",
            }
    return None


def _queue_entry(record):
    extraction = record["extraction"] or {}
    error = record["error"]
    return {
        "document_id": record["document_id"],
        "request_id": extraction.get("request_id"),
        "requester": extraction.get("requester"),
        "kind": extraction.get("kind"),
        "owner": record["owner"],
        "status": record["status"],
        "next_action": record["next_action"],
        "source_sha256": record["source_sha256"],
        "attempt": record["attempt"],
        "routing_signals": record["routing_signals"],
        "error": error["code"] if error else None,
        "last_valid": record["last_valid"],
    }
