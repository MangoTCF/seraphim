"""Turn a parsed score into a 7-voice binaural recording."""

import random
from dataclasses import dataclass, replace

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


def mouth_voice(m, gender=0.0):
    """The voice of mouth m with gender in [-1 masculine, +1 feminine]."""
    t = (min(max(gender, -1), 1) + 1) / 2
    (f_m, s_m), (f_f, s_f) = MOUTH_RANGE[m]
    return Voice(m, f_m ** (1 - t) * f_f ** t, fscale=_lerp(s_m, s_f, t),
                 oq=_lerp(*QUALITY["oq"], t), breath=_lerp(*QUALITY["breath"], t))


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
    voice: dict = None        # gender per mouth / 'choir', -1 masculine .. +1 feminine
    dialect: str = None       # overrides the score's @dialect
    knobs: dict = None        # dialect knob overrides, e.g. {'growl': 0.9}
    tones: dict = None        # tonal markers applied to every word, e.g. {'pain': 0.8}


STOPLIKE = {"stop", "glottal"}


def line_segments(ml, tempo, rng=None, moan=0.0, final=False):
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
    goes higher still and arcs; fear raises it a little; a whimper sinks."""
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
            b *= 2 ** (-(3 * pain + 2 * whimper) / 12)              # the wail falls away
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
        out.append(Seg(x.phone, x.dur, (a, b), x.tag, x.amp))
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
                   jitter=v.jitter * (1 + 4 * pain + 3 * scream + 2 * fear),
                   roar=min(1.0, v.roar + 0.35 * pain + 0.6 * scream + 0.15 * anger),
                   breath=v.breath + 0.15 * pain + 0.3 * whimper + 0.15 * fear + 0.1 * smug,
                   voicing=v.voicing * (1 - 0.3 * whimper),
                   open=max(v.open, scream, 0.3 * pain),
                   vibrato=max(v.vibrato, 0.035 * fear), vib_rate=7.5 if fear else v.vib_rate)


BREAKS = {"break", "crack", "snap", "shatter", "tear", "rip", "split"}
WINGS = {"wing", "feather", "pinion"}


def pain_sounds(score, plans, tones, opts, n):
    """At the ears: a crack inside the wing on breaking words, a rustle of
    feathers on wing words, a sobbing breath in before painful words."""
    import re
    from .lexicon import Lexicon
    from .reading import decode_line
    lx = Lexicon(save=False)
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


def edges(sig, fade=EDGE_FADE):
    """Soft edges so consecutive words join without clicks."""
    r = min(int(fade * SR), len(sig) // 2)
    if r:
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, r))
        sig[:r] *= ramp
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
    from .lexicon import Lexicon
    from .reading import decode_line
    lx = Lexicon(save=False)
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


def grab_curves(plans, sentences, flags, dia, n):
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
        bump = np.zeros(m_)
        for (wi, mm), (kind, _) in flags.items():
            if mm != m:
                continue
            g = plans[wi][1]
            dt = np.clip(t - g, 0, None)
            bump += np.where(t >= g, 0.6 * (1 - np.exp(-dt / 0.08)) * np.exp(-dt / 1.2), 0)
        curve = np.clip(dia.grab * (base + bump), 0, 0.95)
        out[m] = np.interp(np.arange(n) / SR, t, curve)
    return out


def foley_tracks(plans, sentences, flags, dia, opts, n):
    """Mouth sounds at the ears: teeth snapping after hungry words and a wet
    slurp after eating ones (hunger), a kiss before tender words and a
    breath in before each sentence (grab)."""
    events = []
    for (wi, m), (kind, parts) in flags.items():
        start, length = plans[wi][1], plans[wi][3]
        if kind == "hungry" and dia.hunger:
            events.append((start + length - 0.03, "snap", m, dia.hunger))
            if parts & SLURPY:
                events.append((start + length + 0.07, "slurp", m, 0.7 * dia.hunger))
        if kind == "tender" and dia.grab:
            events.append((start - 0.06, "kiss", m, 0.6 * dia.grab))
    if dia.grab:
        for si, idxs in enumerate(sentences):
            events.append((plans[idxs[0]][1] - 0.45, "gasp", MOUTHS[si % len(MOUTHS)], 0.5 * dia.grab))
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


def _line_job(job):
    """Render one mouth's line for one word: voice, growl layer, whisper,
    brightness, damage, 4D movement. Segments arrive with their pitch
    already planned (see the prosody pass). Returns the pieces to place."""
    (wi, mi, m, segs, voice, fem, wound, dia, opts, levels, moved, start, surge, gain) = job
    rng = _rng(opts.seed, 1, wi, mi)
    if surge:
        # Hungry words: the growl and roar surge for this line.
        voice = replace(voice, growl=min(1.0, voice.growl + surge), roar=min(1.0, voice.roar + 0.4 * surge))
    r = render(segs, voice, rng)
    out = {"m": m, "start": start, "main": None, "moved": None, "whisper": None}
    if voice.growl:
        # The growl's body: a second, rougher throat an octave down, kept
        # under the voice (less so toward feminine). Heavy jitter keeps it
        # from locking to exactly half the voice's pitch, whose steady
        # beating pulses like a croak.
        sub_v = replace(voice, growl=0.0, fry=0.0, roar=min(1.0, voice.roar + 0.3), jitter=0.03,
                        fscale=voice.fscale * 0.9, breath=voice.breath + 0.1)
        sub = render([Seg(x.phone, x.dur, (x.f0[0] / 2, x.f0[1] / 2) if x.f0 else None, x.tag, x.amp)
                      for x in segs], sub_v, rng).audio
        sub = fx.sosfilt(fx.sos_lowpass(1600), sub)
        k = min(len(sub), len(r.audio))
        r.audio[:k] += 0.5 * voice.growl * (1 - 0.6 * fem) * sub[:k]
    if dia.whisper:
        # A whispered double, breathed right at the listener's ears.
        wv = replace(voice, voicing=0.0, breath=1.0, growl=0.0, roar=0.0, fry=0.0)
        whisp = render(segs, wv, rng).audio
        whisp *= dia.whisper * 0.8 * (np.sqrt(np.mean(r.audio ** 2)) / (np.sqrt(np.mean(whisp ** 2)) + 1e-9))
        out["whisper"] = edges(whisp)
    octave = None
    if EXTRA in levels.values():
        up = [Seg(x.phone, x.dur, (x.f0[0] * 2, x.f0[1] * 2), x.tag) for x in segs]
        octave = render(up, voice, rng).audio
    sig = fx.brighten(r.audio, r.spans, levels, octave, rng, glitter=opts.glitter)
    if dia.damaged:
        sig = fx.wound(sig, rng, **wound)
    sig = edges(sig) * gain
    if out["whisper"] is not None:
        out["whisper"] = out["whisper"] * gain
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


def _hum_job(job):
    (wi, mi, m, segs, voice, wound, dia, opts, start, gain) = job
    rng = _rng(opts.seed, 2, wi, mi)
    sig = render(segs, voice, rng).audio
    if dia.damaged:
        sig = fx.wound(sig, rng, **wound)
    return {"m": m, "start": start, "main": edges(sig, 0.06) * opts.hum * gain, "moved": None, "whisper": None}


def _choir_chunk_job(job):
    """One stretch of one praise voice, between two of its rests."""
    (vi, ci, offset, segs, voice, factor, opts) = job
    rng = _rng(opts.seed, 3, vi, ci)
    return {"vi": vi, "offset": offset, "sig": render(segs, voice, rng, default_f0=voice.f0 * factor).audio}


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


def _run(fn, jobs, workers, say=None, label=""):
    """Map fn over jobs, in parallel when it pays off."""
    import os
    workers = workers or os.cpu_count() or 1
    if workers <= 1 or len(jobs) < 48:          # below that, starting the pool costs more than it saves
        return [fn(j) for j in jobs]
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    ctx = mp.get_context("fork")
    with ProcessPoolExecutor(max_workers=min(workers, len(jobs)), mp_context=ctx) as ex:
        out = []
        for i, res in enumerate(ex.map(fn, jobs, chunksize=1), 1):
            out.append(res)
            if say and i % 16 == 0:
                say(f"{label} {i}/{len(jobs)}")
        return out


def synthesize(score, opts=None, progress=None):
    opts = opts or Options()
    tempo = float(score.meta.get("tempo", 1.0))
    say = progress or (lambda *_: None)
    knobs = {k: v for k, v in score.meta.items() if k in dialects.KNOBS}
    knobs.update(opts.knobs or {})
    dia = dialects.get(opts.dialect or score.meta.get("dialect"), knobs)
    explicit_voice = "voice" in score.meta or bool(opts.voice)
    gender = parse_voice(score.meta.get("voice", "0"))
    if not explicit_voice and dia.gender is not None:
        gender["all"] = dia.gender
    gender.update(opts.voice or {})
    voices, wounds, femme = {}, {}, {}
    for m in MOUTHS:
        g = gender.get(m, gender["all"])
        femme[m] = fem = max(g, 0.0)
        v = mouth_voice(m, g)
        dmg = dia.mouth(m, opts.seed) if dia.damaged else {}
        # The fall shouldn't turn every voice male: toward feminine, the
        # pitch drop and the lengthened throat fade out (and the growl's
        # sub-octave layer is mixed lower).
        dmg = dict(dmg, throat=dmg.get("throat", 0) * (1 - 0.5 * fem))
        v = replace(v, f0=v.f0 * 2 ** (dia.pitch * (1 - 0.8 * fem) / 12),
                    **{k: dmg[k] for k in ("growl", "fry", "roar", "throat") if k in dmg})
        voices[m] = breathe(v, dia.breath)
        wounds[m] = dict(roar=dmg.get("roar", 0), whistle=dmg.get("whistle", 0),
                         wound_hz=random.Random(f"{opts.seed}:{m}:wound").uniform(3200, 5200))

    # ---- lay out words in time
    plans = []
    t = LEAD_IN
    wtones = [word_tones(w, score, opts, dia) for w in score.words]
    last_of_sentence = {i for i, w in enumerate(score.words)
                        if i + 1 == len(score.words) or score.words[i + 1].sentence_start}
    for wi, w in enumerate(score.words):
        if w.sentence_start and plans:
            t += SENTENCE_GAP / tempo - WORD_GAP / tempo
        lines = {}
        for mi, m in enumerate(MOUTHS):
            ml = w.mouths[m]
            if not ml.silent:
                segs = line_segments(ml, tempo, _rng(opts.seed, 0, wi, mi), dia.moan, wi in last_of_sentence)
                segs = tone_timing(segs, wtones[wi])
                if wtones[wi].get("condescend") and wi in last_of_sentence:
                    segs.append(Seg("h", 0.25 + 0.15 * wtones[wi]["condescend"], amp=0.6))   # *sigh*
                if w.stammer:
                    segs = stammer(segs, _rng(opts.seed, 13, wi, mi), wtones[wi].get("fear", 0.5))
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
        plans.append((w, t, lines, length))
        t += length + WORD_GAP / tempo
    total = t + TAIL
    n = int(total * SR)

    # ---- hungry and tender words, for grab and hunger
    flags = hungry_tender(score, plans) if (dia.grab or dia.hunger) else {}

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
                if m in lines:
                    segs = contour(lines[m], voices[m], start, s0, s1, shape, wobble,
                                   {tg for (k, tg) in accents if k == wi}, prev_end)
                    segs = micro(segs)
                    segs = tone_pitch(segs, wtones[wi], mrng, voices[m].f0, wi in last_of_sentence)
                    if dia.moan:
                        segs = moanify(segs, dia.moan, mrng, dia.grab)
                    lines[m] = segs
                elif opts.hum:
                    segs = contour(hum_segments(length, dia.moan, mrng), voices[m], start, s0, s1,
                                   shape, wobble, set(), prev_end)
                    hums[(wi, m)] = tone_pitch(hum_glide(segs, dia.moan, mrng), wtones[wi], mrng,
                                               voices[m].f0, wi in last_of_sentence)
                else:
                    continue
                voiced = [x for x in (lines[m] if m in lines else hums[(wi, m)]) if x.f0 and x.phone != "sil"]
                prev_end = voiced[-1].f0[1] if voiced else prev_end
            for wi in idxs:
                w = plans[wi][0]
                if opts.hum and m in plans[wi][2] and w.mouths[m].moved:
                    # A closed (moved) mouth hums too, on its contour.
                    segs = contour(hum_segments(plans[wi][3], dia.moan, _rng(opts.seed, 8, wi, mi)), voices[m],
                                   plans[wi][1], s0, s1, shape, wobble, set())
                    hums[(wi, m)] = hum_glide(segs, dia.moan, _rng(opts.seed, 8, wi, mi))

    # ---- the mouths, as jobs
    line_jobs, hum_jobs = [], []
    for wi, (w, start, lines, length) in enumerate(plans):
        for mi, m in enumerate(MOUTHS):
            if (wi, m) in hums:
                hum_jobs.append((wi, mi, m, hums[(wi, m)], tone_voice(voices[m], wtones[wi]), wounds[m], dia, opts, start,
                                 tone_gain(wtones[wi])))
            if m in lines:
                ml = w.mouths[m]
                levels = {i: tk.brightness for i, tk in enumerate(ml.tokens) if tk.kind == "phoneme" and tk.brightness}
                surge = 0.45 * dia.hunger if flags.get((wi, m)) == "hungry" else 0.0
                line_jobs.append((wi, mi, m, lines[m], tone_voice(voices[m], wtones[wi]), femme[m], wounds[m], dia, opts,
                                  levels, ml.moved, start, surge, tone_gain(wtones[wi])))
    say(f"rendering {len(line_jobs)} mouth lines and {len(hum_jobs)} hums")
    results = _run(_line_job, line_jobs, opts.jobs, say, "lines") + _run(_hum_job, hum_jobs, opts.jobs)
    tracks = {m: np.zeros(n) for m in MOUTHS}
    moved = {m: np.zeros(n) for m in MOUTHS}
    whispers = {m: np.zeros(n) for m in MOUTHS}
    for res in results:
        m, start = res["m"], res["start"]
        if res["main"] is not None:
            place(tracks[m], res["main"], start)
        if res["moved"] is not None:
            body, lead = res["moved"]
            place(moved[m], body, start - lead)
        if res["whisper"] is not None:
            place(whispers[m], res["whisper"], start)

    # ---- praise voices
    choir_tracks = []
    if opts.choir:
        bounds = [p[1] for p in plans] + [total]
        choir_rng = random.Random(opts.seed)
        langs = [p[0].langs for p in plans]

        def lang_at(x):
            for i in range(len(plans)):
                if x < bounds[i + 1]:
                    return langs[i]
            return langs[-1]

        jobs, lengths, chdmg = [], {}, {}
        pain_spans = [(plans[wi][1], plans[wi][1] + plans[wi][3] + 0.4,
                       max(wtones[wi].get("pain", 0), wtones[wi].get("scream", 0)))
                      for wi in range(len(plans)) if wtones[wi].get("pain") or wtones[wi].get("scream")]
        for vi in range(len(CHOIR_VOICES)):
            voice, factor = choir_voice(vi, gender.get("choir", gender["all"]))
            factor *= 2 ** (dia.choir_pitch / 12)
            if dia.damaged:
                voice = replace(voice, **{k: v for k, v in dia.choir_damage().items() if k != "whistle"})
            voice = breathe(voice, dia.breath * 0.7)
            segs = choir.schedule(lang_at, total - TAIL + 0.8, vi, tempo, start=LEAD_IN - 0.9,
                                  rng=choir_rng, mode=dia.mode)
            for s in segs:
                if s.f0:
                    s.f0 = (s.f0[0] * factor, s.f0[1] * factor)
            lengths[vi] = sum(s.dur for s in segs)
            segs = falter(segs, pain_spans, LEAD_IN - 0.9, lengths[vi], dia.choir == "backmask",
                          _rng(opts.seed, 14, vi))
            for ci, (offset, chunk) in enumerate(phrase_chunks(segs)):
                jobs.append((vi, ci, offset, chunk, voice, factor, opts))
        say(f"praise voices ({len(jobs)} phrases)")
        tsec = np.arange(n) / SR
        env = np.clip((tsec - (LEAD_IN - 0.9)) / 0.6, 0, 1)
        env *= np.clip((total - TAIL + 0.8 + 1.2 - tsec) / 1.2, 0, 1)
        voices_sig = {vi: np.zeros(int(lengths[vi] * SR) + SR) for vi in lengths}
        for res in _run(_choir_chunk_job, jobs, opts.jobs):
            place(voices_sig[res["vi"]], res["sig"], res["offset"])
        for vi in sorted(voices_sig):
            sig = voices_sig[vi][: int(lengths[vi] * SR)]
            if dia.damaged:
                cd = dia.choir_damage()
                sig = fx.wound(sig, _rng(opts.seed, 4, vi), roar=cd["roar"], whistle=cd["whistle"] * 0.5,
                               wound_hz=4600)
            if dia.choir == "backmask":
                sig = sig[::-1]         # blasphemy: the prayers sung backwards
            tr = np.zeros(n)
            place(tr, sig, LEAD_IN - 0.9)
            choir_tracks.append(tr * env * opts.choir_level)

    # ---- grab and hunger: trajectories toward the ears, and mouth sounds
    curves = grab_curves(plans, sentences, flags, dia, n) if dia.grab else {}
    foley = foley_tracks(plans, sentences, flags, dia, opts, n) if (dia.grab or dia.hunger) else {}
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
        stems[f"mouth-{m}"] = tracks[m] + moved[m]
        sources.append((f"mouth-{m}", tracks[m], az, el, d, 1.0, opts.reverb_mix, curves.get(m)))
        if moved[m].any():
            # In front of the closed mouth: nearer the listener, same side.
            sources.append((f"moved-{m}", moved[m], az * 0.6, el * 0.6, d * 0.55, 0.7, opts.reverb_mix,
                            curves.get(m)))
        if dia.whisper and whispers[m].any():
            # Right at the ears, on the mouth's side, dry: intimate, no hall.
            stems[f"whisper-{m}"] = whispers[m]
            sources.append((f"whisper-{m}", whispers[m], *near(az, el)[:2], 0.25, 1.0, 0.0, None))
        if m in foley and foley[m].any():
            stems[f"foley-{m}"] = foley[m]
            sources.append((f"foley-{m}", foley[m], *near(az, el), 1.0, 0.05, None))
    for vi, tr in enumerate(choir_tracks):
        az, el, d = CHOIR_POS[vi]
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
        placed = [spat(src) for src in sources]
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(sources)) as ex:
            placed = list(ex.map(spat, sources))
    for dry, wet in placed:
        mix += dry
        send += wet

    # ---- the room
    def meta_float(k):
        return float(score.meta[k]) if k in score.meta else None
    rm = fx.room(opts.room or score.meta.get("room", "cathedral"),
                 rt60=opts.reverb_time if opts.reverb_time is not None else meta_float("reverb_time"),
                 predelay=opts.predelay if opts.predelay is not None else meta_float("predelay"),
                 tone=opts.reverb_tone if opts.reverb_tone is not None else meta_float("reverb_tone"))
    amount = opts.reverb if opts.reverb is not None else (meta_float("reverb") if "reverb" in score.meta else 1.0)
    out = mix
    if rm.rt60 > 0 and amount > 0 and rm.wet > 0:
        say(f"reverb: {rm.name}, RT60 {rm.rt60:.2f} s")
        ir = fx.room_ir(rm, _rng(opts.seed, 7))
        out = mix + fx.reverb(send, ir)[:n] * 0.5 * rm.wet * amount
    peak = np.max(np.abs(out)) + 1e-9
    out = np.tanh(out / peak * 1.1) / np.tanh(1.1) * 0.89
    return out, stems
