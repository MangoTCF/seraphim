"""seraphim: a voice synthesizer for Babelingua's Seraphim."""

import argparse
import math
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import wavfile

from . import hebrew
from .grammar import GrammarError
from .score import MOUTHS, ScoreError, parse, report
from .synth import SR


def _write(path, audio, format="pcm16"):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    if not np.isfinite(audio).all():
        raise ScoreError("audio contains nonfinite samples")
    pcm = audio.astype(np.float32) if format == "float32" else (np.clip(audio, -1, 1) * 32767).astype(np.int16)
    wavfile.write(path, SR, pcm)


PLAYERS = (["pw-play"], ["paplay"], ["aplay", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"])


def _play(audio):
    """Play through the first audio player found (PipeWire, Pulse, ALSA, ffmpeg)."""
    cmd = next((c for c in PLAYERS if shutil.which(c[0])), None)
    if cmd is None:
        sys.exit("seraphim: no audio player found (install pipewire, pulseaudio-utils, alsa-utils or ffmpeg)")
    with tempfile.NamedTemporaryFile(suffix=".wav") as f:
        _write(f.name, audio)
        print(f"playing {len(audio) / SR:.1f} s via {cmd[0]} (ctrl-c stops)", file=sys.stderr)
        try:
            subprocess.run(cmd + [f.name], check=False)
        except KeyboardInterrupt:
            pass


def _out(args, audio, default):
    """Write and/or play: --play alone writes nothing, otherwise -o (or default)."""
    path = args.output or (None if args.play else default)
    if path:
        _write(path, audio, getattr(args, "format", "pcm16"))
        print(f"wrote {path} ({len(audio) / SR:.1f} s)", file=sys.stderr)
    if args.play:
        _play(audio)


def _voice(spec):
    from .render import parse_voice
    try:
        return parse_voice(spec)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def _number(s, *, positive=False, unit=False):
    try:
        v = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {s!r}") from None
    if not math.isfinite(v):
        raise argparse.ArgumentTypeError("must be finite")
    if positive and v <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    if not positive and v < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    if unit and not 0 <= v <= 1:
        raise argparse.ArgumentTypeError("must be between 0 and 1")
    return v


def _finite_float(s):
    try:
        v = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {s!r}") from None
    if not math.isfinite(v):
        raise argparse.ArgumentTypeError("must be finite")
    return v


def _positive_float(s):
    return _number(s, positive=True)


def _nonnegative_float(s):
    return _number(s)


def _unit_float(s):
    return _number(s, unit=True)


def _nonnegative_int(s):
    try:
        v = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {s!r}") from None
    if v < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return v


def _knob_type(name):
    if name == "pitch":
        return _finite_float
    if name == "gender":
        def gender(s):
            v = _finite_float(s)
            if not -1 <= v <= 1:
                raise argparse.ArgumentTypeError("must be between -1 and 1")
            return v
        return gender
    return _unit_float


VOICE_HELP = ("-1 masculine .. 0 androgynous .. +1 feminine, or per mouth: "
              "'top=1,1=0.5,2=-0.5,end=0,choir=1' (also: masculine/androgynous/feminine)")


def _dialect(name):
    from . import dialects
    try:
        dialects.get(name)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))
    return name


KNOB_HELP = {
    "growl": "subharmonic growl from torn vocal folds",
    "fry": "creaky vocal fry",
    "roar": "false-fold turbulence and distortion",
    "whistle": "air whistling through wounds",
    "throat": "pharyngeal constriction",
    "disfigure": "how unevenly the damage spreads over the mouths",
    "pitch": "pitch shift in semitones",
    "breath": "breathiness: more air, softer voice (any dialect)",
    "moan": "moaning: long sliding, swelling vowels and sighs (any dialect)",
    "whisper": "a whispered double of each mouth, right at your ears (any dialect)",
    "grab": "voices pull in to your ears, lurching closer on hungry/tender words (any dialect)",
    "hunger": "teeth snaps, slurps, kisses and growl surges on hungry/tender words (any dialect)",
    "swap": "nephilim: how often the angelic and fallen halves trade sides (0 fixed .. 1)",
}


