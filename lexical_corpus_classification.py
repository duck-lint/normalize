"""Read-only, occurrence-complete lexical evidence classification.

This is a DIAGNOSTIC view, not a review decision or authorization. Every
classification preserves the boundary between structured workflow decisions,
agent-authored prose, deterministic context properties and hypotheses.
"""
from collections import Counter, defaultdict
import re

from review_lexicon import context_parts

FORMAT = "lexical_corpus_classification_v1"
PENDING = "pending_human_vocabulary_review"
APPROVED = frozenset(("codex_verified_repair", "human_approved_repair"))
APOSTROPHES = "'\u2019"
PREFIXES = frozenset((
    "aren", "couldn", "didn", "doesn", "don", "hadn", "hasn",
    "haven", "isn", "mustn", "shouldn", "wasn", "weren",
    "won", "wouldn",
))
NAME_NOTE = re.compile(r"\b(?:proper name|surname|personal name|person's name)\b", re.I)
TERM_NOTE = re.compile(r"\b(?:technical term|specialized term|domain-specific term)\b", re.I)
NO_APOSTROPHE_NOTE = re.compile(
    r"\b(?:without an apostrophe|with no apostrophe|no apostrophe|apostrophe[- ]less)\b", re.I)
SOURCE_MARKERS = ("SCAN_VERIFIED:", "SCAN_UNRESOLVED:", "SCAN_BLOCKED:")
ROUTES = {
    "repair_span_safety_audit": "Test whether an approved replacement duplicates untouched context",
    "tokenizer_boundary_experiment": "Investigate incomplete lexical-unit detection (no correction inferred)",
    "existing_verified_repair_candidate": "Preserve existing scan-backed repair approval; no new authorization",
    "previously_triaged": "Retain reviewed/bulk-excluded evidence without reopening vocabulary decisions",
    "book_scoped_recognition_experiment": "Investigate printed conventions without changing shared spelling",
    "source_faithful_nonlexical_candidate": "Keep nonlexical source form distinct from a vocabulary admission",
    "targeted_source_inspection": "Agent reported blocked or unresolved scan evidence; human/source follow-up",
    "lexical_coverage_experiment": "Evaluate names/terminology against external resources; no admission",
    "unclassified_review_candidate": "No supported deterministic route; classify using source evidence",
}


def _normalized_apostrophe(value):
    return value.replace("\u2019", "'").casefold()


def _contraction_suffix(observed, after):
    """Require an exact source-context split within a common n+'t contraction."""
    if observed.casefold() not in PREFIXES:
        return None
    if len(after) >= 2 and after[0] in APOSTROPHES and after[1] == "t":
        if len(after) == 2 or not after[2].isalpha():
            return after[:2]
    return None


def classify_occurrence(o):
    """Classify the recorded UTF-8 span, never OCR correctness from a note."""
    before, observed, after = context_parts({
        "id": o["finding_id"], "start_byte": o["start_byte"],
        "end_byte": o["end_byte"], "observed": o["observed"],
        "ocr_context": o["ocr_context"],
    })
    if observed != o["observed"]:
        raise ValueError("Unexpected context span")
    repair = o["repair_state"]
    notes = (o.get("proposal_note") or "", o.get("verification_note") or "")
    note_text = " ".join(notes)
    proposal_tag = next(
        (m.removesuffix(":").lower() for m in SOURCE_MARKERS if notes[0].startswith(m)), None)
    suffix = _contraction_suffix(observed, after)
    clues = []
    if suffix is not None:
        clues.append("exact_contraction_prefix_span")
    if "contraction_like" in o["signals"]:
        clues.append("contraction_like_spelling")
    if "mixed_greek_latin" in o["signals"]:
        clues.append("mixed_greek_latin_characters")
    if "greek_script" in o["signals"]:
        clues.append("greek_characters")
    if any(s in o["signals"] for s in ("adjacent_apostrophe",)):
        clues.append("adjacent_apostrophe")
    if NAME_NOTE.search(note_text):
        clues.append("agent_note_mentions_proper_name")
    if TERM_NOTE.search(note_text):
        clues.append("agent_note_mentions_technical_term")
    if "contraction_like_spelling" in clues and NO_APOSTROPHE_NOTE.search(notes[1]):
        clues.append("verifier_note_claims_printed_without_apostrophe")
    if proposal_tag:
        clues.append("proposer_note_" + proposal_tag)
    if repair == "source_faithful_nonlexical":
        clues.append("structured_source_faithful_nonlexical")
    elif repair in APPROVED:
        clues.append("structured_approved_repair_candidate")

    duplicate = bool(suffix and repair in APPROVED and
                     isinstance(o.get("replacement"), str) and
                     _normalized_apostrophe(o["replacement"]) ==
                     _normalized_apostrophe(observed + suffix))
    if duplicate:
        route = "repair_span_safety_audit"
    elif suffix:
        route = "tokenizer_boundary_experiment"
    elif repair in APPROVED:
        route = "existing_verified_repair_candidate"
    elif o["disposition"] != PENDING:
        route = "previously_triaged"
    elif "verifier_note_claims_printed_without_apostrophe" in clues:
        route = "book_scoped_recognition_experiment"
    elif repair == "source_faithful_nonlexical":
        route = "source_faithful_nonlexical_candidate"
    elif proposal_tag in ("scan_unresolved", "scan_blocked"):
        route = "targeted_source_inspection"
    elif ("agent_note_mentions_proper_name" in clues or
          "agent_note_mentions_technical_term" in clues):
        route = "lexical_coverage_experiment"
    else:
        route = "unclassified_review_candidate"

    return {
        "book": o["book"], "finding_id": o["finding_id"], "page": o["page"],
        "observed": observed, "canonical": o["canonical"],
        "disposition": o["disposition"], "repair_state": repair,
        "replacement": o["replacement"], "source_image": o["source_image"],
        "paddle_markdown": o["paddle_markdown"],
        "start_byte": o["start_byte"], "end_byte": o["end_byte"],
        "ocr_context": o["ocr_context"],
        "proposal_note": o["proposal_note"], "verification_note": o["verification_note"],
        "human_note": o["human_note"],
        "proposer_note_tag": proposal_tag,
        "clues_not_conclusions": sorted(set(clues)),
        "primary_investigation_route": route,
        "repair_may_duplicate_existing_suffix": duplicate,
        "evidence_levels": {
            "disposition_and_repair_state": "validated_snapshot_and_saved_review",
            "byte_span_and_script": "deterministic_observation",
            "agent_prose": "unstructured_agent_claim_not_a_new_authorization",
            "investigation_route": "diagnostic_hypothesis_only",
        },
    }


