from paddleocr import PPStructureV3

pipeline = PPStructureV3(
    engine="paddle_dynamic",
    enable_mkldnn=False,
)

results = pipeline.predict(
    "/tmp/test.png"
)

for result in results:
    result.print()
    result.save_to_json("./output")
    result.save_to_markdown("./output")
