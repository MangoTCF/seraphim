"""Seraphim morphosyntax: from a gloss to spoken words and back.

Microsyntax (word-internal). A clause is a right-branching tree whose left
daughters are the terminals:  CP[Ø TP[Ø T'[NPFV NegP[NEG vP[1S v'[comprehend
VP[-OBJ KP[ABS- NP[Aghma_Shwa KP[CON- NP[allure]]]]]]]]]]. Each Seraphim word
takes the next two terminals: the top mouth says the pro-form of the current
phrase ('START' for the first word), mouths 1 and 2 say the terminals, and
the end mouth says a pro-phrase standing for the rest of the tree, which the
next word's top mouth then agrees with.

Macrosyntax (word-external). Words may be spoken in any order, but runs of
words sharing a phrase name stay together and in order. Earlier words are
more active ('the cheese caused the man to eat it').

4D V-to-T-to-C movement. After spell-out the aspect marker and the verb move
to the null C position and the subject to the null spec-TP, picking up
nominative case. The mouths stay closed; the sound appears in front of them.
The original positions are left as traces.

Tense is sung, not spoken. Marking a word for tense tenses everything after it
in the tree until another mark. Negative words are always marked.
"""

import random
import re
from dataclasses import dataclass, field

from .lexicon import Lexicon, PRONOUNS

ASPECTS = {"PERF", "NPFV", "NMPF", "PFV", "PROG", "HAB", "IMP", "IRR"}   # IMP, IRR: moods, extensions
CASES = {"NOM", "ABSV", "INS", "ABS", "CON", "DAT", "LOC", "ABL", "ALL", "TRAL", "VOC", "AVR", "BEN"}
TRANSITIVIZERS = {"OBJ", "BEN", "MAL", "INS", "DAT", "DIS", "ORN"}
PRO = {"COMP": "PRO:COMP", "T": "PRO:T", "NEG": "PRO:NEG", "V": "PRO:V", "K": "PRO:K",
       "N": "PRO:N", "ADJ": "PRO:ADJ", "ADV": "PRO:ADV", "CONJ": "PRO:CONJ", "INTJ": "PRO:INTJ"}
TENSES = ("farpast", "gnomic", "nearpast", "nonpast")
TENSE_ALIASES = {"fpst": "farpast", "gnom": "gnomic", "pst": "nearpast", "past": "nearpast",
                 "npst": "nonpast", "npres": "nonpast", "present": "nonpast"}


@dataclass
class Term:
    gloss: str
    cat: str                 # COMP T NEG V K N ADJ ADV
    role: str = ""           # c, spec, asp, subj, verb
    tense: list = None       # explicit tense mark on this terminal's word
    moved: bool = False
    trace: bool = False
    parts: list = None       # for moved slots: the original terms

    @property
    def silent(self):
        return self.gloss in ("Ø", "t") or self.trace


@dataclass
class SWord:
    top: str
    m1: Term = None
    m2: Term = None
    end: str = None
    tense: list = None        # explicit mark (i:) or None (u:)
    eff: list = None          # effective tense
    index: int = 0            # position in the tree


@dataclass
class Sentence:
    terms: list
    tense: list
    english: str = ""
    words: list = field(default_factory=list)
    order: list = field(default_factory=list)
    stages: list = field(default_factory=list)
    tones: dict = field(default_factory=dict)       # tonal markers for every word
    stammer: bool = False


# ------------------------------------------------------------ gloss parsing

def _norm_tense(t):
    t = t.lower()
    t = TENSE_ALIASES.get(t, t)
    if t not in TENSES:
        raise ValueError(f"unknown tense {t!r}")
    return t


def split_gloss(text):
    """'CON-begin-INS' -> ['CON-', 'begin', '-INS']; keeps ':POS' and '^tense'."""
    out = []
    for word in text.split():
        tense = None
        if "^" in word:
            word, _, tense = word.partition("^")
        parts = re.split(r"(?<=[^\s-])-(?=[^\s-])", word)
        pieces = []
        for i, p in enumerate(parts):
            base = p.split(":")[0]
            up = base.split(".")[0]
            if i < len(parts) - 1 and up.upper() == up and up in CASES:
                pieces.append(p + "-")
            elif i > 0 and up.upper() == up and up in TRANSITIVIZERS:
                pieces.append("-" + p)
            elif i > 0 and not pieces[-1].endswith("-"):
                pieces[-1] = pieces[-1] + "-" + p
            else:
                pieces.append(p)
        if tense and pieces:
            pieces[-1] += "^" + tense
        out += pieces
    return out


