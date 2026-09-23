# Evidence corrections

This is a linked erratum, not a rewrite of the earlier evidence snapshots.
The following files remain byte-identical to the verified starting commit:

| Snapshot | SHA-256 | Size |
| --- | --- | ---: |
| `research/geometry/residual-forensics/forensic-report.md` | `988a52b091a5ed134c6808ac6ad441987e128c2c840d9dc9a41871757cfdf72a` | 8061 |
| `research/geometry/residual-forensics/manifest.json` | `c0dab943904ccfdf3fe81f4cad3b30f74d582eef6e99597696abd4d3266170cf` | 23355 |
| `research/geometry/diagnostic-investigation/investigation-report.md` | `879a058a0a56f48959c3fc00c5c22d3d8db4de96b3541c5ab346ee272b6e5d5d` | 14755 |
| `research/geometry/diagnostic-investigation/manifest.json` | `e274a29e1c6c188c672cda95f0c1bb5dd8c2f5e47edcf610bc63a0724bf6668f` | 7716 |

## Historical count correction

The residual report's sentence that the regenerated seven-token results
“agree ... with GH-11's reported counts” is inaccurate. The reproduced
post-GH-11 observation is seven unresolved tokens:

- Relativity 10: four ambiguous and two unassigned;
- Relativity 17: one ambiguous and zero unassigned;
- total: seven.

GH-11's lifecycle record reports a distinct twelve-token result:

- Relativity 10: four ambiguous and six unassigned;
- Relativity 17: one ambiguous and one unassigned;
- total: twelve.

The exact GH-11 twelve-token inventory was not independently reconstructed
from the available research evidence. This erratum does not infer a cause for
the discrepancy and does not relabel the historical twelve-token control as
current evidence. The old report and its manifest are preserved unchanged, so
their recorded artifact relationships are not invalidated.

## Two-sided pixel correction

The earlier diagnostic report described
`two_ordinary_tokens_each_side.png` and
`ocr_rectangle_over_disconnected_regions.png` as different pixel observations.
The two files were byte-identical (`1eed21134de72187451d200f7eff7c7c9b82493e72637e1d157f3a419317a297`).
That claim was therefore unsupported by the preserved artifacts.

The corrected experiment is in this directory. It uses shared, byte-equivalent
TSV payloads and separately generated clean monochrome source pixels. Its
manifest records the input hashes, image hashes, bridge-region measurements,
and complete box-only assignment-state comparisons. The corrected images are
controlled synthetic illustrations, not observations from the scanned books.
