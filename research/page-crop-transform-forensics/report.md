# Manual Crop PDF Transform Forensics

## Finding

All 12 crop PDFs embed the exact same JPEG bytes as the corresponding fixture PDF page (2550×3300 RGB, 8 bits/component, DCTDecode). Each page has one direct image XObject placement through a single `cm` operator followed by `/Im0 Do`; the inspected pages have no Form XObject and no clipping path. Every source and crop page has `/MediaBox [0 0 612 792]`, `/Rotate 90`, and no explicit `/UserUnit`. `/CropBox` is explicit. `/BleedBox`, `/TrimBox`, and `/ArtBox` are absent from the raw page dictionaries; viewers may expose CropBox as their effective values.

The reliable mapping is the PDF content-stream image placement, not a registration estimate. For an embedded image pixel `(x,y)` in a `W×H` JPEG, top-left origin, and its page content `cm=[a,b,c,d,e,f]`:

```text
u = x / W
v = 1 - y / H
x_pdf = a*u + c*v + e
y_pdf = b*u + d*v + f
```

The `1-y/H` term accounts for PDF image space's bottom-left origin. To recover a crop boundary, each raw PDF `/CropBox` corner is inverted through the crop PDF's image `cm`. The resulting image-pixel quadrilateral is then carried through the original fixture PDF's image `cm`, `/Rotate 90`, and 144-DPI scale. The raw `/CropBox` must be used here: PyMuPDF's `page.cropbox` is already converted to its unrotated top-left coordinate representation and cannot be fed directly to the raw content-stream CTM.

## Root cause of the orientation differences

`/Rotate 90` is identical in source and crop documents, so it does not account for the relative differences. The cause is the `cm` matrix in the crop page content stream. The crop PDFs for Relativity 10 and 23 replace the source page's image placement matrix with a different one; mapping the same JPEG sample coordinates through the two matrices yields the measured relative rotations below. There are no Form matrices or clipping operators in these pages that could introduce another transform.

| Pages | Source `cm` `[a b c d e f]` | Crop `cm` `[a b c d e f]` | Relative displayed-raster rotation |
|---|---|---|---:|
| Relativity 10, both sides | `[611.8786011, 11.9998169, -15.5291748, 791.8428955, 7.8252716, -5.9213562]` | `[611.9917603, 1.4663849, -1.8976746, 791.9893799, 0.9528961, -0.7278748]` | +0.986223° |
| Relativity 17, both sides | `[611.9906616, -3.5859375, 4.640625, 791.987915, -2.3156586, 1.7990112]` | identical to source | 0° |
| Relativity 23, both sides | `[612.0, 1.3540649, -1.7523193, 792.0, 0.8761597, -0.6770325]` | `[612.0053101, -1.0365601, 1.3414307, 792.0068359, -0.7336121, 0.5149078]` | +0.223811° |
| Stella Maris 03, both sides | `[611.7385254, -17.9203491, 23.19104, 791.6616211, -11.4647827, 9.129364]` | identical to source | 0° |
| Stella Maris 06, both sides | `[612.0, -1.1953125, 1.546875, 792.0, -0.7734375, 0.5976563]` | identical to source | 0° |
| Stella Maris 18, both sides | `[611.9439697, -8.4232178, 10.9006348, 791.9274902, -5.4223022, 4.2478638]` | `[611.9459229, -8.2831573, 10.7193756, 791.9299927, -5.393219, 4.1766052]` | −0.013114° |

Thus the exact PDF object/operator responsible is the image-placement `cm` in each crop page stream. The PDF structure establishes where the transform enters. It does not establish why the crop-PDF writer changed that matrix or whether a changed placement was intended by the person who authored the crop. No claim about the author's intent is inferred from the matrix alone.

## Recovered bounds for all sides

