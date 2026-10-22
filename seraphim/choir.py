"""The three praise voices.

While a sentence is spoken, three voices sing prayers whose language marks
tense: Biblical Aramaic (far past, gnomic), Koine Greek (near past) and
Ecclesiastical Latin (non-past). Each voice sings on its own: its own place in
the prayers, its own pace, in its own register of D dorian, phrase by phrase
on one of several chant formulas. They switch language at word boundaries and
pick each language's prayers up where they last left them.
"""

import random

from .phones import PHONES, V, tokenize_ipa
from .synth import Seg

PRAYERS = {
    "latin": [
        # Sanctus (Isaiah 6:3 + Matthew 21:9)
        "ˈsanktus ˈsanktus ˈsanktus | ˈdominus ˈdeus ˈsabaot | ˈpleni sunt ˈtʃeli et ˈtɛrra "
        "ˈglɔria ˈtua | oˈzanna in ekˈʃelsis | beneˈdiktus ki ˈvenit in ˈnomine ˈdomini | "
        "oˈzanna in ekˈʃelsis |",
        # Gloria
        "ˈglɔria in ekˈʃelsis ˈdeo | et in ˈtɛrra pax ˈominibus ˈbone voˈluntatis | "
        "lauˈdamus te | beneˈditʃimus te | adoˈramus te | glorifiˈkamus te |",
        # Agnus Dei
        "ˈanjus ˈdei | ki ˈtollis pekˈkata ˈmundi | miseˈrere ˈnobis | ˈanjus ˈdei | "
        "ki ˈtollis pekˈkata ˈmundi | ˈdona ˈnobis ˈpatʃem |",
        # Pater noster
        "ˈpater ˈnoster | ki es in ˈtʃelis | sanktifiˈtʃetur ˈnomen ˈtuum | adˈveniat ˈrenjum ˈtuum | "
        "ˈfiat voˈluntas ˈtua | ˈsikut in ˈtʃelo et in ˈtɛrra |",
        # Te Deum
        "te ˈdeum lauˈdamus | te ˈdominum konfiˈtemur | te eˈternum ˈpatrem | "
        "ˈomnis ˈtɛrra veneˈratur | ˈtibi ˈomnes ˈandʒeli | ˈtibi tʃeˈrubim et ˈserafim |",
    ],
    "greek": [
        # Isaiah 6:3 (Septuagint) + Luke 2:14
        "ˈhagios ˈhagios ˈhagios | ˈkyrios sabaˈoːθ | ˈpleːreːs ˈpasa heː ˈgeː teːs ˈdokseːs "
        "auˈtuː | ˈdoksa en hyˈpsistois θeˈoː | kai epi geːs eiˈreːneː en ˈanθroːpois euˈdokiaːs |",
        # Trisagion
        "ˈhagios ho θeˈos | ˈhagios isxyˈros | ˈhagios aˈθanatos | eˈleːson heːˈmaːs |",
        # Kyrie
        "ˈkyrie eˈleːson | xriˈste eˈleːson | ˈkyrie eˈleːson |",
        # Pater noster (Matthew 6:9-10)
        "ˈpater heːˈmoːn ho en tois uraˈnois | hagiasˈθeːtoː to ˈonoma su | "
        "elˈθetoː heː basiˈleia su | geneˈθeːtoː to ˈθeleːma su |",
        # Revelation 4:8, the song of the six-winged creatures
        "ˈhagios ˈhagios ˈhagios | ˈkyrios ho θeˈos ho pantoˈkratoːr | "
        "ho eːn kai ho oːn kai ho erˈxomenos |",
    ],
    "aramaic": [
        # Daniel 2:20 and 4:34
        "lɛhɛˈwe ʃəˈmeh di ʔɛlɔˈhɔ | məvɔˈrax min ʕɔlˈmɔ wəʕad ʕɔlˈmɔ | di ħɔxməˈθɔ "
        "ugəvurˈθɔ di leh hiʔ | kəˈʕan ʔanɔ nəvuxadnɛsˈsar | məʃabbaħ umroˈmem umhadˈdar "
        "ləˈmɛlɛx ʃəˈmajjɔ |",
        # Daniel 2:21-22
        "wəˈhuʔ məhaʃˈne ʕiddɔnajˈjɔ wəzimnajˈjɔ | məhaʕˈde malˈxin umhaˈqem malˈxin | "
        "jɔˈhev ħɔxməˈθɔ ləħakkiˈmin | huʔ gɔˈle ʕammiqɔˈθɔ umsattərɔˈθɔ | "
        "jɔˈdaʕ mɔ vaħʃoˈxɔ | unhoˈrɔ ʕimˈmeh ʃəˈrɔ |",
        # Daniel 7:9-10, the throne of fire
        "ħɔˈze haˈwet ʕad di xɔrsəˈwɔn rəˈmiw | wəʕatˈtiq joˈmin jəˈθiv | "
        "ləvuˈʃeh kəθaˈlag ħivˈwɔr | kɔrsəˈjeh ʃəviˈvin di nur | galgilˈloh nur dɔˈliq | "
        "nəˈhar di nur nɔˈɣed | ʔˈelef ʔalˈfin jəʃamməʃunˈneh |",
        # Daniel 3:33
        "ʔɔθoˈhi kəˈmɔ ravrəˈvin | wəθimhoˈhi kəˈmɔ θaqqiˈfin | malxuˈθeh malˈxuθ ʕɔˈlam | "
        "wəʃɔltɔˈneh ʕim dɔr wəˈdɔr |",
    ],
}

