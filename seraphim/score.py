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


@dataclass
class Score:
    meta: dict
    words: list


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
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        s = line.strip()
        if s.startswith("@"):
            k, _, v = s[1:].partition(":")
            k = k.strip().lower()
            if k == "dialect" and dialect:
                continue            # the command line wins
            meta[k] = v.strip()
            if k == "dialect":
                try:
                    heresy = heresy or dialects.get(meta[k]).heresy
                except ValueError as e:
                    raise ScoreError(f"line {ln}: {e}") from None
            continue
        if s == "---":
            sentence_start = True
            continue
        if s.split()[0].lower() == "word":
            args = s.split()[1:]
            langs = None
            if args:
                langs = []
                for t in args[0].lower().split("+"):
                    if t not in TENSE_LANG:
                        raise ScoreError(f"line {ln}: unknown tense {t!r}")
                    langs.append(TENSE_LANG[t])
            elif words:
                langs = list(words[-1].langs)   # tense carries over from the previous word
            else:
                langs = [TENSE_LANG[meta["tense"].lower()]]
            cur = Word(langs, {m: MouthLine() for m in MOUTHS}, ln, sentence_start)
            sentence_start = False
            words.append(cur)
            continue
        label, sep, body = s.partition(":")
        if not sep or label.strip().lower() not in MOUTH_ALIASES:
            raise ScoreError(f"line {ln}: expected 'word', '@key: value' or '<mouth>: ...', got {s!r}")
        if cur is None:
            raise ScoreError(f"line {ln}: mouth line before any 'word'")
        mouth = MOUTH_ALIASES[label.strip().lower()]
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
    return Score(meta, words)


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
