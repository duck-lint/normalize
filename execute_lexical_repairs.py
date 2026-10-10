#!/usr/bin/env python3
"""Execute explicitly scan-reviewed lexical replacements on a NEW derived snapshot.

Proposal and verification are separate immutable handoffs. A third, separately
human-authored admissions file may authorize persistent vocabulary updates.
No scan, raw Paddle artifact, prior derivative or prior ledger is modified.
"""
import argparse
from collections import defaultdict
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

from artifact_directory import directory_files, directory_sha256
from extract_lexical import extract
from lexicon_store import apply_human_admissions, read_lexicon, serialize
from lexical_provenance import EXECUTION_FORMAT, LEDGER
from whitespace_provenance import comparison_views as whitespace_comparison


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_handoffs(baseline, proposals, reviewed):
    """The proposer cannot change detection; verifier cannot change proposals."""
    expected = extract(baseline)
    if proposals.get("format") != "lexical_review_v1":
        raise ValueError("Unsupported proposal report")
    copy_proposals = copy.deepcopy(proposals)
    if len(copy_proposals.get("findings", [])) != len(expected["findings"]):
        raise ValueError("Proposal report added or omitted lexical findings")
    for original, edited in zip(expected["findings"], copy_proposals["findings"]):
        for field in ("proposed", "proposal_source", "evidence", "proposal_note", "lexicon_suggestion"):
            edited[field] = original[field]
    if copy_proposals != expected:
        raise ValueError("Proposer changed fields outside the authorized proposal slots")
    if len(reviewed.get("findings", [])) != len(proposals["findings"]):
        raise ValueError("Verifier added or removed findings")
    check_reviewed = copy.deepcopy(reviewed)
    for proposed, verified in zip(proposals["findings"], check_reviewed["findings"]):
        if (not isinstance(verified.get("review"), dict) or
                set(verified["review"]) != {"status", "note"}):
            raise ValueError("Malformed review decision")
        status, note = verified["review"]["status"], verified["review"]["note"]
        if status not in (None, "approved") or (note is not None and not isinstance(note, str)):
            raise ValueError("Unsupported lexical review status")
        verified["review"] = copy.deepcopy(proposed["review"])
    if check_reviewed != proposals:
        raise ValueError("Verifier changed fields outside review.status and review.note")
    for finding in proposals["findings"]:
        proposed = finding["proposed"]
        if proposed is not None:
            if (not isinstance(proposed, str) or proposed == finding["observed"]
                    or finding["proposal_source"] != "codex_scan_proposal"
                    or not isinstance(finding["evidence"], str)
                    or not finding["evidence"].strip()):
                raise ValueError(f"Invalid or unsubstantiated proposal: {finding['id']}")
        elif finding["proposal_source"] is not None:
            raise ValueError(f"Proposal source without replacement: {finding['id']}")
        if (finding["proposal_note"] is not None and not isinstance(finding["proposal_note"], str)):
            raise ValueError(f"Invalid proposal note: {finding['id']}")
        if finding["lexicon_suggestion"] not in (None, True, False):
            raise ValueError(f"Invalid lexical suggestion: {finding['id']}")
    for finding in reviewed["findings"]:
        if finding["review"]["status"] == "approved" and finding["proposed"] is None:
            raise ValueError(f"Approval without a replacement: {finding['id']}")


def validate_source(baseline, artifacts):
    if LEDGER in artifacts:
        raise ValueError("Lexical executor must receive the previous stage, not its own output")
    if "execution_report.json" not in artifacts:
        raise ValueError("Lexical stage requires a verified whitespace-repaired directory")
    if directory_sha256(artifacts) != baseline["inputs"]["paddle_dir_sha256"]:
        raise ValueError("Previous stage directory changed since the lexical probe")
    _, _, metadata = whitespace_comparison(artifacts, baseline["inputs"]["source_dir_sha256"])
    if metadata != baseline["inputs"]["json_markdown_comparison"]:
        raise ValueError("Lexical probe is not bound to this verified whitespace snapshot")
    if metadata["mode"] != "verified_executed_whitespace":
        raise ValueError("Unsupported lexical stage input")


