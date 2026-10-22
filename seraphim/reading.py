"""Seraphim -> gloss -> rough English.

Each mouth is decoded by phoneme values against the lexicon (spelling never
matters), the spoken words are chained back into tree order through their
pro-phrases (each word's end must agree with the next word's top), 4D
movement is undone by putting the raised aspect, verb and subject back into
the traces, and the recovered gloss is rendered as English.
"""

from dataclasses import dataclass

from .grammar import ASPECTS, CASES, TRANSITIVIZERS
from .lexicon import PRONOUNS
from .score import MOUTHS

PRON_EN = {   # subject, object, possessive determiner, possessive pronoun
    "1S": ("I", "me", "my", "mine"), "2S": ("you", "you", "your", "yours"), "3S": ("he", "him", "his", "his"),
    "1P": ("we", "us", "our", "ours"), "2P": ("you", "you", "your", "yours"), "3P": ("they", "them", "their", "theirs"),
    "3N": ("it", "it", "its", "its"), "THIS": ("this", "this", "this", "this"), "THAT": ("that", "that", "that", "that"),
}
CASE_PREP = {"LOC": "in", "ABL": "from", "ALL": "to", "TRAL": "into", "INS": "with", "AVR": "without", "SIM": "like",
             "DAT": "to", "BEN": "for"}
WH_EN = {"INS": "how", "LOC": "where", "BEN": "why", "ABL": "where from", "ALL": "where", None: "what"}
NO_ARTICLE = {"heaven", "hell", "paradise", "eden", "sheol", "love", "darkness", "light", "pleasure",
              "fire", "blood", "flesh", "joy", "glory"}
STOPS = ("COMP", "IF", "AND")       # where a clause's tail of complements ends
TRANS_PREP = {"-DAT": "to", "-BEN": "for", "-MAL": "against", "-INS": "by", "-DIS": "each of", "-ORN": "with"}
IRREGULAR = {
    "be": ("was", "been"), "have": ("had", "had"), "do": ("did", "done"), "go": ("went", "gone"),
    "see": ("saw", "seen"), "eat": ("ate", "eaten"), "give": ("gave", "given"), "take": ("took", "taken"),
    "make": ("made", "made"), "know": ("knew", "known"), "think": ("thought", "thought"),
    "come": ("came", "come"), "say": ("said", "said"), "get": ("got", "gotten"), "find": ("found", "found"),
    "begin": ("began", "begun"), "understand": ("understood", "understood"), "sing": ("sang", "sung"),
    "write": ("wrote", "written"), "speak": ("spoke", "spoken"), "bring": ("brought", "brought"),
    "buy": ("bought", "bought"), "teach": ("taught", "taught"), "fall": ("fell", "fallen"),
    "fly": ("flew", "flown"), "rise": ("rose", "risen"), "shine": ("shone", "shone"), "hear": ("heard", "heard"),
    "hold": ("held", "held"), "keep": ("kept", "kept"), "leave": ("left", "left"), "lose": ("lost", "lost"),
    "meet": ("met", "met"), "run": ("ran", "run"), "sit": ("sat", "sat"), "stand": ("stood", "stood"),
    "tell": ("told", "told"), "win": ("won", "won"), "break": ("broke", "broken"), "choose": ("chose", "chosen"),
    "drink": ("drank", "drunk"), "forget": ("forgot", "forgotten"), "grow": ("grew", "grown"),
    "hide": ("hid", "hidden"), "seek": ("sought", "sought"), "sell": ("sold", "sold"), "send": ("sent", "sent"),
    "show": ("showed", "shown"), "sleep": ("slept", "slept"), "throw": ("threw", "thrown"),
    "wear": ("wore", "worn"), "build": ("built", "built"), "feel": ("felt", "felt"), "lead": ("led", "led"),
    "read": ("read", "read"), "burn": ("burned", "burnt"), "light": ("lit", "lit"), "comprehend": ("comprehended", "comprehended"),
    "witness": ("witnessed", "witnessed"), "put": ("put", "put"), "let": ("let", "let"),
}


