"""A small Klatt-style cascade formant synthesizer.

Segments go in, a mono float signal comes out, along with the sample span of
every tagged segment so effects (brightness, 4D movement) can find them.
"""

from dataclasses import dataclass, field
from functools import lru_cache

import numpy as np
from scipy.signal import butter, lfilter, sosfilt

try:
    from numba import njit
except ImportError:          # optional: without it the cascade runs in scipy, slowly
    njit = None

from .phones import PHONES, V, STOP, FRIC, NAS, APPROX, TRILL, GLOT, ASP

SR = 44100
HOP = 110  # 2.5 ms parameter frames


@dataclass
class Voice:
    name: str
    f0: float               # speaking / reference pitch in Hz
    fscale: float = 1.0     # vocal tract scaling of formants
    breath: float = 0.08    # aspiration noise mixed into voicing
    vibrato: float = 0.0    # depth as a fraction of f0
    vib_rate: float = 5.3
    jitter: float = 0.006
    oq: float = 0.6         # glottal open quotient (higher = softer, breathier)
    tilt: float = 3500      # above this the harmonics roll off and breath takes over
    # Damage (the demonic dialect): see dialects.py
    growl: float = 0.0      # period doubling: every other pulse weakened
    fry: float = 0.0        # creaky, irregular low pulses
    roar: float = 0.0       # turbulent false-fold noise in the source
    throat: float = 0.0     # pharyngeal constriction
    voicing: float = 1.0    # 0 = a pure whisper


@dataclass
class Seg:
    phone: str
    dur: float
    f0: tuple = None        # (start Hz, end Hz); None = caller's default
    tag: object = None
    amp: float = 1.0


@dataclass
class Rendered:
    audio: np.ndarray
    spans: list = field(default_factory=list)   # (tag, start, end) samples


def _expand(segs):
    """Split stops into closure + burst (+ aspiration) sub-segments."""
    out = []
    for i, s in enumerate(segs):
        p = PHONES.get(s.phone)
        if p is None:
            out.append(("sil", s, s.dur, s.f0))
            continue
        if p["kind"] == STOP:
            burst = 0.012
            closure = max(s.dur - burst, 0.02)
            out.append(("closure", s, closure, s.f0))
            out.append(("burst", s, burst, s.f0))
            nxt = segs[i + 1].phone if i + 1 < len(segs) else None
            if not p["voiced"] and nxt in PHONES and PHONES[nxt]["kind"] in (V, APPROX, NAS, TRILL):
                out.append(("asp", s, 0.022, s.f0))
        else:
            out.append(("main", s, s.dur, s.f0))
    return out


def _targets(part, seg, voice):
    """Per-segment parameter targets: formants, bandwidths, AV, AH, flags."""
    p = PHONES.get(seg.phone)
    bw = [70, 110, 240, 330, 430]     # upper bandwidths wide enough not to ring on held vowels
    f = None
    av = ah = 0.0
    creak = trill = 0.0
    if p is None:
        return dict(f=None, bw=bw, av=0, ah=0, creak=0, trill=0)
    kind = p["kind"]
    f = p.get("f")
    if kind == V:
        av = 1.0
    elif kind == NAS:
        av, bw = 0.55, [60, 250, 350, 400, 450]
    elif kind == APPROX:
        av = 0.8
        if p.get("creak"):
            creak, av = 1.0, 0.7
    elif kind == TRILL:
        av, trill = 0.8, 1.0
    elif kind == FRIC:
        av = 0.45 if p["voiced"] else 0.0
    elif kind == ASP:
        ah = p["asp"]
        if seg.phone == "ħ":
            bw = [160, 200, 250, 300, 350]
    elif kind == GLOT:
        av, creak = 0.0, 1.0
    elif kind == STOP:
        if part == "closure":
            av = 0.18 if p["voiced"] else 0.0
            if p["voiced"]:
                f = (200,) + tuple(f[1:])
        elif part == "burst":
            av = 0.3 if p["voiced"] else 0.0
        elif part == "asp":
            ah, f = 0.45, None
    av *= seg.amp
    ah *= seg.amp
    if f is not None:
        f = list(f) + [3500, 4500]
    return dict(f=f, bw=bw, av=av, ah=ah, creak=creak, trill=trill)


