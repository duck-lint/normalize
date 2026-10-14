#!/usr/bin/env python3
"""Prepare a frozen capitalized historical-name list from an offline CSV export.

Expected input: a reviewed Wikidata Query Service CSV export with an itemLabel
column. This tool NEVER downloads live data or modifies the input CSV.
"""
import argparse
import csv
import hashlib
from pathlib import Path
import unicodedata

from lexicon_store import canonical, valid_word


def prepare(raw, column="itemLabel"):
    text = raw.decode("utf-8-sig")
    rows = csv.DictReader(text.splitlines())
    if not rows.fieldnames or column not in rows.fieldnames:
        raise ValueError(f"CSV lacks required {column!r} column")
    names = {}
    skipped = 0
    for row in rows:
        name = (row[column] or "").strip()
        if (not name or not valid_word(name) or not name[0].isupper()
                or len(name) < 4 or unicodedata.normalize("NFC", name) != name):
            skipped += 1
            continue
        names.setdefault(canonical(name), name)
    if not names:
        raise ValueError("No eligible capitalized single-token names in CSV")
    return sorted(names.values(), key=lambda name: (canonical(name), name)), skipped


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True, help="Offline Wikidata CSV export")
    p.add_argument("--out", type=Path, required=True, help="New immutable UTF-8 name-list path")
    p.add_argument("--column", default="itemLabel", help="CSV column containing historical names")
    args = p.parse_args()
    if args.input.resolve() == args.out.resolve() or args.out.exists():
        p.error("Output must be new and different from input; no overwrite")
    try:
        raw = args.input.read_bytes()
        names, skipped = prepare(raw, args.column)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open("x", encoding="utf-8", newline="\n") as stream:
            for name in names:
                stream.write(name + "\n")
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        p.error(str(exc))
    print(f"Frozen {len(names)} historical names; skipped {skipped} non-single-word labels")
    print(f"Source CSV SHA256: {hashlib.sha256(raw).hexdigest()}")
    print(f"Name list SHA256: {hashlib.sha256(args.out.read_bytes()).hexdigest()}")
    print(f"Name list: {args.out}")


if __name__ == "__main__":
    main()
