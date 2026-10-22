"""Render timing and determinism check.

    tools/benchmark.py [score.sera ...]

Renders each score in parallel and sequentially, prints the time and whether
the two outputs are bit-identical (they must be: every job seeds its own
random generator)."""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from seraphim import render  # noqa: E402
from seraphim.score import parse  # noqa: E402


def main(paths):
    for path in paths:
        score = parse(open(path, encoding="utf-8").read())
        t = time.perf_counter()
        par, _ = render.synthesize(score, render.Options(jobs=0))
        tp = time.perf_counter() - t
        t = time.perf_counter()
        seq, _ = render.synthesize(score, render.Options(jobs=1))
        ts = time.perf_counter() - t
        print(f"{path:<28} {len(par) / render.SR:6.1f} s audio | parallel {tp:5.1f} s, sequential {ts:5.1f} s"
              f" | identical: {np.array_equal(par, seq)}")


if __name__ == "__main__":
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "examples")
    main(sys.argv[1:] or sorted(os.path.join(here, f) for f in os.listdir(here) if f.endswith(".sera")))