DOUBLING = {"begin", "run", "sit", "swim", "stop", "get", "put", "let", "win", "forget", "plan",
            "cut", "hit", "shut", "set", "dig", "admit", "commit", "permit", "regret", "occur"}


@dataclass
class Decoded:
    gloss: str
    moved: bool = False
    known: bool = True


def decode_line(ml, lexicon, index):
    """Morpheme glosses for one mouth line."""
    if ml.silent:
        return None
    parts, cur = [], []
    for t in ml.tokens:
        if t.kind == "break":
            parts.append(cur)
            cur = []
        else:
            cur.append((t.value, t.cls, t.brightness))
    parts.append(cur)
    glosses, known = [], True
    for p in parts:
        g = segment(tuple(p), index)
        if g is None:
            known = False
            g = "?" + "".join(f"/{v}{'VC'[c == 'C'] if c else ''}{'*' * b}/" for v, c, b in p)
        glosses.append(g)
    return Decoded("-".join(glosses), ml.moved, known)


def segment(sig, index):
    """Split a signature into known morphemes (fewest pieces), joined by '.'."""
    if sig in index:
        return index[sig].gloss
    best = {0: []}
    for i in range(len(sig)):
        if i not in best:
            continue
        for j in range(len(sig), i, -1):
            if sig[i:j] in index and (j not in best or len(best[j]) > len(best[i]) + 1):
                best[j] = best[i] + [index[sig[i:j]].gloss]
    return ".".join(best[len(sig)]) if len(sig) in best else None


@dataclass
class RWord:
    top: str
    m1: Decoded
    m2: Decoded
    end: str
    langs: list
    spoken: int


def read_score(score, lexicon):
    index = lexicon.by_signature()
    sentences, cur = [], []
    for i, w in enumerate(score.words):
        if w.sentence_start and cur:
            sentences.append(cur)
            cur = []
        d = {m: decode_line(w.mouths[m], lexicon, index) for m in MOUTHS}
        cur.append(RWord(d["top"].gloss if d["top"] else "?", d["1"], d["2"],
                         d["end"].gloss if d["end"] else None, w.langs, i + 1))
    if cur:
        sentences.append(cur)
    # Several sentences may be written without '---': split at each 'start'.
    out = []
    for s in sentences:
        chunk = []
        for w in s:
            if w.top == "START" and any(c.top == "START" for c in chunk):
                out.append(chunk)
                chunk = []
            chunk.append(w)
        out.append(chunk)
    return [reconstruct(s) for s in out]


def reconstruct(words):
    """Chain words into tree order and undo 4D movement."""
    remaining = list(words)
    first = next((w for w in remaining if w.top == "START"), remaining[0])
    chain = [first]
    remaining.remove(first)
    problems = []
    while remaining:
        need = chain[-1].end
        nxt = next((w for w in remaining if w.top == need), None)
        if nxt is None:
            problems.append(f"no word continues {need!r}; appending the rest in spoken order")
            chain += remaining
            break
        chain.append(nxt)
        remaining.remove(nxt)
    # Collect terminals; the start word's mouths hold raised material.
    raised_vt, raised_subj = None, None
    s = chain[0]
    if s.m1 and s.m1.moved:
        raised_vt = s.m1.gloss.split("-")
    if s.m2 and s.m2.moved:
        raised_subj = ".".join(p for p in s.m2.gloss.split(".") if p != "NOM")
    refill = []
    if raised_vt:
        if raised_vt[0] in ASPECTS:
            refill.append(raised_vt[0])
            raised_vt = raised_vt[1:]
        if raised_subj:
            refill.append(raised_subj)
        refill.append("-".join(raised_vt))
    elif raised_subj:
        refill.append(raised_subj)
    main_verb = refill[-1] if raised_vt else None
    main_at = None
    terms, langs = [], []
    for wi, w in enumerate(chain):
        for m in (w.m1, w.m2):
            if wi == 0:
                if m and not m.moved:
                    terms.append(m.gloss)
                    langs.append(w.langs)
                continue
            if m is None:
                # An empty mouth 1 before a full mouth 2 is always a trace;
                # an empty slot at the very end is just the end.
                if refill and (wi < len(chain) - 1 or (m is w.m1 and w.m2 is not None)):
                    if len(refill) == 1 and main_verb:
                        main_at = len(terms)
                    terms.append(refill.pop(0))
                    langs.append(chain[0].langs)     # raised material keeps the start word's tense
                continue
            terms.append(m.gloss)
            langs.append(w.langs)
    if refill and main_verb and main_at is None:
        main_at = len(terms) + len(refill) - 1
    terms += refill
    langs += [chain[0].langs] * len(refill)
    return dict(chain=chain, terms=terms, langs=langs, main_at=main_at, problems=problems,
                tense=chain[0].langs)


