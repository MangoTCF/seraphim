"""Parser and rule checker for .sera score files.

    @title: Never, from the far past onward...
    @tense: nonpast

    word nonpast
      top: אלוקים הבא☀
      1:   Ø
      2:   הדסא חכּז☀
      end: אלוקים☢ אלוקים

    word farpast+nonpast
      1:   ~ אדּב לכּד☀ - בורא אלוקים☀ וו אלוקים☀

Mouths: top, 1, 2, end. `Ø`/`_`/missing = silent; a leading `~` marks a
4D-moved line (closed mouth, sound appears in front of it). `-` is a morpheme
break. `/45/` spells phoneme 45 automatically. Brightness marks after a
token: ☀ or * bright, 🔆 or ☀☀ or ** extra bright, ☢ or ! ionized.
A line `---` separates sentences.
"""

import math
import json
import random
import re
from dataclasses import dataclass, field

from . import hebrew

MOUTHS = ("top", "1", "2", "end")
MOUTH_ALIASES = {"top": "top", "t": "top", "1": "1", "one": "1", "2": "2", "two": "2", "end": "end", "e": "end"}

TENSE_LANG = {
    "farpast": "aramaic", "fpst": "aramaic", "gnomic": "aramaic", "gnom": "aramaic",
    "nearpast": "greek", "pst": "greek", "past": "greek",
    "nonpast": "latin", "npres": "latin", "npst": "latin", "present": "latin",
    "pres": "latin", "future": "latin",
    "aramaic": "aramaic", "greek": "greek", "latin": "latin",
}

# Preserve grammatical distinctions even when two tenses share a prayer language.
TENSE_CANONICAL = {
    'fpst': 'farpast', 'gnom': 'gnomic', 'pst': 'nearpast', 'past': 'nearpast',
    'npres': 'nonpast', 'npst': 'nonpast', 'present': 'nonpast', 'pres': 'nonpast',
    'future': 'nonpast', 'latin': 'nonpast', 'greek': 'nearpast',
    # An old language-only label cannot distinguish gnomic from far past.
    'aramaic': 'aramaic',
}


def tense_names(value):
    return [TENSE_CANONICAL.get(t.lower(), t.lower()) for t in value.split('+')]


def temporal_meaning(tenses):
    names = list(dict.fromkeys(tenses))
    if not names:
        return 'Tense unspecified.'
    labels = {'farpast': 'far past', 'nearpast': 'near past', 'nonpast': 'non-past',
              'gnomic': 'timeless / general truth', 'aramaic': 'Aramaic (far past or gnomic unspecified)'}
    text = ' and '.join(labels.get(t, t) for t in names)
    return ('Applies jointly in ' if len(names) > 1 else 'Applies in ') + text + (
        '; stacking alone does not assert continuous duration or uncertainty.' if len(names) > 1 else '.')

BRIGHT, EXTRA, IONIZED = 1, 2, 3
BRIGHTNESS_NAMES = {0: "-", BRIGHT: "bright", EXTRA: "extra bright", IONIZED: "ionized"}
_MARKS = [("☀☀", EXTRA), ("🔆", EXTRA), ("**", EXTRA), ("☢", IONIZED), ("!", IONIZED), ("☀", BRIGHT), ("☼", BRIGHT), ("*", BRIGHT)]
SILENT = {"Ø", "ø", "_", "∅", "t.", ""}


class ScoreError(Exception):
    pass


@dataclass
class Token:
    text: str
    kind: str = "phoneme"        # phoneme | break
    value: int = None
    cls: str = None              # V | C
    brightness: int = 0
    ipa: list = field(default_factory=list)
    notes: list = field(default_factory=list)


@dataclass
class MouthLine:
    tokens: list = field(default_factory=list)
    moved: bool = False
    syllables: str = ""

    @property
    def silent(self):
        return not any(t.kind == "phoneme" for t in self.tokens)


@dataclass
class Word:
    langs: list
    mouths: dict
    line: int
    sentence_start: bool = False
    tones: dict = field(default_factory=dict)    # tonal markers: {"pain": 0.9, ...}
    stammer: bool = False
    tenses: list = field(default_factory=list)  # exact effective tense, separate from prayer language


@dataclass
class Score:
    meta: dict
    words: list
    lexicon: dict = field(default_factory=dict)


def _split_marks(tok):
    tok = tok.replace("️", "")
    level = 0
    changed = True
    while changed:
        changed = False
        for m, lv in _MARKS:
            if tok.endswith(m) and len(tok) > len(m):
                tok = tok[: -len(m)]
                level = max(level, lv)
                changed = True
                break
    return tok, level


