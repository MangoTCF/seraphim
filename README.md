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

```sh
./seraphim.sh <command>         # uses .venv (with spaCy) if present
# or install:  pipx install '.[english,fast]' && python -m spacy download en_core_web_sm
```

| Command | What it does |
|---|---|
| `translate "English…" -o x.sera --audio x.wav --html x.html` | English → gloss → tree → words → movement → tense → score. It prints every stage, then reads the result back into English as a check. |
| `gloss "NPFV NEG.ever 1S comprehend-OBJ ABS-Aghma_Shwa CON-allure" --tense farpast` | The same pipeline, starting from a gloss written the way the video writes them |
| `read x.sera` | Seraphim → gloss → English, with tree order and movement undone |
| `synth x.sera -o x.wav [--stems dir/]` | Render the seven voices to binaural audio |
| `write x.sera [--html x.html]` | Seraphim orthography |
| `check x.sera` | Gematria, phonemes, syllables, rule breaks |
| `spell 26 45 613` · `gematria אלוקים החם` | Phoneme helpers |
| `lexicon list [--grep x]` · `lexicon add GLOSS TOKENS… [--pos V]` · `lexicon path` | The morpheme lexicon |
| `say --top "שהב ליה☀ גשד" --end "/600/ /45/☢"` | One hand-made word |

Use headphones for the audio. The voices are placed binaurally around the listener.

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

**4D V-to-T-to-C movement.** After spell-out, the aspect marker and the verb move to the null C slot of the `START` word, and a one-word subject moves to spec-TP with `.NOM`. Those mouths stay closed (`~` in scores). Traces stay behind. Again, this is identical to the demo.

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
* Any other word is coined on first use and saved to `~/.local/share/seraphim/lexicon.tsv`. Coining works like a clever angel: each phoneme is spelled with a real word from the Shema, Kedusha, Aleinu, Psalm 150, the priestly blessing or Adon Olam whose gematria gives it, and names of God are filtered out.
* Decoding matches phoneme values, never spelling, because only gematria is phonemic.

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
| Pronunciation | By default, unpointed strings are read the way Hebrew is: ו/י after a consonant are the vowels u/o and i, final א/ה is a, and the vowel between two consonants is a next to gutturals, otherwise e then ə (אלוקים → [ʔaluqim], אהבה → [ʔahava]). `@reading: demo` gives the demo's exact schwa chains ([ʔələwəqəjəm]). Soft בגדכפת unless dagesh. Pointed strings (with niqqud) are read as real Hebrew. |
| Free variation in spelling | Only gematria is phonemic, so generated scores keep each spelling once and respell repeats with other prayer words of the same value. Meaning and decoding are unchanged, but not every word says אלוקים. |
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
| `succubus` (`lilith`, `lilit`, `seductive`) | Hellish grammar (heresy on) in a seductive voice: feminine by default (`-v` overrides), breathy and moaning, with a whispered double breathed right at your ears and only a trace of the fall (light fry, a low growl underneath). The choir sings backwards in Phrygian. |
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

`--tempo 1.4` speeds a render up (moaning is slow).

```sh
./seraphim.sh translate -d demonic --play < examples/demonic.txt
./seraphim.sh synth examples/demonic.sera --growl 1 --whistle 0 --pitch -7 --play
./seraphim.sh synth examples/heaven.sera -d fallen --play      # an angel's text, fallen
```

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
* `examples/heaven.sera` ("Please don't cry, child of hell…") and `examples/demonic.sera`/`demonic.txt` ("My sweet one, if you were a person…", in the demonic dialect) exercise the grammar extensions: imperative `IMP`, irrealis `IRR`, conditional `IF`, questions `Q`/`WH`, `AND`, the vocative, the similative `SIM-`, inanimate `3N` and demonstratives.
* `examples/english.txt` is the video's source text. Try `./seraphim.sh translate < examples/english.txt --audio out/x.wav`.

## Limitations

* Translation is rule-based on a spaCy dependency parse. Plain declarative sentences work well; questions, passives, coordination and heavy idioms come out rough. The video also rephrased its verbs by hand ("understand" → "comprehend"), which this tool doesn't.
* A raw gloss is flat, so when a subject contains a relative clause the main verb can't be found. Mark it with `@main` (`present:V@main`). The English path does this automatically.
* Trees are flattened to a right-branching spine. Left-branching specifiers (an AdjP subject, a relative clause inside it) are spelled out in place, which simplifies what the video does with its separate subtrees.
* The English produced by `read` is a rough gloss reading, not literature.
* The audio is formant synthesis and sounds robotic. For angels that's arguably on-brand.
