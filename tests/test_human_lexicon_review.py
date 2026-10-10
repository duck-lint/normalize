"""Local human-admission UI: type grouping, exact scan evidence, persistent choices."""
import copy
import hashlib
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from artifact_directory import directory_files, directory_sha256
from extract_lexical import extract
from lexicon_store import read_lexicon, sha, apply_human_admissions
from review_lexicon import ReviewSession, ReviewHandler


class HumanLexiconReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.scans = self.root / 'scans'
        self.scans.mkdir()
        (self.scans / 'page01.png').write_bytes(b'original scan pixels 01')
        (self.scans / 'page02.png').write_bytes(b'original scan pixels 02')
        self.lexicon = self.root / 'lexicon.json'
        self.lexicon.write_text('{"format":"normalize_lexicon_v1","entries":[]}\n')
        self.initial_lexicon = self.lexicon.read_bytes()
        self.base = self.root / 'probe2.json'
        self.propose = self.root / 'proposals.json'
        self.verified = self.root / 'verified.json'
        self.progress = self.root / 'progress.json'
        self.output = self.root / 'human-lexicon-approvals.json'
        inputs = {'lexicon_sha256': sha(self.lexicon.read_bytes()),
                  'source_dir_sha256': directory_sha256(directory_files(self.scans))}
        findings = []
        for i, (word, image) in enumerate([
                ('Newtonic', 'page01.png'),
                ('Schopenhuaer', 'page01.png'),
                ('Newtonic', 'page02.png'),
                ('σkiεpov', 'page02.png'),
                ('infrequentword', 'page01.png')]):
            text = 'More text before ' + word + ' and text after.'
            prior = 'More text before '
            start = len(prior.encode('utf-8'))
            end = start + len(word.encode('utf-8'))
            findings.append({'id': f'page{i:03d}:unrecognized_token:{start}',
                             'page': f'page{i:03d}',
                             'rule': 'unrecognized_token',
                             'triggers': ['unrecognized_token'],
                             'source_image': image,
                             'paddle_markdown': f'page{i:03d}.md',
                             'paddle_json': f'page{i:03d}_res.json',
                             'source_md_sha256': hashlib.sha256(text.encode()).hexdigest(),
                             'start_byte': start, 'end_byte': end,
                             'json_block_id': None, 'observed': word, 'proposed': None,
                             'proposal_source': None, 'evidence': None,
                             'ocr_context': {'provenance': 'derived_whitespace_markdown',
                                             'start_byte': 0,
                                             'end_byte': len(text.encode()),
                                             'text': text},
                             'review': {'status': None, 'note': None}})
        self.base.write_text(json.dumps({'inputs': inputs, 'findings': findings}, ensure_ascii=False))
        self.extract = extract(json.loads(self.base.read_bytes()))
        proposals = copy.deepcopy(self.extract)
        for finding in proposals['findings']:
            if finding['observed'] == 'Newtonic':
                finding['lexicon_suggestion'] = True
            if finding['id'] == findings[2]['id']:
                finding['proposed'] = 'New tonic'
            if finding['observed'] == 'Schopenhuaer':
                finding['proposed'] = 'Schopenhauer'
            if finding['proposed'] is not None:
                finding['proposal_source'] = 'codex_scan_proposal'
                finding['evidence'] = 'Exact printing visually inspected by proposer'
        self.propose.write_text(json.dumps(proposals, ensure_ascii=False))
        verified = copy.deepcopy(proposals)
        for finding in verified['findings']:
            if finding['proposed'] is not None:
                finding['review'] = {'status': 'approved', 'note': 'Scan visibly supports correction'}
        self.verified.write_text(json.dumps(verified, ensure_ascii=False))
        self.session = self.make_session()

    def make_session(self):
        return ReviewSession(self.base, self.propose, self.verified,
                             self.scans, self.lexicon, self.progress, self.output)

    def save(self, key, decision, finding_id=None, note='Evidence from original scan', inspected=True):
        return self.session.save_decision({'key': key, 'decision': decision,
                                           'finding_id': finding_id, 'note': note,
                                           'inspected': inspected})

    def test_unique_vocabulary_and_mixed_repair_evidence(self):
        self.assertEqual(len(self.session.groups), 4)
        group = self.session.groups['newtonic']
        self.assertEqual(group['count'], 2)
        self.assertEqual(group['suggested_count'], 2)
        self.assertEqual(group['repair_count'], 1)
        self.assertEqual(group['eligible_count'], 1)
        self.assertEqual(self.session.groups['infrequentword']['suggested_count'], 0)
        self.assertEqual(self.session.groups['schopenhuaer']['eligible_count'], 0)
        self.assertEqual(self.session.groups['σkiεpov']['eligible_count'], 1)
        occurrence = self.session.groups['σkiεpov']['occurrences'][0]
        self.assertEqual(occurrence['context'][1], 'σkiεpov')

    def test_acceptance_requires_exact_eligible_occurrence_and_inspection_note(self):
        newtonic = self.session.groups['newtonic']['occurrences']
        with self.assertRaisesRegex(ValueError, 'inspection'):
            self.save('newtonic', 'accepted', newtonic[0]['id'], inspected=False)
        with self.assertRaisesRegex(ValueError, 'Invalid review'):
            self.save('newtonic', 'accepted', newtonic[1]['id'])
        with self.assertRaisesRegex(ValueError, 'Invalid review'):
            self.save('newtonic', 'accepted', newtonic[0]['id'], note='')
        with self.assertRaisesRegex(ValueError, 'Invalid review'):
            self.save('schopenhuaer', 'accepted',
                      self.session.groups['schopenhuaer']['occurrences'][0]['id'])
        self.assertFalse(self.progress.exists())

    def test_review_persists_and_exports_without_touching_lexicon_or_reports(self):
        fid = self.session.groups['newtonic']['occurrences'][0]['id']
        self.save('newtonic', 'accepted', fid, note='Human checked the printed technical term')
        self.save('infrequentword', 'rejected', note='Do not admit this form', inspected=False)
        self.assertTrue(self.progress.is_file())
        other = self.make_session()
        self.assertEqual(other.decisions, self.session.decisions)
        result = other.export()
        self.assertEqual(result['entries'], 1)
        approvals = json.loads(self.output.read_bytes())
        self.assertEqual(approvals['entries'][0]['word'], 'Newtonic')
        self.assertEqual(approvals['entries'][0]['finding_id'], fid)
        lexicon, lex_sha, _ = read_lexicon(self.lexicon)
        updated, admissions = apply_human_admissions(
            lexicon, approvals, json.loads(self.verified.read_bytes()),
            json.loads(self.base.read_bytes()), sha(self.base.read_bytes()), lex_sha)
        self.assertEqual(len(admissions), 1)
        self.assertEqual(len(updated['entries']), 1)
        self.assertEqual(self.lexicon.read_bytes(), self.initial_lexicon)
        self.assertIsNone(json.loads(self.base.read_bytes())['findings'][0]['proposed'])
        with self.assertRaises(FileExistsError):
            other.export()

    def test_skip_clears_and_export_can_be_empty(self):
        fid = self.session.groups['newtonic']['occurrences'][0]['id']
        self.save('newtonic', 'accepted', fid)
        self.save('newtonic', 'pending', note='', inspected=False)
        self.assertEqual(self.session.decisions, {})
        self.assertEqual(self.session.export()['entries'], 0)

    def test_stale_progress_or_scan_prevents_reuse(self):
        fid = self.session.groups['newtonic']['occurrences'][0]['id']
        self.save('newtonic', 'accepted', fid)
        self.lexicon.write_text('{"format":"normalize_lexicon_v1","entries":[]}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Input changed'):
            self.session.export()
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            self.make_session()
        self.lexicon.write_bytes(self.initial_lexicon)
        (self.scans / 'page01.png').write_bytes(b'tampered pixels')
        with self.assertRaisesRegex(ValueError, 'scans changed'):
            self.session.export()

    def test_invalid_progress_is_rejected_on_resume(self):
        fid = self.session.groups['newtonic']['occurrences'][0]['id']
        self.save('newtonic', 'accepted', fid)
        state = json.loads(self.progress.read_bytes())
        state['decisions']['newtonic']['finding_id'] = 'fabricated'
        self.progress.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, 'Invalid review'):
            self.make_session()

    def test_bulk_rejection_is_only_for_unanimously_verified_repair_types(self):
        self.assertEqual(self.session.groups['schopenhuaer']['verified_repair_count'], 1)
        self.assertEqual(self.session.groups['newtonic']['verified_repair_count'], 1)
        before = self.verified.read_bytes()
        data = {'keys': ['schopenhuaer'], 'acknowledged': True}
        result = self.session.bulk_reject(data)
        self.assertEqual(result['rejected'], 1)
        self.assertEqual(self.session.decisions['schopenhuaer']['decision'], 'rejected')
        self.assertEqual(self.session.groups['newtonic']['eligible_count'], 1)
        self.assertNotIn('newtonic', self.session.decisions)
        self.assertEqual(self.verified.read_bytes(), before)
        self.assertEqual(self.session.approvals()['entries'], [])
        self.assertEqual(self.make_session().decisions, self.session.decisions)

    def test_bulk_rejection_fails_atomically_on_mixed_pending_or_invalid_entries(self):
        for bad in [
            {'keys': ['newtonic'], 'acknowledged': True},  # mixed proposals
            {'keys': ['infrequentword'], 'acknowledged': True},  # no repair
            {'keys': ['schopenhuaer', 'newtonic'], 'acknowledged': True},
            {'keys': ['schopenhuaer', 'schopenhuaer'], 'acknowledged': True},
            {'keys': ['schopenhuaer'], 'acknowledged': False},
            {'keys': [], 'acknowledged': True},
        ]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.session.bulk_reject(bad)
            self.assertFalse(self.session.decisions)
            self.assertFalse(self.progress.exists())
        # An accepted decision must never be overwritten by a bulk operation.
        self.save('newtonic', 'accepted', self.session.groups['newtonic']['occurrences'][0]['id'])
        with self.assertRaises(ValueError):
            self.session.bulk_reject({'keys': ['newtonic'], 'acknowledged': True})
        self.assertEqual(self.session.decisions['newtonic']['decision'], 'accepted')

    def test_bulk_rejection_refuses_stale_scan_snapshot(self):
        (self.scans / 'page01.png').write_bytes(b'changed scan pixels')
        with self.assertRaisesRegex(ValueError, 'scans changed'):
            self.session.bulk_reject({'keys': ['schopenhuaer'], 'acknowledged': True})
        self.assertFalse(self.progress.exists())

    def test_bulk_rejection_requires_an_independently_approved_repair_for_every_occurrence(self):
        # A proposal with review.status null cannot be bulk-accepted as a correction.
        changed = json.loads(self.verified.read_bytes())
        record = next(f for f in changed['findings'] if f['observed'] == 'Schopenhuaer')
        record['review']['status'] = None
        self.verified.write_text(json.dumps(changed, ensure_ascii=False))
        no_verification = self.make_session()
        self.assertEqual(no_verification.groups['schopenhuaer']['repair_count'], 1)
        self.assertEqual(no_verification.groups['schopenhuaer']['verified_repair_count'], 0)
        with self.assertRaises(ValueError):
            no_verification.bulk_reject({'keys': ['schopenhuaer'], 'acknowledged': True})

    def test_http_scan_serving_and_authorized_post(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), ReviewHandler)
        server.session = self.session
        server.token = 'test-random-token'
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(lambda: (server.shutdown(), worker.join(timeout=2), server.server_close()))
        origin = f'http://127.0.0.1:{server.server_port}'
        with urlopen(origin+'/api/data') as response:
            manifest = json.load(response)
        self.assertEqual(manifest['token'], server.token)
        fid = self.session.groups['newtonic']['occurrences'][0]['id']
        from urllib.parse import quote
        with urlopen(origin+'/api/scan?id='+quote(fid, safe='')) as response:
            self.assertEqual(response.read(), b'original scan pixels 01')
        with self.assertRaises(HTTPError) as context:
            urlopen(origin+'/api/scan?id=not-a-real-finding')
        self.assertEqual(context.exception.code, 404)
        payload = json.dumps({'key': 'newtonic', 'decision': 'accepted',
                              'finding_id': fid, 'note': 'I inspected the scan',
                              'inspected': True}).encode()
        with self.assertRaises(HTTPError) as context:
            urlopen(Request(origin+'/api/decision', data=payload, method='POST'))
        self.assertEqual(context.exception.code, 403)
        req = Request(origin+'/api/decision', data=payload, method='POST', headers={
            'X-Normalize-Review-Token': server.token, 'Content-Type': 'application/json'})
        with urlopen(req) as response:
            self.assertEqual(json.load(response)['saved'], True)
        self.assertEqual(self.session.decisions['newtonic']['decision'], 'accepted')


if __name__ == '__main__':
    unittest.main()