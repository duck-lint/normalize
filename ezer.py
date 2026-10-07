from pathlib import Path
from paddleocr import PPStructureV3

input_dir = Path(
    "/mnt/f/books/PNGs/McCarthy, Cormac — Stella Maris"
)

output_dir = Path("./output")
output_dir.mkdir(exist_ok=True)

pipeline = PPStructureV3(
    engine="paddle_dynamic",
    enable_mkldnn=False,
)

images = sorted(
    p for p in input_dir.iterdir()
    if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
)

print(f"Found {len(images)} images")

for i, image in enumerate(images, start=1):
    print(f"\n[{i}/{len(images)}] {image.name}")

    try:
        results = pipeline.predict(str(image))

        for result in results:
            result.save_to_json(str(output_dir))
            result.save_to_markdown(str(output_dir))

        print("  ✓ done")

    except Exception as e:
        print(f"  ✗ FAILED: {e}")
