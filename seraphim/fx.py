"""Effects: vowel brightness, 4D movement, binaural placement, reverb."""

from dataclasses import dataclass, replace

import numpy as np
from scipy.signal import butter, fftconvolve, lfilter, oaconvolve, sosfilt

from .synth import SR, _smooth_noise, design

HEAD_RADIUS = 0.0875
SOUND_SPEED = 343.0


# ---------------------------------------------------------------- filters

def sos_lowpass(fc, sr=SR):
    return design(2, fc, "lowpass", sr)


def high_shelf(x, freq, gain_db, sr=SR):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * freq / sr
    alpha = np.sin(w) / 2 * np.sqrt(2)
    cw = np.cos(w)
    b = [A * ((A + 1) + (A - 1) * cw + 2 * np.sqrt(A) * alpha),
         -2 * A * ((A - 1) + (A + 1) * cw),
         A * ((A + 1) + (A - 1) * cw - 2 * np.sqrt(A) * alpha)]
    a = [(A + 1) - (A - 1) * cw + 2 * np.sqrt(A) * alpha,
         2 * ((A - 1) - (A + 1) * cw),
         (A + 1) - (A - 1) * cw - 2 * np.sqrt(A) * alpha]
    return lfilter(np.array(b) / a[0], np.array(a) / a[0], x)


def peaking(x, freq, gain_db, q, sr=SR):
    A = 10 ** (gain_db / 40)
    w = 2 * np.pi * freq / sr
    alpha = np.sin(w) / (2 * q)
    cw = np.cos(w)
    b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
    a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    return lfilter(np.array(b) / a[0], np.array(a) / a[0], x)


def halo(x, delays=(0.011, 0.016), sr=SR):
    """Static doubled copies: a halo without the pitch wobble of a chorus."""
    out = np.zeros_like(x)
    for d in delays:
        k = int(d * sr)
        out[k:] += x[: len(x) - k] / len(delays)
    return out


def chorus(x, depth=0.003, base=0.011, rate=0.7, sr=SR):
    n = np.arange(len(x))
    d = (base + depth * np.sin(2 * np.pi * rate * n / sr)) * sr
    return np.interp(n - d, n, x, left=0.0)


# ---------------------------------------------------------------- brightness

def span_mask(spans, tags, n, fade=0.07, sr=SR):
    m = np.zeros(n)
    f = int(fade * sr)
    for tag, a, b in spans:
        if tag not in tags:
            continue
        a, b = max(a - f // 2, 0), min(b + f // 2, n)
        seg = np.ones(b - a)
        r = min(f, (b - a) // 2)
        if r:
            ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, r))
            seg[:r] = ramp
            seg[-r:] = ramp[::-1]
        m[a:b] = np.maximum(m[a:b], seg)
    return m


def _poisson_times(n, rate, rng, sr=SR):
    k = rng.poisson(rate * n / sr)
    return rng.integers(0, max(n, 1), k)


def sparkle(n, rng, rate=24, sr=SR):
    """Glitter: tiny grains of high band-limited noise, light made audible.
    Deliberately pitchless; sine pings here were heard as a whistle."""
    noise = sosfilt(design(2, [5000, 11000], "bandpass", sr), rng.standard_normal(n))
    env = np.zeros(n)
    L = int(0.012 * sr)
    grain = np.hanning(L)
    for p in _poisson_times(n, rate, rng):
        e = min(p + L, n)
        env[p:e] += grain[: e - p] * rng.uniform(0.3, 1)
    return noise * env


def geiger(n, rng, rate=55, sr=SR):
    """Crackle of an ionizing glow: sparse, irregular grains of filtered
    noise, each its own length, colour and strength (single-sample clicks
    sounded like a ticking mechanism)."""
    out = np.zeros(n)
    noise = rng.standard_normal(n)
    for p in _poisson_times(n, rate, rng):
        L = int(rng.uniform(0.001, 0.006) * sr)
        e = min(p + L, n)
        grain = noise[p:e] * np.exp(-np.arange(e - p) / (L / 3 + 1))
        out[p:e] += grain * rng.lognormal(-0.5, 0.6)
    lo = design(2, 1500, "highpass", sr)
    return sosfilt(lo, out)


