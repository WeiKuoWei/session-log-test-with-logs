"""Compare current extractions with the hand-written expected facts and write accuracy.md."""

import json
from collections import Counter

from .runner import read_message

FIELDS = ("request_id", "request_date", "kind", "requester", "team", "system", "environment",
          "permission", "start_date", "end_date", "manager")


def measure(paths, store, paraphrase_store):
    """Return the measurements for every document in expected_fields.json. The paraphrase is
    read from its own store, so it never appears in the queue."""
    expected = json.loads(paths.expected_file.read_text(encoding="utf-8"))
    expected.pop("_about", None)
    paraphrase_names = {p.name for p in paths.paraphrase_dir.glob("*.json")}
    docs = []
    for name in sorted(expected):
        source = paths.paraphrase_dir if name in paraphrase_names else paths.input_dir
        record = (paraphrase_store if name in paraphrase_names else store).load_current(name)
        docs.append({
            "name": name,
            "paraphrase": name in paraphrase_names,
            "expected": expected[name],
            "record": record,
            "message": read_message((source / name).read_bytes()),
        })
    result = {"documents": docs}
    result["exact"] = _measure_exact(docs)
    result["purpose"] = _measure_purpose(docs)
    result["quotes"] = _measure_quotes(docs)
    result["null_fields"] = _measure_null_fields(docs)
    result["routes"] = _measure_routes(docs)
    return result


def _extraction(doc):
    return doc["record"]["extraction"] if doc["record"] else None


def _no_extraction_reason(doc):
    record = doc["record"]
    if record is None:
        return "no current result"
    return f"error {record['error']['code']}" if record["error"] else "no extraction"


def _measure_exact(docs):
    mismatches = []
    for doc in docs:
        extraction = _extraction(doc)
        for field in FIELDS:
            want = doc["expected"]["fields"][field]
            if extraction is None:
                mismatches.append(_mismatch(doc, field, want, _no_extraction_reason(doc), "no extraction"))
                continue
            got = extraction[field]
            if got != want:
                kind = "invented value" if want is None else "missing value" if got is None else "wrong value"
                mismatches.append(_mismatch(doc, field, want, got, kind))
    total = len(docs) * len(FIELDS)
    return {"matched": total - len(mismatches), "total": total, "mismatches": mismatches}


def _mismatch(doc, field, want, got, kind):
    return {"document": doc["name"], "field": field, "expected": want, "got": got, "kind": kind}


def _normalise(text):
    return " ".join(text.split())


def _measure_purpose(docs):
    failures = []
    for doc in docs:
        extraction = _extraction(doc)
        present = doc["expected"]["business_purpose"] == "present"
        got = extraction["business_purpose"] if extraction else None
        if extraction is None:
            reason = _no_extraction_reason(doc)
        elif present and not got:
            reason = "expected a purpose, got null"
        elif present and _normalise(got) not in _normalise(doc["message"]):
            reason = "purpose is not found in the message"
        elif not present and got is not None:
            reason = "expected null, got a purpose"
        else:
            continue
        failures.append({"document": doc["name"], "expected": doc["expected"]["business_purpose"],
                         "got": got, "reason": reason})
    return {
        "present": _purpose_tally(docs, failures, "present"),
        "absent": _purpose_tally(docs, failures, "absent"),
        "failures": failures,
    }


def _purpose_tally(docs, failures, expected):
    total = sum(d["expected"]["business_purpose"] == expected for d in docs)
    failed = sum(f["expected"] == expected for f in failures)
    return {"passed": total - failed, "total": total}


def _measure_quotes(docs):
    total, missing = 0, []
    for doc in docs:
        extraction = _extraction(doc)
        for quote in (extraction["supporting_quotes"] if extraction else []):
            total += 1
            if quote not in doc["message"]:
                missing.append({"document": doc["name"], "quote": quote})
    return {"total": total, "not_in_message": missing}


def _expected_null_fields(doc):
    fields = [f for f in FIELDS if doc["expected"]["fields"][f] is None]
    if doc["expected"]["business_purpose"] == "absent":
        fields.append("business_purpose")
    return fields


def _measure_null_fields(docs):
    total, without_issue = 0, []
    for doc in docs:
        extraction = _extraction(doc)
        issues = [i.lower() for i in (extraction["issues"] if extraction else [])]
        for field in _expected_null_fields(doc):
            total += 1
            names = (field, field.replace("_", " "))
            if not any(n in issue for issue in issues for n in names):
                without_issue.append({"document": doc["name"], "field": field})
    return {"total": total, "without_issue": without_issue}


