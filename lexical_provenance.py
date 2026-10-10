"""Verify one lexical repair ledger atop a hash-verified whitespace snapshot.

All reversals occur in memory. Actual derived Markdown remains the input for
new detections; reverse views are used solely for JSON comparison.
"""
from collections import defaultdict
import hashlib
import json

from artifact_directory import manifest_sha256, file_sha256
from whitespace_provenance import comparison_views as whitespace_comparison

EXECUTION_FORMAT = "lexical_repairs_v1"
LEDGER = "lexical_execution_report.json"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def comparison_views(files, scans_hash):
    ledger_path = files.get(LEDGER)
    if ledger_path is None:
        return whitespace_comparison(files, scans_hash)
    ledger_raw = ledger_path.read_bytes()
    ledger = json.loads(ledger_raw)
    if (ledger.get("execution_format") != EXECUTION_FORMAT
            or ledger.get("source_dir_sha256") != scans_hash
            or not isinstance(ledger.get("source_artifact_dir_sha256"), str)
            or not isinstance(ledger.get("source_lexicon_sha256"), str)):
        raise ValueError("Invalid lexical stage identity or source metadata")
    changes = ledger.get("changes")
    if (not isinstance(changes, list) or type(ledger.get("approved_findings")) is not int
            or len(changes) != ledger["approved_findings"]):
        raise ValueError("Invalid lexical execution change count")
    by_page = defaultdict(list)
    ids = set()
    for record in changes:
        fid = record.get("id")
        path = record.get("paddle_markdown")
        if (not isinstance(fid, str) or not fid or fid in ids
                or not isinstance(path, str) or path not in files
                or not path.lower().endswith(".md")):
            raise ValueError("Invalid lexical finding identity or page")
        ids.add(fid)
        if (not isinstance(record.get("observed"), str)
                or not isinstance(record.get("proposed"), str)
                or record["proposed"] == record["observed"]):
            raise ValueError("Invalid executed lexical replacement")
        by_page[path].append(record)

    restored = {}
    for path, records in by_page.items():
        derived = files[path].read_bytes()
        derived_hash = digest(derived)
        ordered = sorted(records, key=lambda r: r["start_byte"])
        shifts = 0
        prior_end = 0
        reverse = []
        for record in ordered:
            start, end = record["start_byte"], record["end_byte"]
            observed = record["observed"].encode("utf-8")
            replacement = record["proposed"].encode("utf-8")
            if (type(start) is not int or type(end) is not int
                    or start < prior_end or end <= start or end - start != len(observed)
                    or record["derived_md_sha256"] != derived_hash):
                raise ValueError("Invalid, overlapping, or stale lexical execution spans")
            revised_start = start + shifts
            revised_end = revised_start + len(replacement)
            if derived[revised_start:revised_end] != replacement:
                raise ValueError("Lexical replacement bytes do not match derived artifact")
            reverse.append((revised_start, revised_end, observed))
            shifts += len(replacement) - len(observed)
            prior_end = end
        source = derived
        for start, end, previous in reversed(reverse):
            source = source[:start] + previous + source[end:]
        if any(digest(source) != r["source_md_sha256"] for r in records):
            raise ValueError("Reconstructed lexical stage source hash mismatch")
        restored[path] = source

    # This snapshot includes the earlier whitespace execution ledger, untouched
    # assets/JSON and unchanged Markdown pages. Only the new lexical ledger is omitted.
    manifest = {name: digest(restored[name]) if name in restored else file_sha256(file)
                for name, file in files.items() if name != LEDGER}
    if manifest_sha256(manifest) != ledger["source_artifact_dir_sha256"]:
        raise ValueError("Reconstructed lexical source directory hash mismatch")

    views, whitespace_records, metadata = whitespace_comparison(
        files, scans_hash, overrides=restored, skip_files={LEDGER})
    all_pages = set(whitespace_records) | set(by_page)
    combined = {page: list(whitespace_records.get(page, [])) + list(by_page.get(page, []))
                for page in all_pages}
    metadata.update({"mode": "verified_executed_lexical_and_whitespace",
                     "lexical_execution_report_sha256": digest(ledger_raw),
                     "lexical_executed_findings": len(changes),
                     "source_lexicon_sha256": ledger["source_lexicon_sha256"]})
    return views, combined, metadata
