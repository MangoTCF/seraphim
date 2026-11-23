"""Dialects: grammar permissions, voice damage and choir behaviour.

seraphic   The default. Names of God are forbidden as phonemes; the praise
           voices sing the prayers.
demonic    The fallen. Heresy is allowed (names of God may be phonemes), and the
           fall left the voices disfigured:
             growl     torn vocal folds vibrate unevenly: every other pulse is
                       weakened, giving a subharmonic an octave down
             fry       creaky, irregular low pulses
             roar      turbulent false-fold noise and asymmetric distortion
             whistle   air whistling through wounds: gliding whistles, and
                       sibilants whistling at each mouth's wound frequency
             throat    a constricted pharynx and a longer, lower tract
             pitch     overall shift in semitones
             disfigure how unevenly the damage is spread over the mouths
           The praise voices blaspheme: the prayers backmasked, an octave down,
           in Locrian, the mode built on the tritone.
succubus   Hellish grammar (heresy) in a seductive voice: feminine by default,
           breathy and moaning, whispering right at your ears, with only a
           trace of the fall (a little fry, a low growl underneath). The
           choir sings backwards in Phrygian.
cupid      A light masculine voice with lilting vowels and a close whisper.
           The playful melody falls into a dismissive close at sentence ends.

nephilim   Half-angel, half-fallen (Genesis 6). Two diagonal mouths are
           seraphic, the other two fallen: succubus if that mouth's voice is
           feminine, demonic otherwise. The halves trade sides at sentence
           starts (and now and then mid-sentence), as often as `swap` says.
           Voices default to a mix across the mouths. The choir is torn: two
           praise voices sing forward, the middle one blasphemes backwards
           in Locrian against them.
             swap      0 fixed halves .. 1 trading sides at every sentence and often within

Style knobs, for every dialect:
             breath    breathiness: more air, softer folds, darker highs
             moan      sustained, sliding, swelling vowels and soft sighs
             whisper   a whispered double of every mouth, close to the ears
             grab      the voices pull in: from their places to right at your
                       ears over each sentence, lurching closer on hungry and
                       tender words; moans scoop up and swell; a breath in
                       before each sentence
             hunger    the cannibal half: teeth snapping after hungry words,
                       wet slurps, kisses on tender words, growl surges

Every knob can be overridden on the command line (--growl 0.9) or in a score
(@growl: 0.9).
"""

import random
from dataclasses import dataclass, fields, replace

MOUTHS = ("top", "1", "2", "end")
DAMAGE = ("growl", "fry", "roar", "whistle", "throat")
STYLE = ("breath", "moan", "whisper", "grab", "hunger")


@dataclass(frozen=True)
class Dialect:
    name: str
    heresy: bool = False
    growl: float = 0.0
    fry: float = 0.0
    roar: float = 0.0
    whistle: float = 0.0
    throat: float = 0.0
    pitch: float = 0.0          # semitones
    disfigure: float = 0.0
    breath: float = 0.0
    moan: float = 0.0
    whisper: float = 0.0
    grab: float = 0.0
    hunger: float = 0.0
    gender: float = None        # default voice (-1..1) when -v isn't given
    tone: str = None            # default tonal marker for words that carry none
    swap: float = 0.0           # nephilim: how often the halves trade sides
    voices: str = None          # default per-mouth voices when -v isn't given
    composite: bool = False     # made of other dialects, mouth by mouth
    choir: str = "praise"       # praise | backmask
    mode: str = "dorian"        # dorian | locrian | phrygian
    choir_pitch: float = 0.0    # semitones

    def mouth(self, m, seed=0):
        """This dialect's damage for one mouth: each knob scaled by a per-mouth
        factor in [1 - disfigure, 1 + disfigure], fixed for a given seed."""
        rng = random.Random(f"{seed}:{m}")
        d = min(max(self.disfigure, 0), 1)
        return {k: getattr(self, k) * rng.uniform(1 - d, 1 + d) for k in DAMAGE}

    def choir_damage(self):
        return {k: getattr(self, k) * 0.5 for k in DAMAGE}

    @property
    def damaged(self):
        return any(getattr(self, k) for k in DAMAGE)


DIALECTS = {
    # Higher beings: by default every unmarked word is a little condescending.
    "seraphic": Dialect("seraphic", tone="condescend:0.6"),
    "demonic": Dialect("demonic", heresy=True, growl=0.8, fry=0.4, roar=0.55, whistle=0.45,
                       throat=0.6, pitch=-4, disfigure=0.7, hunger=0.3, choir="backmask", mode="locrian",
                       choir_pitch=-12),
    "nephilim": Dialect("nephilim", heresy=True, swap=0.5, composite=True, choir="torn",
                        voices="top=-0.4,1=0.8,2=0.6,end=-0.8"),
    "succubus": Dialect("succubus", heresy=True, growl=0.25, fry=0.25, roar=0.1, whistle=0.0,
                        throat=0.1, pitch=0, disfigure=0.3, breath=0.65, moan=0.6, whisper=0.45,
                        grab=0.7, hunger=0.5, gender=0.85, choir="backmask", mode="phrygian", choir_pitch=0),
    "cupid": Dialect("cupid", gender=-0.55, pitch=2, breath=0.34, moan=0.22,
                     whisper=0.38, grab=0.28, tone="condescend:0.65"),
}
ALIASES = {"fallen": "demonic", "infernal": "demonic", "satanic": "demonic", "hellish": "demonic",
           "hell": "demonic", "angelic": "seraphic", "heavenly": "seraphic",
           "lilith": "succubus", "lilit": "succubus", "seductive": "succubus",
           "eros": "cupid",
           "nephil": "nephilim", "hybrid": "nephilim", "grigori": "nephilim"}
KNOBS = [f.name for f in fields(Dialect) if f.type in (float, "float")]


def roles(dia, words, gender, seed=0, knobs=None):
    """The dialect of every mouth at every word: {(word, mouth): Dialect}.
    For an ordinary dialect that's itself everywhere. For a composite one
    (nephilim) the diagonal halves are seraphic and fallen (succubus for a
    feminine voice, demonic otherwise), trading sides now and then."""
    if not dia.composite:
        return {(wi, m): dia for wi in range(len(words)) for m in MOUTHS}
    parts = {k: get(k, knobs) for k in ("seraphic", "demonic", "succubus")}
    rng = random.Random(f"{seed}:nephilim")
    angel = {"top", "2"}
    out = {}
    for wi, w in enumerate(words):
        if wi:
            p = dia.swap if w.sentence_start else dia.swap * 0.25
            if rng.random() < p:
                angel = set(MOUTHS) - angel
        for m in MOUTHS:
            g = gender.get(m, gender.get("all", 0))
            out[(wi, m)] = parts["seraphic"] if m in angel else parts["succubus" if g > 0.3 else "demonic"]
    return out


def names():
    return sorted(DIALECTS) + sorted(ALIASES)


def get(name=None, overrides=None):
    """Look a dialect up by name or alias and apply knob overrides
    ({'growl': 0.9, ...}; strings are fine, as they come from scores)."""
    key = (name or "seraphic").strip().lower()
    key = ALIASES.get(key, key)
    if key not in DIALECTS:
        raise ValueError(f"unknown dialect {name!r}; known: {', '.join(names())}")
    d = DIALECTS[key]
    vals = {k: float(v) for k, v in (overrides or {}).items() if k in KNOBS and v is not None}
    return replace(d, **vals) if vals else d