def brighten(audio, spans, levels, octave=None, rng=None, sr=SR, glitter=1.0):
    """levels: {tag: 1|2|3}. octave: optional same line rendered an octave up.
    1 bright: airy shelf and a soft static halo.
    2 extra bright: stronger shelf, octave-up overtone voice and noise glitter.
    3 ionized: a drifting high glow of the voice itself and a sparse crackle."""
    rng = rng or np.random.default_rng(0)
    n = len(audio)
    y = audio.copy()
    ref = np.sqrt(np.mean(audio ** 2)) + 1e-9
    t = np.arange(n) / sr
    by = {lv: {tag for tag, l in levels.items() if l == lv} for lv in (1, 2, 3)}
    if by[1]:
        m = span_mask(spans, by[1], n)
        wet = high_shelf(audio, 3000, 5) + 0.3 * halo(audio)
        y = y * (1 - m) + wet * m
    if by[2]:
        m = span_mask(spans, by[2], n)
        wet = high_shelf(audio, 2500, 9) + 0.4 * halo(audio, (0.017, 0.023))
        if octave is not None:
            o = np.zeros(n)
            o[: min(n, len(octave))] = octave[:n]
            wet = wet + 0.45 * high_shelf(o, 2500, 6)
        if glitter:
            wet = wet + 0.8 * glitter * ref * sparkle(n, rng)
        y = y * (1 - m) + wet * m
    if by[3]:
        # Long, rounded fades: switching the glow on and off at token edges
        # sounded like a steam valve.
        m = span_mask(spans, by[3], n, fade=0.14)
        # A glow, not a hiss: the vowel itself turned up in the highs, its
        # intensity drifting slowly at random, with a sparse crackle riding
        # on the voice. Nothing periodic and nothing switched (earlier
        # versions: a ring modulator whistled or wobbled, arc flutter croaked,
        # broadband hiss hissed like steam).
        drift = np.clip(0.75 + 0.35 * _smooth_noise(n, 1.5, sr, rng), 0.3, 1.2)
        glow = high_shelf(audio, 2500, 5) + 0.2 * halo(audio, (0.007, 0.013))
        env = sosfilt(design(1, 20, "lowpass", sr), np.abs(audio))
        env /= env.max() + 1e-12
        wet = audio + drift * (glow - audio)
        wet = wet + 0.35 * ref * env * drift * geiger(n, rng, rate=30)
        y = y * (1 - m) + wet * m
    return y


# ---------------------------------------------------------------- damage

def wound(audio, rng, roar=0.0, whistle=0.0, wound_hz=4000.0, sr=SR):
    """Post-voice damage for the demonic dialect.

    roar: asymmetric saturation, the gnarl of a voice pushed through
    scar tissue. whistle: air escaping through a wound, two ways: sibilants
    and breath ring at this mouth's wound frequency, and now and then a
    gliding whistle rides on the voice."""
    n = len(audio)
    if n == 0:
        return audio
    ref = np.sqrt(np.mean(audio ** 2)) + 1e-9
    y = audio.copy()
    if roar:
        k = 1 + 4 * roar
        x = y / (3 * ref)
        y = np.tanh(k * x + 0.3 * roar * k * x ** 2) / np.tanh(k) * 3 * ref
    if whistle:
        env = sosfilt(design(1, 25, "lowpass", sr), np.abs(audio))
        # Whistling sibilants: a high-Q resonance on the hiss.
        hiss = sosfilt(design(2, 2800, "highpass", sr), audio)
        w0 = 2 * np.pi * wound_hz / sr
        q = 30
        alpha = np.sin(w0) / (2 * q)
        b = np.array([alpha, 0, -alpha]) / (1 + alpha)
        a = np.array([1, -2 * np.cos(w0) / (1 + alpha), (1 - alpha) / (1 + alpha)])
        ring = lfilter(b, a, hiss)
        ring *= ref / (np.sqrt(np.mean(ring ** 2)) + 1e-9)
        y = y + 0.5 * whistle * ring
        # Gliding wound whistles.
        for p in _poisson_times(n, 0.9 * whistle, rng):
            dur = rng.uniform(0.15, 0.6)
            L = min(int(dur * sr), n - p)
            if L < 64:
                continue
            t = np.arange(L) / sr
            f_a, f_b = rng.uniform(2200, 5500, 2)
            f = f_a + (f_b - f_a) * t / dur + 60 * np.sin(2 * np.pi * rng.uniform(3, 7) * t)
            tone = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.hanning(L)
            y[p:p + L] = y[p:p + L] + 1.1 * whistle * tone * env[p:p + L]
    return y


