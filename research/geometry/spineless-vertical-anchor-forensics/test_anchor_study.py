"""Falsification checks for the frozen spineless vertical-anchor study."""

from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).with_name("run_anchor_study.py")
SPEC = importlib.util.spec_from_file_location("anchor_study", SCRIPT)
assert SPEC and SPEC.loader
STUDY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STUDY)


class FrozenAnchorStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = STUDY.run()

    def test_exact_saved_observations_and_pixel_hashes_reproduce(self) -> None:
        expected = {"26": 202, "27": 264, "40": 139, "41": 307, "52": 148, "53": 221}
        self.assertFalse(self.result["ocr_rerun"])
        self.assertTrue(self.result["all_variants_reuse_frozen_tokens"])
        self.assertEqual({page: record["token_count"] for page, record in self.result["pages"].items()}, expected)
        self.assertTrue(all(record["production_expected_membership_reproduced"] for record in self.result["pages"].values()))

    def test_center_shadow_matches_production_and_three_known_traces(self) -> None:
        self.assertEqual(self.result["pages"]["26"]["variants"]["target_trace"]["center_y"]["running_median"], 607.5)
        self.assertEqual(self.result["pages"]["26"]["variants"]["target_trace"]["center_y"]["anchor_value"], 612.0)
        self.assertEqual(self.result["pages"]["27"]["variants"]["target_trace"]["center_y"]["running_median"], 167.0)
        self.assertEqual(self.result["pages"]["53"]["variants"]["target_trace"]["center_y"]["running_median"], 502.0)
        self.assertEqual(self.result["pages"]["27"]["variants"]["target_trace"]["y1"]["decision"], "starts_new_band")
        self.assertEqual(self.result["pages"]["53"]["variants"]["target_trace"]["y1"]["decision"], "starts_new_band")

    def test_tokens_are_identity_equivalent_across_anchors_and_orders(self) -> None:
        for page, record in self.result["pages"].items():
            rows = record["pixel_oracle_rows"]
            expected = [(token["source_row"], token["x0"], token["y0"], token["x1"], token["y1"])
                        for row in rows for token in row["tokens"]]
            self.assertEqual(len(expected), record["oracle_token_count"], page)
            self.assertEqual(len({item[0] for item in expected}), len(expected), page)
            self.assertEqual(record["variants"]["center_y"]["production"]["grouping"]["values"].keys(),
                             record["variants"]["y1"]["production"]["grouping"]["values"].keys())
            for anchor in ("center_y", "y1"):
                for case in record["variants"]["sensitivity"][anchor]["cases"]:
                    self.assertEqual(case["token_count"], record["token_count"], (page, anchor, case["mode"]))

    def test_study_never_invokes_tesseract(self) -> None:
        import pytesseract

        original = pytesseract.image_to_data
        def forbidden(*_args, **_kwargs):
            raise AssertionError("frozen-anchor study must not rerun OCR")
        pytesseract.image_to_data = forbidden
        try:
            result = STUDY.run()
        finally:
            pytesseract.image_to_data = original
        self.assertFalse(result["ocr_rerun"])

    def test_row_oracle_covers_more_than_known_failures(self) -> None:
        self.assertEqual(sum(r["oracle_row_count"] for r in self.result["pages"].values()), 105)
        for record in self.result["pages"].values():
            self.assertTrue(all(row["source_rows"] for row in record["pixel_oracle_rows"]))
            self.assertTrue(all(row["pixel_region"] for row in record["pixel_oracle_rows"]))

    def test_bottom_edge_harms_and_target_failure_are_identity_complete(self) -> None:
        self.assertEqual(self.result["row_classification_counts"]["center_y"]["production"]["correct_single_band"], 87)
        self.assertEqual(self.result["row_classification_counts"]["y1"]["production"]["correct_single_band"], 8)
        self.assertEqual(self.result["row_classification_counts"]["y1"]["vertical_bands_production"]["destructive_merge_with_neighbor"], 6)
        for page, events in self.result["row_transition_ledger"].items():
            event_ids = {event["row_id"] for event in events}
            record = self.result["pages"][page]
            row_membership = {source: row["row_id"] for row in self.result["pages"][page]["pixel_oracle_rows"]
                              for source in row["source_rows"]}
            center = record["variants"]["center_y"]["production"]
            bottom = record["variants"]["y1"]["production"]
            for row_id in center["row_classifications"]:
                changed = (center["row_classifications"][row_id] != bottom["row_classifications"][row_id]
                           or center["vertical_row_classifications"][row_id]
                           != bottom["vertical_row_classifications"][row_id])
                if changed:
                    self.assertIn(row_id, event_ids, (page, row_id))
            for event in events:
                self.assertTrue(event["source_rows"], (page, event["row_id"]))
                self.assertTrue(event["boxes"], (page, event["row_id"]))
                if event["y1_vertical"] == "destructive_merge_with_neighbor":
                    self.assertTrue(any(any(row_membership.get(source) != event["row_id"]
                                            for source in group if source in row_membership)
                                        for group in event["y1_vertical_band_memberships"]))

    def test_synthetic_controls_expose_both_anchor_failure_modes(self) -> None:
        cases = self.result["synthetic_controls"]
        self.assertTrue(cases["equal_bottom_varying_heights"]["y1"]["correct"])
        self.assertFalse(cases["equal_bottom_varying_heights"]["center_y"]["correct"])
        self.assertTrue(cases["equal_center_varying_heights"]["center_y"]["correct"])
        self.assertFalse(cases["equal_center_varying_heights"]["y1"]["correct"])
        self.assertTrue(cases["two_adjacent_rows_equal_height"]["center_y"]["correct"])
        self.assertTrue(cases["two_adjacent_rows_equal_height"]["y1"]["correct"])
        self.assertFalse(cases["close_rows_nearly_overlapping_bottoms"]["y1"]["correct"])

    def test_production_geometry_is_unchanged_and_no_binary_is_tracked(self) -> None:
        changed = subprocess.run(["git", "diff", "--name-only", "HEAD", "--", "src/normalize/geometry.py"],
                                 cwd=ROOT, check=True, text=True, capture_output=True).stdout.strip()
        self.assertEqual(changed, "")
        tracked = subprocess.run(["git", "ls-files", "*.jpg", "*.jpeg", "*.png", "*.pdf"],
                                 cwd=ROOT, check=True, text=True, capture_output=True).stdout.strip()
        self.assertEqual(tracked, "")


if __name__ == "__main__":
    unittest.main()
