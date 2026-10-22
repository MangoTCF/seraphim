"""English -> Seraphim gloss, following the steps Babelingua takes by hand:
drop articles, agreement and tense (keep aspect), turn sentence adverbs into
'3S be ADJ COMP ...', add cases and transitivizers, make complementizers
explicit. Needs spaCy with en_core_web_sm.

Case logic: main clauses are nominative-accusative with the accusative
unmarked (the subject gets NOM through 4D movement); embedded clauses are
ergative-absolutive, so patients and intransitive subjects take ABSV-.
'X of Y' and possessives become construct chains: CON-X ABS-Y.
"""

from .grammar import Sentence, Term, categorize, _norm_tense

PRON = {
    "i": "1S", "me": "1S", "my": "1S", "mine": "1S", "myself": "1S",
    "we": "1P", "us": "1P", "our": "1P", "ours": "1P", "ourselves": "1P",
    "you": "2S", "your": "2S", "yours": "2S", "yourself": "2S", "yourselves": "2P",
    "he": "3S", "him": "3S", "his": "3S", "himself": "3S",
    "she": "3S", "her": "3S", "hers": "3S", "herself": "3S",
    "it": "3N", "its": "3N", "itself": "3N",
    "this": "THIS", "these": "THIS.PL", "that": "THAT", "those": "THAT.PL",
    "they": "3P", "them": "3P", "their": "3P", "theirs": "3P", "themselves": "3P",
}
PREP_CASE = {
    "in": "LOC", "on": "LOC", "at": "LOC", "inside": "LOC", "within": "LOC", "upon": "LOC",
    "among": "LOC", "about": "LOC", "over": "LOC", "under": "LOC", "near": "LOC",
    "from": "ABL", "out": "ABL", "off": "ABL", "away": "ABL", "since": "ABL",
    "to": "ALL", "toward": "ALL", "towards": "ALL", "onto": "ALL", "until": "ALL",
    "into": "TRAL", "by": "INS", "with": "INS", "through": "INS", "via": "INS",
    "for": "BEN", "against": "MAL", "without": "AVR", "despite": "AVR", "unlike": "AVR",
    "of": "CON", "like": "SIM", "as": "SIM",
}
POSS_PRED = {"mine": "1S", "yours": "2S", "hers": "3S", "ours": "1P", "theirs": "3P"}
IDIOMS = {("adam", "apple"): "Adam's_apple"}      # possessive idioms kept whole
IRREALIS_AUX = {"would", "could", "should", "might", "'d"}
SKIP_ADV = {"never", "not", "n't", "then"}
TRANSITIVIZED = {"BEN": "-BEN", "MAL": "-MAL", "DAT": "-DAT"}
WH_CASE = {"how": "INS", "where": "LOC", "when": "LOC", "why": "BEN", "whence": "ABL", "whither": "ALL"}
FAR_PAST_CUES = {"ago", "once", "ancient", "anciently", "formerly", "beginning", "olden"}
GNOMIC_CUES = {"always", "forever", "eternally", "generally", "usually"}

_nlp = None


def nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
        except ImportError:
            raise SystemExit("translation needs spaCy: pip install spacy && python -m spacy download en_core_web_sm")
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


def adverb_to_adjective(word):
    w = word.lower()
    if w.endswith("ically"):
        return w[:-4]
    if w.endswith("ily"):
        return w[:-3] + "y"
    if w.endswith("ly"):
        return w[:-2]
    return w


