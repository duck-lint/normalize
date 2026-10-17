"""Regression: executor refuses edits that duplicate an existing apostrophe+t."""
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from execute_lexical_repairs import build, validate_lexical_repair_boundary


class LexicalRepairBoundaryTests(unittest.TestCase):
    def test_exact_existing_ascii_suffix_refused(self):
        page = b"Actually it doesn't matter."
        start = page.index(b"doesn")
        with self.assertRaisesRegex(ValueError, "duplicate an existing contraction suffix"):
            validate_lexical_repair_boundary(
                page, start, start + len(b"doesn"), "doesn", "doesn't", "p01:unknown:1")

    def test_curly_suffix_and_ascii_normalization_refused(self):
        page = "Actually it doesn’t matter.".encode("utf-8")
        start = page.index(b"doesn")
        for proposed in ("doesn't", "doesn’t"):
            with self.subTest(proposed=proposed):
                with self.assertRaisesRegex(ValueError, "p01:unknown:1"):
                    validate_lexical_repair_boundary(
                        page, start, start + 5, "doesn", proposed, "p01:unknown:1")

    def test_safe_edits_not_blocked(self):
        cases = [
            (b"actually it doesnt matter", "doesnt", "doesn't"),
            (b"actually it doesn't matter", "doesn", "doesnt"),
            ("A name Schaffer's idea".encode("utf-8"), "Schaffer", "Schaffner"),
            (b"we dont know", "dont", "don't"),
            (b"her didnt have time", "didnt", "didn't"),
        ]
        for page, observed, proposed in cases:
            with self.subTest(observed=observed, proposed=proposed):
                start = page.index(observed.encode("utf-8"))
                validate_lexical_repair_boundary(
                    page, start, start + len(observed.encode("utf-8")),
                    observed, proposed, "p01:unknown:1")

    def test_build_fails_before_any_derived_changes_for_approved_partial_span(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            page = folder / "p001.md"
            raw = b"The proposal doesn't resolve the issue."
            page.write_bytes(raw)
            start = raw.index(b"doesn")
            finding = {
                "id": "p001:unrecognized_token:13", "paddle_markdown": "p001.md",
                "observed": "doesn", "proposed": "doesn't",
                "start_byte": start, "end_byte": start + 5,
                "source_md_sha256": hashlib.sha256(raw).hexdigest(),
                "review": {"status": "approved", "note": "Reviewer checked source pixels"},
            }
            baseline = {"inputs": {"source_dir_sha256": "source",
                                   "paddle_dir_sha256": "paddle"}}
            reviewed = {"findings": [finding]}
            with self.assertRaisesRegex(ValueError, finding["id"]):
                build(baseline, reviewed, {"p001.md": page},
                      "old-lexicon", "new-lexicon", [])
            self.assertEqual(page.read_bytes(), raw)

    def test_build_applies_real_full_span_repair_safely(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            page = folder / "p001.md"
            raw = b"It doesnt matter."
            page.write_bytes(raw)
            start = raw.index(b"doesnt")
            finding = {
                "id": "p001:unrecognized_token:3", "paddle_markdown": "p001.md",
                "observed": "doesnt", "proposed": "doesn't",
                "start_byte": start, "end_byte": start + len("doesnt"),
                "source_md_sha256": hashlib.sha256(raw).hexdigest(),
                "review": {"status": "approved", "note": "Reviewer checked source pixels"},
            }
            baseline = {"inputs": {"source_dir_sha256": "source",
                                   "paddle_dir_sha256": "paddle"}}
            derived, ledger = build(
                baseline, {"findings": [finding]}, {"p001.md": page},
                "old-lexicon", "new-lexicon", [])
            self.assertEqual(derived["p001.md"], b"It doesn't matter.")
            self.assertEqual(ledger["approved_findings"], 1)
            self.assertEqual(page.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