def build(baseline, reviewed, artifacts, lexicon_hash, new_lexicon_hash, admitted):
    pages = {name: file.read_bytes() for name, file in artifacts.items()
             if name.lower().endswith(".md")}
    edits = defaultdict(list)
    records = []
    for finding in reviewed["findings"]:
        if finding["review"]["status"] != "approved":
            continue
        fid = finding["id"]
        path = finding["paddle_markdown"]
        if path not in pages:
            raise ValueError(f"No source Markdown page for approved repair: {fid}")
        original = pages[path]
        start, end = finding["start_byte"], finding["end_byte"]
        if (digest(original) != finding["source_md_sha256"]
                or type(start) is not int or type(end) is not int
                or start < 0 or end <= start or end > len(original)
                or original[start:end] != finding["observed"].encode("utf-8")):
            raise ValueError(f"Invalid source bytes or coordinates for approved repair: {fid}")
        replacement = finding["proposed"].encode("utf-8")
        edits[path].append((start, end, replacement, finding))

    derived = dict(pages)
    for path, page_edits in sorted(edits.items()):
        ordered = sorted(page_edits)
        for left, right in zip(ordered, ordered[1:]):
            if left[1] > right[0]:
                raise ValueError(f"Overlapping lexical repairs: {left[3]['id']} and {right[3]['id']}")
        for start, end, replacement, finding in reversed(ordered):
            derived[path] = derived[path][:start] + replacement + derived[path][end:]
            records.append({"id": finding["id"], "paddle_markdown": path,
                            "start_byte": start, "end_byte": end,
                            "observed": finding["observed"], "proposed": finding["proposed"],
                            "source_md_sha256": digest(pages[path])})
    for record in records:
        record["derived_md_sha256"] = digest(derived[record["paddle_markdown"]])
    records.sort(key=lambda entry: (entry["paddle_markdown"], entry["start_byte"]))
    summary = {"execution_format": EXECUTION_FORMAT,
               "source_dir_sha256": baseline["inputs"]["source_dir_sha256"],
               "source_artifact_dir_sha256": baseline["inputs"]["paddle_dir_sha256"],
               "source_lexicon_sha256": lexicon_hash,
               "target_lexicon_sha256": new_lexicon_hash,
               "human_approved_lexicon_entries": admitted,
               "artifact_policy": "Markdown derivative only; JSON/assets/previous ledger copied",
               "approved_findings": len(records),
               "page_count": len(pages),
               "changed_pages": sum(derived[p] != pages[p] for p in pages),
               "changes": records}
    return derived, summary


def validate_paths(source, out, lexicon):
    source = source.resolve()
    out = out.resolve()
    lexicon = lexicon.resolve()
    if (out.is_relative_to(source) or source.is_relative_to(out)
            or lexicon.is_relative_to(source) or lexicon.is_relative_to(out)):
        raise ValueError("Output, source artifacts, and shared lexicon must be independent paths")


def publish(source, out, derived, ledger):
    if out.exists():
        raise ValueError(f"Output already exists: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{out.name}-", dir=out.parent) as temp:
        staged = Path(temp) / "artifacts"
        shutil.copytree(source, staged)
        if directory_sha256(directory_files(staged)) != ledger["source_artifact_dir_sha256"]:
            raise ValueError("Source changed during copying; refused to publish")
        for path, data in derived.items():
            if staged.joinpath(path).read_bytes() != data:
                staged.joinpath(path).write_bytes(data)
        (staged / LEDGER).write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
        if out.exists():
            raise ValueError(f"Output appeared during staging: {out}")
        staged.rename(out)


