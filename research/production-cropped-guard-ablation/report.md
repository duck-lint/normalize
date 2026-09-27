# Production-cropped oversized-guard ablation

## Scope and method

This is a bounded research result on the six exact fixture PDFs and the twelve page-side images emitted by current Slice 1 preprocessing at 144 DPI. `run_ablation.py` calls production preprocessing and production `run_geometry` unchanged. The production OCR invocation ran once per page (`eng`, `--psm 6`, TSV); the captured TSV was parsed once and the same admitted token objects, source rows, boxes, confidence values, and locators were sent to both grouping variants. Tesseract was 5.3.4. Image files and diagnostic sheets remain local under `/tmp/normalize-guard-ablation/`.

The off variant uses every token box’s observed right edge for cumulative coverage and applies the ordinary adjacent-box gap predicate in the candidate-support check. It does not alter token admission, vertical predicates, tolerance, the production-selected slope, gap limit, reconciliation, or uncertainty rules. Slope was held at the production guard-on value in both variants. The guard-on baseline is the actual production geometry output, and a second call to the unmodified production grouping entry point is checked against it.

Page pixels are the authority for event adjudication. OCR strings locate the source rows only. Per-token ink occupancy, centroid, and vertical extent in `results.json` are descriptive observations; no numeric pixel cutoff made an adjudication.

## A. Production input provenance

The crop rectangle is post-split side-local production pixels. The source PDF SHA is repeated per side to make each page record independently traceable. Full page/token identities and every admitted row are in `results.json`.

