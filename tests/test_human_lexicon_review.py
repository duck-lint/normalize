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
from human_lexical_approvals import HUMAN_APPROVAL_FORMAT, effective_review
from execute_lexical_repairs import validate_handoffs


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

    def test_numeric_mixed_trigger_findings_are_visible_but_never_admissible(self):
        # Actual merged probe shapes from The First Philosophers: lexical
        # reports can contain a longer adjacency span with digits.
        cases = [('450HerodotusT', None, None),
                 ('YYlL1u1t', '', 'approved'),
                 ('8oBio', '80B10', 'approved')]
        baseline = json.loads(self.base.read_bytes())
        for n, (word, _, _) in enumerate(cases, 1):
            text = 'Timeline ' + word + ' marker'
            finding = copy.deepcopy(baseline['findings'][0])
            finding.update(id=f'page{n+30:03d}:lower_upper:9',
                           page=f'page{n+30:03d}', rule='lower_upper',
                           triggers=['lower_upper', 'unrecognized_token'],
                           source_image='page01.png', observed=word,
                           start_byte=9, end_byte=9 + len(word.encode()),
                           source_md_sha256=hashlib.sha256(text.encode()).hexdigest(),
                           ocr_context={'provenance': 'derived_whitespace_markdown',
                                        'start_byte': 0, 'end_byte': len(text.encode()),
                                        'text': text})
            baseline['findings'].append(finding)
        self.base.write_text(json.dumps(baseline))
        extracted = extract(baseline)
        proposals = json.loads(self.propose.read_bytes())
        proposals['findings'].extend(copy.deepcopy(extracted['findings'][-3:]))
        proposals['vocabulary'] = extracted['vocabulary']
        for finding, (_, proposed, _) in zip(proposals['findings'][-3:], cases):
            if proposed is not None:
                finding.update(proposed=proposed, proposal_source='codex_scan_proposal',
                               evidence='Scan confirms this exact replacement')
        self.propose.write_text(json.dumps(proposals))
        reviewed = json.loads(self.verified.read_bytes())
        reviewed['findings'] = copy.deepcopy(proposals['findings'])
        reviewed['vocabulary'] = proposals['vocabulary']
        for finding, (_, proposed, status) in zip(reviewed['findings'][-3:], cases):
            finding['review'] = {'status': status,
                                 'note': 'Independent scan review of merged token'}
        self.verified.write_text(json.dumps(reviewed))
        fresh = self.make_session()  # must not reject the complete report
        for word, proposed, _ in cases:
            group = fresh.groups[word.casefold()]
            self.assertFalse(group['admissible'])
            self.assertEqual(group['eligible_count'], 0)
            occurrence = group['occurrences'][0]
            self.assertFalse(occurrence['eligible'])
            self.assertEqual(occurrence['context'][1], word)
            self.assertEqual(occurrence['proposed'], proposed)
            with self.assertRaisesRegex(ValueError, 'Invalid review approval'):
                fresh.save_decision({'key': group['key'], 'decision': 'accepted',
                                     'finding_id': occurrence['id'],
                                     'note': 'Inspected the scan', 'inspected': True})
        fresh.save_decision({'key': '450herodotust', 'decision': 'rejected',
                             'finding_id': None, 'note': 'Not a lexical word',
                             'inspected': False})
        self.assertEqual(fresh.approvals()['entries'], [])

    def repair(self, fid, decision, replacement=None, note='Visually inspected the printed scan', inspected=True):
        return self.session.save_repair_decision({
            'finding_id': fid, 'decision': decision, 'replacement': replacement,
            'note': note, 'inspected': inspected})

    def test_human_scan_repairs_override_but_never_mutate_frozen_codex_files(self):
        before_proposals = self.propose.read_bytes()
        before_reviewed = self.verified.read_bytes()
        fid = next(f['id'] for f in self.session.reviewed['findings']
                   if f['observed'] == 'Schopenhuaer')
        with self.assertRaisesRegex(ValueError, 'inspection acknowledgment'):
            self.repair(fid, 'approved', 'Schopenhauer', inspected=False)
        with self.assertRaisesRegex(ValueError, 'Invalid human occurrence'):
            self.repair(fid, 'approved', 'Schopenhuaer')
        self.repair(fid, 'approved', 'Schopenhauer revised')
        self.assertEqual(self.session.findings[fid]['proposed'], 'Schopenhauer revised')
        self.assertEqual(self.session.findings[fid]['review_status'], 'approved')
        self.assertEqual(self.session.findings[fid]['codex_proposed'], 'Schopenhauer')
        self.assertEqual(self.session.repair_decisions[fid]['decision'], 'approved')
        self.assertEqual(self.propose.read_bytes(), before_proposals)
        self.assertEqual(self.verified.read_bytes(), before_reviewed)
        exported = self.session.approvals()
        self.assertEqual(exported['format'], HUMAN_APPROVAL_FORMAT)
        self.assertEqual(exported['entries'], [])
        effective, repairs = effective_review(
            self.session.baseline, self.session.proposals, self.session.reviewed,
            exported, *[self.session.snapshots[k] for k in (
                'baseline_sha256', 'proposals_sha256', 'reviewed_sha256', 'lexicon_sha256')])
        edited = next(f for f in effective['findings'] if f['id'] == fid)
        self.assertEqual(edited['proposed'], 'Schopenhauer revised')
        self.assertEqual(edited['proposal_source'], 'human_scan_proposal')
        self.assertEqual(edited['review']['status'], 'approved')
        self.assertEqual(repairs[0]['finding_id'], fid)
        validate_handoffs(self.session.baseline, self.session.proposals, self.session.reviewed)
        self.assertEqual(self.make_session().repair_decisions[fid]['replacement'], 'Schopenhauer revised')

    def test_human_rejection_can_allow_independent_lexicon_admission(self):
        fid = next(f['id'] for f in self.session.reviewed['findings']
                   if f['observed'] == 'Schopenhuaer')
        self.repair(fid, 'rejected')
        self.assertEqual(self.session.findings[fid]['proposed'], None)
        self.assertEqual(self.session.findings[fid]['review_status'], None)
        self.assertTrue(self.session.findings[fid]['eligible'])
        self.save('schopenhuaer', 'accepted', fid,
                  note='Human directly inspected the printed form')
        bundle = self.session.approvals()
        self.assertEqual(len(bundle['repairs']), 1)
        self.assertEqual(len(bundle['entries']), 1)
        # Restoring a repair would invalidate that occurrence's admission.
        with self.assertRaisesRegex(ValueError, 'clear the admission first'):
            self.repair(fid, 'pending')
        self.assertEqual(self.session.repair_decisions[fid]['decision'], 'rejected')
        self.assertEqual(self.make_session().decisions['schopenhuaer']['decision'], 'accepted')
        self.assertEqual(self.verified.read_bytes(), self.session.paths['reviewed'].read_bytes())

    def test_repair_and_corrected_word_admission_are_independently_approved(self):
        fid = next(f['id'] for f in self.session.reviewed['findings']
                   if f['observed'] == 'Schopenhuaer')
        self.repair(fid, 'approved', 'Schopenhauer')
        item = self.session.findings[fid]
        self.assertTrue(item['corrected_word_admissible'])
        self.assertFalse(item['eligible'])  # misspelled observed form is ineligible
        with self.assertRaisesRegex(ValueError, 'source occurrence'):
            self.save('schopenhuaer', 'accepted', fid,
                      note='Observed spelling was wrong')
        self.session.save_decision({
            'key': 'schopenhuaer', 'decision': 'accepted', 'finding_id': fid,
            'note': 'I inspected this exact corrected single word in the source scan',
            'inspected': True, 'word': 'Schopenhauer'})
        bundle = self.session.approvals()
        self.assertEqual(bundle['entries'][0]['word'], 'Schopenhauer')
        self.assertEqual(bundle['repairs'][0]['replacement'], 'Schopenhauer')
        updated, added = apply_human_admissions(
            self.session.lexicon, bundle,
            effective_review(self.session.baseline, self.session.proposals,
                self.session.reviewed, bundle,
                *[self.session.snapshots[k] for k in (
                  'baseline_sha256','proposals_sha256','reviewed_sha256','lexicon_sha256')])[0],
            self.session.baseline, self.session.snapshots['baseline_sha256'],
            self.session.snapshots['lexicon_sha256'])
        self.assertEqual(added[0]['word'], 'Schopenhauer')
        self.assertEqual(len(updated['entries']), 1)
        self.assertEqual(self.make_session().decisions['schopenhuaer']['word'], 'Schopenhauer')

    def test_human_can_create_repair_and_delete_numeric_span_without_lexicon_admission(self):
        fid = next(f['id'] for f in self.session.reviewed['findings']
                   if f['observed'] == 'infrequentword')
        self.repair(fid, 'approved', '')
        self.assertEqual(self.session.findings[fid]['proposed'], '')
        self.assertEqual(self.session.findings[fid]['review_status'], 'approved')
        self.assertFalse(self.session.findings[fid]['eligible'])
        approved = self.session.approvals()
        self.assertEqual(approved['repairs'][0]['replacement'], '')
        self.assertEqual(approved['entries'], [])
        self.repair(fid, 'pending')
        self.assertEqual(self.session.findings[fid]['proposed'], None)
        self.assertTrue(self.session.findings[fid]['eligible'])
        self.assertEqual(self.session.approvals()['repairs'], [])

    def test_executor_builds_human_deletion_with_original_byte_span_and_authority(self):
        from execute_lexical_repairs import build
        fid = next(f['id'] for f in self.session.reviewed['findings']
                   if f['observed'] == 'infrequentword')
        self.repair(fid, 'approved', '')
        bundle = self.session.approvals()
        effective, repairs = effective_review(
            self.session.baseline, self.session.proposals, self.session.reviewed, bundle,
            *[self.session.snapshots[k] for k in (
              'baseline_sha256', 'proposals_sha256', 'reviewed_sha256', 'lexicon_sha256')])
        artifacts = {}
        for finding in self.session.baseline['findings']:
            name = finding['paddle_markdown']
            path = self.root / name
            path.write_text(finding['ocr_context']['text'])
            artifacts[name] = path
        self.session.baseline['inputs']['paddle_dir_sha256'] = 'untouched-whitespace-stage'
        output, ledger = build(self.session.baseline, effective, artifacts,
                               'source-lexicon-sha', 'target-lexicon-sha', [], repairs)
        page = next(f['paddle_markdown'] for f in effective['findings'] if f['id'] == fid)
        self.assertNotIn(b'infrequentword', output[page])
        self.assertEqual(ledger['human_occurrence_repair_decisions'], repairs)
        executed = next(r for r in ledger['changes'] if r['id'] == fid)
        self.assertEqual(executed['authority'], 'human_scan_approval')
        self.assertEqual(executed['proposed'], '')
        self.assertEqual(executed['start_byte'], 17)
        self.assertEqual(executed['end_byte'], 17 + len('infrequentword'))

    def test_human_repair_bundle_refuses_changed_frozen_reports_and_duplicate_ids(self):
        fid = next(f['id'] for f in self.session.reviewed['findings']
                   if f['observed'] == 'infrequentword')
        self.repair(fid, 'approved', 'properword')
        bundle = self.session.approvals()
        hashes = [self.session.snapshots[k] for k in
                  ('baseline_sha256','proposals_sha256','reviewed_sha256','lexicon_sha256')]
        bad = copy.deepcopy(bundle)
        bad['repairs'].append(copy.deepcopy(bad['repairs'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            effective_review(self.session.baseline, self.session.proposals,
                             self.session.reviewed, bad, *hashes)
        bad = copy.deepcopy(bundle)
        bad['source_proposals_sha256'] = 'stale'
        with self.assertRaisesRegex(ValueError, 'not bound'):
            effective_review(self.session.baseline, self.session.proposals,
                             self.session.reviewed, bad, *hashes)

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

    def test_verified_printed_irregularity_bulk_excludes_from_lexicon_only(self):
        from review_lexicon import SOURCE_FAITHFUL_MARKER, source_faithful_verified
        verified = json.loads(self.verified.read_bytes())
        target = next(f for f in verified['findings'] if f['observed'] == 'infrequentword')
        target['review']['note'] = SOURCE_FAITHFUL_MARKER + ' Scan page01 prints this form exactly; isolated source typo'
        self.assertTrue(source_faithful_verified(target))  # verifier note alone is sufficient
        self.verified.write_text(json.dumps(verified, ensure_ascii=False))
        fresh = self.make_session()
        self.assertEqual(fresh.groups['infrequentword']['source_faithful_count'], 1)
        self.assertEqual(fresh.groups['infrequentword']['eligible_count'], 1)
        self.assertEqual(fresh.groups['newtonic']['source_faithful_count'], 0)
        old_verifier = self.verified.read_bytes()
        old_lexicon = self.lexicon.read_bytes()
        result = fresh.bulk_reject_source_faithful({
            'keys': ['infrequentword'], 'acknowledged': True})
        self.assertEqual(result['rejected'], 1)
        self.assertEqual(fresh.decisions['infrequentword']['decision'], 'rejected')
        self.assertEqual(fresh.approvals()['entries'], [])
        self.assertEqual(self.verified.read_bytes(), old_verifier)
        self.assertEqual(self.lexicon.read_bytes(), old_lexicon)
        self.assertEqual(self.make_session().decisions, fresh.decisions)
        with self.assertRaisesRegex(ValueError, 'fully source-faithful'):
            fresh.bulk_reject_source_faithful({'keys':['infrequentword'],'acknowledged':True})

    def test_source_faithful_marker_requires_verifier_not_proposer_and_conservative_evidence(self):
        from review_lexicon import SOURCE_FAITHFUL_MARKER, source_faithful_verified
        candidate = next(f for f in json.loads(self.propose.read_bytes())['findings'] if f['observed'] == 'infrequentword')
        candidate = copy.deepcopy(candidate)
        candidate['proposal_note'] = 'SOURCE_FAITHFUL_NONLEXICAL_CANDIDATE: This proposer hint is insufficient'
        self.assertFalse(source_faithful_verified(candidate))
        candidate['review']['note'] = 'Scan matches this word'
        self.assertFalse(source_faithful_verified(candidate))
        candidate['review']['note'] = SOURCE_FAITHFUL_MARKER + ' short'
        self.assertFalse(source_faithful_verified(candidate))
        candidate['review']['note'] = SOURCE_FAITHFUL_MARKER + ' Source prints this exact irregularity'
        self.assertTrue(source_faithful_verified(candidate))
        candidate['lexicon_suggestion'] = True
        self.assertFalse(source_faithful_verified(candidate))
        candidate['lexicon_suggestion'] = None
        candidate['proposed'] = 'replacement'
        self.assertFalse(source_faithful_verified(candidate))

    def test_source_faithful_bulk_reject_is_atomic_for_mixed_evidence_and_stale_scans(self):
        from review_lexicon import SOURCE_FAITHFUL_MARKER
        verified = json.loads(self.verified.read_bytes())
        for f in verified['findings']:
            if f['observed'] in ('infrequentword', 'Newtonic') and f['proposed'] is None:
                f['review']['note'] = SOURCE_FAITHFUL_MARKER + ' Scan exactly supports this isolated printed form'
        # Newtonic has a separate verified repair and cannot be bulk-excluded.
        # Suppress its proposer suggestion solely to exercise the mixed-evidence case.
        proposals = json.loads(self.propose.read_bytes())
        for f in proposals['findings']:
            if f['observed'] == 'Newtonic' and f['proposed'] is None:
                f['lexicon_suggestion'] = None
        for f in verified['findings']:
            if f['observed'] == 'Newtonic' and f['proposed'] is None:
                f['lexicon_suggestion'] = None
        self.propose.write_text(json.dumps(proposals, ensure_ascii=False))
        self.verified.write_text(json.dumps(verified, ensure_ascii=False))
        fresh = self.make_session()
        self.assertEqual(fresh.groups['newtonic']['source_faithful_count'], 1)
        self.assertEqual(fresh.groups['newtonic']['count'], 2)
        for bad in [
            {'keys':['newtonic'],'acknowledged':True},
            {'keys':['infrequentword','newtonic'],'acknowledged':True},
            {'keys':['infrequentword'],'acknowledged':False},
            {'keys':['infrequentword','infrequentword'],'acknowledged':True},
            {'keys':[],'acknowledged':True}
        ]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                fresh.bulk_reject_source_faithful(bad)
            self.assertFalse(self.progress.exists())
            self.assertFalse(fresh.decisions)
        (self.scans / 'page01.png').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'scans changed'):
            fresh.bulk_reject_source_faithful({'keys':['infrequentword'],'acknowledged':True})
        self.assertFalse(self.progress.exists())

    def test_source_faithful_bulk_http_requires_local_authorization(self):
        from review_lexicon import SOURCE_FAITHFUL_MARKER
        verified = json.loads(self.verified.read_bytes())
        candidate = next(f for f in verified['findings'] if f['observed'] == 'infrequentword')
        candidate['review']['note'] = SOURCE_FAITHFUL_MARKER + ' Scan page01 clearly retains this printed irregularity'
        self.verified.write_text(json.dumps(verified))
        fresh = self.make_session()
        server = ThreadingHTTPServer(('127.0.0.1', 0), ReviewHandler)
        server.session = fresh
        server.token = 'source-review-token'
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(lambda: (server.shutdown(), worker.join(timeout=2), server.server_close()))
        url = f'http://127.0.0.1:{server.server_port}/api/bulk-reject-source-faithful'
        payload = json.dumps({'keys':['infrequentword'],'acknowledged':True}).encode()
        with self.assertRaises(HTTPError) as err:
            urlopen(Request(url, data=payload, method='POST'))
        self.assertEqual(err.exception.code, 403)
        req = Request(url,data=payload,method='POST',headers={
            'X-Normalize-Review-Token':server.token,'Content-Type':'application/json'})
        with urlopen(req) as reply:
            self.assertEqual(json.load(reply)['rejected'], 1)
        self.assertEqual(fresh.decisions['infrequentword']['decision'], 'rejected')

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
        with urlopen(origin+'/metrics.js') as response:
            self.assertIn(b'function summarize', response.read())
            self.assertIn('javascript', response.headers['Content-Type'])
        with urlopen(origin+'/') as response:
            self.assertIn(b'/metrics.js', response.read())
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