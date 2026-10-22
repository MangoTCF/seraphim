"""seraphim: a voice synthesizer for Babelingua's Seraphim."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from scipy.io import wavfile

from . import hebrew
from .score import MOUTHS, ScoreError, parse, report
from .synth import SR


def _write(path, audio):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
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
        _write(path, audio)
        print(f"wrote {path} ({len(audio) / SR:.1f} s)", file=sys.stderr)
    if args.play:
        _play(audio)


def _voice(spec):
    from .render import parse_voice
    try:
        return parse_voice(spec)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e))


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
}


def _room_kw(args):
    """Reverb and parallelism options shared by every rendering command."""
    return dict(room=getattr(args, "room", None), reverb=getattr(args, "reverb", None),
                reverb_time=getattr(args, "reverb_time", None), reverb_tone=getattr(args, "reverb_tone", None),
                predelay=None if getattr(args, "predelay", None) is None else args.predelay / 1000,
                jobs=getattr(args, "jobs", 0) or 0)


def _knobs(args):
    return {k: getattr(args, k, None) for k in KNOB_HELP if getattr(args, k, None) is not None}


def _load(args):
    with open(args.score, encoding="utf-8") as f:
        text = f.read()
    return parse(text, heresy=args.heresy, seed=args.seed, dialect=getattr(args, "dialect", None))


def cmd_check(args):
    print(report(_load(args)))


def cmd_synth(args):
    from .render import Options, synthesize
    score = _load(args)
    if args.tempo:
        score.meta["tempo"] = str(args.tempo)
    if not args.quiet:
        print(report(score), file=sys.stderr)
    opts = Options(choir=not args.no_choir, space=not args.no_space,
                   reverse_4d=args.reverse_4d, seed=args.seed, glitter=args.glitter, hum=args.hum,
                   voice=args.voice, dialect=args.dialect, knobs=_knobs(args), **_room_kw(args))
    if args.choir_level is not None:
        opts.choir_level = args.choir_level
    say = (lambda s: print(f"  … {s}", file=sys.stderr)) if not args.quiet else None
    out, stems = synthesize(score, opts, say)
    if args.stems:
        for name, sig in stems.items():
            peak = np.max(np.abs(sig))
            if peak > 0:
                _write(os.path.join(args.stems, f"{name}.wav"), sig / peak * 0.9)
        print(f"wrote stems to {args.stems}/", file=sys.stderr)
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
                                       dialect=args.dialect, knobs=_knobs(args), **_room_kw(args)))
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
                                           knobs=_knobs(args), **_room_kw(args)))
        if args.audio:
            _write(args.audio, out)
            print(f"wrote {args.audio} ({len(out) / SR:.1f} s)", file=sys.stderr)
        if args.play:
            _play(out)


def cmd_translate(args):
    from .english import translate
    lx = _lexicon(args)
    text = " ".join(args.text) if args.text else sys.stdin.read()
    _emit(translate(text, lx), lx, args)


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
    lx = _lexicon(args)
    score = _load(args)
    for i, r in enumerate(read_score(score, lx), 1):
        print(f"sentence {i}")
        for w in r["chain"]:
            m = lambda d: "Ø" if d is None else ("~" if d.moved else "") + d.gloss
            print(f"  [{w.spoken}] {w.top} / {m(w.m1)} / {m(w.m2)} / {w.end or '-'}   ({'+'.join(w.langs)})")
        for p in r["problems"]:
            print(f"  ! {p}")
        print("  gloss:   " + " ".join(r["terms"]))
        if fronted(r):
            print("  active:  " + ", ".join(fronted(r)) + " (spoken before the start word)")
        print("  english: " + english(r, lx))


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
    from .lexicon import USER, Lexicon, check_tokens, guess_pos
    lx = Lexicon(save=False)
    if args.action == "list":
        for e in sorted(lx.entries.values(), key=lambda e: (e.source, e.gloss)):
            if args.grep and args.grep not in e.gloss:
                continue
            print(f"{e.gloss:<16} {e.pos:<5} {e.source:<8} {' '.join(e.tokens)}")
    elif args.action == "add":
        check_tokens(args.tokens)
        os.makedirs(os.path.dirname(USER), exist_ok=True)
        with open(USER, "a", encoding="utf-8") as f:
            f.write(f"{args.gloss}\t{args.pos or guess_pos(args.gloss)}\t{' '.join(args.tokens)}\tuser\n")
        print(f"added {args.gloss} to {USER}")
    elif args.action == "path":
        print(USER)


def main(argv=None):
    p = argparse.ArgumentParser(prog="seraphim", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    from . import dialects

    def common(sp):
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--heresy", action="store_true", help="allow names of God as phonemes")
        sp.add_argument("-d", "--dialect", type=_dialect, metavar="NAME",
                        help="seraphic (default), demonic or succubus; aliases: " + ", ".join(sorted(dialects.ALIASES)))

    def knob_opts(sp):
        g = sp.add_argument_group("voice and dialect tuning (0 = off; defaults come from the dialect)")
        for k, h in KNOB_HELP.items():
            g.add_argument(f"--{k}", type=float, metavar="N", help=h)
        from .fx import ROOMS
        r = sp.add_argument_group("reverb")
        r.add_argument("--room", choices=list(ROOMS),
                       help="reverb preset; 'clip' matches source-materials/video_2026-10-22_02-40-39.mp4 (default cathedral)")
        r.add_argument("--reverb", type=float, metavar="N", help="wet amount: 1 = the room's normal level, 0 = dry, 2 = drenched")
        r.add_argument("--reverb-time", type=float, metavar="S", help="decay time (RT60) in seconds, overriding the room")
        r.add_argument("--reverb-tone", type=float, metavar="N", help="tail colour: 0 bright .. 1 dark")
        r.add_argument("--predelay", type=float, metavar="MS", help="gap before the tail starts, in milliseconds")
        sp.add_argument("-j", "--jobs", type=int, default=0, help="parallel workers (0 = one per core, 1 = no parallelism)")

    sp = sub.add_parser("synth", help="render a .sera score to WAV")
    sp.add_argument("score")
    sp.add_argument("-o", "--output", help="WAV to write (default seraphim.wav unless --play)")
    sp.add_argument("-p", "--play", action="store_true", help="play it through the speakers")
    sp.add_argument("--stems", metavar="DIR", help="also write each voice dry")
    sp.add_argument("--no-choir", action="store_true", help="skip the three praise voices")
    sp.add_argument("--no-space", action="store_true", help="plain stereo instead of binaural")
    sp.add_argument("--reverse-4d", action="store_true", help="play 4D-moved morphemes backwards")
    sp.add_argument("--choir-level", type=float)
    sp.add_argument("--tempo", type=float, help="speed factor, e.g. 1.3 (overrides the score's @tempo)")
    sp.add_argument("--glitter", type=float, default=1.0, help="extra-bright glitter level (0 = off)")
    sp.add_argument("--hum", type=float, default=0.3, help="closed/null mouths hum at this level (0 = silent, as in the video)")
    sp.add_argument("-v", "--voice", type=_voice, help=VOICE_HELP)
    knob_opts(sp)
    sp.add_argument("-q", "--quiet", action="store_true")
    common(sp)
    sp.set_defaults(func=cmd_synth)

    sp = sub.add_parser("check", help="analyse a score: gematria, phonemes, syllables, rule breaks")
    sp.add_argument("score")
    common(sp)
    sp.set_defaults(func=cmd_check)

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
    sp.set_defaults(func=cmd_translate)

    sp = sub.add_parser("gloss", help="gloss line -> Seraphim, e.g. 'NPFV NEG.ever 1S comprehend-OBJ ABS-Aghma_Shwa CON-allure'")
    sp.add_argument("gloss", nargs="+", help="morphemes; separate sentences with //")
    sp.add_argument("--tense", default="nonpast", help="farpast | gnomic | nearpast | nonpast, stackable with +")
    lang_opts(sp)
    sp.set_defaults(func=cmd_gloss)

    sp = sub.add_parser("read", help="Seraphim score -> gloss -> rough English")
    sp.add_argument("score")
    common(sp)
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
    sp.set_defaults(func=cmd_lexicon)

    args = p.parse_args(argv)
    try:
        args.func(args)
    except ScoreError as e:
        sys.exit(f"seraphim: {e}")


if __name__ == "__main__":
    main()
