#!/usr/bin/env python3
"""Generate optional deterministic word-boundary hints; NEVER authorize repairs.

Uses Hunspell + the versioned human-approved lexicon for admissible segments,
and recognized word frequencies from the CURRENT OCR derivative for ranking.
Suggestions are a separate, read-only handoff to the first visual Codex reviewer.
"""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from math import log1p
from pathlib import Path

from artifact_directory import directory_files, directory_sha256
from lexical_detection import lexical_character, lexical_visibility
from lexicon_store import canonical, read_lexicon
from normalize_probe import Spellcheck


def known_counts(files, recognizes):
    counts = Counter()
    for name, file in files.items():
        if not name.lower().endswith(".md"):
            continue
        text = file.read_text(encoding="utf-8")
        mask = lexical_visibility(text)
        i = 0
        while i < len(text):
            if not mask[i] or not lexical_character(text[i]):
                i += 1
                continue
            start = i
            while i < len(text) and mask[i] and lexical_character(text[i]):
                i += 1
            word = text[start:i]
            if recognizes(word):
                counts[canonical(word)] += 1
    return counts


def segments(word, recognizes, counts, maximum=3):
    """Rank known-word-only segmentations. Never produce character replacements."""
    if not isinstance(word, str) or not word or len(word) > 96 or recognizes(word):
        return []
    length = len(word)

    @lru_cache(None)
    def part(start):
        if start == length:
            return [(0.0, ())]
        choices = []
        for stop in range(start + 1, min(length, start + 32) + 1):
            piece = word[start:stop]
            if not recognizes(piece):
                continue
            # Short fragments easily produce implausible segmentations.
            if len(piece) == 1 and piece.casefold() not in ("a", "i"):
                continue
            weight = log1p(counts.get(canonical(piece), 0)) + len(piece) * 0.05 - 1.0
            for later_score, later in part(stop):
                choices.append((weight + later_score, (piece,) + later))
        return sorted(choices, key=lambda pair: (-pair[0], pair[1]))[:maximum]
    return [{"proposed": " ".join(pieces), "segments": list(pieces),
             "relative_score": round(score, 4)}
            for score, pieces in part(0) if len(pieces) >= 2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, required=True, help="Untouched output of extract_lexical.py")
    p.add_argument("--paddle", type=Path, required=True, help="Current derived Markdown directory")
    p.add_argument("--lexicon", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True, help="Read-only segmentation hint sidecar")
    args = p.parse_args()
    if args.out.exists():
        p.error("Refusing to overwrite segmentation sidecar")
    report_bytes = args.report.read_bytes()
    report = json.loads(report_bytes)
    _, lexicon_hash, words = read_lexicon(args.lexicon)
    if (report.get("format") != "lexical_review_v1" or
            report["inputs"].get("lexicon_sha256") != lexicon_hash):
        p.error("Lexicon or extracted report snapshot mismatch")
    files = directory_files(args.paddle)
    if directory_sha256(files) != report["inputs"]["paddle_dir_sha256"]:
        p.error("Derived OCR snapshot changed since probe")
    spelling = Spellcheck(lexicon_words=words)
    try:
        if spelling.digests != report["inputs"]["dictionary_sha256"]:
            p.error("Hunspell dictionary changed since probe")
        counts = known_counts(files, spelling.recognizes)
        generated = [{"finding_id": finding["id"], "observed": finding["observed"],
                      "candidates": segments(finding["observed"], spelling.recognizes, counts)}
                     for finding in report["findings"]]
    finally:
        spelling.close()
    result = {"format": "segmentation_hints_v1",
              "source_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
              "lexicon_sha256": lexicon_hash,
              "dictionary_sha256": report["inputs"]["dictionary_sha256"],
              "source_artifact_dir_sha256": report["inputs"]["paddle_dir_sha256"],
              "suggestions": generated}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Produced hints for {len(generated)} tokens; "
          f"{sum(bool(x['candidates']) for x in generated)} have known-word-only split candidates")


if __name__ == "__main__":
    main()
