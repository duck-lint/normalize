"""Configurable lexical recognition: external names are recognition, not approval."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from multilingual_spellcheck import Spellcheck
from prepare_historical_names import prepare
from audit_dictionary_coverage import compare


class DictionaryCoverageTests(unittest.TestCase):
    def test_english_variant_locales_are_explicitly_pinned_and_hashed(self):
        default = Spellcheck()
        expanded = Spellcheck(languages=("en_US", "en_CA", "en_GB", "de_DE", "fr_FR"))
        try:
            self.assertEqual(set(default.digests), {"en_US", "de_DE", "fr_FR"})
            self.assertEqual(set(expanded.digests),
                             {"en_US", "en_CA", "en_GB", "de_DE", "fr_FR"})
            for form in ("neighbour", "favour", "honour", "colour"):
                with self.subTest(form=form):
                    self.assertTrue(expanded.recognizes(form))
            self.assertFalse(expanded.recognizes("zqxwvv"))
            self.assertIn("dic", expanded.digests["en_CA"])
        finally:
            default.close()
            expanded.close()

    def test_capitalized_historical_names_only_and_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "names.txt"
            path.write_text("Simplicius\nXenophontulus\n", encoding="utf-8")
            dictionary = Spellcheck(languages=("en_US",), historical_names=path)
            try:
                self.assertTrue(dictionary.recognizes("Xenophontulus"))
                self.assertTrue(dictionary.recognizes("XENOPHONTULUS"))
                self.assertFalse(dictionary.recognizes("xenophontulus"))
                self.assertEqual(dictionary.historical_names_sha256,
                                 hashlib.sha256(path.read_bytes()).hexdigest())
            finally:
                dictionary.close()
            path.write_text("Simplicius\nXenophontulus\nWrongly\n")
            other = Spellcheck(languages=("en_US",), historical_names=path)
            try:
                self.assertNotEqual(other.historical_names_sha256,
                                    hashlib.sha256(b"Simplicius\nXenophontulus\n").hexdigest())
            finally:
                other.close()
            for contents in ("socrates\n", "Simplicius of Rome\n", "Alcmaeon1\n",
                             "Simplicius\nSimplicius\n"):
                path.write_text(contents)
                with self.subTest(contents=contents), self.assertRaises(ValueError):
                    Spellcheck(languages=("en_US",), historical_names=path)

    def test_import_wikidata_export_offline_and_reject_multitoken_labels(self):
        csv = ('item,itemLabel\n'
               'Q1,Simplicius\n'
               'Q2,Thrasymachus\n'
               'Q3,Simplicius\n'
               'Q4,Plato of Athens\n'
               'Q5,neighbour\n'
               'Q6,Xenophontulus\n').encode("utf-8")
        names, skipped = prepare(csv)
        self.assertEqual(names, ["Simplicius", "Thrasymachus", "Xenophontulus"])
        self.assertEqual(skipped, 2)
        with self.assertRaisesRegex(ValueError, "required"):
            prepare(b"name\nSocrates\n")

    def test_readonly_coverage_distinguishes_unknown_only_and_other_triggers(self):
        with tempfile.TemporaryDirectory() as tmp:
            names = Path(tmp) / "names.txt"
            names.write_text("Xenophontulus\n")
            spell = Spellcheck(languages=("en_US",), historical_names=names)
            try:
                report = {"findings": [
                    {"observed": "Xenophontulus", "triggers": ["unrecognized_token"]},
                    {"observed": "Xenophontulus",
                     "triggers": ["lower_upper", "unrecognized_token"]},
                    {"observed": "zqxwvv", "triggers": ["unrecognized_token"]},
                ]}
                totals = compare(report, spell)
                self.assertEqual(totals["total_unknown_occurrences"], 3)
                self.assertEqual(totals["recognized_occurrences"], 2)
                self.assertEqual(totals["recognized_distinct_forms"], 1)
                self.assertEqual(totals["sole_unknown_occurrences_recognized"], 1)
                self.assertEqual(totals["other_triggers_still_active"], 1)
                self.assertEqual(totals["pending_recognized_occurrences"], 2)
                decided = compare(report, spell, {"xenophontulus"})
                self.assertEqual(decided["pending_recognized_occurrences"], 0)
                self.assertEqual(decided["recognized_occurrences"], 2)
            finally:
                spell.close()

    def test_probe_filters_sourced_name_without_modifying_raw_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scans, paddle = root / "scans", root / "paddle"
            scans.mkdir()
            paddle.mkdir()
            (scans / "page001.png").write_bytes(b"source scan")
            raw = b"The Xenophontulus wrote about zqxwvv.\n"
            (paddle / "page001.md").write_bytes(raw)
            (paddle / "page001_res.json").write_text(json.dumps({
                "parsing_res_list": [{
                    "block_id": 0, "block_label": "text",
                    "block_content": raw.decode("utf-8")
                }]}))
            names = root / "names.txt"
            names.write_text("Xenophontulus\n")
            report_path = root / "probe.json"
            result = subprocess.run([sys.executable, str(ROOT / "normalize_probe.py"),
                                     "--scans", str(scans), "--paddle", str(paddle),
                                     "--locales", "en_US", "en_CA", "en_GB",
                                     "--historical-names", str(names), "--out", str(report_path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(report_path.read_bytes())
            observed = {f["observed"] for f in report["findings"]
                        if "unrecognized_token" in f["triggers"]}
            self.assertNotIn("Xenophontulus", observed)
            self.assertIn("zqxwvv", observed)
            self.assertEqual(set(report["inputs"]["dictionary_sha256"]),
                             {"en_US", "en_CA", "en_GB"})
            self.assertEqual(report["inputs"]["historical_names_sha256"],
                             hashlib.sha256(names.read_bytes()).hexdigest())
            self.assertEqual((paddle / "page001.md").read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
