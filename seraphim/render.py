"""Turn a parsed score into a 7-voice binaural recording."""

import random
from dataclasses import dataclass, field, replace
from typing import NamedTuple

import numpy as np

from . import choir, dialects, fx
from .phones import PHONES
from .score import MOUTHS, EXTRA
from .synth import SR, Seg, Voice, render

# The four primary mouths sit clockwise around the central eye (top-left,
# top-right, bottom-right, bottom-left); the praise mouths above and below.
# Each mouth at the masculine (-1) and feminine (+1) ends of the voice slider:
# (pitch Hz, vocal tract formant scale). Pitch moves geometrically so the
# mouths keep their intervals; 0 lands in the androgynous band. Voice quality
# moves too: feminine voices get a softer glottal pulse and more breath.
MOUTH_RANGE = {
    "top": ((131, 0.97), (262, 1.19)),
    "1": ((147, 1.00), (294, 1.22)),
    "2": ((110, 0.95), (220, 1.16)),
    "end": ((98, 0.93), (196, 1.13)),
}
QUALITY = dict(oq=(0.55, 0.70), breath=(0.06, 0.15))


def _lerp(a, b, t):
    return a + (b - a) * t


# Stable articulatory identities: not random per render or just pitch offsets.
MOUTH_CHARACTER = {
    'top': dict(jitter=.004, tilt=3800, coarticulation=.3, articulation=1.12),
    '1': dict(jitter=.005, tilt=3500, coarticulation=.4, articulation=1.06),
    '2': dict(jitter=.008, tilt=3000, coarticulation=.6, articulation=.92),
    'end': dict(jitter=.006, tilt=2700, coarticulation=.5, articulation=.86),
}

def mouth_voice(m, gender=0.0):
    """The voice of mouth m with gender in [-1 masculine, +1 feminine]."""
    t = (min(max(gender, -1), 1) + 1) / 2
    (f_m, s_m), (f_f, s_f) = MOUTH_RANGE[m]
    return Voice(m, f_m ** (1 - t) * f_f ** t, fscale=_lerp(s_m, s_f, t),
                 oq=_lerp(*QUALITY["oq"], t), breath=_lerp(*QUALITY["breath"], t), **MOUTH_CHARACTER[m])


def choir_voice(vi, gender=0.0):
    """Praise voice vi; returns (voice, pitch factor). The whole choir is
    transposed by up to half an octave either way, which keeps it in mode."""
    t = (min(max(gender, -1), 1) + 1) / 2
    v = CHOIR_VOICES[vi]
    return (Voice(v.name, v.f0, fscale=_lerp(0.98, 1.26, t) - 0.04 * vi, breath=_lerp(0.10, 0.18, t),
                  vibrato=v.vibrato, vib_rate=v.vib_rate, jitter=v.jitter, oq=_lerp(0.62, 0.72, t),
                  tilt=2400),
            2 ** (0.5 * gender))


MOUTH_VOICES = {m: mouth_voice(m) for m in MOUTH_RANGE}
MOUTH_POS = {"top": (-38, 24, 1.1), "1": (38, 24, 1.1), "2": (38, -22, 1.1), "end": (-38, -22, 1.1)}
CHOIR_VOICES = [
    Voice("praise-a", 293.7, fscale=1.2, breath=0.16, vibrato=0.006, vib_rate=5.6, jitter=0.004, oq=0.7),
    Voice("praise-b", 220.0, fscale=1.16, breath=0.14, vibrato=0.005, vib_rate=4.9, jitter=0.004, oq=0.7),
    Voice("praise-c", 146.8, fscale=1.1, breath=0.12, vibrato=0.005, vib_rate=5.2, jitter=0.004, oq=0.68),
]
CHOIR_POS = [(0, 55, 2.2), (-18, -48, 2.2), (18, -48, 2.2)]

BREAK_GAP = 0.08
WORD_GAP = 0.025           # words run into each other, with soft edges
SENTENCE_GAP = 0.5
EDGE_FADE = 0.012          # fade at each line's edges, so words join without clicks
MAX_STRETCH = 2.6          # for the elastic segments (vowels, sonorants, fricatives)
ELASTIC = {"vowel", "nasal", "approx", "fric", "aspirate"}     # not trills: a long trill croaks
LEAD_IN = 1.6      # room for 4D swells that arrive before the first word
TAIL = 3.0


@dataclass
class Options:
    choir: bool = True
    prayer_time: bool = True  # melodic tense signatures, aligned even in backmasked choirs
    syllable_blend: float = 0.5  # 0 discrete syllables .. 1 strongly connected
    mouth_blend: dict = None    # independent mouth/prayer overrides; missing means inherit
    transitions: float = 1.0  # 0 linear ramps .. 1 smooth articulatory motion
    space: bool = True
    choir_level: float = 0.42
    reverb_mix: float = 0.28  # mouths' send into the room (the choir sends 1.4)
    room: str = None          # reverb preset (see fx.ROOMS); default the score's @room or cathedral
    reverb: float = None      # wet level, 1 = the room's normal amount, 0 = dry
    reverb_time: float = None # RT60 override, seconds
    reverb_tone: float = None # 0 bright .. 1 dark
    predelay: float = None    # seconds
    jobs: int = 0             # parallel workers, 0 = one per core
    reverse_4d: bool = False
    seed: int = 0
    glitter: float = 1.0      # extra-bright glitter level, 0 = off
    hum: float = 0.3          # closed and null mouths hum [m] at this level, 0 = silent
    prayer_tail: float = 2.4  # seconds of sustained prayer after the last phrase
    prayer_rise: float = 7.0  # semitones over the sustained prayer
    sample_banks: dict = None  # bank IDs by mouth, praise-1/2/3, choir or all
    sample_approximation: bool = True  # permit documented nearest-phoneme mappings
    voice: dict = None        # gender per mouth / 'choir', -1 masculine .. +1 feminine
    dialect: str = None       # overrides the score's @dialect
    knobs: dict = None        # dialect knob overrides, e.g. {'growl': 0.9}
    tones: dict = None        # tonal markers applied to every word, e.g. {'pain': 0.8}
    master: bool = True        # normalize and gently saturate the final mix
    keep_stems: bool = True    # disable when only the stereo mix is needed


class WordPlan(NamedTuple):
    word: object
    start: float
    lines: dict
    duration: float


@dataclass
class RenderPlan:
    options: Options
    tempo: float
    dialect: object
    knobs: dict
    gender: dict
    roles: dict
    voices: dict
    mouth_tones: dict
    tones: list
    words: list
    sentences: list
    hums: dict
    flags: dict
    total: float
    room: object
    reverb_amount: float
    sample_report: dict = field(default_factory=dict)
    vowel_brightness: dict = field(default_factory=dict)

    def summary(self):
        from dataclasses import asdict
        from .legato import amount, CHANNELS
        return dict(syllable_blend={c: amount(self.options, c) for c in CHANNELS}, options=asdict(self.options), sample_banks=self.sample_report, tempo=self.tempo,
                    dialect=asdict(self.dialect), voice=self.gender, seconds=self.total,
                    room=asdict(self.room), reverb=self.reverb_amount,
                    words=[dict(index=i + 1, start=w.start, duration=w.duration, tenses=w.word.tenses,
                                sentence_start=w.word.sentence_start,
                                mouths={m: dict(dialect=self.roles[(i, m)].name,
                                                tones=self.mouth_tones[(i, m)],
                                                seconds=sum(s.dur for s in w.lines.get(m, [])))
                                        for m in MOUTHS}) for i, w in enumerate(self.words)])


STOPLIKE = {"stop", "glottal"}


