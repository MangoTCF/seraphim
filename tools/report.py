"""Objective proxies for listening complaints, on any score and options.

    tools/report.py score.sera [--dialect NAME] [--voice N]

Prints, averaged over the four mouths: croak-band envelope modulation
(frog-likeness), noise onset steepness (valve-likeness), median pitch and
spectral centroid; plus sustained-whistle counts above 3 kHz."""
import argparse
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from seraphim import render  # noqa: E402
from seraphim.score import parse  # noqa: E402
from metrics import report  # noqa: E402
from whistle import whistles  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("score")
ap.add_argument("--dialect")
ap.add_argument("--voice", type=float)
a = ap.parse_args()
score = parse(open(a.score, encoding="utf-8").read(), heresy=True, dialect=a.dialect)
out, stems = render.synthesize(score, render.Options(dialect=a.dialect, voice={"all": a.voice} if a.voice is not None else None))
report(os.path.basename(a.score), stems)
print("whistles >3 kHz in the mix:", len(whistles(out.mean(1), render.SR, fmin=3000)))
