"""How many of the four mouths sound at once, from rendered stems.

    tools/density.py STEMS_DIR      (made with: seraphim synth X.sera --stems STEMS_DIR)
"""
import sys, numpy as np
from scipy.io import wavfile
d = sys.argv[1]
act = []
for m in ("top", "1", "2", "end"):
    sr, x = wavfile.read(f"{d}/mouth-{m}.wav")
    x = x.astype(float) / 32768
    fr = x[: len(x) // 441 * 441].reshape(-1, 441)            # 10 ms frames
    rms = np.sqrt((fr ** 2).mean(1))
    act.append(rms > 0.02 * rms.max())
act = np.array(act)
n = act.sum(0)
speech = np.flatnonzero(n > 0)
n = n[speech[0]: speech[-1] + 1]
print(f"speech span {len(n) / 100:.1f} s; time with 0/1/2/3/4 mouths sounding: " +
      " ".join(f"{(n == k).mean() * 100:.0f}%" for k in range(5)) + f"; mean {n.mean():.2f}")