def line_segments(ml, tempo, rng=None, moan=0.0, final=False, formant_blend=0.0):
    """Segments for one mouth line, as connected speech: no pauses between
    tokens (only at morpheme breaks), each token its own loudness, durations
    a little uneven, the last token softer. The last word of a sentence
    slows down. Moaning stretches the vowels, slurs the stops and ends the
    line on a sigh."""
    rng = rng or np.random.default_rng(0)
    segs = []
    phon = [i for i, t in enumerate(ml.tokens) if t.kind == "phoneme"]
    for i, t in enumerate(ml.tokens):
        if t.kind == "break":
            if (formant_blend and t.text in ("-", "–") and segs
                    and i + 1 < len(ml.tokens) and ml.tokens[i + 1].kind == "phoneme"):
                previous = segs[-1].phone
                kind = PHONES.get(previous, {}).get("kind")
                gap = BREAK_GAP / tempo * (1 - formant_blend)
                if gap > 0:
                    if kind in ("vowel", "nasal", "approx", "trill", "fric", "aspirate"):
                        segs.append(Seg("_join", gap, join_from=previous))
                    else:
                        segs.append(Seg("sil", gap))
                continue
            segs.append(Seg("sil", BREAK_GAP / tempo))
            continue
        last = phon and i == phon[-1]
        amp = rng.uniform(0.82, 1.08) * (0.85 if last else 1.0)
        for p in t.ipa:
            kind = PHONES[p]["kind"]
            d = PHONES[p]["dur"] / tempo * rng.lognormal(0, 0.07)
            if kind == "vowel" and final and last:
                d *= 1.3                    # final lengthening
            if moan and kind == "vowel":
                d *= 1 + 1.1 * moan
            elif moan and kind in STOPLIKE:
                d *= 1 - 0.3 * moan
            segs.append(Seg(p, d, tag=i, amp=amp))
    if moan > 0.2:
        segs.append(Seg("h", (0.08 + 0.2 * moan) / tempo, amp=0.55))       # a sigh
    return segs


CONTOURS = {
    "fall": lambda k: 1.08 - 0.18 * k,
    "hat": lambda k: 1.0 + 0.12 * np.sin(np.pi * min(k * 1.3, 1)) - 0.1 * k,
    "rise-fall": lambda k: 0.97 + 0.16 * np.sin(np.pi * k) - 0.06 * k,
}
HIGH_VOWELS = set("iuyɪʊ")
LOW_VOWELS = set("aæɔ")


def micro(segs):
    """Micro-prosody, the involuntary bits that make speech sound alive:
    high vowels a touch higher, low ones lower; after a voiceless consonant
    the pitch starts a little high, after a voiced one a little low."""
    prev = None
    for s in segs:
        p = PHONES.get(s.phone)
        if p and p["kind"] == "vowel" and s.f0:
            a, b = s.f0
            k = 1.04 if s.phone in HIGH_VOWELS else 0.97 if s.phone in LOW_VOWELS else 1.0
            onset = 1.0
            if prev and prev["kind"] in ("stop", "fric", "aspirate"):
                onset = 1.05 if not prev.get("voiced", False) else 0.96
            s.f0 = (a * k * onset, b * k)
        if p:
            prev = p
    return segs


def contour(segs, voice, t0, s0, s1, shape, wobble, accents, prev_end=None, glide=0.06):
    """Pitch for a word's segments on its sentence's contour: x runs from the
    sentence's start (s0) to its end (s1), so the declination spans the whole
    sentence. The word starts where this mouth's last word ended and glides
    to the contour, so pitch flows across word boundaries."""
    span = max(s1 - s0, 1e-3)
    t = t0
    for s in segs:
        def at(x):
            k = min(max((x - s0) / span, 0), 1)
            return voice.f0 * (shape(k) + wobble[int(min(k, 0.999) * len(wobble))])
        bump = 1.09 if s.tag in accents else 1.0
        s.f0 = (at(t) * bump, at(t + s.dur) * bump)
        t += s.dur
    if prev_end:
        # Portamento from the previous word over the first ~60 ms.
        acc = 0.0
        for s in segs:
            if acc >= glide:
                break
            w0 = 1 - acc / glide
            w1 = max(1 - (acc + s.dur) / glide, 0)
            s.f0 = (s.f0[0] * (1 - w0) + prev_end * w0, s.f0[1] * (1 - w1) + prev_end * w1)
            acc += s.dur
    return segs


def moanify(segs, moan, rng, grab=0.0):
    """Moaning: each long vowel becomes a swell, its pitch sliding up and
    back down by a few semitones while its loudness rises and falls. With
    grab, the swell scoops up from below and grows toward its end instead of
    fading: it pulls you in."""
    out = []
    for s in segs:
        if PHONES.get(s.phone, {}).get("kind") != "vowel" or s.dur < 0.08:
            out.append(s)
            continue
        a, b = s.f0
        u = moan * rng.uniform(0.06, 0.2)
        mid = (a + b) / 2
        scoop = 2 ** (-grab * rng.uniform(1.5, 3.5) / 12)          # start up to ~3 st below
        pts = [a * scoop, mid * (1 + u), mid * (1 + 0.4 * u), b * (1 - 0.3 * u * (1 - grab))]
        amps = [(0.8 - 0.25 * grab), 1.0, (0.75 + 0.4 * grab)]
        for k, (frac, amp) in enumerate(zip((0.3, 0.4, 0.3), amps)):
            out.append(Seg(s.phone, s.dur * frac, (pts[k], pts[k + 1]), s.tag, s.amp * amp))
    return out


def fit(segs, target):
    """Stretch a mouth's line to the word's length. Vowels and other
    sustainable sounds absorb the stretch; stop closures and bursts keep
    their length, so the line stays crisp instead of slowing down evenly."""
    elastic = [s for s in segs if PHONES.get(s.phone, {}).get("kind") in ELASTIC]
    fixed = sum(s.dur for s in segs) - sum(s.dur for s in elastic)
    flex = sum(s.dur for s in elastic)
    if flex <= 0:
        return segs
    factor = min(max((target - fixed) / flex, 1.0), MAX_STRETCH)
    for s in elastic:
        s.dur *= factor
    return segs


# ---------------------------------------------------------------- tones
# Tonal markers (tone=pain:0.9,... on a word) say how a word is said. They
# don't change what it means; they change the voice, the way pain, fear and
# anger change a real one.

def word_tones(w, score, opts, dia=None):
    """A word's tones. The dialect's default (seraphim: condescending) is
    replaced by the score's @tone; a word's own markers replace both (a
    screaming angel has stopped being condescending); --tone adds on top.
    'neutral' anywhere clears everything."""
    from .score import parse_tones
    base = parse_tones(dia.tone) if dia is not None and dia.tone else {}
    if "tone" in score.meta:
        base = parse_tones(score.meta["tone"])
    t = dict(w.tones) if w.tones else dict(base)
    cli = opts.tones or {}
    if "neutral" in cli or "neutral" in t:
        t = {}
    t.update({k: v for k, v in cli.items() if k != "neutral"})
    return t


def tone_timing(segs, tones):
    """Pain and screams stretch the vowels into cries; anger and fear hurry
    the consonants; screams and pain are louder, whimpers softer."""
    if not tones:
        return segs
    pain, scream, anger, fear, whimper = (tones.get(k, 0) for k in ("pain", "scream", "anger", "fear", "whimper"))
    smug = tones.get("condescend", 0)
    vk = 1 + 0.6 * pain + 1.0 * scream - 0.15 * anger + 0.35 * smug     # unhurried, drawn-out vowels
    ck = 1 - 0.2 * anger - 0.1 * fear + 0.1 * smug
    ak = 1 + 0.4 * pain + 0.8 * scream + 0.4 * anger - 0.4 * whimper
    for x in segs:
        kind = PHONES.get(x.phone, {}).get("kind")
        if kind == "vowel":
            x.dur *= vk
        elif kind:
            x.dur *= ck
        x.amp *= ak
    return segs


def stammer(segs, rng, fear=0.5):
    """'I... I...': the first syllable, started and broken off, once or twice."""
    head = []
    for x in segs:
        head.append(x)
        if PHONES.get(x.phone, {}).get("kind") == "vowel":
            break
    out = []
    for _ in range(2 if fear > 0.5 else 1):
        out += [Seg(x.phone, x.dur * 0.8, None, x.tag, x.amp * 0.85) for x in head]
        out.append(Seg("sil", rng.uniform(0.18, 0.32)))
    return out + segs