def _tones(spec):
    from .score import parse_tones
    try:
        return parse_tones(spec)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


def _room_kw(args):
    """Reverb, tone and parallelism options shared by every rendering command."""
    return dict(sample_banks=getattr(args, "sample_bank", None), sample_approximation=not getattr(args, "strict_bank_phones", False),
                syllable_blend=getattr(args, "syllable_blend", .5), mouth_blend=getattr(args, "mouth_blend", None),
                prayer_time=not getattr(args, "no_prayer_time", False), transitions=getattr(args, "transitions", 1.0),
                prayer_tail=getattr(args, "prayer_tail", 2.4), prayer_rise=getattr(args, "prayer_rise", 7.0),
                tones=getattr(args, "tone", None),room=getattr(args, "room", None), reverb=getattr(args, "reverb", None),
                reverb_time=getattr(args, "reverb_time", None), reverb_tone=getattr(args, "reverb_tone", None),
                predelay=None if getattr(args, "predelay", None) is None else args.predelay / 1000,
                jobs=getattr(args, "jobs", 0) or 0, master=not getattr(args, "no_master", False))


def _knobs(args):
    return {k: getattr(args, k, None) for k in KNOB_HELP if getattr(args, k, None) is not None}


def _load(args):
    with open(args.score, encoding="utf-8") as f:
        text = f.read()
    return parse(text, heresy=args.heresy, seed=args.seed, dialect=getattr(args, "dialect", None))


def cmd_check(args):
    from .score import diagnostics
    score = _load(args)
    issues = diagnostics(score)
    print(json.dumps(issues, ensure_ascii=False, indent=2) if args.json else report(score))
    if args.strict and issues:
        raise SystemExit(1)


def cmd_inspect(args):
    from .render import Options, plan
    score = _load(args)
    resolved = plan(score, Options(seed=args.seed, dialect=args.dialect, voice=args.voice,
                                   knobs=_knobs(args), **_room_kw(args)))
    summary = resolved.summary()
    summary["score"] = dict(title=score.meta.get("title", ""),
                           portable=bool(score.lexicon), lexicon_hash=score.meta.get("lexicon_hash"))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_synth(args):
    from .render import Options, plan, synthesize
    score = _load(args)
    if args.tempo is not None:
        score.meta["tempo"] = str(args.tempo)
    if not args.quiet:
        print(report(score), file=sys.stderr)
    opts = Options(choir=not args.no_choir, space=not args.no_space,
                   reverse_4d=args.reverse_4d, seed=args.seed, glitter=args.glitter, hum=args.hum,
                   keep_stems=bool(args.stems or args.preview),
                   voice=args.voice, dialect=args.dialect, knobs=_knobs(args), **_room_kw(args))
    if args.choir_level is not None:
        opts.choir_level = args.choir_level
    say = (lambda s: print(f"  … {s}", file=sys.stderr)) if not args.quiet else None
    resolved = plan(score, opts)
    out, stems = synthesize(score, progress=say, render_plan=resolved)
    if args.stems:
        for name, sig in stems.items():
            peak = np.max(np.abs(sig))
            if args.normalize_stems and peak > 0:
                sig = sig / peak * 0.9
            _write(os.path.join(args.stems, f"{name}.wav"), sig, args.format)
        print(f"wrote stems to {args.stems}/", file=sys.stderr)
    if args.preview:
        from .preview import html_preview
        os.makedirs(os.path.dirname(os.path.abspath(args.preview)), exist_ok=True)
        with open(args.preview, "w", encoding="utf-8") as f:
            f.write(html_preview(score, resolved, out, stems))
        print(f"wrote {args.preview}", file=sys.stderr)
    _out(args, out, "seraphim.wav")


def cmd_say(args):
    """One word straight from the command line."""
    lines = [f"@tense: {args.tense}", "word"]
    for m, v in zip(MOUTHS, (args.top, args.one, args.two, args.end)):
        if v:
            lines.append(f"  {m}: {v}")
    args.score = None
    score = parse("\n".join(lines), heresy=args.heresy, seed=args.seed, dialect=args.dialect)
    from .render import Options, synthesize
    if not args.quiet:
        print(report(score), file=sys.stderr)
    out, _ = synthesize(score, Options(choir=not args.no_choir, seed=args.seed, voice=args.voice,
                                       dialect=args.dialect, knobs=_knobs(args), keep_stems=False, **_room_kw(args)))
    _out(args, out, "seraphim-word.wav")