class Translator:
    def __init__(self):
        self.notes = []
        self.skip = set()      # tokens split off into their own utterance

    # -------------------------------------------------------- noun phrases

    def np(self, tok, case=None, subject=False):
        if tok.tag_ in ("WDT", "WP", "WP$") or tok.morph.get("PronType") == ["Rel"]:
            return []
        out = [case + "-"] if case else []
        if tok.lower_ in POSS_PRED:
            return out + ["ABS-", POSS_PRED[tok.lower_] + ":PRON"]       # 'be mine'
        if tok.pos_ == "PRON" or tok.lower_ in PRON:
            code = PRON.get(tok.lower_)
            if code is None:
                code = tok.lemma_.lower()
                self.notes.append(f"pronoun {tok.text!r} kept as a word")
            return out + [code + ":PRON"]
        kids = [c for c in tok.children if c not in self.skip]
        adjs = [c.lemma_.lower() + ":ADJ" for c in kids
                if c.dep_ in ("amod", "nummod") or (c.dep_ == "advmod" and c.pos_ == "ADJ")]
        head = self.noun_gloss(tok)
        # 'Adam's' is a possessor ('nmod' + 's) unless it makes an idiom
        poss = [c for c in kids if c.dep_ == "poss"
                or (c.dep_ == "nmod" and any(k.dep_ == "case" for k in c.children))]
        for c in list(poss):
            if (c.lower_, tok.lemma_.lower()) in IDIOMS:
                head = IDIOMS[(c.lower_, tok.lemma_.lower())]
                poss.remove(c)
        if tok.pos_ == "ADJ":
            # 'my sweet' is 'my sweet one'
            adjs.append(tok.lemma_.lower() + ":ADJ")
            head = "one"
        of = [c for c in kids if c.dep_ == "prep" and c.lower_ == "of"]
        # Case markings first, then adjectives, then the word: CON- sweet one
        if poss or of:
            out.append("CON-")
        out += adjs + [head + ":N"]
        for p in poss:
            out += self.np(p, "ABS")
        for p in of:
            for po in p.children:
                if po.dep_ == "pobj":
                    out += self.np(po, "ABS")
        for c in kids:
            if c.dep_ == "prep" and c.lower_ != "of":
                cs = PREP_CASE.get(c.lower_, "LOC")
                for po in c.children:
                    if po.dep_ == "pobj":
                        out += self.np(po, cs)
            elif c.dep_ in ("relcl", "acl"):
                out += self.clause(c, embedded=True)
        for c in kids:
            if c.dep_ == "conj" and c.pos_ in ("NOUN", "PROPN", "PRON"):
                # 'my heart and soul' -> CON-heart ABS-1S AND CON-soul ABS-1S
                sub = self.np(c)
                if poss and not any(k.dep_ == "poss" for k in c.children):
                    sub = ["CON-"] + sub + sum((self.np(p, "ABS") for p in poss), [])
                out += ["AND"] + sub
        return out

    def noun_gloss(self, tok):
        comp = [c for c in tok.children if c.dep_ == "compound"]
        if tok.pos_ == "PROPN":
            words = [c.text for c in comp] + [tok.text]
            return "_".join(words)
        base = "_".join([c.lemma_.lower() for c in comp] + [tok.lemma_.lower()])
        if tok.tag_ in ("NNS", "NNPS"):
            base += ".PL"
        return base

    # -------------------------------------------------------- clauses

    def finite(self, v):
        aux = [c for c in v.children if c.dep_ in ("aux", "auxpass")]
        if any(a.tag_ == "TO" for a in aux):
            return False
        return v.tag_ in ("VBD", "VBZ", "VBP", "MD") or any(a.tag_ in ("VBD", "VBZ", "VBP", "MD") for a in aux)

    def tense_of(self, v):
        """Tense of a finite clause; None for non-finite ones, which inherit."""
        if v.dep_ != "ROOT" and not self.finite(v):
            return None
        aux = [c for c in v.children if c.dep_ in ("aux", "auxpass")]
        words = {t.lower_ for t in v.subtree}
        if words & FAR_PAST_CUES:
            return "farpast"
        perfect = any(a.lemma_ == "have" for a in aux) and v.tag_ == "VBN"
        if perfect:
            return "farpast"        # began in the far past (the demo's reading)
        if v.tag_ == "VBD" or any(a.tag_ == "VBD" for a in aux):
            return "nearpast"
        subj = next((c for c in v.children if c.dep_ in ("nsubj", "nsubjpass")), None)
        generic = subj is not None and subj.tag_ in ("NNS", "NNPS") and not any(c.dep_ == "det" for c in subj.children)
        if (words & GNOMIC_CUES or generic) and not aux:
            return "gnomic"
        return "nonpast"

    def imperative(self, v):
        kids = list(v.children)
        return (v.tag_ == "VB" and v.dep_ not in ("xcomp", "pcomp", "ccomp")
                and not any(c.dep_ in ("nsubj", "nsubjpass", "expl") for c in kids)
                and not any(c.tag_ in ("TO", "MD") for c in kids))

    def clause(self, v, embedded=False, own_tense=None, main=False, question=False):
        """Mood/aspect, negation, adverbs and subject, then the predicate."""
        out = ["Q"] if question else []
        nominal = embedded and not self.finite(v)
        kids = [c for c in v.children if c not in self.skip]
        aux = [c for c in kids if c.dep_ in ("aux", "auxpass")]
        conditional = any(c.dep_ == "mark" and c.lower_ == "if" for c in kids)
        irrealis = any(a.lower_ in IRREALIS_AUX for a in aux) or (conditional and v.tag_ == "VBD")
        if embedded and not nominal:
            t = self.tense_of(v)
            mark = f"^{t}" if own_tense and t and t != own_tense and not irrealis else ""
            out.append(("IF" if conditional else "COMP") + mark)
        negs = [c for c in kids if c.dep_ == "neg"]
        imperative = main and self.imperative(v)
        future = any(a.lower_ in ("will", "shall", "'ll", "wo") for a in aux)
        never = any(n.lower_ in ("never", "nowhere", "nothing") for n in negs)
        perfect = any(a.lemma_ == "have" for a in aux) and v.tag_ == "VBN"
        prog = any(a.lemma_ == "be" for a in aux) and v.tag_ == "VBG"
        past = v.tag_ == "VBD" or any(a.tag_ == "VBD" for a in aux)
        if nominal:
            pass        # gerunds and infinitives are nominalized: no aspect
        elif imperative:
            out.append("IMP")
        elif irrealis:
            out.append("IRR")       # would, counterfactual were (an extension)
        elif future:
            out.append("PFV")       # perfective non-past reads as future
        elif prog or (perfect and never):
            out.append("NPFV")
        elif perfect or past:
            out.append("PERF")
        else:
            out.append("NPFV")
        if negs:
            out.append("NEG.ever" if never else "NEG")
        wh = None
        for c in kids:
            if c.lower_ in WH_CASE and c.dep_ == "advmod":
                wh = WH_CASE[c.lower_]
            elif (c.dep_ == "advmod" and c.lower_ not in SKIP_ADV and c.pos_ == "ADV"
                    and not (c.i == c.sent.start and c.lower_.endswith("ly"))) \
                    or (c.dep_ == "intj" and c.lower_ == "please"):
                out.append(c.lower_ + ":ADV")
        subj = next((c for c in kids if c.dep_ in ("nsubj", "nsubjpass", "expl")), None)
        if imperative:
            out.append("2S:PRON@mainsubj")      # the implied addressee raises like any subject
        transitive = any(c.dep_ in ("dobj", "dative", "iobj") for c in kids)
        if subj is not None and subj.dep_ != "expl":
            if nominal:
                # 'him starting' -> ABS-3S CON-start: a construct chain
                out += self.np(subj, "ABS") + ["CON-"]
            else:
                case = "ABSV" if embedded and not transitive else None
                terms = self.np(subj, case, subject=True)
                if not embedded and len(terms) > 1:
                    terms = ["NOM-"] + terms
                elif main and len(terms) == 1:
                    terms = [terms[0] + "@mainsubj"]
                out += terms
        return out + self.predicate(v, embedded, main, wh, own=self.tense_of(v))

    def predicate(self, v, embedded=False, main=False, wh=None, own=None):
        """Verb, transitivizers, complements, coordinated verbs ('bite …,
        tear out … and chew it' -> bite … AND tear.out … AND chew …), and
        last, since the spine branches right, any embedded clauses."""
        kids = [c for c in v.children if c not in self.skip]
        verb = v.lemma_.lower()
        prt = [c for c in kids if c.dep_ == "prt"]
        if prt:
            verb += "." + ".".join(p.lower_ for p in prt)
        out = [verb + ":V" + ("@main" if main else "")]
        trans, comps, conjs, clauses = [], [], [], []
        for c in kids:
            if c.dep_ == "dobj":
                trans.append("-OBJ")
                comps.append(("obj", c))
            elif c.dep_ in ("dative", "iobj") and c.pos_ != "ADP":
                trans.append("-DAT")
                comps.append(("obj", c))
            elif c.dep_ in ("attr", "acomp", "oprd"):
                comps.append(("pred", c))
            elif c.dep_ == "prep" or (c.dep_ == "dative" and c.pos_ == "ADP"):
                cs = PREP_CASE.get(c.lower_, "LOC")
                for po in c.children:
                    if po.dep_ == "pobj":
                        if cs in TRANSITIVIZED:
                            trans.append(TRANSITIVIZED[cs])
                            comps.append(("obj", po))
                        elif cs == "INS":
                            trans.append("-INS")
                            comps.append(("case", (cs, po)))
                        else:
                            comps.append(("case", (cs, po)))
                    elif po.dep_ == "pcomp":
                        if cs in TRANSITIVIZED or cs == "INS":
                            trans.append(TRANSITIVIZED.get(cs, "-INS"))
                        comps.append(("caseclause", (cs, po)))
            elif c.dep_ == "ccomp" and c.pos_ == "ADJ" and any(k.dep_ == "nsubj" for k in c.children):
                # 'swallow you whole': a small clause, object plus predicate
                trans.append("-OBJ")
                comps.append(("obj", next(k for k in c.children if k.dep_ == "nsubj")))
                comps.append(("pred", c))
            elif c.dep_ in ("ccomp", "xcomp", "advcl"):
                clauses.append(c)
            elif c.dep_ == "conj" and c.pos_ in ("VERB", "AUX"):
                conjs.append(c)
        if wh:
            # 'how' is 'by what means': INS- WH, with its transitivizer
            if wh in TRANSITIVIZED or wh == "INS":
                trans.append(TRANSITIVIZED.get(wh, "-INS"))
            comps.insert(0, ("case", (wh, None)))
        out += trans
        for kind, c in comps:
            if kind == "obj":
                out += self.np(c, "ABSV" if embedded else None)
            elif kind == "pred":
                out += [c.lemma_.lower() + ":ADJ"] if c.pos_ == "ADJ" else self.np(c)
            elif kind == "case" and c[1] is None:
                out += [c[0] + "-", "WH:N"]
            elif kind == "case":
                out += self.np(c[1], c[0])
            elif kind == "caseclause":
                cs, pc = c
                out.append(cs + "-")
                out += self.clause(pc, embedded=True)
        for c in conjs:
            out += ["AND"] + self.predicate(c, embedded, own=own)
        for c in clauses:
            out += self.clause(c, embedded=True, own_tense=own)
        return out

    # -------------------------------------------------------- sentences

    def utterances(self, sent):
        """Split off what English packs into one sentence but Seraphim can't:
        a leading imperative ('Please don't cry, …') and vocatives ('…, child
        of hell, …'). Each becomes its own utterance with its own START."""
        root = sent.root
        parts = []
        for c in root.children:
            if c.dep_ in ("advcl", "parataxis", "ccomp") and c.i < root.i and self.imperative(c) \
                    and not any(k.dep_ == "mark" for k in c.children):
                parts.append(("imperative", c))
        heads = [root] + [c for _, c in parts]
        for h in heads:
            subjects = [c for c in h.children if c.dep_ == "nsubj"]
            if len(subjects) > 1:
                # 'My sweet one, … I would bite': the extra subject is a vocative
                parts += [("vocative", c) for c in subjects[:-1]]
        for h in heads:
            for c in h.children:
                left = sent.doc[c.left_edge.i - 1] if c.left_edge.i > sent.start else None
                right = sent.doc[c.right_edge.i + 1] if c.right_edge.i + 1 < sent.end else None
                commas = (left is None or left.is_punct) and (right is None or right.is_punct)
                if c.pos_ in ("NOUN", "PROPN") and c.dep_ in ("npadvmod", "appos", "dep", "vocative") and commas:
                    parts.append(("vocative", c))
        subtrees = {c.i: set(c.subtree) for _, c in parts}
        out = []
        for kind, c in sorted(parts, key=lambda p: p[1].i):
            # Translate this part with everything else split off hidden.
            self.skip = set().union(*(t for i, t in subtrees.items() if i != c.i)) - subtrees[c.i]
            text = " ".join(t.text for t in c.subtree if t not in self.skip and not t.is_punct)
            if kind == "imperative":
                out.append((self.clause(c, main=True), "nonpast", text))
            else:
                self.notes.append(f"vocative {text!r} spoken on its own, in VOC-")
                out.append((self.np(c, "VOC"), "nonpast", text))
        self.skip = set().union(*subtrees.values())
        question = sent.text.rstrip().rstrip("!").endswith("?")
        if root.pos_ not in ("VERB", "AUX"):
            # 'My sweet…': no verb at all, so a vocative on its own
            self.notes.append("verbless sentence read as a vocative")
            text = " ".join(t.text for t in sent if t not in self.skip and not t.is_punct)
            return out + [(self.np(root, "VOC"), "nonpast", text)]
        pieces, tense, _ = self.sentence(sent, question)
        if any(c.dep_ == "cc" and c.i == sent.start for c in root.children):
            pieces = ["AND"] + pieces         # 'And I want to …'
        rest = " ".join(t.text for t in sent if t not in self.skip and not t.is_punct)
        out.append((pieces, tense, rest))
        return out

    def sentence(self, sent, question=False):
        root = sent.root
        tense = self.tense_of(root)
        lead = sent[0]
        if lead.dep_ == "advmod" and lead.head == root and lead.lower_.endswith("ly"):
            # 'Obviously, I didn't continue the video' ->
            # '3S be obvious COMP 1S NEG continue-OBJ video'
            adj = adverb_to_adjective(lead.text)
            pieces = ["NPFV", "3S:PRON@mainsubj", "be:V@main", adj + ":ADJ"] + self.clause(root, embedded=True, own_tense="nonpast")
            self.notes.append(f"sentence adverb {lead.text!r} became '3S be {adj} COMP …'")
            tense = "nonpast"
        else:
            pieces = self.clause(root, main=True, question=question)
        stripped = " ".join(t.lemma_ if t.pos_ in ("VERB", "AUX") else t.text for t in sent
                            if t.dep_ not in ("det", "punct", "aux") or t.dep_ == "neg")
        return pieces, tense, stripped


def translate(text, lexicon):
    tr = Translator()
    out = []
    for sent in nlp()(text).sents:
        tr.notes = []
        tr.skip = set()
        for k, (pieces, tense, label) in enumerate(tr.utterances(sent)):
            terms = categorize(pieces, lexicon)
            terms = [Term("Ø", "COMP", "c"), Term("Ø", "T", "spec")] + terms
            gloss = " ".join(p.split("@")[0].split(":")[0].split("^")[0] for p in pieces)
            s = Sentence(terms, [_norm_tense(tense)], english=label)
            s.stages = [("english", label), ("gloss", gloss), ("tense", tense)]
            s.stages += [("note", n) for n in tr.notes]
            s.source = sent.text.strip() if k == 0 else ""   # the original wording, for titles
            tr.notes = []
            out.append(s)
    return out
