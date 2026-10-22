"""Articulatory targets for the formant synthesizer, keyed by IPA symbol.

Formants are for a neutral adult tract; voices scale them. `fric` is a list of
(centre Hz, bandwidth Hz, gain) noise bands; `burst` likewise for stop releases.
"""

V = "vowel"
STOP = "stop"
FRIC = "fric"
NAS = "nasal"
APPROX = "approx"
TRILL = "trill"
GLOT = "glottal"
ASP = "aspirate"

# Place loci used during closures and as consonant formant targets.
LAB = (300, 900, 2300)
ALV = (320, 1700, 2650)
PAL = (280, 2200, 3000)
VEL = (300, 1900, 2400)
UVU = (450, 1150, 2450)
PHAR = (720, 1150, 2500)

PHONES = {
    # vowels: formants (F1, F2, F3), duration
    "a": dict(kind=V, f=(760, 1300, 2550), dur=0.13),
    "e": dict(kind=V, f=(440, 1950, 2600), dur=0.12),
    "ɛ": dict(kind=V, f=(580, 1800, 2550), dur=0.12),
    "i": dict(kind=V, f=(290, 2250, 3000), dur=0.11),
    "ɪ": dict(kind=V, f=(400, 2000, 2600), dur=0.09),
    "o": dict(kind=V, f=(450, 850, 2500), dur=0.12),
    "ɔ": dict(kind=V, f=(590, 920, 2500), dur=0.13),
    "u": dict(kind=V, f=(320, 800, 2350), dur=0.11),
    "ʊ": dict(kind=V, f=(420, 1000, 2400), dur=0.09),
    "y": dict(kind=V, f=(290, 1800, 2250), dur=0.11),
    "ə": dict(kind=V, f=(500, 1450, 2500), dur=0.055),
    "æ": dict(kind=V, f=(680, 1700, 2500), dur=0.13),

    # stops: closure locus, burst spectrum
    "p": dict(kind=STOP, voiced=False, f=LAB, burst=[(1100, 1500, 0.35)], dur=0.075),
    "b": dict(kind=STOP, voiced=True, f=LAB, burst=[(1100, 1500, 0.25)], dur=0.065),
    "t": dict(kind=STOP, voiced=False, f=ALV, burst=[(4200, 2500, 0.6)], dur=0.075),
    "d": dict(kind=STOP, voiced=True, f=ALV, burst=[(4000, 2500, 0.4)], dur=0.065),
    "tˤ": dict(kind=STOP, voiced=False, f=(420, 1150, 2500), burst=[(3500, 2200, 0.6)], dur=0.08),
    "k": dict(kind=STOP, voiced=False, f=VEL, burst=[(2300, 900, 0.6)], dur=0.08),
    "g": dict(kind=STOP, voiced=True, f=VEL, burst=[(2200, 900, 0.4)], dur=0.07),
    "q": dict(kind=STOP, voiced=False, f=UVU, burst=[(1300, 700, 0.6)], dur=0.085),
    "ʔ": dict(kind=GLOT, f=None, dur=0.05),

    # fricatives
    "f": dict(kind=FRIC, voiced=False, f=LAB, fric=[(3500, 5000, 0.18)], dur=0.09),
    "v": dict(kind=FRIC, voiced=True, f=LAB, fric=[(3500, 5000, 0.08)], dur=0.07),
    "ɸ": dict(kind=FRIC, voiced=False, f=LAB, fric=[(2500, 4000, 0.15)], dur=0.09),
    "θ": dict(kind=FRIC, voiced=False, f=ALV, fric=[(5000, 6000, 0.17)], dur=0.09),
    "ð": dict(kind=FRIC, voiced=True, f=ALV, fric=[(5000, 6000, 0.07)], dur=0.07),
    "s": dict(kind=FRIC, voiced=False, f=ALV, fric=[(7000, 3000, 0.5)], dur=0.1),
    "z": dict(kind=FRIC, voiced=True, f=ALV, fric=[(7000, 3000, 0.25)], dur=0.085),
    "sˤ": dict(kind=FRIC, voiced=False, f=(450, 1100, 2450), fric=[(5800, 2800, 0.5)], dur=0.11),
    "ʃ": dict(kind=FRIC, voiced=False, f=PAL, fric=[(3300, 2000, 0.55)], dur=0.1),
    "ʒ": dict(kind=FRIC, voiced=True, f=PAL, fric=[(3300, 2000, 0.3)], dur=0.085),
    "x": dict(kind=FRIC, voiced=False, f=VEL, fric=[(1800, 900, 0.45), (3600, 1500, 0.15)], dur=0.1),
    "ɣ": dict(kind=FRIC, voiced=True, f=VEL, fric=[(1800, 900, 0.18)], dur=0.075),
    "χ": dict(kind=FRIC, voiced=False, f=UVU, fric=[(1300, 800, 0.5)], dur=0.1),
    "ç": dict(kind=FRIC, voiced=False, f=PAL, fric=[(4200, 2000, 0.5)], dur=0.1),
    "ʝ": dict(kind=FRIC, voiced=True, f=PAL, fric=[(4200, 2000, 0.15)], dur=0.075),
    "ħ": dict(kind=ASP, f=PHAR, asp=1.0, dur=0.1),
    "h": dict(kind=ASP, f=None, asp=0.75, dur=0.075),

    # sonorants
    "m": dict(kind=NAS, f=(260, 1100, 2200), dur=0.075),
    "n": dict(kind=NAS, f=(260, 1600, 2600), dur=0.07),
    "ŋ": dict(kind=NAS, f=(260, 2000, 2500), dur=0.07),
    "l": dict(kind=APPROX, f=(360, 1100, 2700), dur=0.065),
    "j": dict(kind=APPROX, f=(270, 2200, 3050), dur=0.055),
    "w": dict(kind=APPROX, f=(300, 700, 2300), dur=0.055),
    "ʕ": dict(kind=APPROX, f=PHAR, creak=True, dur=0.08),
    "r": dict(kind=TRILL, f=(400, 1350, 1750), dur=0.08),
    "ɾ": dict(kind=TRILL, f=(400, 1500, 2300), dur=0.035),
}

AFFRICATES = {"ts": ("t", "s"), "tʃ": ("t", "ʃ"), "dz": ("d", "z"), "dʒ": ("d", "ʒ")}
SYMBOLS = sorted(list(PHONES) + list(AFFRICATES), key=len, reverse=True)


def tokenize_ipa(s):
    """IPA string -> list of (phone, long, stressed). Unknown symbols skipped;
    spaces become word breaks ('#'), '|' becomes a phrase break."""
    out = []
    i = 0
    stress = False
    while i < len(s):
        c = s[i]
        if c in "ˈ":
            stress = True
            i += 1
            continue
        if c in "ˌ.":
            i += 1
            continue
        if c == " ":
            out.append(("#", False, False))
            i += 1
            continue
        if c == "|":
            out.append(("|", False, False))
            i += 1
            continue
        for sym in SYMBOLS:
            if s.startswith(sym, i):
                i += len(sym)
                long_ = False
                while i < len(s) and s[i] in "ːʰ":
                    long_ = long_ or s[i] == "ː"
                    i += 1
                parts = AFFRICATES.get(sym, (sym,))
                for p in parts:
                    out.append((p, long_, stress))
                    if PHONES[p]["kind"] == V:
                        stress = False
                break
        else:
            i += 1
    return out