# ---------------------------------------------------------------- 4D movement

def temporal_swell(dry, ir, sr=SR):
    """Reverse reverb: the sound's echo arrives before the sound itself, as
    if it had been heard from the future. Returns (swell, lead) where the
    swell must start `lead` samples before `dry`."""
    rev = fftconvolve(dry[::-1], ir)[::-1]
    lead = len(ir) - 1
    return rev, lead


_SHORT_IRS = {}


def short_ir(seconds=1.4, rng=None, sr=SR):
    if rng is None and (seconds, sr) in _SHORT_IRS:
        return _SHORT_IRS[(seconds, sr)]
    ir = _short_ir(seconds, rng, sr)
    if rng is None:
        _SHORT_IRS[(seconds, sr)] = ir
    return ir


def _short_ir(seconds=1.4, rng=None, sr=SR):
    rng = rng or np.random.default_rng(1)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    ir = rng.standard_normal(n) * np.exp(-6.9 * t / seconds)
    sos = design(2, [300, 9000], "bandpass", sr)
    ir = sosfilt(sos, ir)
    return ir / np.sqrt(np.sum(ir ** 2))


# ---------------------------------------------------------------- space

def _head_shadow(x, theta, sr=SR):
    """Brown & Duda one-pole head shadow; theta = angle from the ear axis."""
    a_min, th_min = 0.1, np.deg2rad(150)
    alpha = (1 + a_min / 2) + (1 - a_min / 2) * np.cos(theta / th_min * np.pi)
    w0 = SOUND_SPEED / HEAD_RADIUS
    beta = 2 * w0
    K = 2 * sr
    b = np.array([alpha * K + beta, beta - alpha * K]) / (K + beta)
    a = np.array([1, (beta - K) / (K + beta)])
    return lfilter(b, a, x)


def _delay(x, d):
    """Constant fractional delay by d samples: two-tap interpolation on
    shifted slices (np.interp over the whole signal was a hotspot)."""
    if d <= 0:
        return x
    k = int(d)
    frac = d - k
    y = np.zeros_like(x)
    if k < len(x):
        y[k:] = (1 - frac) * x[: len(x) - k]
    if frac and k + 1 < len(x):
        y[k + 1:] += frac * x[: len(x) - k - 1]
    return y


def spatialize(x, az, el, dist, sr=SR):
    """Mono -> binaural stereo for a source at azimuth az (deg, + = right),
    elevation el (deg, + = up) and distance in metres."""
    a, e = np.deg2rad(az), np.deg2rad(el)
    src = np.array([np.sin(a) * np.cos(e), np.cos(a) * np.cos(e), np.sin(e)])
    out = []
    # Elevation colouring: a pinna notch that rises with elevation, and a
    # little extra air for sources above.
    y = peaking(x, 7000 + 2500 * np.sin(e), -9, 2.5, sr)
    y = high_shelf(y, 5000, 3 * np.sin(e), sr)
    if dist > 1.5:
        sos = design(1, max(16000 / dist, 4000), "lowpass", sr)
        y = sosfilt(sos, y)
    y = y / max(dist, 0.3)
    for ear in (np.array([-1.0, 0, 0]), np.array([1.0, 0, 0])):
        theta = np.arccos(np.clip(src @ ear, -1, 1))
        if theta < np.pi / 2:
            tau = -HEAD_RADIUS / SOUND_SPEED * np.cos(theta)
        else:
            tau = HEAD_RADIUS / SOUND_SPEED * (theta - np.pi / 2)
        tau += HEAD_RADIUS / SOUND_SPEED
        out.append(_delay(_head_shadow(y, theta, sr), tau * sr))
    return np.stack(out, axis=1)


@dataclass(frozen=True)
class Room:
    """A reverb: decay time, pre-delay, early reflections (seconds, gain;
    None = a random scatter), how much faster the highs die (hf_ratio),
    stereo width of the tail, and its default wet level."""
    name: str
    rt60: float
    predelay: float = 0.028
    early: tuple = None
    hf_ratio: float = 0.45
    width: float = 1.0
    wet: float = 1.0
    build: float = 0.05          # how long the tail takes to fill in
    lowpass: float = None        # darkens the whole tail (Hz)


