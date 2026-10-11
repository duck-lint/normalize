#!/usr/bin/env python3
"""Copy punctuation-space findings from a probe report, without changing them."""
import argparse
import json
from pathlib import Path

WHITESPACE_TRIGGERS = {"punctuation_letter", "period_capital"}


def extract(report):
    # The probe owns proposals, offsets, IDs, and initial review values. This
    # stage only selects records, including original byte spans and OCR locating
    # context; it never builds or rewrites any of them or generates proposals.
    # inputs also carries the probe's comparison provenance unchanged. No
    # reviewer-controlled suppression flag or second approval state is created.
    return {
        "inputs": report["inputs"],
        "findings": [
            finding for finding in report["findings"]
            if finding["triggers"]
            and set(finding["triggers"]) <= WHITESPACE_TRIGGERS
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path, help="Full probe report")
    parser.add_argument("--out", required=True, type=Path, help="New whitespace-only report")
    args = parser.parse_args()
    output = extract(json.loads(args.report.read_bytes()))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(output, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"Copied {len(output['findings'])} findings to {args.out}")


if __name__ == "__main__":
    main()