def commit_lexicon(lexicon_path, expected_hash, target_bytes):
    if digest(lexicon_path.read_bytes()) == digest(target_bytes):
        return
    if digest(lexicon_path.read_bytes()) != expected_hash:
        raise ValueError("Shared lexicon changed since review; refusing stale admission")
    with tempfile.NamedTemporaryFile(dir=lexicon_path.parent,
                                     prefix=f".{lexicon_path.name}.",
                                     delete=False) as handle:
        staged = Path(handle.name)
        try:
            handle.write(target_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            staged.unlink(missing_ok=True)
            raise
    try:
        # Atomic file replacement after the derivative and its authorization
        # intent ledger are published. Resume handles failure between commits.
        os.replace(staged, lexicon_path)
    finally:
        staged.unlink(missing_ok=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline", type=Path, required=True, help="Untouched post-whitespace Probe 2")
    p.add_argument("--proposals", type=Path, required=True, help="Frozen output of proposer Codex session")
    p.add_argument("--reviewed", type=Path, required=True, help="Output of independent verifier session")
    p.add_argument("--paddle", type=Path, required=True, help="Verified whitespace-stage derivative")
    p.add_argument("--lexicon", type=Path, required=True, help="Persistent reviewed lexicon")
    p.add_argument("--lexicon-approvals", type=Path, help="Separate explicitly human-authored approvals")
    p.add_argument("--out", type=Path, required=True, help="New lexical-stage derivative")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--resume-lexicon", action="store_true", help="Recover a failed lexicon commit after derivative publication")
    args = p.parse_args()
    try:
        validate_paths(args.paddle, args.out, args.lexicon)
        baseline_raw = args.baseline.read_bytes()
        proposals_raw = args.proposals.read_bytes()
        reviewed_raw = args.reviewed.read_bytes()
        baseline, proposals, reviewed = map(json.loads, (baseline_raw, proposals_raw, reviewed_raw))
        validate_handoffs(baseline, proposals, reviewed)
        lexicon, lexicon_hash, _ = read_lexicon(args.lexicon)
        if baseline["inputs"].get("lexicon_sha256") != lexicon_hash:
            raise ValueError("Lexicon changed since probe; regenerate the lexical baseline")
        approvals_raw = args.lexicon_approvals.read_bytes() if args.lexicon_approvals else None
        approvals = json.loads(approvals_raw) if approvals_raw is not None else None
        updated, admissions = apply_human_admissions(
            lexicon, approvals, reviewed, baseline, digest(baseline_raw), lexicon_hash)
        target_bytes = serialize(updated)
        if args.resume_lexicon:
            if not args.execute or not args.out.is_dir():
                raise ValueError("Resume requires --execute and an existing lexical derivative")
            ledger = json.loads((args.out / LEDGER).read_bytes())
            if (ledger["source_lexicon_sha256"] != lexicon_hash or
                    ledger["target_lexicon_sha256"] != digest(target_bytes) or
                    ledger["source_baseline_sha256"] != digest(baseline_raw) or
                    ledger["source_proposals_sha256"] != digest(proposals_raw) or
                    ledger["source_reviewed_sha256"] != digest(reviewed_raw)):
                raise ValueError("Published lexical ledger does not match the supplied inputs")
            from lexical_provenance import comparison_views
            comparison_views(directory_files(args.out), baseline["inputs"]["source_dir_sha256"])
            commit_lexicon(args.lexicon, lexicon_hash, target_bytes)
            print("Recovered lexicon commit from verified published derivative")
            return
        if args.out.exists():
            raise ValueError(f"Output already exists: {args.out}")
        artifacts = directory_files(args.paddle)
        validate_source(baseline, artifacts)
        derived, ledger = build(baseline, reviewed, artifacts, lexicon_hash,
                                digest(target_bytes), admissions)
        ledger.update({"source_baseline_sha256": digest(baseline_raw),
                       "source_proposals_sha256": digest(proposals_raw),
                       "source_reviewed_sha256": digest(reviewed_raw),
                       "source_lexicon_approvals_sha256": digest(approvals_raw) if approvals_raw else None})
        print(f"Validated {ledger['page_count']} pages; {ledger['approved_findings']} repairs; "
              f"{len(admissions)} human-approved lexicon entries; {ledger['changed_pages']} changed pages")
        if not args.execute:
            print("Dry run only. Add --execute to publish derived artifacts and commit vocabulary.")
            return
        publish(args.paddle, args.out, derived, ledger)
        try:
            commit_lexicon(args.lexicon, lexicon_hash, target_bytes)
        except Exception:
            print("Derived output was published but shared lexicon update did not complete. "
                  "Recover with --execute --resume-lexicon.", flush=True)
            raise
        print(f"Published {args.out} and committed the approved lexicon additions")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        p.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
