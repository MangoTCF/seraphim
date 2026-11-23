# seraphim

A voice synthesizer, grammar engine and translator for **Seraphim**,
Babelingua's entry to Agma Schwa's Cursed Conlang Circus
([wiki](https://cursedconlangcircus.miraheze.org/wiki/Seraphim),
[video](https://www.youtube.com/watch?v=EOctKnETWi4)).

Seraphim needs seven voices at seven points in space. Four mouths (top, 1, 2,
end) say the four morphemes of each word at the same time. Three smaller
mouths sing prayers, and the prayer language marks tense. Every phoneme is a
whole Hebrew string, and only its gematria counts. Vowels also have a
brightness. Words are built by walking a syntax tree. Their order is free, but
it says how active each participant is. After a word has been said, the verb
travels back in time to the complementizer.

Install the release wheel with Python 3.10 or newer, then use `seraphim` for
the CLI and `seraphim-web` for the browser workbench.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install seraphim-0.1.0-py3-none-any.whl
.venv/bin/seraphim --help
.venv/bin/seraphim-web
```

From a source checkout, run `uv build` to produce a wheel and source archive in
`dist/`. For an editable install with English translation and compiled filters:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[english,fast]'
.venv/bin/python -m spacy download en_core_web_sm
./seraphim.sh <command>
```

| Command | What it does |
|---|---|
| `translate "English…" -o x.sera --audio x.wav --html x.html` | English → gloss → tree → words → movement → tense → score. It prints every stage, then reads the result back into English as a check. |
| `gloss "NPFV NEG.ever 1S comprehend-OBJ ABS-Aghma_Shwa CON-allure" --tense farpast` | The same pipeline, starting from a gloss written the way the video writes them |
| `read x.sera` | Seraphim → gloss → English, with tree order and movement undone |
| `synth x.sera -o x.wav [--stems dir/]` | Render the seven voices to binaural audio |
| `write x.sera [--html x.html]` | Seraphim orthography |
| `check x.sera` | Gematria, phonemes, syllables, rule breaks |
| `inspect x.sera --room hall` | Resolved voice/dialect/room settings and word timings as JSON; no audio render |
| `spell 26 45 613` · `gematria אלוקים החם` | Phoneme helpers |
| `lexicon list [--grep x]` · `lexicon add GLOSS TOKENS… [--pos V]` · `lexicon path` | The morpheme lexicon |
| `say --top "שהב ליה☀ גשד" --end "/600/ /45/☢"` | One hand-made word |

Use headphones for the audio. The voices are placed binaurally around the listener.

## Local web workbench

```sh
./seraphim.sh web
# Or: .venv/bin/python -m seraphim.web
# Open http://127.0.0.1:8765
# Alternative after installing this package: seraphim-web
# Optional: --port 8766 --output out/my-session
```

Open [the workbench documentation](http://127.0.0.1:8765/docs) from the running
server. For the authoring workflow, choose a character, enter English or gloss,
and click **Prepare score**. Review missing words, then edit and arrange the
resulting score before rendering or downloading it. The **Dictionary** editor
manages pronunciation overrides. The browser remembers drafts, dictionary
entries, and settings in local storage.

The browser UI accepts English, glosses and `.sera` scores. Choose an example or
open a local file, set dialect/voice/tempo/room controls, then **Render voices**.
English input needs the optional spaCy dependency and model described above.
Rendering runs in a separate process and can be cancelled. Score metadata is
preserved unless a control explicitly overrides it; Reset clears overrides.

Expandable controls expose individual mouth/choir voice character, all dialect
style and damage knobs, choir transposition and gain, hum and glitter, global
emotion intensities, reversed 4D speech, binaural/stereo placement, reverb send,
decay/darkness/predelay, mastering and worker count. Blank numeric controls
inherit score/dialect settings. Neutral clears inherited tonal markers before
applying explicit global intensities. Damage controls operate where the dialect
uses damaged voices. Word-specific tones and stammering remain editable in the
score itself.

Score generation controls expose title, fronted morphemes, shuffle seed, grammar
movement and strict English translation; the divine-name permission also applies
to raw scores. Render settings are visible beside the result. Downloads support
PCM16 or float32 and optional independent stem normalization; browser solo tracks
keep original gain. The render bundle contains the mix, all dry stems, portable
score, requested settings and resolved timing plan, plus an optional self-contained
HTML preview. These exports preserve the exact render configuration separately
from the source score.

A six-winged angel places the four speech mouths and three prayer voices on a
regular heptagon. Playback animates each mouth from its rendered stem amplitude.
Select a word to seek and see its four simultaneous morphemes; select a mouth
to inspect and solo it (select it again for the full ensemble). Prayer labels follow the actual tense-cue schedule; the inspector also shows
the chant language. They are not a syllable-level prayer transcript. The
heptagon is schematic; the synth's acoustic positions remain independent.
Dry solo tracks preserve their gain and can sound quieter than the mastered mix.

Save the mix or selected stem as WAV, or save the portable generated score.
The app binds to loopback only, uses no external services or frontend build tools,
and does not save coined vocabulary to your user lexicon. Render files and logs
are retained in `out/webui/`; files opened in the editor stay local. Settings apply
to the next render, rather than changing a playing recording. Both dark and light
themes and narrow-screen layouts are supported.

Development checks:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_web.py' -v
# With the server running; optional Chromium + Node.js, no npm dependencies:
node tools/check_web.cjs http://127.0.0.1:8765
```

### Word editing, auditions and grammar

Select a preview word, then expand **Edit this word**. Edit the four mouth lines,
change vowel brightness, set exact tense stacks (`gnomic+nonpast`), tone
intensities and stammering. **Apply & render score** validates the edit and
renders the full portable score. **Audition word** renders only that word;
**Undo edit** restores the previous score and rerenders it. Opening the editor
pauses playback. Editing a composition with pending source/control changes
requires rendering those changes first, to avoid editing an outdated preview.

An audition replans the word in isolation, so its prosody/choir entry can differ
from connected speech. Its score download and grammar panel retain the full
composition. A local tense edit preserves the following word's inherited tense;
use the raw score editor if the change should propagate to later words.

**Grammar · scope & tense** shows reconstructed terminal order, movement-related
chain diagnostics and exact tense labels. Far past and gnomic remain distinct in
written/read-back data even though both use Aramaic prayers. See
[scope and tense conventions](docs/language-semantics.md) for implemented semantics
and remaining limits, including approximate quantifier scope and English tense
realization. These are implementation conventions, not new claims about the
original language's specification.

The synth now uses adjacent vowels to shape consonant formant targets, without
crossing pauses or changing segment durations. The four mouths also have stable
articulatory identities (spectral tilt, jitter, consonant strength and amount of
coarticulation), in addition to pitch and tract differences. Generate dry A/B
samples with `.venv/bin/python tools/articulation_demo.py`; the reference disables
the new context/identity settings, and does not emulate an entire archived build.

### Smooth transitions and audible prayer tense

Formant, bandwidth, voicing and pitch tracks now use smooth ramps with no
overshoot. Stop closure, release and aspiration share a continuous pitch glide
rather than restarting it at each subpart. Phoneme durations and real pauses are
preserved. **Speech transitions → Transition smoothness** (or `--transitions`)
controls this: 1 uses smooth ramps; 0 uses linear ramps for comparison.

The prayer voices now sing short tense signatures at word entries:

| Tense | Prayer language | Sung contour |
| --- | --- | --- |
| farpast | Aramaic | Descending |
| gnomic | Aramaic | Steady |
| nearpast | Greek | Rising |
| nonpast | Latin | Arching |

These contours are an optional implementation extension, relative to the
current dialect's musical scale and choir transposition. **Audible tense
signatures** enables them by default; `--no-prayer-time` restores legacy chant.
The new schedule aligns prayer languages and cue directions with the final
playback timeline, including backwards choirs. Stacks of up to three tenses
split across the voices; larger stacks use successive short slots so every
context is heard. Legacy `aramaic` labels receive no invented farpast/gnomic cue.

Try `examples/prayer-time.sera` in the web UI. For isolated listening comparisons:

```sh
.venv/bin/python tools/prayer_time_demo.py
# out/prayer-time/prayer-tense-comparison.wav: farpast, gnomic, nearpast, nonpast
# out/prayer-time/transitions-linear.wav and transitions-smooth.wav
```

### Syllable blending, independently per mouth

**Speech transitions → Syllable blend** controls connected articulation independently
of the existing phoneme-transition smoothness control. The global default is
**0.5**. Every speech mouth and prayer voice has its own slider and **Inherit**
toggle: checked inherits the global value, unchecked uses that mouth's explicit
value. **0 turns blending off**; 1 is strongest. Clearing a numeric override
restores inheritance. Reset restores the global default and clears all overrides.
Settings apply on the next render and are retained in exported settings/plans.

With blending enabled, compatible consecutive words share one continuous source
render instead of restarting the vocoder/vocal-fold phase and fading to silence
at every word. Sustained vowels, sonorants and fricatives can carry through the
short scheduling gap; the same applies to closed-mouth hums. Internal word-edge
fades are removed on these connections. Existing word/phoneme timestamps and
brightness tags are preserved. Sentence breaks, intentional rests, stop/glottal
closures and displaced speech remain distinct. Voice/tone changes and long
runs can require separate source chunks.

The amount controls short join-local timbre/pitch/gain ramps, with 0 retaining
the independent-word renderer. It does not average whole vowels, automatically
flatten their energy, or morph between unrelated recordings. Those earlier
approaches blurred articulation without fixing the word-gap problem and have
been removed. Recorded diphone selection stays unchanged.

```sh
# Global amount; zero restores the previous discrete articulation:
./seraphim.sh synth examples/kadosh.sera --sample-bank miku-en --syllable-blend 0.7 --play
# A dry top mouth, more blended main 1, and separate prayer settings:
./seraphim.sh synth examples/kadosh.sera --sample-bank miku-en \
  --syllable-blend 0.5 --mouth-blend 'top=0,1=0.9,choir=0.6,praise-1=1' --play
.venv/bin/python tools/demo_legato.py
# out/legato/off.wav, moderate.wav, strong.wav and off-then-strong.wav
```

`--mouth-blend` supports top, 1, 2, end, praise-1/2/3, choir and all. Specific
mouths override groups; explicit zero is an off setting, not inheritance. The
comparison tool uses one common gain, so loudness differences stay meaningful.

### Local recorded voicebanks (experimental)

Each of the four speech mouths and three prayer voices can use a separately
selected local bank. In **Recorded voicebanks**, choose a singer for each mouth;
leave **Formant synth** selected for the original engine. The six converted Miku
V4 profiles in this workspace are English and Japanese Original, Soft, Sweet,
Dark and Solid. The same bank can be reused by several mouths; their score pitch
and timing remain independent.

The optional sample backend uses WORLD to analyze recorded spectral envelopes
and aperiodicity, retime aligned phonemes, apply the planned pitch curve and
synthesize a continuous voice. Two-phoneme recordings are preferred when a
matching transition exists. Analyses are cached under each bank's `world-cache/`
and reused across renders; the first render can be slower. Parallel sample jobs
use fresh worker interpreters rather than forking an initialized native vocoder.

```sh
# This workspace uses uv; ordinary pip installation of .[samples] also works.
uv pip install --python .venv/bin/python -e '.[samples]'
./seraphim.sh synth examples/kadosh.sera \
  --sample-bank 'top=miku-en,1=miku-jp-original,choir=miku-jp-soft' --play
# One bank everywhere, except the top mouth stays formant-based:
./seraphim.sh synth examples/kadosh.sera --sample-bank 'miku-en,top=formant' --play
# Require exact bank phonemes; approximate sounds use formant fallback instead:
./seraphim.sh synth examples/kadosh.sera --sample-bank miku-en --strict-bank-phones --play
.venv/bin/python tools/demo_samplebanks.py
```

Assignments accept `all`, `top`, `1`, `2`, `end`, `choir`, and individual
`praise-1`, `praise-2`, `praise-3`. Specific assignments override groups; explicit
`formant` disables the bank on that channel. The web UI can select all seven
channels independently and reports sample use, pronunciation approximations and
formant fallbacks after rendering. Exported render plans retain assignments and
coverage. CLI progress also reports approximated/fallback phones.

Banks do not magically acquire new sounds: English /r/ for a trill and Japanese
/ɯ/ for /u/ are reported approximations. Pharyngeals, uvulars and other uncovered
sounds use formant spectra. **Allow nearest bank phonemes** controls approximate
mapping independently of fallback. Fallback regions pass through WORLD along
with the sampled regions, to keep excitation continuous; they will not be
bit-identical to the original formant waveform.

Brightness, displaced speech, whispers/growl layers, choir tense signatures,
backmasking, spatial placement, reverb, stems and mastering remain in the shared
pipeline. Pitch/duration are controlled directly; character, breath, throat and
jaw changes use approximate spectral/noise adjustments on recorded voices.
Physical source parameters such as vocal fry are not faithfully reproduced by
this backend. This is a new experimental renderer using the recordings, not a
reimplementation of Yamaha's synthesis engine or a promise of matching quality.

No recordings ship with Seraphim. Put converted manifests under
`vocaloid-vbanks/converted/<bank-id>/bank.json`, or
`~/.local/share/seraphim/voicebanks/<bank-id>/bank.json`. Set `SERAPHIM_BANK_DIR`
to one or more search roots (separated by the OS path separator) to override
those locations. The `samples` extra includes a setuptools compatibility pin
because current PyWORLD imports `pkg_resources`.

For an already unpacked DDI/DDB pair, the importer uses the inspected
[ddb-tools](https://github.com/yuukawahiroshi/ddb-tools) checkout for DDI parsing:

```sh
.venv/bin/python tools/import_vocaloid_bank.py /path/to/Singer.ddi \
  --id my-bank --name 'My singer' --language english --parser src/ddb-tools
```

It writes PCM16 WAVs, phoneme/pitch/region metadata and a versioned manifest,
without requiring the extraction tools at runtime. Japanese is also supported;
internal EVEC append suffixes and triphones are currently excluded. See
[the Miku investigation](docs/miku-voicebank-investigation.md) for this workspace's
source inventory and archive extraction steps. Bank data and caches stay ignored.

Tests synthesize their own small fixture bank and do not require Miku recordings.
Optional real-bank browser QA uses `SERAPHIM_TEST_BANKS=1 node tools/check_web.cjs`
with the local server running.

## Grammar

All of this is reconstructed from the video (2:31–9:45), which shows the trees and word tables.

**Glossing.** A sentence becomes the video's style of gloss:
* Articles, agreement and tense are dropped; aspect is kept: `PERF`, `NPFV` (perfective-ish past vs. imperfective/ongoing).
* Sentence adverbs become a clause: *"Obviously, X"* → `3S be obvious COMP X`.
* Complementizers are made explicit (`COMP`).
* Case prefixes go before the word and transitivizer suffixes after the verb:
  * Main clauses are nominative–accusative with an unmarked accusative.
  * Embedded clauses are ergative–absolutive: patients and intransitive subjects take `ABSV-`.
  * *X of Y* and possessives become construct chains, `CON-X ABS-Y`.
  * Prepositions map to cases (`LOC-` `ABL-` `ALL-` `TRAL-` `INS-` `AVR-`), or to transitivizers (`-BEN` `-MAL` `-DAT`).
  * Gerunds and infinitives are nominalized: *"had him starting out by trying…"* → `ABS-3S CON-start.out-INS INS-try…`.

**Microsyntax.** The gloss is a right-branching tree whose left daughters are the terminals. Each word takes the next two terminals:
* **top** says the pro-form of the current phrase (`START` for the first word).
* **1** and **2** say the terminals.
* **end** says a pro-phrase (`PRO:T`, `PRO:V`, `PRO:N`, `PRO:K`, `PRO:COMP`, …) that stands for the rest of the tree.

The next word's top mouth must agree with the previous word's end. Given the gloss above, this reproduces the video's word table exactly.

**4D V-to-T-to-C movement.** After spell-out, the aspect marker and the verb move to the null C slot of the `START` word, and the subject's head moves to spec-TP with `.NOM`; any remaining modifiers stay in place. Those mouths stay closed (`~` in scores). Traces stay behind.

**Tense** is sung by the praise voices:
* The first word is marked (`i:`) with the sentence tense, and later words inherit it (`u:`).
* Negative words are always marked. A negation that reaches back to the far past is re-marked non-past ("never, from the far past onward, have I…").
* An embedded clause with a different tense marks its `COMP`.
* You can force a mark in a gloss with `word^gnomic`.

**Macrosyntax.** Runs of words with the same phrase name stay together and in order. Otherwise words can go anywhere, and earlier words are claimed to be *more active*:
* `--front cheese` speaks the cheese word first, and `read` then reports *"The cheese caused the man to eat it"*, which is the video's example.
* `--shuffle N` picks a random legal order. Shuffled scores still read back correctly, because `read` re-chains words through their pro-phrases.

**Lexicon.**
* Morphemes recovered from the demo are built in: START, PRO:*, NPFV, NEG, 1S, comprehend, -OBJ, ABS-, CON-, Aghma_Shwa, allure, plus approximate ones from sentences 2–3.
* Grammatical morphemes the demo never shows were coined once and frozen in `seraphim/data/lexicon.tsv`.
* Any other word is coined on first use and saved to `~/.local/share/seraphim/lexicon.tsv`. Coining works like a clever angel: each phoneme is spelled with a real word from the Shema, Kedusha, Aleinu, Psalm 150, the priestly blessing or Adon Olam whose gematria gives it, and names of God are filtered out. Updates are locked and atomically replaced; invalid entries and phonemic collisions are rejected.
* Decoding matches phoneme values, never spelling, because only gematria is phonemic.
* Generated scores embed the vocabulary they use, including grammatical entries, with `@format: 1`, `@lexicon:` and a SHA-256 `@lexicon_hash:`. They decode and trigger semantic sound effects without the author's user lexicon, even with `--no-save`. Embedded definitions take precedence over local vocabulary. Older scores still use the built-in and user lexicons; `read --strict` reports missing words. The hash detects accidental changes, not authenticity.

**Orthography.**
* Phonemes are written right to left, and syllables left to right.
* The longest morpheme of a word is the core. Every letter of the other mouths becomes a diacritic: above the core if its mouth outscopes the core's, below if not. The result is Hebrew zalgo.
* Brightness is shown by colour: bright orange, extra bright yellow, ionized cyan.
* The diacritic shapes approximate the video's table with Unicode combining marks.

## Sound

| Spec | Implementation |
|---|---|
| Phoneme = Hebrew string; gematria is phonemic | Mispar Hechrachi with final letters ך ם ן ף ץ = 500–900, as in the video's table; this is what makes the demo's החם = 5+8+600 = 613 work |
| Sum not a phoneme → first (rightmost) letter counts | שהב (307) → ש /300/, גשד (307) → ג /3/ |
| 39 consonants, 8 vowels (1, 3, 15, 16, 26, 45, 86, 314) | /1/ and /3/ are both; a brightness mark makes them vowels |
| Names of God forbidden | rejected unless `--heresy`; substitutes like אלוקים and הויה are fine |
| Pronunciation | By default, unpointed strings are read the way Hebrew is, with the filler vowels and vowel letters varying from string to string (deterministically, so a spelling always sounds the same): ו/י after a consonant are the vowels u/o and i, final א/ה is a, and the vowel between two consonants is a next to gutturals, otherwise e then ə (אלוקים → [ʔaluqim], אהבה → [ʔahava]). `@reading: demo` gives the demo's exact schwa chains ([ʔələwəqəjəm]). Soft בגדכפת unless dagesh. Pointed strings (with niqqud) are read as real Hebrew. |
| Free variation in spelling | Only gematria is phonemic, so generated scores keep each spelling once and respell repeats with other prayer words of the same value. Meaning and decoding are unchanged, but not every word says אלוקים. The word bank is drawn from the Shema, Kedusha, Aleinu, Psalms 23, 91, 121 and 150, the priestly blessing, Adon Olam and the Song of Songs (8:6: love is strong as death). |
| Prosody | Speech is connected: no pauses between tokens, and words join with soft edges. Each mouth follows one pitch contour per sentence and glides from the end of one word into the next, with accents, micro-prosody (high vowels higher; pitch kicks after voiceless consonants), rubato and final lengthening. |
| Null and closed mouths | They hum [m] softly on their own pitch, which is what a closed mouth vocalizing is, so the four mouths stay dense. `--hum 0` restores the video's silence. Mouth lines are stretched to the word's length through their vowels and sonorants, not with pauses. |
| Bright / extra bright / ionized | Bright adds airy shimmer and a static halo. Extra bright adds an overtone voice an octave up and pitchless noise glitter (`--glitter 0` turns it off). Ionized is a glow: the vowel itself turned up in the highs with an intensity that drifts at random, fading in and out over ~150 ms, with a sparse crackle on top. Everything is pitchless, unswept and unswitched on purpose: sine sparkles whistled, swept modulation went "weuweu", and a switched broadband sizzle hissed like a steam valve. |
| Voice: masculine ↔ androgynous ↔ feminine | `-v/--voice` from -1 to +1 on `synth`, `say`, `translate`, `gloss`, or `@voice:` in a score. It moves pitch (the mouths span 98–147 Hz at -1, 139–208 at 0, 196–294 at +1, keeping their intervals), vocal-tract length (formants ×0.93–1.22), and voice quality (softer, breathier glottal pulse toward feminine). The choir is transposed by up to half an octave either way. Per-mouth values give a mixed choir: `-v "top=1,1=0.6,2=-0.2,end=-0.8,choir=0.8"`. The default is 0, androgynous, as befits angels. |
| Four simultaneous mouths | Klatt-style formant synthesis, each mouth with its own pitch and tract, placed clockwise around the listener |
| Praise voices: Aramaic (far past, gnomic), Koine Greek (near past), Ecclesiastical Latin (non-past) | Three independent voices, each at its own place, pace and register in D dorian, on four chant formulas. The texts are Daniel 2:20–22, 3:33, 4:34 and 7:9–10 in Aramaic; Isaiah 6:3, the Trisagion, the Kyrie, the Pater and Revelation 4:8 in Koine; the Sanctus, Gloria, Agnus Dei, Pater noster and Te Deum in Latin. Prayer order and starting points change with `--seed`. They switch language word by word, and stacked tenses split the voices. |
| 4D-moved morphemes | Heard in front of the closed mouth, with the reverb arriving *before* the sound (the echo comes from the future); `--reverse-4d` plays them backwards too |

## Dialects

`--dialect=NAME` (`-d`) on `synth`, `say`, `translate`, `gloss`, `check` and `read`, or `@dialect:` in a score; the command line wins.

| Dialect | |
|---|---|
| `seraphic` (default; `angelic`, `heavenly`) | Names of God are forbidden as phonemes. The praise voices sing the prayers in D dorian. |
| `cupid` (`eros`) | A light masculine voice with gently swelling vowels and a close whispered double. A teasing lilt gives way to a cool, falling cadence at the end of each sentence. Uses seraphic grammar and forward Dorian praise. Try `examples/cupid.sera`. |
| `succubus` (`lilith`, `lilit`, `seductive`) | Hellish grammar (heresy on) in a seductive voice: feminine by default (`-v` overrides), breathy and moaning, with a whispered double breathed right at your ears and only a trace of the fall (light fry, a low growl underneath). The choir sings backwards in Phrygian. |
| `nephilim` (`nephil`, `hybrid`, `grigori`) | Half-angel, half-fallen (Genesis 6), mouth by mouth. Two diagonal mouths are seraphic (condescending, clean) and the other two fallen: succubus if that mouth's voice is feminine, demonic otherwise, each with its full package of damage, moaning, whispering and grabbing. The halves trade sides at sentence starts and now and then mid-sentence, as often as `--swap` says (default 0.5; 0 keeps them fixed). Voices default to a mix (top −0.4, 1 +0.8, 2 +0.6, end −0.8), so both kinds of fallen appear; `-v feminine` makes every fallen mouth a succubus. The choir is torn: two praise voices sing forward while the middle one blasphemes backwards in Locrian against them. Heresy is on. |
| `demonic` (`fallen`, `infernal`, `satanic`, `hellish`, `hell`) | Heresy is on: names of God are allowed, and generated scores happily respell /1/ as אלוהים or /26/ as יהוה. The fall left the voices disfigured, and each mouth is damaged differently. The praise voices blaspheme: backmasked, an octave down, growling, in Locrian, the mode built on the tritone. A demonic score can't be performed in the seraphic dialect, because a seraph won't say those names. |

The demonic damage is physically modelled, and every part is a knob: `--growl --fry --roar --whistle --throat --disfigure --pitch` on the command line, or `@growl: 0.9` etc. in a score. The damage is gender-aware: toward `-v feminine`, the pitch drop and throat lengthening fade out and the growl layer sits lower, so a fallen woman stays a woman (median pitch 230 Hz, against 98 Hz before this fix).

| Knob | Default | What it does |
|---|---|---|
| `growl` | 0.8 | A second, rougher throat an octave down, jittered so it never locks to the voice, plus a hint of uneven folds. (Strong period doubling was tried first: it halved the heard pitch and pulsed like a frog.) |
| `fry` | 0.4 | Creaky, irregular low pulses, kept mild and worst where the voice is weak |
| `roar` | 0.55 | False-fold turbulence riding on each pulse, random cycle-to-cycle roughness, and asymmetric distortion |
| `whistle` | 0.45 | Air whistling through wounds. Sibilants ring at each mouth's own wound frequency (3.2–5.2 kHz), and gliding whistles ride on the voice. |
| `throat` | 0.6 | A constricted pharynx: F1 up, F2 down, wider resonances |
| `pitch` | −4 | Overall shift in semitones |
| `disfigure` | 0.7 | How unevenly the damage is spread. Each mouth gets each knob scaled by 1 ± this, fixed per `--seed`. |

Three style knobs work in every dialect (the succubus turns them up by default):

| Knob | succubus | What it does |
|---|---|---|
| `breath` | 0.65 | Breathiness: more air through the folds, a softer pulse, darker highs |
| `moan` | 0.6 | Moaning: vowels lengthen into swells whose pitch slides up and back down by a few semitones while their loudness rises and falls; stops soften; lines end on a sigh; hums swell too |
| `whisper` | 0.45 | A whispered double of every mouth, dry and close, right at your ears |
| `grab` | 0.7 | She pulls you in. Each mouth drifts from its place to right at your ear over every sentence and lurches closer on hungry and tender words (bite, eat, swallow, tear… love, sweet, one, want). Up close the voice gets the bass of a mouth at your ear and leaves the hall. Moans scoop up from below and swell toward their end, and every sentence begins with a breath in. |
| `hunger` | 0.5 | The cannibal half. Teeth snap after hungry words, eating words end in a wet slurp, tender words get a kiss, and lines with hungry words surge with growl and roar. Demonic has a little of it too (0.3), without the kisses. |

`--tempo 1.4` speeds a render up (moaning is slow).

```sh
./seraphim.sh translate -d demonic --play < examples/demonic.txt
./seraphim.sh synth examples/demonic.sera --growl 1 --whistle 0 --pitch -7 --play
./seraphim.sh synth examples/heaven.sera -d fallen --play      # an angel's text, fallen
```

## Tonal markers

How a word is said, without changing what it means: pain, fear and anger change a seraph's voice the way they change a real one. In a score they go on word lines, `word nonpast tone=pain:0.9,scream:0.5`, plus `stammer` to break off and restart the first syllable. `@tone:` sets them for a whole score and `--tone pain:0.8` for a render. `translate` infers them from the English: pain words and cries ("Oh!") for pain, "!" for screams and commands, fear words and "…" for trembling, a trailing "…" for a whimper, "I… I" for a stammer.

| Tone | What it does |
|---|---|
| `pain` | Pitch forced up (up to ~6 st), each vowel wailing downward, sudden upward voice cracks, a pressed and rough voice with heavy jitter, catching breath, sobbing breaths before words, louder |
| `scream` | Up to an octave higher in rising–falling arcs, the jaw wide open (first formant up), harsh and loud, vowels held |
| `anger` | Louder, faster consonants, pressed voice, a little higher ("Begone!") |
| `fear` | An irregular tremor in pitch and loudness, breathier, higher, hurried |
| `whimper` | Softer, breathy and thin, pitch sinking |
| `condescend` (`smug`, `haughty`, `patronizing`) | The voice of a higher being: unhurried (vowels drawn out, ~15% slower), exaggerated sing-song pitch (swings around the voice's centre stretched, ~1.6× wider at the default 0.6, with a lilt on long vowels), sentences closing on a falling, final note, a relaxed slightly breathy voice with a dismissive creak, a touch quieter, and a weary sigh after each sentence |

**The seraphic dialect is condescending by default** (`condescend:0.6`): every word without its own markers gets it. A score's `@tone:` replaces the default, a word's own markers replace both (a screaming angel has stopped being condescending), `--tone` adds on top, and `--tone neutral` turns it all off.

While a mouth is in pain or screaming, the praise choir falters with it: the chant sags, cracks and drops out (mirrored correctly for backmasked choirs). Breaking words ("break", "snap", "crack", "tear") get a crack inside the wing, and wing words a rustle of feathers, both at the ears.

Measured on `examples/pain.sera` against the same score without markers: "Oh!" goes from 185 to 399 Hz with 4.7× the high-frequency harshness, "Stop hurting me!" from 160 to 286 Hz and is the loudest line, and the whimpered last line is the softest.

## Reverb

`--room NAME` picks the space and `--reverb N` sets how wet it is (1 = the room's normal amount, 0 = dry, 2 = drenched). `--reverb-time S` (RT60), `--reverb-tone` (0 bright .. 1 dark) and `--predelay MS` reshape any room. All of them also work in a score: `@room: clip`, `@reverb: 0.8`, `@reverb_time: 2.5`.

| Room | RT60 | Character |
|---|---|---|
| `cathedral` (default) | 3.3 s | Long, with a random scatter of early reflections; the highs die faster than the lows |
| `clip` | 1.75 s | Matched to `source-materials/video_2026-10-22_02-40-39.mp4`. Measured there: RT60 1.6–2.0 s over nine phrase endings, early reflections at ~16 and ~23 ms, no echoes, a near-mono voice in a fully wide tail, the tail darker than the voice and ~9 dB under it 80 ms after each phrase. Renders through this room measure RT60 1.77 s and −9.1 dB, fully wide. |
| `hall` | 2.2 s | A concert hall |
| `plate` | 1.4 s | Dense and bright, no early reflections |
| `room` | 0.6 s | A small room |
| `dry` | – | No reverb |

```sh
./seraphim.sh synth examples/succubus.sera --room clip --play
./seraphim.sh synth examples/demonic.sera --room hall --reverb 1.5 --reverb-time 4 --play
```

## Speed

A render runs well faster than real time on a multi-core machine: 105 s of succubus in about 11 s, against 78 s before the optimisation pass. Where the time went, and what fixed it:

* The formant filters were evaluated with one scipy call per 2.5 ms frame per resonator, 2.8 million calls per render. They're now a compiled numba loop, 28× faster. numba is optional: without it, the old path runs.
* Every mouth line, hum and praise phrase is an independent job on a process pool (`-j N`, 0 = one per core, 1 = off). Each job seeds its own random generator from (seed, word, mouth), so parallel and sequential renders are bit-identical.
* The choir is split into phrases at its rests, so three long voices don't hold up 16 cores.
* Spatialization and the reverb run on threads (scipy releases the GIL, and nothing gets copied between processes). Delays are sliced instead of interpolated, the reverb uses overlap-add convolution, and filter designs are cached.

Rendering now has an explicit planning stage (`seraphim.render.plan`) used by both synthesis and `inspect`. Stop closure, release and aspiration share the planned duration, so lines and choir chunks do not overrun their slots. Worker results and spatialized buffers are consumed in bounded batches. The CLI only retains stems when exporting them or making a preview. Process workers and lexicon locks currently target Linux.

## Preview, diagnostics and audio export

```sh
./seraphim.sh synth examples/pain.sera -o out/pain.wav --preview out/pain.html
./seraphim.sh synth examples/succubus.sera --stems out/stems --format float32 --no-master -o out/raw.wav
./seraphim.sh inspect examples/nephilim.sera --room hall > out/plan.json
./seraphim.sh check examples/pain.sera --strict --json
./seraphim.sh translate --strict --no-save "The woman was seen by the man." -o out/portable.sera
```

The preview is a self-contained HTML file with audio, word highlighting, click-to-seek, and dry solo tracks for the mouths and choir. Open it locally in a browser; it needs no server or internet connection. Including all audio makes preview files fairly large.

`check --json` emits structured phonological diagnostics, and `--strict` exits unsuccessfully on rule violations. `read --strict` fails on unknown morphemes or broken word chains. `translate --strict` rejects constructions reported as approximations (currently unsupported coordination/conjunctions, unknown prepositions, and modal perfect/progressive combinations). This does not guarantee correct translation for arbitrary English. Unknown score metadata, duplicate mouth definitions and misspelled per-mouth voice keys are rejected early. Metadata belongs before the first word; `@predelay` uses seconds, while CLI `--predelay` uses milliseconds.

Stems preserve their original gain by default; `--normalize-stems` restores independent normalization for auditioning. Use `--format float32` to retain stem or raw-mix headroom without PCM clipping. `--no-master` bypasses final DC/rumble removal, peak normalization and saturation. By default mastering uses lighter saturation, consonant bursts have a short rounded attack, and strong sibilance is gently reduced before brightness and dialect wound effects are added. Reverb tails are allocated according to the selected decay time.

Simple modals are preserved as explicit `.MOD_can`, `.MOD_must`, `.MOD_may`, etc. features. Agentless passives use `.PASS`; passives with an agent become agent–verb–patient clauses. These are grammar extensions. Coordinated clauses with separate subjects receive separate START words and retain the conjunction in read-back.

## Development checks

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/regress.py > out/text-snapshot.txt
# Optional: Chromium and Node.js, no npm dependencies or listening port
node tools/check_preview.cjs out/pain.html
```

The suite covers translation roles and modals, vocabulary portability in a fresh process, atomic/concurrent lexicon updates, timing and choir chunk boundaries, both filter backends, dialect audio, stem export, and a render large enough to exercise multiprocessing. English tests skip if spaCy or its model is absent. CI runs core Python 3.10/3.12 environments and a separate English/numba environment.

## Score format (`.sera`)

```
@title: anything
@tense: nonpast          # later words inherit the previous word's tense
word farpast             # farpast | gnomic | nearpast | nonpast (FPST GNOM PST NPRES), stack with +
  top: אלוקים בור אלוקים☢ מה
  1:   ~ אדּב לכּדּ☀ - בורא אלוקים☀ וו אלוקים☀
  2:   Ø
  end: /600/ /45/*
---                      # sentence break
```

Brightness marks go after a token: `☀`/`*` bright, `🔆`/`☀☀`/`**` extra bright, `☢`/`!` ionized. `/n/` auto-spells phoneme *n*. `-` is a morpheme break and `~` marks a 4D-moved line.

## Examples

* `examples/sentence1.sera` is sentence 1 of the video's demo, transcribed back into Hebrew from the on-screen IPA. `read` decodes it to the video's own gloss, `NPFV NEG 1S comprehend -OBJ ABS- Aghma_Shwa CON- allure`. `check` shows where the demo breaks its own phonology.
* `examples/kadosh.sera` hides *qadosh* and *amen* in pointed-Hebrew phonemes.
* `examples/pain.sera`/`pain.txt` ("Begone, evil spirits! Stop hurting me! Oh! I… I feel like my wings are breaking…") is the tonal-marker test: commands, a scream, a stammer, a whimper, and wings breaking.
* `examples/heaven.sera` ("Please don't cry, child of hell…") and `examples/demonic.sera`/`demonic.txt` ("My sweet one, if you were a person…", in the demonic dialect) exercise the grammar extensions: imperative `IMP`, irrealis `IRR`, conditional `IF`, questions `Q`/`WH`, `AND`, the vocative, the similative `SIM-`, inanimate `3N` and demonstratives.
* `examples/english.txt` is the video's source text. Try `./seraphim.sh translate < examples/english.txt --audio out/x.wav`.

## Limitations

* Translation is rule-based on a spaCy dependency parse. Simple passives, modal distinctions and separate-subject coordination are supported, but complex questions, relative clauses, nested coordination, modal perfect/progressive combinations and heavy idioms remain approximate. spaCy can misidentify predicates. `--strict` rejects known approximations; it cannot detect every semantic loss. The video also rephrased its verbs by hand ("understand" → "comprehend"), which this tool doesn't.
* A raw gloss is flat, so when a subject contains a relative clause the main verb can't be found. Mark it with `@main` (`present:V@main`). The English path does this automatically.
* Trees are flattened to a right-branching spine. Left-branching specifiers (an AdjP subject, a relative clause inside it) are spelled out in place, which simplifies what the video does with its separate subtrees.
* The English produced by `read` is a rough gloss reading, not literature.
* The audio is formant synthesis and sounds robotic. For angels that's arguably on-brand.