def _measure_routes(docs):
    rows = []
    for doc in docs:
        record = doc["record"]
        want = doc["expected"]["route"]
        got = ({"owner": record["owner"], "status": record["status"], "next_action": record["next_action"]}
               if record else None)
        rows.append({"document": doc["name"], "expected": want, "got": got, "match": got == want})
    return {"matched": sum(r["match"] for r in rows), "total": len(rows), "rows": rows}


# --- report -------------------------------------------------------------------


def summary_lines(result):
    exact, purpose, quotes = result["exact"], result["purpose"], result["quotes"]
    nulls, routes = result["null_fields"], result["routes"]
    return [
        f"exact-match fields: {exact['matched']}/{exact['total']}",
        f"business_purpose present and found in the message: "
        f"{purpose['present']['passed']}/{purpose['present']['total']}",
        f"business_purpose null where no purpose is expected: "
        f"{purpose['absent']['passed']}/{purpose['absent']['total']}",
        f"supporting quotes not found in the message: {len(quotes['not_in_message'])} of {quotes['total']}",
        f"expected-null fields with no issue: {len(nulls['without_issue'])} of {nulls['total']}",
        f"route matches: {routes['matched']}/{routes['total']}",
    ]


def render_report(result, settings, policy, mock_labels):
    docs = result["documents"]
    records = [d["record"] for d in docs if d["record"]]
    live = [r for r in records if r["provider"] != "mock"]
    out = ["# Accuracy", ""]
    out += ["## Result", "", "| Check | Result |", "|---|---|"]
    exact = result["exact"]
    out += [f"| 11 fields, exact string match, {len(docs)} documents | {exact['matched']}/{exact['total']} |"]
    for line in summary_lines(result)[1:]:
        name, value = line.rsplit(": ", 1)
        out.append(f"| {name} | {value} |")
    out += [""] + _source_section(records, live, mock_labels)
    out += _procedure_section(len(docs))
    out += _mismatch_section(result)
    out += _other_checks_section(result)
    out += _expected_section(docs)
    out += _configuration_section(records, settings, policy)
    return "\n".join(out) + "\n"


def _source_section(records, live, mock_labels):
    counts = Counter((r["provider"], r["model"]) for r in records)
    out = ["## Source of the results", "", "| Provider | Model | Documents |", "|---|---|---|"]
    out += [f"| {p} | {m} | {n} |" for (p, m), n in sorted(counts.items())]
    out.append("")
    if len(live) < len(records):
        out += ["Mocked results: canned replies in mock_replies/, one per document, authored by hand "
                "from the message text. No model produced them.", ""]
        if mock_labels:
            out.append("Injected errors (labelled `_deliberate_error` in the mock reply files):")
            out += [f"- {doc}: {label}" for doc, label in sorted(mock_labels.items())] + [""]
    if live:
        out.append(f"Live observation: {len(live)} documents were processed by a live provider; "
                   "see the provider and model columns above.")
    else:
        out.append("Live observation: none. No record in this file came from a live provider.")
    return out + [""]


def _procedure_section(doc_count):
    return [
        "## Procedure and counting rules", "",
        "1. Expected facts in expected/expected_fields.json were written by hand from the request "
        "messages and the office policy, and committed before any mock reply existed.",
        "2. Each document is read from its current record. The 20 supplied messages come from the "
        "queue's state; the paraphrase is processed into a separate store and is not in the queue.",
        f"3. Exact-match fields: request_id, request_date, kind, requester, team, system, environment, "
        f"permission, start_date, end_date, manager. Each is compared as an exact string with no "
        f"trimming or case folding. null equals null. null against a value is a mismatch. "
        f"Denominator: {doc_count} documents x 11 fields = {doc_count * 11}. A document with no "
        f"valid extraction counts all 11 fields as mismatches.",
        "4. business_purpose is free text and is not exact-matched. Where the expected file says a "
        "purpose is present, the extraction must have a non-null purpose that is a "
        "whitespace-normalised substring of the message. Where it says absent, the extraction must be null.",
        "5. Supporting quotes: each must be an exact substring of the decoded message. Counted across "
        "all documents with an extraction.",
        "6. Expected-null fields: every field expected to be null (the 11 fields, plus business_purpose "
        "where absent) must be explained by an issue that names the field. Counted per field.",
        "7. Route match: the record's owner, status and next_action must all equal the expected route "
        "derived from the policy.",
        "8. Factual-error reporting: a mismatch is classed as wrong value (a different value), "
        "invented value (a value where the message gives none or leaves it unresolved), missing value "
        "(null where the message states one), or no extraction. Wrong and invented values are "
        "factual errors; missing values are omissions.", "",
    ]