@lru_cache(maxsize=1024)
def _sos(order, cutoff, btype, sr):
    return butter(order, cutoff, btype, fs=sr, output="sos")


def design(order, cutoff, btype, sr=SR):
    """Butterworth sos, cached: the same few filters get designed thousands
    of times per render otherwise."""
    if isinstance(cutoff, (list, tuple)):
        cutoff = tuple(round(float(c), 2) for c in cutoff)
    else:
        cutoff = round(float(cutoff), 2)
    return _sos(order, cutoff, btype, sr)


def _cascade_py(src, F, Bw, hop, sr):
    """Five time-varying resonators in cascade, coefficients per frame."""
    n = len(src)
    y = src
    for k in range(F.shape[0]):
        out = np.empty(n)
        zi = np.zeros(2)
        for fr in range(F.shape[1]):
            a0, b0 = fr * hop, min((fr + 1) * hop, n)
            if a0 >= n:
                break
            A, Bc, C = _resonator_coeffs(F[k, fr], Bw[k, fr], sr)
            out[a0:b0], zi = lfilter([A], [1, -Bc, -C], y[a0:b0], zi=zi)
        y = out
    return y


if njit is not None:
    @njit(cache=True)
    def _cascade_nb(src, F, Bw, hop, sr):
        n = src.shape[0]
        y = src.copy()
        T = 1.0 / sr
        for k in range(F.shape[0]):
            y1 = 0.0
            y2 = 0.0
            for fr in range(F.shape[1]):
                a0 = fr * hop
                if a0 >= n:
                    break
                b0 = min(a0 + hop, n)
                bw = Bw[k, fr]
                C = -np.exp(-2.0 * np.pi * bw * T)
                Bc = 2.0 * np.exp(-np.pi * bw * T) * np.cos(2.0 * np.pi * F[k, fr] * T)
                A = 1.0 - Bc - C
                for i in range(a0, b0):
                    v = A * y[i] + Bc * y1 + C * y2
                    y2 = y1
                    y1 = v
                    y[i] = v
        return y


def cascade(src, F, Bw, hop=None, sr=SR):
    hop = hop or HOP
    if njit is not None:
        return _cascade_nb(np.ascontiguousarray(src, dtype=np.float64), np.ascontiguousarray(F, dtype=np.float64),
                           np.ascontiguousarray(Bw, dtype=np.float64), hop, float(sr))
    return _cascade_py(src, F, Bw, hop, sr)


def _resonator_coeffs(F, B, sr):
    T = 1.0 / sr
    C = -np.exp(-2 * np.pi * B * T)
    Bc = 2 * np.exp(-np.pi * B * T) * np.cos(2 * np.pi * F * T)
    A = 1 - Bc - C
    return A, Bc, C


def _glottal(phase, oq):
    """Rosenberg glottal flow for phases in [0, 1)."""
    t1 = oq * 0.7
    g = np.zeros_like(phase)
    rise = phase < t1
    fall = (phase >= t1) & (phase < oq)
    g[rise] = 0.5 * (1 - np.cos(np.pi * phase[rise] / t1))
    g[fall] = np.cos(np.pi * (phase[fall] - t1) / (2 * (oq - t1)))
    return g


def _smooth_noise(n, rate, sr, rng):
    """Low-frequency random wobble, unit-ish amplitude."""
    k = max(int(n * rate / sr) + 3, 3)
    pts = rng.standard_normal(k)
    return np.interp(np.linspace(0, k - 1, n), np.arange(k), pts)


