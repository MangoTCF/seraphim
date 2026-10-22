"""Find sustained narrow-band tones (whistles) above 1.5 kHz in a signal."""
import sys
import numpy as np
from scipy.signal import stft

def whistles(x, sr, fmin=1500, min_dur=0.12, prominence_db=18):
    f, t, Z = stft(x, sr, nperseg=4096, noverlap=3072)
    mag = 20 * np.log10(np.abs(Z) + 1e-9)
    band = f >= fmin
    hits = []
    # A tonal peak: much louder than the spectrum ±300 Hz around it.
    k = int(300 / (f[1] - f[0]))
    from scipy.ndimage import median_filter
    floor = median_filter(mag, size=(2 * k + 1, 1), mode="nearest")
    prom = mag - floor
    loud = mag > (mag.max() - 50)
    tonal = (prom > prominence_db) & loud & band[:, None]
    # Track: same bin (±1) over consecutive frames.
    dt = t[1] - t[0]
    runs = {}
    for j in range(tonal.shape[1]):
        bins = np.flatnonzero(tonal[:, j])
        new = {}
        for b in bins:
            prev = next((runs[c] for c in (b - 1, b, b + 1) if c in runs), None)
            new[b] = (prev[0], prev[1] + 1, max(prev[2], prom[b, j])) if prev else (t[j], 1, prom[b, j])
        for b, r in runs.items():
            if not any(c in new for c in (b - 1, b, b + 1)) and r[1] * dt >= min_dur:
                hits.append((r[0], r[1] * dt, f[b], r[2]))
        runs = new
    for b, r in runs.items():
        if r[1] * dt >= min_dur:
            hits.append((r[0], r[1] * dt, f[b], r[2]))
    return sorted(hits)

if __name__ == "__main__":
    from scipy.io import wavfile
    for path in sys.argv[1:]:
        sr, x = wavfile.read(path)
        x = x.astype(float)
        if x.ndim > 1:
            x = x.mean(1)
        h = whistles(x, sr)
        tot = sum(d for _, d, _, _ in h)
        print(f"{path}: {len(h)} whistles, {tot:.1f} s total" + "".join(
            f"\n   t={s:6.2f}s  {d:4.2f}s  {fr:6.0f} Hz  +{p:.0f} dB" for s, d, fr, p in h[:8]))
