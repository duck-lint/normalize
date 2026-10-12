"""Explicit, scan-inspected human occurrence repairs, separate from vocabulary.

Codex proposal and verifier reports remain immutable. This module constructs an
in-memory effective reviewed view only after validating the human export's
original-source bindings. Legacy lexicon-only approvals remain supported.
"""
import copy

HUMAN_APPROVAL_FORMAT = "human_lexical_approvals_v2"
LEGACY_APPROVAL_FORMAT = "human_lexicon_approvals_v1"


def effective_review(baseline, proposals, reviewed, approvals,
                     baseline_hash, proposals_hash, reviewed_hash, lexicon_hash):
    """Return a separate effective report and validated human repair entries."""
    result = copy.deepcopy(reviewed)
    if approvals is None or approvals.get("format") == LEGACY_APPROVAL_FORMAT:
        return result, []
    if (not isinstance(approvals, dict)
            or set(approvals) != {
                "format", "source_report_sha256", "source_proposals_sha256",
                "source_reviewed_sha256", "source_scans_sha256",
                "lexicon_sha256", "entries", "repairs"
            }
            or approvals["format"] != HUMAN_APPROVAL_FORMAT
            or approvals["source_report_sha256"] != baseline_hash
            or approvals["source_proposals_sha256"] != proposals_hash
            or approvals["source_reviewed_sha256"] != reviewed_hash
            or approvals["source_scans_sha256"] != baseline["inputs"]["source_dir_sha256"]
            or approvals["lexicon_sha256"] != lexicon_hash
            or not isinstance(approvals["entries"], list)
            or not isinstance(approvals["repairs"], list)):
        raise ValueError("Human approval file is not bound to frozen lexical source snapshots")
    by_id = {f["id"]: f for f in result["findings"]}
    before = {f["id"]: f for f in reviewed["findings"]}
    seen = set()
    repairs = []
    for item in approvals["repairs"]:
        if not isinstance(item, dict) or set(item) != {
                "finding_id", "observed", "decision", "replacement", "note"}:
            raise ValueError("Malformed human occurrence repair decision")
        fid = item["finding_id"]
        if not isinstance(fid, str) or fid in seen or fid not in by_id:
            raise ValueError(f"Unknown or duplicate human repair finding: {fid}")
        seen.add(fid)
        original = before[fid]
        choice, replacement, note = item["decision"], item["replacement"], item["note"]
        if (item["observed"] != original["observed"]
                or choice not in ("approved", "rejected")
                or not isinstance(note, str) or not note.strip()
                or (choice == "approved" and (
                    not isinstance(replacement, str)
                    or replacement == original["observed"]))
                or (choice == "rejected" and (
                    replacement is not None or original["proposed"] is None))):
            raise ValueError(f"Invalid human scan repair decision: {fid}")
        finding = by_id[fid]
        if choice == "approved":
            finding["proposed"] = replacement  # empty string is valid deletion
            finding["proposal_source"] = "human_scan_proposal"
            finding["evidence"] = note
            finding["review"] = {"status": "approved",
                                  "note": "HUMAN_SCAN_APPROVED: " + note}
        else:
            finding["proposed"] = None
            finding["proposal_source"] = None
            finding["evidence"] = None
            finding["review"] = {"status": None,
                                  "note": "HUMAN_SCAN_REJECTED: " + note}
        repairs.append(copy.deepcopy(item))
    return result, repairs