def cmd_spell(args):
    for v in args.values:
        kind = []
        if v in hebrew.CONSONANT_VALUES:
            kind.append("consonant")
        if v in hebrew.VOWEL_VALUES:
            kind.append("vowel")
        if not kind:
            print(f"/{v}/: not a Seraphim phoneme")
            continue
        words = hebrew.spell(v, limit=args.n)
        print(f"/{v}/ ({' or '.join(kind)}): " + "  ".join(f"{w} [{''.join(hebrew.to_ipa(w))}]" for w in words))


def cmd_gematria(args):
    for s in args.strings:
        total = hebrew.gematria(s)
        val = hebrew.phoneme_value(s)
        ambiguous = val in hebrew.AMBIGUOUS_VALUES
        cls = "vowel or consonant (brightness decides)" if ambiguous else hebrew.classify(val, False)
        cls = {"V": "vowel", "C": "consonant"}.get(cls, cls)
        note = "" if total == val else f" (sum not a phoneme, first letter used)"
        warn = "  ✝ divine name, forbidden" if hebrew.is_divine_name(s) else ""
        print(f"{s}: Σ={total} → /{val}/ {cls}{note} [{''.join(hebrew.to_ipa(s))}]{warn}")


def _lexicon(args):
    from .lexicon import Lexicon
    return Lexicon(save=not getattr(args, "no_save", False))


def _emit(sentences, lx, args):
    """Shared tail of translate/gloss: tables, score, audio, writing."""
    from .grammar import build, format_table, to_sera
    from .reading import english, read_score
    build(sentences, lx, move=not args.no_move, front=args.front or (), shuffle=args.shuffle)
    for s in sentences:
        for k, v in s.stages:
            print(f"{k:>12}: {v}", file=sys.stderr)
        print(format_table(s), file=sys.stderr)
        print(file=sys.stderr)
    title = args.title or " ".join(" ".join(getattr(s, "source", s.english).split()) for s in sentences if getattr(s, "source", s.english))
    text = to_sera(sentences, lx, title=title,
                   seed=args.seed, dialect=args.dialect)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.output}", file=sys.stderr)
    elif not args.audio and not args.html and not args.play:
        print(text)
    score = parse(text, heresy=True, seed=args.seed)
    back = " ".join(english(r, lx) for r in read_score(score, lx))
    print(f"{'read back':>12}: {back}", file=sys.stderr)
    if args.html:
        from .orthography import html_page
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(html_page(score, score.meta.get("title", "Seraphim")))
        print(f"wrote {args.html}", file=sys.stderr)
    if args.audio or args.play:
        from .render import Options, synthesize
        out, _ = synthesize(score, Options(seed=args.seed, voice=args.voice, dialect=args.dialect,
                                           knobs=_knobs(args), keep_stems=False, **_room_kw(args)))
        if args.audio:
            _write(args.audio, out, args.format)
            print(f"wrote {args.audio} ({len(out) / SR:.1f} s)", file=sys.stderr)
        if args.play:
            _play(out)


def cmd_translate(args):
    from .english import translate
    lx = _lexicon(args)
    text = " ".join(args.text) if args.text else sys.stdin.read()
    _emit(translate(text, lx, strict=args.strict), lx, args)


def cmd_gloss(args):
    from .grammar import clause_from_gloss
    lx = _lexicon(args)
    sents = []
    for g in " ".join(args.gloss).split("//"):
        s = clause_from_gloss(g.strip(), args.tense, lx)
        s.english = g.strip()
        sents.append(s)
    _emit(sents, lx, args)


