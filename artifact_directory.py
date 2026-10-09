"""Directory inventory and content hashes shared by the probe and executor."""
import hashlib
import json
from pathlib import Path


def directory_files(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Expected a regular input directory: {root}")
    files = {}
    for path in sorted(root.rglob('*')):
        # Following links would make a snapshot depend on files outside its root.
        if path.is_symlink():
            raise ValueError(f"Symlinks are not supported in artifact directories: {path}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path
        elif not path.is_dir():
            raise ValueError(f"Not a regular file or directory: {path}")
    return files


def file_sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def directory_sha256(files):
    # Hash relative names and bytes, not absolute paths, mtimes, or permissions.
    # Moving an unchanged directory does not invalidate its reports.
    manifest = {name: file_sha256(path) for name, path in sorted(files.items())}
    encoded = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