TONES = ("pain", "scream", "anger", "fear", "whimper", "condescend", "neutral")
TONE_ALIASES = {"command": "anger", "rage": "anger", "terror": "fear", "tremble": "fear",
                "smug": "condescend", "haughty": "condescend", "patronizing": "condescend",
                "patronising": "condescend", "condescending": "condescend", "none": "neutral",
                "agony": "scream", "sob": "whimper", "hurt": "pain"}


def parse_tones(spec):
    """'pain:0.9,scream' -> {'pain': 0.9, 'scream': 1.0}."""
    out = {}
    for part in str(spec).replace(" ", "").split(","):
        if not part:
            continue
        name, _, val = part.partition(":")
        name = TONE_ALIASES.get(name.lower(), name.lower())
        if name not in TONES:
            raise ValueError(f"unknown tone {name!r}; known: {', '.join(TONES)}")
        v = float(val) if val else 1.0
        if not 0 <= v <= 1:
            raise ValueError(f"tone {name} intensity {v} is outside 0..1")
        out[name] = v
    return out


def _meta_number(key, value, ln, *, positive=False, unit=False, signed=False):
    try:
        x = float(value)
    except ValueError:
        raise ScoreError(f"line {ln}: @{key} must be a number, got {value!r}") from None
    if not math.isfinite(x):
        raise ScoreError(f"line {ln}: @{key} must be finite, got {value!r}")
    if positive and x <= 0:
        raise ScoreError(f"line {ln}: @{key} must be greater than 0")
    if not positive and not signed and x < 0:
        raise ScoreError(f"line {ln}: @{key} must not be negative")
    if unit and not 0 <= x <= 1:
        raise ScoreError(f"line {ln}: @{key} must be between 0 and 1")
    return x


def validate_meta(key, value, ln):
    """Reject bad @metadata while parsing, so check and synth agree."""
    key = key.lower()
    v = value.strip()
    if key in ("title", "lexicon_hash"):
        return
    if key == "format":
        if v != "1":
            raise ScoreError(f"line {ln}: unsupported score format {v!r}")
    elif key == "lexicon":
        from .lexicon import validate_entry
        try:
            entries = json.loads(v)
            if not isinstance(entries, dict):
                raise ValueError("expected an object of glosses")
            for g, entry in entries.items():
                if not isinstance(entry, dict) or set(entry) != {"pos", "tokens"}:
                    raise ValueError(f"invalid entry for {g!r}")
                validate_entry(g, entry["pos"], entry["tokens"])
        except (ValueError, TypeError, ScoreError) as e:
            raise ScoreError(f"line {ln}: @lexicon: {e}") from None
    elif key == "tense":
        t = v.lower()
        if "+" in t:
            raise ScoreError(f"line {ln}: @tense does not stack; write 'word farpast+nonpast' instead")
        if t not in TENSE_LANG:
            known = ", ".join(sorted(TENSE_LANG))
            raise ScoreError(f"line {ln}: unknown tense {v!r}; known: {known}")
    elif key == "tempo":
        _meta_number(key, v, ln, positive=True)
    elif key == "tone":
        try:
            parse_tones(v)
        except ValueError as e:
            raise ScoreError(f"line {ln}: @tone: {e}") from None
    elif key == "reading":
        if v not in ("matres", "demo"):
            raise ScoreError(f"line {ln}: unknown reading {v!r}; known: matres, demo")
    elif key == "begadkefat":
        if v not in ("soft", "hard"):
            raise ScoreError(f"line {ln}: unknown begadkefat {v!r}; known: soft, hard")
    elif key == "dialect":
        from . import dialects
        try:
            dialects.get(v)
        except ValueError as e:
            raise ScoreError(f"line {ln}: {e}") from None
    elif key == "room":
        from .fx import ROOMS
        if v not in ROOMS:
            raise ScoreError(f"line {ln}: unknown room {v!r}; known: {', '.join(ROOMS)}")
    elif key == "voice":
        from .render import parse_voice
        try:
            parse_voice(v)
        except ValueError as e:
            raise ScoreError(f"line {ln}: @voice: {e}") from None
    elif key == "reverb":
        _meta_number(key, v, ln)
    elif key == "reverb_time":
        _meta_number(key, v, ln)
    elif key == "reverb_tone":
        _meta_number(key, v, ln, unit=True)
    elif key == "predelay":
        _meta_number(key, v, ln)
    else:
        from . import dialects
        if key in dialects.KNOBS:
            if key in ("pitch", "gender"):
                x = _meta_number(key, v, ln, signed=True)
                if key == "gender" and not -1 <= x <= 1:
                    raise ScoreError(f"line {ln}: @gender must be between -1 and 1")
            else:
                _meta_number(key, v, ln, unit=True)
        else:
            raise ScoreError(f"line {ln}: unknown metadata @{key}")