def cmd_read(args):
    from .reading import english, fronted, read_score
    score = _load(args)
    from .lexicon import score_lexicon
    lx = score_lexicon(score)
    for i, r in enumerate(read_score(score, lx), 1):
        print(f"sentence {i}")
        for w in r["chain"]:
            m = lambda d: "Ø" if d is None else ("~" if d.moved else "") + d.gloss
            print(f"  [{w.spoken}] {w.top} / {m(w.m1)} / {m(w.m2)} / {w.end or '-'}   ({'+'.join(w.langs)})")
        for p in r["problems"]:
            print(f"  ! {p}")
        print("  gloss:   " + " ".join(r["terms"]))
        print("  tense:   " + "; ".join(f"word {w['spoken']}: {'+'.join(w['tenses']) or 'unspecified'}" for w in r["temporal"]))
        if fronted(r):
            print("  active:  " + ", ".join(fronted(r)) + " (spoken before the start word)")
        print("  english: " + english(r, lx))
        if args.strict and r["problems"]:
            raise SystemExit(1)


def cmd_write(args):
    from .orthography import html_page, terminal
    score = _load(args)
    if args.html:
        with open(args.html, "w", encoding="utf-8") as f:
            f.write(html_page(score, score.meta.get("title", "Seraphim")))
        print(f"wrote {args.html}", file=sys.stderr)
    else:
        print(terminal(score))


def cmd_lexicon(args):
    from .lexicon import POS_VALUES, USER, Lexicon, LexiconError, check_tokens, guess_pos
    lx = Lexicon(save=False)
    if args.action == "list":
        for e in sorted(lx.entries.values(), key=lambda e: (e.source, e.gloss)):
            if args.grep and args.grep not in e.gloss:
                continue
            print(f"{e.gloss:<16} {e.pos:<5} {e.source:<8} {' '.join(e.tokens)}")
    elif args.action == "add":
        if not args.gloss:
            raise LexiconError("lexicon add needs a gloss and at least one token: seraphim lexicon add GLOSS TOKENS...")
        if not args.tokens:
            raise LexiconError(f"lexicon add {args.gloss}: at least one token is required")
        pos = args.pos or guess_pos(args.gloss)
        if pos not in POS_VALUES:
            raise LexiconError(
                f"unknown part of speech {pos!r}; known: {', '.join(sorted(POS_VALUES))}")
        check_tokens(args.tokens)
        lx.add(args.gloss, pos, args.tokens, replace=args.replace)
        print(f"added {args.gloss} to {USER}")
    elif args.action == "path":
        print(USER)