| Fixture side | Output px | Crop rect px | Source PDF SHA-256 | Preprocess metadata SHA-256 | Output image SHA-256 | TSV SHA-256 | Admitted-token record SHA-256 |
|---|---:|---|---|---|---|---|---|
| `relativity_pdf10_pp26-27.left` | 545×813 | `[96, 231, 641, 1044]` | `de6ac98f0b4a558e4be70005f1060d0fd42f4d2d4db0eb5f859b78978ac536b3` | `bb132cd99a03a8aa80068c6fd2775e05c40974fa6b0c76060d02394d60393193` | `9a71eb9ca1a4873a619f917fd8167e2250ea83a814b469a70d175b739275b79e` | `b7ed62e7d4b953d1ecd2c35168eacc5f9291ddcde29ed7fe63e0ff6be62babc9` | `268ae5f7ccc0e57fa30b9b305332320e7d19053058adc13e374bc4c40d737dca` |
| `relativity_pdf10_pp26-27.right` | 556×983 | `[0, 28, 556, 1011]` | `de6ac98f0b4a558e4be70005f1060d0fd42f4d2d4db0eb5f859b78978ac536b3` | `bb132cd99a03a8aa80068c6fd2775e05c40974fa6b0c76060d02394d60393193` | `9782e5d3fd24b6b617e203a4c653de4db7f9aef1f26a9defffba3bb002eae35a` | `bafd6758f4357377ce3bdf78b9f13092defad61fed4297870a76053f8fe3744b` | `4281eb448507a6c90d5862ab0d58ff11ea768b99f006967762f6be881cab12d6` |
| `relativity_pdf17_pp40-41.left` | 538×777 | `[133, 255, 671, 1032]` | `0ab3c29ffd98fee0a61ab3a9c054dfebc18167ccf10c9283f47aec274a61e532` | `eac3de2ced51452ecb00db7f0dda3aa43aaa4e60e25b0df628275c4f38c49e1d` | `dda166075f605f256a3c3e62141c2d46b820a5ca5552238880f38ca905b54bc8` | `4e108ef5c4b6d5b0e2f2126e0cf776588e067241a25f4336965e52415a466ec0` | `893f07b5a0281ea8ce2f8f01e30d286c927ecf319c76488541bc4ed16c6f9e24` |
| `relativity_pdf17_pp40-41.right` | 538×974 | `[34, 70, 572, 1044]` | `0ab3c29ffd98fee0a61ab3a9c054dfebc18167ccf10c9283f47aec274a61e532` | `eac3de2ced51452ecb00db7f0dda3aa43aaa4e60e25b0df628275c4f38c49e1d` | `d3187f901642ad02c89f728f81a73eef114e70a4e69ffc1e148eef1d3d6ea815` | `b0d480a89a3d1455efd7dd018453d55d2e9b2d5c4d8fba64d70a6dd03407bd88` | `7db16299bb62fd53e869d90d972b8d2f56587a9ba41f32e42702af76b87e2d98` |
| `relativity_pdf23_pp52-53.left` | 535×818 | `[154, 225, 689, 1043]` | `aad2a70bfa047fe7ee08eb3d16d0e23998ef08cbd82d67d4a443f1aa8169a2d4` | `b3b1efe80d7d46de619d3dc8f8b037e8ae901e5644a4549c797b19b1fddc50d9` | `e432e07f11e97740f85d87823b4e476cb3b307566837e3f724f072ecdb2caab3` | `3f054028c1bb134434f9b99559cdd2f12778fa98230cb57d789e7ea4ded47245` | `74b493d939770503e3cc045233638d7c143a0ccecf446e94046fd7418cd4c972` |
| `relativity_pdf23_pp52-53.right` | 540×977 | `[21, 69, 561, 1046]` | `aad2a70bfa047fe7ee08eb3d16d0e23998ef08cbd82d67d4a443f1aa8169a2d4` | `b3b1efe80d7d46de619d3dc8f8b037e8ae901e5644a4549c797b19b1fddc50d9` | `ab8e444abba403e4498118f97e063aafe3409fbd8628134d9f1197abe7271bc5` | `3d700d562df0146fa3599e1cdd1d2a637916c3eb24695017efa99371fd2a50b8` | `94ab22e69ff19d6fba87dd5567651da17fccd473f39e79ada93e794d3f27b454` |
| `stella_maris_pdf03_session-I.left` | 646×991 | `[26, 77, 672, 1068]` | `bb501cd40b495ade5151c74a1fb1a581876631115550971ee54e3e384e328ef4` | `6ec465d62e0341dabc6ed5fb50494dfc9e142ad794855d1252dd91094f9a1101` | `1a6b2a3b5bb4ee19df2617d063ae29e4e1a891253c0d815146d3d65d0987bbcd` | `429d87facb63716c0f436f2ba33771e3fd4dd9591e3e8dea9a41312e2d3401fa` | `a882b38217bea688bd8956682b87ddc9c0c674118c98ad05ccd3a5e28f278523` |
| `stella_maris_pdf03_session-I.right` | 619×821 | `[41, 292, 660, 1113]` | `bb501cd40b495ade5151c74a1fb1a581876631115550971ee54e3e384e328ef4` | `6ec465d62e0341dabc6ed5fb50494dfc9e142ad794855d1252dd91094f9a1101` | `ecb5322bdd51b08de5daf9fbba0b97a96da13f89cda3ef49d47f3211fc1d1124` | `6a76ba683a9a578fae9cc0617c7e16c9b9335dfc8dd1961b27273c0d7ce67586` | `22d62263fce0b5a0182b21f5ff26b1ba131fb90abcadee79d7ad0f7c8ca0140a` |
| `stella_maris_pdf06_dense-dialogue.left` | 638×1129 | `[31, 44, 669, 1173]` | `d2e63e236ba54477f5e4080d72cbd2d89fb8afbb2ddefe04b6ab60dbc55ee9bc` | `899fce950b0feb628533c8e6e954f5f2f5b6fd29af470338c61eb9170bbca35a` | `488c5214be76b0677ce5df2816b716d85031d7d36b967fdf74c2b8d09635dc9a` | `7db712535fb9aaa5c292881cbc6486f9b1f19ee4dd9131148a6dd12ec600a150` | `dfe804989fc2c454fb7b86ac68d8da48e936e4a4fc1955ac7de20dbe2aa6fdc2` |
| `stella_maris_pdf06_dense-dialogue.right` | 634×1128 | `[73, 46, 707, 1174]` | `d2e63e236ba54477f5e4080d72cbd2d89fb8afbb2ddefe04b6ab60dbc55ee9bc` | `899fce950b0feb628533c8e6e954f5f2f5b6fd29af470338c61eb9170bbca35a` | `710cc423a2d4d1b43fce09cee6e93c118253e045e1cf971e3e02324101705f68` | `bca4291398cb9a63ae45793c7ce26db9748a883ce3504dca4cce63870970f50d` | `c1611cf1092ffeea1e51c126584ce9a853d4cf0d010020fbe640f75290dccc8b` |
| `stella_maris_pdf18_session-II_p35.left` | 625×818 | `[60, 302, 685, 1120]` | `c3a3ea3bda79cb462cb537f39d3199058afa84d6f1a784507aacd86a31e80c23` | `3c0006e2dacd071b81e39a962096fa8e2b48b5c001ec905ea9a52a70d493de1d` | `7a255ea8db43f17bec2b4325079c948910e4b21df506d23eca5f29cf493ceb56` | `5bcd47c147c7361301e30aff857b40ef711e000a51095674d85122e91666f3ce` | `7e4c8fc9a6e629c51617298a12fef1f21eabf891d33e7d673ccaed3eae5cbb88` |
| `stella_maris_pdf18_session-II_p35.right` | 626×1092 | `[77, 31, 703, 1123]` | `c3a3ea3bda79cb462cb537f39d3199058afa84d6f1a784507aacd86a31e80c23` | `3c0006e2dacd071b81e39a962096fa8e2b48b5c001ec905ea9a52a70d493de1d` | `7ebe91070f389cf9302d41439f278ffad3b3e14ef9dde257dbcaa4e415c9e13b` | `3f2a73b3bfdf833f75ddf92dd3fd2efececd9a813887255b28e2cea831404c4e` | `00332780274da7aa649397a82d8948e1f4b8524c597d2a28e87182460a151ea3` |

