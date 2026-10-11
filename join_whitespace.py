#!/usr/bin/env python3
"""Join scan-reviewed whitespace batches into the unchanged executor report contract.

Workers may alter only review.status and review.note. The joined report is
rebuilt from the untouched Probe 1; no worker-authored source data is reused.
"""
import argparse
import copy
import json
from pathlib import Path

from execute_repairs import check_against_baseline
from extract_whitespace import extract


def join(baseline, original, batches):
    expected = extract(baseline)
    if original != expected:
        raise ValueError("Extracted whitespace report is not the untouched Probe 1 subset")
    if not batches:
        raise ValueError("No batch review reports supplied")

    source = expected["findings"]
    ids = [finding["id"] for finding in source]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate finding ID in extracted report")
    originals = {finding["id"]: finding for finding in source}
    positions = {fid: i for i, fid in enumerate(ids)}
    decisions = {}

    for name, batch in batches:
        if (not isinstance(batch, dict) or set(batch) != set(original)
                or batch["inputs"] != expected["inputs"]
                or not isinstance(batch["findings"], list)
                or not batch["findings"]):
            raise ValueError(f"Malformed or empty batch report: {name}")
        last_position = -1
        for finding in batch["findings"]:
            if not isinstance(finding, dict) or not isinstance(finding.get("id"), str):
                raise ValueError(f"Malformed finding in {name}")
            fid = finding["id"]
            if fid not in originals:
                raise ValueError(f"Unknown finding in {name}: {fid}")
            if fid in decisions:
                raise ValueError(f"Duplicate finding across batches: {fid}")
            if positions[fid] <= last_position:
                raise ValueError(f"Batch finding order changed: {name}")
            last_position = positions[fid]
            review = finding.get("review")
            if not isinstance(review, dict) or set(review) != {"status", "note"}:
                raise ValueError(f"Invalid review fields: {fid}")
            status, note = review["status"], review["note"]
            if status not in (None, "approved") or (note is not None and not isinstance(note, str)):
                raise ValueError(f"Invalid review decision: {fid}")
            if status is None and (note is None or not note.strip()):
                raise ValueError(f"Unreviewed finding in completed batch: {fid}")
            comparable = copy.deepcopy(finding)
            comparable["review"] = copy.deepcopy(originals[fid]["review"])
            if comparable != originals[fid]:
                raise ValueError(f"Unauthorized change to finding: {fid}")
            decisions[fid] = copy.deepcopy(review)

    missing = [fid for fid in ids if fid not in decisions]
    if missing:
        raise ValueError(f"Missing {len(missing)} original findings; first: {missing[0]}")

    merged = copy.deepcopy(expected)
    for finding in merged["findings"]:
        finding["review"] = decisions[finding["id"]]
    check_against_baseline(merged, baseline)
    exceptions = {"findings": [copy.deepcopy(f) for f in merged["findings"]
                               if f["review"]["status"] != "approved"]}
    return merged, exceptions


def read_json(path):
    return json.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True,
                        help="Untouched full Probe 1 report")
    parser.add_argument("--report", type=Path, required=True,
                        help="Untouched extracted whitespace report")
    parser.add_argument("--batches", type=Path, required=True,
                        help="Directory containing only completed agent JSON outputs")
    parser.add_argument("--out", type=Path, required=True,
                        help="New complete executor-compatible reviewed report")
    parser.add_argument("--exceptions-out", type=Path, required=True,
                        help="New informational non-approved findings report")
    args = parser.parse_args()
    try:
        if args.out.resolve() == args.exceptions_out.resolve():
            raise ValueError("Reviewed and exceptions output paths must differ")
        if args.out.exists() or args.exceptions_out.exists():
            raise ValueError("Output already exists; refusing to overwrite")
        if not args.batches.is_dir():
            raise ValueError("Batch output directory does not exist")
        paths = sorted(args.batches.iterdir())
        if not paths or any(not p.is_file() or p.suffix.lower() != ".json" for p in paths):
            raise ValueError("Batch output directory must contain only JSON files")
        baseline = read_json(args.baseline)
        original = read_json(args.report)
        merged, exceptions = join(baseline, original, [(p.name, read_json(p)) for p in paths])

        # All report-level validation completes before either output is published.
        contents = [(args.out, merged), (args.exceptions_out, exceptions)]
        created = []
        try:
            for path, content in contents:
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("x", encoding="utf-8", newline="\n") as stream:
                    created.append(path)
                    json.dump(content, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
        except (OSError, ValueError, TypeError):
            for path in created:
                path.unlink(missing_ok=True)
            raise
        approvals = sum(f["review"]["status"] == "approved" for f in merged["findings"])
        print(f"Joined {len(paths)} batches: {len(merged['findings'])} findings, "
              f"{approvals} approved, {len(exceptions['findings'])} exceptions")
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