def render(segs, voice, rng=None, sr=SR, default_f0=None):
    rng = rng or np.random.default_rng(0)
    parts = _expand(segs)
    if not parts:
        return Rendered(np.zeros(0))
    durs = np.array([d for _, _, d, _ in parts])
    starts = np.concatenate([[0], np.cumsum(durs)[:-1]])
    total = float(durs.sum())
    n = int(total * sr) + HOP
    nfr = n // HOP + 1
    tf = np.arange(nfr) * HOP / sr

    tg = [_targets(part, seg, voice) for part, seg, _, _ in parts]
    # Formant-less segments (h, ʔ, aspiration) borrow from their neighbours.
    for i, t in enumerate(tg):
        if t["f"] is None:
            nb = next((tg[j]["f"] for j in range(i + 1, len(tg)) if tg[j]["f"] is not None), None)
            if nb is None:
                nb = next((tg[j]["f"] for j in range(i - 1, -1, -1) if tg[j]["f"] is not None), None)
            t["f"] = list(nb) if nb is not None else [500, 1450, 2500, 3500, 4500]

    def track(key, trans, idx=None):
        xs, ys = [], []
        for i, t in enumerate(tg):
            v = t[key] if idx is None else t[key][idx]
            s0, d = starts[i], durs[i]
            h = min(trans, d / 2)
            xs += [s0 + h, s0 + d - h]
            ys += [v, v]
        return np.interp(tf, xs, ys)

    F = np.stack([track("f", 0.035, k) for k in range(5)]) * voice.fscale
    if voice.throat:
        # A constricted pharynx raises F1 and pulls F2 down; damage widens
        # the resonances.
        F[0] *= 1 + 0.22 * voice.throat
        F[1] *= 1 - 0.2 * voice.throat
    F[3:] = np.clip(F[3:], 0, 0.45 * sr)
    Bw = np.stack([track("bw", 0.02, k) for k in range(5)]) * (1 + 0.35 * voice.throat)
    AV = track("av", 0.008)
    AH = track("ah", 0.01)
    CR = track("creak", 0.02)
    TR = track("trill", 0.01)

    # ---- source ----
    ts = np.arange(n) / sr
    f0_seg = []
    base = default_f0 or voice.f0
    for (_, seg, d, f0), s0 in zip(parts, starts):
        a, b = f0 if f0 is not None else (base, base)
        f0_seg.append((s0, a, s0 + d, b))
    fx = np.array([[s, a] for s, a, _, _ in f0_seg] + [[e, b] for _, _, e, b in f0_seg])
    order = np.argsort(fx[:, 0], kind="stable")
    f0 = np.interp(ts, fx[order, 0], fx[order, 1])
    cr = np.interp(ts, tf, CR)
    if voice.fry:
        # Vocal fry everywhere, and worst where the voice is weak (onsets,
        # offsets, voiced consonants).
        weak = 1 - np.clip(np.interp(ts, tf, AV), 0, 1)
        # Kept mild: deep, regular fry pulses are what a frog's croak is.
        cr = np.clip(cr + voice.fry * (0.1 + 0.35 * weak) * (0.6 + 0.4 * _smooth_noise(n, 3, sr, rng)), 0, 1.2)
    if voice.vibrato:
        # Drifting rate and depth: a perfectly periodic vibrato sounds mechanical.
        rate = voice.vib_rate * (1 + 0.08 * _smooth_noise(n, 0.7, sr, rng))
        depth = voice.vibrato * (0.6 + 0.4 * np.abs(_smooth_noise(n, 0.5, sr, rng)))
        f0 = f0 * (1 + depth * np.sin(2 * np.pi * np.cumsum(rate) / sr) * np.clip(ts / 0.4, 0, 1))
    f0 = f0 * (1 + voice.jitter * _smooth_noise(n, 30, sr, rng))
    f0 = f0 * (1 - 0.25 * cr) * (1 + 0.06 * cr * rng.standard_normal(n))
    cycles = np.cumsum(f0 / sr)
    phase = cycles % 1.0
    flow = _glottal(phase, voice.oq)
    dflow = np.diff(flow, prepend=0.0) * sr / (np.pi * base)
    if voice.growl:
        # A hint of uneven folds: alternate pulses slightly weaker. Kept light:
        # strong period doubling halves the heard pitch (any voice turns male)
        # and pulses like a croak. The growl's body is a separate sub-octave
        # layer mixed in by the renderer.
        depth = np.clip(0.18 * voice.growl * (0.7 + 0.3 * _smooth_noise(n, 2, sr, rng)), 0, 0.3)
        odd = (np.floor(cycles) % 2) == 1
        dflow = np.where(odd, dflow * (1 - depth), dflow)
    if voice.roar:
        # Roughness the way real rough voices have it: every cycle a slightly
        # different strength, at random. (Smooth periodic flutter croaked.)
        ncyc = int(cycles[-1]) + 2
        per_cycle = rng.lognormal(0.0, 0.35 * voice.roar, ncyc)
        dflow = dflow * per_cycle[np.floor(cycles).astype(int)]
    av = np.interp(ts, tf, AV)
    tr = np.interp(ts, tf, TR)
    if tr.any():
        # A real trill is two or three tongue taps at an uneven rate, not a
        # steady 27 Hz flutter (which, sustained, croaked like a frog).
        rate = 25 * (1 + 0.15 * _smooth_noise(n, 8, sr, rng))
        taps = 0.5 + 0.5 * np.cos(2 * np.pi * np.cumsum(rate) / sr)
        av = av * (1 - 0.6 * tr * taps ** 3)
    shimmer = 1 + 0.04 * _smooth_noise(n, 40, sr, rng)
    hp = design(2, 600, "highpass", sr)
    noise = sosfilt(hp, rng.standard_normal(n))
    ah = np.interp(ts, tf, AH)
    breath = voice.breath * av * (0.4 + flow)
    # Real voices turn aperiodic up high: tilt the harmonics down above ~3.5
    # kHz and let pulse-synchronous breath noise take over, otherwise held
    # vowels ring glassy on single harmonics.
    voiced_src = av * dflow * shimmer * voice.voicing
    tilt = sosfilt(design(2, voice.tilt, "lowpass", sr), voiced_src)
    high_noise = sosfilt(design(2, min(2500, voice.tilt), "highpass", sr), noise)
    aper = 0.6 * av * (0.3 + flow) * high_noise * np.sqrt(np.mean(dflow ** 2) + 1e-12)
    src = (0.5 * voiced_src + 0.5 * tilt if voice.tilt >= 3500 else tilt) + aper + (ah * 0.35 + breath * 0.35) * noise
    if voice.roar:
        # False vocal folds: turbulence riding on each glottal pulse.
        turb = sosfilt(design(2, [250, 3500], "bandpass", sr), rng.standard_normal(n))
        ref = np.sqrt(np.mean(av * dflow ** 2) + 1e-12)
        src = src + 1.1 * voice.roar * av * (0.2 + flow) * turb * ref

    # ---- cascade formant filter, coefficients updated per frame ----
    voiced = cascade(src, F, Bw, HOP, sr)

    # ---- frication and bursts, parallel noise bands ----
    fric = np.zeros(n)
    for (part, seg, d, _), s0 in zip(parts, starts):
        p = PHONES.get(seg.phone)
        if p is None:
            continue
        bands = None
        if p["kind"] == FRIC and part == "main":
            bands = p["fric"]
        elif p["kind"] == STOP and part == "burst":
            bands = p["burst"]
        if not bands:
            continue
        a0 = int(s0 * sr)
        m = int(d * sr)
        if m < 8:
            continue
        seg_noise = np.zeros(m)
        for cf, bw, g in bands:
            lo = max(cf - bw / 2, 80)
            hi = min(cf + bw / 2, 0.47 * sr)
            sos = design(2, [lo, hi], "bandpass", sr)
            seg_noise += g * sosfilt(sos, rng.standard_normal(m))
        if part == "burst":
            env = np.exp(-np.arange(m) / (0.004 * sr))
        else:
            # Soft, rounded onsets and offsets: hard ramps hissed like a valve.
            r = min(int(0.035 * sr), m // 2)
            env = np.ones(m)
            ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, r))
            env[:r] = ramp
            env[m - r:] = ramp[::-1]
        fric[a0:a0 + m] += seg_noise * env * seg.amp

    # Calibrate: voiced vowels near 0.1 RMS, frication relative to that.
    vowel = av > 0.9
    ref = np.sqrt(np.mean(voiced[vowel] ** 2)) if vowel.sum() > sr * 0.01 else np.sqrt(np.mean(voiced ** 2) + 1e-12)
    audio = voiced * (0.1 / (ref + 1e-9)) + fric * 0.12

    spans = []
    seen = {}
    for (part, seg, d, _), s0 in zip(parts, starts):
        if seg.tag is None:
            continue
        a0, b0 = int(s0 * sr), int((s0 + d) * sr)
        if seg.tag in seen:
            i = seen[seg.tag]
            spans[i] = (seg.tag, spans[i][1], b0)
        else:
            seen[seg.tag] = len(spans)
            spans.append((seg.tag, a0, b0))
    return Rendered(audio[: int(total * sr)], spans)
