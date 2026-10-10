#!/usr/bin/env python3
"""Select unknown-word findings and summarize recurring forms. Never propose fixes."""
import argparse
from collections import defaultdict
import copy
import json
from pathlib import Path

from lexicon_store import canonical


def extract(report):
    if "lexicon_sha256" not in report.get("inputs", {}):
        raise ValueError("Lexical extraction requires a probe with recorded lexicon provenance")
    findings = [copy.deepcopy(f) for f in report["findings"]
                if "unrecognized_token" in f["triggers"]]
    groups = defaultdict(list)
    for finding in findings:
        if finding["start_byte"] is None or finding["proposed"] is not None:
            raise ValueError(f"Unexpected lexical proposal or offset: {finding['id']}")
        finding["proposal_note"] = None
        finding["lexicon_suggestion"] = None
        groups[canonical(finding["observed"])].append(finding)
    inventory = [{"word": records[0]["observed"],
                  "count": len(records),
                  "finding_ids": [f["id"] for f in records]}
                 for _, records in sorted(groups.items(), key=lambda entry: (-len(entry[1]), entry[0]))]
    return {"format": "lexical_review_v1", "inputs": copy.deepcopy(report["inputs"]),
            "findings": findings, "vocabulary": inventory}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    extracted = extract(json.loads(args.report.read_bytes()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(extracted, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Copied {len(extracted['findings'])} unknown-token occurrences; {len(extracted['vocabulary'])} unique forms")


if __name__ == "__main__":
    main()
