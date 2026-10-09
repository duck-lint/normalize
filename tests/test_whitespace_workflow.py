"""Verify report authority and the actual CLI handoff using tiny book ZIPs."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

from execute_repairs import build, check_against_baseline, safe_relative
from extract_whitespace import extract

ROOT = Path(__file__).resolve().parents[1]


class WhitespaceWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.text = 'élan,word.Next U.S.A today,zqxwvv.\r\n'
        self.raw = self.text.encode('utf-8')
        self.unchanged = b'An unchanged page.\r\n'
        self.scans = self.workspace / 'scans.zip'
        self.paddle = self.workspace / 'paddle.zip'
        with zipfile.ZipFile(self.scans, 'w') as archive:
            # The read-only probe records image paths; it does not inspect pixels.
            archive.writestr('scans/page001.jpg', b'image fixture')
            archive.writestr('scans/page002.jpg', b'image fixture')
        with zipfile.ZipFile(self.paddle, 'w') as archive:
            for page, raw in [('page001', self.raw), ('page002', self.unchanged)]:
                archive.writestr(f'paddle/{page}.md', raw)
                archive.writestr(f'paddle/{page}_res.json', json.dumps({
                    'parsing_res_list': [{'block_id': 0, 'block_label': 'text',
                                          'block_content': raw.decode('utf-8')}]}))
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
                     [self.paddle, self.scans, self.baseline_path, self.report_path, exceptions_path]}
        output = self.workspace / 'repaired'
        args = ['--baseline', str(self.baseline_path), '--report', str(self.report_path),
                '--paddle', str(self.paddle), '--out', str(output)]
        self.run_cli('execute_repairs.py', *args)
        self.assertFalse(output.exists())
        self.run_cli('execute_repairs.py', *args, '--execute')
        self.assertEqual((output / 'paddle/page001.md').read_bytes(),
                         'élan, word. Next U.S.A today, zqxwvv.\r\n'.encode('utf-8'))
        self.assertEqual((output / 'paddle/page002.md').read_bytes(), self.unchanged)
        log = json.loads((output / 'execution_report.json').read_bytes())
        self.assertEqual(log['approved_findings'], 2)
        self.assertEqual(log['changed_pages'], 1)
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
                self.assertEqual(derived['paddle/page001.md'], self.raw)
                self.assertEqual(summary['approved_findings'], 0)

    def test_only_status_and_note_can_change(self):
        mutations = [
            lambda r: r['findings'][0].update(proposed=', altered'),
            lambda r: r['findings'][0].update(start_byte=0),
            lambda r: r['findings'][0].update(observed='different'),
            lambda r: r['findings'][0].update(triggers=['lower_upper']),
            lambda r: r['findings'][0]['review'].update(replacement='arbitrary'),
            lambda r: r['findings'].pop(),
            lambda r: r['findings'].reverse(),
            lambda r: r['inputs'].update(paddle_zip_sha256='altered'),
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

    def test_changed_paddle_archive_is_refused(self):
        with zipfile.ZipFile(self.paddle, 'a') as archive:
            archive.writestr('unexpected.txt', 'change')
        with self.assertRaisesRegex(ValueError, 'Paddle ZIP differs'):
            build(self.reviewed(), self.paddle)

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

    def test_unsafe_output_paths_are_refused(self):
        for name in ['../outside.md', '/outside.md', 'folder\\outside.md']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_relative(name)


if __name__ == '__main__':
    unittest.main()
