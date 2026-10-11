"""Batch joining accepts complete authorized decisions, never partial/mutated reports."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from extract_whitespace import extract
from join_whitespace import join


class JoinWhitespaceTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {
            "inputs": {"json_markdown_comparison": {"mode": "raw"},
                       "paddle_dir_sha256": "paddle", "source_dir_sha256": "scans"},
            "findings": [self.finding(i) for i in range(1, 5)]
        }
        self.baseline["findings"].append({**self.finding(5), "triggers": ["unrecognized_token"]})
        self.original = extract(self.baseline)
        self.batches = [self.batch(0, 2), self.batch(2, 4)]
        self.batches[0][1]["findings"][0]["review"]["status"] = "approved"
        self.batches[0][1]["findings"][1]["review"]["note"] = "SCAN_REJECTED: printed abbreviation"
        self.batches[1][1]["findings"][0]["review"]["status"] = "approved"
        self.batches[1][1]["findings"][1]["review"]["note"] = "SCAN_UNRESOLVED: unreadable punctuation"

    @staticmethod
    def finding(i):
        return {"id": f"page{i:03d}:period_capital:0", "page": f"page{i:03d}",
                "triggers": ["period_capital"], "source_image": f"page{i:03d}.jpg",
                "paddle_markdown": f"page{i:03d}.md", "start_byte": 0,
                "end_byte": 5, "source_md_sha256": "page hash",
                "observed": ".Next", "proposed": ". Next",
                "ocr_context": {"start_byte": 0, "end_byte": 5, "text": ".Next"},
                "review": {"status": None, "note": None}}

    def batch(self, start, stop):
        return (f"agent{start+1}.json", {"inputs": copy.deepcopy(self.original["inputs"]),
                                          "findings": copy.deepcopy(self.original["findings"][start:stop])})

    def test_join_reconstructs_complete_executor_report_and_exceptions(self):
        merged, exceptions = join(self.baseline, self.original, self.batches)
        self.assertEqual([f["id"] for f in merged["findings"]],
                         [f["id"] for f in self.original["findings"]])
        self.assertEqual([f["review"]["status"] for f in merged["findings"]],
                         ["approved", None, "approved", None])
        self.assertEqual([f["id"] for f in exceptions["findings"]],
                         [self.original["findings"][1]["id"], self.original["findings"][3]["id"]])
        self.assertEqual(self.original, extract(self.baseline))

    def test_refuse_bad_batches(self):
        operations = {
            "missing": lambda b: b[1][1]["findings"].pop(),
            "duplicate": lambda b: b[1][1]["findings"].append(copy.deepcopy(b[0][1]["findings"][0])),
            "unknown": lambda b: b[0][1]["findings"][0].update(id="made-up"),
            "changed_proposal": lambda b: b[0][1]["findings"][0].update(proposed="altered"),
            "changed_span": lambda b: b[0][1]["findings"][0].update(start_byte=9),
            "changed_context": lambda b: b[0][1]["findings"][0]["ocr_context"].update(text="different"),
            "changed_inputs": lambda b: b[0][1]["inputs"].update(paddle_dir_sha256="other"),
            "extra_review_field": lambda b: b[0][1]["findings"][0]["review"].update(evidence="made-up"),
            "invalid_status": lambda b: b[0][1]["findings"][0]["review"].update(status="rejected"),
            "unreviewed": lambda b: b[0][1]["findings"][1]["review"].update(note=None),
            "reordered": lambda b: b[0][1]["findings"].reverse(),
            "empty_batch": lambda b: b[0][1]["findings"].clear(),
        }
        for name, change in operations.items():
            with self.subTest(name=name):
                batches = copy.deepcopy(self.batches)
                change(batches)
                with self.assertRaises(ValueError):
                    join(self.baseline, self.original, batches)

    def test_refuse_stale_or_edited_extraction(self):
        original = copy.deepcopy(self.original)
        original["findings"][0]["review"]["status"] = "approved"
        with self.assertRaisesRegex(ValueError, "untouched"):
            join(self.baseline, original, self.batches)

    def test_cli_publishes_only_after_complete_validation_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            paths = [root / "probe1.json", root / "whitespace.json", root / "batches",
                     root / "reviewed.json", root / "exceptions.json"]
            baseline, original, batch_dir, output, exceptions = paths
            baseline.write_text(json.dumps(self.baseline))
            original.write_text(json.dumps(self.original))
            batch_dir.mkdir()
            for name, report in self.batches:
                (batch_dir / name).write_text(json.dumps(report))
            argv = [sys.executable, str(ROOT / "join_whitespace.py"),
                    "--baseline", str(baseline), "--report", str(original),
                    "--batches", str(batch_dir), "--out", str(output),
                    "--exceptions-out", str(exceptions)]
            (batch_dir / self.batches[1][0]).unlink()
            failed = subprocess.run(argv, capture_output=True, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse(output.exists())
            self.assertFalse(exceptions.exists())
            name, report = self.batches[1]
            (batch_dir / name).write_text(json.dumps(report))
            passed = subprocess.run(argv, capture_output=True, text=True)
            self.assertEqual(passed.returncode, 0, passed.stderr)
            self.assertEqual(json.loads(output.read_text())["findings"][0]["review"]["status"],
                             "approved")
            self.assertEqual(len(json.loads(exceptions.read_text())["findings"]), 2)
            refused = subprocess.run(argv, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)


if __name__ == "__main__":
    unittest.main()
