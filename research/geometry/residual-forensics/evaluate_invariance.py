"""Run exploratory identity, translation, and scale diagnostics.

This is evidence code, not an acceptance rule.  Translation and scale are
reported separately because the Slice 2 contract does not promise either
property, and integer geometry thresholds can make scale effects observable.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from normalize.geometry import TSV_HEADER, group_physical_lines, parse_tsv_rows
from tests.geometry_oracle import canonical_geometry_state, canonical_serialized_page_state


ROOT = Path(__file__).resolve().parent


def _row(text: str, x: int, y: int, width: int, height: int, word: int) -> str:
    return "\t".join(map(str, (5, 1, 1, 1, 1, word, x, y, width, height, 95, text)))


def _tokens(rows: list[str]):
    tsv = "\t".join(TSV_HEADER) + "\n" + "\n".join(rows) + "\n"
    tokens, errors = parse_tsv_rows(tsv, 2000, 2000)
    if errors:
        raise AssertionError(errors)
    return tokens


def _assignment_projection(state):
    return tuple(
        (item[0], item[2], item[3], item[4])
        for item in state[0]
    )


def _transformed(tokens, scale: float = 1.0, dx: int = 0, dy: int = 0):
    return [
        replace(
            token,
            x=round(token.x * scale) + dx,
            y=round(token.y * scale) + dy,
            width=max(1, round(token.width * scale)),
            height=max(1, round(token.height * scale)),
        )
        for token in tokens
    ]


def _state(tokens):
    return canonical_geometry_state("synthetic-diagnostics", "left", tokens, *group_physical_lines(tokens))


def _synthetic_results() -> dict[str, object]:
    cases = {
        "separate": _tokens(
            [
                _row("a", 10, 20, 30, 10, 1),
                _row("b", 60, 20, 30, 10, 2),
                _row("c", 10, 50, 30, 10, 3),
                _row("d", 60, 50, 30, 10, 4),
            ]
        ),
        "ambiguous": _tokens(
            [
                _row("a", 10, 15, 30, 10, 1),
                _row("b", 10, 20, 30, 10, 2),
                _row("c", 10, 21, 30, 10, 3),
                _row("d", 10, 24, 30, 10, 4),
            ]
        ),
        "sloped": _tokens(
            [
                _row("a", 10, 35, 30, 10, 1),
                _row("b", 100, 30, 30, 10, 2),
                _row("c", 190, 25, 30, 10, 3),
                _row("d", 10, 65, 30, 10, 4),
                _row("e", 100, 60, 30, 10, 5),
                _row("f", 190, 55, 30, 10, 6),
            ]
        ),
    }
    result: dict[str, object] = {}
    for name, tokens in cases.items():
        baseline = _assignment_projection(_state(tokens))
        permuted = _assignment_projection(_state([tokens[index] for index in reversed(range(len(tokens)))]))
        translated = _assignment_projection(_state(_transformed(tokens, dx=37, dy=19)))
        scaled_up = _assignment_projection(_state(_transformed(tokens, scale=2)))
        scaled_down = _assignment_projection(_state(_transformed(tokens, scale=0.5)))
        result[name] = {
            "permutation_same": permuted == baseline,
            "translation_same": translated == baseline,
            "scale_2_same": scaled_up == baseline,
            "scale_half_same": scaled_down == baseline,
        }
    return result


def _fixture_results() -> list[dict[str, object]]:
    rows = []
    for geometry_path in sorted(ROOT.glob("*/geometry.json")):
        geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
        page_results = []
        for page in geometry["pages"]:
            shuffled = dict(page)
            shuffled["tokens"] = list(reversed(page["tokens"]))
            page_results.append(
                {
                    "side": page["side"],
                    "token_count": len(page["tokens"]),
                    "permuted_serialized_tokens_same": canonical_serialized_page_state(
                        geometry["fixture_id"], page
                    )
                    == canonical_serialized_page_state(geometry["fixture_id"], shuffled),
                }
            )
        rows.append({"fixture_id": geometry["fixture_id"], "pages": page_results})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "invariance-diagnostics.json")
    args = parser.parse_args()
    report = {"synthetic": _synthetic_results(), "fixtures": _fixture_results()}
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