def parse_token(raw, begadkefat="soft", rng=None, heresy=False, reading="matres"):
    if raw in ("-", "–", "|"):
        return Token(raw, kind="break")
    text, level = _split_marks(raw)
    m = re.fullmatch(r"/(\d+)/", text)
    tok = Token(raw, brightness=level)
    if m:
        value = int(m.group(1))
        options = hebrew.spell(value, limit=4)
        if not options:
            raise ScoreError(f"cannot spell phoneme /{value}/")
        text = (rng or random).choice(options)
        tok.notes.append(f"· /{value}/ spelled as {text}")
    if not hebrew.letters(text):
        raise ScoreError(f"token {raw!r} has no Hebrew letters")
    if hebrew.is_divine_name(text):
        msg = f"{text} is a name of God and may not be used as a phoneme"
        if not heresy:
            raise ScoreError(msg + " (pass --heresy, or --dialect=demonic if you are a fallen angel)")
        tok.notes.append(f"· heresy: {text} is a name of God, used as a phoneme (this dialect allows it)")
    tok.text = text
    tok.value = hebrew.phoneme_value(text)
    tok.cls = hebrew.classify(tok.value, level > 0)
    total = hebrew.gematria(text)
    if total != tok.value:
        tok.notes.append(f"· sum {total} is not a phoneme, first letter gives /{tok.value}/")
    if tok.cls == "V" and level == 0:
        tok.brightness = BRIGHT
        tok.notes.append("· vowel without brightness, assuming bright")
    if tok.cls == "C" and level > 0:
        tok.notes.append("brightness mark on a consonant")
    tok.ipa = hebrew.to_ipa(text, begadkefat, reading)
    return tok


SYLLABLE_SHAPES = ("CCVC", "CCV", "CVC", "CV", "VC", "C")


def syllabify(classes):
    """Best split of a C/V string into (C)(C)V(C) syllables with at least one
    consonant each, using as few syllabic consonants as possible.
    Returns the dotted split, or None if the vowels can't all be housed."""
    s = "".join(classes)
    best = {0: (0, [])}
    for i in range(len(s)):
        if i not in best:
            continue
        cost, parts = best[i]
        for shape in SYLLABLE_SHAPES:
            if s.startswith(shape, i):
                j = i + len(shape)
                c = cost + (shape == "C")
                if j not in best or c < best[j][0]:
                    best[j] = (c, parts + [shape])
    return ".".join(best[len(s)][1]) if len(s) in best else None


