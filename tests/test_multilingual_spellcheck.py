"""Regression tests for strict, snapshot-bound en_US/de_DE/fr_FR recognition."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from multilingual_spellcheck import Spellcheck, LANGUAGES
from lexicon_store import canonical
from suggest_segments import segments


class MultilingualSpellcheckTests(unittest.TestCase):
    def test_required_dictionary_pairs_missing_fails_instead_of_downgrading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "en_US.aff").write_text("SET UTF-8\n")
            (root / "en_US.dic").write_text("1\nhouse\n")
            with self.assertRaisesRegex(RuntimeError, "de_DE"):
                Spellcheck(dictionary_dir=root)
            for language in ("de_DE", "fr_FR"):
                (root / (language + ".aff")).write_text("SET UTF-8\n")
                (root / (language + ".dic")).write_text("1\nword\n")
            (root / "fr_FR.dic").unlink()
            with self.assertRaisesRegex(RuntimeError, "fr_FR"):
                Spellcheck(dictionary_dir=root)

    def test_real_dictionaries_recognize_multiple_languages_without_lexicon_admission(self):
        spell = Spellcheck()
        try:
            self.assertEqual(list(spell.digests), list(LANGUAGES))
            self.assertEqual(set(spell.handles), set(LANGUAGES))
            for language in LANGUAGES:
                for kind in ("aff", "dic"):
                    self.assertEqual(
                        spell.digests[language][kind],
                        hashlib.sha256((Path("/usr/share/hunspell") / (language + "." + kind)).read_bytes()).hexdigest())
            for word in ("house", "Freiheit", "liberté"):
                with self.subTest(word=word):
                    self.assertTrue(spell.recognizes(word), word)
            self.assertFalse(spell.recognizes("zqxwvv"))
            self.assertFalse(spell.recognizes("ofthe"))
            self.assertNotEqual(spell.digests["en_US"], spell.digests["fr_FR"])
        finally:
            spell.close()
            spell.close()  # owning code can safely close twice

    def test_custom_lexicon_remains_separate_and_segments_require_recognized_parts(self):
        spell = Spellcheck(lexicon_words={canonical("technicalnonce")})
        try:
            self.assertTrue(spell.recognizes("technicalnonce"))
            self.assertFalse(spell.recognizes("zqxwvv"))
            self.assertEqual(segments("ofthe", spell.recognizes, {})[0]["proposed"], "of the")
            # Already-recognized ordinary French/German terms should not need segmentation.
            self.assertEqual(segments("Freiheit", spell.recognizes, {}), [])
            self.assertEqual(segments("liberté", spell.recognizes, {}), [])
        finally:
            spell.close()

    def test_probe_removes_recognized_french_and_german_from_unknown_queue_without_editing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scans = root / "scans"
            paddle = root / "paddle"
            scans.mkdir()
            paddle.mkdir()
            (scans / "page001.png").write_bytes(b"fake scan")
            source = "The liberté of Freiheit;zqxwvv keeps the original glyphs.\n".encode("utf-8")
            (paddle / "page001.md").write_bytes(source)
            (paddle / "page001_res.json").write_text(json.dumps({
                "parsing_res_list": [{"block_id": 0, "block_label": "text",
                                       "block_content": source.decode("utf-8")}]},
                ensure_ascii=False), encoding="utf-8")
            target = root / "probe.json"
            process = subprocess.run([
                sys.executable, str(ROOT / "normalize_probe.py"),
                "--scans", str(scans), "--paddle", str(paddle), "--out", str(target)
            ], capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            report = json.loads(target.read_bytes())
            unknown = {f["observed"] for f in report["findings"]
                       if "unrecognized_token" in f["triggers"]}
            self.assertNotIn("liberté", unknown)
            self.assertNotIn("Freiheit", unknown)
            self.assertIn("zqxwvv", unknown)
            self.assertEqual(set(report["inputs"]["dictionary_sha256"]), set(LANGUAGES))
            self.assertEqual((paddle / "page001.md").read_bytes(), source)
            for finding in report["findings"]:
                if finding["start_byte"] is not None:
                    a, b = finding["start_byte"], finding["end_byte"]
                    self.assertEqual(source[a:b], finding["observed"].encode("utf-8"))

    def test_segmentation_cli_uses_exact_probe_dictionary_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scans, paddle = root / "scans", root / "paddle"
            scans.mkdir()
            paddle.mkdir()
            (scans / "page001.png").write_bytes(b"source")
            raw = "Some liberté from Freiheit and ofthe examples.".encode("utf-8")
            (paddle / "page001.md").write_bytes(raw)
            (paddle / "page001_res.json").write_text(json.dumps({
                "parsing_res_list": [{"block_id": 0, "block_label": "text",
                                      "block_content": raw.decode("utf-8")}]}))
            lexicon = root / "lexicon.json"
            lexicon.write_text('{"format":"normalize_lexicon_v1","entries":[]}\n')
            baseline = root / "probe2.json"
            extracted = root / "lexical-extracted.json"
            hints = root / "hints.json"
            commands = [
                ("normalize_probe.py", "--scans", str(scans), "--paddle", str(paddle),
                 "--lexicon", str(lexicon), "--out", str(baseline)),
                ("extract_lexical.py", "--report", str(baseline),
                 "--out", str(extracted)),
                ("suggest_segments.py", "--report", str(extracted),
                 "--paddle", str(paddle), "--lexicon", str(lexicon),
                 "--out", str(hints)),
            ]
            for args in commands:
                result = subprocess.run([sys.executable, str(ROOT / args[0]), *args[1:]],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            probe = json.loads(baseline.read_bytes())
            extracted_data = json.loads(extracted.read_bytes())
            sidecar = json.loads(hints.read_bytes())
            self.assertEqual(sidecar["dictionary_sha256"], probe["inputs"]["dictionary_sha256"])
            self.assertEqual(
                sidecar["dictionary_sha256"],
                extracted_data["inputs"]["dictionary_sha256"])
            unknown = {f["observed"] for f in extracted_data["findings"]}
            self.assertNotIn("liberté", unknown)
            self.assertNotIn("Freiheit", unknown)
            self.assertIn("ofthe", unknown)
            self.assertEqual(raw, (paddle / "page001.md").read_bytes())

    def test_probe_refuses_missing_dictionary_set_before_emitting_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scans = root / "scans"
            paddle = root / "paddle"
            dictionary_dir = root / "hunspell"
            scans.mkdir()
            paddle.mkdir()
            dictionary_dir.mkdir()
            (scans / "page1.png").write_bytes(b"fake scan")
            (paddle / "page1.md").write_bytes(b"Hello")
            (paddle / "page1_res.json").write_text("{}")
            report = root / "probe.json"
            process = subprocess.run([
                sys.executable, str(ROOT / "normalize_probe.py"),
                "--scans", str(scans), "--paddle", str(paddle),
                "--out", str(report), "--hunspell-dir", str(dictionary_dir)
            ], capture_output=True, text=True)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("Missing Hunspell en_US", process.stderr)
            self.assertFalse(report.exists())


if __name__ == "__main__":
    unittest.main()
