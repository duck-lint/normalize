"""Lexical-only Markdown visibility and Unicode word spans (no repair proposals).

The visibility mask addresses the original Python string by character index;
nothing is removed or normalized, so probe byte offsets remain unchanged.
"""
import re
import unicodedata

HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG = re.compile(r"""</?[A-Za-z][A-Za-z0-9:-]*(?:[^"'<>]|"[^"]*"|'[^']*')*>""")
HTML_ENTITY = re.compile(r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);")
TEX_COMMAND = re.compile(r"\\(?:[A-Za-z@]+|.)", re.DOTALL)
MARKDOWN_IMAGE = re.compile(r"!\[[^]\n]*\]\((?:[^()\n]|\([^()\n]*\))*\)")
MARKDOWN_LINK_TARGET = re.compile(r"\]\((?:[^()\n]|\([^()\n]*\))*\)")
FENCE_OPEN = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")
FENCE_CLOSE = re.compile(r"^[ \t]{0,3}(`+|~+)[ \t]*$")
BACKTICKS = re.compile(r"`+")


def lexical_character(char):
    """Letters and their combining marks belong to lexical words."""
    return char.isalpha() or unicodedata.category(char).startswith("M")


def numeric_character(char):
    """Include Unicode decimal, digit, and other numeric characters in clusters."""
    return char.isdigit() or unicodedata.category(char).startswith("N")


def token_character(char):
    """Keep numeric and underscore material attached while deciding word spans."""
    return lexical_character(char) or numeric_character(char) or char == "_"


def word_character(char):
    """Character used by adjacency rules to expand around a lexical token."""
    return token_character(char)


def lexical_visibility(text):
    """Return a positional mask: 1 for text, 0 for structural markup/code."""
    visible = bytearray(b"\x01") * len(text)

    def hide(start, end):
        visible[start:end] = b"\x00" * (end - start)

    # Code fences are not transcribed prose. Include unclosed fences through EOF.
    open_at = None
    delimiter = None
    offset = 0
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        if open_at is None:
            match = FENCE_OPEN.match(body)
            if match:
                open_at = offset
                delimiter = match.group(1)
        else:
            match = FENCE_CLOSE.fullmatch(body)
            if match and match.group(1)[0] == delimiter[0] and len(match.group(1)) >= len(delimiter):
                hide(open_at, offset + len(line))
                open_at = None
                delimiter = None
        offset += len(line)
    if open_at is not None:
        hide(open_at, len(text))

    for pattern in (HTML_COMMENT, HTML_TAG, HTML_ENTITY, MARKDOWN_IMAGE,
                    MARKDOWN_LINK_TARGET, TEX_COMMAND):
        for match in pattern.finditer(text):
            hide(*match.span())

    # Backtick-delimited inline code, including multi-backtick delimiters.
    runs = list(BACKTICKS.finditer(text))
    i = 0
    while i < len(runs):
        opener = runs[i]
        if not visible[opener.start()]:
            i += 1
            continue
        j = i + 1
        while j < len(runs):
            closer = runs[j]
            if visible[closer.start()] and len(closer.group()) == len(opener.group()):
                hide(opener.start(), closer.end())
                i = j
                break
            j += 1
        i += 1
    return visible


def unrecognized_spans(text, recognizes, visible):
    """Return unrecognized alphabetic runs from visible lexical token clusters.

    Numbers stay attached while finding cluster boundaries, preventing identifier
    fragments from being treated as separate prose words. Within a numeric
    cluster, however, alphabetic runs remain eligible for lexical checking.
    """
    spans = []
    pos = 0
    while pos < len(text):
        if not visible[pos] or not token_character(text[pos]):
            pos += 1
            continue
        cluster_start = pos
        while pos < len(text) and visible[pos] and token_character(text[pos]):
            pos += 1
        cluster_end = pos
        cluster = text[cluster_start:cluster_end]
        # Underscores are strong evidence of an identifier or file name. Keep
        # suppressing that whole cluster instead of reporting its word pieces.
        if "_" in cluster:
            continue

        run_start = cluster_start
        while run_start < cluster_end:
            if not lexical_character(text[run_start]):
                run_start += 1
                continue
            run_end = run_start + 1
            while run_end < cluster_end and lexical_character(text[run_end]):
                run_end += 1
            token = text[run_start:run_end]
            # Preserve the existing minimum length so short fragments around
            # numbers do not become findings, while recovering longer prose runs.
            if sum(char.isalpha() for char in token) >= 4 and not recognizes(token):
                spans.append((run_start, run_end, "unrecognized_token"))
            run_start = run_end
    return spans