The `image polygon` column gives the exact retained boundary in original embedded-JPEG pixel coordinates (floating-point values are retained; no integer rounding is applied). `source-page polygon bbox` is the axis-aligned bounding box of the same boundary after applying the original fixture's PDF placement and 144-DPI display transform, with x made side-local for right pages. The bbox is not itself the retained polygon when the four corners are not axis-aligned.

| Fixture | Side | Source raster | Relative angle | Source/crop `cm` same? | Image polygon TL,TR,BR,BL (pixel coordinates) | Image polygon bbox `[x0,y0,x1,y1]` | Source-page polygon bbox at 144 DPI `[x0,y0,x1,y1]` | Prior candidate `[x0,y0,x1,y1]` | Crop render dimensions |
|---|---|---:|---:|---|---|---|---|---|---:|
| relativity_pdf10_pp26-27 | left | 2550×3300 | +0.986223° | no | [[458.40659744532917, 1973.1685967468093], [2159.6864020945945, 1977.2450092779386], [2156.98984015623, 3102.6478056077403], [455.7100355069647, 3098.571393076611]] | [455.7100355069647, 1973.1685967468093, 2159.6864020945945, 3102.6478056077403] | [89.11281011370347, 223.15442845153927, 643.2798873376672, 1048.9428849929257] | [95.7528, 220.412, 635.942, 1037.02] | 541×817 |
| relativity_pdf10_pp26-27 | right | 2550×3300 | +0.986223° | no | [[74.35075597442258, 459.15307654159346], [2127.5574450145473, 464.07273611395146], [2124.712071014349, 1651.5818420123799], [71.50538197422458, 1646.6621824400218]] | [71.50538197422458, 459.15307654159346, 2127.5574450145473, 1651.5818420123799] | [-9.725000719391574, 24.594851952748115, 577.1561164173477, 1019.7957460996412] | [0.2179999999999609, 34.3264, 570.2180000000001, 1019.858] | 570×986 |
| relativity_pdf17_pp40-41 | left | 2550×3300 | -0.000000° | yes | [[543.5399504059244, 1915.4232819040524], [2152.563426597841, 1905.9952661126706], [2159.0251963807764, 3008.787148170115], [550.0017201888595, 3018.2151639614963]] | [543.5399504059244, 1905.9952661126706, 2159.0251963807764, 3018.2151639614963] | [137.30580000000003, 260.158, 666.6560000000001, 1032.504] | [137.3058, 260.158, 666.656, 1032.504] | 530×773 |
| relativity_pdf17_pp40-41 | right | 2550×3300 | -0.000000° | yes | [[139.91793557016393, 479.97051797216494], [2168.6050737742394, 468.08349788963204], [2175.155048787092, 1585.928842817914], [146.46791058301594, 1597.815862900447]] | [139.91793557016393, 468.08349788963204, 2175.155048787092, 1597.815862900447] | [28.221999999999866, 70.45959999999998, 564.798, 1044.248] | [28.22199999999998, 70.4596, 564.798, 1044.248] | 537×974 |
| relativity_pdf23_pp52-53 | left | 2550×3300 | +0.223811° | no | [[450.41920831657717, 1873.0073792386388], [2159.1953132901835, 1870.1132062935433], [2161.066325775792, 2974.7955025923684], [452.29022080218584, 2977.689675537464]] | [450.41920831657717, 1870.1132062935433, 2161.066325775792, 2977.689675537464] | [153.8352282420968, 216.43805653721904, 687.2846866347626, 1038.7187847922262] | [155.3724, 215.896, 685.626, 1036.118] | 531×821 |
| relativity_pdf23_pp52-53 | right | 2550×3300 | +0.223811° | no | [[135.64929551276688, 473.3942601039761], [2179.4069496852744, 469.93272521252806], [2181.325775080753, 1602.844696873798], [137.56812090824545, 1606.3062317652461]] | [135.64929551276688, 469.93272521252806, 2181.325775080753, 1606.3062317652461] | [19.765042704745383, 63.86209288763684, 567.3927825477001, 1046.9862926552673] | [21.898000000000025, 65.943, 565.702, 1046.958] | 544×982 |
| stella_maris_pdf03_session-I | left | 2550×3300 | +0.000000° | yes | [[292.84337240915966, 2024.7400729570106], [2356.435760192416, 1964.2889251969887], [2390.4360642846063, 3124.941308863975], [326.84367650135005, 3185.392456623997]] | [292.84337240915966, 1964.2889251969887, 2390.4360642846063, 3185.392456623997] | [68.65300000000002, 135.49919999999997, 626.0059999999999, 1126.4499999999998] | [68.653, 135.4992, 626.006, 1126.45] | 558×991 |
| stella_maris_pdf03_session-I | right | 2550×3300 | +0.000000° | yes | [[560.1667501351008, 288.5539670306966], [2275.7489679374694, 238.29747512037156], [2313.772004575733, 1536.271987018752], [598.189786773364, 1586.5284789290768]] | [560.1667501351008, 238.29747512037156, 2313.772004575733, 1586.5284789290768] | [39.965999999999894, 288.162, 663.262, 1111.9960000000003] | [39.96600000000001, 288.162, 663.262, 1111.996] | 624×824 |
| stella_maris_pdf06_dense-dialogue | left | 2550×3300 | +0.000000° | yes | [[98.40433373428192, 1928.4855386190084], [2433.876674614329, 1923.924069203227], [2436.423893087566, 3228.09992750048], [100.95155220751874, 3232.6613969162613]] | [98.40433373428192, 1923.924069203227, 2436.423893087566, 3232.6613969162613] | [33.42320000000002, 46.973000000000006, 659.4300000000001, 1168.0040000000001] | [33.4232, 46.973, 659.43, 1168.004] | 627×1122 |
| stella_maris_pdf06_dense-dialogue | right | 2550×3300 | +0.000000° | yes | [[91.2185815233554, 176.4204066246291], [2441.746281638432, 171.82953221034194], [2444.3670154562296, 1513.645246922937], [93.83931534115342, 1518.2361213372242]] | [91.2185815233554, 171.82953221034194, 2444.3670154562296, 1518.2361213372242] | [64.35399999999993, 45.1664, 708.4279999999999, 1173.4240000000002] | [64.35400000000004, 45.1664, 708.4280000000001, 1173.424] | 645×1129 |
| stella_maris_pdf18_session-II_p35 | left | 2550×3300 | -0.013114° | no | [[635.7182856678465, 1885.9316870655762], [2348.1142163149943, 1862.7530943607896], [2365.5363716330316, 3149.873565478302], [653.1404409858841, 3173.052158183089]] | [635.7182856678465, 1862.7530943607896, 2365.5363716330316, 3173.052158183089] | [64.92203209100238, 303.4727787759798, 682.9865380034904, 1125.6421238818646] | [65.0396, 303.518, 682.916, 1125.546] | 618×823 |
| stella_maris_pdf18_session-II_p35 | right | 2550×3300 | -0.013114° | no | [[46.51382074019693, 209.42895871784614], [2319.672402299959, 178.66001330494035], [2337.1454698128014, 1469.541794488106], [63.986888253039425, 1500.3107399010119]] | [46.51382074019693, 178.66001330494035, 2337.1454698128014, 1500.3107399010119] | [79.59500236734925, 31.755838750156766, 699.5267202268697, 1123.1171719158854] | [79.71199999999999, 31.6164, 699.394, 1122.836] | 620×1092 |

