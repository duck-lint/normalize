#!/usr/bin/env python3
"""Join completed parallel lexical proposal and verification batches in one pass.

Both review teams finish first. Rebuild both full executor-ready handoffs
from frozen sources, never by concatenating agent-authored reports.
"""
import argparse
import copy
import json
import os
import tempfile
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
                    changed = sorted(
                        key for key in set(comparable) | set(original_finding)
                        if comparable.get(key) != original_finding.get(key)
                    )
                    raise ValueError(
                        f"Unauthorized verification-stage edit: {fid}; "
                        f"batch={filename}; changed_fields={','.join(changed)}"
                    )
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


def join_all(baseline, extracted, proposal_batches, verification_batches):
    """Rebuild both reports and verify the whole two-stage handoff together."""
    proposals = join("proposals", baseline, extracted, proposal_batches)
    reviewed = join("reviewed", baseline, proposals, verification_batches)
    validate_handoffs(baseline, proposals, reviewed)
    return proposals, reviewed


def load_batches(directory):
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError(f"Batch output directory is missing or not a directory: {directory}")
    paths = sorted(directory.iterdir())
    if not paths or any(path.is_symlink() or not path.is_file() or path.suffix.lower() != ".json"
                        for path in paths):
        raise ValueError(f"Batch output directory must contain only completed JSON files: {directory}")
    return [(path.name, read_json(path)) for path in paths]


def publish_pair(output_dir, proposals, reviewed):
    """Stage both fully validated reports and refuse existing output files."""
    targets = [output_dir / "lexical-proposals.json",
               output_dir / "lexical-reviewed.json"]
    if any(path.exists() or path.is_symlink() for path in targets):
        raise ValueError("Joined lexical output already exists; refusing to overwrite")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".lexical-join-", dir=output_dir) as directory:
        staged = []
        for target, report in zip(targets, (proposals, reviewed)):
            candidate = Path(directory) / target.name
            with candidate.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2)
                handle.write(chr(10))
            staged.append(candidate)
        created = []
        try:
            for candidate, target in zip(staged, targets):
                os.link(candidate, target)  # atomic no-clobber publication
                created.append(target)
        except OSError:
            for target in created:
                target.unlink(missing_ok=True)
            raise
    return targets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path,
                        help="Untouched full lexical Probe 2")
    parser.add_argument("--extracted", required=True, type=Path,
                        help="Untouched lexical-extracted.json")
    parser.add_argument("--proposal-batches", required=True, type=Path,
                        help="Directory containing only completed proposal-agent JSON files")
    parser.add_argument("--verification-batches", required=True, type=Path,
                        help="Directory containing only completed verifier-agent JSON files")
    parser.add_argument("--out-dir", required=True, type=Path,
                        help="Directory for new lexical-proposals.json and lexical-reviewed.json")
    args = parser.parse_args()
    try:
        proposal_root = args.proposal_batches.resolve()
        verification_root = args.verification_batches.resolve()
        output_root = args.out_dir.resolve()
        if proposal_root == verification_root:
            raise ValueError("Proposal and verification batch directories must differ")
        if (output_root.is_relative_to(proposal_root)
                or output_root.is_relative_to(verification_root)):
            raise ValueError("Joined outputs must be outside both batch directories")

        baseline = read_json(args.baseline)
        extracted = read_json(args.extracted)
        proposal_batches = load_batches(args.proposal_batches)
        verification_batches = load_batches(args.verification_batches)
        proposals, reviewed = join_all(baseline, extracted,
                                        proposal_batches, verification_batches)
        targets = publish_pair(args.out_dir, proposals, reviewed)
        count = len(proposals["findings"])
        proposed_count = sum(f["proposed"] is not None for f in proposals["findings"])
        approved_count = sum(f["review"]["status"] == "approved"
                             for f in reviewed["findings"])
        print(f"Joined {len(proposal_batches)} proposer and "
              f"{len(verification_batches)} verifier batches: {count} findings, "
              f"{proposed_count} proposed replacements, {approved_count} approved")
        print(f"Wrote: {targets[0]}")
        print(f"Wrote: {targets[1]}")
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"ERROR: {exc}\\n")


if __name__ == "__main__":
    main()
