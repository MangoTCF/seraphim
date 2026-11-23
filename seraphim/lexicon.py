"""Morpheme lexicon: gloss -> Seraphim phoneme strings.

Entries recovered from Babelingua's demonstration are built in. Anything else
is coined on demand the way a clever angel would: each needed phoneme is
spelled with a real word from a Hebrew prayer whose gematria gives it.
Coined entries are saved to the user lexicon so they stay stable and can be
decoded again later.

Matching for decoding goes by phoneme values and brightness, never spelling:
only gematria is phonemic, so אדב and בדא are the same morpheme.
"""

import hashlib
import json
import os
import random
import tempfile
import unicodedata
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache

from . import hebrew
from .score import parse_token, ScoreError

DATA = os.path.join(os.path.dirname(__file__), "data", "lexicon.tsv")
USER = os.path.join(os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")), "seraphim", "lexicon.tsv")

# Unpointed words from the Shema, the Kedusha, Aleinu, Psalm 150, the priestly
# blessing and Adon Olam. Divine names are filtered out below.
PRAYER_TEXT = """
שמע ישראל אחד ברוך שם כבוד מלכותו לעולם ועד ואהבת את בכל לבבך ובכל נפשך ובכל מאדך
והיו הדברים האלה אשר אנכי מצוך היום על לבבך ושננתם לבניך ודברת בם בשבתך בביתך ובלכתך בדרך
ובשכבך ובקומך וקשרתם לאות על ידך והיו לטטפת בין עיניך וכתבתם על מזזות ביתך ובשעריך
קדוש קדוש קדוש מלא כל הארץ כבודו ברוך כבוד ממקומו ימלך לעולם אלהיך ציון לדר ודר
עלינו לשבח לאדון הכל לתת גדלה ליוצר בראשית שלא עשנו כגויי הארצות ולא שמנו כמשפחות האדמה
הללו בקדשו הללוהו ברקיע עזו בגבורתיו כרב גדלו בתקע שופר בנבל וכנור בתף ומחול במנים ועוגב
בצלצלי שמע תרועה כל הנשמה תהלל יברכך וישמרך יאר פניו אליך ויחנך ישא וישם לך שלום
אדון עולם אשר מלך בטרם כל יציר נברא לעת נעשה בחפצו כל אזי מלך שמו נקרא ואחרי ככלות הכל לבדו
ימלוך נורא והוא היה והוא הווה והוא יהיה בתפארה והוא אחד ואין שני להמשיל לו להחבירה בלי ראשית
בלי תכלית ולו העז והמשרה והוא אלי וחי גואלי וצור חבלי בעת צרה והוא נסי ומנוס לי מנת כוסי ביום
אקרא בידו אפקיד רוחי בעת אישן ואעירה ועם רוחי גויתי לי ולא אירא אמן
רעי לא אחסר בנאות דשא ירביצני על מי מנחות ינהלני נפשי ישובב ינחני במעגלי צדק למען שמו
גם כי אלך בגיא צלמות לא אירא רע כי אתה עמדי שבטך ומשענתך המה ינחמני תערך לפני שלחן נגד צררי
דשנת בשמן ראשי כוסי רויה אך טוב וחסד ירדפוני כל ימי חיי ושבתי בבית לארך ימים
אשא עיני ההרים מאין יבא עזרי עזרי מעם עשה שמים וארץ ישב בסתר עליון בצל יתלונן
ישקני מנשיקות פיהו כי טובים דדיך מיין לריח שמניך טובים שמן תורק שמך על כן עלמות אהבוך
משכני אחריך נרוצה הביאני המלך חדריו נגילה ונשמחה בך נזכירה דדיך מיין דודי לי ואני לו הרעה בשושנים
לבבתני אחתי כלה לבבתיני באחת מעיניך באחד ענק מצורניך מה יפו דדיך מה טבו דדיך מיין
שימני כחותם על לבך כחותם על זרועך כי עזה כמות אהבה קשה כשאול קנאה רשפיה רשפי אש
מים רבים לא יוכלו לכבות את האהבה ונהרות לא ישטפוה
"""

BANNED_SUBSTRINGS = ("יהוה", "אלה", "אלוה", "שדי", "אדני", "צבאות")


def _prayer_bank():
    bank = {}
    for w in PRAYER_TEXT.split():
        w = hebrew.letters(w)
        if not w or hebrew.is_divine_name(w) or any(b in w for b in BANNED_SUBSTRINGS):
            continue
        bank.setdefault(hebrew.phoneme_value(w), []).append(w)
    return {k: sorted(set(v), key=lambda x: (len(x), x)) for k, v in bank.items()}


BANK = _prayer_bank()


def _heretic_bank():
    """For dialects that allow heresy: nothing filtered, names of God included."""
    bank = {}
    for w in set(map(hebrew.letters, PRAYER_TEXT.split())) | hebrew.DIVINE_NAMES:
        if w:
            bank.setdefault(hebrew.phoneme_value(w), []).append(w)
    return {k: sorted(set(v), key=lambda x: (len(x), x)) for k, v in bank.items()}


HERETIC_BANK = _heretic_bank()

GRAMMATICAL_POS = {
    "COMP": "COMP", "PERF": "T", "NPFV": "T", "PFV": "T", "PROG": "T", "HAB": "T",
    "NEG": "NEG", "START": "-",
}
PRONOUNS = {"1S", "2S", "3S", "1P", "2P", "3P", "3N", "THIS", "THAT"}
# The categories a lexicon entry may declare. Grammar categories are the same
# minus the two meta-values: '-' for pro-form morphemes and 'PRON', which the
# grammar treats as a noun.
POS_VALUES = {"-", "N", "V", "ADJ", "ADV", "K", "T", "NEG", "COMP", "CONJ", "INTJ", "PRON"}


class LexiconError(ScoreError):
    """A malformed or impossible lexicon entry."""


@dataclass
class Entry:
    gloss: str
    pos: str
    tokens: list        # .sera token strings
    source: str

    @property
    def signature(self):
        return signature(self.tokens)


def signature(tokens):
    """Phonemic identity of a token sequence: value, class and brightness."""
    return _signature(tuple(tokens))


@lru_cache(maxsize=8192)
def _signature(tokens):
    sig = []
    for t in tokens:
        tok = parse_token(t, heresy=True)
        if tok.kind == "break":
            continue
        sig.append((tok.value, tok.cls, tok.brightness))
    return tuple(sig)


def guess_pos(gloss):
    if gloss in GRAMMATICAL_POS:
        return GRAMMATICAL_POS[gloss]
    if gloss.startswith("PRO:"):
        return "-"
    if gloss.endswith("-"):
        return "K"
    if gloss.startswith("-"):
        return "V"
    if gloss in PRONOUNS:
        return "PRON"
    return "N"


class Lexicon:
    def __init__(self, user_path=USER, save=True):
        self.entries = {}
        self.user_path = user_path
        self.save = save
        self._user_glosses = set()
        self._load(DATA, "builtin")
        self._builtin_entries = dict(self.entries)
        if user_path and os.path.exists(user_path):
            self._load(user_path, None)

    def _load(self, path, default_source):
        with open(path, encoding="utf-8") as f:
            for ln, line in enumerate(f, 1):
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                parts = line.rstrip("\r\n").split("\t")
                if len(parts) not in (3, 4):
                    raise LexiconError(
                        f"{path}: line {ln}: expected 'gloss<TAB>pos<TAB>tokens', "
                        f"got {line.rstrip()!r}")
                gloss, pos, toks = (p.strip() for p in parts[:3])
                if not gloss:
                    raise LexiconError(f"{path}: line {ln}: empty gloss")
                if pos not in POS_VALUES:
                    raise LexiconError(
                        f"{path}: line {ln}: unknown part of speech {pos!r} for {gloss!r}; "
                        f"known: {', '.join(sorted(POS_VALUES))}")
                tokens = toks.split()
                if not tokens:
                    raise LexiconError(f"{path}: line {ln}: {gloss!r} has no tokens")
                try:
                    validate_entry(gloss, pos, tokens)
                except LexiconError as e:
                    raise LexiconError(f"{path}: line {ln}: {e}") from None
                source = parts[3].strip() if len(parts) > 3 and parts[3].strip() else (default_source or "user")
                old = self.entries.get(gloss)
                if old and source == "coined" and old.source != "coined":
                    continue    # a built-in entry beats an automatic coinage
                self.entries[gloss] = Entry(gloss, pos, tokens, source)
                if default_source is None:
                    self._user_glosses.add(gloss)
        try:
            self.by_signature()   # reject ambiguous dictionaries at the boundary
        except LexiconError as e:
            raise LexiconError(f"{path}: {e}") from None

    def by_signature(self):
        index = {}
        for e in self.entries.values():
            sig = e.signature
            if sig in index:
                raise LexiconError(f"phonemic collision: {e.gloss!r} and {index[sig].gloss!r}")
            index[sig] = e
        return index

    def dependencies(self, gloss):
        """Entries used to spell a gloss, including compound components."""
        if gloss in self.entries:
            return {gloss}
        for sep in (".", "-"):
            inner = gloss.strip("-")
            if sep in inner and not gloss.startswith("PRO:"):
                parts = [p for p in inner.split(sep) if p]
                if len(parts) > 1:
                    return set().union(*(self.dependencies(p) for p in parts))
        return set()

    def add(self, gloss, pos, tokens, *, replace=False, source="user"):
        validate_entry(gloss, pos, tokens)
        if not self.user_path:
            raise LexiconError("no user lexicon path configured")
        with _locked(self.user_path):
            current = Lexicon(self.user_path, save=False)
            old = current.entries.get(gloss)
            if old and gloss in current._user_glosses and not replace:
                raise LexiconError(f"{gloss!r} already exists; pass --replace to overwrite it")
            current.entries[gloss] = Entry(gloss, pos, list(tokens), source)
            current.by_signature()
            current._write_user()
            self.entries = current.entries
        return self.entries[gloss]

    def _write_user(self):
        directory = os.path.dirname(os.path.abspath(self.user_path))
        comments = []
        if os.path.exists(self.user_path):
            with open(self.user_path, encoding="utf-8") as original:
                comments = [line for line in original if not line.strip() or line.lstrip().startswith("#")]
        fd, temporary = tempfile.mkstemp(prefix=".lexicon-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                for line in comments:
                    f.write(line.rstrip("\r\n") + "\n")
                for e in self.entries.values():
                    if e != self._builtin_entries.get(e.gloss):
                        f.write(f"{e.gloss}\t{e.pos}\t{' '.join(e.tokens)}\t{e.source}\n")
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, self.user_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def get(self, gloss, pos=None):
        if gloss in self.entries:
            return self.entries[gloss]
        return self.coin(gloss, pos)

    def tokens(self, gloss, pos=None):
        """Tokens for a gloss; compounds joined with '.' or '-' are built from
        their parts when the whole isn't listed."""
        if gloss in self.entries:
            return list(self.entries[gloss].tokens)
        for sep, joiner in ((".", []), ("-", ["-"])):
            inner = gloss.strip("-")
            if sep in inner and not gloss.startswith("PRO:"):
                parts = [p for p in inner.split(sep) if p]
                if len(parts) > 1:
                    out = []
                    for i, p in enumerate(parts):
                        if i:
                            out += joiner
                        out += self.tokens(p, pos if i == 0 else None)
                    return out
        return list(self.coin(gloss, pos).tokens)

    # ------------------------------------------------------------ coining

    def coin(self, gloss, pos=None):
        if self.save and self.user_path:
            # Reload and choose while holding the same lock: two processes
            # must not allocate colliding words from stale snapshots.
            with _locked(self.user_path):
                current = Lexicon(self.user_path, save=False)
                entry = current.get(gloss, pos)
                current._write_user()
                self.entries = current.entries
                return entry
        pos = pos or guess_pos(gloss)
        validate_entry(gloss, pos, ["א☀"])
        taken = set(self.by_signature())
        grammatical = pos not in ("N", "V", "ADJ", "ADV") or gloss.isupper()
        for attempt in range(200):
            seed = int(hashlib.sha256(f"{gloss}#{attempt}".encode()).hexdigest()[:12], 16)
            rng = random.Random(seed)
            n_syll = 1 if grammatical else rng.choice((1, 2, 2, 3))
            toks = []
            for _ in range(n_syll):
                toks += self._syllable(rng)
            entry = Entry(gloss, pos, toks, "coined")
            if entry.signature not in taken:
                break
        else:
            raise LexiconError(f"could not coin {gloss!r}: every candidate collides with an existing entry")
        self.entries[gloss] = entry
        return entry

    def _syllable(self, rng):
        shape = rng.choice(("CV", "CV", "CVC", "CVC", "CCV", "VC"))
        out = []
        for slot in shape:
            if slot == "C":
                value = rng.choice([v for v in hebrew.CONSONANT_VALUES if v not in hebrew.AMBIGUOUS_VALUES])
                out.append(self._spell(value, rng))
            else:
                value = rng.choice(hebrew.VOWEL_VALUES)
                mark = rng.choices(["☀", "🔆", "☢"], weights=(6, 3, 2))[0]
                out.append(self._spell(value, rng) + mark)
        return out

    def _spell(self, value, rng):
        """Prefer a prayer word that spells the phoneme; else any string."""
        words = BANK.get(value)
        if words:
            return rng.choice(words[:12])
        options = hebrew.spell(value, limit=5)
        return rng.choice(options)


class Varier:
    """Free variation in spelling. Only gematria is phonemic, so every string
    with the same phoneme value is the same phoneme. The first time a spelling
    appears it is kept; after that each repeat is respelled with another
    prayer word of the same value (and the same brightness, which keeps
    ambiguous /1/ and /3/ in the same class). Meaning and decoding are
    unchanged; it just stops every word saying אלוקים."""

    def __init__(self, seed=0, heresy=False):
        self.rng = random.Random(seed)
        self.seen = set()
        self.bank = HERETIC_BANK if heresy else BANK

    def __call__(self, tokens):
        return [self.respell(t) for t in tokens]

    def respell(self, token):
        from .score import _split_marks
        if token in ("-", "–", "|"):
            return token
        text, _ = _split_marks(token)
        marks = token.replace("\ufe0f", "")[len(text):]
        if text not in self.seen or any(unicodedata.category(c) == "Mn" for c in text):
            self.seen.add(text)
            return token        # first use, or pointed Hebrew: keep as written
        value = hebrew.phoneme_value(text)
        candidates = [w for w in self.bank.get(value, []) + hebrew.spell(value, limit=6)
                      if w != text and hebrew.phoneme_value(w) == value]
        options = [w for w in candidates if w not in self.seen]
        if not options:
            options = candidates       # all alternates used; allow repeats
        if not options:
            return token
        chosen = self.rng.choice(options)
        self.seen.add(chosen)          # don't repeat an alternate spelling either
        return chosen + marks


def check_tokens(tokens, heresy=False):
    if not tokens:
        raise LexiconError("an entry needs at least one token")
    for t in tokens:
        try:
            parse_token(t, heresy=heresy, rng=random.Random(0))
        except ScoreError as e:
            raise LexiconError(f"lexicon token {t!r}: {e}") from None
    if not signature(tokens):
        raise LexiconError("an entry needs at least one phoneme")


def validate_entry(gloss, pos, tokens):
    if not isinstance(gloss, str) or not gloss or any(c.isspace() or c == "#" for c in gloss):
        raise LexiconError("a gloss must be a nonempty word without whitespace or '#'")
    if pos not in POS_VALUES:
        raise LexiconError(f"unknown part of speech {pos!r}")
    if not isinstance(tokens, list) or not all(isinstance(t, str) and not any(c.isspace() or c == "#" for c in t) for t in tokens):
        raise LexiconError("tokens must be a list of words without whitespace or '#'")
    check_tokens(tokens, heresy=True)


@contextmanager
def _locked(path):
    import fcntl
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path + ".lock", "a", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def snapshot_json(entries):
    return json.dumps(entries, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def snapshot_hash(entries):
    return hashlib.sha256(snapshot_json(entries).encode()).hexdigest()


def score_lexicon(score, fallback=None):
    """Embedded vocabulary wins; a portable score never loads ambient state."""
    if not score.lexicon:
        return fallback if fallback is not None else Lexicon(save=False)
    lx = Lexicon(user_path=None, save=False)
    # The snapshot already includes every dependency. Unused builtins could
    # otherwise change segmentation as the installed dictionary evolves.
    lx.entries = {}
    for g, e in score.lexicon.items():
        lx.entries[g] = Entry(g, e["pos"], list(e["tokens"]), "embedded")
    lx.by_signature()
    return lx