Preprocessing config SHA-256: `347551a2f59b8c0baaf59a11b81a0d4a274c9e80809e10479a895759d383181c`. Each side record declares `same_ocr_inputs_proven: true`; the guard-on and guard-off token identity hashes are equal to each other and to the admitted-token record hash.

## B. Guard-on baseline and paired measurements

| Page side | Tokens | Lines on/off | Ambiguous | Unassigned | Median width px | Gap limit px | Oversized threshold px | Oversized / extent withheld |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `relativity_pdf10_pp26-27.left` | 191 | 34/26 | 0 | 0 | 36 | 72 | 108 | 10 / 9 |
| `relativity_pdf10_pp26-27.right` | 263 | 65/62 | 0 | 1 | 39 | 78 | 117 | 6 / 6 |
| `relativity_pdf17_pp40-41.left` | 138 | 35/30 | 0 | 0 | 38.5 | 77 | 115.5 | 6 / 6 |
| `relativity_pdf17_pp40-41.right` | 305 | 42/32 | 0 | 0 | 33 | 66 | 99 | 12 / 12 |
| `relativity_pdf23_pp52-53.left` | 143 | 29/24 | 0 | 0 | 29 | 58 | 87 | 8 / 8 |
| `relativity_pdf23_pp52-53.right` | 226 | 34/32 | 3 | 0 | 34 | 68 | 102 | 3 / 3 |
| `stella_maris_pdf03_session-I.right` | 133 | 23/23 | 0 | 0 | 37 | 74 | 111 | 0 / 0 |
| `stella_maris_pdf06_dense-dialogue.left` | 255 | 48/42 | 0 | 0 | 36 | 72 | 108 | 10 / 9 |
| `stella_maris_pdf06_dense-dialogue.right` | 271 | 43/38 | 0 | 0 | 35 | 70 | 105 | 8 / 8 |
| `stella_maris_pdf18_session-II_p35.left` | 68 | 23/23 | 0 | 0 | 42 | 84 | 126 | 0 / 0 |
| `stella_maris_pdf18_session-II_p35.right` | 132 | 35/33 | 0 | 0 | 40.5 | 81 | 121.5 | 4 / 4 |

Across the primary 11 sides: 67 boxes met the current `width > 1.5 × gap_limit` classification; in 65 unsupported cases the production path withheld full right extent. Forty-six distinct oversized classifications caused 46 stale-extent split boundaries whose actual-box gap would have passed the unchanged ordinary gap test. Those boundaries formed 43 connected changed-grouping events.