def _mismatch_section(result):
    mismatches = result["exact"]["mismatches"]
    kinds = Counter(m["kind"] for m in mismatches)
    out = ["## Mismatches", ""]
    if not mismatches:
        return out + ["None.", ""]
    out.append("Counts by class: " + ", ".join(f"{k} {n}" for k, n in sorted(kinds.items())) + ".")
    out += ["", "| Document | Field | Expected | Got | Class |", "|---|---|---|---|---|"]
    out += [f"| {m['document']} | {m['field']} | {_show(m['expected'])} | {_show(m['got'])} | {m['kind']} |"
            for m in mismatches]
    return out + [""]


def _other_checks_section(result):
    purpose, quotes = result["purpose"], result["quotes"]
    nulls, routes = result["null_fields"], result["routes"]
    out = ["## Other checks", "",
           f"business_purpose present and found in the message: "
           f"{purpose['present']['passed']}/{purpose['present']['total']}.",
           f"business_purpose null where no purpose is expected: "
           f"{purpose['absent']['passed']}/{purpose['absent']['total']}."]
    out += [f"- {f['document']}: {f['reason']}" for f in purpose["failures"]]
    out += ["", f"Supporting quotes not found in the message: {len(quotes['not_in_message'])} of {quotes['total']}."]
    out += [f"- {q['document']}: {q['quote']!r}" for q in quotes["not_in_message"]]
    out += ["", f"Expected-null fields with no issue naming them: {len(nulls['without_issue'])} of {nulls['total']}."]
    out += [f"- {n['document']}: {n['field']}" for n in nulls["without_issue"]]
    out += ["", f"Route matches: {routes['matched']}/{routes['total']}.", "",
            "| Document | Expected | Got | Match |", "|---|---|---|---|"]
    for row in routes["rows"]:
        out.append(f"| {row['document']} | {_route(row['expected'])} | {_route(row['got'])} | "
                   f"{'yes' if row['match'] else 'NO'} |")
    return out + [""]


def _expected_section(docs):
    out = ["## Expected fields", "",
           "Written from the messages. null = absent, unresolved, conflicting or relative in the message.", "",
           "| Document | " + " | ".join(FIELDS) + " | business_purpose |",
           "|---|" + "---|" * (len(FIELDS) + 1)]
    for doc in docs:
        cells = [_show(doc["expected"]["fields"][f]) for f in FIELDS]
        label = doc["name"] + (" (paraphrase)" if doc["paraphrase"] else "")
        out.append(f"| {label} | " + " | ".join(cells) + f" | {doc['expected']['business_purpose']} |")
    for doc in docs:
        if doc["paraphrase"]:
            out += ["", f"Paraphrase message ({doc['name']}, authored for this check, not in the queue):", "",
                    f"> {doc['message']}"]
    return out + [""]


def _configuration_section(records, settings, policy):
    out = ["## Model and configuration", "",
           f"- Configured provider: {settings.provider}; model: {settings.model}; "
           f"max_tokens: {settings.max_tokens}; tool_choice: forced single tool call "
           "(record_access_request); temperature: not sent (not a parameter of messages.create "
           "in anthropic 2.3.0).",
           f"- Policy version: {policy}."]
    prints = Counter((r["provider"], r["settings_fingerprint"][:12], r["policy_version"]) for r in records)
    out += [f"- Records: {n} produced by provider {p}, settings fingerprint {f}, policy version {v}."
            for (p, f, v), n in sorted(prints.items())]
    return out + [""]


def _show(value):
    return "null" if value is None else str(value).replace("|", "\\|")


def _route(route):
    return "none" if route is None else f"{route['owner']} / {route['status']} / {route['next_action']}"


def mock_labels(replies_dir):
    """Document -> label for every canned reply that carries a `_deliberate_error`."""
    labels = {}
    for path in sorted(replies_dir.glob("*.json")):
        canned = json.loads(path.read_text(encoding="utf-8"))
        if "_deliberate_error" in canned:
            labels[path.name] = canned["_deliberate_error"]
    return labels
