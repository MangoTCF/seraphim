"""The three praise voices.

While a sentence is spoken, three voices sing prayers whose language marks
tense: Biblical Aramaic (far past, gnomic), Koine Greek (near past) and
Ecclesiastical Latin (non-past). Each voice sings on its own: its own place in
the prayers, its own pace, in its own register of D dorian, phrase by phrase
on one of several chant formulas. They switch language at word boundaries and
pick each language's prayers up where they last left them.
"""

import random
from dataclasses import replace

from .phones import PHONES, V, tokenize_ipa
from .synth import Seg


def linger(segs, duration, semitones, *, backmask=False):
    """Carry the closing syllables into a rising tail in playback order."""
    ordered = segs[::-1] if backmask else segs
    end = next((i for i in range(len(ordered) - 1, -1, -1)
                if ordered[i].f0), None)
    if end is None:
        return segs, None
    phrase = ordered[:end + 1]
    start_pitch = phrase[-1].f0[0 if backmask else 1]
    # Keep whole phones and include the consonants before the oldest vowel.
    start = end
    elapsed = 0.0
    while start > 0 and elapsed < duration:
        elapsed += phrase[start].dur
        start -= 1
    while start > 0 and phrase[start - 1].tag == phrase[end].tag and (
            PHONES.get(phrase[start - 1].phone, {}).get("kind") != V):
        start -= 1
    closing = [s for s in phrase[start:] if s.f0 and s.tag == phrase[end].tag]
    scale = duration / sum(s.dur for s in closing)

    def pitch_at(t):
        return start_pitch * 2 ** (semitones * t / (12 * duration))

    tail = []
    cursor = 0.0
    for seg in closing:
        length = seg.dur * scale
        f0 = (pitch_at(cursor), pitch_at(cursor + length))
        tail.append(replace(seg, dur=length, f0=f0[::-1] if backmask else f0))
        cursor += length
    played = phrase + tail
    return (played[::-1] if backmask else played), sum(s.dur for s in phrase)

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

# Implementation extension: melodic signatures distinguish tense without adding
# prayer languages. Scale-relative shapes survive transposition and dialect mode.
TENSE_MOTIFS = {
    'farpast': (4, 2, 0),
    'gnomic': (4, 4, 4),
    'nearpast': (0, 1, 2),
    'nonpast': (2, 4, 2),
}
TENSE_CUES = {'farpast': 'descending', 'gnomic': 'steady', 'nearpast': 'rising', 'nonpast': 'arching',
              'aramaic': 'unspecified Aramaic tense'}


def time_spans(plans, voice_index, start, end):
    """Final-playback intervals, including lead-in and tail. Each word gets a cue."""
    from bisect import bisect_right
    starts = [p.start for p in plans]
    bounds = sorted({start, end, *(t for t in starts if start < t < end)})
    spans = []
    for a, b in zip(bounds, bounds[1:]):
        index = max(0, bisect_right(starts, (a + b) / 2) - 1)
        word = plans[index].word
        tenses = word.tenses or [{'latin': 'nonpast', 'greek': 'nearpast', 'aramaic': 'aramaic'}[lang] for lang in word.langs]
        # More than three simultaneous contexts need sequential subslots;
        # otherwise the fourth label would never reach a prayer voice.
        slots = (len(tenses) + 2) // 3
        for slot in range(slots):
            chosen = (slot * 3 + voice_index) % len(tenses)
            tense = tenses[chosen]
            lang = word.langs[chosen % len(word.langs)]
            spans.append(dict(start=a + (b-a) * slot / slots, end=a + (b-a) * (slot+1) / slots,
                              tense=tense, language=lang, word=index,
                              cue=TENSE_CUES.get(tense, 'unspecified tense')))
    return spans


def _scale_hz(step, mode):
    """Continuous scale degree, interpolated in log frequency."""
    import math
    lower = math.floor(step)
    fraction = step - lower
    a, b = step_to_hz(lower, mode), step_to_hz(lower + 1, mode)
    return a * (b / a) ** fraction


def motif_pitch(tense, progress, voice_index=0, mode='dorian'):
    """Pure cue pitch, useful for preview legends and numerical verification."""
    shape = TENSE_MOTIFS[tense]
    x = min(max(progress, 0), 1) * 2
    left = min(int(x), 1)
    fraction = x - left
    step = shape[left] + fraction * (shape[left + 1] - shape[left])
    return _scale_hz(step + REGISTERS[voice_index], mode)