## What the rectangles do and do not establish

The exact inverse transform establishes a quadrilateral for every side in raw JPEG pixel coordinates. This is not evidence that the person intentionally drew a rotated quadrilateral: the source fixture itself places the JPEG with a nontrivial `cm`, so even a rectangular CropBox in page/display coordinates maps to a slightly skewed quadrilateral in JPEG pixels. The distinction is visible in the records: for six sides, crop and source `cm` are identical and the recovered boundary maps to an axis-aligned rectangle in the original source page's 144-DPI display frame; for Relativity 10 and 23, crop `cm` differs and the recovered boundary remains a quadrilateral in that source-page frame. Stella Maris 18 also has a distinct crop matrix, but the induced edge deviations are below 0.25 displayed pixel.

For the four Relativity 10/23 sides, the crop PDF encodes enough geometry to state the exact quadrilateral, but not enough provenance to decide whether that quadrilateral is the intended page boundary or an incidental export transform around an intended rectangle. The result is therefore **unresolved as to intended shape** for those sides. Treating the crop PDF's own orientation as authoritative would contradict the requested source-image coordinate analysis; silently replacing its quadrilateral with a bounding rectangle would add pixels and change the boundary. Accordingly, this investigation does not authorize production cropping from these artifacts without resolving the intended shape.