def categorize(pieces, lexicon=None):
    """Assign each terminal its phrase category."""
    terms = []
    for i, raw in enumerate(pieces):
        tense = None
        role = ""
        if "@" in raw:
            raw, _, role = raw.partition("@")
        if "^" in raw:
            raw, _, t = raw.partition("^")
            tense = [_norm_tense(x) for x in t.split("+")]
        gloss, _, pos = raw.partition(":")
        base = gloss.split(".")[0]
        nxt_raw = pieces[i + 1].split("@")[0] if i + 1 < len(pieces) else ""
        nxt = nxt_raw.split(":")[0].split("^")[0]
        nxt_pos = nxt_raw.partition(":")[2].split("^")[0]
        if pos:
            cat = {"PRON": "N"}.get(pos.upper(), pos.upper())
        elif base in ("COMP", "Q", "IF"):
            cat = "COMP"
        elif pos.upper() == "INTJ":
            cat = "INTJ"
        elif base == "AND":
            cat = "CONJ"
        elif base in ASPECTS:
            cat = "T"
        elif base == "NEG":
            cat = "NEG"
        elif gloss.endswith("-"):
            cat = "K"
        elif gloss.startswith("-"):
            cat = "V"
        elif lexicon and gloss in lexicon.entries and lexicon.entries[gloss].pos not in ("-", "PRON"):
            cat = {"PRON": "N"}.get(lexicon.entries[gloss].pos, lexicon.entries[gloss].pos)
        elif nxt.startswith("-") and nxt.lstrip("-").split(".")[0] in TRANSITIVIZERS:
            cat = "V"
        else:
            cat = "N"
        # A subject pronoun or noun right before its verb sits in spec-vP.
        verbish = nxt_pos.upper() == "V" or (lexicon and nxt in lexicon.entries and lexicon.entries[nxt].pos == "V")
        case_marked = i > 0 and pieces[i - 1].split("@")[0].split(":")[0].endswith("-")
        if cat == "N" and verbish and not case_marked and (base in PRONOUNS or pos.upper() in ("N", "PRON")):
            cat = "V"
            role = role or "subj"
        terms.append(Term(gloss, cat, role, tense))
    for i, t in enumerate(terms):
        if t.cat == "V" and not t.role and not t.gloss.startswith("-"):
            if pieces[i].split("@")[0].partition(":")[2].split("^")[0].upper() == "V" or (lexicon and t.gloss in lexicon.entries and lexicon.entries[t.gloss].pos == "V") \
                    or (i + 1 < len(terms) and terms[i + 1].gloss.startswith("-")):
                t.role = "verb"
    return terms


def clause_from_gloss(text, tense="nonpast", lexicon=None):
    """A main clause from a gloss line such as the video's
    'NPFV NEG.ever 1S comprehend-OBJ ABS-Aghma_Shwa CON-allure'."""
    terms = categorize(split_gloss(text), lexicon)
    terms = [Term("Ø", "COMP", "c"), Term("Ø", "T", "spec")] + terms
    tl = tense if isinstance(tense, list) else [_norm_tense(t) for t in tense.split("+")]
    return Sentence(terms, tl, stages=[("gloss", text)])


# ------------------------------------------------------------ microsyntax

def spell_out(sent):
    """Group terminals two by two into words with their pro-forms."""
    terms = sent.terms
    words = []
    for k in range(0, len(terms), 2):
        pair = terms[k:k + 2]
        top = "START" if k == 0 else PRO[pair[0].cat]
        nxt = terms[k + 2] if k + 2 < len(terms) else None
        w = SWord(top, pair[0], pair[1] if len(pair) > 1 else None, PRO[nxt.cat] if nxt else None, index=len(words))
        words.append(w)
    sent.words = words
    return words


def move_4d(sent):
    """V-to-T-to-C: aspect+verb to C, subject to spec-TP (+NOM), traces left."""
    terms = sent.terms
    main_end = next((i for i, t in enumerate(terms) if t.gloss == "COMP"), len(terms))
    asp = next((t for t in terms[2:main_end] if t.cat == "T"), None)
    verb = next((t for t in terms if t.role == "main"), None)
    verb = verb or next((t for t in terms[2:main_end] if t.role == "verb"), None)
    subj = next((t for t in terms if t.role == "mainsubj"), None)
    explicit = any(t.role in ("main", "mainsubj") for t in terms)
    if verb and subj is None and not explicit:
        vi = terms.index(verb)
        cand = terms[vi - 1] if vi > 2 else None
        if cand is not None and cand.role == "subj":
            subj = cand
    if not verb:
        return False
    c, spec = terms[0], terms[1]
    c.gloss = "-".join(t.gloss for t in (asp, verb) if t)
    c.parts = [t for t in (asp, verb) if t]
    c.moved = True
    for t in (asp, verb):
        if t:
            t.trace = True
    if subj:
        spec.gloss = subj.gloss + ".NOM"
        spec.parts = [subj, Term("NOM", "K")]
        spec.moved = True
        subj.trace = True
    sent.stages.append(("4D movement", f"{c.gloss} → C, " + (f"{spec.gloss} → spec-TP" if subj else "no subject to raise")))
    return True