# ------------------------------------------------------------ English

class Realizer:
    def __init__(self, lexicon, langs=None, fronted=()):
        self.lx = lexicon
        self.langs = langs if langs is not None else []
        self.fronted = set(fronted)
        self.depth = 0
        self.main_at = None
        self.pending_if = []
        self.copula = False
        self.subj_plural = False

    def pos(self, g):
        base = g.split(".")[0]
        if g in self.lx.entries:
            return self.lx.entries[g].pos
        if base in self.lx.entries:
            return self.lx.entries[base].pos
        if base in PRONOUNS:
            return "PRON"
        return "N"

    def noun(self, g, form=0):
        base, *feats = g.split(".")
        if base in PRON_EN:
            return PRON_EN[base][form]
        if base.startswith("?"):
            return "[unknown]"
        if base == "WH":
            return "what"
        word = base.replace("_", " ")
        if "PL" in feats:
            word = word + ("es" if word.endswith(("s", "x", "ch", "sh")) else "s")
        proper = base[:1].isupper() or base in NO_ARTICLE
        return word if proper or form == 2 else "the " + word

    def np(self, toks, i, form=1, stop=None, inf=False):
        """Parse an NP starting at toks[i]; returns (english, case, next i).
        A verb as head is a nominalized clause and takes its complements."""
        stop = len(toks) if stop is None else stop
        case = None
        adjs = []
        construct = False
        absolute = False
        while i < stop and toks[i].endswith("-"):
            c = toks[i][:-1]
            if c == "CON":
                construct = True
            elif c == "ABS":
                absolute = True
            else:
                case = c
            i += 1
        if absolute and not construct and i < stop and toks[i].split(".")[0] in PRON_EN \
                and not (i + 1 < stop and toks[i + 1] == "CON-"):
            return PRON_EN[toks[i].split(".")[0]][3], case, i + 1      # 'be mine'
        while i < stop and self.pos(toks[i]) == "ADJ":
            adjs.append(toks[i].replace("_", " "))
            i += 1
        if i >= stop:
            return " ".join(adjs), case, i
        head = toks[i]
        i += 1
        if self.pos(head) == "V":
            words, i = self.tail(toks, i, stop)
            v = "to " + head.replace(".", " ") if inf else self.gerund(head)
            while i + 1 < stop and toks[i] == "AND" and self.pos(toks[i + 1]) == "V":
                conj = toks[i + 1]
                more, i = self.tail(toks, i + 2, stop)
                words += ["and", conj.replace(".", " ") if inf else self.gerund(conj)] + more
            return " ".join([v] + words), case, i
        phrase = self.noun(head, form)
        if adjs:
            if phrase.startswith("the "):
                phrase = "the " + " ".join(adjs) + " " + phrase[4:]
            else:
                phrase = " ".join(adjs) + " " + phrase
        if construct and i < stop and toks[i] == "ABS-":
            if i + 1 < stop and toks[i + 1].split(".")[0] in PRON_EN:
                owner = PRON_EN[toks[i + 1].split(".")[0]][2]
                phrase = owner + " " + phrase.removeprefix("the ")
                i += 2
            else:
                owner, _, i = self.np(toks, i + 1, 1, stop)
                phrase = f"{phrase} of {owner}"
        elif i < stop and toks[i] == "CON-":
            # Absolute first: 'ABS-X CON-Y' is 'the Y of X', or with a verb
            # as Y a clause with X as its subject ('him starting out').
            j = i + 1
            while j < stop and self.pos(toks[j]) == "ADJ":
                j += 1
            if j < stop and self.pos(toks[j]) == "V":
                owned, _, i = self.np(toks, i + 1, form, stop)
                phrase = f"{phrase} {owned}"
            else:
                owned, _, i = self.np(toks, i, form, stop)
                phrase = f"{owned} of {phrase}"
        if i + 1 < stop and toks[i] == "AND" and self.pos(toks[i + 1]) != "V":
            other, _, i = self.np(toks, i + 1, form, stop)
            # 'my heart and my soul' -> 'my heart and soul'
            first = phrase.split(" ", 1)[0]
            if first in ("my", "your", "his", "our", "their") and other.startswith(first + " "):
                other = other[len(first) + 1:]
            phrase = f"{phrase} and {other}"
        return phrase, case, i

    def tail(self, toks, i, stop=None):
        """Transitivizers and complements after a verb, as English chunks."""
        stop = len(toks) if stop is None else stop
        trans = []
        while i < stop and toks[i].startswith("-") and toks[i][1:].split(".")[0] in TRANSITIVIZERS:
            trans.append(toks[i])
            i += 1
        objs = []
        while i < stop and toks[i] not in STOPS:
            if self.pos(toks[i]) == "ADJ" and (i + 1 >= stop or self.pos(toks[i + 1]) not in ("N", "PRON")):
                objs.append((None, toks[i].replace("_", " "), {toks[i]}, False, False))
                i += 1
                continue
            begin = i
            verbal = self.pos(toks[i]) == "V" and not self.copula
            if self.pos(toks[i]) == "V" and self.copula:
                e, case, i = self.noun(toks[i], 1), None, i + 1
                if e.startswith("the ") and e[4:] in NO_ARTICLE:
                    e = e[4:]
            else:
                e, case, i = self.np(toks, i, 1, stop, inf=verbal)
            self.copula = False
            head_v = self.pos(next((t for t in toks[begin:i] if not t.endswith("-")), "")) == "V"
            objs.append((case, e, set(toks[begin:i]), verbal, head_v))
        sub = None
        if i < stop and toks[i] in ("COMP", "IF"):
            sub, i = self.clause(toks, None, i, stop)
            if sub.startswith("if "):
                self.pending_if.append(sub)     # conditionals go up front
                sub = None
        self.last_objs = objs
        self.last_trans = trans
        tq = list(trans)
        direct, oblique = [], []
        for case, e, span, verbal, head_v in objs:
            if "WH" in span:
                # 'INS- WH' is 'by what means': how. It goes to the front.
                self.wh = WH_EN.get(case, "what")
                if tq and tq[0] == "-" + (case or "OBJ"):
                    tq.pop(0)
                continue
            if case and case in CASE_PREP and not (tq and tq[0] == "-" + case):
                if case == "SIM" and e.startswith("the "):
                    e = ("an " if e[4:5] in "aeiou" else "a ") + e[4:]     # 'like a cracker'
                oblique.append(f"{CASE_PREP[case]} {e}")
                continue
            if verbal and not case:
                direct.append(e)            # 'manage to love me'
                continue
            t = tq.pop(0) if tq else "-OBJ"
            prep = TRANS_PREP.get(t.split(".")[0])
            if t == "-INS" and not head_v:
                prep = "with"               # by trying, with great pleasure
            (oblique if prep else direct).append(f"{prep} {e}" if prep else e)
        self.last_direct = direct
        return direct + oblique + ([sub] if sub else []), i

    def gerund(self, v):
        w = v.split(".")[0]
        if w in DOUBLING:
            w += w[-1]
        elif w.endswith("e") and not w.endswith(("ee", "be")):
            w = w[:-1]
        return w + "ing" + "".join(" " + p for p in v.split(".")[1:])

    def verb(self, v, aspect, langs, neg, subj):
        base, *prt = v.split(".")
        prt = "".join(" " + p for p in prt)
        past, part = IRREGULAR.get(base, (base + ("d" if base.endswith("e") else "ed"),) * 2)
        third = bool(subj) and subj not in ("I", "you", "we", "they") and not self.subj_plural
        tense = langs[0] if langs else "latin"
        never = neg == "NEG.ever"
        if aspect == "IMP":
            return ("never " if never else "do not " if neg else "") + base + prt
        if aspect == "PFV" and tense == "latin":
            return "will " + ("never " if never else "not " if neg else "") + base + prt
        if base == "be":
            pres = "is" if third else ("am" if subj == "I" else "are")
            pst = "was" if third or subj == "I" else "were"
            if tense == "latin":
                return pres + (" never" if never else " not" if neg else "")
            return pst + (" never" if never else " not" if neg else "")
        if tense == "aramaic":
            # Far past or gnomic. Imperfective far past reaches into now.
            have = "has" if third else "have"
            if never:
                return f"{have} never {part}{prt}"
            if aspect == "NPFV" and neg:
                return f"{have} not {part}{prt}"
            if aspect == "NPFV":
                return (base + ("es" if base.endswith(("s", "sh", "ch")) else "s") if third else base) + prt
            return "had " + ("not " if neg else "") + part + prt
        if tense == "greek":
            if aspect == "NPFV":
                return ("was" if third or subj == "I" else "were") + (" not" if neg else "") + " " + self.gerund(v)
            if never:
                return "never " + past + prt
            return ("did not " + base if neg else past) + prt
        if never:
            return "never " + (base + "s" if third else base) + prt
        if neg:
            return ("does not " if third else "do not ") + base + prt
        return (base + ("es" if base.endswith(("s", "sh", "ch")) else "s") if third else base) + prt

    def clause(self, toks, langs, i=0, stop=None):
        """English for a clause starting at toks[i] (up to `stop`)."""
        stop = len(toks) if stop is None else stop
        top = self.depth == 0
        self.depth += 1
        comp = None
        lead = ""
        if i < stop and toks[i] == "AND":
            lead = "and"
            i += 1
        if i < stop and toks[i] in ("COMP", "IF"):
            comp = "if" if toks[i] == "IF" else "that"
            i += 1
        question = i < stop and toks[i] == "Q"
        if question:
            i += 1
        if top:
            self.wh = None
        aspect = toks[i] if i < stop and toks[i] in ASPECTS else None
        if aspect:
            i += 1
        neg = None
        if i < stop and toks[i].split(".")[0] == "NEG":
            neg = toks[i]
            i += 1
        advs = []
        while i < stop and self.pos(toks[i]) == "ADV":
            advs.append(toks[i])
            i += 1
        subj = None
        self.subj_plural = False
        if i < stop and self.pos(toks[i]) != "V":
            s0 = i
            subj, case, i = self.np(toks, i, 0, stop)
            span = toks[s0:i]
            self.subj_plural = "AND" in span or any(t.split(".")[0] in ("1P", "2P", "3P") or "PL" in t.split(".")[1:]
                                                    for t in span if not t.endswith("-"))
            if case == "VOC":
                subj = "O " + subj.removeprefix("the ") + "!"
            # A relative clause inside the subject runs up to the main verb.
            if top and i < stop and toks[i] == "COMP" and self.main_at and i < self.main_at <= stop:
                rel, _ = self.clause(toks, langs, i, self.main_at)
                subj = f"{subj} {rel}"
                i = self.main_at
        if i >= stop:
            self.depth -= 1
            return subj or "", i
        v = toks[i]
        if i < len(self.langs) and self.langs[i]:
            langs = self.langs[i]
        i += 1
        self.copula = v == "be"
        rest, i = self.tail(toks, i, stop)
        direct, trans, objs = self.last_direct, self.last_trans, self.last_objs
        verb = self.verb(v, aspect, langs, neg, subj)
        if aspect == "IRR":
            base = v.replace(".", " ")
            if comp == "if":        # counterfactual: 'if you were a person'
                verb = "were" if v == "be" else IRREGULAR.get(v.split(".")[0], (v + "ed",))[0]
            else:
                verb = "would " + ("not " if neg else "") + base
        # Coordinated verbs share the subject and mood: 'bite …, tear out … and chew it'
        while i + 1 < stop and toks[i] == "AND" and self.pos(toks[i + 1]) == "V":
            v2 = toks[i + 1]
            more, i = self.tail(toks, i + 2, stop)
            v2_en = v2.replace(".", " ") if aspect == "IRR" else self.verb(v2, aspect, langs, None, subj)
            rest = rest + ["and", v2_en] + more
        if i < stop and toks[i] in ("COMP", "IF"):
            sub, i = self.clause(toks, langs, i, stop)
            if sub.startswith("if "):
                self.pending_if.append(sub)
            else:
                rest = rest + [sub]
        self.depth -= 1
        # Sentence adverb wrapper: '3S be obvious COMP …' -> 'Obviously, …'
        if v == "be" and subj == "he" and len(objs) == 1 and objs[0][0] is None and len(rest) == 2:
            return f"{objs[0][1].capitalize()}ly, {rest[1].removeprefix('that ')}", i
        # A fronted object is more active than the subject: 'the cheese
        # caused the man to eat it' (the video's example).
        if top and direct and trans and trans[0] == "-OBJ" and objs and objs[0][2] & self.fronted:
            obj_form = {"I": "me", "we": "us", "he": "him", "she": "her", "they": "them"}.get(subj, subj)
            return f"{direct[0]} caused {obj_form} to {v.split('.')[0]} it", i
        advs = [a.replace("_", " ") for a in advs]
        front = [a for a in advs if a == "please"]
        advs = [a for a in advs if a != "please"]
        if aspect == "IMP":
            out = front + advs + [verb] + rest
        elif question and top:
            out = front + self.question(v, aspect, langs, neg, subj, advs) + rest
        else:
            if v == "be" and objs and objs[0][1].startswith("the ") and len(objs) == 1 and objs[0][0] is None:
                noun = objs[0][1][4:]
                rest = [("an " if noun[:1] in "aeiou" else "a ") + noun] + rest[1:]   # 'a sinner', 'an obsession'
            out = front + [subj or ""] + advs + [verb] + rest
        text = " ".join(x for x in [lead] + out if x)
        if question and top:
            text += "?"
        if top and self.pending_if:
            # 'If you were a person, I would bite …'
            text = ", ".join(self.pending_if + [text])
            self.pending_if = []
        return (f"{comp} {text}" if comp else text), i

    def question(self, v, aspect, langs, neg, subj, advs):
        """English do-support and inversion: 'how did you even manage …'."""
        base, *prt = v.split(".")
        main = " ".join([base] + prt)
        tense = langs[0] if langs else "latin"
        stmt = self.verb(v, aspect, langs, None, subj).split(" ")
        if base == "be":
            aux, main = stmt[0], ""
        elif aspect == "PFV" and tense == "latin":
            aux = "will"
        elif tense == "greek" and aspect == "NPFV":
            aux, main = stmt[0], self.gerund(v)
        elif tense == "greek":
            aux = "did"
        elif tense == "aramaic" and aspect != "NPFV":
            aux, main = "had", IRREGULAR.get(base, (None, base + "ed"))[1] + "".join(" " + p for p in prt)
        else:
            third = subj in ("he", "she", "it")
            aux = "does" if third else "do"
        out = ([self.wh] if self.wh else []) + [aux] + (["not"] if neg else []) + [subj or ""] + advs + [main]
        return [x for x in out if x]


def fronted(reading):
    """Content morphemes spoken before the start word: claimed more active."""
    chain = reading["chain"]
    start = next((w for w in chain if w.top == "START"), None)
    if start is None:
        return []
    out = []
    for w in chain:
        if w.spoken < start.spoken:
            for m in (w.m1, w.m2):
                if m and not m.gloss.endswith("-") and not m.gloss.startswith(("-", "?")):
                    out.append(m.gloss)
    return out


def english(reading, lexicon):
    flat, flat_langs = [], []
    r = Realizer(lexicon, flat_langs, fronted(reading))
    for k, (t, l) in enumerate(zip(reading["terms"], reading["langs"])):
        if k == reading.get("main_at"):
            r.main_at = len(flat)
        parts = t.split("-") if "-" in t.strip("-") and not t.startswith("?") else [t]
        flat += parts
        flat_langs += [l] * len(parts)
    text, _ = r.clause(flat, reading["tense"])
    text = text.strip()
    if not text:
        return ""
    return text[:1].upper() + text[1:] + ("" if text.endswith(("?", "!")) else ".")