Production geometry returned `success` for Relativity 17, Stella Maris 06, and Stella Maris 18, and `uncertain` without geometry errors for Relativity 10, Relativity 23, and Stella Maris 03. The declared uncertainties were one unassigned token on Relativity 10 right, three ambiguous tokens on Relativity 23 right, and the blank Stella Maris 03 left-side ambiguity/unassigned records. Line-count differences are reported as effects of the changed grouping input; they are not used as correctness evidence.

## C–D. Differential, complete events, and adjudication

All 43 primary changed events were adjudicated `repaired_false_split`; destructive merges 0, benign differences 0, unresolved 0. For each event, `results.json` records affected source rows and `token-NNNN` IDs; bbox, confidence and OCR locator; full on/off line memberships; exact newly joined pairs; the responsible oversized source row(s); the related production predicate trace, including stale and actual gaps, threshold, bridge support, coverage updates, and selected slope; and per-box pixel metrics. The page-level `supported_bridge_predicate_calls` array preserves every production `_supported_bridge_ids()` call, including each input token set and returned supported-bridge identities. `adjudications.json` is the separate reviewed decision record. The token source row, not OCR wording, disambiguates repeated strings.

| Event | Changed source rows | Causal oversized source rows | Class |
|---|---|---|---|
| `relativity_pdf10_pp26-27.left.event-001` | `5,6,7,8` | `6` | `repaired_false_split` |
| `relativity_pdf10_pp26-27.left.event-002` | `10,11,12,13` | `12` | `repaired_false_split` |
| `relativity_pdf10_pp26-27.left.event-003` | `56,57,58,59,60,61,62` | `57,58` | `repaired_false_split` |
| `relativity_pdf10_pp26-27.left.event-004` | `64,65,66,67,68,69,70,71` | `70` | `repaired_false_split` |
| `relativity_pdf10_pp26-27.left.event-005` | `101,102,103,104,105,106` | `101` | `repaired_false_split` |
| `relativity_pdf10_pp26-27.left.event-006` | `141,142,143,144,145,146,147,148` | `146` | `repaired_false_split` |
| `relativity_pdf10_pp26-27.left.event-007` | `150,151,152,153,154,155,156,157,158` | `151` | `repaired_false_split` |
| `relativity_pdf10_pp26-27.right.event-001` | `178,179,180,181` | `179` | `repaired_false_split` |
| `relativity_pdf10_pp26-27.right.event-002` | `193,194,195` | `194` | `repaired_false_split` |
| `relativity_pdf10_pp26-27.right.event-003` | `242,243,244,245,246` | `242` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.left.event-001` | `5,6,7,8` | `6` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.left.event-002` | `10,11,12,13,14,15,16,17,18` | `14` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.left.event-003` | `31,32,33` | `32` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.left.event-004` | `145,146,147,148,149,150` | `147` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.left.event-005` | `151,152` | `151` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.right.event-001` | `26,27,28,29,30,31,32,33,34` | `30` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.right.event-002` | `37,38,39,40,41,42,43` | `40` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.right.event-003` | `75,76,77,78,79,80,81,82` | `75,80` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.right.event-004` | `109,110,111,112,113,114,115,116,117,118,119` | `116` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.right.event-005` | `121,122,123,124,125,126,127,128,129,130,131,132` | `125` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.right.event-006` | `158,159,160,161,162,163,164,165,166` | `160` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.right.event-007` | `228,229,230,231,232,233,234,235,236,237` | `234` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.right.event-008` | `250,251,252,253,254,255,256,257,258` | `255` | `repaired_false_split` |
| `relativity_pdf17_pp40-41.right.event-009` | `308,309,310,311,312,313,314,315,316` | `315` | `repaired_false_split` |
| `relativity_pdf23_pp52-53.left.event-001` | `5,6,7` | `6` | `repaired_false_split` |
| `relativity_pdf23_pp52-53.left.event-002` | `15,16,17,18,19,20,21,22,23,24,25,26` | `17` | `repaired_false_split` |
| `relativity_pdf23_pp52-53.left.event-003` | `28,29,30,31,32,33,34,35,36,37,38` | `31` | `repaired_false_split` |
| `relativity_pdf23_pp52-53.left.event-004` | `53,54,55,56,57,58,59,60,61,62,63,64` | `63` | `repaired_false_split` |
| `relativity_pdf23_pp52-53.left.event-005` | `80,81,82,83,84,85,86,87,88,89,90,91,92` | `82` | `repaired_false_split` |
| `relativity_pdf23_pp52-53.right.event-001` | `161,162,163,164,165,166` | `162,163` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.left.event-001` | `107,108,109,110,111,112,113,114,115,116,117,118` | `109` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.left.event-002` | `135,136,137,138,139` | `138` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.left.event-003` | `178,179,180,181,182,183,184,185,186,187,188` | `185` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.left.event-004` | `204,205,206,207,208,209,210,211,212,213,214` | `212` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.left.event-005` | `246,247,248,249,250,251,252` | `250` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.left.event-006` | `255,256,257,258,259,260,261,262` | `255` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.right.event-001` | `89,90,91,92,93,94,95,96,97,98,99,100,101,102` | `89` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.right.event-002` | `115,116,117,118,119,120,121,122,123` | `118` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.right.event-003` | `125,126,127,128,129,130,131,132,133,134` | `127` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.right.event-004` | `150,151,152,153,154,155,156,157,158,159,160,161,162,163` | `150` | `repaired_false_split` |
| `stella_maris_pdf06_dense-dialogue.right.event-005` | `227,228,229,230,231,232,233,234,235,236` | `229` | `repaired_false_split` |
| `stella_maris_pdf18_session-II_p35.right.event-001` | `62,63,64,65,66,67,68` | `64` | `repaired_false_split` |
| `stella_maris_pdf18_session-II_p35.right.event-002` | `170,171,172,173,174,175,176` | `173` | `repaired_false_split` |

Visual review found that the boxes newly related by each event occupy one printed row in the production raster; none cross a visibly separate text row, column, or figure region. The per-event ink metrics corroborate that visual inspection but do not substitute for it. The diagnostic PNGs are local-only and not in this commit.

## E. Historical locators

These are crop-local OCR rows from this 144-DPI run, not carried historical token identities:

| Historical locator/page | Current observed behavior |
|---|---|
| Relativity 10 left: `system` | 2 current occurrences; both memberships unchanged on/off. |
| Relativity 10 left: `that` | 4 occurrences; row 144 changes membership, 3 do not. |
| Relativity 10 left: `the` | 13 occurrences; rows 5, 11, 61, and 69 change membership. |
| Relativity 10 left: `with`, `respect` | 2 current occurrences of each; none change membership. |
| Relativity 10 right: `impossible` | 1 current occurrence; membership unchanged. |
| Relativity 17 right: capital `A` | 10 current occurrences; 4 change membership. |
| Relativity 10 heading row | Current rows 5–8 split into two guard-on groups and form one visible heading line guard-off. |
| `embankment` | Two current Relativity 10 left occurrences and five Relativity 17 right occurrences participate in changed events; each is recorded by its current source row. |
| Relativity 17 right: `reference-body`, `conclusion` | One occurrence each; `reference-body` changes membership, `conclusion` does not. |
| Relativity 23 left: `x'-axis`, `x' = 0` locators | No exact `x'-axis` token was emitted; OCR produced two `x'` tokens and two `=0`-like tokens. Both `x'` rows and one `=0` row change membership. Current event/token rows are in the locator records. |

