# Manual page-side crop bounds

These bounds were recovered from the twelve local manual PNGs present at recovery time by exact RGB subimage matching against the canonical 300-DPI rasters. Their SHA-256 values in the JSON identify the reviewed bytes; the Stella Maris 03 left crop was re-edited after the historical manual-crop commit. Manual PNGs carried fully opaque alpha; that channel was dropped only in temporary copies for the RGB-only matcher. Original manual crops were not modified.

Production edges use the exact 12/25 ratio. Leading edges round down and trailing exclusive edges round up. That uniformly contains each selected physical interval; every edge extension is less than one 144-DPI pixel. See manual-crop-bounds.json for full hashes, per-edge rational errors, physical errors, and validation provenance.

| Fixture side | 300-DPI bounds [x0,y0,x1,y1] | Exact 144-DPI edges | Configured 144-DPI bounds | Pre-crop side | Output | Validation |
|---|---:|---:|---:|---:|---:|---|
| relativity_pdf10_pp26-27.left | [201, 483, 1334, 2175] | [2412/25, 5796/25, 16008/25, 1044/1] | [96, 231, 641, 1044] | [792, 1224] | [545, 813] | exact/unique; physical PASS |
| relativity_pdf10_pp26-27.right | [0, 59, 1158, 2106] | [0/1, 708/25, 13896/25, 25272/25] | [0, 28, 556, 1011] | [792, 1224] | [556, 983] | exact/unique; physical PASS |
| relativity_pdf17_pp40-41.left | [279, 532, 1396, 2150] | [3348/25, 6384/25, 16752/25, 1032/1] | [133, 255, 671, 1032] | [792, 1224] | [538, 777] | exact/unique; physical PASS |
| relativity_pdf17_pp40-41.right | [72, 146, 1190, 2175] | [864/25, 1752/25, 2856/5, 1044/1] | [34, 70, 572, 1044] | [792, 1224] | [538, 974] | exact/unique; physical PASS |
| relativity_pdf23_pp52-53.left | [321, 470, 1434, 2171] | [3852/25, 1128/5, 17208/25, 26052/25] | [154, 225, 689, 1043] | [792, 1224] | [535, 818] | exact/unique; physical PASS |
| relativity_pdf23_pp52-53.right | [44, 144, 1167, 2178] | [528/25, 1728/25, 14004/25, 26136/25] | [21, 69, 561, 1046] | [792, 1224] | [540, 977] | exact/unique; physical PASS |
| stella_maris_pdf03_session-I.left | [56, 162, 1398, 2225] | [672/25, 1944/25, 16776/25, 1068/1] | [26, 77, 672, 1068] | [792, 1224] | [646, 991] | exact/unique; physical PASS |
| stella_maris_pdf03_session-I.right | [87, 609, 1374, 2317] | [1044/25, 7308/25, 16488/25, 27804/25] | [41, 292, 660, 1113] | [792, 1224] | [619, 821] | exact/unique; physical PASS |
| stella_maris_pdf06_dense-dialogue.left | [66, 92, 1392, 2443] | [792/25, 1104/25, 16704/25, 29316/25] | [31, 44, 669, 1173] | [792, 1224] | [638, 1129] | exact/unique; physical PASS |
| stella_maris_pdf06_dense-dialogue.right | [153, 97, 1471, 2444] | [1836/25, 1164/25, 17652/25, 29328/25] | [73, 46, 707, 1174] | [792, 1224] | [634, 1128] | exact/unique; physical PASS |
| stella_maris_pdf18_session-II_p35.left | [127, 630, 1426, 2333] | [1524/25, 1512/5, 17112/25, 27996/25] | [60, 302, 685, 1120] | [792, 1224] | [625, 818] | exact/unique; physical PASS |
| stella_maris_pdf18_session-II_p35.right | [162, 65, 1463, 2338] | [1944/25, 156/5, 17556/25, 28056/25] | [77, 31, 703, 1123] | [792, 1224] | [626, 1092] | exact/unique; physical PASS |

Source: human-selected manual crop rectangles. These fixture values are operational inputs; automatic physical-page boundary detection remains deferred to a separate issue.
