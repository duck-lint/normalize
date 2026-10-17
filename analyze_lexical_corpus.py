#!/usr/bin/env python3
"""Read-only, provenance-bound analysis of post-bulk lexical review workloads.

Joins frozen Probe 2, lexical proposals, independent verification and the
Review UI's saved progress. No scan inspection, re-probing, admissions,
approvals or OCR edits occur. All inferred signals are hypotheses, not verdicts.
"""
import argparse
from collections import Counter, defaultdict
import difflib
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from execute_lexical_repairs import validate_handoffs
from lexicon_store import canonical
from review_lexicon import (LEGACY_PROGRESS_FORMAT, PROGRESS_FORMAT,
                            source_faithful_verified)

FORMAT = "post_bulk_lexical_corpus_analysis_v1"
BULK_REPAIR_NOTE = (
    "Human bulk exclusion from this lexicon admission batch: every "
    "observed occurrence has an independently approved OCR repair. "
    "Occurrence-level repair decisions remain unchanged.")
BULK_SOURCE_NOTE = (
    "Human bulk lexicon exclusion: every observed occurrence was annotated "
    "SOURCE_FAITHFUL_NONLEXICAL_VERIFIED by independent scan review. "
    "No OCR repair decisions or persistent vocabulary changed.")
CONTRACTIONS = frozenset({
    "arent", "cant", "couldnt", "didnt", "doesnt", "dont", "hadnt", "hasnt",
    "havent", "isnt", "mustnt", "shouldnt", "wasnt", "werent", "wont",
    "wouldnt", "youre", "theyre", "weve", "ive", "im", "thats", "theres",
})
APOSTROPHES = "'\u2019"
SIGNAL_HINTS = {
    "contraction_like": "Inspect punctuation/tokenization against source scans",
    "adjacent_apostrophe": "Inspect apostrophe-aware lexical segmentation",
    "mixed_greek_latin": "Inspect script confusion and OCR routing",
    "greek_script": "Inspect Greek-specific OCR or script handling",
    "mixed_digits_letters": "Inspect numeric-cluster segmentation",
    "roman_numeral_like": "Inspect historical numbering/notation policy",
    "no_obvious_signal": "Further scan-backed classification needed",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"Duplicate JSON key: {key}")
        obj[key] = value
    return obj


def read_json(path):
    raw = path.read_bytes()
    return json.loads(raw, object_pairs_hook=unique_pairs), digest(raw)


def signals(finding):
    """Conservative lexical clues; NEVER automatic OCR diagnoses or repairs."""
    word = finding["observed"]
    latin = greek = False
    for char in word:
        if char.isalpha():
            name = unicodedata.name(char, "")
            latin |= "LATIN" in name
            greek |= "GREEK" in name
    labels = []
    if canonical(word) in CONTRACTIONS:
        labels.append("contraction_like")
    if latin and greek:
        labels.append("mixed_greek_latin")
    elif greek:
        labels.append("greek_script")
    if any(c.isdigit() for c in word) and any(c.isalpha() for c in word):
        labels.append("mixed_digits_letters")
    if re.fullmatch(r"[IVXLCDMivxlcdm]{4,}", word):
        labels.append("roman_numeral_like")
    context = finding.get("ocr_context")
    if isinstance(context, dict) and isinstance(context.get("text"), str):
        raw = context["text"].encode("utf-8")
        left = finding.get("start_byte", -1) - context.get("start_byte", 0)
        right = finding.get("end_byte", -1) - context.get("start_byte", 0)
        if (isinstance(left, int) and isinstance(right, int)
                and 0 <= left < right <= len(raw)
                and raw[left:right] == word.encode("utf-8")):
            preceding = raw[:left].decode("utf-8")
            following = raw[right:].decode("utf-8")
            if (preceding[-1:] in APOSTROPHES or
                    following[:1] in APOSTROPHES):
                labels.append("adjacent_apostrophe")
    return sorted(set(labels)) or ["no_obvious_signal"]


