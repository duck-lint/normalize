"""End-to-end lexical repair and cumulative vocabulary authority regression suite."""
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

from lexicon_store import read_lexicon, sha
from extract_lexical import extract
from execute_lexical_repairs import validate_handoffs
from suggest_segments import segments


class LexicalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scans = self.root / "scans"
        self.paddle = self.root / "paddle"
        self.scans.mkdir()
        self.paddle.mkdir()
        (self.scans / "p001.png").write_bytes(b"image pixels are reviewed out-of-band")
        self.raw = "Schopenhuaer,ofthe page. Newtonic has priori.\r\n".encode("utf-8")
        (self.paddle / "p001.md").write_bytes(self.raw)
        (self.paddle / "p001_res.json").write_text(json.dumps({
            "parsing_res_list": [{"block_id": 1, "block_label": "text",
                                  "block_content": self.raw.decode("utf-8")}]}))
        self.lexicon = self.root / "global-lexicon.json"
        self.lexicon.write_text('{"format": "normalize_lexicon_v1", "entries": []}\n')
        self.lex_before = self.lexicon.read_bytes()
        self.probe1 = self.root / "probe1.json"
        self.run_script("normalize_probe.py", "--scans", self.scans, "--paddle", self.paddle,
                        "--out", self.probe1)
        white = self.root / "white.json"
        self.run_script("extract_whitespace.py", "--report", self.probe1, "--out", white)
        white_data = json.loads(white.read_bytes())
        for f in white_data["findings"]:
            f["review"]["status"] = "approved"
        white.write_text(json.dumps(white_data))
        self.whitespace = self.root / "whitespace"
        self.run_script("execute_repairs.py", "--baseline", self.probe1, "--report", white,
                        "--paddle", self.paddle, "--out", self.whitespace, "--execute")
        self.probe2 = self.root / "probe2.json"
        self.run_script("normalize_probe.py", "--scans", self.scans, "--paddle", self.whitespace,
                        "--lexicon", self.lexicon, "--out", self.probe2)
        self.extract_path = self.root / "lexical.json"
        self.run_script("extract_lexical.py", "--report", self.probe2, "--out", self.extract_path)
        self.extracted = json.loads(self.extract_path.read_bytes())
        self.proposals = copy.deepcopy(self.extracted)
        for finding in self.proposals["findings"]:
            if finding["observed"] == "Schopenhuaer":
                finding["proposed"] = "Schopenhauer"
            if finding["observed"] == "ofthe":
                finding["proposed"] = "of the"
            if finding["proposed"] is not None:
                finding["proposal_source"] = "codex_scan_proposal"
                finding["evidence"] = "Exact occurrence confirmed visually against scan"
            if finding["observed"] == "Newtonic":
                finding["lexicon_suggestion"] = True
        self.proposals_path = self.root / "proposals.json"
        self.proposals_path.write_text(json.dumps(self.proposals))
        self.reviewed = copy.deepcopy(self.proposals)
        for finding in self.reviewed["findings"]:
            if finding["proposed"] is not None:
                finding["review"]["status"] = "approved"
                finding["review"]["note"] = "Second visual inspection approved exact printing"
        self.reviewed_path = self.root / "verified.json"
        self.reviewed_path.write_text(json.dumps(self.reviewed))
        newtonic = next(f for f in self.reviewed["findings"] if f["observed"] == "Newtonic")
        self.approvals_path = self.root / "human-vocabulary.json"
        self.approvals_path.write_text(json.dumps({
            "format": "human_lexicon_approvals_v1",
            "source_report_sha256": sha(self.probe2.read_bytes()),
            "lexicon_sha256": sha(self.lex_before),
            "entries": [{"word": "Newtonic", "finding_id": newtonic["id"],
                         "approved": True, "note": "Human checked this legitimate adjective"}]
        }))
        self.lexical_dir = self.root / "lexical-output"

    def run_script(self, script, *args, expected=0):
        values = [str(arg) for arg in args]
        proc = subprocess.run([sys.executable, str(ROOT / script), *values],
                              cwd=self.root, capture_output=True, text=True)
        self.assertEqual(proc.returncode, expected, proc.stdout + proc.stderr)
        return proc

    def execute_args(self):
        return ("--baseline", self.probe2, "--proposals", self.proposals_path,
                "--reviewed", self.reviewed_path, "--paddle", self.whitespace,
                "--lexicon", self.lexicon, "--lexicon-approvals", self.approvals_path,
                "--out", self.lexical_dir)

    def test_two_scan_sessions_and_human_admission_then_reprobe(self):
        self.assertEqual(self.raw, (self.paddle / "p001.md").read_bytes())
        self.assertEqual(len(self.extracted["vocabulary"]),
                         len({f["observed"].casefold() for f in self.extracted["findings"]}))
        self.run_script("execute_lexical_repairs.py", *self.execute_args())
        self.assertFalse(self.lexical_dir.exists())
        self.assertEqual(self.lex_before, self.lexicon.read_bytes())
        self.run_script("execute_lexical_repairs.py", *self.execute_args(), "--execute")
        self.assertIn(b"Schopenhauer, of the page", (self.lexical_dir / "p001.md").read_bytes())
        self.assertEqual(self.raw, (self.paddle / "p001.md").read_bytes())
        self.assertEqual((self.whitespace / "p001_res.json").read_bytes(),
                         (self.lexical_dir / "p001_res.json").read_bytes())
        self.assertEqual((self.whitespace / "execution_report.json").read_bytes(),
                         (self.lexical_dir / "execution_report.json").read_bytes())
        data, _, keys = read_lexicon(self.lexicon)
        self.assertIn("newtonic", keys)
        self.assertEqual(len(data["entries"]), 1)
        post = self.root / "probe3.json"
        self.run_script("normalize_probe.py", "--scans", self.scans, "--paddle", self.lexical_dir,
                        "--lexicon", self.lexicon, "--out", post)
        p = json.loads(post.read_bytes())
        self.assertEqual(p["inputs"]["json_markdown_comparison"]["mode"],
                         "verified_executed_lexical_and_whitespace")
        self.assertEqual(p["inputs"]["json_markdown_comparison"]["lexical_executed_findings"], 2)
        tokens = [f["observed"] for f in p["findings"] if "unrecognized_token" in f["triggers"]]
        self.assertNotIn("Newtonic", tokens)
        self.assertNotIn("Schopenhuaer", tokens)
        self.assertNotIn("ofthe", tokens)
        self.assertFalse(any(f["rule"] == "json_markdown_difference:text" for f in p["findings"]))
        self.assertTrue(p["json_markdown_exceptions"])
        ids = p["json_markdown_exceptions"][0]["page_executed_finding_ids"]
        self.assertGreaterEqual(len(ids), 3)  # whitespace + both lexical repairs

    def test_unmodified_extraction_proposals_and_independent_review(self):
        self.assertTrue(all(f["review"] == {"status": None, "note": None}
                            for f in self.extracted["findings"]))
        validate_handoffs(json.loads(self.probe2.read_bytes()), self.proposals, self.reviewed)
        edited = copy.deepcopy(self.reviewed)
        edited["findings"][0]["proposed"] = "unverified change"
        with self.assertRaisesRegex(ValueError, "Verifier changed"):
            validate_handoffs(json.loads(self.probe2.read_bytes()), self.proposals, edited)
        edited = copy.deepcopy(self.proposals)
        edited["findings"][0]["start_byte"] += 1
        with self.assertRaisesRegex(ValueError, "Proposer changed"):
            validate_handoffs(json.loads(self.probe2.read_bytes()), edited, self.reviewed)

    def test_invalid_human_admission_never_publishes_or_mutates_lexicon(self):
        bad = json.loads(self.approvals_path.read_bytes())
        bad["entries"][0]["word"] = "ofthe"
        self.approvals_path.write_text(json.dumps(bad))
        self.run_script("execute_lexical_repairs.py", *self.execute_args(), "--execute", expected=2)
        self.assertFalse(self.lexical_dir.exists())
        self.assertEqual(self.lex_before, self.lexicon.read_bytes())

    def test_stale_lexicon_is_a_hard_error(self):
        data = json.loads(self.lexicon.read_bytes())
        self.lexicon.write_text(json.dumps(data, indent=2))
        self.run_script("execute_lexical_repairs.py", *self.execute_args(), "--execute", expected=2)
        self.assertFalse(self.lexical_dir.exists())

    def test_lexical_edits_provenance_must_validate_against_derived_bytes(self):
        self.run_script("execute_lexical_repairs.py", *self.execute_args(), "--execute")
        source = self.lexical_dir / "p001.md"
        source.write_bytes(source.read_bytes().replace(b"Schopenhauer", b"Schopenhuer"))
        post = self.root / "tamper.json"
        self.run_script("normalize_probe.py", "--scans", self.scans,
                        "--paddle", self.lexical_dir, "--lexicon", self.lexicon,
                        "--out", post, expected=2)
        self.assertFalse(post.exists())

    def test_segmentation_uses_lexicon_and_never_changes_characters(self):
        recognized = {"of", "the", "prior", "i"}
        counts = {"of": 10, "the": 15, "prior": 1, "i": 1}
        hints = segments("ofthe", lambda word: word in recognized, counts)
        self.assertEqual(hints[0]["proposed"], "of the")
        self.assertEqual(hints[0]["proposed"].replace(" ", ""), "ofthe")
        self.assertTrue(segments("priori", lambda word: word in recognized, counts))
        recognized.add("priori")  # a separately human-approved lexicon entry
        self.assertEqual(segments("priori", lambda word: word in recognized, counts), [])


if __name__ == "__main__":
    unittest.main()
