#!/usr/bin/env python3
"""Local, scan-backed human review of global lexical admissions.

Creates only a separate progress file and an explicit executor-ready approvals file.
Never mutates the scans, reviewed reports, repaired Markdown, or the lexicon.
"""
import argparse
from collections import defaultdict
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import secrets
import tempfile
import threading
from urllib.parse import parse_qs, urlparse
import webbrowser

from artifact_directory import directory_files, directory_sha256
from execute_lexical_repairs import validate_handoffs
from lexicon_store import (APPROVAL_FORMAT, apply_human_admissions,
                           canonical, read_lexicon, valid_word)

PROGRESS_FORMAT = 'human_lexicon_review_progress_v1'
UI_DIR = Path(__file__).with_name('review_ui')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load_json(path):
    raw = path.read_bytes()
    return json.loads(raw), digest(raw)


def context_parts(finding):
    """Slice exact UTF-8 context bytes, NOT Unicode codepoint approximations."""
    ctx = finding.get('ocr_context')
    if not isinstance(ctx, dict):
        raise ValueError(f"Missing OCR context: {finding['id']}")
    text = ctx['text'].encode('utf-8')
    offset = finding['start_byte'] - ctx['start_byte']
    end = finding['end_byte'] - ctx['start_byte']
    if (offset < 0 or end > len(text) or end <= offset or
            len(text) != ctx['end_byte'] - ctx['start_byte'] or
            text[offset:end] != finding['observed'].encode('utf-8')):
        raise ValueError(f"Invalid exact OCR span/context: {finding['id']}")
    return [data.decode('utf-8') for data in (text[:offset], text[offset:end], text[end:])]