def disposition(group, decision, effective):
    """Form-level Review UI disposition; unrelated to OCR correctness."""
    if decision is None:
        return "pending_human_vocabulary_review"
    if not isinstance(decision, dict) or decision.get("decision") not in ("accepted", "rejected"):
        raise ValueError(f"Invalid saved vocabulary decision for {group[0]['observed']}")
    if decision["decision"] == "accepted":
        if (not isinstance(decision.get("finding_id"), str)
                or decision["finding_id"] not in {f["id"] for f in group}
                or not isinstance(decision.get("note"), str)):
            raise ValueError("Invalid accepted vocabulary decision")
        return "human_accepted_vocabulary"
    if decision.get("finding_id") is not None or not isinstance(decision.get("note"), str):
        raise ValueError("Invalid rejected vocabulary decision")
    note = decision["note"]
    if note == BULK_REPAIR_NOTE:
        if not all(effective[f["id"]]["state"] in
                   ("codex_verified_repair", "human_approved_repair") for f in group):
            raise ValueError("Bulk repair exclusion conflicts with occurrence decisions")
        return "bulk_excluded_all_repair_verified"
    if note == BULK_SOURCE_NOTE:
        if not all(effective[f["id"]]["state"] == "source_faithful_nonlexical"
                   for f in group):
            raise ValueError("Bulk source-faithful exclusion conflicts with verification")
        return "bulk_excluded_source_faithful_nonlexical"
    return "human_rejected_vocabulary_reason_unclassified"


def effective_state(finding, human):
    """Compute the view that Review UI displays, without authorizing anything."""
    proposed = finding["proposed"]
    approved = finding["review"]["status"] == "approved"
    if human is not None:
        if (not isinstance(human, dict)
                or human.get("observed") != finding["observed"]
                or human.get("decision") not in ("approved", "rejected")
                or not isinstance(human.get("note"), str) or not human["note"].strip()):
            raise ValueError(f"Invalid human occurrence override: {finding['id']}")
        if human["decision"] == "approved":
            replacement = human.get("replacement")
            if not isinstance(replacement, str) or replacement == finding["observed"]:
                raise ValueError(f"Invalid human replacement: {finding['id']}")
            return {"state": "human_approved_repair", "replacement": replacement}
        if human.get("replacement") is not None or proposed is None:
            raise ValueError(f"Invalid human repair rejection: {finding['id']}")
        return {"state": "human_rejected_repair", "replacement": None}
    if approved:
        return {"state": "codex_verified_repair", "replacement": proposed}
    if proposed is not None:
        return {"state": "proposed_not_verified", "replacement": proposed}
    if source_faithful_verified(finding):
        return {"state": "source_faithful_nonlexical", "replacement": None}
    return {"state": "no_verified_repair", "replacement": None}


def load_book(book):
    name = book["name"]
    paths = {key: book[key] for key in ("probe2", "proposals", "reviewed", "progress")}
    inputs = {key: read_json(path) for key, path in paths.items()}
    baseline, baseline_hash = inputs["probe2"]
    proposed, proposed_hash = inputs["proposals"]
    reviewed, reviewed_hash = inputs["reviewed"]
    progress, progress_hash = inputs["progress"]
    validate_handoffs(baseline, proposed, reviewed)

    if not isinstance(progress, dict) or progress.get("format") not in (
            PROGRESS_FORMAT, LEGACY_PROGRESS_FORMAT):
        raise ValueError(f"{name}: unsupported Review UI progress format")
    expected = {"baseline_sha256": baseline_hash,
                "proposals_sha256": proposed_hash,
                "reviewed_sha256": reviewed_hash,
                "lexicon_sha256": baseline["inputs"]["lexicon_sha256"],
                "scans_sha256": baseline["inputs"]["source_dir_sha256"]}
    if progress.get("snapshots") != expected:
        raise ValueError(f"{name}: progress belongs to different frozen source snapshots")
    if not isinstance(progress.get("decisions"), dict):
        raise ValueError(f"{name}: malformed vocabulary decisions")
    human_repairs = progress.get("repair_decisions", {})
    if (progress["format"] == PROGRESS_FORMAT and "repair_decisions" not in progress
            or not isinstance(human_repairs, dict)
            or (progress["format"] == LEGACY_PROGRESS_FORMAT
                and "repair_decisions" in progress)):
        raise ValueError(f"{name}: malformed occurrence overrides")

    by_id = {f["id"]: f for f in reviewed["findings"]}
    if len(by_id) != len(reviewed["findings"]):
        raise ValueError(f"{name}: duplicate finding IDs")
    if set(human_repairs) - set(by_id):
        raise ValueError(f"{name}: human override references unknown finding")
    effective = {fid: effective_state(f, human_repairs.get(fid))
                 for fid, f in by_id.items()}
    groups = defaultdict(list)
    for f in reviewed["findings"]:
        groups[canonical(f["observed"])].append(f)
    if set(progress["decisions"]) - set(groups):
        raise ValueError(f"{name}: vocabulary decision references unknown form")

    forms = []
    occurrences = []
    for key, members in sorted(groups.items()):
        status = disposition(members, progress["decisions"].get(key), effective)
        form_signals = Counter()
        for f in members:
            state = effective[f["id"]]
            tags = signals(f)
            form_signals.update(tags)
            occurrences.append({
                "book": name, "finding_id": f["id"], "page": f.get("page"),
                "observed": f["observed"], "canonical": key,
                "triggers": f["triggers"], "disposition": status,
                "repair_state": state["state"], "replacement": state["replacement"],
                "signals": tags,
                "proposal_note": f.get("proposal_note"),
                "verification_note": f["review"].get("note"),
                "human_note": (human_repairs.get(f["id"]) or {}).get("note"),
                "source_image": f.get("source_image"),
                "paddle_markdown": f.get("paddle_markdown"),
                "start_byte": f.get("start_byte"), "end_byte": f.get("end_byte"),
                "ocr_context": f.get("ocr_context"),
            })
        forms.append({"book": name, "key": key, "word": members[0]["observed"],
                      "count": len(members), "disposition": status,
                      "signals": dict(sorted(form_signals.items()))})

    snapshots = {key + "_sha256": value[1] for key, value in inputs.items()}
    snapshots["lexicon_sha256"] = expected["lexicon_sha256"]
    snapshots["scans_sha256"] = expected["scans_sha256"]
    return {"name": name, "snapshots": snapshots, "forms": forms,
            "occurrences": occurrences}