def build_classification(books, examples=3):
    """One record per occurrence. Book inputs must already pass load_book()."""
    if examples < 1:
        raise ValueError("examples must be positive")
    records = []
    hashes = []
    seen = set()
    for book in books:
        hashes.append({"name": book["name"], "snapshots": book["snapshots"]})
        for occ in book["occurrences"]:
            key = (book["name"], occ["finding_id"])
            if key in seen:
                raise ValueError(f"Duplicate book/finding ID: {key}")
            seen.add(key)
            if occ["book"] != book["name"]:
                raise ValueError(f"Book name mismatch for {occ['finding_id']}")
            records.append(classify_occurrence(occ))
    records.sort(key=lambda r: (r["book"], r["page"] or "", r["start_byte"], r["finding_id"]))
    pending = [r for r in records if r["disposition"] == PENDING]
    route_counts = Counter(r["primary_investigation_route"] for r in records)
    pending_route_counts = Counter(r["primary_investigation_route"] for r in pending)
    clue_counts = Counter(clue for r in pending for clue in r["clues_not_conclusions"])

    groups = defaultdict(list)
    for r in records:
        groups[(r["primary_investigation_route"], r["canonical"])].append(r)
    ranked = []
    for (route, word), members in groups.items():
        active = [m for m in members if m["disposition"] == PENDING]
        ranked.append({
            "route": route, "canonical": word,
            "books": sorted({m["book"] for m in members}),
            "occurrences": len(members), "pending_occurrences": len(active),
            "dispositions": dict(sorted(Counter(m["disposition"] for m in members).items())),
            "examples": [{
                "book": m["book"], "finding_id": m["finding_id"],
                "source_image": m["source_image"],
                "start_byte": m["start_byte"], "observed": m["observed"],
                "repair_state": m["repair_state"], "replacement": m["replacement"],
                "clues": m["clues_not_conclusions"],
            } for m in members[:examples]],
        })
    ranked.sort(key=lambda g: (-g["pending_occurrences"], -g["occurrences"],
                               g["route"], g["canonical"]))
    return {
        "format": FORMAT,
        "interpretation": (
            "Read-only, occurrence-complete diagnostic, not executor input. "
            "A proposed route is not a source-level verdict, correction, "
            "lexicon admission or waiver of human review. Agent prose is "
            "not converted into an approval. Existing approved repairs are "
            "reported without modification."),
        "books": hashes,
        "summary": {
            "occurrences": len(records), "pending_occurrences": len(pending),
            "book_forms": sum(len(book["forms"]) for book in books),
            "pending_book_forms": sum(sum(
                form["disposition"] == PENDING for form in book["forms"]) for book in books),
            "routes_all_occurrences": dict(sorted(route_counts.items())),
            "routes_pending_occurrences": dict(sorted(pending_route_counts.items())),
            "clues_pending_occurrences": dict(sorted(clue_counts.items())),
            "possible_duplicate_suffix_repairs": sum(
                r["repair_may_duplicate_existing_suffix"] for r in records),
            "route_form_groups": len(groups),
        },
        "route_descriptions": ROUTES,
        "ranked_route_form_groups": ranked,
        "occurrences": records,
    }
