# Scope and tense conventions for this implementation

These are implementation conventions, not a claim that the original creator
specified every case below. They make the existing representation explicit;
they introduce no new spoken morphemes or prayer languages.

## Scope follows the reconstructed tree

The grammar builds a right-branching spine. Within a word, the structural order
is **top → mouth 1 → mouth 2 → end**. Top names the current phrase; 1 and 2 carry
its next terminals; end names the remaining phrase. This is a structural order,
not a rule that the earlier sound wins: those mouths speak simultaneously.

A word's end links to the following word's top in **tree order**. Macrosyntactic
fronting and shuffle change spoken order/activity, not this chain. Read-back
reconstructs the chain before interpreting terminals. The grammar panel displays
both the recovered terminal spine and the spoken word numbers in tree order.

4D movement relocates aspect/verb and subject into START slots. For decoding,
these expressions return to their traces. Moving material does not independently
change its scope. Editing a mouth can break a chain or introduce an unknown
morpheme; diagnostics report that rather than inventing a valid interpretation.

This is not a complete logical-form interpreter. General quantifier raising,
ambiguous quantifier/negation readings and relative-clause attachment remain
unsupported/approximate. Separate explicit COMP clauses are preferable when a
flat gloss would leave the intended structure unclear. Changing spoken order
alone must not be used to express a different quantifier scope.

## Exact tense is distinct from chant language

| Grammatical tense | Prayer language |
| --- | --- |
| farpast | Aramaic |
| gnomic | Aramaic |
| nearpast | Greek |
| nonpast | Latin |

The parser now retains `Word.tenses`, separately from `Word.langs`. The reader
and workbench expose those exact effective tense labels. Omitted word tense
inherits the preceding word's labels, just as its chant languages already did.
The legacy spelling `aramaic` remains ambiguous between far past and gnomic;
we do not guess which the author meant. Existing aliases retain their old
meaning (`future` remains a nonpast alias, not a newly invented future tense).

For this implementation, `farpast+nonpast` applies the clause jointly in both
named temporal contexts. It does **not**, on its own, assert uninterrupted truth
throughout the intervening interval, uncertainty about which time applies, or a
choice between two mutually exclusive readings. `gnomic+nonpast` combines a
present-context assertion with a general-truth assertion; gnomic is not an
earlier point on a timeline. Duplicate labels are semantically redundant, while
the existing choir scheduling is retained unchanged for compatibility.

Prayer voices share stacks of up to three labels round-robin. With the new
optional audible-tense extension, larger stacks use successive subslots so all
labels reach a voice. This does not turn conjunction into temporal sequence;
the slots are an acoustic serialization of the same jointly asserted contexts.

### Audible-tense extension

The default synth adds short scale-relative contours at word entries: descending
for farpast, steady for gnomic, rising for nearpast and arching for nonpast.
Both Aramaic tenses therefore have distinct sung signatures without adding a new
prayer language. The selected dialect's mode and choir transposition still apply.
Unknown/legacy `aramaic` labels do not acquire a guessed grammatical cue.

The chant schedule is built against final playback time. Backmasked prayer
voices get mirrored source-language intervals and pre-mirrored pitch contours,
so reversing the waveform preserves word-to-tense assignment and the audible
cue direction. Phrase breaths avoid swallowing the short identifying cue.

This is an implementation extension, not an assertion about the original
language. Turn off **Audible tense signatures** or use `--no-prayer-time` for
legacy chant. Legacy chant retains the previous syllable-boundary language
scheduling and whole-track backmask behavior; it has no new alignment guarantee.
The English read-back remains a rough realization, so exact written tense
labels remain authoritative.

Continuous intervals and epistemic uncertainty remain future language-design
proposals, not implemented syntax.

## Editing and auditions

The word inspector edits the existing source score, including its embedded
lexicon. A local tense edit explicitly freezes the following word's previous
effective tense when necessary, so it does not silently retime the rest of the
utterance. Changing the scope of subsequent words remains possible in the raw
score editor. Invalid edits leave the source untouched.

An audition renders only the selected word, with its effective tense and source
index retained. It replans that word in isolation; its contour, choir entry and
reverb can differ from the same word inside a full sentence. The source download
and grammar panel retain the full composition. Render the full score to judge
connected speech and final movement/timing.
