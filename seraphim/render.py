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

TOKEN_GAP = 0.008
BREAK_GAP = 0.08
WORD_GAP = 0.06
SENTENCE_GAP = 0.5
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


STOPLIKE = {"stop", "glottal"}


def line_segments(ml, tempo, rng=None, moan=0.0):
    """Segments for one mouth line, humanized: each token its own loudness,
    durations a little uneven, the last token softer. Moaning stretches the
    vowels, slurs the stops and ends the line on a sigh."""
    rng = rng or np.random.default_rng(0)
    segs = []
    phon = [i for i, t in enumerate(ml.tokens) if t.kind == "phoneme"]
    for i, t in enumerate(ml.tokens):
        if t.kind == "break":
            segs.append(Seg("sil", BREAK_GAP / tempo))
            continue
        amp = rng.uniform(0.82, 1.08) * (0.85 if phon and i == phon[-1] else 1.0)
        for p in t.ipa:
            kind = PHONES[p]["kind"]
            d = PHONES[p]["dur"] / tempo * rng.lognormal(0, 0.07)
            if moan and kind == "vowel":
                d *= 1 + 1.1 * moan
            elif moan and kind in STOPLIKE:
                d *= 1 - 0.3 * moan
            segs.append(Seg(p, d, tag=i, amp=amp))
        segs.append(Seg("sil", TOKEN_GAP / tempo))
    if moan > 0.2:
        segs.append(Seg("h", (0.08 + 0.2 * moan) / tempo, amp=0.55))       # a sigh
    return segs


CONTOURS = {
    "fall": lambda k: 1.08 - 0.18 * k,
    "hat": lambda k: 1.0 + 0.12 * np.sin(np.pi * min(k * 1.3, 1)) - 0.1 * k,
    "rise-fall": lambda k: 0.97 + 0.16 * np.sin(np.pi * k) - 0.06 * k,
}


def intonation(segs, voice, rng, moan=0.0):
    """Speech contour: a random contour shape per line, a slow wander, and
    an accent peak on one or two tokens."""
    total = sum(s.dur for s in segs) or 1
    shape = CONTOURS[rng.choice(list(CONTOURS))]
    wobble = rng.uniform(-0.03, 0.03, 4)
    tags = sorted({s.tag for s in segs if s.tag is not None})
    accents = set(rng.choice(tags, size=min(len(tags), int(rng.integers(1, 3))), replace=False)) if tags else set()
    t = 0.0
    for s in segs:
        def at(x):
            k = x / total
            return voice.f0 * (shape(k) + wobble[int(min(k, 0.999) * 4)])
        bump = 1.09 if s.tag in accents else 1.0
        s.f0 = (at(t) * bump, at(t + s.dur) * bump)
        t += s.dur
    return moanify(segs, moan, rng) if moan else segs


def moanify(segs, moan, rng):
    """Moaning: each long vowel becomes a swell, its pitch sliding up and
    back down by a few semitones while its loudness rises and falls."""
    out = []
    for s in segs:
        if PHONES.get(s.phone, {}).get("kind") != "vowel" or s.dur < 0.08:
            out.append(s)
            continue
        a, b = s.f0
        u = moan * rng.uniform(0.06, 0.2)
        mid = (a + b) / 2
        pts = [a, mid * (1 + u), mid * (1 + 0.4 * u), b * (1 - 0.3 * u)]
        for k, (frac, amp) in enumerate(((0.3, 0.8), (0.4, 1.0), (0.3, 0.75))):
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