## Reconciliation with prior 144-DPI candidates

The earlier candidate rectangles are exactly the crop PDF's visible CropBox expressed in its own 144-DPI display frame and split-side-local x coordinates. They are useful to describe the manual crop PDF render, but they are not automatically the same as the retained region in the original fixture render.

For Relativity 17, Stella Maris 03, and Stella Maris 06, the source and crop image matrices are equal, so mapping the recovered bounds back through the original fixture reproduces the prior candidate rectangle to floating-point precision. For Stella Maris 18, the crop `cm` differs slightly: source-frame polygon edges deviate by at most 0.250 px from axis alignment, with the bounding box differing from the prior candidate by less than 0.3 px. For Relativity 10 and 23, the altered image placement makes the polygon differ materially from the prior rectangle. Relative to the prior candidate's four edges, the mapped source-frame polygon corners shift by up to about 11 px for Relativity 10 and 2.2 px for Relativity 23; the exact corners and bounds are in `results.json`. Those discrepancies are explained by the measured `cm` changes, not by rounding.

The crop reference raster dimensions match the CropBox dimensions after `/Rotate 90` and 144-DPI rendering, rounded by the renderer to integer pixels. `results.json` contains raw CropBox values, matrices, inverse round-trip errors, rendered dimensions, full PDF hashes, and image hashes for independent checking.

## Classification and implementation boundary

- **Six sides:** their crop boundary is a clear axis-aligned rectangle in the original source-page display frame; the inverse image-pixel representation is a quadrilateral because the fixture's own image placement is affine.
- **Stella Maris 18, two sides:** the source-frame boundary is within 0.25 px of an axis-aligned rectangle, but the PDF alone does not show whether to snap that subpixel transform or preserve it.
- **Relativity 10 and 23, four sides:** exact source-frame retained regions are non-axis-aligned quadrilaterals, and the documents do not establish whether the altered transform is incidental or intended.

Therefore the requested Case A is **not established for all 12 sides**. No exact source-image axis-aligned crop rectangle can be supplied for all sides without adding a rounding/snap policy or deciding the disputed Relativity transforms. The evidence does **not** yet authorize implementation of post-split rectangular per-page cropping across all 12 sides without deskew/affine handling. This is a research conclusion only; no production code or fixture authority was changed.

## Verification

- `run_forensics.py` opens source and crop PDFs read-only, checks corresponding image dimensions and extracted JPEG SHA-256 equality, extracts raw page dictionaries/content streams, inverts all CropBox corners, checks forward/inverse round trips, and records source/crop file hashes.
- For all 24 source/crop pages, the four known JPEG corners transformed through the extracted `cm` match PyMuPDF's rendered image-placement matrix within `0.00005 pt`. Crop render dimensions also match CropBox-derived dimensions at 144 DPI to raster rounding.
- The regenerated records cover 12 page sides. The source and crop raster render sizes are recorded, as are CropBox-derived display dimensions.
- Input PDFs and all crop files were only read. No source or crop file was written by the investigation.
- Research-only checks: see `test_forensics.py`.
