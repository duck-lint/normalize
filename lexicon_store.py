"""Versioned human-approved vocabulary, separate from per-occurrence repair authority."""
import hashlib
import json
import unicodedata
from pathlib import Path

from lexical_detection import lexical_character

LEXICON_FORMAT = "normalize_lexicon_v1"
APPROVAL_FORMAT = "human_lexicon_approvals_v1"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(word):
    return unicodedata.normalize("NFC", word).casefold()


def valid_word(word):
    return (isinstance(word, str) and bool(word) and
            any(c.isalpha() for c in word) and
            all(lexical_character(c) for c in word))


def validate_lexicon(data):
    if not isinstance(data, dict) or data.get("format") != LEXICON_FORMAT or not isinstance(data.get("entries"), list):
        raise ValueError("Unsupported lexicon format")
    if set(data) != {"format", "entries"}:
        raise ValueError("Unexpected lexicon fields")
    seen = set()
    for item in data["entries"]:
        if (not isinstance(item, dict) or set(item) != {"word", "approval", "note"}
                or not valid_word(item["word"]) or not isinstance(item["approval"], dict)
                or set(item["approval"]) != {"finding_id", "source_report_sha256", "source_scans_sha256"}
                or not all(isinstance(x, str) and x for x in item["approval"].values())
                or not isinstance(item["note"], str) or not item["note"].strip()):
            raise ValueError("Malformed approved lexicon entry")
        key = canonical(item["word"])
        if key in seen:
            raise ValueError("Duplicate lexicon word")
        seen.add(key)
    return seen


def read_lexicon(path):
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    return data, sha(raw), validate_lexicon(data)


def serialize(data):
    validate_lexicon(data)
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def apply_human_admissions(lexicon, approvals, reviewed, baseline, baseline_hash, lexicon_hash):
    """Require a separate human-written explicit approval file; never infer admissions."""
    if approvals is None:
        return lexicon, []
    if (not isinstance(approvals, dict) or approvals.get("format") != APPROVAL_FORMAT
            or approvals.get("source_report_sha256") != baseline_hash
            or approvals.get("lexicon_sha256") != lexicon_hash
            or not isinstance(approvals.get("entries"), list)
            or set(approvals) != {"format", "source_report_sha256", "lexicon_sha256", "entries"}):
        raise ValueError("Lexicon approval file not bound to the current report and lexicon")
    by_id = {f["id"]: f for f in reviewed["findings"]}
    base_ids = {f["id"]: f for f in baseline["findings"]}
    existing = validate_lexicon(lexicon)
    added = []
    for entry in approvals["entries"]:
        if (not isinstance(entry, dict) or set(entry) != {"word", "finding_id", "approved", "note"}
                or entry["approved"] is not True or not valid_word(entry["word"])
                or not isinstance(entry["note"], str) or not entry["note"].strip()):
            raise ValueError("Lexicon admissions require explicit human approval and a reason")
        fid = entry["finding_id"]
        finding = by_id.get(fid)
        original = base_ids.get(fid)
        if (finding is None or original is None
                or "unrecognized_token" not in original["triggers"]
                or canonical(entry["word"]) != canonical(original["observed"])
                or finding["proposed"] is not None or finding["review"]["status"] is not None):
            raise ValueError(f"Lexicon admission not supported by an unrepaired finding: {fid}")
        key = canonical(entry["word"])
        if key in existing:
            raise ValueError(f"Word already admitted in lexicon or approval file: {entry['word']}")
        existing.add(key)
        added.append({"word": entry["word"],
                      "approval": {"finding_id": fid, "source_report_sha256": baseline_hash,
                                   "source_scans_sha256": baseline["inputs"]["source_dir_sha256"]},
                      "note": entry["note"]})
    return {"format": LEXICON_FORMAT, "entries": lexicon["entries"] + added}, added
