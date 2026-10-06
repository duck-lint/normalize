from normalize.alignment import align_monotonic, anchors_from_geometry, tokenize_canonical
from normalize.markdown import emit_markdown
from normalize.reconstruction import PageSpan, _page_lines, reconstruct_document


def geometry(words_by_line, *, width=100, height=100, lefts=None, tops=None, heights=None, gaps=None):
    tokens, lines = [], []
    row = 0
    for number, words in enumerate(words_by_line):
        line_id = f"l{number}"
        left = (lefts or [10] * len(words_by_line))[number]
        top = (tops or [number * 14 for number in range(len(words_by_line))])[number]
        line_height = (heights or [10] * len(words_by_line))[number]
        ids = []
        for offset, word in enumerate(words):
            row += 1
            token_id = f"t{row}"
            tokens.append({"token_id": token_id, "text": word, "confidence": 90,
                           "x_px": left + offset * 12, "y_px": top, "width_px": 10,
                           "height_px": line_height, "physical_line_id": line_id})
            ids.append(token_id)
        lines.append({"line_id": line_id, "token_ids": ids, "left_px": left,
                      "right_px": left + max(0, len(words) - 1) * 12 + 10,
                      "top_px": top, "bottom_px": top + line_height,
                      "line_height_px": line_height,
                      "vertical_gap_to_next_px": (gaps or [2] * len(words_by_line))[number]})
    return {"page_id": "p", "width_px": width, "height_px": height,
            "tokens": tokens, "physical_lines": lines}


def make_document(source, line_words, **kwargs):
    page = geometry(line_words, **kwargs)
    return reconstruct_document(source, "raw", [PageSpan("p", 0, len(source), page)])


def test_one_paragraph_continues_across_physical_lines():
    source = "One paragraph continues\nacross two observed rows."
    doc = make_document(source, [["One", "paragraph", "continues"], ["across", "two", "observed", "rows."]])
    assert [block.kind for block in doc.blocks] == ["paragraph"]
    assert "One paragraph continues across two observed rows." == emit_markdown(doc).strip()


def test_false_physical_row_fragment_does_not_force_paragraph_boundary():
    source = "changes its position\nrelative to the embankment yet"
    doc = make_document(source, [["changes", "its", "position"], ["relative", "to", "the", "embankment", "yet"]], tops=[0, 12])
    assert len(doc.blocks) == 1


def test_large_vertical_gap_separates_paragraphs():
    source = "First paragraph ends.\nSecond paragraph begins."
    doc = make_document(source, [["First", "paragraph", "ends."], ["Second", "paragraph", "begins."]], tops=[0, 32], gaps=[22, 0])
    assert [block.text for block in doc.blocks] == ["First paragraph ends.", "Second paragraph begins."]


def test_first_line_indentation_separates_paragraph():
    source = "body row continues\nindented new paragraph"
    doc = reconstruct_document(source, "raw", [PageSpan("p", 0, len(source), {
        **geometry([["body", "row", "continues"], ["indented", "new", "paragraph"]], lefts=[10, 28]),
        "width_px": 130,
        "physical_lines": [
            {"line_id": "l0", "token_ids": ["t1", "t2", "t3"], "left_px": 10, "right_px": 90,
             "top_px": 0, "bottom_px": 10, "line_height_px": 10, "vertical_gap_to_next_px": 2},
            {"line_id": "l1", "token_ids": ["t4", "t5", "t6"], "left_px": 28, "right_px": 58,
             "top_px": 14, "bottom_px": 24, "line_height_px": 10, "vertical_gap_to_next_px": 0},
        ]
    })])
    assert len(doc.blocks) == 2


def test_heading_uses_canonical_wording_and_geometry():
    source = "5\nA Centered Heading\nBody begins here."
    page = geometry([["5"], ["A", "Centered", "Heading"], ["Body", "begins", "here."]],
                     lefts=[45, 33, 10], tops=[0, 10, 50], heights=[10, 18, 10], gaps=[2, 22, 0])
    doc = reconstruct_document(source, "raw", [PageSpan("p", 0, len(source), page)])
    assert doc.blocks[0].kind == "heading"
    assert "A Centered Heading" in emit_markdown(doc)


def test_figure_cluster_is_preserved_as_nonprose_structure():
    source = "prose before\nA\nB\nC\nFig. 1\nprose after"
    page = geometry([["prose", "before"], ["A"], ["B"], ["C"], ["Fig.", "1"], ["prose", "after"]],
                     lefts=[10, 20, 45, 70, 40, 10], tops=[0, 20, 25, 30, 35, 60], gaps=[2, 2, 2, 2, 10, 0])
    doc = reconstruct_document(source, "raw", [PageSpan("p", 0, len(source), page)])
    assert any(block.kind == "figure" for block in doc.blocks)
    assert all(word in emit_markdown(doc) for word in ("A", "B", "C", "Fig.", "1"))
    assert "prose before [Figure:" in emit_markdown(doc)
    assert "Fig. 1] prose after" in emit_markdown(doc)


def test_isolated_formula_like_line_is_display_math():
    source = "before formula\nx = 1\nafter formula"
    page = geometry([["before", "formula"], ["x", "=", "1"], ["after", "formula"]],
                     lefts=[10, 40, 10], tops=[0, 20, 40])
    doc = reconstruct_document(source, "raw", [PageSpan("p", 0, len(source), page)])
    assert any(block.kind == "display_math" for block in doc.blocks)
    assert "$$\nx = 1\n$$" in emit_markdown(doc)


