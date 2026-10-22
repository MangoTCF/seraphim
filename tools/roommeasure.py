"""Measure a reverb room the way the source clip was measured: decay (RT60)
after the dry voice stops, tail level 80 ms after the end, stereo width of
the tail, and tail/voice brightness. Usage: tools/roommeasure.py [room ...]"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from seraphim import render
from seraphim.score import parse
SR = 44100
words = ["אלוקים הבא☀ אהבה", "שמים אור🔆 רקיע", "מתוק אש☢ גדול", "קרע אש🔆 נפש"]
def measure(room, reverb=None):
    rts, lvls, sides, cents = [], [], [], []
    for w in words:
        score = parse(f"word\n  top: {w}\n  1: {w}\n  2: {w}\n  end: {w}\n")
        out, _ = render.synthesize(score, render.Options(choir=False, hum=0, room=room, reverb=reverb, jobs=1))
        dry, _ = render.synthesize(score, render.Options(choir=False, hum=0, room="dry", jobs=1))
        mono = out.mean(1); L, R = out[:, 0], out[:, 1]
        fr = int(0.01 * SR)
        frames = lambda x: 10 * np.log10((x[: len(x) // fr * fr].reshape(-1, fr) ** 2).mean(1) + 1e-12)
        db, ddb = frames(mono), frames(dry.mean(1))
        peak = db.max(); loud = np.flatnonzero(db > peak - 20)
        end = np.flatnonzero(ddb > ddb.max() - 45)[-1]       # where the dry voice really stops
        lvls.append(db[end + 8] - np.median(db[loud]))
        seg = db[end + 3: end + 120]; stop = np.flatnonzero(seg < seg[0] - 35); k = stop[0] if len(stop) else len(seg)
        rts.append(60 / -np.polyfit(np.arange(k) * 0.01, seg[:k], 1)[0])
        a, b = (end + 10) * fr, (end + 60) * fr
        S_, M_ = (L - R) / 2, (L + R) / 2
        sides.append(10 * np.log10((S_[a:b] ** 2).sum() / (M_[a:b] ** 2).sum()))
        def cent(x):
            F = np.abs(np.fft.rfft(x * np.hanning(len(x)))) ** 2; f = np.fft.rfftfreq(len(x), 1 / SR); m = (f > 100) & (f < 8000)
            return (f[m] * F[m]).sum() / F[m].sum()
        cents.append(cent(mono[a:b]) / cent(mono[loud[0] * fr: end * fr]))
    print(f"{room:<10} RT60 {np.median(rts):.2f} s | tail 80 ms after end {np.median(lvls):+.1f} dB | "
          f"tail side/mid {np.median(sides):+.1f} dB | tail/voice brightness {np.median(cents):.2f}")
if __name__ == "__main__":
    print("clip (measured)  RT60 1.75 s | tail 80 ms after end  -9.2 dB | tail side/mid  +0.5 dB | tail/voice brightness 0.70")
    for name in sys.argv[1:] or ["clip"]:
        measure(name)
