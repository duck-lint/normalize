#!/usr/bin/env python3
"""Apply approved punctuation-space proposals from the edited second report.

The human runs this command. Without --execute it validates and previews only.
Copies the full Paddle directory to a NEW output directory, then repairs only
the copied Markdown. Original artifacts and all three reports remain unchanged.
"""
import argparse
from collections import defaultdict
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

from artifact_directory import directory_files, directory_sha256
from extract_whitespace import extract
from whitespace_provenance import EXECUTION_FORMAT, whitespace_proposal


def digest(data):
    return hashlib.sha256(data).hexdigest()


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


def build(report, paddle_dir):
    files = directory_files(paddle_dir)
    if report["inputs"]["json_markdown_comparison"]["mode"] != "raw":
        raise ValueError("Whitespace execution requires a probe of raw Paddle output")
    if "execution_report.json" in files:
        raise ValueError("Whitespace execution requires raw Paddle output, not a prior execution")
    if directory_sha256(files) != report["inputs"]["paddle_dir_sha256"]:
        raise ValueError("Paddle directory differs from the probe input")
    raw_pages = {name: path.read_bytes() for name, path in files.items()
                 if name.lower().endswith(".md")}

    edits = defaultdict(list)
    approved_triggers = {}
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
        approved_triggers[fid] = finding["triggers"]

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
                            "proposed": replacement.decode("utf-8"),
                            "triggers": approved_triggers[fid],
                            "json_markdown_comparison": "reverse_executed_punctuation_spaces",
                            "source_md_sha256": digest(raw_pages[path])})
    for record in records:
        record["derived_md_sha256"] = digest(derived[record["paddle_markdown"]])
    summary = {"execution_format": EXECUTION_FORMAT,
               "source_dir_sha256": report["inputs"]["source_dir_sha256"],
               "source_paddle_dir_sha256": report["inputs"]["paddle_dir_sha256"],
               "artifact_policy": {"markdown": "derived; approved spaces applied",
                                   "json_and_other_files": "unchanged raw Paddle observations/assets"},
               "approved_findings": len(records),
               "page_count": len(raw_pages),
               "changed_pages": sum(derived[path] != raw_pages[path] for path in raw_pages),
               "changes": sorted(records, key=lambda item: (item["paddle_markdown"], item["start_byte"]))}
    return derived, summary


def validate_output_location(paddle_dir, out):
    if out.resolve().is_relative_to(paddle_dir.resolve()):
        raise ValueError("Output must be outside the original Paddle directory")
    if out.exists():
        raise ValueError(f"Output already exists: {out}")


def write_output(paddle_dir, out, derived, summary):
    """Publish a copied artifact directory only after validation and repair finish."""
    validate_output_location(paddle_dir, out)
    if "execution_report.json" in directory_files(paddle_dir):
        raise ValueError("Input already contains execution_report.json; use original Paddle output")
    out.parent.mkdir(parents=True, exist_ok=True)
    # Stage outside the original directory. A failed copy/check/repair cannot
    # publish a partial result as the requested output or modify the source.
    with tempfile.TemporaryDirectory(prefix=f".{out.name}-", dir=out.parent) as temporary:
        staged = Path(temporary) / "artifacts"
        shutil.copytree(paddle_dir, staged)
        if directory_sha256(directory_files(staged)) != summary["source_paddle_dir_sha256"]:
            raise ValueError("Paddle input changed during copying; no repaired output published")
        for member, content in derived.items():
            destination = staged / member
            if destination.read_bytes() != content:
                destination.write_bytes(content)
        (staged / "execution_report.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        validate_output_location(paddle_dir, out)
        staged.rename(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path, help="Untouched report one; validates that only status/note changed in report two")
    parser.add_argument("--report", required=True, type=Path, help="Whitespace report edited by Codex (report two)")
    parser.add_argument("--paddle", required=True, type=Path, help="Original Paddle output directory; read-only")
    parser.add_argument("--out", required=True, type=Path, help="New full Paddle copy; only its Markdown is repaired")
    parser.add_argument("--execute", action="store_true", help="Write the validated derived pages")
    args = parser.parse_args()
    try:
        validate_output_location(args.paddle, args.out)
        report_bytes = args.report.read_bytes()
        baseline_bytes = args.baseline.read_bytes()
        report = json.loads(report_bytes)
        baseline = json.loads(baseline_bytes)
        check_against_baseline(report, baseline)
        derived, summary = build(report, args.paddle)
        summary["source_report_sha256"] = digest(report_bytes)
        summary["source_baseline_sha256"] = digest(baseline_bytes)
        print(f"Validated {summary['page_count']} pages; {summary['approved_findings']} approved "
              f"proposals; {summary['changed_pages']} pages would change.")
        if not args.execute:
            print("Dry run; pass --execute to write derived Markdown.")
            return
        write_output(args.paddle, args.out, derived, summary)
        print(f"Wrote: {args.out}")
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
