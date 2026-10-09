#!/usr/bin/env python3
"""Experimental read-only OCR anomaly scan for two book ZIPs. Not a repair tool."""
import argparse
from collections import Counter
import ctypes
from ctypes.util import find_library
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import zipfile

# The rules are explicit and inspectable. Every hit is a *candidate*, not a correction.
ADJACENCY = {
    "punctuation_letter": re.compile(r"[,;:!?][A-Za-z]"),
    "period_capital": re.compile(r"\.[A-Z]"),
    "lower_upper": re.compile(r"[a-z][A-Z]"),
}
WORDS = re.compile(r"(?<![A-Za-z])[A-Za-z]{4,}(?![A-Za-z])")
WHITESPACE = re.compile(r"\s+")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def names_by_stem(archive, suffix):
    out = {}
    for name in archive.namelist():
        if name.endswith(suffix) and not name.endswith("/"):
            stem = PurePosixPath(name).name.removesuffix(suffix)
            if stem in out:
                raise ValueError(f"Duplicate {suffix} for {stem}")
            out[stem] = name
    return out


class Spellcheck:
    """Use installed Hunspell with its affix rules, not a homemade book vocabulary."""
    def __init__(self, aff="/usr/share/hunspell/en_US.aff", dic="/usr/share/hunspell/en_US.dic"):
        libpath = find_library("hunspell-1.7")
        if not libpath or not Path(aff).is_file() or not Path(dic).is_file():
            raise RuntimeError("This experiment requires installed Hunspell and en_US .aff/.dic files")
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


def whitespace_proposal(observed, triggers):
    """Insert only ASCII spaces for findings triggered solely by punctuation adjacency."""
    if not triggers or not set(triggers) <= {"punctuation_letter", "period_capital"}:
        return None
    proposed = re.sub(r"([,;:!?])(?=[A-Za-z])", r"\1 ", observed)
    proposed = re.sub(r"\.(?=[A-Z])", ". ", proposed)
    return proposed if proposed != observed else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scans", type=Path, required=True, help="ZIP of source page images")
    parser.add_argument("--paddle", type=Path, required=True, help="ZIP of Paddle per-page JSON and Markdown")
    parser.add_argument("--out", type=Path, required=True, help="New editable findings JSON path")
    parser.add_argument("--propose-whitespace", action="store_true",
                        help="Pre-fill deterministic ASCII-space proposals for punctuation-only findings")
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output exists; refusing to overwrite prior human reviews")

    spelling = Spellcheck()
    findings = []
    scans_hash = sha256(args.scans.read_bytes())
    paddle_hash = sha256(args.paddle.read_bytes())

    with zipfile.ZipFile(args.scans) as scans, zipfile.ZipFile(args.paddle) as paddle:
        images = {}
        for suffix in (".png", ".jpg", ".jpeg"):
            for stem, name in names_by_stem(scans, suffix).items():
                if stem in images:
                    raise ValueError(f"Duplicate scan page: {stem}")
                images[stem] = name
        markdown = names_by_stem(paddle, ".md")
        json_files = names_by_stem(paddle, "_res.json")

        def emit(page, rule, observed, start=None, end=None, block=None, source_sha=None, triggers=None):
            ref = str(start) if start is not None else f"block-{block}" if block is not None else "page"
            trigger_list = triggers if triggers is not None else [rule]
            proposal = whitespace_proposal(observed, trigger_list) if args.propose_whitespace else None
            findings.append({
                "id": f"{page}:{rule}:{ref}", "page": page, "rule": rule,
                "triggers": trigger_list,
                "source_image": images.get(page), "paddle_markdown": markdown.get(page),
                "paddle_json": json_files.get(page), "source_md_sha256": source_sha,
                "start_byte": start, "end_byte": end, "json_block_id": block,
                "observed": observed, "proposed": proposal,
                "proposal_source": "deterministic_whitespace" if proposal is not None else None,
                "evidence": None,
                "review": {"status": None, "replacement": None, "note": None},
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

            raw = paddle.read(markdown[page])
            digest = sha256(raw)
            text = raw.decode("utf-8")
            if not text.strip():
                emit(page, "empty_markdown", "Markdown is empty", source_sha=digest)

            spans = []
            for rule, pattern in ADJACENCY.items():
                for match in pattern.finditer(text):
                    start, end = full_span(text, rule, match)
                    spans.append((start, end, rule))
            for match in WORDS.finditer(text):
                if not spelling.recognizes(match.group()):
                    spans.append((*match.span(), "unrecognized_token"))

            for start, end, triggers in combine_spans(spans):
                start_byte = len(text[:start].encode("utf-8"))
                end_byte = len(text[:end].encode("utf-8"))
                emit(page, triggers[0], text[start:end], start_byte, end_byte,
                     source_sha=digest, triggers=triggers)

            try:
                data = json.loads(paddle.read(json_files[page]))
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                emit(page, "invalid_json", str(exc), source_sha=digest)
                continue
            ignored = set(data.get("model_settings", {}).get("markdown_ignore_labels", []))
            md_text = flatten(text)
            for block in data.get("parsing_res_list", []):
                label = block.get("block_label", "unknown")
                content = flatten(block.get("block_content") or "")
                if content and label not in ignored and content not in md_text:
                    emit(page, f"json_markdown_difference:{label}", content,
                         block=block.get("block_id"), source_sha=digest)

    spelling.close()
    findings.sort(key=lambda f: (f["page"], f["start_byte"] if f["start_byte"] is not None else -1, f["rule"], str(f["json_block_id"])))
    if len({f["id"] for f in findings}) != len(findings):
        raise RuntimeError("Finding IDs are not unique")
    # A combined finding may have more than one detection rule.
    counts = dict(sorted(Counter(rule for f in findings for rule in f["triggers"]).items()))
    result = {"pilot": True, "inputs": {"source_zip_sha256": scans_hash,
              "paddle_zip_sha256": paddle_hash, "dictionary_sha256": spelling.digests},
              "page_count": len(images), "counts_by_rule": counts, "findings": findings}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(images)} images; {len(findings)} candidate findings")
    print(json.dumps(counts, indent=2))
    print(f"Report: {args.out}")


if __name__ == "__main__":
    main()
