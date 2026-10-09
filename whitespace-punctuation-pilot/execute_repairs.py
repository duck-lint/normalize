#!/usr/bin/env python3
"""Apply only explicitly approved OCR findings to derived per-page Markdown.

Inputs are a v2/v3 probe JSON report and the unchanged Paddle OCR ZIP.
Run without --execute to validate/preview; --execute writes a NEW output folder.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

ALLOWED_STATUSES = {None, "approved", "rejected", "deferred"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_relative(member):
    path = PurePosixPath(member)
    if not member or path.is_absolute() or any(part in ("..", ".") for part in path.parts):
        raise ValueError(f"Unsafe ZIP member path: {member!r}")
    return Path(*path.parts)


IMMUTABLE_FINDING_KEYS = (
    "id", "page", "rule", "triggers", "source_image", "paddle_markdown",
    "paddle_json", "source_md_sha256", "start_byte", "end_byte",
    "json_block_id", "observed", "proposal_source",
)


def check_against_baseline(report, baseline):
    """Codex/human may edit decisions, never the detector's findings or fixed proposals."""
    for key in ("inputs", "page_count", "counts_by_rule"):
        if report[key] != baseline[key]:
            raise ValueError(f"Reviewed report altered baseline field: {key}")
    new = report["findings"]
    old = baseline["findings"]
    if len(new) != len(old):
        raise ValueError("Reviewed report added or removed findings")
    for original, reviewed in zip(old, new):
        for key in IMMUTABLE_FINDING_KEYS:
            if original.get(key) != reviewed.get(key):
                raise ValueError(f"Reviewed report changed {key}: {original['id']}")
        if original.get("proposal_source") == "deterministic_whitespace" and original["proposed"] != reviewed["proposed"]:
            raise ValueError(f"Reviewed report changed deterministic whitespace proposal: {original['id']}")


def build(report, paddle_zip):
    if digest(paddle_zip.read_bytes()) != report["inputs"]["paddle_zip_sha256"]:
        raise ValueError("Paddle ZIP hash differs from the probe report; refusing to apply offsets")

    with zipfile.ZipFile(paddle_zip) as archive:
        all_names = archive.namelist()
        if len(set(all_names)) != len(all_names):
            raise ValueError("Duplicate ZIP member paths")
        raw_pages = {name: archive.read(name) for name in all_names if name.endswith(".md") and not name.endswith("/")}

    pending_edits = defaultdict(list)
    seen_ids = set()
    seen_hashes = {}
    status_counts = Counter()
    approved_ids = []

    for finding in report["findings"]:
        fid = finding["id"]
        if fid in seen_ids:
            raise ValueError(f"Duplicate finding ID: {fid}")
        seen_ids.add(fid)
        status = finding["review"]["status"]
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"Unknown review.status {status!r} for {fid}")
        status_counts["pending" if status is None else status] += 1

        path = finding["paddle_markdown"]
        if path not in raw_pages:
            if status == "approved":
                raise ValueError(f"Approved finding has no Markdown file: {fid}")
            continue
        original = raw_pages[path]
        recorded_hash = finding["source_md_sha256"]
        if recorded_hash != digest(original):
            raise ValueError(f"Per-page Markdown hash mismatch: {fid}")
        if path in seen_hashes and recorded_hash != seen_hashes[path]:
            raise ValueError(f"Inconsistent page hashes: {path}")
        seen_hashes[path] = recorded_hash

        if status != "approved":
            continue
        start, end = finding["start_byte"], finding["end_byte"]
        if not (isinstance(start, int) and not isinstance(start, bool) and
                isinstance(end, int) and not isinstance(end, bool) and 0 <= start < end <= len(original)):
            raise ValueError(f"Approved finding has no valid byte range: {fid}")
        observed = finding["observed"].encode("utf-8")
        if original[start:end] != observed:
            raise ValueError(f"Observed text does not match original bytes: {fid}")
        override = finding["review"]["replacement"]
        proposal = finding["proposed"]
        if override is not None and not isinstance(override, str):
            raise ValueError(f"Human replacement must be text: {fid}")
        if override is None and not isinstance(proposal, str):
            raise ValueError(f"Approved finding has no proposed replacement: {fid}")
        replacement = override if override is not None else proposal
        pending_edits[path].append((start, end, replacement.encode("utf-8"), fid,
                                    "review.replacement" if override is not None else "proposed"))
        approved_ids.append(fid)

    # Construct output only after EVERY approved edit has passed validation.
    derived = dict(raw_pages)
    records = []
    for path, edits in sorted(pending_edits.items()):
        original = raw_pages[path]
        ordered = sorted(edits)
        for left, right in zip(ordered, ordered[1:]):
            if left[1] > right[0]:
                raise ValueError(f"Conflicting approved ranges: {left[3]} and {right[3]}")
        # Right-to-left replacement preserves original byte offsets.
        changed = original
        for start, end, replacement, fid, source in reversed(ordered):
            changed = changed[:start] + replacement + changed[end:]
            records.append({"id": fid, "page_markdown": path, "start_byte": start,
                            "end_byte": end, "replacement_source": source,
                            "observed": original[start:end].decode("utf-8"),
                            "replacement": replacement.decode("utf-8")})
        derived[path] = changed

    summary = {"source_paddle_zip_sha256": report["inputs"]["paddle_zip_sha256"],
               "source_report_sha256": None, "page_count": len(raw_pages),
               "review_status_counts": dict(sorted(status_counts.items())),
               "approved_findings": len(approved_ids),
               "changed_pages": sum(derived[p] != raw_pages[p] for p in raw_pages),
               "changes": sorted(records, key=lambda r: (r["page_markdown"], r["start_byte"]))}
    return derived, summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", type=Path, required=True, help="Codex/human-reviewed findings JSON")
    ap.add_argument("--baseline", type=Path, required=True, help="Original untouched scanner findings JSON")
    ap.add_argument("--paddle", type=Path, required=True, help="Original Paddle ZIP")
    ap.add_argument("--out", type=Path, required=True, help="New directory for derived Markdown")
    ap.add_argument("--execute", action="store_true", help="Write derived files after validation")
    args = ap.parse_args()

    report_bytes = args.report.read_bytes()
    report = json.loads(report_bytes)
    baseline = json.loads(args.baseline.read_bytes())
    check_against_baseline(report, baseline)
    derived, summary = build(report, args.paddle)
    summary["source_baseline_sha256"] = digest(args.baseline.read_bytes())
    summary["source_report_sha256"] = digest(report_bytes)
    print(f"Validated {summary['page_count']} Markdown pages; "
          f"{summary['approved_findings']} approved findings; "
          f"{summary['changed_pages']} pages would change.")
    print("Review statuses:", summary["review_status_counts"])
    if not args.execute:
        print("DRY RUN ONLY — nothing written. Pass --execute to create derived output.")
        return

    if args.out.exists():
        ap.error("Output already exists; refusing to overwrite")
    for member in derived:
        safe_relative(member)
    # The output is derived data only. Neither original ZIP nor report is mutated.
    args.out.mkdir(parents=True)
    for member, content in sorted(derived.items()):
        dst = args.out / safe_relative(member)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(content)
    (args.out / "execution_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Wrote:", args.out)


if __name__ == "__main__":
    main()