ROOMS = {
    "cathedral": Room("cathedral", 3.3),
    # Measured from source-materials/video_2026-10-22_02-40-39.mp4: RT60 1.6-2.0 s
    # (median 1.75) over nine phrase endings, early reflections at ~16 and
    # ~23 ms, no echoes, a near-mono voice with a fully wide tail, the tail
    # darker than the voice (centroid 534 vs 758 Hz), the tail ~9 dB under
    # the voice 80 ms after each phrase. Calibrated with tools/roommeasure.py:
    # renders measure RT60 1.77 s and the tail at -9.1 dB, fully wide.
    "clip": Room("clip", 1.75, predelay=0.012, early=((0.0164, 0.55), (0.0226, 0.5), (0.031, 0.3), (0.043, 0.22)),
                 hf_ratio=0.3, width=1.0, wet=1.5, build=0.03, lowpass=1200),
    "hall": Room("hall", 2.2, predelay=0.02, hf_ratio=0.5),
    "plate": Room("plate", 1.4, predelay=0.0, early=(), hf_ratio=0.7, build=0.005),
    "room": Room("room", 0.6, predelay=0.006, hf_ratio=0.55, wet=0.6, build=0.01),
    "dry": Room("dry", 0.0, wet=0.0),
}


def room(name="cathedral", rt60=None, predelay=None, tone=None):
    """A room preset with optional overrides; tone 0 bright .. 1 dark."""
    if name not in ROOMS:
        raise ValueError(f"unknown room {name!r}; known: {', '.join(ROOMS)}")
    r = ROOMS[name]
    kw = {}
    if rt60 is not None:
        kw["rt60"] = rt60
    if predelay is not None:
        kw["predelay"] = predelay
    if tone is not None:
        kw["hf_ratio"] = 0.9 - 0.75 * min(max(tone, 0), 1)
    return replace(r, **kw) if kw else r


def room_ir(rm, rng=None, sr=SR):
    """Stereo impulse response for a Room: early reflections plus a noise
    tail whose highs die faster than its lows. Independent noise per channel
    makes the tail wide; width < 1 folds the channels together."""
    rng = rng or np.random.default_rng(7)
    if rm.rt60 <= 0:
        return None
    n = int((rm.rt60 * 1.15 + rm.predelay) * sr)
    t = np.arange(n) / sr
    lo = design(2, 3500, "lowpass", sr)
    hi = design(2, 3500, "highpass", sr)
    pre = int(rm.predelay * sr)
    build = max(int(rm.build * sr), 1)
    early = rm.early if rm.early is not None else tuple((d, rng.uniform(-0.6, 0.6)) for d in rng.uniform(0.008, 0.07, 9))
    chans = []
    for c in range(2):
        noise = rng.standard_normal(n)
        tail = sosfilt(lo, noise) * np.exp(-6.9 * t / rm.rt60) + sosfilt(hi, noise) * np.exp(-6.9 * t / (rm.rt60 * rm.hf_ratio))
        tail[:pre] = 0
        tail[pre:pre + build] *= np.linspace(0, 1, len(tail[pre:pre + build]))
        for k, (d, g) in enumerate(early):
            # The two ears hear each reflection a little apart.
            i = int((d + (0.0007 if (c + k) % 2 else 0)) * sr)
            if i < n:
                tail[i] += g * 25 * (1 if c == 0 or k % 2 == 0 else 0.8)
        chans.append(tail)
    left, right = chans
    right = rm.width * right + (1 - rm.width) * left
    if rm.lowpass:
        lp = design(1, rm.lowpass, "lowpass", sr)
        left, right = sosfilt(lp, left), sosfilt(lp, right)
    ir = np.stack([left, right], axis=1)
    return ir / np.sqrt(np.sum(ir ** 2) / 2)


def cathedral_ir(rng=None, sr=SR):
    return room_ir(ROOMS["cathedral"], rng, sr)


def reverb(stereo, ir):
    # Overlap-add: much cheaper than one huge FFT for a long signal and a
    # short impulse response.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(2) as ex:
        chans = list(ex.map(lambda c: oaconvolve(stereo[:, c], ir[:, c]), range(2)))
    return np.stack(chans, axis=1)
