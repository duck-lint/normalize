"""Verify report authority and the actual CLI handoff using tiny book directories."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

# Direct script invocation puts tests/, not the checkout root, on sys.path.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from execute_repairs import build, check_against_baseline, write_output
from extract_whitespace import extract
from normalize_probe import CONTEXT_CHARACTERS, ocr_context


class WhitespaceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.text = 'élan,word.Next U.S.A today,zqxwvv.\r\n'
        self.raw = self.text.encode('utf-8')
        self.unchanged = b'An unchanged page.\r\n'
        self.scans = self.workspace / 'scans'
        self.paddle = self.workspace / 'paddle'
        self.scans.mkdir()
        (self.paddle / 'pages').mkdir(parents=True)
        # The read-only probe records image paths; it does not inspect pixels.
        (self.scans / 'page001.JPG').write_bytes(b'image fixture')
        (self.scans / 'page002.jpg').write_bytes(b'image fixture')
        for page, raw in [('page001', self.raw), ('page002', self.unchanged)]:
            (self.paddle / f'pages/{page}.md').write_bytes(raw)
            (self.paddle / f'pages/{page}_res.json').write_text(json.dumps({
                'parsing_res_list': [{'block_id': 0, 'block_label': 'text',
                                      'block_content': raw.decode('utf-8')}]}), encoding='utf-8')
        (self.paddle / 'assets').mkdir()
        (self.paddle / 'assets/crop.png').write_bytes(b'raw asset fixture')
        self.baseline_path = self.workspace / 'review/probe.json'
        self.report_path = self.workspace / 'review/whitespace.json'
        self.run_cli('normalize_probe.py', '--scans', str(self.scans),
                     '--paddle', str(self.paddle), '--out', str(self.baseline_path))
        self.run_cli('extract_whitespace.py', '--report', str(self.baseline_path),
                     '--out', str(self.report_path))
        self.baseline = json.loads(self.baseline_path.read_bytes())
        self.report = json.loads(self.report_path.read_bytes())

    def run_cli(self, script, *args, expected=0):
        result = subprocess.run([sys.executable, str(ROOT / script), *args],
                                cwd=self.workspace, capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def reviewed(self):
        report = copy.deepcopy(self.report)
        for finding in report['findings']:
            if finding['observed'] == '.S.A':
                finding['review']['note'] = 'U.S.A is an abbreviation; no spaces belong.'
            else:
                finding['review']['status'] = 'approved'
        return report

    def test_extractor_copies_complete_records_without_synthesizing_proposals(self):
        originals = {finding['id']: finding for finding in self.baseline['findings']}
        self.assertEqual(len(self.report['findings']), 3)
        for finding in self.report['findings']:
            self.assertEqual(finding, originals[finding['id']])
            self.assertEqual(finding['review'], {'status': None, 'note': None})
        # Even an absent or unusual proposal is copied, not repaired by extraction.
        changed = copy.deepcopy(self.baseline)
        punctuation = next(f for f in changed['findings'] if f['proposed'] is not None)
        punctuation['proposed'] = None
        punctuation['extra_provenance'] = {'preserve': True}
        copied = next(f for f in extract(changed)['findings'] if f['id'] == punctuation['id'])
        self.assertEqual(copied, punctuation)

    def test_probe_logs_exact_context_and_extractor_carries_all_byte_spans(self):
        originals = {f['id']: f for f in self.baseline['findings']}
        for finding in self.report['findings']:
            context = finding['ocr_context']
            self.assertEqual(context['provenance'], 'raw_paddle_markdown')
            self.assertEqual(self.raw[context['start_byte']:context['end_byte']],
                             context['text'].encode('utf-8'))
            relative_start = finding['start_byte'] - context['start_byte']
            relative_end = finding['end_byte'] - context['start_byte']
            self.assertEqual(context['text'].encode('utf-8')[relative_start:relative_end],
                             finding['observed'].encode('utf-8'))
            self.assertEqual(finding['start_byte'], originals[finding['id']]['start_byte'])
            self.assertEqual(finding['end_byte'], originals[finding['id']]['end_byte'])
            self.assertEqual(context, originals[finding['id']]['ocr_context'])
        self.assertIn('élan', self.report['findings'][0]['ocr_context']['text'])
        self.assertIn('\r\n', self.report['findings'][0]['ocr_context']['text'])

    def test_context_is_bounded_and_keeps_utf8_boundaries_for_repeated_spans(self):
        text = 'é' * 200 + ' first,Next ' + '界' * 400 + ' second,Next ' + 'é' * 200
        raw = text.encode('utf-8')
        positions = [text.index(',Next'), text.rindex(',Next')]
        contexts = []
        for start in positions:
            end = start + len(',Next')
            context = ocr_context(text, start, end)
            contexts.append(context)
            self.assertEqual(raw[context['start_byte']:context['end_byte']],
                             context['text'].encode('utf-8'))
            self.assertEqual(len(context['text']), 2 * CONTEXT_CHARACTERS + len(',Next'))
            relative_start = len(text[:start].encode('utf-8')) - context['start_byte']
            self.assertEqual(context['text'].encode('utf-8')[relative_start:relative_start + 5], b',Next')
        self.assertNotEqual(contexts[0]['text'], contexts[1]['text'])
        self.assertNotEqual(contexts[0]['start_byte'], contexts[1]['start_byte'])

    def test_review_handoff_needs_no_raw_paddle_files_or_baseline_in_review_workspace(self):
        reviewer = self.workspace / 'reviewer'
        (reviewer / 'review').mkdir(parents=True)
        shutil.copytree(self.scans, reviewer / 'Example Book/imgs/source')
        report_path = reviewer / 'review/whitespace.json'
        shutil.copyfile(self.report_path, report_path)
        loaded = json.loads(report_path.read_bytes())
        for finding in loaded['findings']:
            self.assertTrue((reviewer / 'Example Book/imgs/source' / finding['source_image']).is_file())
            context = finding['ocr_context']
            start = finding['start_byte'] - context['start_byte']
            end = finding['end_byte'] - context['start_byte']
            self.assertEqual(context['text'].encode('utf-8')[start:end], finding['observed'].encode('utf-8'))
        self.assertEqual(list(reviewer.rglob('*.md')), [])
        self.assertEqual(list(reviewer.rglob('*_res.json')), [])
        self.assertEqual(list(reviewer.rglob('probe.json')), [])
        reviewed = self.reviewed()
        report_path.write_text(json.dumps(reviewed), encoding='utf-8')
        exceptions = {'findings': [f for f in reviewed['findings'] if f['review']['status'] != 'approved']}
        (reviewer / 'review/whitespace_exceptions.json').write_text(json.dumps(exceptions), encoding='utf-8')
        # The separate execution environment still has the untouched baseline/raw files.
        check_against_baseline(json.loads(report_path.read_bytes()), self.baseline)
        derived, _ = build(json.loads(report_path.read_bytes()), self.paddle)
        self.assertEqual(derived['pages/page001.md'], 'élan, word. Next U.S.A today, zqxwvv.\r\n'.encode('utf-8'))

    def test_lexical_overlap_does_not_swallow_whitespace_finding(self):
        lexical = next(f for f in self.baseline['findings'] if f['observed'] == 'zqxwvv')
        punctuation = next(f for f in self.report['findings'] if f['observed'] == ',zqxwvv')
        self.assertIn('unrecognized_token', lexical['triggers'])
        self.assertIsNone(lexical['proposed'])
        self.assertEqual(punctuation['triggers'], ['punctuation_letter'])
        self.assertEqual(punctuation['proposed'], ', zqxwvv')
        self.assertLess(punctuation['start_byte'], lexical['start_byte'])
        self.assertEqual(punctuation['end_byte'], lexical['end_byte'])
        self.assertNotIn(lexical, self.report['findings'])

    def test_empty_or_mixed_or_lexical_triggers_are_excluded(self):
        probe = copy.deepcopy(self.baseline)
        example = copy.deepcopy(self.report['findings'][0])
        for triggers in [[], ['lower_upper'], ['period_capital', 'unrecognized_token']]:
            example['triggers'] = triggers
            probe['findings'] = [copy.deepcopy(example)]
            self.assertEqual(extract(probe)['findings'], [])

    def test_approval_executes_second_report_and_leaves_abbreviation_unchanged(self):
        reviewed = self.reviewed()
        check_against_baseline(reviewed, self.baseline)
        self.report_path.write_text(json.dumps(reviewed), encoding='utf-8')
        exceptions_path = self.workspace / 'review/whitespace_exceptions.json'
        exceptions = {'findings': [copy.deepcopy(f) for f in reviewed['findings']
                                   if f['review']['status'] != 'approved']}
        exceptions_path.write_text(json.dumps(exceptions), encoding='utf-8')
        self.assertEqual(len(exceptions['findings']), 1)
        self.assertIsNone(exceptions['findings'][0]['review']['status'])
        snapshots = {path: path.read_bytes() for path in
                     [*self.paddle.rglob('*'), *self.scans.rglob('*'),
                      self.baseline_path, self.report_path, exceptions_path] if path.is_file()}
        output = self.workspace / 'repaired'
        args = ['--baseline', str(self.baseline_path), '--report', str(self.report_path),
                '--paddle', str(self.paddle), '--out', str(output)]
        self.run_cli('execute_repairs.py', *args)
        self.assertFalse(output.exists())
        self.run_cli('execute_repairs.py', *args, '--execute')
        self.assertEqual((output / 'pages/page001.md').read_bytes(),
                         'élan, word. Next U.S.A today, zqxwvv.\r\n'.encode('utf-8'))
        self.assertEqual((output / 'pages/page002.md').read_bytes(), self.unchanged)
        log = json.loads((output / 'execution_report.json').read_bytes())
        self.assertEqual(log['approved_findings'], 2)
        self.assertEqual(log['changed_pages'], 1)
        final_hash = hashlib.sha256((output / 'pages/page001.md').read_bytes()).hexdigest()
        self.assertTrue(all(record['derived_md_sha256'] == final_hash for record in log['changes']))
        for path in self.paddle.rglob('*'):
            if path.is_file() and path.suffix != '.md':
                self.assertEqual((output / path.relative_to(self.paddle)).read_bytes(), path.read_bytes())
        for path, raw in snapshots.items():
            self.assertEqual(path.read_bytes(), raw)
        # A repeated invocation cannot overwrite the derived output.
        self.run_cli('execute_repairs.py', *args, '--execute', expected=2)

    def test_no_approval_and_all_other_statuses_produce_no_change(self):
        for status in [None, 'pending', 'rejected', 'deferred', 'replace', 'APPROVED']:
            with self.subTest(status=status):
                reviewed = copy.deepcopy(self.report)
                for finding in reviewed['findings']:
                    finding['review']['status'] = status
                check_against_baseline(reviewed, self.baseline)
                derived, summary = build(reviewed, self.paddle)
                self.assertEqual(derived['pages/page001.md'], self.raw)
                self.assertEqual(summary['approved_findings'], 0)

    def test_only_status_and_note_can_change(self):
        mutations = [
            lambda r: r['findings'][0].update(proposed=', altered'),
            lambda r: r['findings'][0].update(start_byte=0),
            lambda r: r['findings'][0].update(observed='different'),
            lambda r: r['findings'][0].update(triggers=['lower_upper']),
            lambda r: r['findings'][0]['ocr_context'].update(text='altered context'),
            lambda r: r['findings'][0]['ocr_context'].update(start_byte=99),
            lambda r: r['findings'][0]['review'].update(replacement='arbitrary'),
            lambda r: r['findings'].pop(),
            lambda r: r['findings'].reverse(),
            lambda r: r['inputs'].update(paddle_dir_sha256='altered'),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                report = self.reviewed()
                mutate(report)
                with self.assertRaises(ValueError):
                    check_against_baseline(report, self.baseline)

    def test_nonspace_proposal_is_refused_even_with_matching_baseline(self):
        report = self.reviewed()
        baseline = copy.deepcopy(self.baseline)
        target = report['findings'][0]
        target['proposed'] = target['observed'].replace(',', ';')
        original = next(f for f in baseline['findings'] if f['id'] == target['id'])
        original['proposed'] = target['proposed']
        check_against_baseline(report, baseline)
        with self.assertRaisesRegex(ValueError, 'deterministic punctuation-space'):
            build(report, self.paddle)

    def test_offsets_and_page_hashes_are_checked(self):
        for field, value in [('start_byte', 0), ('source_md_sha256', 'wrong')]:
            with self.subTest(field=field):
                report = self.reviewed()
                report['findings'][0][field] = value
                with self.assertRaises(ValueError):
                    build(report, self.paddle)

    def test_changed_paddle_directory_is_refused(self):
        for name, content in [('unexpected.txt', b'new file'),
                              ('pages/page001_res.json', b'changed JSON'),
                              ('assets/crop.png', b'changed asset')]:
            with self.subTest(name=name):
                path = self.paddle / name
                before = path.read_bytes() if path.exists() else None
                path.write_bytes(content)
                with self.assertRaisesRegex(ValueError, 'Paddle directory differs'):
                    build(self.reviewed(), self.paddle)
                if before is None:
                    path.unlink()
                else:
                    path.write_bytes(before)

    def test_overlapping_approved_ranges_are_refused(self):
        report = self.reviewed()
        duplicate = copy.deepcopy(report['findings'][0])
        duplicate['id'] = 'different-id-same-span'
        report['findings'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'Overlapping approved'):
            build(report, self.paddle)

    def test_failed_validation_writes_no_output(self):
        report = self.reviewed()
        report['findings'][0]['proposed'] = 'unauthorized change'
        self.report_path.write_text(json.dumps(report), encoding='utf-8')
        output = self.workspace / 'repaired'
        self.run_cli('execute_repairs.py', '--baseline', str(self.baseline_path),
                     '--report', str(self.report_path), '--paddle', str(self.paddle),
                     '--out', str(output), '--execute', expected=2)
        self.assertFalse(output.exists())

    def test_extraction_cannot_overwrite_reviewed_report(self):
        raw = self.report_path.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / 'extract_whitespace.py'),
                                 '--report', str(self.baseline_path), '--out', str(self.report_path)],
                                cwd=self.workspace, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.report_path.read_bytes(), raw)

    def test_output_cannot_be_nested_inside_original_paddle(self):
        self.report_path.write_text(json.dumps(self.reviewed()), encoding='utf-8')
        output = self.paddle / 'repaired'
        self.run_cli('execute_repairs.py', '--baseline', str(self.baseline_path),
                     '--report', str(self.report_path), '--paddle', str(self.paddle),
                     '--out', str(output), '--execute', expected=2)
        self.assertFalse(output.exists())

    def test_changed_input_during_copy_cannot_publish_output(self):
        derived, summary = build(self.reviewed(), self.paddle)
        (self.paddle / 'pages/page001_res.json').write_bytes(b'changed after validation')
        output = self.workspace / 'repaired'
        with self.assertRaisesRegex(ValueError, 'changed during copying'):
            write_output(self.paddle, output, derived, summary)
        self.assertFalse(output.exists())
        self.assertEqual(list(self.workspace.glob('.repaired-*')), [])

    def test_reports_cannot_be_written_inside_raw_inputs(self):
        output = self.paddle / 'probe.json'
        self.run_cli('normalize_probe.py', '--scans', str(self.scans),
                     '--paddle', str(self.paddle), '--out', str(output), expected=2)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
