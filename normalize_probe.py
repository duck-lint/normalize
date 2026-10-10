#!/usr/bin/env python3
"""Read-only PaddleOCR probe. Report candidates; propose only punctuation spaces."""
import argparse
from collections import Counter
import ctypes
from ctypes.util import find_library
import hashlib
import json
from pathlib import Path
import re
from artifact_directory import directory_files, directory_sha256
from whitespace_provenance import comparison_views, whitespace_proposal

# The rules are explicit and inspectable. Every hit is a *candidate*, not a correction.
ADJACENCY = {
    "punctuation_letter": re.compile(r"[,;:!?][A-Za-z]"),
    "period_capital": re.compile(r"\.[A-Z]"),
    "lower_upper": re.compile(r"[a-z][A-Z]"),
}
WORDS = re.compile(r"(?<![A-Za-z])[A-Za-z]{4,}(?![A-Za-z])")
WHITESPACE = re.compile(r"\s+")
CONTEXT_CHARACTERS = 160


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def names_by_stem(files, suffix):
    out = {}
    for name in files:
        if name.lower().endswith(suffix):
            stem = Path(name).name[:-len(suffix)]
            if stem in out:
                raise ValueError(f"Duplicate {suffix} for {stem}")
            out[stem] = name
    return out


class Spellcheck:
    """Use installed Hunspell with its affix rules, not a homemade book vocabulary."""
    def __init__(self, aff="/usr/share/hunspell/en_US.aff", dic="/usr/share/hunspell/en_US.dic"):
        libpath = find_library("hunspell-1.7")
        if not libpath or not Path(aff).is_file() or not Path(dic).is_file():
            raise RuntimeError("The probe requires installed Hunspell and en_US .aff/.dic files")
        self.lib = ctypes.CDLL(libpath)
        self.lib.Hunspell_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.lib.Hunspell_create.restype = ctypes.c_void_p
        self.lib.Hunspell_spell.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        self.lib.Hunspell_spell.restype = ctypes.c_int
        self.lib.Hunspell_destroy.argtypes = [ctypes.c_void_p]
        self.handle = self.lib.Hunspell_create(aff.encode(), dic.encode())
        if not self.handle:
            raise RuntimeError("Failed to initialize Hunspell")
        self.digests = {"aff": sha256(Path(aff).read_bytes()), "dic": sha256(Path(dic).read_bytes())}

    def recognizes(self, word):
        return bool(self.lib.Hunspell_spell(self.handle, word.encode("utf-8")))

    def close(self):
        self.lib.Hunspell_destroy(self.handle)


def flatten(text):
    return WHITESPACE.sub(" ", text).strip()


def full_span(text, rule, match):
    """Expand adjacency hits to whole adjacent tokens; keep other hits intact."""
    start, end = match.span()
    if rule == "lower_upper":
        while start > 0 and text[start - 1].isascii() and text[start - 1].isalnum():
            start -= 1
    if rule in ADJACENCY:
        while end < len(text) and text[end].isascii() and text[end].isalnum():
            end += 1
    return start, end


def combine_spans(spans):
    """Combine overlapping/touching character spans, preserving trigger names."""
    combined = []
    for start, end, rule in sorted(spans):
        if combined and start <= combined[-1][1]:
            previous = combined[-1]
            previous[1] = max(previous[1], end)
            if rule not in previous[2]:
                previous[2].append(rule)
        else:
            combined.append([start, end, [rule]])
    return combined