def hum(length, voice, rng, tempo, moan=0.0):
    """A closed mouth vocalizing is a hum: [m] on the mouth's own pitch.
    Moaning turns it into a swelling, sliding 'mmm'."""
    segs = [Seg("m", length)]
    intonation(segs, voice, rng)
    if moan:
        a, b = segs[0].f0
        u = moan * rng.uniform(0.08, 0.2)
        segs = [Seg("m", length * 0.35, (a, a * (1 + u)), amp=0.8),
                Seg("m", length * 0.4, (a * (1 + u), a * (1 + 0.5 * u)), amp=1.0),
                Seg("m", length * 0.25, (a * (1 + 0.5 * u), b * (1 - 0.2 * u)), amp=0.7)]
    sig = render(segs, voice, rng).audio
    r = min(int(0.06 * SR), len(sig) // 2)
    if r:
        sig[:r] *= np.linspace(0, 1, r)
        sig[-r:] *= np.linspace(1, 0, r)
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
    brightness, damage, 4D movement. Returns the pieces to place."""
    (wi, mi, m, segs, voice, fem, wound, dia, opts, levels, moved, start) = job
    rng = _rng(opts.seed, 1, wi, mi)
    segs = intonation(segs, voice, rng, dia.moan)
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
        out["whisper"] = whisp
    octave = None
    if EXTRA in levels.values():
        up = [Seg(x.phone, x.dur, (x.f0[0] * 2, x.f0[1] * 2), x.tag) for x in segs]
        octave = render(up, voice, rng).audio
    sig = fx.brighten(r.audio, r.spans, levels, octave, rng, glitter=opts.glitter)
    if dia.damaged:
        sig = fx.wound(sig, rng, **wound)
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
    (wi, mi, m, length, voice, wound, dia, opts, tempo, start) = job
    rng = _rng(opts.seed, 2, wi, mi)
    sig = hum(length, voice, rng, tempo, dia.moan)
    if dia.damaged:
        sig = fx.wound(sig, rng, **wound)
    return {"m": m, "start": start, "main": sig * opts.hum, "moved": None, "whisper": None}


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
    for wi, w in enumerate(score.words):
        if w.sentence_start and plans:
            t += SENTENCE_GAP / tempo - WORD_GAP / tempo
        lines = {}
        for mi, m in enumerate(MOUTHS):
            ml = w.mouths[m]
            if not ml.silent:
                lines[m] = line_segments(ml, tempo, _rng(opts.seed, 0, wi, mi), dia.moan)
        own = {m: sum(s.dur for s in segs) for m, segs in lines.items()}
        length = max(own.values(), default=0.3)
        for m, segs in lines.items():
            fit(segs, length)
        plans.append((w, t, lines, length))
        t += length + WORD_GAP / tempo
    total = t + TAIL
    n = int(total * SR)

    # ---- the mouths, as jobs
    line_jobs, hum_jobs = [], []
    for wi, (w, start, lines, length) in enumerate(plans):
        for mi, m in enumerate(MOUTHS):
            if opts.hum and (m not in lines or w.mouths[m].moved):
                hum_jobs.append((wi, mi, m, length, voices[m], wounds[m], dia, opts, tempo, start))
            if m in lines:
                ml = w.mouths[m]
                levels = {i: tk.brightness for i, tk in enumerate(ml.tokens) if tk.kind == "phoneme" and tk.brightness}
                line_jobs.append((wi, mi, m, lines[m], voices[m], femme[m], wounds[m], dia, opts,
                                  levels, ml.moved, start))
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

    # ---- mix in space
    say("spatializing")
    stems = {}
    # (source, azimuth, elevation, distance, gain, reverb send)
    sources = []
    for m in MOUTHS:
        az, el, d = MOUTH_POS[m]
        stems[f"mouth-{m}"] = tracks[m] + moved[m]
        sources.append((f"mouth-{m}", tracks[m], az, el, d, 1.0, opts.reverb_mix))
        if moved[m].any():
            # In front of the closed mouth: nearer the listener, same side.
            sources.append((f"moved-{m}", moved[m], az * 0.6, el * 0.6, d * 0.55, 0.7, opts.reverb_mix))
        if dia.whisper and whispers[m].any():
            # Right at the ears, on the mouth's side, dry: intimate, no hall.
            stems[f"whisper-{m}"] = whispers[m]
            sources.append((f"whisper-{m}", whispers[m], 80 * (-1 if az < 0 else 1), el * 0.3, 0.25, 1.0, 0.0))
    for vi, tr in enumerate(choir_tracks):
        az, el, d = CHOIR_POS[vi]
        stems[f"praise-{vi + 1}"] = tr
        sources.append((f"praise-{vi + 1}", tr, az, el, d, 1.0, 1.4))
    mix = np.zeros((n, 2))
    send = np.zeros((n, 2))
    sends = {key: snd for key, _, _, _, _, _, snd in sources}
    if opts.space:
        # Threads, not processes: scipy's filters release the GIL, and the
        # stereo results stay in memory instead of being copied back.
        from concurrent.futures import ThreadPoolExecutor

        def spat(src):
            key, sig, az, el, d, g, _ = src
            return key, fx.spatialize(sig, az, el, d) * g
        if opts.jobs == 1:
            placed = [spat(src) for src in sources]
        else:
            with ThreadPoolExecutor(max_workers=len(sources)) as ex:
                placed = list(ex.map(spat, sources))
    else:
        placed = [(key, np.repeat(sig[:, None], 2, axis=1) * 0.7 * g) for key, sig, _, _, _, g, _ in sources]
    for key, dry in placed:
        mix += dry
        if sends[key]:
            send += dry * sends[key]

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
