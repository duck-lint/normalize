#!/usr/bin/env python3
"""Save raw PaddleOCR JSON and Markdown for each scanned page."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", required=True, type=Path, help="Directory of PNG/JPG page scans")
    parser.add_argument("--out", required=True, type=Path, help="New directory for raw Paddle output")
    parser.add_argument("--device", default="gpu:0", help="Paddle device, e.g. gpu:0 or cpu")
    args = parser.parse_args()
    images = sorted(path for path in args.images.iterdir()
                    if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg"})
    if not images:
        parser.error("No page images found")
    if len({image.stem for image in images}) != len(images):
        parser.error("Page image stems must be unique")
    if args.out.exists():
        parser.error("Output exists; use a new directory to preserve raw observations")

    from paddleocr import PPStructureV3

    pipeline = PPStructureV3(
        device=args.device,
        markdown_ignore_labels=["number", "header", "footer", "footer_image", "aside_text"],
    )
    args.out.mkdir(parents=True)
    for index, image in enumerate(images, start=1):
        print(f"[{index}/{len(images)}] {image.name}")
        # Let failures stop the scan rather than silently leaving missing pages.
        for result in pipeline.predict(str(image)):
            result.save_to_json(str(args.out))
            result.save_to_markdown(str(args.out))


if __name__ == "__main__":
    main()
