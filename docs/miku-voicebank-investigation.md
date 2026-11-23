# Miku V4 bank investigation

Observed 2026-11-17 (local investigation; source archive timestamps are from 2016).
User-provided input: `vocaloid-vbanks/MikuJP_EN/`.

## Confirmed contents

The supplied EXEs are installer wrappers. Their `setup.bin` files are FreeArc
archives containing the actual `.ddb` audio databases and `.ddi` indexes.
The installers were not executed. Native UnArc extracted both archives into
`out/miku-v4/`; all source inputs remain unchanged.

| Bank identified from archive/index | Stationary samples | Articulation samples |
| --- | ---: | ---: |
| MIKU V4 English | 48 | 4,651 |
| MIKU V4X Original EVEC | 144 | 5,701 |
| MIKU V4X Soft EVEC | 144 | 4,832 |
| MIKU V4X Sweet | 48 | 1,552 |
| MIKU V4X Dark | 48 | 1,556 |
| MIKU V4X Solid EVEC | 120 | 4,457 |

Every index parsed with `ddb-tools`. Counts are indexed recordings, not unique
IPA phonemes. EVEC variants have additional internal phoneme/style distinctions.
Japanese audio payloads were unpacked; only English was exported to WAV and
audited end to end during this investigation.

English contains 4,702 raw SND chunks: 44,100 Hz, mono, signed 16-bit PCM.
There are 48 stationary samples for 24 XSAMPA-labelled units, 4,649 two-unit
articulations, two three-unit articulations, and three growl samples. The 4,699
non-growl samples have extracted LAB timing annotations. Timings were checked
against WAV lengths, allowing the extractor's tiny SND-header endpoint offset
and clamping it in the audited inventory. All 4,702 exported WAV payloads were
verified byte-for-byte against PCM chunks in the source DDB.

Stationary recordings include vowels/nasals; consonants also appear in recorded
transitions. This is much richer material than anonymous isolated vowel files.
The DDI supplies labels, approximate recorded pitch and alignment information,
so manual annotation does not have to start from scratch.

## Local artifacts

All bank data, raw indexes and audio remain ignored local files:

- `out/miku-v4/banks.json`: inventory for all six bank indexes.
- `out/miku-v4/english-index.json`: compact English unit index.
- `out/miku-v4/english-detail.json`: detailed index, including timing metadata.
- `out/miku-v4/english-samples/`: labelled native PCM WAVs and LABs.
- `out/miku-v4/audit/inventory.json`: checked sample paths and clipped timings.
- `out/miku-v4/audit/summary.json`: counts, format checks and audition manifest.
- `out/miku-v4/audit/recovered-vowels.wav`: source-vowel audition, separately
  normalized and faded for listening, with short gaps. Order: i:, e, {, O:, u:.
  It is not a synthesized Seraphim performance.

The source-bank directory was added to `.gitignore`. No bank data is bundled
with the Python package, and the current formant renderer was not changed.

## Reproduction and tool provenance

Sources were cloned under the ignored `src/` directory:

- `xredor/unarc`, commit `adc333d6cdd76d72da254cc80d766fbbcc683c95`.
- `yuukawahiroshi/ddb-tools`, commit `2e78b11f0f1fd63535f1c67e8aa5096bf4ac94a7`.
- `shmishtopher/VAU`, commit `e1286ead0bac01487bb97d2cb23a489d72c29195`.
  Built and inspected, but not used for audio export: its CLI defaults to a
  manually specified rate/bit depth, while ddb-tools reads this bank's headers
  and retains the phoneme/timing index.
- `ain-soph/ddb-extraction`, commit `752826a8fd17a9aec51c9678ab840ef57d971313`: inspected as the older precursor. The modern parser
  can be used directly without installing PyYAML; YAML serialization is optional.

Build logs are `out/unarc-build.log` and `out/vau-build.log`. Extraction logs are
`out/miku-{english,japanese}-extract.log` and `out/miku-wav-extract.log`.
UnArc required modern compiler overrides, without modifying its source:

```sh
make -C src/unarc -j4 OPT_FLAGS='-fomit-frame-pointer -fstrict-aliasing' \
  LIBDIR=/usr/lib CXX='g++ -std=gnu++98 -fpermissive'
src/unarc/unarc l vocaloid-vbanks/MikuJP_EN/MikuV4_english/setup.bin
src/unarc/unarc x -dpout/miku-v4/english vocaloid-vbanks/MikuJP_EN/MikuV4_english/setup.bin
src/unarc/unarc x -dpout/miku-v4/japanese vocaloid-vbanks/MikuJP_EN/MikuV4x/setup.bin
.venv/bin/python src/ddb-tools/extract_wav.py \
  --src_path out/miku-v4/english/MikuV4_ENG/BMLTD846MLYP2MEK/MIKU_V4_English.ddi \
  --dst_path out/miku-v4/english-samples --gen_lab
.venv/bin/python tools/audit_voicebank.py out/miku-v4/english-samples out/miku-v4/audit
```

The audit tool validates WAV formats/alignment and regenerates the audition;
byte-for-byte DDB verification was a separate read-only check, recorded above.

## Integration status (2026-11-17)

The optional `seraphim.samplebank` backend now loads versioned manifests from
`vocaloid-vbanks/converted/` and uses WORLD spectral resynthesis for planned pitch
and duration. All six profiles have been converted locally. Two-phoneme units
are selected when available, and supported units otherwise come from stationary
recordings or aligned regions of transition recordings. Unsupported sounds use
formant spectra; nearest-phoneme mappings can be disabled and are reported.

The web UI has seven independent bank selectors plus post-render coverage.
CLI assignments use `--sample-bank`. Bank choices also apply to hums, whisper and
growl layers, brightness octaves, and prayer synthesis, while the shared effects
and spatial mixer remain active. Exact physical-source simulation is not
preserved; source fry and some articulation controls remain approximations.

The local converter is `tools/import_vocaloid_bank.py`; runtime needs no DDI
parser. EVEC internal append suffixes and triphones are excluded from the first
manifest format. Zero recorded pitch is retained for unpitched consonant units;
it must not be treated as a corrupt voiced sample.

`tools/demo_samplebanks.py` generates `out/miku-integration/formant.wav`,
`miku-ensemble.wav`, their dry stems and resolved plans. This is an experimental
sample-backed renderer, not Yamaha's original algorithm. Native recordings are
kept local and untracked.
