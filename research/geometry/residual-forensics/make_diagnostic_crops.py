"""Generate small, non-authoritative crops for unresolved geometry tokens.

Run this after the six standard preprocess/geometry commands have populated
``/tmp/normalize-residual-forensics``.  The source PDFs remain outside the
research directory; crops are derived from the preprocessed page images.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
WORK_ROOT = Path("/tmp/normalize-residual-forensics")
MARGIN_PX = 80


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "token"


def main() -> None:
    annotations: list[dict[str, object]] = []
    for geometry_path in sorted(ROOT.glob("*/geometry.json")):
        geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
        fixture_id = geometry["fixture_id"]
        for page in geometry["pages"]:
            lines_by_id = {line["line_id"]: line for line in page["physical_lines"]}
            for token in page["tokens"]:
                if token["physical_line_id"] is not None:
                    continue

                source_row = token["source_row"]
                candidate_ids = token["candidate_line_ids"]
                uncertainty = (
                    "ambiguous_line_assignment" if candidate_ids else "unassigned_line_assignment"
                )
                image_path = WORK_ROOT / fixture_id / "preprocessed" / f"{fixture_id}.{page['side']}.png"
                with Image.open(image_path) as source:
                    left = max(0, token["x_px"] - MARGIN_PX)
                    top = max(0, token["y_px"] - MARGIN_PX)
                    right = min(source.width, token["right_px"] + MARGIN_PX)
                    bottom = min(source.height, token["bottom_px"] + MARGIN_PX)
                    crop = source.crop((left, top, right, bottom)).convert("RGB")

                draw = ImageDraw.Draw(crop)
                for line_id in candidate_ids:
                    line = lines_by_id[line_id]
                    if any(line[key] is None for key in ("left_px", "top_px", "right_px", "bottom_px")):
                        # An unassigned token makes affected line bounds
                        # intentionally non-numeric; the token box remains
                        # the only authorized local geometry in that case.
                        continue
                    draw.rectangle(
                        (
                            max(0, line["left_px"] - left),
                            max(0, line["top_px"] - top),
                            min(crop.width - 1, line["right_px"] - left),
                            min(crop.height - 1, line["bottom_px"] - top),
                        ),
                        outline=(40, 110, 220),
                        width=3,
                    )
                draw.rectangle(
                    (
                        token["x_px"] - left,
                        token["y_px"] - top,
                        token["right_px"] - left,
                        token["bottom_px"] - top,
                    ),
                    outline=(220, 40, 40),
                    width=4,
                )

                crop_path = (
                    geometry_path.parent
                    / "crops"
                    / f"{page['side']}-row-{source_row:04d}-{_slug(token['text'])}.png"
                )
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                crop.save(crop_path)
                annotations.append(
                    {
                        "fixture_id": fixture_id,
                        "side": page["side"],
                        "source_row": source_row,
                        "stable_identity": [fixture_id, page["side"], source_row],
                        "text": token["text"],
                        "uncertainty": uncertainty,
                        "candidate_line_ids": candidate_ids,
                        "token_box_px": {
                            key: token[key]
                            for key in ("x_px", "y_px", "right_px", "bottom_px")
                        },
                        "crop_bounds_px": [left, top, right, bottom],
                        "crop_path": crop_path.relative_to(ROOT).as_posix(),
                    }
                )

    (ROOT / "residual-annotations.json").write_text(
        json.dumps(annotations, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
