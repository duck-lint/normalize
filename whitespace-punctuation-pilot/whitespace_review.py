#!/usr/bin/env python3
"""Prepare and authorize a punctuation/whitespace-only review, independent of OCR detection.

Reads a Normalize probe JSON report (v2/v3). Does not run OCR, spellcheck,
or change detection rules. Codex receives ONLY the filtered review batch.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys

KIND = "normalize.whitespace_review_batch"
ALLOWED_TRIGGERS = {"punctuation_letter", "period_capital"}
PUNCTUATION_LETTER = re.compile(r"([,;:!?])(?=[A-Za-z])")
PERIOD_CAPITAL = re.compile(r"\.(?=[A-Z])")


def checksum(raw):
    return hashlib.sha256(raw).hexdigest()


def load_json(path):
    return json.loads(path.read_bytes())


def write_new_json(path, value):
    if path.exists():
        raise ValueError(f"Output already exists; refusing overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def get_triggers(finding):
    triggers = finding.get("triggers")
    if triggers is None:
        triggers = [finding["rule"]]
    if not isinstance(triggers, list) or not triggers or any(not isinstance(t, str) for t in triggers):
        raise ValueError(f"Invalid trigger list on {finding.get('id')}")
    return triggers


def proposal(observed):
    """Return a whitespace-only proposal; never alter the original characters."""
    result = PUNCTUATION_LETTER.sub(r"\1 ", observed)
    result = PERIOD_CAPITAL.sub(". ", result)
    return result if result != observed else None


def is_insert_spaces_only(before, after):
    """True iff `after` is `before` with >=1 ASCII spaces inserted."""
    i = 0
    inserted = 0
    for char in after:
        if i < len(before) and char == before[i]:
            i += 1
        elif char == " ":
            inserted += 1
        else:
            return False
    return i == len(before) and inserted > 0


def project(report, source_sha256):
    """Select only punctuation/period-triggered findings; no lexical findings included."""
    selected = []
    seen_ids = set()
    for finding in report["findings"]:
        fid = finding["id"]
        if fid in seen_ids:
            raise ValueError(f"Duplicate finding ID in original report: {fid}")
        seen_ids.add(fid)
        triggers = get_triggers(finding)
        if not set(triggers) <= ALLOWED_TRIGGERS:
            continue
        # A punctuation-only trigger is not sufficient unless we can propose a
        # reversible insert-spaces-only transformation for its complete span.
        observed = finding.get("observed")
        if not isinstance(observed, str):
            raise ValueError(f"Non-text observed value: {fid}")
        proposed = proposal(observed)
        if proposed is None or not is_insert_spaces_only(observed, proposed):
            raise ValueError(f"Punctuation-only finding has no safe space proposal: {fid}")
        if finding.get("proposed") is not None and finding["proposed"] != proposed:
            raise ValueError(f"Existing proposed text contradicts deterministic proposal: {fid}")
        if finding.get("proposal_source") not in (None, "deterministic_whitespace"):
            raise ValueError(f"Unexpected proposal source: {fid}")
        start, end = finding.get("start_byte"), finding.get("end_byte")
        if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool) or start >= end or start < 0:
            raise ValueError(f"Invalid replacement offsets: {fid}")
        if end - start != len(observed.encode("utf-8")):
            raise ValueError(f"Span length does not equal original UTF-8 bytes: {fid}")
        for key in ("page", "source_image", "paddle_markdown"):
            if not isinstance(finding.get(key), str) or not finding[key]:
                raise ValueError(f"Missing {key} for {fid}")
        selected.append({
            "id": fid,
            "page": finding["page"],
            "source_image": finding["source_image"],
            "paddle_markdown": finding["paddle_markdown"],
            "start_byte": start,
            "end_byte": end,
            "observed": observed,
            "proposed": proposed,
            "triggers": triggers,
        })
    return {
        "kind": KIND,
        "version": 1,
        "source_report_sha256": source_sha256,
        "candidate_count": len(selected),
        "page_count": len({f["page"] for f in selected}),
        "findings": selected,
    }


def prepare(args):
    raw = args.report.read_bytes()
    output = project(json.loads(raw), checksum(raw))
    write_new_json(args.out, output)
    print(f"Prepared {output['candidate_count']} whitespace proposals on {output['page_count']} pages; only these findings are in the handoff.")
    print(f"Wrote: {args.out}")


def parse_exceptions(exceptions, batch):
    if not isinstance(exceptions, dict):
        raise ValueError("Exception report must be a JSON object")
    checked = exceptions.get("checked_pages")
    if not isinstance(checked, list) or any(not isinstance(p, str) for p in checked) or len(set(checked)) != len(checked):
        raise ValueError("checked_pages must be a list of unique page strings")
    candidates = {f["id"]: f for f in batch["findings"]}
    candidate_pages = {f["page"] for f in batch["findings"]}
    if not set(checked) <= candidate_pages:
        raise ValueError("checked_pages includes pages not in the whitespace batch")
    listed = exceptions.get("exceptions")
    if not isinstance(listed, list):
        raise ValueError("exceptions must be a list; use [] when none are found")
    objections = {}
    for entry in listed:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError("Each exception requires an id")
        fid = entry["id"]
        if fid not in candidates or fid in objections:
            raise ValueError(f"Unknown or repeated exception id: {fid}")
        reason = entry.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"Exception requires a nonempty reason: {fid}")
        objections[fid] = reason
    return set(checked), objections


def authorize(args):
    raw = args.report.read_bytes()
    report = json.loads(raw)
    # Recompute the handoff from the original detector output, byte-for-byte;
    # reject a modified/substituted batch before authorizing anything.
    expected_batch = project(report, checksum(raw))
    supplied_batch = load_json(args.batch)
    if supplied_batch != expected_batch:
        raise ValueError("Whitespace handoff differs from the source report projection")
    checked, objections = parse_exceptions(load_json(args.exceptions), supplied_batch)
    if args.require_complete and len(checked) != expected_batch["page_count"]:
        missing = expected_batch["page_count"] - len(checked)
        raise ValueError(f"Codex exception report omits {missing} pages; cannot authorize complete batch")

    # Preserve all original findings and ordering. Only edit proposal/status on
    # uncontested, fully checked punctuation-only findings. No lexical change.
    eligible = {f["id"]: f for f in expected_batch["findings"]}
    output = copy.deepcopy(report)
    authorized = 0
    untouched = 0
    for finding in output["findings"]:
        candidate = eligible.get(finding["id"])
        if candidate is None or candidate["page"] not in checked or candidate["id"] in objections:
            untouched += 1
            continue
        if finding.get("review", {}).get("status") is not None:
            raise ValueError(f"Refusing to overwrite an existing review decision: {finding['id']}")
        if finding["review"].get("replacement") is not None:
            raise ValueError(f"Refusing to override a human replacement: {finding['id']}")
        finding["proposed"] = candidate["proposed"]
        finding["review"]["status"] = "approved"
        authorized += 1

    print(f"Codex reported {len(checked)}/{expected_batch['page_count']} checked pages and {len(objections)} exceptions.")
    print(f"Uncontested proposals eligible for human batch approval: {authorized}; untouched findings: {untouched}.")
    if not args.approve_uncontested:
        print("DRY RUN ONLY. Nothing written. Pass --approve-uncontested to explicitly authorize these proposals.")
        return
    write_new_json(args.out, output)
    print(f"Human-authorized reviewed report: {args.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="Create narrow Codex handoff from an existing full probe report")
    p.add_argument("--report", required=True, type=Path, help="Untouched full probe report JSON")
    p.add_argument("--out", required=True, type=Path, help="New whitespace-only handoff JSON")
    p.set_defaults(function=prepare)
    a = sub.add_parser("authorize", help="Dry-run or authorize uncontested changes back into full report")
    a.add_argument("--report", required=True, type=Path, help="Same untouched full probe report JSON")
    a.add_argument("--batch", required=True, type=Path, help="Original whitespace-only handoff JSON")
    a.add_argument("--exceptions", required=True, type=Path, help="Codex-generated exception report JSON")
    a.add_argument("--out", required=True, type=Path, help="New full reviewed report JSON")
    a.add_argument("--require-complete", action="store_true", help="Reject if any candidate page is unchecked")
    a.add_argument("--approve-uncontested", action="store_true", help="Explicit human batch authorization; otherwise dry run")
    a.set_defaults(function=authorize)
    args = ap.parse_args()
    try:
        args.function(args)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        ap.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
