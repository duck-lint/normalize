"""Post-bulk corpus diagnosis preserves review authority and original snapshots."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analyze_lexical_corpus import (
    BULK_REPAIR_NOTE, BULK_SOURCE_NOTE, FORMAT, analyze_books, manifest_books,
    read_json,
)
from extract_lexical import extract
from lexical_corpus_classification import (
    FORMAT as CLASSIFICATION_FORMAT, build_classification, classify_occurrence,
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")


class CorpusAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.book1 = self.make_book(
            "Ancients",
            ["Schopenhuaer", "Schopenhuaer", "Oddprint", "didnt",
             "σkiεpov", "mistkae", "Otherword", "Acceptable"],
        )
        self.book2 = self.make_book(
            "Moderns", ["didnt", "σkiεpov", "Routlledge"])
        self.manifest = self.root / "manifest.json"
        write(self.manifest, {"books": [self.entry(self.book1), self.entry(self.book2)]})

    def make_book(self, name, words):
        directory = self.root / name
        directory.mkdir()
        findings = []
        for index, word in enumerate(words):
            text = "Before " + word + " after"
            start = len("Before ".encode("utf-8"))
            findings.append({
                "id": f"page{index:03d}:unrecognized_token:{start}",
                "page": f"page{index:03d}", "rule": "unrecognized_token",
                "triggers": ["unrecognized_token"],
                "source_image": f"page{index:03d}.png",
                "paddle_markdown": f"page{index:03d}.md",
                "start_byte": start, "end_byte": start + len(word.encode("utf-8")),
                "observed": word, "proposed": None, "proposal_source": None,
                "evidence": None, "source_md_sha256": "page-md-sha",
                "ocr_context": {"start_byte": 0, "end_byte": len(text.encode("utf-8")),
                                "text": text},
                "review": {"status": None, "note": None},
            })
        baseline = {
            "inputs": {"lexicon_sha256": "lexicon" + name,
                       "source_dir_sha256": "scans" + name},
            "findings": findings,
        }
        proposals = extract(baseline)
        for f in proposals["findings"]:
            if f["observed"] in ("Schopenhuaer", "Routlledge"):
                f["proposed"] = "Schopenhauer" if f["observed"] == "Schopenhuaer" else "Routledge"
                f["proposal_source"] = "codex_scan_proposal"
                f["evidence"] = "Source pixels show corrected spelling"
            f["proposal_note"] = "Inspected original source pixels"
        reviewed = copy.deepcopy(proposals)
        for f in reviewed["findings"]:
            if f["proposed"] is not None:
                f["review"] = {"status": "approved", "note": "Independently confirmed pixels"}
            if f["observed"] == "Oddprint":
                f["review"] = {"status": None, "note":
                    "SOURCE_FAITHFUL_NONLEXICAL_VERIFIED: Scan shows irregular printing, do not reuse."}
        paths = {name: directory / (name + ".json") for name in
                 ("probe2", "proposals", "reviewed", "progress")}
        for name_key, data in (("probe2", baseline), ("proposals", proposals), ("reviewed", reviewed)):
            write(paths[name_key], data)
        decisions = {}
        overrides = {}
        if name == "Ancients":
            decisions = {
                "schopenhuaer": {"decision": "rejected", "finding_id": None, "note": BULK_REPAIR_NOTE},
                "oddprint": {"decision": "rejected", "finding_id": None, "note": BULK_SOURCE_NOTE},
                "otherword": {"decision": "rejected", "finding_id": None, "note": "Other human reason"},
                "acceptable": {"decision": "accepted",
                               "finding_id": findings[7]["id"], "note": "Observed on scan"},
            }
            overrides = {
                findings[5]["id"]: {"observed": "mistkae", "decision": "approved",
                                    "replacement": "mistake", "note": "Human examined scan"}
            }
        snapshots = {
            "baseline_sha256": sha(paths["probe2"]),
            "proposals_sha256": sha(paths["proposals"]),
            "reviewed_sha256": sha(paths["reviewed"]),
            "lexicon_sha256": baseline["inputs"]["lexicon_sha256"],
            "scans_sha256": baseline["inputs"]["source_dir_sha256"],
        }
        write(paths["progress"], {
            "format": "human_lexicon_review_progress_v2",
            "snapshots": snapshots, "decisions": decisions, "repair_decisions": overrides,
        })
        return paths

    def entry(self, paths):
        return {"name": paths["probe2"].parent.name,
                **{field: str(path.relative_to(self.root)) for field, path in paths.items()}}

    def load(self):
        return manifest_books(self.manifest)

    def analyze(self):
        return analyze_books(self.load(), top=20, examples=2)

    def test_read_only_post_bulk_snapshot_with_two_books(self):
        before = {p: sha(p) for paths in (self.book1, self.book2)
                  for p in paths.values()}
        report = self.analyze()
        self.assertEqual(report["format"], FORMAT)
        self.assertEqual(report["summary"]["books"], 2)
        self.assertEqual(report["summary"]["unknown_occurrences"], 11)
        self.assertEqual(report["summary"]["book_distinct_forms"], 10)
        self.assertEqual(report["summary"]["corpus_distinct_forms"], 8)
        self.assertEqual(report["summary"]["pending_forms"], 6)
        self.assertEqual(report["summary"]["pending_occurrences"], 6)
        self.assertEqual(
            report["summary"]["form_dispositions"]["bulk_excluded_all_repair_verified"], 1)
        self.assertEqual(
            report["summary"]["occurrence_dispositions"]["bulk_excluded_all_repair_verified"], 2)
        self.assertEqual(
            report["summary"]["form_dispositions"]["bulk_excluded_source_faithful_nonlexical"], 1)
        self.assertEqual(report["summary"]["repair_states"]["human_approved_repair"], 1)
        self.assertEqual(report["summary"]["repair_states"]["codex_verified_repair"], 3)
        self.assertEqual({p: sha(p) for p in before}, before)

    def test_bulk_rejections_preserved_without_becoming_ocr_errors(self):
        report = self.analyze()
        items = {item["canonical"]: item for item in report["top_bulk_excluded_forms"]}
        self.assertEqual(items["schopenhuaer"]["dispositions"],
                         {"bulk_excluded_all_repair_verified": 2})
        self.assertEqual(items["oddprint"]["dispositions"],
                         {"bulk_excluded_source_faithful_nonlexical": 1})
        self.assertEqual(items["schopenhuaer"]["repair_states"],
                         {"codex_verified_repair": 2})
        self.assertIn("NOT proof", report["interpretation"])

    def test_unclassified_rejection_not_treated_as_verified_repair(self):
        report = self.analyze()
        self.assertEqual(
            report["summary"]["form_dispositions"][
                "human_rejected_vocabulary_reason_unclassified"], 1)
        self.assertNotIn("otherword",
                         {item["canonical"] for item in report["top_pending_forms"]})

    def test_cross_book_recurrence_and_conservative_signals(self):
        report = self.analyze()
        recurring = {item["canonical"]: item
                     for item in report["recurring_cross_book_forms"]}
        self.assertEqual(recurring["didnt"]["occurrences"], 2)
        self.assertEqual(recurring["didnt"]["pending_occurrences"], 2)
        self.assertIn("contraction_like", recurring["didnt"]["signals"])
        self.assertIn("mixed_greek_latin", recurring["σkiεpov"]["signals"])
        self.assertEqual(report["signals_by_disposition"][
            "pending_human_vocabulary_review"]["contraction_like"], 2)

    def test_repairs_are_patterns_not_executions(self):
        report = self.analyze()
        pairs = {(p["observed"], p["replacement"]): p["occurrences"]
                 for p in report["verified_repair_pairs"]}
        self.assertEqual(pairs[("Schopenhuaer", "Schopenhauer")], 2)
        self.assertEqual(pairs[("mistkae", "mistake")], 1)
        self.assertEqual(pairs[("Routlledge", "Routledge")], 1)
        self.assertEqual(report["books"][0]["snapshots"]["progress_sha256"],
                         sha(self.book1["progress"]))

    def test_refuses_stale_progress_and_tampered_agent_handoff(self):
        old = self.book1["progress"].read_bytes()
        state, _ = read_json(self.book1["progress"])
        state["snapshots"]["reviewed_sha256"] = "stale"
        write(self.book1["progress"], state)
        with self.assertRaisesRegex(ValueError, "different frozen"):
            self.analyze()
        self.book1["progress"].write_bytes(old)
        reviewed, _ = read_json(self.book1["reviewed"])
        reviewed["findings"][0]["observed"] = "tampered"
        write(self.book1["reviewed"], reviewed)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_bulk_claim_without_support_fails(self):
        progress, _ = read_json(self.book1["progress"])
        progress["decisions"]["didnt"] = {
            "decision": "rejected", "finding_id": None, "note": BULK_REPAIR_NOTE}
        write(self.book1["progress"], progress)
        with self.assertRaisesRegex(ValueError, "Bulk repair exclusion"):
            self.analyze()

    def test_human_override_rejection_changes_effective_view(self):
        progress, _ = read_json(self.book2["progress"])
        reviewed, _ = read_json(self.book2["reviewed"])
        fid = next(f["id"] for f in reviewed["findings"]
                   if f["observed"] == "Routlledge")
        progress["repair_decisions"][fid] = {
            "observed": "Routlledge", "decision": "rejected",
            "replacement": None, "note": "Human inspected and disagreed"}
        write(self.book2["progress"], progress)
        report = self.analyze()
        self.assertEqual(report["summary"]["repair_states"]["human_rejected_repair"], 1)
        self.assertEqual(report["summary"]["repair_states"]["codex_verified_repair"], 2)
        self.assertNotIn(("Routlledge", "Routledge"),
                         {(p["observed"], p["replacement"])
                          for p in report["verified_repair_pairs"]})

    def test_per_book_count_mismatch_reports_snapshot_cause(self):
        proposed, _ = read_json(self.book1["proposals"])
        proposed["findings"].pop()
        write(self.book1["proposals"], proposed)
        with self.assertRaisesRegex(ValueError, "Ancients: Proposal report added or omitted") as raised:
            self.analyze()
        message = str(raised.exception)
        self.assertIn("Probe 2 expects 8 lexical findings; proposals contain 7", message)
        self.assertIn("IDs only in Probe 2: 1", message)
        self.assertIn("progress.proposals_sha256 differs", message)

    def test_check_only_reports_every_book_without_publishing(self):
        cmd = [sys.executable, str(ROOT / "analyze_lexical_corpus.py"),
               "--manifest", str(self.manifest), "--check-only"]
        valid = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(valid.returncode, 0, valid.stderr)
        self.assertIn("PASS Ancients", valid.stdout)
        self.assertIn("PASS Moderns", valid.stdout)
        self.assertIn("2 pass, 0 fail", valid.stdout)
        proposed, _ = read_json(self.book1["proposals"])
        proposed["findings"].pop()
        write(self.book1["proposals"], proposed)
        invalid = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 1, invalid.stderr)
        self.assertIn("FAIL Ancients:", invalid.stdout)
        self.assertIn("PASS Moderns:", invalid.stdout)
        self.assertIn("1 pass, 1 fail", invalid.stdout)
        self.assertFalse((self.root / "analysis.json").exists())


    def test_classification_preserves_every_occurrence_and_both_outcome_axes(self):
        before = {p: sha(p) for paths in (self.book1, self.book2)
                  for p in paths.values()}
        report = build_classification([__import__(
            "analyze_lexical_corpus").load_book(book) for book in self.load()])
        self.assertEqual(report["format"], CLASSIFICATION_FORMAT)
        self.assertEqual(report["summary"]["occurrences"], 11)
        self.assertEqual(report["summary"]["pending_occurrences"], 6)
        self.assertEqual(len(report["occurrences"]), 11)
        self.assertEqual(len({(x["book"], x["finding_id"])
                             for x in report["occurrences"]}), 11)
        excluded = next(x for x in report["occurrences"]
                        if x["observed"] == "Schopenhuaer")
        self.assertEqual(excluded["disposition"], "bulk_excluded_all_repair_verified")
        self.assertEqual(excluded["repair_state"], "codex_verified_repair")
        self.assertEqual(excluded["primary_investigation_route"],
                         "existing_verified_repair_candidate")
        other = next(x for x in report["occurrences"] if x["observed"] == "Otherword")
        self.assertEqual(other["primary_investigation_route"], "previously_triaged")
        self.assertEqual({p: sha(p) for p in before}, before)

    def test_exact_contraction_prefix_and_unsafe_replacement_are_distinct(self):
        original = "doesn"
        prefix = "Before "
        text = "Before doesn't go away"
        start = len(prefix.encode("utf-8"))
        entry = {
            "book": "Book", "finding_id": "p:unrecognized_token:7", "page": "p",
            "observed": original, "canonical": original,
            "disposition": "pending_human_vocabulary_review",
            "repair_state": "no_verified_repair", "replacement": None,
            "signals": ["adjacent_apostrophe"],
            "source_image": "p.png", "paddle_markdown": "p.md",
            "start_byte": start, "end_byte": start + len(original),
            "ocr_context": {"text": text, "start_byte": 0,
                            "end_byte": len(text.encode("utf-8"))},
            "proposal_note": "SCAN_VERIFIED: observed span is a partial token",
            "verification_note": "The source has an intact contraction",
            "human_note": None,
        }
        good = classify_occurrence(entry)
        self.assertEqual(good["primary_investigation_route"],
                         "tokenizer_boundary_experiment")
        self.assertIn("exact_contraction_prefix_span", good["clues_not_conclusions"])
        self.assertEqual(good["proposer_note_tag"], "scan_verified")
        self.assertFalse(good["repair_may_duplicate_existing_suffix"])

        approved = dict(entry, repair_state="codex_verified_repair",
                        replacement="doesn't")
        danger = classify_occurrence(approved)
        self.assertEqual(danger["primary_investigation_route"], "repair_span_safety_audit")
        self.assertTrue(danger["repair_may_duplicate_existing_suffix"])
        approved_curly = dict(approved, replacement="doesn’t")
        self.assertTrue(classify_occurrence(approved_curly)["repair_may_duplicate_existing_suffix"])

        # A possessive surname is not a contraction-prefix issue.
        surname_text = "Before Schaffer's claim"
        surname = dict(entry, observed="Schaffer", canonical="schaffer",
                       end_byte=start + len("Schaffer"),
                       ocr_context={"text": surname_text, "start_byte": 0,
                                    "end_byte": len(surname_text)},
                       replacement=None)
        self.assertNotIn("exact_contraction_prefix_span",
                         classify_occurrence(surname)["clues_not_conclusions"])

    def test_notes_are_hypotheses_not_verdicts_or_repair_approvals(self):
        word = "didnt"
        text = "I didnt know"
        base = {
            "book": "Stella Maris", "finding_id": "p:unknown:2", "page": "p",
            "observed": word, "canonical": word, "disposition": "pending_human_vocabulary_review",
            "repair_state": "no_verified_repair", "replacement": None,
            "signals": ["contraction_like"], "source_image": "p.png",
            "paddle_markdown": "p.md", "start_byte": 2, "end_byte": 7,
            "ocr_context": {"text": text, "start_byte": 0, "end_byte": len(text)},
            "proposal_note": "SCAN_VERIFIED: retained printed spelling",
            "verification_note": "Scan prints didnt without an apostrophe",
            "human_note": None,
        }
        scoped = classify_occurrence(base)
        self.assertEqual(scoped["primary_investigation_route"],
                         "book_scoped_recognition_experiment")
        self.assertNotIn("structured_approved_repair_candidate",
                         scoped["clues_not_conclusions"])
        uncertain = classify_occurrence(dict(base,
            proposal_note="SCAN_UNRESOLVED: glyph ambiguous",
            verification_note="Source remains ambiguous"))
        self.assertEqual(uncertain["primary_investigation_route"],
                         "targeted_source_inspection")
        self.assertEqual(uncertain["proposer_note_tag"], "scan_unresolved")
        generic = classify_occurrence(dict(base, verification_note="looks like a name"))
        self.assertEqual(generic["primary_investigation_route"],
                         "unclassified_review_candidate")

    def test_utf8_context_fail_closed_and_classification_cli(self):
        entry = {
            "book": "A", "finding_id": "p:x:1", "page": "p",
            "observed": "é", "canonical": "é",
            "disposition": "pending_human_vocabulary_review",
            "repair_state": "no_verified_repair", "replacement": None,
            "signals": [], "source_image": "p.png", "paddle_markdown": "p.md",
            "start_byte": 1, "end_byte": 2,
            "ocr_context": {"text": "é", "start_byte": 0, "end_byte": 2},
            "proposal_note": None, "verification_note": None, "human_note": None,
        }
        with self.assertRaises(ValueError):
            classify_occurrence(entry)
        cmd = [sys.executable, str(ROOT / "analyze_lexical_corpus.py"),
               "--manifest", str(self.manifest), "--classify",
               "--out", str(self.root / "classified.json")]
        first = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        created, _ = read_json(self.root / "classified.json")
        self.assertEqual(created["summary"]["occurrences"], 11)
        self.assertEqual(len(created["occurrences"]), 11)
        second = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("already exists", second.stderr)

    def test_refuses_manifest_duplicates(self):
        write(self.manifest, {"books": [self.entry(self.book1), self.entry(self.book1)]})
        with self.assertRaisesRegex(ValueError, "unique"):
            self.load()

    def test_cli_stdout_and_exclusive_json_report(self):
        cmd = [sys.executable, str(ROOT / "analyze_lexical_corpus.py"),
               "--manifest", str(self.manifest), "--top", "2"]
        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["summary"]["books"], 2)
        out = self.root / "analysis.json"
        published = subprocess.run(cmd + ["--out", str(out)],
                                   capture_output=True, text=True)
        self.assertEqual(published.returncode, 0, published.stderr)
        self.assertTrue(out.exists())
        again = subprocess.run(cmd + ["--out", str(out)],
                               capture_output=True, text=True)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("already exists", again.stderr)
        self.assertNotEqual(
            subprocess.run(cmd + ["--out", str(self.book1["progress"])],
                           capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