def timed_schedule(spans, voice_index, tempo=1.0, rng=None, mode='dorian', backmask=False):
    """Chant fits exact final-time intervals, including backwards playback.

    Language order is mirrored before waveform reversal. Tense motifs are also
    pre-mirrored, so their audible direction and assignment remain grammatical.
    Syllables at boundaries fit the remaining slot rather than overrunning it.
    """
    from bisect import bisect_right
    rng = rng or random.Random(0)
    if not spans:
        return []
    chants, segs = {}, []
    previous = None
    for span in reversed(spans) if backmask else spans:
        lang = span['language']
        if lang not in chants:
            chants[lang] = Chant(lang, rng)
        span_duration = span['end'] - span['start']
        remaining = span_duration
        cue_duration = min(.42 / tempo, span_duration * .85)
        cue_start, cue_end = (span_duration - cue_duration, span_duration) if backmask else (0, cue_duration)
        first_in_span = len(segs)
        while remaining > 1e-9:
            # Stretch the last vowel into a tiny leftover slot instead of
            # clipping the onset of a whole new syllable to a few milliseconds.
            if remaining < .07 / tempo and len(segs) > first_in_span:
                vowel = next((s for s in reversed(segs[first_in_span:]) if PHONES.get(s.phone, {}).get('kind') == V), segs[-1])
                vowel.dur += remaining
                break
            phones, final, stressed, step = chants[lang].next()
            f0 = step_to_hz(step + REGISTERS[voice_index], mode)
            duration = BEATS[voice_index] / tempo * (2 if final else 1.3 if stressed else .85)
            consonants = [p for p, _ in phones if PHONES[p]['kind'] != V]
            vowels = [p for p, _ in phones if PHONES[p]['kind'] == V]
            cdur = sum(min(PHONES[p]['dur'] / tempo, .07 / tempo) for p in consonants)
            vdur = max(duration - cdur, .08 / tempo)
            durations = [vdur / max(len(vowels), 1) if PHONES[p]['kind'] == V else min(PHONES[p]['dur'] / tempo, .07 / tempo) for p, _ in phones]
            total = sum(durations)
            if total <= 0:
                break
            scale = min(1, remaining / total)
            for i, ((phone, _), d) in enumerate(zip(phones, durations)):
                segs.append(Seg(phone, d * scale, (previous if i == 0 and previous else f0, f0), tag=lang))
            previous = f0
            remaining = max(0, remaining - total * scale)
            if final and remaining > 1e-9:
                rest = min(remaining, rng.uniform(.15, .35) / tempo)
                elapsed = span_duration - remaining
                # A phrase breath must not swallow the identifying contour.
                if elapsed < cue_end and elapsed + rest > cue_start:
                    rest = max(0, cue_start - elapsed)
                if rest > 1e-9:
                    segs.append(Seg('sil', rest))
                    remaining -= rest

    origin, end = spans[0]['start'], spans[-1]['end']
    length = end - origin
    starts = [span['start'] for span in spans]
    # Split at cue control points so even a long vowel follows the whole shape.
    final_cuts = set()
    for span in spans:
        duration = min(.42 / tempo, (span['end'] - span['start']) * .85)
        final_cuts.update([span['start'], span['start'] + min(.025 / tempo, duration * .15),
                           span['start'] + duration / 2, span['start'] + duration * .85,
                           span['start'] + duration, span['end']])
    cuts = sorted((end - t if backmask else t - origin) for t in final_cuts)

    def mapped_pitch(frequency, when, span):
        elapsed = when - span['start']
        duration = min(.42 / tempo, (span['end'] - span['start']) * .85)
        if span['tense'] not in TENSE_MOTIFS or not 0 <= elapsed <= duration:
            return frequency
        attack = min(.025 / tempo, duration * .15)
        release = duration * .15
        weight = min(1, elapsed / max(attack, 1e-9), (duration - elapsed) / max(release, 1e-9))
        weight = weight * weight * (3 - 2 * weight)
        target = motif_pitch(span['tense'], elapsed / duration, voice_index, mode)
        return frequency * (target / frequency) ** weight

    out, cursor = [], 0.0
    for seg in segs:
        finish = cursor + seg.dur
        interior = cuts[bisect_right(cuts, cursor + 1e-9):bisect_right(cuts, finish - 1e-9)]
        points = [cursor, *interior, finish]
        for a, b in zip(points, points[1:]):
            if b - a <= 1e-10:
                continue
            f0 = seg.f0
            if f0:
                midpoint = end - (a + b) / 2 if backmask else origin + (a + b) / 2
                span = spans[max(0, min(len(spans) - 1, bisect_right(starts, midpoint) - 1))]
                def pitch(x):
                    base = f0[0] + (f0[1] - f0[0]) * ((x - cursor) / seg.dur)
                    return mapped_pitch(base, end - x if backmask else origin + x, span)
                f0 = (pitch(a), pitch(b))
            out.append(replace(seg, dur=b - a, f0=f0))
        cursor = finish
    # Remove accumulated floating-point residue without changing musical time.
    if out:
        out[-1].dur += length - sum(s.dur for s in out)
    return out
