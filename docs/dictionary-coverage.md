# Dictionary coverage before lexical review

This is a deterministic recognition filter, **not an OCR corrector**. A token
recognized by an external resource no longer produces an `unrecognized_token`
finding solely for lack of dictionary coverage. Other triggers (e.g.,
`lower_upper`) remain independent. No recognized token is thereby certified
as source-faithful or automatically admitted to the persistent human lexicon.

## Locale coverage (future probes)

Install the locale-specific Hunspell pairs in the **tooling checkout's** WSL
environment, where Normalize runs (not the isolated Codex review workroot):

```bash
sudo apt-get update
sudo apt-get install -y hunspell-en-ca hunspell-en-gb
ls -l /usr/share/hunspell/{en_US,en_CA,en_GB,de_DE,fr_FR}.{aff,dic}
```

The probe retains its previous default (`en_US de_DE fr_FR`) for backward
compatibility. Opt into expanded coverage explicitly:

```bash
python normalize_probe.py \
  --scans "$scans" --paddle "$whitespace_output" \
  --lexicon "$lexicon" \
  --locales en_US en_CA en_GB de_DE fr_FR \
  --out "$new_probe"
```

Any locale listed in `--locales` is **required**. The probe will fail if
its .aff or .dic file is missing. File content hashes are stored by language
under `inputs.dictionary_sha256`. The optional `suggest_segments.py`
sidecar must use the *identical* list of locales and files; it fails closed
when hashes do not match.

## Sourced historical names (future probes)

For historical proper names, use a **separate external name dataset** rather
than writing hundreds of dictionary-known names into the persistent human
lexicon. Wikidata's Query Service offers export to CSV. Wikidata structured
data is CC0. You can create a bounded source list appropriate to the book,
for example a list of philosophers with birth dates before 600 CE, then save
the *unmodified CSV* as a source snapshot.

Example Wikidata SPARQL query to adapt and inspect before exporting:

```sparql
SELECT DISTINCT ?item ?itemLabel WHERE {
  ?item wdt:P106 wd:Q4964182 .
  ?item wdt:P569 ?birth .
  FILTER(?birth < "0600-01-01T00:00:00Z"^^xsd:dateTime)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT 5000
```

This example is deliberately **not an exhaustive historical-name resource**:
it will miss historians, editors, ancient philosophers without recorded birth
dates, translators, Romanized alternative spellings and multiword names. Review
the source export and expand its scope as needed.

Normalize's offline importer converts the saved CSV's `itemLabel` column
into a sorted list of **single-token, capitalized** names:

```bash
python prepare_historical_names.py \
  --input sources/wikidata-historical-figures.csv \
  --out dictionaries/historical-names-v1.txt
```

Record the SPARQL query and export date alongside the CSV. The importer prints
both the source CSV SHA-256 and the derived list SHA-256. It skips multiword
labels, lowercase words and invalid names and refuses to overwrite outputs.
The `.txt` is ordinary UTF-8, one name per line (comments starting `#`
and blank lines are permitted).

To include the file in recognition, add this argument to the same probe
invocation:

```bash
  --historical-names dictionaries/historical-names-v1.txt
```

The exact name-list SHA-256 appears under
`inputs.historical_names_sha256`. Historical names only suppress a lexical
unknown finding if the observed token starts with an uppercase character and
case-insensitively matches the listed name. They **do not** change raw OCR,
Codex proposals, verification decisions or the persistent lexicon.
For the optional segmentation sidecar, pass the same
`--historical-names` path and the same `--locales` list.

## Avoid changing an in-flight book

Do **not** regenerate Probe 2 or alter frozen join reports and review progress
for the current book. Those artifacts are correctly bound to the original
dictionary snapshot. Apply the new vocabulary set only when running a *new*
book's probe, or write a **separate, read-only coverage comparison** against
a completed report. An expanded recognizer does not retroactively alter
existing decisions.
