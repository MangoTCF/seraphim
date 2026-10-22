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
import os
import random
import unicodedata
from dataclasses import dataclass

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
        self._load(DATA, "builtin")
        if user_path and os.path.exists(user_path):
            self._load(user_path, None)

    def _load(self, path, default_source):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip() or line.startswith("#"):
                    continue
                parts = line.rstrip("\n").split("\t")
                gloss, pos, toks = parts[0], parts[1], parts[2]
                source = parts[3] if len(parts) > 3 else (default_source or "user")
                old = self.entries.get(gloss)
                if old and source == "coined" and old.source != "coined":
                    continue    # a built-in entry beats an automatic coinage
                self.entries[gloss] = Entry(gloss, pos, toks.split(), source)

    def by_signature(self):
        index = {}
        for e in self.entries.values():
            index.setdefault(e.signature, e)
        return index

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
        pos = pos or guess_pos(gloss)
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
        self.entries[gloss] = entry
        if self.save and self.user_path:
            os.makedirs(os.path.dirname(self.user_path), exist_ok=True)
            with open(self.user_path, "a", encoding="utf-8") as f:
                f.write(f"{gloss}\t{pos}\t{' '.join(toks)}\tcoined\n")
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
        options = [w for w in self.bank.get(value, []) + hebrew.spell(value, limit=6)
                   if w != text and hebrew.phoneme_value(w) == value]
        return self.rng.choice(options) + marks if options else token


def check_tokens(tokens):
    for t in tokens:
        try:
            parse_token(t)
        except ScoreError as e:
            raise ScoreError(f"lexicon token {t!r}: {e}") from None