# Semitones above D, as scale steps. Locrian, built on the tritone, is the
# demonic dialect's mode.
SCALES = {"dorian": [0, 2, 3, 5, 7, 9, 10], "locrian": [0, 1, 3, 5, 6, 8, 10],
          "phrygian": [0, 1, 3, 5, 7, 8, 10]}
SCALE = SCALES["dorian"]
# Chant formulas in scale steps: (intonation, reciting tone, termination).
FORMULAS = [
    ([2, 3], 4, [3, 1, 0]),     # recite on A, close on D
    ([3, 4], 6, [5, 4, 3]),     # recite on C, close on G
    ([1, 2], 3, [2, 1, 0]),     # recite on G, close on D
    ([4, 5], 7, [6, 5, 4]),     # recite on high D, close on A
]
REGISTERS = [7, 3, 0]           # each voice's transposition in scale steps
BEATS = [0.31, 0.36, 0.42]      # lower voices move more slowly
BASE_D = 146.83


def step_to_hz(step, mode="dorian"):
    octave, k = divmod(step, 7)
    return BASE_D * 2 ** (octave + SCALES[mode][k] / 12)


def syllables(ipa):
    """IPA text -> list of (phones, phrase_final, stressed). Consonants
    between vowels go to the next onset, except the first of a cluster,
    which closes the previous syllable."""
    toks = tokenize_ipa(ipa.replace("ɡ", "g"))
    words, cur = [], []
    phrase_ends = set()
    for p, long_, stress in toks:
        if p in ("#", "|"):
            if cur:
                words.append(cur)
                cur = []
            if p == "|" and words:
                phrase_ends.add(len(words) - 1)
            continue
        cur.append((p, long_, stress))
    if cur:
        words.append(cur)
    out = []
    for wi, w in enumerate(words):
        nuclei = [i for i, (p, _, _) in enumerate(w) if PHONES[p]["kind"] == V]
        if not nuclei:
            out.append(([(p, l) for p, l, _ in w], False, False))
            continue
        groups = []
        for i in nuclei:
            if groups and groups[-1][-1] == i - 1:
                groups[-1].append(i)
            else:
                groups.append([i])
        bounds = [0]
        for a, b in zip(groups, groups[1:]):
            gap = b[0] - a[-1] - 1
            bounds.append(a[-1] + 1 + (1 if gap >= 2 else 0))
        bounds.append(len(w))
        sylls = [w[bounds[i]:bounds[i + 1]] for i in range(len(groups))]
        for si, s in enumerate(sylls):
            final = wi in phrase_ends and si == len(sylls) - 1
            stressed = any(st for _, _, st in s)
            out.append(([(p, l) for p, l, _ in s], final, stressed))
    return out


def melody(sylls, rng):
    """Scale step for each syllable: phrase by phrase on a random formula,
    with the odd neighbour-note ornament on a stressed reciting syllable."""
    steps, phrase = [], []
    for i, (_, final, _) in enumerate(sylls):
        phrase.append(i)
        if final or i == len(sylls) - 1:
            inton, tenor, term = rng.choice(FORMULAS)
            n = len(phrase)
            d = [tenor] * n
            for k, v in enumerate(inton[: max(n - 3, 0)]):
                d[k] = v
            for k, v in enumerate(term[-min(n, 3):]):
                d[n - min(n, 3) + k] = v
            for k in range(len(inton), n - 3):
                if sylls[phrase[k]][2] and rng.random() < 0.3:
                    d[k] = tenor + rng.choice((1, -1))
            steps += d
            phrase = []
    return steps


class Chant:
    """One voice's path through one language's prayers."""

    def __init__(self, lang, rng):
        texts = list(PRAYERS[lang])
        rng.shuffle(texts)
        self.sylls = [s for t in texts for s in syllables(t)]
        self.steps = melody(self.sylls, rng)
        self.pos = rng.randrange(len(self.sylls))

    def next(self):
        s, final, stressed = self.sylls[self.pos]
        step = self.steps[self.pos]
        self.pos = (self.pos + 1) % len(self.sylls)
        return s, final, stressed, step


def schedule(lang_at, total, voice_index, tempo=1.0, start=0.0, rng=None, mode="dorian"):
    """Segments for one praise voice. lang_at(t) -> list of languages
    sounding at time t; voice i sings language i mod len(list)."""
    rng = rng or random.Random(0)
    chants = {}
    segs = []
    t = start
    prev_f0 = None
    beat = BEATS[voice_index] / tempo
    while t < total:
        langs = lang_at(t)
        lang = langs[voice_index % len(langs)]
        ch = chants.get(lang) or chants.setdefault(lang, Chant(lang, rng))
        phones, final, stressed, step = ch.next()
        f0 = step_to_hz(step + REGISTERS[voice_index], mode)
        dur = beat * (2.0 if final else 1.3 if stressed else 0.85)
        cons = [p for p, _ in phones if PHONES[p]["kind"] != V]
        vows = [p for p, _ in phones if PHONES[p]["kind"] == V]
        cdur = sum(min(PHONES[p]["dur"], 0.07) for p in cons)
        vdur = max(dur - cdur, 0.08)
        first = True
        for p, _ in phones:
            d = vdur / max(len(vows), 1) if PHONES[p]["kind"] == V else min(PHONES[p]["dur"], 0.07)
            segs.append(Seg(p, d, (prev_f0 if first and prev_f0 else f0, f0), tag=lang))
            first = False
        prev_f0 = f0
        t += cdur + vdur
        if final:
            rest = rng.uniform(0.15, 0.35) / tempo
            segs.append(Seg("sil", rest))
            t += rest
    return segs
