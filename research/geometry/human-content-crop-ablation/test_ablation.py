"""Artifact-level checks for the human content-crop ablation.

These tests deliberately consume the captured JSON instead of invoking OCR a
second time. The committed observations are the experiment's frozen record.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PAGES = ("26", "27", "40", "41", "52", "53")
REQUIRED_COMMITS = (
    "53ece235af82ef37fc7fe49be027301a25a8d104",
    "2d7918efa63e89357fa4bc6239da1aadbe2ac367",
    "22912345ceee5330bffe02bc189ce2b38075ce52",
    "5b644c1edad2dc0318b7cd8fbeee54299a5c7577",
)


def read_json(name: str):
    return json.loads((HERE / name).read_text())


class HumanCropAblationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = read_json("results.json")
        cls.rows = read_json("row-comparison.json")
        cls.ocr = read_json("ocr-comparison.json")
        cls.adjudications = read_json("adjudications.json")

    def test_required_historical_authorities_exist(self):
        for commit in REQUIRED_COMMITS:
            result = subprocess.run(
                ["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                cwd=ROOT,
                check=False,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, commit)

    def test_captured_observation_set_covers_six_pages(self):
        self.assertEqual(set(self.results["pages"]), set(PAGES))
        self.assertEqual(self.results["manual_page_ocr_invocations"], 6)
        self.assertEqual(self.results["tesseract"]["version"], "5.3.4")
        for page in PAGES:
            record = self.results["pages"][page]
            ocr = record["ocr"]
            self.assertEqual(ocr["tesseract_version"], "5.3.4")
            self.assertEqual(ocr["language"], "eng")
            self.assertEqual(ocr["config"], "--psm 6")
            self.assertEqual(ocr["invocations_on_manual_crop"], 1)
            self.assertEqual(ocr["raw_tsv_word_count"], ocr["admitted_token_count"])
            self.assertTrue(record["source_sha256"])
            self.assertTrue(record["manual_sha256"])
            self.assertTrue(ocr["raw_tsv_sha256"])
            self.assertTrue(record["transform"]["final_rgb_sha256"])

    def test_human_crop_transform_metadata_and_angles(self):
        expected_angles = {
            "26": 0.48,
            "27": -0.92,
            "40": 0.90,
            "41": -0.80,
            "52": 0.74,
            "53": -0.38,
        }
        for page, angle in expected_angles.items():
            record = self.results["pages"][page]
            self.assertAlmostEqual(record["transform"]["angle_degrees"], angle)
            self.assertEqual(record["transform"]["interpolation"], "bicubic")
            self.assertTrue(record["transform"]["expand"])
            self.assertEqual(record["transform"]["background_rgb"], [255, 255, 255])
            self.assertEqual(record["transform"]["downsample"], "Pillow LANCZOS")
            self.assertEqual(record["manual_mode"], "RGB")
            registration = record["manual_to_source_registration"]
            self.assertFalse(registration["pixel_subset_exact"])
            self.assertGreater(registration["decoded_rgb_mean_absolute_difference"], 0)
            self.assertTrue(registration["same_dimensions_as_source_rectangle"])

    def test_oracle_is_pixel_based_and_all_rows_are_classified(self):
        self.assertEqual(self.results["row_oracle_total_rows"], 105)
        self.assertEqual(self.results["row_oracle_total_counts"], {
            "correct_single_line": 103,
            "false_split": 2,
            "destructive_merge": 0,
            "unresolved": 0,
        })
        self.assertEqual(set(self.rows), set(PAGES))
        total = {"correct_single_line": 0, "false_split": 0, "destructive_merge": 0, "unresolved": 0}
        for page in PAGES:
            counts = self.rows[page]["counts"]
            for key in total:
                total[key] += counts[key]
            self.assertEqual(sum(counts.values()), len(self.rows[page]["rows"]))
        self.assertEqual(total, {
            "correct_single_line": 103,
            "false_split": 2,
            "destructive_merge": 0,
            "unresolved": 0,
        })
        self.assertEqual(self.results["row_oracle_transition_counts"], {
            "repaired_false_split": 16,
            "both_correct": 87,
            "persistent_false_split": 2,
        })

    def test_physical_sheet_control_hashes_reproduce(self):
        baseline = read_json("physical-sheet-baseline.json")
        self.assertTrue(baseline["all_prior_tsv_hashes_matched"])
        self.assertEqual(baseline["reproduced_tesseract_version"], "5.3.4")
        self.assertEqual(baseline["reproduced_language"], "eng")
        self.assertEqual(baseline["reproduced_config"], "--psm 6")
        self.assertEqual(baseline["reproduction_ocr_invocations"], 6)
        self.assertEqual(set(baseline["pages"]), set(PAGES))

    def test_target_adjudications_preserve_expected_groupings(self):
        events = self.adjudications["events"]
        self.assertEqual(events["26"]["human_crop_classification"], "correct_single_line")
        self.assertEqual(events["27"]["human_crop_classification"], "false_split")
        self.assertEqual(events["53"]["human_crop_classification"], "false_split")
        p27 = events["27"]["human_crop_tokens"]
        system = next(token for token in p27 if token["text_locator"] == "system,")
        self.assertEqual(system["center_xy"][1], 129.0)
        self.assertEqual(events["27"]["vertical_observation"]["tolerance_px"], 4)

        raw_words = self.results["pages"]["27"]["ocr"]["raw_word_records"]
        target = [word for word in raw_words if 600 <= word["box_xyxy"][1] <= 650 and word["text_locator"] in {
            "affords", "an", "insufficient", "foundation", "for", "the", "physical"
        }]
        self.assertEqual(len(target), 7)
        self.assertEqual([word["box_xyxy"] for word in target], [
            [15, 624, 90, 654], [102, 624, 125, 654], [211, 628, 214, 630],
            [332, 628, 335, 630], [375, 624, 408, 654], [420, 624, 453, 654],
            [525, 628, 539, 643],
        ])
        self.assertFalse(any(word["text_locator"] == "See" for word in raw_words))

    def test_repository_sources_and_binary_policy(self):
        changed = subprocess.run(
            ["git", "diff", "--name-only", "2d7918efa63e89357fa4bc6239da1aadbe2ac367", "--", "src", "tests"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(changed, [])
        tracked = subprocess.run(
            ["git", "ls-files", "*.jpg", "*.jpeg", "*.png", "*.pdf"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(tracked, [])
        status = subprocess.run(
            ["git", "status", "--short", "--", "fixtures/einstein/spineless"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertIn("?? fixtures/einstein/spineless/", status)


if __name__ == "__main__":
    unittest.main()