def tone_pitch(segs, tones, rng, base=None, final=False):
    """Pitch under strain. Pain pushes the voice up and makes each vowel wail
    downward, with sudden upward cracks where the voice breaks; a scream
    goes higher still and arcs; fear raises it a little; a whimper catches
    and sinks."""
    if not tones:
        return segs
    pain, scream, anger, fear, whimper = (tones.get(k, 0) for k in ("pain", "scream", "anger", "fear", "whimper"))
    smug = tones.get("condescend", 0)
    if smug:
        segs = condescend(segs, smug, rng, base, final)
    lift = 2 ** ((6 * pain + 12 * scream + 2 * anger + 3 * fear - 2 * whimper) / 12)
    out = []
    for x in segs:
        if not x.f0:
            out.append(x)
            continue
        a, b = x.f0[0] * lift, x.f0[1] * lift
        if PHONES.get(x.phone, {}).get("kind") == "vowel":
            b *= 2 ** (-(3 * pain + 4 * whimper) / 12)
            if scream:
                mid = (a + b) / 2 * 2 ** (scream * rng.uniform(1, 3) / 12)
                out += [Seg(x.phone, x.dur * 0.45, (a, mid), x.tag, x.amp),
                        Seg(x.phone, x.dur * 0.55, (mid, b), x.tag, x.amp)]
                continue
            if x.dur > 0.12 and rng.random() < 0.4 * (pain + scream):
                # The voice cracks: a sudden jump up, held briefly, then back.
                k = rng.uniform(0.25, 0.55)
                c = min(rng.uniform(0.06, 0.11), x.dur * 0.4)
                pre = x.dur * k
                up = 2 ** (rng.uniform(5, 9) / 12)
                mid = a + (b - a) * k
                out += [Seg(x.phone, pre, (a, mid), x.tag, x.amp),
                        Seg(x.phone, c, (mid * up, mid * up), x.tag, x.amp * 1.1),
                        Seg(x.phone, x.dur - pre - c, (mid, b), x.tag, x.amp)]
                continue
            if whimper and x.dur >= .085:
                # A brief loss of voicing under the upward catch, followed by
                # a weaker vowel release. Keep the spoken rhythm and tags.
                catch_at = rng.uniform(.23, .36)
                release_at = catch_at + .18
                peak = a * 2 ** (whimper * rng.uniform(3, 5) / 12)
                release = peak + (b - peak) * .55
                out.extend((
                    replace(x, dur=x.dur * catch_at, f0=(a, peak)),
                    replace(x, dur=x.dur * (release_at - catch_at), f0=(peak, release),
                            amp=x.amp * (1 - .65 * whimper)),
                    replace(x, dur=x.dur * (1 - release_at), f0=(release, b),
                            amp=x.amp * (1 - .4 * whimper)),
                ))
                continue
        out.append(replace(x, f0=(a, b)))
    return out


def tone_gain(tones):
    """Loudness as a gain after rendering (each render is normalized, so
    per-segment amplitudes only shape a word from inside)."""
    if not tones:
        return 1.0
    g = lambda k: tones.get(k, 0)
    return max(1 + 0.5 * g("pain") + 1.4 * g("scream") + 0.5 * g("anger") - 0.45 * g("whimper")
               - 0.12 * g("condescend"), 0.3)


def condescend(segs, c, rng, base=None, final=False):
    """Condescension: exaggerated, sing-song pitch (the swings around the
    voice's centre stretched up to 1.8x, a lilt on long vowels) and a closed,
    final fall at the end of a sentence."""
    base = base or np.median([x.f0[0] for x in segs if x.f0] or [1.0])
    total = sum(x.dur for x in segs) or 1
    out, t = [], 0.0
    for x in segs:
        if not x.f0:
            out.append(x)
            t += x.dur
            continue
        def shape(f, at):
            f = base * (f / base) ** (1 + 0.8 * c)                     # wider range
            if final:
                f *= 2 ** (-4 * c * (at / total) ** 1.5 / 12)         # the matter is closed
            return f
        a, b = shape(x.f0[0], t), shape(x.f0[1], t + x.dur)
        if PHONES.get(x.phone, {}).get("kind") == "vowel" and x.dur > 0.1:
            mid = (a + b) / 2 * 2 ** (c * rng.uniform(1, 2.5) / 12)  # the lilt
            out += [Seg(x.phone, x.dur * 0.5, (a, mid), x.tag, x.amp), Seg(x.phone, x.dur * 0.5, (mid, b), x.tag, x.amp)]
        else:
            out.append(Seg(x.phone, x.dur, (a, b), x.tag, x.amp))
        t += x.dur
    return out


def tone_voice(v, tones):
    """Voice quality: pain presses and roughens the folds and catches the
    breath; a scream opens the jaw and turns harsh; fear trembles;
    anger presses; a whimper goes breathy and thin."""
    if not tones:
        return v
    pain, scream, anger, fear, whimper = (tones.get(k, 0) for k in ("pain", "scream", "anger", "fear", "whimper"))
    smug = tones.get("condescend", 0)
    return replace(v,
                   oq=max(v.oq - 0.12 * pain - 0.15 * scream - 0.1 * anger + 0.1 * whimper + 0.05 * smug, 0.35),
                   fry=max(v.fry, 0.3 * smug),                           # the dismissive creak
                   jitter=v.jitter * (1 + 4 * pain + 3 * scream + 2 * fear + 2 * whimper),
                   roar=min(1.0, v.roar + 0.35 * pain + 0.6 * scream + 0.15 * anger),
                   breath=v.breath + 0.15 * pain + 0.45 * whimper + 0.15 * fear + 0.1 * smug,
                   voicing=v.voicing * (1 - 0.3 * whimper),
                   open=max(v.open, scream, 0.3 * pain),
                   vibrato=max(v.vibrato, 0.035 * fear, 0.065 * whimper),
                   vib_rate=7.5 if fear else 5.5 if whimper else v.vib_rate)


BREAKS = {"break", "crack", "snap", "shatter", "tear", "rip", "split"}
WINGS = {"wing", "feather", "pinion"}


def pain_sounds(score, plans, tones, opts, n):
    """At the ears: a crack inside the wing on breaking words, a rustle of
    feathers on wing words, a sobbing breath in before painful words."""
    import re
    from .lexicon import score_lexicon
    from .reading import decode_line
    lx = score_lexicon(score)
    index = lx.by_signature()
    events = []
    rng = _rng(opts.seed, 11)
    for wi, (w, start, lines, length) in enumerate(plans):
        hurt = max(tones[wi].get("pain", 0), tones[wi].get("scream", 0))
        for m in MOUTHS:
            d = decode_line(w.mouths[m], lx, index)
            if d is None:
                continue
            parts = set(re.split(r"[-.]", d.gloss))
            if parts & BREAKS:
                events.append((start + length * 0.6, "crack", m, 0.6 + 0.4 * hurt))
            if parts & WINGS:
                events.append((start + length * 0.3, "rustle", m, 0.5))
        if hurt >= 0.5 and rng.random() < 0.6:
            events.append((start - 0.35, "gasp", MOUTHS[wi % len(MOUTHS)], 0.4 * hurt))
    tracks = {m: np.zeros(n) for m in MOUTHS}
    last = {}
    for k, (when, kind, m, level) in enumerate(sorted(events)):
        if when - last.get(kind, -9) < 0.4:
            continue
        last[kind] = when
        place(tracks[m], fx.FOLEY[kind](_rng(opts.seed, 12, k)) * level * 0.22, max(when, 0))
    return tracks


def falter(segs, spans, t0, length, backmask, rng):
    """The praise breaks while a mouth is in pain: the chant sags, cracks and
    drops out. spans are (start, end, intensity) on the final timeline; a
    backmasked choir is reversed afterwards, so its times are mirrored."""
    if not spans:
        return segs
    t = 0.0
    for x in segs:
        mid = t + x.dur / 2
        when = t0 + (length - mid if backmask else mid)
        t += x.dur
        p = max((k for a, b, k in spans if a <= when <= b), default=0)
        if not p or not x.f0:
            continue
        sag = 2 ** (-(1.5 + 1.5 * rng.random()) * p / 12)
        crack = 2 ** (4 / 12) if rng.random() < 0.25 * p else 1.0
        x.f0 = (x.f0[0] * sag * crack, x.f0[1] * sag)
        x.amp *= 0.0 if rng.random() < 0.12 * p else rng.uniform(1 - 0.6 * p, 1)
    return segs


def hum_segments(length, moan, rng):
    """A closed mouth vocalizing is a hum: [m]. Moaning turns it into a
    swelling, sliding 'mmm' (pitch is filled in by the prosody pass)."""
    if not moan:
        return [Seg("m", length)]
    return [Seg("m", length * 0.35, amp=0.8), Seg("m", length * 0.4, amp=1.0), Seg("m", length * 0.25, amp=0.7)]