Full per-occurrence membership records are in `secondary_historical_locators` in `results.json`. A matching string is only a locator; no historical ID equivalence or “resolved residual” claim is made.

## F. Genuine-gap controls

Two clean production-pixel controls were found in the Relativity 17 left-side diagram. They are separate figure labels/marks with visible intervening blank page area, not prose gaps selected because of OCR wording. In guard-off they remain separate under the same cumulative extent predicate:

| Figure items (source rows) | Prior covered right | Next x | Actual gap | Page gap limit | Guard-off result |
|---|---:|---:|---:|---:|---|
| `relativity_pdf17_pp40-41.left` rows `[85]` → `86` | 84 | 202 | 118 | 77 | separate |
| `relativity_pdf17_pp40-41.left` rows `[90]` → `93` | 129 | 383 | 254 | 77 | separate |

Thus guard-off trusts real box extents before the same gap check; it does not disable the ordinary horizontal separation rule. The focused synthetic test also verifies an oversized one-token bridge case still splits when its true gap exceeds the limit.

## G. Blank-side diagnostic

`stella_maris_pdf03_session-I.left`: 385 admitted boxes; 113 guard-on lines / 101 guard-off lines; 34 guard-triggering boxes; 12 changed events. Those events are labeled `excluded_blank_diagnostic`; they are excluded from every primary count and the decision.

