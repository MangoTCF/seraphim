# Word-join correction

2026-11-18. User reported that the initial syllable blending made speech less
natural and still left audible word gaps.

## Confirmed problems

- Speech was synthesized independently for each word. Each source restarted its
  excitation phase, then received an edge fade before placement on the timeline.
- The plan also reserved a 25 ms inter-word gap (scaled by tempo). Broad spectral
  smoothing inside words did nothing to fill that interval.
- Whole-phoneme log-spectrum averaging and automatic energy leveling could blur
  articulation; changing source recordings halfway through a phone compounded it.
- Closed-mouth hums separately restarted and faded at every word too.

## Correction

Positive syllable blend now groups compatible consecutive lines into a source
phrase, bounded to twelve seconds for memory use. Conditions include the same
mouth/voice/tone/dialect settings, consecutive words and a short scheduling gap.
Sentence boundaries, displaced lines and incompatible voice changes split groups.

Each group is synthesized once. Word-specific effects and brightness spans are
then applied to the corresponding slices. The slices use a shared sample grid,
so their placement cannot accumulate sample-rounding holes. Word timestamps
remain unchanged to preview/sample precision. Internal fades are removed where
words are actually connected. Sustained voiced sounds or unvoiced fricatives
can carry across the microgap; this is not insertion of voicing into a fricative
or deletion of a consonant closure. Formant and sampled voices use the same
connection policy. Hums have an equivalent continuous-source path.

Whole-vowel smoothing, adaptive spectral energy leveling and alternate-recording
morphs have been removed. The remaining amount-dependent repair is local to
short joins, preserving stable vowel interiors and native dynamics. Zero keeps
the independent-word renderer; the seven per-mouth overrides remain available.

Growl/whisper/damage/brightness effects retain their word-specific processing;
not every effect layer shares a single phrase source. Source grouping is bounded,
and intentionally different roles or expressive settings can still form separate
chunks. This remains an experimental sample renderer, not a replacement for a
complete speech model.

## Evidence

`out/word-joins/before.wav` preserves the previous strong-blend dry Miku rendering
of `examples/kadosh.sera` at tempo 1.5. `after.wav` uses the corrected renderer.
`before-then-after.wav` uses one common gain for comparison. Before/after source
copies and plans, plus `verification.json`, are retained in that directory.

For the ordinary word join at approximately 2.395–2.411 s, the old dry stem had
RMS 0.0; the corrected stem had RMS approximately 0.02546. The sentence break
was excluded from this measurement. Source timestamps and total frame counts
were unchanged. This confirms removal of an artificial silence; it is not an
objective measure of perceived speech naturalness.

Regression tests cover voiced and unvoiced connections, continuous hums, explicit
sentence pauses, unchanged timing/tags, per-mouth isolation, source recording
selection, zero bypass and serial/parallel rendering. Browser QA uses the normal
word-edit/audition/undo flow with real Miku bank assignments.