def parse(text, heresy=False, seed=0, dialect=None):
    """dialect (from the command line) beats the score's own @dialect; a
    heretical dialect allows names of God as phonemes."""
    from . import dialects
    rng = random.Random(seed)
    meta = {"tense": "nonpast", "tempo": "1.0", "begadkefat": "soft", "dialect": "seraphic", "reading": "matres"}
    if dialect:
        meta["dialect"] = dialect
        heresy = heresy or dialects.get(dialect).heresy
    words = []
    cur = None
    sentence_start = True
    seen_mouths = set()
    for ln, line in enumerate(text.splitlines(), 1):
        # JSON strings may contain '#'; generated snapshots escape Hebrew
        # and remain single-line, but user-entered JSON is valid too.
        line = line.rstrip() if line.lstrip().startswith("@lexicon:") else line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        s = line.strip()
        if s.startswith("@"):
            if words:
                raise ScoreError(f"line {ln}: score metadata must precede words")
            k, _, v = s[1:].partition(":")
            k = k.strip().lower()
            if k == "dialect" and dialect:
                continue            # the command line wins
            meta[k] = v.strip()
            validate_meta(k, meta[k], ln)
            if k == "dialect":
                heresy = heresy or dialects.get(meta[k]).heresy
            continue
        if s == "---":
            sentence_start = True
            continue
        if s.split()[0].lower() == "word":
            args = s.split()[1:]
            langs = None
            tenses = None
            tones, stammer = {}, False
            if args and not args[0].startswith("tone=") and args[0] != "stammer":
                langs = []
                tense_spec = args.pop(0).lower()
                tenses = tense_names(tense_spec)
                for t in tense_spec.split("+"):
                    if t not in TENSE_LANG:
                        raise ScoreError(f"line {ln}: unknown tense {t!r}")
                    langs.append(TENSE_LANG[t])
            for a in args:
                if a == "stammer":
                    stammer = True
                elif a.startswith("tone="):
                    try:
                        tones = parse_tones(a[5:])
                    except ValueError as e:
                        raise ScoreError(f"line {ln}: {e}") from None
                else:
                    raise ScoreError(f"line {ln}: unknown word option {a!r} (expected tone=… or stammer)")
            if langs is None:
                if words:
                    tenses = list(words[-1].tenses)
                    langs = list(words[-1].langs)   # tense carries over from the previous word
                else:
                    tenses = tense_names(meta["tense"])
                    langs = [TENSE_LANG[meta["tense"].lower()]]
            cur = Word(langs, {m: MouthLine() for m in MOUTHS}, ln, sentence_start, tones, stammer, tenses)
            sentence_start = False
            words.append(cur)
            seen_mouths = set()
            continue
        label, sep, body = s.partition(":")
        if not sep or label.strip().lower() not in MOUTH_ALIASES:
            raise ScoreError(f"line {ln}: expected 'word', '@key: value' or '<mouth>: ...', got {s!r}")
        if cur is None:
            raise ScoreError(f"line {ln}: mouth line before any 'word'")
        mouth = MOUTH_ALIASES[label.strip().lower()]
        if mouth in seen_mouths:
            raise ScoreError(f"line {ln}: duplicate mouth {mouth!r}")
        seen_mouths.add(mouth)
        body = body.strip()
        ml = MouthLine()
        if body.startswith("~"):
            ml.moved = True
            body = body[1:].strip()
        if body in SILENT:
            cur.mouths[mouth] = ml
            continue
        try:
            ml.tokens = [parse_token(t, meta["begadkefat"], rng, heresy, meta["reading"]) for t in body.split()]
        except ScoreError as e:
            raise ScoreError(f"line {ln}: {e}") from None
        classes = [t.cls or "C" for t in ml.tokens if t.kind == "phoneme"]
        ml.syllables = syllabify(classes) or ""
        if not ml.syllables:
            ml.tokens[0].notes.append(f"line breaks the (C)(C)V(C) syllable rule: {''.join(classes)}")
        cur.mouths[mouth] = ml
    if not words:
        raise ScoreError("score has no words")
    entries = json.loads(meta.get("lexicon", "{}"))
    score = Score(meta, words, entries)
    if entries or "lexicon_hash" in meta:
        from .lexicon import score_lexicon, snapshot_hash
        if "lexicon_hash" in meta and meta["lexicon_hash"] != snapshot_hash(entries):
            raise ScoreError("embedded lexicon hash mismatch")
        score_lexicon(score)
    return score


def diagnostics(score):
    """Machine-readable phonological violations; informational notes omitted."""
    return [dict(word=i, line=w.line, mouth=m, token=t.text, message=n)
            for i, w in enumerate(score.words, 1) for m, ml in w.mouths.items()
            for t in ml.tokens for n in t.notes if not n.startswith("·")]


def report(score):
    """Human-readable analysis of every word and mouth."""
    out = []
    for wi, w in enumerate(score.words, 1):
        out.append(f"word {wi} (line {w.line})  choir: {' + '.join(w.langs)}")
        for m in MOUTHS:
            ml = w.mouths[m]
            if ml.silent:
                out.append(f"  {m:>3}: {'(moved, closed)' if ml.moved else 'silent'}")
                continue
            head = f"  {m:>3}: " + ("[4D-moved] " if ml.moved else "") + f"syllables {ml.syllables or 'INVALID'}"
            out.append(head)
            for t in ml.tokens:
                if t.kind == "break":
                    out.append("         -  morpheme break")
                    continue
                ipa = "".join(t.ipa)
                br = BRIGHTNESS_NAMES[t.brightness] if t.cls == "V" or t.brightness else ""
                out.append(f"         {t.text:<8} Σ={hebrew.gematria(t.text):<5} /{t.value}/ {t.cls or '?'} [{ipa}] {br}")
                for n in t.notes:
                    out.append(f"             {n}" if n.startswith("·") else f"             ! {n}")
    return "\n".join(out)
