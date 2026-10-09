#!/usr/bin/env python3
"""Apply approved punctuation-space proposals from the edited second report.

The human runs this command. Without --execute it validates and previews only.
Raw Paddle files and all three reports remain unchanged.
"""
import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

from extract_whitespace import extract
from normalize_probe import whitespace_proposal


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_relative(member):
    path = PurePosixPath(member)
    if not member or path.is_absolute() or ".." in path.parts or "\\" in member:
        raise ValueError(f"Unsafe ZIP member path: {member!r}")
    return Path(*path.parts)


def check_against_baseline(report, baseline):
    """Permit only status/note edits to the exact subset copied from report one."""
    expected = extract(baseline)
    comparable = copy.deepcopy(report)
    if len(comparable["findings"]) != len(expected["findings"]):
        raise ValueError("Reviewed report added or removed findings")
    for original, reviewed in zip(expected["findings"], comparable["findings"]):
        review = reviewed["review"]
        if review["status"] is not None and not isinstance(review["status"], str):
            raise ValueError(f"Invalid review.status: {reviewed['id']}")
        if review["note"] is not None and not isinstance(review["note"], str):
            raise ValueError(f"Invalid review.note: {reviewed['id']}")
        review["status"] = original["review"]["status"]
        review["note"] = original["review"]["note"]
    if comparable != expected:
        raise ValueError("Only review.status and review.note may change in report two")


def build(report, paddle_zip):
    if digest(paddle_zip.read_bytes()) != report["inputs"]["paddle_zip_sha256"]:
        raise ValueError("Paddle ZIP differs from the probe input")
    with zipfile.ZipFile(paddle_zip) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError("Duplicate ZIP member paths")
        raw_pages = {name: archive.read(name) for name in names if name.endswith(".md")}

    edits = defaultdict(list)
    seen_ids = set()
    for finding in report["findings"]:
        fid = finding["id"]
        if fid in seen_ids:
            raise ValueError(f"Duplicate finding ID: {fid}")
        seen_ids.add(fid)
        # No exceptions report, inferred approval, or replacement override is
        # authority to edit. Only this explicit status enables the proposal.
        if finding["review"]["status"] != "approved":
            continue
        path = finding["paddle_markdown"]
        if path not in raw_pages:
            raise ValueError(f"Approved finding has no Markdown page: {fid}")
        original = raw_pages[path]
        if digest(original) != finding["source_md_sha256"]:
            raise ValueError(f"Markdown hash mismatch: {fid}")
        start, end = finding["start_byte"], finding["end_byte"]
        if not (type(start) is int and type(end) is int and 0 <= start < end <= len(original)):
            raise ValueError(f"Invalid byte range: {fid}")
        observed, proposed = finding["observed"], finding["proposed"]
        if not isinstance(observed, str) or not isinstance(proposed, str):
            raise ValueError(f"Missing text proposal: {fid}")
        if original[start:end] != observed.encode("utf-8"):
            raise ValueError(f"Observed bytes do not match: {fid}")
        if proposed != whitespace_proposal(observed, finding["triggers"]):
            raise ValueError(f"Not the deterministic punctuation-space proposal: {fid}")
        edits[path].append((start, end, proposed.encode("utf-8"), fid))

    derived = dict(raw_pages)
    records = []
    for path, page_edits in sorted(edits.items()):
        ordered = sorted(page_edits)
        for left, right in zip(ordered, ordered[1:]):
            if left[1] > right[0]:
                raise ValueError(f"Overlapping approved findings: {left[3]} and {right[3]}")
        # Offsets refer to raw UTF-8 bytes. Work right-to-left so earlier offsets
        # stay valid even when multiple insertions change the same page.
        for start, end, replacement, fid in reversed(ordered):
            derived[path] = derived[path][:start] + replacement + derived[path][end:]
            records.append({"id": fid, "paddle_markdown": path,
                            "start_byte": start, "end_byte": end,
                            "observed": raw_pages[path][start:end].decode("utf-8"),
                            "proposed": replacement.decode("utf-8")})
    summary = {"approved_findings": len(records),
               "page_count": len(raw_pages),
               "changed_pages": sum(derived[path] != raw_pages[path] for path in raw_pages),
               "changes": sorted(records, key=lambda item: (item["paddle_markdown"], item["start_byte"]))}
    return derived, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path, help="Untouched full probe report (report one)")
    parser.add_argument("--report", required=True, type=Path, help="Whitespace report edited by Codex (report two)")
    parser.add_argument("--paddle", required=True, type=Path, help="Original Paddle ZIP")
    parser.add_argument("--out", required=True, type=Path, help="New derived Markdown directory")
    parser.add_argument("--execute", action="store_true", help="Write the validated derived pages")
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_bytes())
        baseline = json.loads(args.baseline.read_bytes())
        check_against_baseline(report, baseline)
        derived, summary = build(report, args.paddle)
        print(f"Validated {summary['page_count']} pages; {summary['approved_findings']} approved "
              f"proposals; {summary['changed_pages']} pages would change.")
        if not args.execute:
            print("Dry run; pass --execute to write derived Markdown.")
            return
        if args.out.exists():
            raise ValueError(f"Output already exists: {args.out}")
        for member in derived:
            safe_relative(member)
        args.out.mkdir(parents=True)
        for member, content in sorted(derived.items()):
            destination = args.out / safe_relative(member)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        (args.out / "execution_report.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote: {args.out}")
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