def analyze_books(books, top=50, examples=3):
    loaded = [load_book(book) for book in books]
    all_forms = [f for book in loaded for f in book["forms"]]
    all_occ = [f for book in loaded for f in book["occurrences"]]
    form_counts = Counter(f["disposition"] for f in all_forms)
    occurrence_counts = Counter(o["disposition"] for o in all_occ)
    repair_counts = Counter(o["repair_state"] for o in all_occ)

    per_book = []
    for book in loaded:
        bs = book["forms"]
        bo = book["occurrences"]
        per_book.append({
            "name": book["name"], "snapshots": book["snapshots"],
            "findings": len(bo), "distinct_forms": len(bs),
            "pending_forms": sum(f["disposition"] == "pending_human_vocabulary_review"
                                 for f in bs),
            "pending_occurrences": sum(o["disposition"] == "pending_human_vocabulary_review"
                                       for o in bo),
            "form_dispositions": dict(sorted(Counter(f["disposition"] for f in bs).items())),
            "occurrence_dispositions": dict(sorted(Counter(o["disposition"] for o in bo).items())),
            "repair_states": dict(sorted(Counter(o["repair_state"] for o in bo).items())),
        })

    signals_by_disposition = defaultdict(Counter)
    for o in all_occ:
        for tag in o["signals"]:
            signals_by_disposition[o["disposition"]][tag] += 1

    groups = defaultdict(list)
    for o in all_occ:
        groups[o["canonical"]].append(o)

    def summarize_form(key, records):
        dispositions = Counter(o["disposition"] for o in records)
        return {
            "canonical": key, "example_spelling": records[0]["observed"],
            "books": sorted({o["book"] for o in records}),
            "occurrences": len(records),
            "pending_occurrences": dispositions["pending_human_vocabulary_review"],
            "dispositions": dict(sorted(dispositions.items())),
            "repair_states": dict(sorted(Counter(o["repair_state"] for o in records).items())),
            "signals": sorted({tag for o in records for tag in o["signals"]}),
            "examples": [{
                "book": o["book"], "finding_id": o["finding_id"], "page": o["page"],
                "observed": o["observed"], "triggers": o["triggers"],
                "disposition": o["disposition"], "repair_state": o["repair_state"],
                "replacement": o["replacement"], "signals": o["signals"],
                "proposal_note": o["proposal_note"],
                "verification_note": o["verification_note"],
                "human_note": o["human_note"],
                "source_image": o["source_image"],
                "paddle_markdown": o["paddle_markdown"],
                "start_byte": o["start_byte"], "end_byte": o["end_byte"],
                "ocr_context": o["ocr_context"],
            } for o in records[:examples]],
        }

    ranked = [summarize_form(key, records) for key, records in groups.items()]
    pending = sorted((r for r in ranked if r["pending_occurrences"]),
                     key=lambda r: (-r["pending_occurrences"], -len(r["books"]), r["canonical"]))
    recurring = sorted((r for r in ranked if len(r["books"]) > 1),
                       key=lambda r: (-len(r["books"]), -r["occurrences"], r["canonical"]))
    excluded = sorted((r for r in ranked if any(
        s.startswith("bulk_excluded_") for s in r["dispositions"])),
        key=lambda r: (-r["occurrences"], r["canonical"]))

    approved = (o for o in all_occ if o["repair_state"] in
                ("codex_verified_repair", "human_approved_repair"))
    pairs = defaultdict(list)
    op_counts = Counter()
    for o in approved:
        replacement = o["replacement"]
        pairs[(o["observed"], replacement)].append(o["book"])
        for op, a, b, c, d in difflib.SequenceMatcher(
                a=o["observed"], b=replacement, autojunk=False).get_opcodes():
            if op != "equal":
                op_counts[(op, o["observed"][a:b], replacement[c:d])] += 1

    patterns = sorted((
        {"observed": old, "replacement": new, "occurrences": len(names),
         "books": sorted(set(names))}
        for (old, new), names in pairs.items()),
        key=lambda r: (-r["occurrences"], r["observed"], r["replacement"]))

    return {
        "format": FORMAT,
        "interpretation": (
            "Read-only pre-execution diagnostic. Vocabulary rejection is NOT proof "
            "of bad OCR; verified repair is a correction candidate, not executed "
            "text. Signals are hypotheses requiring source-scan validation."),
        "summary": {
            "books": len(loaded), "unknown_occurrences": len(all_occ),
            "book_distinct_forms": len(all_forms),
            "corpus_distinct_forms": len(groups),
            "pending_forms": form_counts["pending_human_vocabulary_review"],
            "pending_occurrences": occurrence_counts["pending_human_vocabulary_review"],
            "form_dispositions": dict(sorted(form_counts.items())),
            "occurrence_dispositions": dict(sorted(occurrence_counts.items())),
            "repair_states": dict(sorted(repair_counts.items())),
        },
        "books": per_book,
        "signal_hints_not_diagnoses": SIGNAL_HINTS,
        "signals_by_disposition": {
            label: dict(sorted(counts.items()))
            for label, counts in sorted(signals_by_disposition.items())
        },
        "top_pending_forms": pending[:top],
        "recurring_cross_book_forms": recurring[:top],
        "top_bulk_excluded_forms": excluded[:top],
        "verified_repair_pairs": patterns[:top],
        "verified_repair_edit_operations": [
            {"operation": op, "from": old, "to": new, "occurrences": count}
            for (op, old, new), count in sorted(
                op_counts.items(), key=lambda pair: (-pair[1], pair[0]))[:top]
        ],
        "ranked_list_limits": {"top": top, "examples_per_form": examples,
                               "pending_total": len(pending),
                               "recurring_total": len(recurring),
                               "bulk_excluded_total": len(excluded),
                               "repair_pair_total": len(patterns)},
    }


