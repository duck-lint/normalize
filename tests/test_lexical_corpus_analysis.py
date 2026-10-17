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
        self.assertEqual(report["summary"]["pending_occurrences"], 7)
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
