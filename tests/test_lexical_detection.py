"""Lexical detection must report printed tokens, never markup fragments."""
import sys
from pathlib import Path
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lexical_detection import lexical_visibility, unrecognized_spans


class LexicalDetectionTests(unittest.TestCase):
    def findings(self, text, accepted=()):
        accepted = set(accepted)
        spans = unrecognized_spans(text, lambda word: word in accepted,
                                   lexical_visibility(text))
        for start, end, rule in spans:
            self.assertEqual(rule, "unrecognized_token")
            self.assertEqual(text.encode("utf-8")[len(text[:start].encode("utf-8")):
                                                  len(text[:end].encode("utf-8"))],
                             text[start:end].encode("utf-8"))
        return [text[start:end] for start, end, _ in spans]

    def test_unicode_tokens_include_accents_and_combining_marks(self):
        text = "Büffon Göttingen naïve e\u0301lan Ἀριστοτέλης 中文词汇"
        self.assertEqual(self.findings(text),
                         ["Büffon", "Göttingen", "naïve", "e\u0301lan", "Ἀριστοτέλης", "中文词汇"])
        self.assertNotIn("ttingen", self.findings(text))
        self.assertEqual(self.findings("café calf", accepted={"café"}), ["calf"])

    def test_markup_is_excluded_but_visible_text_is_checked(self):
        text = ('<div style="textAlign: center;" data-note="fakeword">Büffon '
                '<em>Göttingen</em><img src="imgs/thing.jpg" alt="altword"></div> '
                '&nbsp; \\mathrm{Newtonic} [visibleword](images/targetname.png) '
                '![imagealt](images/anothername.png) `inlineword`')
        self.assertEqual(self.findings(text), ["Büffon", "Göttingen", "Newtonic", "visibleword"])

    def test_code_fences_and_comments_remain_invisible(self):
        text = ('outsideword\n```python\ninsideword = 123\n```\n'
                '<!-- hiddenword -->\nmorewords\n~~~ text\nhiddenagain\n~~~\n')
        self.assertEqual(self.findings(text), ["outsideword", "morewords"])
        self.assertEqual(self.findings('startword\n```\nnevervisible'), ["startword"])

    def test_identifiers_and_embedded_numbers_are_not_partial_words(self):
        text = 'imgs img_in_image_box_117_63 x2wrong wrong3x realword'
        self.assertEqual(self.findings(text), ["imgs", "realword"])

    def test_probe_cli_keeps_byte_spans_and_existing_punctuation_proposals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scans = root / "scans"
            paddle = root / "paddle"
            scans.mkdir()
            paddle.mkdir()
            (scans / "page001.png").write_bytes(b"source scan fixture")
            text = ('<div style="textAlign: center" title="brokenName">'
                    'ézqxwvv,word</div> \\mathrm{zqxwvv}\r\n')
            (paddle / "page001.md").write_bytes(text.encode("utf-8"))
            (paddle / "page001_res.json").write_text(json.dumps({
                "parsing_res_list": [{"block_id": 0, "block_label": "text",
                                      "block_content": text}]}), encoding="utf-8")
            out = root / "probe.json"
            run = subprocess.run([sys.executable, str(ROOT / "normalize_probe.py"),
                                  "--scans", str(scans), "--paddle", str(paddle),
                                  "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            findings = json.loads(out.read_text(encoding="utf-8"))["findings"]
            words = [f["observed"] for f in findings if "unrecognized_token" in f["triggers"]]
            self.assertIn("ézqxwvv", words)
            for structural in ("div", "textAlign", "brokenName", "mathrm"):
                self.assertNotIn(structural, words)
            self.assertFalse(any("lower_upper" in f["triggers"] for f in findings))
            self.assertTrue(any(f["observed"] == ",word" and
                                f["proposed"] == ", word" for f in findings))
            source = text.encode("utf-8")
            for finding in findings:
                if finding["start_byte"] is not None:
                    self.assertEqual(source[finding["start_byte"]:finding["end_byte"]],
                                     finding["observed"].encode("utf-8"))

    def test_no_content_shifts_when_markup_is_removed_from_detection(self):
        text = 'élan <div title="badword">Büffon</div> göttingen\r\n'
        spans = unrecognized_spans(text, lambda _: False, lexical_visibility(text))
        self.assertEqual([text[a:b] for a, b, _ in spans], ["élan", "Büffon", "göttingen"])
        self.assertEqual(len(lexical_visibility(text)), len(text))


if __name__ == '__main__':
    unittest.main()