def ocr_context(text, start, end, provenance="raw_paddle_markdown"):
    """A bounded input Markdown excerpt for locating, never printing evidence.

    Character slicing keeps UTF-8 boundaries intact. Both context and finding
    ranges address the SAME input Markdown bytes, including raw newlines.
    """
    context_start = max(0, start - CONTEXT_CHARACTERS)
    context_end = min(len(text), end + CONTEXT_CHARACTERS)
    return {
        "provenance": provenance,
        "start_byte": len(text[:context_start].encode("utf-8")),
        "end_byte": len(text[:context_end].encode("utf-8")),
        "text": text[context_start:context_end],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scans", type=Path, required=True, help="Directory of source page images (searched recursively)")
    parser.add_argument("--paddle", type=Path, required=True, help="Raw Paddle or verified whitespace output directory (searched recursively)")
    parser.add_argument("--out", type=Path, required=True, help="New full candidate report JSON path")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output exists; refusing to overwrite the probe report")

    if any(args.out.resolve().is_relative_to(root.resolve()) for root in (args.scans, args.paddle)):
        parser.error("Write the report outside the raw input directories")
    scans = directory_files(args.scans)
    paddle = directory_files(args.paddle)
    scans_hash = directory_sha256(scans)
    paddle_hash = directory_sha256(paddle)
    try:
        comparison_text, executed_by_page, comparison = comparison_views(paddle, scans_hash)
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        parser.error(f"Invalid execution provenance: {exc}")
    spelling = Spellcheck()
    findings = []
    comparison_exceptions = []

    try:
        images = {}
        for suffix in (".png", ".jpg", ".jpeg"):
            for stem, name in names_by_stem(scans, suffix).items():
                if stem in images:
                    raise ValueError(f"Duplicate scan page: {stem}")
                images[stem] = name
        markdown = names_by_stem(paddle, ".md")
        json_files = names_by_stem(paddle, "_res.json")

        def emit(page, rule, observed, start=None, end=None, block=None, source_sha=None, triggers=None, context=None):
            ref = str(start) if start is not None else f"block-{block}" if block is not None else "page"
            trigger_list = triggers if triggers is not None else [rule]
            proposal = whitespace_proposal(observed, trigger_list)
            findings.append({
                "id": f"{page}:{rule}:{ref}", "page": page, "rule": rule,
                "triggers": trigger_list,
                "source_image": images.get(page), "paddle_markdown": markdown.get(page),
                "paddle_json": json_files.get(page), "source_md_sha256": source_sha,
                "start_byte": start, "end_byte": end, "json_block_id": block,
                "ocr_context": context,
                "observed": observed, "proposed": proposal,
                "proposal_source": "deterministic_whitespace" if proposal is not None else None,
                "evidence": None,
                "review": {"status": None, "note": None},
            })

        for page in sorted(set(images) | set(markdown) | set(json_files)):
            if page not in images:
                emit(page, "unexpected_ocr_page", "OCR page has no source image")
            if page not in markdown:
                emit(page, "missing_markdown", "Missing Markdown for page")
            if page not in json_files:
                emit(page, "missing_json", "Missing JSON for page")
            if page not in markdown or page not in json_files:
                continue

            raw = paddle[markdown[page]].read_bytes()
            digest = sha256(raw)
            text = raw.decode("utf-8")
            if not text.strip():
                emit(page, "empty_markdown", "Markdown is empty", source_sha=digest)

            punctuation_spans = []
            lexical_spans = []
            for rule, pattern in ADJACENCY.items():
                for match in pattern.finditer(text):
                    start, end = full_span(text, rule, match)
                    target = punctuation_spans if rule in {"punctuation_letter", "period_capital"} else lexical_spans
                    target.append((start, end, rule))
            for match in WORDS.finditer(text):
                if not spelling.recognizes(match.group()):
                    lexical_spans.append((*match.span(), "unrecognized_token"))

            # A lexical overlap must not swallow a punctuation proposal. Each
            # family remains a separate finding; extraction only copies records.
            for start, end, triggers in combine_spans(punctuation_spans) + combine_spans(lexical_spans):
                start_byte = len(text[:start].encode("utf-8"))
                end_byte = len(text[:end].encode("utf-8"))
                emit(page, triggers[0], text[start:end], start_byte, end_byte,
                     source_sha=digest, triggers=triggers,
                     context=ocr_context(text, start, end,
                         "derived_whitespace_markdown" if comparison["mode"] != "raw"
                         else "raw_paddle_markdown"))

            try:
                data = json.loads(paddle[json_files[page]].read_bytes())
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                emit(page, "invalid_json", str(exc), source_sha=digest)
                continue
            ignored = set(data.get("model_settings", {}).get("markdown_ignore_labels", []))
            md_text = flatten(text)
            comparison_md = flatten(comparison_text.get(markdown[page], text))
            for block in data.get("parsing_res_list", []):
                label = block.get("block_label", "unknown")
                content = flatten(block.get("block_content") or "")
                if content and label not in ignored and content not in md_text:
                    if content in comparison_md:
                        comparison_exceptions.append({
                            "page": page, "rule": f"json_markdown_difference:{label}",
                            "json_block_id": block.get("block_id"), "observed": content,
                            "paddle_markdown": markdown[page], "paddle_json": json_files[page],
                            "derived_md_sha256": digest,
                            "reason": "present_in_verified_pre_whitespace_markdown",
                            "page_executed_finding_ids": [r["id"] for r in executed_by_page[markdown[page]]],
                            "source_md_sha256": executed_by_page[markdown[page]][0]["source_md_sha256"],
                        })
                        continue
                    emit(page, f"json_markdown_difference:{label}", content,
                         block=block.get("block_id"), source_sha=digest)

    finally:
        spelling.close()
    findings.sort(key=lambda f: (f["page"], f["start_byte"] if f["start_byte"] is not None else -1, f["rule"], str(f["json_block_id"])))
    if len({f["id"] for f in findings}) != len(findings):
        raise RuntimeError("Finding IDs are not unique")
    # A combined finding may have more than one detection rule.
    counts = dict(sorted(Counter(rule for f in findings for rule in f["triggers"]).items()))
    result = {"inputs": {"source_dir_sha256": scans_hash,
              "paddle_dir_sha256": paddle_hash, "dictionary_sha256": spelling.digests,
              "json_markdown_comparison": comparison},
              "page_count": len(images), "counts_by_rule": counts, "findings": findings,
              "json_markdown_exceptions": comparison_exceptions}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print(f"{len(images)} images; {len(findings)} candidate findings")
    print(json.dumps(counts, indent=2))
    print(f"Report: {args.out}")


if __name__ == "__main__":
    main()
