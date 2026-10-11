#!/usr/bin/env python3
"""Join parallel lexical proposals or independent verification for the existing executor.

Source reports are frozen. Import only each stage's authorized finding fields;
rebuild the complete report in original order and validate executor handoffs.
"""
import argparse
import copy
import json
from pathlib import Path

from execute_lexical_repairs import validate_handoffs
from extract_lexical import extract

PROPOSAL_FIELDS = ("proposed", "proposal_source", "evidence",
                   "proposal_note", "lexicon_suggestion")
REVIEW_FIELDS = ("status", "note")


def join(stage, baseline, source, batches):
    if stage not in ("proposals", "reviewed"):
        raise ValueError(f"Unsupported lexical join stage: {stage}")

    expected = extract(baseline)
    if stage == "proposals":
        if source != expected:
            raise ValueError("Proposal source must be the untouched Probe 2 extraction")
    else:
        # The verifier starts from the already frozen, complete proposal artifact.
        validate_handoffs(baseline, source, source)

    if not batches:
        raise ValueError("No completed batch reports supplied")
    original = source["findings"]
    ids = [f["id"] for f in original]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate finding IDs in frozen source report")
    by_id = {f["id"]: f for f in original}
    positions = {fid: pos for pos, fid in enumerate(ids)}
    decisions = {}

    for filename, batch in batches:
        if (not isinstance(batch, dict) or set(batch) != set(source)
                or any(batch[key] != source[key] for key in source if key != "findings")
                or not isinstance(batch["findings"], list) or not batch["findings"]):
            raise ValueError(f"Invalid or empty lexical batch: {filename}")
        previous_position = -1
        for finding in batch["findings"]:
            if not isinstance(finding, dict) or not isinstance(finding.get("id"), str):
                raise ValueError(f"Malformed finding in {filename}")
            fid = finding["id"]
            if fid not in by_id:
                raise ValueError(f"Unknown finding in {filename}: {fid}")
            if fid in decisions:
                raise ValueError(f"Duplicate finding across batches: {fid}")
            if positions[fid] <= previous_position:
                raise ValueError(f"Finding order changed in {filename}")
            previous_position = positions[fid]
            original_finding = by_id[fid]
            comparable = copy.deepcopy(finding)

            if stage == "proposals":
                if any(field not in finding for field in PROPOSAL_FIELDS):
                    raise ValueError(f"Missing proposal field: {fid}")
                for field in PROPOSAL_FIELDS:
                    comparable[field] = original_finding[field]
                if comparable != original_finding:
                    raise ValueError(f"Unauthorized proposal-stage edit: {fid}")
                proposed = finding["proposed"]
                note = finding["proposal_note"]
                if proposed is None and (not isinstance(note, str) or not note.strip()):
                    raise ValueError(f"Unreviewed occurrence in completed proposal batch: {fid}")
                decisions[fid] = {field: copy.deepcopy(finding[field])
                                  for field in PROPOSAL_FIELDS}
            else:
                review = finding.get("review")
                if not isinstance(review, dict) or set(review) != set(REVIEW_FIELDS):
                    raise ValueError(f"Invalid verification fields: {fid}")
                if (review["status"] not in (None, "approved")
                        or not isinstance(review["note"], str)
                        or not review["note"].strip()):
                    raise ValueError(f"Unreviewed or invalid verification outcome: {fid}")
                comparable["review"] = copy.deepcopy(original_finding["review"])
                if comparable != original_finding:
                    raise ValueError(f"Unauthorized verification-stage edit: {fid}")
                decisions[fid] = copy.deepcopy(review)

    missing = [fid for fid in ids if fid not in decisions]
    if missing:
        raise ValueError(f"Missing {len(missing)} lexical findings; first: {missing[0]}")

    merged = copy.deepcopy(source)
    for finding in merged["findings"]:
        if stage == "proposals":
            finding.update(decisions[finding["id"]])
        else:
            finding["review"] = decisions[finding["id"]]

    if stage == "proposals":
        validate_handoffs(baseline, merged, merged)
    else:
        validate_handoffs(baseline, source, merged)
    return merged


def read_json(path):
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON object key: {key}")
            result[key] = value
        return result
    return json.loads(path.read_bytes(), object_pairs_hook=unique_keys)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("proposals", "reviewed"), required=True)
    parser.add_argument("--baseline", type=Path, required=True,
                        help="Untouched full lexical Probe 2")
    parser.add_argument("--source", type=Path, required=True,
                        help="Untouched lexical-extracted report (proposals) or frozen joined proposals (reviewed)")
    parser.add_argument("--batches", type=Path, required=True,
                        help="Directory containing only completed agent JSON outputs")
    parser.add_argument("--out", type=Path, required=True,
                        help="New full proposal or independently reviewed artifact")
    args = parser.parse_args()
    try:
        if args.out.exists() or args.out.is_symlink():
            raise ValueError("Output already exists; refusing to overwrite")
        if not args.batches.is_dir():
            raise ValueError("Batch output directory is missing")
        if args.out.resolve().is_relative_to(args.batches.resolve()):
            raise ValueError("Join output must be outside batch outputs directory")
        paths = sorted(args.batches.iterdir())
        if not paths or any(p.is_symlink() or not p.is_file() or p.suffix.lower() != ".json"
                            for p in paths):
            raise ValueError("Batch directory must contain only regular JSON output files")
        merged = join(args.stage, read_json(args.baseline), read_json(args.source),
                      [(path.name, read_json(path)) for path in paths])
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\\n") as stream:
            json.dump(merged, stream, ensure_ascii=False, indent=2)
            stream.write("\\n")
        if args.stage == "proposals":
            selected = sum(f["proposed"] is not None for f in merged["findings"])
            print(f"Joined {len(paths)} proposal batches: {len(merged['findings'])} findings, "
                  f"{selected} proposed replacements")
        else:
            selected = sum(f["review"]["status"] == "approved" for f in merged["findings"])
            print(f"Joined {len(paths)} verification batches: {len(merged['findings'])} findings, "
                  f"{selected} approved replacements")
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"ERROR: {exc}\\n")


if __name__ == "__main__":
    main()