def main(argv=None):
    p = argparse.ArgumentParser(prog="seraphim", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    web = sub.add_parser("web", help="open the local browser voice workbench")
    web.add_argument("--port", type=int, default=8765)
    web.add_argument("--output", help="directory for render files")
    def launch_web(args):
        from .web import main as web_main
        options = ["--port", str(args.port)]
        if args.output:
            options += ["--output", args.output]
        web_main(options)
    web.set_defaults(func=launch_web)

    from . import dialects

    def common(sp):
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--heresy", action="store_true", help="allow names of God as phonemes")
        sp.add_argument("-d", "--dialect", type=_dialect, metavar="NAME",
                        help="dialects: " + ", ".join(sorted(dialects.DIALECTS)) +
                        "; default: seraphic; aliases: " + ", ".join(sorted(dialects.ALIASES)))

    def knob_opts(sp):
        def sample_assignment(value):
            from .samplebank import parse_selection
            try:
                return parse_selection(value)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(str(exc)) from None
        sp.add_argument("--sample-bank", type=sample_assignment, metavar="ASSIGNMENTS", help="BANK or top=BANK,1=BANK,choir=BANK,praise-1=BANK; formant keeps the built-in voice")
        sp.add_argument("--strict-bank-phones", action="store_true", help="use formant fallback rather than approximating missing bank phonemes")
        def blend_assignment(value):
            from .legato import parse_overrides
            try:
                return parse_overrides(value)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(str(exc)) from None
        sp.add_argument("--syllable-blend", type=_unit_float, default=.5, metavar="N", help="0 previous articulation .. 1 connected syllable blending")
        sp.add_argument("--mouth-blend", type=blend_assignment, metavar="ASSIGNMENTS", help="per-mouth syllable blend, e.g. top=0.8,1=0.4,praise-1=0; omitted mouths inherit")
        sp.add_argument("--transitions", type=_unit_float, default=1.0, metavar="N", help="0 linear ramps .. 1 smooth sound transitions")
        sp.add_argument("--no-prayer-time", action="store_true", help="use legacy chant without melodic tense signatures")
        sp.add_argument("--prayer-tail", type=float, default=2.4, metavar="SECONDS", help="final prayer fade, 0 to disable")
        sp.add_argument("--prayer-rise", type=float, default=7.0, metavar="SEMITONES", help="pitch rise during the prayer fade")
        g = sp.add_argument_group("voice and dialect tuning (0 = off; defaults come from the dialect)")
        for k, h in KNOB_HELP.items():
            g.add_argument(f"--{k}", type=_knob_type(k), metavar="N", help=h)
        from .fx import ROOMS
        r = sp.add_argument_group("reverb")
        r.add_argument("--room", choices=list(ROOMS),
                       help="reverb preset; 'clip' matches source-materials/video_2026-10-22_02-40-39.mp4 (default cathedral)")
        r.add_argument("--reverb", type=_nonnegative_float, metavar="N", help="wet amount: 1 = the room's normal level, 0 = dry, 2 = drenched")
        r.add_argument("--reverb-time", type=_nonnegative_float, metavar="S", help="decay time (RT60) in seconds, overriding the room")
        r.add_argument("--reverb-tone", type=_unit_float, metavar="N", help="tail colour: 0 bright .. 1 dark")
        r.add_argument("--predelay", type=_nonnegative_float, metavar="MS", help="gap before the tail starts, in milliseconds")
        sp.add_argument("--no-master", action="store_true", help="preserve raw mix gain; pair with --format float32")
        sp.add_argument("--format", choices=("pcm16", "float32"), default="pcm16", help="WAV sample format (default pcm16)")
        sp.add_argument("-j", "--jobs", type=_nonnegative_int, default=0, help="parallel workers (0 = one per core, 1 = no parallelism)")
        sp.add_argument("--tone", type=_tones, metavar="SPEC",
                        help="tonal markers for every word, e.g. pain:0.8,scream:0.5 (pain scream anger fear whimper)")

    sp = sub.add_parser("synth", help="render a .sera score to WAV")
    sp.add_argument("score")
    sp.add_argument("-o", "--output", help="WAV to write (default seraphim.wav unless --play)")
    sp.add_argument("-p", "--play", action="store_true", help="play it through the speakers")
    sp.add_argument("--stems", metavar="DIR", help="also write each voice dry, preserving its gain")
    sp.add_argument("--normalize-stems", action="store_true", help="normalize stems independently (for auditioning)")
    sp.add_argument("--preview", metavar="HTML", help="self-contained player with timed words and solo voices")
    sp.add_argument("--no-choir", action="store_true", help="skip the three praise voices")
    sp.add_argument("--no-space", action="store_true", help="plain stereo instead of binaural")
    sp.add_argument("--reverse-4d", action="store_true", help="play 4D-moved morphemes backwards")
    sp.add_argument("--choir-level", type=_nonnegative_float)
    sp.add_argument("--tempo", type=_positive_float, help="speed factor, e.g. 1.3 (overrides the score's @tempo)")
    sp.add_argument("--glitter", type=_nonnegative_float, default=1.0, help="extra-bright glitter level (0 = off)")
    sp.add_argument("--hum", type=_nonnegative_float, default=0.3, help="closed/null mouths hum at this level (0 = silent, as in the video)")
    sp.add_argument("-v", "--voice", type=_voice, help=VOICE_HELP)
    knob_opts(sp)
    sp.add_argument("-q", "--quiet", action="store_true")
    common(sp)
    sp.set_defaults(func=cmd_synth)

    sp = sub.add_parser("check", help="analyse a score: gematria, phonemes, syllables, rule breaks")
    sp.add_argument("score")
    common(sp)
    sp.add_argument("--strict", action="store_true", help="fail on phonological rule violations")
    sp.add_argument("--json", action="store_true", help="structured diagnostics")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("inspect", help="show resolved render settings and word timings as JSON")
    sp.add_argument("score")
    sp.add_argument("-v", "--voice", type=_voice, help=VOICE_HELP)
    knob_opts(sp)
    common(sp)
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("say", help="render a single word given on the command line")
    sp.add_argument("--top")
    sp.add_argument("--one", "-1")
    sp.add_argument("--two", "-2")
    sp.add_argument("--end")
    sp.add_argument("--tense", default="nonpast")
    sp.add_argument("-v", "--voice", type=_voice, help=VOICE_HELP)
    knob_opts(sp)
    sp.add_argument("-o", "--output", help="WAV to write (default seraphim-word.wav unless --play)")
    sp.add_argument("-p", "--play", action="store_true", help="play it through the speakers")
    sp.add_argument("--no-choir", action="store_true")
    sp.add_argument("-q", "--quiet", action="store_true")
    common(sp)
    sp.set_defaults(func=cmd_say)

    sp = sub.add_parser("spell", help="suggest Hebrew strings for phoneme values")
    sp.add_argument("values", type=int, nargs="+")
    sp.add_argument("-n", type=int, default=6)
    sp.set_defaults(func=cmd_spell)

    sp = sub.add_parser("gematria", help="value and phoneme of Hebrew strings")
    sp.add_argument("strings", nargs="+")
    sp.set_defaults(func=cmd_gematria)

    def lang_opts(sp):
        sp.add_argument("-o", "--output", help="write the .sera score here (default: stdout)")
        sp.add_argument("--audio", metavar="WAV", help="also render audio")
        sp.add_argument("-p", "--play", action="store_true", help="render and play it through the speakers")
        sp.add_argument("-v", "--voice", type=_voice, help=VOICE_HELP)
        knob_opts(sp)
        sp.add_argument("--html", metavar="HTML", help="also write the orthography as a web page")
        sp.add_argument("--front", nargs="+", metavar="MORPHEME",
                        help="speak the words containing these first (makes them more active)")
        sp.add_argument("--shuffle", type=int, metavar="SEED", help="random legal word order")
        sp.add_argument("--no-move", action="store_true", help="skip 4D V-to-T-to-C movement (ungrammatical!)")
        sp.add_argument("--no-save", action="store_true", help="don't remember newly coined words")
        sp.add_argument("--title")
        common(sp)

    sp = sub.add_parser("translate", help="English -> Seraphim (needs spaCy)")
    sp.add_argument("text", nargs="*", help="English text (default: stdin)")
    lang_opts(sp)
    sp.add_argument("--strict", action="store_true", help="reject unsupported constructions reported as warnings")
    sp.set_defaults(func=cmd_translate)

    sp = sub.add_parser("gloss", help="gloss line -> Seraphim, e.g. 'NPFV NEG.ever 1S comprehend-OBJ ABS-Aghma_Shwa CON-allure'")
    sp.add_argument("gloss", nargs="+", help="morphemes; separate sentences with //")
    sp.add_argument("--tense", default="nonpast", help="farpast | gnomic | nearpast | nonpast, stackable with +")
    lang_opts(sp)
    sp.set_defaults(func=cmd_gloss)

    sp = sub.add_parser("read", help="Seraphim score -> gloss -> rough English")
    sp.add_argument("score")
    common(sp)
    sp.add_argument("--strict", action="store_true", help="fail on unknown morphemes or a broken word chain")
    sp.set_defaults(func=cmd_read)

    sp = sub.add_parser("write", help="Seraphim orthography (terminal, or --html page)")
    sp.add_argument("score")
    sp.add_argument("--html", metavar="HTML")
    common(sp)
    sp.set_defaults(func=cmd_write)

    sp = sub.add_parser("lexicon", help="list or extend the morpheme lexicon")
    sp.add_argument("action", choices=["list", "add", "path"])
    sp.add_argument("gloss", nargs="?")
    sp.add_argument("tokens", nargs="*")
    sp.add_argument("--pos")
    sp.add_argument("--grep")
    sp.add_argument("--replace", action="store_true", help="overwrite an existing user entry")
    sp.set_defaults(func=cmd_lexicon)

    args = p.parse_args(argv)
    try:
        args.func(args)
    except (ScoreError, GrammarError, OSError) as e:
        sys.exit(f"seraphim: {e}")


if __name__ == "__main__":
    main()
