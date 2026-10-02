from normalize.alignment import GeometryAnchor, align_monotonic, tokenize_canonical


def anchors(words, line_ids=None):
    return tuple(
        GeometryAnchor(f"o{i}", "p1", word, 90.0, (i * 12, 0, i * 12 + 10, 10),
                       (line_ids or ["l1"] * len(words))[i], i)
        for i, word in enumerate(words)
    )


def aligned(canonical, ocr):
    tokens = tokenize_canonical(canonical, "raw.md")
    result = align_monotonic(tokens, anchors(ocr))
    return tokens, result


def linked_pairs(result):
    return [(link.canonical_token_indices, link.anchor_ids) for link in result.links]


def test_exact_words_match_and_keep_original_spans():
    tokens, result = aligned("A canonically spelled line.", ["A", "canonically", "spelled", "line."])
    assert [token.text for token in tokens] == ["A", "canonically", "spelled", "line."]
    assert len(result.links) == 4
    assert not result.unmatched_canonical_indices


def test_bounded_spelling_substitution_matches_without_changing_source():
    tokens, result = aligned("sense remains canonical", ["sen5e", "remains", "canonical"])
    assert result.links[0].canonical_token_indices == (0,)
    assert tokens[0].text == "sense"


def test_missing_ocr_word_is_explicit_canonical_gap():
    _, result = aligned("one missing word remains", ["one", "word", "remains"])
    assert result.unmatched_canonical_indices == (1,)


def test_extra_ocr_word_is_explicit_anchor_gap():
    _, result = aligned("one word remains", ["one", "stray", "word", "remains"])
    assert "o1" in result.unmatched_anchor_ids


def test_two_canonical_words_can_match_one_merged_ocr_anchor():
    _, result = aligned("railway carriage", ["railwaycarriage"])
    assert result.links[0].canonical_token_indices == (0, 1)
    assert result.links[0].anchor_ids == ("o0",)


def test_one_canonical_word_can_match_two_fragmented_ocr_anchors():
    _, result = aligned("foundation remains", ["found", "ation", "remains"])
    assert result.links[0].canonical_token_indices == (0,)
    assert result.links[0].anchor_ids == ("o0", "o1")


def test_punctuation_disagreement_does_not_change_canonical_token():
    tokens, result = aligned("word, follows.", ["word", "follows"])
    assert len(result.links) == 2
    assert tokens[0].text == "word,"


def test_line_end_hyphenation_matches_unhyphenated_ocr_word():
    _, result = aligned("co-ordinate system", ["coordinate", "system"])
    assert result.links[0].canonical_token_indices == (0,)


def test_malformed_anchor_does_not_remove_canonical_material():
    tokens = tokenize_canonical("insufficient foundation", "raw")
    bad = GeometryAnchor("tiny", "p1", "insufficient", 70, (0, 0, 3, 2), "l1", 0, True)
    result = align_monotonic(tokens, (bad,))
    assert tuple(tokens[i].text for i in result.unmatched_canonical_indices) == ("foundation",)
    assert tokens[0].text == "insufficient"


def test_repeated_words_remain_in_monotonic_order():
    tokens, result = aligned("the train and the train", ["the", "train", "and", "the", "train"])
    assert [tokens[i].text for link in result.links for i in link.canonical_token_indices] == ["the", "train", "and", "the", "train"]


def test_multiple_omissions_and_empty_ocr_remain_explicit():
    _, result = aligned("alpha beta gamma delta", ["alpha", "delta"])
    assert len(result.unmatched_canonical_indices) == 2
    _, no_ocr = aligned("all words survive", [])
    assert no_ocr.unmatched_canonical_indices == (0, 1, 2)


def test_ocr_only_words_never_become_canonical_matches():
    _, result = aligned("canonical source", ["canonical", "invented", "source"])
    assert result.unmatched_anchor_ids == ("o1",)