class ReviewSession:
    def __init__(self, baseline, proposals, reviewed, scans, lexicon, progress, output):
        self.paths = {key: Path(path).resolve() for key, path in {
            'baseline': baseline, 'proposals': proposals, 'reviewed': reviewed,
            'scans': scans, 'lexicon': lexicon, 'progress': progress, 'output': output,
        }.items()}
        paths = self.paths
        originals = [paths[k] for k in ('baseline', 'proposals', 'reviewed', 'lexicon')]
        writable = [paths[k] for k in ('progress', 'output')]
        if (len(set(originals + writable)) != len(originals + writable)
                or writable[0] == writable[1]
                or any(w.is_relative_to(paths['scans']) for w in writable)
                or any(w.is_relative_to(paths['lexicon']) for w in writable)):
            raise ValueError('Review outputs must not overwrite any input or reside in scans/lexicon')
        self.baseline, base_hash = load_json(paths['baseline'])
        self.proposals, proposals_hash = load_json(paths['proposals'])
        self.reviewed, reviewed_hash = load_json(paths['reviewed'])
        validate_handoffs(self.baseline, self.proposals, self.reviewed)
        self.lexicon, lex_hash, existing = read_lexicon(paths['lexicon'])
        if self.baseline['inputs'].get('lexicon_sha256') != lex_hash:
            raise ValueError('The shared lexicon no longer matches the untouched probe')
        self.images = directory_files(paths['scans'])
        scan_hash = directory_sha256(self.images)
        if scan_hash != self.baseline['inputs']['source_dir_sha256']:
            raise ValueError('The scan directory no longer matches the untouched probe')
        self.snapshots = {'baseline_sha256': base_hash,
                          'proposals_sha256': proposals_hash,
                          'reviewed_sha256': reviewed_hash,
                          'lexicon_sha256': lex_hash,
                          'scans_sha256': scan_hash}
        self.existing = existing
        self.groups = {}
        self.group_index = {}
        self.findings = {}
        source_by_id = {f['id']: f for f in self.baseline['findings']}
        for finding in self.reviewed['findings']:
            fid = finding['id']
            if fid not in source_by_id or 'unrecognized_token' not in source_by_id[fid]['triggers']:
                raise ValueError(f'Untracked candidate: {fid}')
            if not valid_word(finding['observed']):
                raise ValueError(f'Unexpected lexical form: {fid}')
            source_image = finding['source_image']
            if (not isinstance(source_image, str) or source_image not in self.images or
                    self.images[source_image].suffix.lower() not in ('.png', '.jpg', '.jpeg')):
                raise ValueError(f'Source image absent or unsupported: {fid}')
            key = canonical(finding['observed'])
            proposed = finding['proposed']
            item = {'id': fid, 'word': finding['observed'], 'page': finding['page'],
                    'image': source_image, 'context': context_parts(finding),
                    'proposed': proposed, 'review_status': finding['review']['status'],
                    'suggested': finding.get('lexicon_suggestion') is True,
                    'eligible': proposed is None and finding['review']['status'] is None}
            self.findings[fid] = item
            group = self.groups.setdefault(key, {'key': key, 'word': finding['observed'],
                                                  'occurrences': [], 'count': 0,
                                                  'suggested_count': 0, 'repair_count': 0,
                                                  'verified_repair_count': 0, 'eligible_count': 0,
                                                  'already_known': key in existing})
            group['occurrences'].append(item)
            group['count'] += 1
            group['suggested_count'] += bool(item['suggested'])
            group['repair_count'] += proposed is not None
            group['verified_repair_count'] += (proposed is not None and item['review_status'] == 'approved')
            group['eligible_count'] += bool(item['eligible'])
        self.groups = dict(sorted(self.groups.items(), key=lambda pair:
                                  (-pair[1]['count'], -pair[1]['suggested_count'], pair[0])))
        self.lock = threading.RLock()
        self.decisions = {}
        if paths['progress'].exists():
            state = json.loads(paths['progress'].read_bytes())
            if (not isinstance(state, dict) or state.get('format') != PROGRESS_FORMAT
                    or state.get('snapshots') != self.snapshots
                    or not isinstance(state.get('decisions'), dict)
                    or set(state) != {'format', 'snapshots', 'decisions'}):
                raise ValueError('Saved progress references different source snapshots')
            for key, record in state['decisions'].items():
                self._validate_decision(key, record)
            self.decisions = state['decisions']

    def _validate_decision(self, key, record):
        group = self.groups.get(key)
        if group is None or not isinstance(record, dict) or set(record) != {'decision', 'finding_id', 'note'}:
            raise ValueError('Malformed or unknown review decision')
        status, fid, note = record['decision'], record['finding_id'], record['note']
        if (status not in ('accepted', 'rejected') or not isinstance(note, str) or
                (status == 'accepted' and not note.strip()) or
                (status == 'accepted' and (
                    group['already_known'] or fid not in self.findings or
                    canonical(self.findings[fid]['word']) != key or
                    not self.findings[fid]['eligible'])) or
                (status == 'rejected' and fid is not None)):
            raise ValueError('Invalid review approval, source occurrence, or note')

    def save_decision(self, data):
        if not isinstance(data, dict) or set(data) != {'key', 'decision', 'finding_id', 'note', 'inspected'}:
            raise ValueError('Unexpected decision fields')
        key, status = data['key'], data['decision']
        if key not in self.groups or status not in ('accepted', 'rejected', 'pending'):
            raise ValueError('Unknown lexical candidate or decision')
        if status == 'accepted' and data['inspected'] is not True:
            raise ValueError('Explicit source-scan inspection acknowledgment is required')
        record = {'decision': status, 'finding_id': data['finding_id'], 'note': data['note']}
        if status != 'pending':
            self._validate_decision(key, record)
            self.decisions[key] = record
        else:
            self.decisions.pop(key, None)
        self._save_progress()
        return {'saved': True, 'decisions': self.decisions}

    def bulk_reject(self, data):
        """One atomic human-confirmed batch of vocabulary rejections, never OCR repairs.

        Restrict to previously undecided lexical forms where ALL occurrences
        have independently approved OCR repair proposals. A mixed group could
        contain a genuine word despite another occurrence needing repair.
        """
        if (not isinstance(data, dict) or set(data) != {'keys', 'acknowledged'}
                or data['acknowledged'] is not True or not isinstance(data['keys'], list)
                or not data['keys'] or len(data['keys']) > 10000
                or any(not isinstance(k, str) for k in data['keys'])
                or len(set(data['keys'])) != len(data['keys'])):
            raise ValueError('Bulk rejection requires a nonempty unique key list and explicit human confirmation')
        for key in data['keys']:
            group = self.groups.get(key)
            if (group is None or key in self.decisions or group['already_known']
                    or group['repair_count'] != group['count']
                    or group['verified_repair_count'] != group['count']):
                raise ValueError(f'Not pending and fully repair-verified: {key}')
        self._check_unchanged()
        note = ('Human bulk exclusion from this lexicon admission batch: every '
                'observed occurrence has an independently approved OCR repair. '
                'Occurrence-level repair decisions remain unchanged.')
        for key in data['keys']:
            self.decisions[key] = {'decision': 'rejected', 'finding_id': None,
                                   'note': note}
        self._save_progress()
        return {'saved': True, 'rejected': len(data['keys']),
                'decisions': self.decisions}

    def _save_progress(self):
        path = self.paths['progress']
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {'format': PROGRESS_FORMAT, 'snapshots': self.snapshots,
                 'decisions': self.decisions}
        raw = (json.dumps(state, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        fd, name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def _check_unchanged(self):
        for key, field in (('baseline', 'baseline_sha256'),
                           ('proposals', 'proposals_sha256'),
                           ('reviewed', 'reviewed_sha256'),
                           ('lexicon', 'lexicon_sha256')):
            if digest(self.paths[key].read_bytes()) != self.snapshots[field]:
                raise ValueError(f'Input changed since review: {key}')
        if directory_sha256(directory_files(self.paths['scans'])) != self.snapshots['scans_sha256']:
            raise ValueError('Original scans changed since review')

    def approvals(self):
        self._check_unchanged()
        entries = []
        for key, record in self.decisions.items():
            self._validate_decision(key, record)
            if record['decision'] != 'accepted':
                continue
            finding = self.findings[record['finding_id']]
            entries.append({'word': finding['word'], 'finding_id': record['finding_id'],
                            'approved': True, 'note': record['note'].strip()})
        entries.sort(key=lambda item: canonical(item['word']))
        result = {'format': APPROVAL_FORMAT,
                  'source_report_sha256': self.snapshots['baseline_sha256'],
                  'lexicon_sha256': self.snapshots['lexicon_sha256'], 'entries': entries}
        # Exercise the *same* admission validation used by the production executor.
        apply_human_admissions(self.lexicon, result, self.reviewed, self.baseline,
                               self.snapshots['baseline_sha256'], self.snapshots['lexicon_sha256'])
        return result

    def export(self):
        approval = self.approvals()
        path = self.paths['output']
        path.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite previously authorized files; a fresh filename
        # is required if the human later changes decisions.
        with path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(approval, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        return {'path': str(path), 'entries': len(approval['entries'])}

    def manifest(self):
        public_groups = []
        for group in self.groups.values():
            public_groups.append({**group, 'occurrences': group['occurrences']})
        return {'groups': public_groups, 'decisions': self.decisions,
                'output': str(self.paths['output']),
                'snapshots': self.snapshots}


class ReviewHandler(BaseHTTPRequestHandler):
    server_version = 'NormalizeReview/1.0'

    def _send(self, status, data, mime='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        target = urlparse(self.path)
        if target.path in ('/', '/metrics.js', '/app.js', '/style.css'):
            file_name = {'/': 'index.html', '/metrics.js': 'metrics.js', '/app.js': 'app.js', '/style.css': 'style.css'}[target.path]
            mime = {'index.html': 'text/html; charset=utf-8',
                    'metrics.js': 'text/javascript; charset=utf-8',
                    'app.js': 'text/javascript; charset=utf-8',
                    'style.css': 'text/css; charset=utf-8'}[file_name]
            self._send(200, (UI_DIR / file_name).read_bytes(), mime)
        elif target.path == '/api/data':
            with self.server.session.lock:
                manifest = self.server.session.manifest()
            manifest['token'] = self.server.token
            self._json(200, manifest)
        elif target.path == '/api/scan':
            fid = parse_qs(target.query).get('id', [None])[0]
            item = self.server.session.findings.get(fid)
            if not item:
                self._json(404, {'error': 'Unknown source occurrence'})
                return
            # Only scans indexed and verified on startup may be served.
            path = self.server.session.images[item['image']]
            data = path.read_bytes()
            self._send(200, data, mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        else:
            self._json(404, {'error': 'Not found'})

    def do_POST(self):
        origin = self.headers.get('Origin')
        host = self.headers.get('Host', '')
        if (origin and origin not in (f'http://{host}', f'http://127.0.0.1:{self.server.server_port}')):
            self._json(403, {'error': 'Disallowed origin'})
            return
        if self.headers.get('X-Normalize-Review-Token') != self.server.token:
            self._json(403, {'error': 'Missing local review token'})
            return
        length = self.headers.get('Content-Length', '')
        if not length.isdigit() or int(length) > 65536:
            self._json(413, {'error': 'Invalid body length'})
            return
        try:
            data = json.loads(self.rfile.read(int(length)))
            if self.path == '/api/decision':
                with self.server.session.lock:
                    result = self.server.session.save_decision(data)
            elif self.path == '/api/bulk-reject':
                with self.server.session.lock:
                    result = self.server.session.bulk_reject(data)
            elif self.path == '/api/export':
                if data != {}:
                    raise ValueError('Export does not accept fields')
                with self.server.session.lock:
                    result = self.server.session.export()
            else:
                self._json(404, {'error': 'Not found'})
                return
        except (KeyError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            self._json(400, {'error': str(exc)})
            return
        self._json(200, result)

    def log_message(self, fmt, *args):
        # Keep the terminal useful without logging the contents of private text.
        if self.path.split('?', 1)[0] != '/api/scan':
            super().log_message(fmt, *args)


def run():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True, help='Untouched lexicon-aware Probe 2')
    p.add_argument('--proposals', type=Path, required=True, help='Frozen session-1 proposals')
    p.add_argument('--reviewed', type=Path, required=True, help='Frozen session-2 verification output')
    p.add_argument('--scans', type=Path, required=True, help='Original source scans')
    p.add_argument('--lexicon', type=Path, required=True, help='Current global lexicon')
    p.add_argument('--out', type=Path, required=True, help='New human approvals JSON output path')
    p.add_argument('--progress', type=Path, help='Autosaved review decisions (default: output path + .progress.json)')
    p.add_argument('--port', type=int, default=0, help='Local port; 0 selects a free one')
    p.add_argument('--no-browser', action='store_true')
    args = p.parse_args()
    progress = args.progress or args.out.with_name(args.out.stem + '.progress.json')
    try:
        session = ReviewSession(args.baseline, args.proposals, args.reviewed,
                                args.scans, args.lexicon, progress, args.out)
        server = ThreadingHTTPServer(('127.0.0.1', args.port), ReviewHandler)
        server.session = session
        server.token = secrets.token_urlsafe(32)
        url = f'http://127.0.0.1:{server.server_port}/'
        print(f'Local human vocabulary reviewer: {url}', flush=True)
        print(f'{len(session.groups)} distinct lexical forms, {sum(g["count"] for g in session.groups.values())} occurrences', flush=True)
        print(f'Progress saves to: {progress}; export writes only to: {args.out}', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        server.serve_forever()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        p.exit(2, f'ERROR: {exc}\n')


if __name__ == '__main__':
    run()