def manifest_books(path):
    data, _ = read_json(path)
    if (not isinstance(data, dict) or set(data) != {"books"}
            or not isinstance(data["books"], list) or not data["books"]):
        raise ValueError("Manifest must contain a nonempty books array")
    result = []
    names = set()
    used = set()
    for item in data["books"]:
        if not isinstance(item, dict) or set(item) != {
                "name", "probe2", "proposals", "reviewed", "progress"}:
            raise ValueError("Each book needs name, probe2, proposals, reviewed, progress")
        name = item["name"]
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Book names must be unique nonempty strings")
        names.add(name)
        book = {"name": name}
        for field in ("probe2", "proposals", "reviewed", "progress"):
            if not isinstance(item[field], str) or not item[field]:
                raise ValueError(f"{name}: invalid {field} path")
            candidate = (path.parent / item[field]).resolve()
            if candidate in used:
                raise ValueError(f"{name}: duplicate input path {candidate}")
            used.add(candidate)
            book[field] = candidate
        result.append(book)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="JSON books manifest, with paths relative to the manifest")
    parser.add_argument("--out", type=Path,
                        help="New JSON diagnostic file (refuses overwrite); otherwise stdout")
    parser.add_argument("--top", type=int, default=50,
                        help="Maximum ranked forms and patterns per category")
    parser.add_argument("--examples", type=int, default=3,
                        help="Maximum original finding examples per ranked form")
    args = parser.parse_args()
    if args.top < 1 or args.examples < 1:
        parser.error("--top and --examples must be positive")
    try:
        books = manifest_books(args.manifest.resolve())
        if args.out:
            target = args.out.resolve()
            if target == args.manifest.resolve() or any(
                    target == book[field] for book in books
                    for field in ("probe2", "proposals", "reviewed", "progress")):
                raise ValueError("Output cannot overwrite any input")
            if target.exists():
                raise ValueError(f"Output already exists: {target}")
        result = analyze_books(books, top=args.top, examples=args.examples)
        formatted = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            with args.out.open("x", encoding="utf-8") as stream:
                stream.write(formatted)
            print(f"Published read-only diagnostic: {args.out}")
        else:
            print(formatted, end="")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
