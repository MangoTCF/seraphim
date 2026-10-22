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
    "succubus": Dialect("succubus", heresy=True, growl=0.25, fry=0.25, roar=0.1, whistle=0.0,
                        throat=0.1, pitch=0, disfigure=0.3, breath=0.65, moan=0.6, whisper=0.45,
                        grab=0.7, hunger=0.5, gender=0.85, choir="backmask", mode="phrygian", choir_pitch=0),
}
ALIASES = {"fallen": "demonic", "infernal": "demonic", "satanic": "demonic", "hellish": "demonic",
           "hell": "demonic", "angelic": "seraphic", "heavenly": "seraphic",
           "lilith": "succubus", "lilit": "succubus", "seductive": "succubus"}
KNOBS = [f.name for f in fields(Dialect) if f.type in (float, "float")]


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