## H. Historical 300-DPI comparison

The earlier manual-crop study reported 68 oversized boxes, 46 classifications affecting partitioning, 44 repaired false-split events, zero destructive merges, and zero unresolved events on 11 nonblank 300-DPI pages. This independent 144-DPI production-crop run found 67, 46, and 43 respectively, also with zero destructive and unresolved events. The count-level causal classification is numerically the same; one fewer connected changed event was adjudicated here. No token IDs or event identities were forced across DPI/rerender. Different DPI, OCR segmentation, and page-local width statistics are plausible sources of the count difference; the records do not isolate which one caused it. The corpus-bounded no-destructive-merge observation survives in this run, not as a universal guarantee.

## I. Decision

**Corpus-bounded evidence supports a separate production change removing the oversized-token special case.** All primary changed events were adjudicated; 43 false splits were repaired; zero destructive merges and zero unresolved events were observed; and genuine large-gap diagram controls remained split. This research branch makes no production behavior change and does not implement removal.

## J. Verification

- Branch base: current `origin/guh`; dedicated branch: `research/production-cropped-guard-ablation`.
- Exact six source PDFs passed the local availability gate. Their source paths and SHA-256 values appear in Section A and were rechecked after preprocessing.
- Production preprocessing and production OCR/geometry ran on all six fixture PDFs / twelve sides. Tesseract was invoked exactly 12 times, once per emitted side; both variants used those same persisted OCR identities.
- Focused research tests: 6 passed. The full repository suite ran and reported 9 failures, all before any production-source change: tests requiring absent ignored manual-crop or historical diagnostic PNGs, or historical commit objects not present in this clone. Missing raster inputs include `tests/fixtures/manual-page-crops/*.png`, `research/geometry/evidence-corrections/pixel-cases/*.png`, and `research/geometry/vertical-clustering-investigation/recovered-inputs/**/*.png`. Historical checks require commit objects `699771d01c1a83c6f89c6a7eb2102e79a709b671` and `dfa6cd1ef2387364dded5ba86f92635d94875b4d`, which are absent locally. The affected tests are `test_all_twelve_manual_crops_recover_uniquely_from_canonical_source_renders`, `test_measurement_interface_returns_raw_observations_only`, `test_synthetic_controls_and_negative_controls_are_discriminating`, four `test_verification_repair.py` cases, `test_recovered_evidence_and_manifest_hashes_are_durable`, and `test_fidelity_gate_rejects_an_injected_control_mismatch`. The verification-repair mismatch case also exits at its missing-ancestor gate before reaching the injected check. These absent resources are outside this task; no substitutes were generated.
- All 6 fixture preprocessing runs returned success at 144 DPI; all 12 output image hashes were rechecked. Production `run_geometry` completed for all six fixtures, and the experiment captured exactly 12 TSV outputs total, one per side.
- All 6 source fixture PDFs still match the hashes recorded at input capture. `fixtures/preprocessing.json`, geometry/OCR/preprocessing production code, and structural expected JSON have no diff from `origin/guh`.
- `git diff --check` passed. `git ls-files '*.png' '*.pdf'` and the staged-name check were empty before commit. No page images or PDFs are included.
- No production geometry, OCR, preprocessing, crop configuration, source PDF, expected JSON, PNG, or PDF changes are part of this research commit.
- Full per-side hashes, token records, event trace and measured pixel evidence: `results.json`; human review decisions: `adjudications.json`.
