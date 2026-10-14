#!/usr/bin/env python3
"""Read-only comparison: how many frozen lexical findings would new dictionaries recognize?

Never re-probes, edits OCR, rewrites findings, changes approvals or admits words.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from lexicon_store import canonical
from multilingual_spellcheck import DEFAULT_DICTIONARY_DIR, LANGUAGES, Spellcheck


def compare(report, spelling, decided=()):
    decided = set(decided)
    unknown = [f for f in report["findings"] if "unrecognized_token" in f["triggers"]]
    recognized = [f for f in unknown if spelling.recognizes(f["observed"])]
    only = [f for f in recognized if set(f["triggers"]) == {"unrecognized_token"}]
    pending = [f for f in unknown if canonical(f["observed"]) not in decided]
    pending_recognized = [f for f in pending if spelling.recognizes(f["observed"])]
    by_form = Counter(f["observed"] for f in recognized)
    return {"total_unknown_occurrences": len(unknown),
            "recognized_occurrences": len(recognized),
            "recognized_distinct_forms": len(by_form),
            "sole_unknown_occurrences_recognized": len(only),
            "other_triggers_still_active": len(recognized) - len(only),
            "pending_unknown_occurrences": len(pending),
            "pending_recognized_occurrences": len(pending_recognized),
            "top_recognized_forms": by_form.most_common(30)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, required=True,
                   help="Existing, frozen probe2.json; never modified")
    p.add_argument("--progress", type=Path,
                   help="Optional saved human review progress (matching same baseline snapshot)")
    p.add_argument("--hunspell-dir", type=Path, default=DEFAULT_DICTIONARY_DIR)
    p.add_argument("--locales", nargs="+", default=list(LANGUAGES))
    p.add_argument("--historical-names", type=Path)
    args = p.parse_args()
    try:
        raw = args.report.read_bytes()
        report = json.loads(raw)
        decided = ()
        if args.progress:
            progress = json.loads(args.progress.read_bytes())
            if (progress.get("snapshots", {}).get("baseline_sha256") !=
                    hashlib.sha256(raw).hexdigest()
                    or not isinstance(progress.get("decisions"), dict)):
                raise ValueError("Progress does not match frozen baseline; refusing comparison")
            decided = progress["decisions"]
        spell = Spellcheck(dictionary_dir=args.hunspell_dir, languages=args.locales,
                          historical_names=args.historical_names)
        try:
            result = compare(report, spell, decided)
            result["dictionary_sha256"] = spell.digests
            result["historical_names_sha256"] = spell.historical_names_sha256
            result["source_report_sha256"] = hashlib.sha256(raw).hexdigest()
        finally:
            spell.close()
    except (OSError, KeyError, TypeError, ValueError, RuntimeError,
            UnicodeError, LookupError, json.JSONDecodeError) as exc:
        p.error(str(exc))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("READ-ONLY diagnostic; no findings, reviews or execution authority changed.")


if __name__ == "__main__":
    main()