def hum_glide(segs, moan, rng):
    """The hum's own swell on top of the contour."""
    if not moan or len(segs) < 3:
        return segs
    u = moan * rng.uniform(0.08, 0.2)
    for s, (ka, kb) in zip(segs, ((1, 1 + u), (1 + u, 1 + 0.5 * u), (1 + 0.5 * u, 1 - 0.2 * u))):
        s.f0 = (s.f0[0] * ka, s.f0[1] * kb)
    return segs


def edges(sig, fade=EDGE_FADE, *, left=None, right=None):
    """Soft edges so consecutive words join without clicks."""
    for side, duration in [('left', fade if left is None else left), ('right', fade if right is None else right)]:
        r = min(int(duration * SR), len(sig) // 2)
        if r:
            ramp = .5 - .5 * np.cos(np.linspace(0, np.pi, r))
            if side == 'left':
                sig[:r] *= ramp
            else:
                sig[-r:] *= ramp[::-1]
    return sig


def breathe(v, amount):
    """Breathiness: more air through the folds, a softer pulse, darker highs."""
    if not amount:
        return v
    return replace(v, breath=v.breath + 0.45 * amount, oq=min(v.oq + 0.1 * amount, 0.85),
                   tilt=min(v.tilt, 3500 - 1300 * amount), voicing=v.voicing * (1 - 0.3 * amount))


def parse_voice(spec):
    """'0.7' or 'top=1,1=0.5,2=-0.3,end=0,choir=1' -> {'all': .., mouth: ..}.
    Words work too: masculine, androgynous, feminine."""
    named = {"masculine": -1.0, "male": -1.0, "androgynous": 0.0, "feminine": 1.0, "female": 1.0}
    out = {"all": 0.0}
    for part in str(spec).replace(" ", "").split(","):
        if not part:
            continue
        key, _, val = part.rpartition("=")
        v = named.get(val.lower()) if val.lower() in named else float(val)
        if not -1 <= v <= 1:
            raise ValueError(f"voice {v} is outside -1 (masculine) .. +1 (feminine)")
        if key and key not in (*MOUTHS, "all", "choir"):
            raise ValueError(f"unknown voice key {key!r}; expected top, 1, 2, end, choir or all")
        out[key or "all"] = v
    return out


HUNGRY = {"bite", "eat", "chew", "swallow", "lick", "tear", "devour", "taste", "consume", "hunger",
          "drink", "gnaw", "suck", "flesh", "blood", "neck", "throat", "Adam's_apple", "obsession"}
TENDER = {"love", "sweet", "heart", "soul", "kiss", "desire", "want", "pleasure", "beloved",
          "darling", "embrace", "one"}
SLURPY = {"lick", "eat", "swallow", "suck", "drink", "taste", "devour", "chew"}


def hungry_tender(score, plans):
    """Which mouth lines carry a hungry or tender morpheme, found by decoding
    them through the lexicon (by phoneme value, so respelling doesn't matter).
    Returns {(word, mouth): (kind, glosses)}."""
    import re
    from .lexicon import score_lexicon
    from .reading import decode_line
    lx = score_lexicon(score)
    index = lx.by_signature()
    out = {}
    for wi, (w, *_rest) in enumerate(plans):
        for m in MOUTHS:
            d = decode_line(w.mouths[m], lx, index)
            if d is None:
                continue
            parts = set(re.split(r"[-.]", d.gloss))
            if parts & HUNGRY:
                out[(wi, m)] = ("hungry", parts)
            elif parts & TENDER:
                out[(wi, m)] = ("tender", parts)
    return out


def grab_curves(plans, sentences, flags, role, n):
    """How far each mouth has pulled in toward the listener's ear, 0..~0.9,
    over time: drifting in over each sentence, lurching closer on hungry and
    tender words, easing back between sentences."""
    rate = 100
    m_ = int(n / SR * rate) + 2
    t = np.arange(m_) / rate
    base = np.zeros(m_)
    for idxs in sentences:
        s0 = plans[idxs[0]][1]
        s1 = plans[idxs[-1]][1] + plans[idxs[-1]][3]
        inside = (t >= s0) & (t <= s1)
        base[inside] = np.maximum(base[inside], 0.15 + 0.75 * (t[inside] - s0) / max(s1 - s0, 1e-3))
        after = t > s1
        base[after] = np.maximum(base[after], 0.9 * np.exp(-(t[after] - s1) / 0.5))
    out = {}
    for m in MOUTHS:
        # How much this mouth grabs, word by word (it changes when a
        # nephilim mouth changes sides), eased so nothing jumps.
        amount = np.full(m_, role[(0, m)].grab)
        for wi, (_w, start, *_r) in enumerate(plans):
            amount[t >= start] = role[(wi, m)].grab
        if np.ptp(amount):
            k = int(0.3 * rate)
            amount = np.convolve(np.pad(amount, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "same")[k:-k]
        bump = np.zeros(m_)
        for (wi, mm), (kind, _) in flags.items():
            if mm != m:
                continue
            g = plans[wi][1]
            dt = np.clip(t - g, 0, None)
            bump += np.where(t >= g, 0.6 * (1 - np.exp(-dt / 0.08)) * np.exp(-dt / 1.2), 0)
        curve = np.clip(amount * (base + bump), 0, 0.95)
        out[m] = np.interp(np.arange(n) / SR, t, curve)
    return out


def foley_tracks(plans, sentences, flags, role, opts, n):
    """Mouth sounds at the ears: teeth snapping after hungry words and a wet
    slurp after eating ones (hunger), a kiss before tender words and a
    breath in before each sentence (grab)."""
    events = []
    for (wi, m), (kind, parts) in flags.items():
        start, length = plans[wi][1], plans[wi][3]
        R = role[(wi, m)]
        if kind == "hungry" and R.hunger:
            events.append((start + length - 0.03, "snap", m, R.hunger))
            if parts & SLURPY:
                events.append((start + length + 0.07, "slurp", m, 0.7 * R.hunger))
        if kind == "tender" and R.grab:
            events.append((start - 0.06, "kiss", m, 0.6 * R.grab))
    for si, idxs in enumerate(sentences):
        m = MOUTHS[si % len(MOUTHS)]
        if role[(idxs[0], m)].grab:
            events.append((plans[idxs[0]][1] - 0.45, "gasp", m, 0.5 * role[(idxs[0], m)].grab))
    tracks = {m: np.zeros(n) for m in MOUTHS}
    last = {}
    for k, (when, kind, m, level) in enumerate(sorted(events)):
        if when - last.get((kind, m), -9) < 0.3:
            continue                    # no machine-gun of identical sounds
        last[(kind, m)] = when
        sound = fx.FOLEY[kind](_rng(opts.seed, 10, k))
        place(tracks[m], sound * level * 0.22, max(when, 0))
    return tracks


def place(track, sig, start):
    a = int(round(start * SR))
    if a < 0:
        sig, a = sig[-a:], 0
    b = min(a + len(sig), len(track))
    track[a:b] += sig[: b - a]


# ---------------------------------------------------------------- jobs
# Every mouth line, hum and praise voice is rendered as an independent job
# with its own random generator, seeded from (seed, word, mouth), so the
# result is the same whether the jobs run one by one or in parallel.

def _rng(seed, *key):
    return np.random.default_rng([seed & 0xFFFFFFFF, *key])


def render_voice(segs, voice, rng, opts, channel, default_f0=None):
    from .samplebank import selected
    from .legato import amount
    voice = replace(voice, syllable_blend=amount(opts, channel))
    bank = selected(opts.sample_banks, channel)
    if bank:
        from .samplebank import render as sample_render
        return sample_render(segs, voice, rng, bank, opts.sample_approximation, default_f0)
    return render(segs, voice, rng, default_f0=default_f0)


def _bank_coverage(segs, opts, channel):
    from .samplebank import coverage, selected
    bank = selected(opts.sample_banks, channel)
    return coverage(bank, [s.phone for s in segs], opts.sample_approximation) if bank else None


def _record_bank(plan, channel, report):
    if not report:
        return
    entry = plan.sample_report.setdefault(channel, dict(bank=report['bank'], name=report['name'], counts={}, mapping={}))
    entry['mapping'].update(report['mapping'])
    for kind, phones in report['counts'].items():
        counts = entry['counts'].setdefault(kind, {})
        for phone, count in phones.items():
            counts[phone] = counts.get(phone, 0) + count


def _line_job(job, prepared=None, join_left=0, join_right=0):
    """Render one mouth's line for one word: voice, growl layer, whisper,
    brightness, damage, 4D movement. Segments arrive with their pitch
    already planned (see the prosody pass). Returns the pieces to place."""
    (wi, mi, m, segs, voice, fem, wound, dia, opts, levels, moved, start, surge, gain) = job
    rng = _rng(opts.seed, 1, wi, mi)
    if surge:
        # Hungry words: the growl and roar surge for this line.
        voice = replace(voice, growl=min(1.0, voice.growl + surge), roar=min(1.0, voice.roar + 0.4 * surge))
    r = prepared if prepared is not None else render_voice(segs, voice, rng, opts, m)
    if prepared is None:
        r.audio = fx.deess(r.audio)
    out = {"m": m, "start": start, "main": None, "moved": None, "whisper": None, "bank_coverage": _bank_coverage(segs, opts, m)}
    if voice.growl:
        # The growl's body: a second, rougher throat an octave down, kept
        # under the voice (less so toward feminine). Heavy jitter keeps it
        # from locking to exactly half the voice's pitch, whose steady
        # beating pulses like a croak.
        sub_v = replace(voice, growl=0.0, fry=0.0, roar=min(1.0, voice.roar + 0.3), jitter=0.03,
                        fscale=voice.fscale * 0.9, breath=voice.breath + 0.1)
        sub = render_voice([Seg(x.phone, x.dur, (x.f0[0] / 2, x.f0[1] / 2) if x.f0 else None, x.tag, x.amp)
                      for x in segs], sub_v, rng, opts, m).audio
        sub = fx.sosfilt(fx.sos_lowpass(1600), sub)
        k = min(len(sub), len(r.audio))
        r.audio[:k] += 0.5 * voice.growl * (1 - 0.6 * fem) * sub[:k]
    if dia.whisper:
        # A whispered double, breathed right at the listener's ears.
        wv = replace(voice, voicing=0.0, breath=1.0, growl=0.0, roar=0.0, fry=0.0)
        whisp = render_voice(segs, wv, rng, opts, m).audio
        whisp *= dia.whisper * 0.8 * (np.sqrt(np.mean(r.audio ** 2)) / (np.sqrt(np.mean(whisp ** 2)) + 1e-9))
        out["whisper"] = edges(whisp)
    octave = None
    if EXTRA in levels.values():
        up = [Seg(x.phone, x.dur, (x.f0[0] * 2, x.f0[1] * 2), x.tag) for x in segs]
        octave = render_voice(up, voice, rng, opts, m).audio
    sig = fx.brighten(r.audio, r.spans, levels, octave, rng, glitter=opts.glitter)
    if dia.damaged:
        sig = fx.wound(sig, rng, **wound)
    sig = edges(sig, left=EDGE_FADE*(1-join_left), right=EDGE_FADE*(1-join_right)) * gain
    if out["whisper"] is not None:
        out["whisper"] = out["whisper"] * gain
    vowel_tags = {seg.tag for seg in segs if PHONES.get(seg.phone, {}).get("kind") == "vowel"}
    brightness = [(a, min(b, len(sig)), levels[tag]) for tag, a, b in r.spans
                  if tag in vowel_tags and tag in levels and a < min(b, len(sig))]
    if moved and opts.reverse_4d:
        brightness = [(len(sig) - b, len(sig) - a, level) for a, b, level in brightness]
    out["vowel_brightness"] = brightness
    if moved:
        # The mouth stays shut; the morpheme materialises in front of it,
        # its echo arriving from the future before the sound does.
        if opts.reverse_4d:
            sig = sig[::-1]
        swell, lead = fx.temporal_swell(sig, fx.short_ir(rng=_rng(opts.seed, 9)))
        body = swell * 0.55
        body[lead:lead + len(sig)] += sig
        out["moved"] = (body, lead / SR)
    else:
        out["main"] = sig
    return out


def _speech_groups(jobs, plans):
    """Keep connected words in one excitation stream, with bounded job memory."""
    from .legato import amount
    by_mouth = {m: [] for m in MOUTHS}
    for job in jobs:
        by_mouth[job[2]].append(job)
    groups = []
    for mouth_jobs in by_mouth.values():
        current = []
        for job in mouth_jobs:
            compatible = False
            if current and amount(job[8], job[2]) > 0:
                previous = current[-1]
                gap = job[11] - previous[11] - sum(s.dur for s in previous[3])
                compatible = (job[0] == previous[0]+1 and not plans[job[0]].word.sentence_start
                              and not job[10] and not previous[10] and not job[12] and not previous[12]
                              and job[4] == previous[4] and job[5:8] == previous[5:8]
                              and job[13] == previous[13] and -.00001 <= gap <= .06
                              and job[11] + sum(s.dur for s in job[3]) - current[0][11] <= 12)
            if current and not compatible:
                groups.append(current); current = []
            current.append(job)
        if current:
            groups.append(current)
    return groups


def _speech_job(group, hum=False):
    """Render phrase-continuous source once, then retain word-specific effects."""
    finish_line = _hum_line if hum else _line_job
    if len(group) == 1:
        return [finish_line(group[0])]
    from .legato import amount
    from .synth import Rendered
    first = group[0]
    opts, mouth, voice = first[8], first[2], first[4]
    strength = amount(opts, mouth)
    merged, offsets, connections = [], [], []
    origin = first[11]
    origin_frame = int(round(origin * SR))
    sustain = {'vowel', 'nasal', 'approx', 'trill', 'fric', 'aspirate'}
    for index, job in enumerate(group):
        if index:
            previous = group[index-1]
            gap = max(0, job[11] - previous[11] - sum(s.dur for s in previous[3]))
            last = previous[3][-1]
            connected = (gap > 1e-6 and PHONES.get(last.phone, {}).get('kind') in sustain
                         and job[3][0].phone in PHONES)
            connections.append(connected)
            if gap > 1e-9:
                start_pitch = last.f0[1] if last.f0 else voice.f0
                end_pitch = job[3][0].f0[0] if job[3][0].f0 else start_pitch
                merged.append(Seg('_join' if connected else 'sil', gap,
                                  (start_pitch, end_pitch), amp=1.0, join_from=last.phone if connected else None))
        offsets.append(job[11] - origin)
        merged.extend(replace(s, tag=(index, s.tag) if s.tag is not None else None) for s in job[3])
    rng = _rng(opts.seed, 1, first[0], first[1])
    raw = render_voice(merged, voice, rng, opts, mouth)
    if not hum:
        raw.audio = fx.deess(raw.audio)
    results = []
    for index, job in enumerate(group):
        begin = int(offsets[index] * SR)
        length = int(sum(s.dur for s in job[3]) * SR)
        spans = [(tag[1], max(0,a-begin), min(length,b-begin)) for tag,a,b in raw.spans
                 if tag[0] == index and b > begin and a < begin+length]
        prepared = Rendered(np.pad(raw.audio[begin:begin+length].copy(),
                                  (0,max(0,begin+length-len(raw.audio)))), spans)
        piece = finish_line(job, prepared, 1 if index and connections[index-1] else 0,
                          1 if index < len(connections) and connections[index] else 0)
        piece['start'] = (origin_frame + begin) / SR
        results.append(piece)
        if index < len(connections) and connections[index]:
            finish = int(offsets[index+1] * SR)
            bridge = raw.audio[begin+length:finish].copy() * job[13]
            if job[7].damaged:
                bridge = fx.wound(bridge, _rng(opts.seed,16,job[0],job[1]), **job[6])
            results.append(dict(m=mouth,start=(origin_frame+begin+length)/SR,main=bridge,moved=None,whisper=None))
    return results


def _hum_line(job, prepared=None, join_left=0, join_right=0):
    wi,mi,m,segs,voice,_,wound,dia,opts,_,_,start,_,gain = job
    rng = _rng(opts.seed, 2, wi, mi)
    audio = prepared.audio if prepared is not None else render_voice(segs, voice, rng, opts, m).audio
    if dia.damaged:
        audio = fx.wound(audio, rng, **wound)
    audio = edges(audio, .06, left=.06*(1-join_left), right=.06*(1-join_right)) * gain
    return dict(m=m, start=start, main=audio, moved=None, whisper=None,
                bank_coverage=_bank_coverage(segs, opts, m))


def _hum_speech_job(group):
    return _speech_job(group, hum=True)


def _hum_job(job):
    (wi, mi, m, segs, voice, wound, dia, opts, start, gain) = job
    rng = _rng(opts.seed, 2, wi, mi)
    sig = render_voice(segs, voice, rng, opts, m).audio
    if dia.damaged:
        sig = fx.wound(sig, rng, **wound)
    return {"m": m, "start": start, "main": edges(sig, 0.06) * opts.hum * gain, "moved": None, "whisper": None, "bank_coverage": _bank_coverage(segs, opts, m)}


def _choir_chunk_job(job):
    """One stretch of one praise voice, between two of its rests."""
    (vi, ci, offset, segs, voice, factor, opts) = job
    rng = _rng(opts.seed, 3, vi, ci)
    return {"vi": vi, "offset": offset, "sig": render_voice(segs, voice, rng, opts, f"praise-{vi + 1}", default_f0=voice.f0 * factor).audio,
            "bank_coverage": _bank_coverage(segs, opts, f"praise-{vi + 1}")}


def phrase_chunks(segs, target=4.0):
    """Split a long segment list at rests into chunks of about `target`
    seconds, with each chunk's start time. Cutting in silence is seamless."""
    chunks, cur, t, start = [], [], 0.0, 0.0
    for s in segs:
        cur.append(s)
        t += s.dur
        if s.phone == "sil" and t - start >= target:
            chunks.append((start, cur))
            cur, start = [], t
    if cur:
        chunks.append((start, cur))
    return chunks


def _run(fn, jobs, workers, say=None, label="", start_method="fork"):
    """Map fn over jobs, in parallel when it pays off."""
    import os
    workers = workers or os.cpu_count() or 1
    grouped = fn in (_speech_job, _hum_speech_job) and any(len(group) > 1 for group in jobs)
    if workers <= 1 or (len(jobs) < 48 and not grouped):          # below that, starting the pool costs more than it saves
        yield from (fn(j) for j in jobs)
        return
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    ctx = mp.get_context(start_method)
    with ProcessPoolExecutor(max_workers=min(workers, len(jobs)), mp_context=ctx) as ex:
        from collections import deque
        pending = deque()
        source = iter(jobs)
        for _ in range(min(workers * 2, len(jobs))):
            pending.append(ex.submit(fn, next(source)))
        i = 0
        while pending:
            yield pending.popleft().result()
            i += 1
            job = next(source, None)
            if job is not None:
                pending.append(ex.submit(fn, job))
            if say and i % 16 == 0:
                say(f"{label} {i}/{len(jobs)}")


def resolve_gender(score, dia, overrides=None):
    if "voice" not in score.meta and not overrides:
        if dia.voices:
            return parse_voice(dia.voices)
        if dia.gender is not None:
            return {"all": dia.gender}
    return {**parse_voice(score.meta.get("voice", "0")), **(overrides or {})}


def plan(score, opts=None):
    """Resolve configuration and plan timed segments without rendering audio."""
    opts = opts or Options()
    if not 0 <= opts.prayer_tail <= 12 or not 0 <= opts.prayer_rise <= 24:
        raise ValueError("Prayer tail must be 0–12 seconds and its rise 0–24 semitones.")
    from .legato import validate
    opts.mouth_blend = validate(opts.mouth_blend)
    if not np.isfinite(opts.syllable_blend) or not 0 <= opts.syllable_blend <= 1:
        raise ValueError('Syllable blend must be between 0 and 1.')
    if opts.sample_banks:
        from .samplebank import validate_selection
        opts.sample_banks = validate_selection(opts.sample_banks)
    tempo = float(score.meta.get("tempo", 1.0))
    knobs = {k: v for k, v in score.meta.items() if k in dialects.KNOBS}
    knobs.update(opts.knobs or {})
    dia = dialects.get(opts.dialect or score.meta.get("dialect"), knobs)
    gender = resolve_gender(score, dia, opts.voice)
    femme = {m: max(gender.get(m, gender["all"]), 0.0) for m in MOUTHS}
    # Which dialect each mouth speaks at each word (all the same, except for
    # composite dialects like nephilim).
    role = dialects.roles(dia, score.words, gender, opts.seed, knobs)
    _voices = {}

    def voice_of(m, d):
        """A mouth's voice and wound in dialect d."""
        if (m, d.name) not in _voices:
            fem = femme[m]
            v = replace(mouth_voice(m, gender.get(m, gender["all"])), transitions=opts.transitions)
            dmg = d.mouth(m, opts.seed) if d.damaged else {}
            # The fall shouldn't turn every voice male: toward feminine, the
            # pitch drop and the lengthened throat fade out (and the growl's
            # sub-octave layer is mixed lower).
            dmg = dict(dmg, throat=dmg.get("throat", 0) * (1 - 0.5 * fem))
            v = replace(v, f0=v.f0 * 2 ** (d.pitch * (1 - 0.8 * fem) / 12),
                        **{k: dmg[k] for k in ("growl", "fry", "roar", "throat") if k in dmg})
            wound = dict(roar=dmg.get("roar", 0), whistle=dmg.get("whistle", 0),
                         wound_hz=random.Random(f"{opts.seed}:{m}:wound").uniform(3200, 5200))
            _voices[(m, d.name)] = (breathe(v, d.breath), wound)
        return _voices[(m, d.name)]

    # ---- lay out words in time
    plans = []
    t = LEAD_IN
    wt = {(wi, m): word_tones(w, score, opts, role[(wi, m)]) for wi, w in enumerate(score.words) for m in MOUTHS}
    # Per word, the strongest of each tone over its mouths (for the choir and sounds).
    wtones = [{k: max(wt[(wi, m)].get(k, 0) for m in MOUTHS) for k in set().union(*(wt[(wi, m)] for m in MOUTHS))}
              for wi in range(len(score.words))]
    last_of_sentence = {i for i, w in enumerate(score.words)
                        if i + 1 == len(score.words) or score.words[i + 1].sentence_start}
    from .legato import amount as blend_amount
    from .samplebank import selected
    formant_blends = {m: 0.0 if selected(opts.sample_banks, m) else blend_amount(opts, m)
                      for m in MOUTHS}
    for wi, w in enumerate(score.words):
        if w.sentence_start and plans:
            t += SENTENCE_GAP / tempo - WORD_GAP / tempo
        lines = {}
        for mi, m in enumerate(MOUTHS):
            ml = w.mouths[m]
            if not ml.silent:
                R, T = role[(wi, m)], wt[(wi, m)]
                segs = line_segments(ml, tempo, _rng(opts.seed, 0, wi, mi), R.moan,
                                     wi in last_of_sentence, formant_blends[m])
                segs = tone_timing(segs, T)
                if T.get("condescend") and wi in last_of_sentence:
                    segs.append(Seg("h", 0.25 + 0.15 * T["condescend"], amp=0.6))   # *sigh*
                if w.stammer:
                    segs = stammer(segs, _rng(opts.seed, 13, wi, mi), T.get("fear", 0.5))
                lines[m] = segs
        own = {m: sum(s.dur for s in segs) for m, segs in lines.items()}
        length = max(own.values(), default=0.3)
        for m, segs in lines.items():
            fit(segs, length)
        # A little rubato: no two words quite the same speed.
        rub = _rng(opts.seed, 6, wi).lognormal(0, 0.05)
        for segs in lines.values():
            for x in segs:
                x.dur *= rub
        length *= rub
        plans.append(WordPlan(w, t, lines, length))
        t += length + WORD_GAP / tempo
    def setting(name, fallback=None):
        value = getattr(opts, name)
        return value if value is not None else score.meta.get(name, fallback)
    rm = fx.room(setting("room", "cathedral"),
                 rt60=float(setting("reverb_time")) if setting("reverb_time") is not None else None,
                 predelay=float(setting("predelay")) if setting("predelay") is not None else None,
                 tone=float(setting("reverb_tone")) if setting("reverb_tone") is not None else None)
    amount = float(setting("reverb", 1.0))
    decay = rm.rt60 * 1.15 + rm.predelay if amount > 0 and rm.wet else 0
    total = t + max(TAIL, decay + (2.0 if opts.choir else 0))
    if opts.choir:
        total += opts.prayer_tail
    n = int(total * SR)

    # ---- hungry and tender words, for grab and hunger
    flags = hungry_tender(score, plans) if any(R.grab or R.hunger for R in role.values()) else {}

    # ---- prosody: one contour per sentence and mouth, gliding across words
    sentences, cur = [], []
    for wi, (w, *_rest) in enumerate(plans):
        if w.sentence_start and cur:
            sentences.append(cur)
            cur = []
        cur.append(wi)
    if cur:
        sentences.append(cur)
    hums = {}
    for si, idxs in enumerate(sentences):
        s0 = plans[idxs[0]][1]
        s1 = plans[idxs[-1]][1] + plans[idxs[-1]][3]
        for mi, m in enumerate(MOUTHS):
            rng = _rng(opts.seed, 5, si, mi)
            shape = CONTOURS[rng.choice(list(CONTOURS))]
            wobble = rng.uniform(-0.03, 0.03, 6)
            tags = [(wi, tg) for wi in idxs if m in plans[wi][2]
                    for tg in sorted({x.tag for x in plans[wi][2][m] if x.tag is not None})]
            pick = rng.choice(len(tags), size=min(len(tags), int(rng.integers(1, 4))), replace=False) if tags else []
            accents = {tags[k] for k in pick}
            prev_end = None
            for wi in idxs:
                w, start, lines, length = plans[wi]
                mrng = _rng(opts.seed, 8, wi, mi)
                R, T = role[(wi, m)], wt[(wi, m)]
                v = voice_of(m, R)[0]
                if m in lines:
                    segs = contour(lines[m], v, start, s0, s1, shape, wobble,
                                   {tg for (k, tg) in accents if k == wi}, prev_end)
                    segs = micro(segs)
                    segs = tone_pitch(segs, T, mrng, v.f0, wi in last_of_sentence)
                    if R.moan:
                        segs = moanify(segs, R.moan, mrng, R.grab)
                    lines[m] = segs
                elif opts.hum:
                    segs = contour(hum_segments(length, R.moan, mrng), v, start, s0, s1,
                                   shape, wobble, set(), prev_end)
                    hums[(wi, m)] = tone_pitch(hum_glide(segs, R.moan, mrng), T, mrng,
                                               v.f0, wi in last_of_sentence)
                else:
                    continue
                voiced = [x for x in (lines[m] if m in lines else hums[(wi, m)]) if x.f0 and x.phone != "sil"]
                prev_end = voiced[-1].f0[1] if voiced else prev_end
            for wi in idxs:
                w = plans[wi][0]
                if opts.hum and m in plans[wi][2] and w.mouths[m].moved:
                    # A closed (moved) mouth hums too, on its contour.
                    R = role[(wi, m)]
                    segs = contour(hum_segments(plans[wi][3], R.moan, _rng(opts.seed, 8, wi, mi)), voice_of(m, R)[0],
                                   plans[wi][1], s0, s1, shape, wobble, set())
                    hums[(wi, m)] = hum_glide(segs, R.moan, _rng(opts.seed, 8, wi, mi))

    return RenderPlan(opts, tempo, dia, knobs, gender, role, _voices, wt, wtones,
                      plans, sentences, hums, flags, total, rm, amount)


def synthesize(score, opts=None, progress=None, *, render_plan=None):
    p = render_plan or plan(score, opts)
    p.sample_report.clear()
    p.vowel_brightness.clear()
    opts, tempo, dia, knobs, gender = p.options, p.tempo, p.dialect, p.knobs, p.gender
    role, wt, wtones = p.roles, p.mouth_tones, p.tones
    plans, sentences, hums, flags, total = p.words, p.sentences, p.hums, p.flags, p.total
    n = int(total * SR)
    femme = {m: max(gender.get(m, gender["all"]), 0.0) for m in MOUTHS}
    say = progress or (lambda *_: None)

    def voice_of(m, d):
        return p.voices[(m, d.name)]

    # ---- the mouths, as jobs
    line_jobs, hum_jobs = [], []
    for wi, (w, start, lines, length) in enumerate(plans):
        for mi, m in enumerate(MOUTHS):
            R, T = role[(wi, m)], wt[(wi, m)]
            v, wound = voice_of(m, R)
            if (wi, m) in hums:
                hum_jobs.append((wi, mi, m, hums[(wi, m)], tone_voice(v, T), wound, R, opts, start, tone_gain(T)))
            if m in lines:
                ml = w.mouths[m]
                levels = {i: tk.brightness for i, tk in enumerate(ml.tokens) if tk.kind == "phoneme" and tk.brightness}
                surge = 0.45 * R.hunger if flags.get((wi, m), ("",))[0] == "hungry" else 0.0
                line_jobs.append((wi, mi, m, lines[m], tone_voice(v, T), femme[m], wound, R, opts,
                                  levels, ml.moved, start, surge, tone_gain(T)))
    say(f"rendering {len(line_jobs)} mouth lines and {len(hum_jobs)} hums")
    from itertools import chain
    # A fresh interpreter avoids forking a process with native WORLD/BLAS state.
    start_method = 'spawn' if any((opts.sample_banks or {}).values()) else 'fork'
    groups = _speech_groups(line_jobs, plans)
    from .legato import amount as blend_amount
    connected_hums, isolated_hums = [], []
    for job in hum_jobs:
        wi,mi,m,segs,voice,wound,dia,_,start,gain = job
        if blend_amount(opts,m) > 0:
            connected_hums.append((wi,mi,m,segs,voice,0,wound,dia,opts,{},False,start,0,gain*opts.hum))
        else:
            isolated_hums.append(job)
    hum_groups = _speech_groups(connected_hums, plans)
    results = chain(chain.from_iterable(_run(_speech_job, groups, opts.jobs, say, "phrases", start_method)),
                    chain.from_iterable(_run(_hum_speech_job, hum_groups, opts.jobs, start_method=start_method)),
                    _run(_hum_job, isolated_hums, opts.jobs, start_method=start_method))
    tracks = {m: np.zeros(n) for m in MOUTHS}
    moved = {m: np.zeros(n) for m in MOUTHS}
    whispers = {m: np.zeros(n) for m in MOUTHS}
    for res in results:
        m, start = res["m"], res["start"]
        _record_bank(p, m, res.get("bank_coverage"))
        brightness = res.get("vowel_brightness")
        if brightness:
            origin = round(start * SR)
            p.vowel_brightness.setdefault(f"mouth-{m}", []).extend(
                ((origin + a) / SR, (origin + b) / SR, level) for a, b, level in brightness
            )
        if res["main"] is not None:
            place(tracks[m], res["main"], start)
        if res["moved"] is not None:
            body, lead = res["moved"]
            place(moved[m], body, start - lead)
        if res["whisper"] is not None:
            place(whispers[m], res["whisper"], start)

    for timeline in p.vowel_brightness.values():
        timeline.sort()

    # ---- praise voices
    choir_tracks = []
    if opts.choir:
        speech_end = plans[-1].start + plans[-1].duration + WORD_GAP / tempo
        bounds = [p[1] for p in plans] + [total]
        choir_rng = random.Random(opts.seed)
        langs = [p[0].langs for p in plans]

        def lang_at(x):
            for i in range(len(plans)):
                if x < bounds[i + 1]:
                    return langs[i]
            return langs[-1]

        jobs, lengths, tails = [], {}, {}
        pain_spans = [(plans[wi][1], plans[wi][1] + plans[wi][3] + 0.4,
                       max(wtones[wi].get("pain", 0), wtones[wi].get("scream", 0)))
                      for wi in range(len(plans)) if wtones[wi].get("pain") or wtones[wi].get("scream")]
        if dia.choir == "torn":
            # Two praise voices sing forward; the middle one blasphemes
            # backwards in Locrian against them.
            cdias = [dialects.get("seraphic", knobs), dialects.get("demonic", knobs), dialects.get("seraphic", knobs)]
        else:
            cdias = [dia] * len(CHOIR_VOICES)
        for vi in range(len(CHOIR_VOICES)):
            cd = cdias[vi]
            voice, factor = choir_voice(vi, gender.get("choir", gender["all"]))
            factor *= 2 ** (cd.choir_pitch / 12)
            if cd.damaged:
                voice = replace(voice, **{k: v for k, v in cd.choir_damage().items() if k != "whistle"})
            voice = replace(breathe(voice, cd.breath * 0.7), transitions=opts.transitions)
            if opts.prayer_time:
                spans = choir.time_spans(plans, vi, LEAD_IN - 0.9, speech_end + 0.8)
                segs = choir.timed_schedule(spans, vi, tempo, rng=choir_rng, mode=cd.mode,
                                            backmask=cd.choir == "backmask")
            else:
                segs = choir.schedule(lang_at, speech_end + 0.8, vi, tempo, start=LEAD_IN - 0.9,
                                      rng=choir_rng, mode=cd.mode)
            for s in segs:
                if s.f0:
                    s.f0 = (s.f0[0] * factor, s.f0[1] * factor)
            lengths[vi] = sum(s.dur for s in segs)
            segs = falter(segs, pain_spans, LEAD_IN - 0.9, lengths[vi], cd.choir == "backmask",
                          _rng(opts.seed, 14, vi))
            if opts.prayer_tail:
                segs, tails[vi] = choir.linger(segs, opts.prayer_tail, opts.prayer_rise,
                                              backmask=cd.choir == "backmask")
                lengths[vi] = sum(s.dur for s in segs)
            for ci, (offset, chunk) in enumerate(phrase_chunks(segs)):
                jobs.append((vi, ci, offset, chunk, voice, factor, opts))
        say(f"praise voices ({len(jobs)} phrases)")
        tsec = np.arange(n) / SR
        env = np.clip((tsec - (LEAD_IN - 0.9)) / 0.6, 0, 1)
        env *= np.clip((speech_end + 0.8 + 1.2 - tsec) / 1.2, 0, 1)
        voices_sig = {vi: np.zeros(int(lengths[vi] * SR) + SR) for vi in lengths}
        for res in _run(_choir_chunk_job, jobs, opts.jobs, start_method=start_method):
            place(voices_sig[res["vi"]], res["sig"], res["offset"])
            _record_bank(p, f"praise-{res['vi'] + 1}", res.get("bank_coverage"))
        for vi in sorted(voices_sig):
            sig = voices_sig[vi][: int(lengths[vi] * SR)]
            cd = cdias[vi]
            if cd.damaged:
                dmg = cd.choir_damage()
                sig = fx.wound(sig, _rng(opts.seed, 4, vi), roar=dmg["roar"], whistle=dmg["whistle"] * 0.5,
                               wound_hz=4600)
            if cd.choir == "backmask":
                sig = sig[::-1]         # blasphemy: the prayers sung backwards
            tr = np.zeros(n)
            place(tr, sig, LEAD_IN - 0.9)
            envelope = env
            if tails.get(vi) is not None:
                tail_start = LEAD_IN - 0.9 + tails[vi]
                # Let the rising note speak for the first third, then use a
                # cubic fade with a flat slope at both full gain and silence.
                fade_time = opts.prayer_tail * (2 / 3)
                fade_start = tail_start + opts.prayer_tail / 3
                remaining = np.clip(1 - (tsec - fade_start) / fade_time, 0, 1)
                envelope = np.clip((tsec - (LEAD_IN - 0.9)) / 0.6, 0, 1)
                envelope *= remaining ** 2 * (3 - 2 * remaining)
            choir_tracks.append(tr * envelope * opts.choir_level)

    # ---- grab and hunger: trajectories toward the ears, and mouth sounds
    curves = grab_curves(plans, sentences, flags, role, n) if any(R.grab for R in role.values()) else {}
    foley = foley_tracks(plans, sentences, flags, role, opts, n) if any(R.grab or R.hunger for R in role.values()) else {}
    if any(wtones):
        for m, tr in pain_sounds(score, plans, wtones, opts, n).items():
            foley[m] = foley[m] + tr if m in foley else tr

    # ---- mix in space
    say("spatializing")
    stems = {}

    def near(az, el):
        """Right at the listener's ear on the source's side."""
        return 78 * (-1 if az < 0 else 1), el * 0.2, 0.3

    # (key, signal, azimuth, elevation, distance, gain, reverb send, grab curve)
    sources = []
    for m in MOUTHS:
        az, el, d = MOUTH_POS[m]
        if opts.keep_stems:
            stems[f"mouth-{m}"] = tracks[m] + moved[m]
        sources.append((f"mouth-{m}", tracks[m], az, el, d, 1.0, opts.reverb_mix, curves.get(m)))
        if moved[m].any():
            # In front of the closed mouth: nearer the listener, same side.
            sources.append((f"moved-{m}", moved[m], az * 0.6, el * 0.6, d * 0.55, 0.7, opts.reverb_mix,
                            curves.get(m)))
        if whispers[m].any():
            # Right at the ears, on the mouth's side, dry: intimate, no hall.
            if opts.keep_stems:
                stems[f"whisper-{m}"] = whispers[m]
            sources.append((f"whisper-{m}", whispers[m], *near(az, el)[:2], 0.25, 1.0, 0.0, None))
        if m in foley and foley[m].any():
            if opts.keep_stems:
                stems[f"foley-{m}"] = foley[m]
            sources.append((f"foley-{m}", foley[m], *near(az, el), 1.0, 0.05, None))
    for vi, tr in enumerate(choir_tracks):
        az, el, d = CHOIR_POS[vi]
        if opts.keep_stems:
            stems[f"praise-{vi + 1}"] = tr
        sources.append((f"praise-{vi + 1}", tr, az, el, d, 1.0, 1.4, None))
    mix = np.zeros((n, 2))
    send = np.zeros((n, 2))

    def spat(src):
        key, sig, az, el, d, g, snd, curve = src
        if not opts.space:
            dry = np.repeat(sig[:, None], 2, axis=1) * 0.7 * g
            return dry, dry * snd
        if curve is None:
            dry = fx.spatialize(sig, az, el, d) * g
            return dry, dry * snd
        # Grab: crossfade (equal power) from the source's place to the ear.
        # The close version gets the proximity bass of a mouth at your ear
        # and stays out of the hall.
        far = fx.spatialize(sig * np.cos(curve * np.pi / 2), az, el, d) * g
        close = fx.spatialize(sig * np.sin(curve * np.pi / 2), *near(az, el)) * g
        close = np.stack([fx.low_shelf(close[:, c], 250, 5) for c in range(2)], axis=1)
        return far + close, far * snd

    # Threads, not processes: scipy's filters release the GIL, and the
    # stereo results stay in memory instead of being copied back.
    if opts.jobs == 1:
        for src in sources:
            dry, wet = spat(src)
            mix += dry
            send += wet
    else:
        from concurrent.futures import ThreadPoolExecutor
        import os
        workers = min(len(sources), opts.jobs or os.cpu_count() or 1)
        with ThreadPoolExecutor(max_workers=workers) as ex:
            # Bound in-flight stereo buffers even on machines with many cores.
            for start in range(0, len(sources), workers):
                for dry, wet in ex.map(spat, sources[start:start + workers]):
                    mix += dry
                    send += wet

    # ---- the room
    rm, amount = p.room, p.reverb_amount
    out = mix
    if rm.rt60 > 0 and amount > 0 and rm.wet > 0:
        say(f"reverb: {rm.name}, RT60 {rm.rt60:.2f} s")
        ir = fx.room_ir(rm, _rng(opts.seed, 7))
        out = mix + fx.reverb(send, ir)[:n] * 0.5 * rm.wet * amount
    if opts.master:
        out = master(out)
    for channel, entry in sorted(p.sample_report.items()):
        fallback = ', '.join(sorted(entry['counts'].get('formant', {}))) or 'none'
        approximated = ', '.join(sorted(entry['counts'].get('approximation', {}))) or 'none'
        say(f"{channel}: {entry['name']}; approximate: {approximated}; formant fallback: {fallback}")
    return out, stems


def master(audio):
    """Remove inaudible DC/rumble and leave headroom with mild saturation."""
    from scipy.signal import sosfilt
    clean = sosfilt(fx.design(2, 35, "highpass"), audio, axis=0)
    peak = np.max(np.abs(clean)) + 1e-9
    # The former 1.1 drive compressed every render heavily and added harmonics
    # to already bright vowels. A lower drive preserves expressive dynamics.
    drive = 0.35
    return np.tanh(clean / peak * drive) / np.tanh(drive) * 0.89
