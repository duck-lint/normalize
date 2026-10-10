"""Verified comparison semantics for the single punctuation-whitespace stage.

This is not a general repair history engine. Never use this comparison view for
new proposals: their offsets and hashes must address the actual input Markdown.
"""
from collections import defaultdict
import hashlib
import json
import re

from artifact_directory import manifest_sha256, file_sha256

EXECUTION_FORMAT = "punctuation_whitespace_v1"


def whitespace_proposal(observed, triggers):
    """Insert only ASCII spaces for punctuation adjacency findings."""
    if not triggers or not set(triggers) <= {"punctuation_letter", "period_capital"}:
        return None
    proposed = re.sub(r"([,;:!?])(?=[A-Za-z])", r"\1 ", observed)
    proposed = re.sub(r"\.(?=[A-Z])", ". ", proposed)
    return proposed if proposed != observed else None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def comparison_views(files, scans_hash, overrides=None, skip_files=()):
    """Reverse recorded edits in memory, then verify the whole source snapshot.

    Presence of a ledger requires validation; invalid provenance must never
    silently fall back to a raw comparison or suppress findings.
    """
    overrides = overrides or {}
    skip_files = set(skip_files)
    ledger_path = files.get("execution_report.json")
    if ledger_path is None:
        return {}, {}, {"mode": "raw", "execution_report_sha256": None}
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)
    if ledger["execution_format"] != EXECUTION_FORMAT:
        raise ValueError("Unsupported whitespace execution format; regenerate from raw artifacts")
    if ledger["source_dir_sha256"] != scans_hash:
        raise ValueError("Source scans differ from the whitespace execution input")
    changes = ledger["changes"]
    if (not isinstance(changes, list) or type(ledger["approved_findings"]) is not int
            or ledger["approved_findings"] != len(changes)):
        raise ValueError("Invalid execution change count")
    by_page = defaultdict(list)
    seen = set()
    for change in changes:
        fid = change["id"]
        if not isinstance(fid, str) or fid in seen:
            raise ValueError("Invalid or duplicate executed finding ID")
        seen.add(fid)
        path = change["paddle_markdown"]
        if path not in files or not path.lower().endswith(".md"):
            raise ValueError(f"Executed Markdown page is missing: {fid}")
        if change["json_markdown_comparison"] != "reverse_executed_punctuation_spaces":
            raise ValueError(f"Unsupported comparison semantics: {fid}")
        if (not isinstance(change["observed"], str) or not isinstance(change["proposed"], str)
                or not isinstance(change["triggers"], list)
                or change["proposed"] != whitespace_proposal(change["observed"], change["triggers"])):
            raise ValueError(f"Invalid executed punctuation-space proposal: {fid}")
        by_page[path].append(change)

    views = {}
    for path, records in by_page.items():
        raw = overrides.get(path)
        if raw is None:
            raw = files[path].read_bytes()
        derived_hash = digest(raw)
        ordered = sorted(records, key=lambda r: r["start_byte"])
        shift = 0
        previous_end = 0
        spans = []
        for record in ordered:
            start, end = record["start_byte"], record["end_byte"]
            observed = record["observed"].encode("utf-8")
            proposed = record["proposed"].encode("utf-8")
            if (type(start) is not int or type(end) is not int
                    or start < previous_end or end <= start or end - start != len(observed)):
                raise ValueError("Invalid or overlapping executed byte ranges")
            if derived_hash != record["derived_md_sha256"]:
                raise ValueError(f"Derived Markdown hash mismatch: {path}")
            derived_start = start + shift
            derived_end = derived_start + len(proposed)
            if raw[derived_start:derived_end] != proposed:
                raise ValueError(f"Executed replacement bytes do not match: {record['id']}")
            spans.append((derived_start, derived_end, observed))
            shift += len(proposed) - len(observed)
            previous_end = end
        original = raw
        for start, end, observed in reversed(spans):
            original = original[:start] + observed + original[end:]
        original_hash = digest(original)
        if any(original_hash != r["source_md_sha256"] for r in records):
            raise ValueError(f"Reconstructed source Markdown hash mismatch: {path}")
        views[path] = original.decode("utf-8")

    # This binds unchanged JSON/assets/pages as well as repaired pages. The
    # ledger is the only added file; the remaining snapshot must reconstruct
    # exactly to the executor's recorded input directory hash.
    manifest = {name: digest(views[name].encode("utf-8")) if name in views else
                digest(overrides[name]) if name in overrides else file_sha256(path)
                for name, path in files.items()
                if name != "execution_report.json" and name not in skip_files}
    if manifest_sha256(manifest) != ledger["source_paddle_dir_sha256"]:
        raise ValueError("Reconstructed Paddle directory hash mismatch")
    return views, dict(by_page), {
        "mode": "verified_executed_whitespace",
        "execution_report_sha256": digest(ledger_bytes),
        "source_paddle_dir_sha256": ledger["source_paddle_dir_sha256"],
        "executed_findings": len(changes),
    }