def mark_tense(sent):
    """Explicit marks: the first word carries the sentence tense, negative
    words are always marked, ^tense annotations mark their word. Everything
    else inherits along the tree."""
    prev = None
    for w in sent.words:
        mark = None
        for t in (w.m1, w.m2):
            if t and t.tense:
                mark = t.tense
        if w.index == 0:
            mark = mark or sent.tense
        elif any(t and not t.trace and t.gloss.split(".")[0] == "NEG" for t in (w.m1, w.m2)):
            # A negation reaching back to the far past still holds now.
            mark = mark or (["nonpast"] if prev == ["farpast"] else prev)
        w.tense = mark
        w.eff = mark or prev or sent.tense
        prev = w.eff


# ------------------------------------------------------------ macrosyntax

def groups(words):
    out = []
    for w in words:
        if out and out[-1][-1].top == w.top:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def macro_order(sent, front=(), shuffle=None):
    gs = groups(sent.words)
    if shuffle is not None:
        random.Random(shuffle).shuffle(gs)
    for f in reversed(list(front)):
        for i, g in enumerate(gs):
            if any(t and not t.trace and f in t.gloss for w in g for t in (w.m1, w.m2)):
                gs.insert(0, gs.pop(i))
                break
    sent.order = [w for g in gs for w in g]
    return sent.order


# ------------------------------------------------------------ to a score

def word_table(sent):
    rows = []
    for w in sent.order or sent.words:
        def m(t):
            if t is None:
                return "-"
            if t.trace:
                return "t"
            return ("~" if t.moved else "") + t.gloss
        mark = ("i:" if w.tense else "u:") + "+".join(w.eff)
        rows.append((w.index + 1, w.top, m(w.m1), m(w.m2), w.end or "-", mark))
    return rows


def format_table(sent):
    rows = word_table(sent)
    head = ("#", "top", "1", "2", "end", "tense")
    widths = [max(len(str(r[i])) for r in rows + [head]) for i in range(6)]
    line = lambda r: "  ".join(str(c).ljust(widths[i]) for i, c in enumerate(r))
    return "\n".join([line(head), line(["-" * w for w in widths])] + [line(r) for r in rows])


def to_sera(sentences, lexicon, title="", vary=True, seed=0, dialect=None):
    from . import dialects
    from .lexicon import Varier
    heresy = bool(dialect) and dialects.get(dialect).heresy
    v = Varier(seed, heresy) if vary else (lambda toks: toks)
    out = []
    if title:
        out.append(f"@title: {title}")
    if dialect:
        out.append(f"@dialect: {dialect}")
    for si, s in enumerate(sentences):
        if si:
            out.append("---")
        out.append(f"# {s.english or ''}".rstrip())
        tone = (" tone=" + ",".join(f"{k}:{v:.2g}" for k, v in s.tones.items())) if s.tones else ""
        for k, w in enumerate(s.order or s.words):
            mark = "+".join(w.eff) + tone + (" stammer" if s.stammer and k == 0 else "")
            out.append(f"word {mark}    # {w.index + 1}: {w.top} / {_g(w.m1)} / {_g(w.m2)} / {w.end or '-'}")
            out.append(f"  top: {' '.join(v(lexicon.tokens(w.top)))}")
            for name, t in (("1", w.m1), ("2", w.m2)):
                if t is None or t.silent:
                    out.append(f"  {name}:   Ø")
                    continue
                if t.parts and t.gloss.endswith(".NOM"):
                    toks = sum((lexicon.tokens(p.gloss, _pos(p)) for p in t.parts), [])
                elif t.parts:
                    toks = []
                    for k, p in enumerate(t.parts):
                        toks += (["-"] if k else []) + lexicon.tokens(p.gloss, _pos(p))
                else:
                    toks = lexicon.tokens(t.gloss, _pos(t))
                out.append(f"  {name}:   {'~ ' if t.moved else ''}{' '.join(v(toks))}")
            out.append(f"  end: {' '.join(v(lexicon.tokens(w.end))) if w.end else 'Ø'}")
        out.append("")
    return "\n".join(out)


def _g(t):
    if t is None:
        return "-"
    return "t" if t.trace else t.gloss


def _pos(t):
    if t.role in ("subj", "mainsubj"):
        return "PRON" if t.gloss.split(".")[0] in PRONOUNS else "N"
    return {"V": "V", "N": "N", "ADJ": "ADJ", "ADV": "ADV", "K": "K", "T": "T", "NEG": "NEG", "COMP": "COMP"}.get(t.cat)


def build(sentences, lexicon=None, move=True, front=(), shuffle=None):
    lexicon = lexicon or Lexicon()
    for s in sentences:
        spell_out(s)
        if move:
            move_4d(s)
        mark_tense(s)
        macro_order(s, front, shuffle)
    return sentences
