"""Parallel lexical batch joins preserve both frozen executor handoffs."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from execute_lexical_repairs import validate_handoffs
from extract_lexical import extract
from join_lexical import join


class JoinLexicalTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {
            "inputs": {"lexicon_sha256": "lexicon-snapshot", "source_dir_sha256": "scans"},
            "findings": [self.finding(i) for i in range(1, 5)]
        }
        self.baseline["findings"].append({**self.finding(5), "triggers": ["period_capital"]})
        self.extracted = extract(self.baseline)
        self.proposal_batches = self.split(self.extracted)
        for _, batch in self.proposal_batches:
            for finding in batch["findings"]:
                finding["proposal_note"] = "SCAN_VERIFIED: original spelling seen in image"
        first = self.proposal_batches[0][1]["findings"][0]
        first.update(proposed="corrected", proposal_source="codex_scan_proposal",
                     evidence="Original scan shows corrected glyph")
        second = self.proposal_batches[0][1]["findings"][1]
        second.update(lexicon_suggestion=True)
        self.proposals = join("proposals", self.baseline, self.extracted,
                              self.proposal_batches)
        self.review_batches = self.split(self.proposals)
        for _, batch in self.review_batches:
            for finding in batch["findings"]:
                finding["review"]["note"] = "NO_PROPOSAL: inspected source occurrence"
        self.review_batches[0][1]["findings"][0]["review"] = {
            "status": "approved", "note": "Independent scan confirms corrected glyph"}
        self.reviewed = join("reviewed", self.baseline, self.proposals,
                             self.review_batches)

    @staticmethod
    def finding(i):
        return {"id": f"page{i:03d}:unrecognized_token:1", "page": f"page{i:03d}",
                "triggers": ["unrecognized_token"], "source_image": f"page{i:03d}.jpg",
                "paddle_markdown": f"page{i:03d}.md", "source_md_sha256": "pagehash",
                "start_byte": 1, "end_byte": 8, "observed": f"token{i}",
                "proposed": None, "proposal_source": None, "evidence": None,
                "ocr_context": {"start_byte": 0, "end_byte": 9, "text": f" token{i} "},
                "review": {"status": None, "note": None}}

    @staticmethod
    def split(report):
        result = []
        for i, (start, end) in enumerate(((0, 2), (2, 4)), 1):
            batch = copy.deepcopy(report)
            batch["findings"] = batch["findings"][start:end]
            result.append((f"agent{i}.json", batch))
        return result

    def test_complete_two_handoffs_validate_with_unchanged_executor(self):
        self.assertEqual(len(self.proposals["findings"]), 4)
        self.assertEqual(self.proposals["vocabulary"], self.extracted["vocabulary"])
        self.assertEqual(self.proposals["findings"][0]["proposed"], "corrected")
        self.assertEqual(self.reviewed["findings"][0]["review"]["status"], "approved")
        self.assertIsNone(self.reviewed["findings"][1]["review"]["status"])
        self.assertEqual(self.proposals["findings"][0]["review"]["status"], None)
        validate_handoffs(self.baseline, self.proposals, self.reviewed)

    def test_proposal_join_refuses_invalid_outputs(self):
        alterations = {
            "missing": lambda b: b[1][1]["findings"].pop(),
            "duplicate": lambda b: b[1][1]["findings"].append(copy.deepcopy(b[0][1]["findings"][0])),
            "unknown": lambda b: b[0][1]["findings"][0].update(id="unknown"),
            "reordered": lambda b: b[0][1]["findings"].reverse(),
            "changed_observation": lambda b: b[0][1]["findings"][0].update(observed="wrong"),
            "changed_context": lambda b: b[0][1]["findings"][0]["ocr_context"].update(text="wrong"),
            "changed_vocabulary": lambda b: b[0][1]["vocabulary"].clear(),
            "changed_inputs": lambda b: b[0][1]["inputs"].update(lexicon_sha256="new"),
            "changed_review": lambda b: b[0][1]["findings"][0]["review"].update(status="approved"),
            "unreviewed": lambda b: b[1][1]["findings"][0].update(proposal_note=None),
            "bad_proposal": lambda b: b[0][1]["findings"][0].update(evidence=None),
            "empty_batch": lambda b: b[0][1]["findings"].clear(),
        }
        for label, edit in alterations.items():
            with self.subTest(label=label):
                batches = copy.deepcopy(self.proposal_batches)
                edit(batches)
                with self.assertRaises((ValueError, KeyError)):
                    join("proposals", self.baseline, self.extracted, batches)

    def test_verification_join_refuses_invalid_outputs(self):
        alterations = {
            "missing": lambda b: b[1][1]["findings"].pop(),
            "duplicate": lambda b: b[1][1]["findings"].append(copy.deepcopy(b[0][1]["findings"][0])),
            "changed_proposal": lambda b: b[0][1]["findings"][0].update(proposed="tampered"),
            "changed_note": lambda b: b[0][1]["findings"][0].update(proposal_note="tampered"),
            "changed_vocabulary": lambda b: b[0][1].update(vocabulary=[]),
            "unreviewed": lambda b: b[1][1]["findings"][0]["review"].update(note=None),
            "bad_status": lambda b: b[0][1]["findings"][0]["review"].update(status="rejected"),
            "approve_unproposed": lambda b: b[1][1]["findings"][0]["review"].update(status="approved"),
            "extra_review": lambda b: b[0][1]["findings"][0]["review"].update(foo="bar"),
            "reordered": lambda b: b[0][1]["findings"].reverse(),
        }
        for label, edit in alterations.items():
            with self.subTest(label=label):
                batches = copy.deepcopy(self.review_batches)
                edit(batches)
                with self.assertRaises((ValueError, KeyError)):
                    join("reviewed", self.baseline, self.proposals, batches)

    def test_frozen_source_and_probe_are_required(self):
        stale = copy.deepcopy(self.extracted)
        stale["findings"][0]["observed"] = "wrong"
        with self.assertRaises(ValueError):
            join("proposals", self.baseline, stale, self.proposal_batches)
        stale = copy.deepcopy(self.proposals)
        stale["findings"][0]["proposed"] = "unsubstantiated"
        with self.assertRaises(ValueError):
            join("reviewed", self.baseline, stale, self.review_batches)

    def test_cli_join_both_stages_and_refuse_incomplete_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline = root / "probe2.json"
            extraction = root / "lexical-extracted.json"
            batch_dir = root / "outputs"
            batch_dir.mkdir()
            proposals_path = root / "lexical-proposals.json"
            reviewed_path = root / "lexical-reviewed.json"
            baseline.write_text(json.dumps(self.baseline))
            extraction.write_text(json.dumps(self.extracted))

            def command(stage, source, output):
                return [sys.executable, str(ROOT / "join_lexical.py"), "--stage", stage,
                        "--baseline", str(baseline), "--source", str(source),
                        "--batches", str(batch_dir), "--out", str(output)]

            for name, batch in self.proposal_batches:
                (batch_dir / name).write_text(json.dumps(batch))
            (batch_dir / "agent2.json").unlink()
            result = subprocess.run(command("proposals", extraction, proposals_path),
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(proposals_path.exists())
            (batch_dir / "agent2.json").write_text(json.dumps(self.proposal_batches[1][1]))
            result = subprocess.run(command("proposals", extraction, proposals_path),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(proposals_path.read_text()), self.proposals)
            for name, batch in self.review_batches:
                (batch_dir / name).write_text(json.dumps(batch))
            result = subprocess.run(command("reviewed", proposals_path, reviewed_path),
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(reviewed_path.read_text()), self.reviewed)
            self.assertNotEqual(subprocess.run(command("reviewed", proposals_path, reviewed_path),
                                               capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