def test_explicitly_unavailable_line_geometry_preserves_text_without_inventing_center():
    source = "x = 1\nBody text remains in sequence."
    page = {
        "page_id": "p",
        "width_px": 100,
        "height_px": 100,
        "tokens": [
            {"token_id": "token-0001", "text": "x", "confidence": 90,
             "x_px": 10, "y_px": 10, "width_px": 8, "height_px": 10,
             "physical_line_id": "line-0001"},
            {"token_id": "token-0002", "text": "=", "confidence": 90,
             "x_px": 22, "y_px": 10, "width_px": 8, "height_px": 10,
             "physical_line_id": "line-0001"},
            {"token_id": "token-0003", "text": "1", "confidence": 90,
             "x_px": 34, "y_px": 10, "width_px": 8, "height_px": 10,
             "physical_line_id": "line-0001"},
            {"token_id": "token-0004", "text": "Body", "confidence": 90,
             "x_px": 10, "y_px": 30, "width_px": 24, "height_px": 10,
             "physical_line_id": "line-0002"},
            {"token_id": "token-0005", "text": "text", "confidence": 90,
             "x_px": 38, "y_px": 30, "width_px": 20, "height_px": 10,
             "physical_line_id": "line-0002"},
            {"token_id": "token-0006", "text": "remains", "confidence": 90,
             "x_px": 62, "y_px": 30, "width_px": 35, "height_px": 10,
             "physical_line_id": "line-0002"},
            {"token_id": "token-0007", "text": "in", "confidence": 90,
             "x_px": 10, "y_px": 44, "width_px": 8, "height_px": 10,
             "physical_line_id": "line-0003"},
            {"token_id": "token-0008", "text": "sequence.", "confidence": 90,
             "x_px": 22, "y_px": 44, "width_px": 46, "height_px": 10,
             "physical_line_id": "line-0003"},
        ],
        "physical_lines": [
            {"line_id": "line-0001", "token_ids": ["token-0001", "token-0002", "token-0003"],
             "left_px": None, "right_px": None, "top_px": None, "bottom_px": None,
             "line_height_px": None, "vertical_gap_to_next_px": None},
            {"line_id": "line-0002", "token_ids": ["token-0004", "token-0005", "token-0006"],
             "left_px": 10, "right_px": 97, "top_px": 30, "bottom_px": 40,
             "line_height_px": 10, "vertical_gap_to_next_px": 4},
            {"line_id": "line-0003", "token_ids": ["token-0007", "token-0008"],
             "left_px": 10, "right_px": 68, "top_px": 44, "bottom_px": 54,
             "line_height_px": 10, "vertical_gap_to_next_px": 0},
        ],
    }

    page_span = PageSpan("p", 0, len(source), page)
    alignment = align_monotonic(tokenize_canonical(source, "raw"), anchors_from_geometry(page))
    lines, _ = _page_lines(page_span, alignment, source, "raw")

    assert lines[0].left is None and lines[0].right is None
    assert lines[0].top is None and lines[0].bottom is None and lines[0].height is None
    assert lines[0].gap_after is None
    assert lines[0].centered is False

    doc = reconstruct_document(source, "raw", [page_span])

    assert emit_markdown(doc).replace("\n", " ").strip() == source.replace("\n", " ")
    assert [block.kind for block in doc.blocks] == ["paragraph"]
    assert doc.blocks[0].physical_line_ids == ("line-0001", "line-0002", "line-0003")
    assert doc.blocks[0].anchor_ids == tuple(f"token-{index:04d}" for index in range(1, 9))
    assert doc.blocks[0].text == "x = 1 Body text remains in sequence."


def test_null_vertical_measurements_abstain_from_heading_classification():
    source = "A Centered Title\nBody begins here."
    page = geometry([["A", "Centered", "Title"], ["Body", "begins", "here."]],
                    lefts=[25, 10], tops=[0, 20])
    page["physical_lines"][0].update({"top_px": None, "bottom_px": None, "line_height_px": None})

    doc = reconstruct_document(source, "raw", [PageSpan("p", 0, len(source), page)])

    assert [block.kind for block in doc.blocks] == ["paragraph"]
    assert "A Centered Title Body begins here." == doc.blocks[0].text
    assert "l0" in doc.blocks[0].physical_line_ids


def test_null_vertical_gap_does_not_split_paragraph_or_drop_text():
    source = "First line continues\nwith the next line."
    page = geometry([["First", "line", "continues"], ["with", "the", "next", "line."]],
                    tops=[0, 40], gaps=[None, 0])

    doc = reconstruct_document(source, "raw", [PageSpan("p", 0, len(source), page)])

    assert [block.kind for block in doc.blocks] == ["paragraph"]
    assert doc.blocks[0].text == "First line continues with the next line."


def test_complete_line_geometry_keeps_existing_heading_classification():
    source = "5\nA Centered Heading\nBody begins here."
    page = geometry([["5"], ["A", "Centered", "Heading"], ["Body", "begins", "here."]],
                    lefts=[45, 33, 10], tops=[0, 10, 50], heights=[10, 18, 10], gaps=[2, 22, 0])

    doc = reconstruct_document(source, "raw", [PageSpan("p", 0, len(source), page)])

    assert [block.kind for block in doc.blocks] == ["heading", "paragraph"]
    assert doc.blocks[0].text == "5 A Centered Heading"


def test_page_boundary_does_not_force_paragraph_boundary():
    source = "first page words\nsecond page continuation"
    first = PageSpan("26", 0, 16, geometry([["first", "page", "words"]], tops=[50], height=100))
    second = PageSpan("27", 17, len(source), {**geometry([["second", "page", "continuation"]], tops=[0], height=100), "page_id": "27"})
    doc = reconstruct_document(source, "raw", [first, second])
    assert len(doc.blocks) == 1
    assert doc.blocks[0].page_ids == ("26", "27")
