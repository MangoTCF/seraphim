"""Objective proxies for listening complaints (frog-like croaks, valve-like
noise onsets, perceived pitch, brightness), per rendered stem set."""
import numpy as np
from scipy.signal import butter, sosfilt, welch, hilbert

SR = 44100

def frogness(x):
    """Share of envelope modulation at 15-80 Hz (croak pulsing) vs 2-80 Hz."""
    env = np.abs(hilbert(sosfilt(butter(2, [200, 3000], "bandpass", fs=SR, output="sos"), x)))
    env = sosfilt(butter(2, 150, "lowpass", fs=SR, output="sos"), env)[::49]       # 900 Hz
    f, P = welch(env - env.mean(), 900, nperseg=2048)
    return P[(f > 15) & (f < 80)].sum() / (P[(f > 2) & (f < 80)].sum() + 1e-12)

def valveness(x):
    """95th percentile of 10 ms jumps (dB) in >3.5 kHz noise energy, where loud."""
    h = sosfilt(butter(4, 3500, "highpass", fs=SR, output="sos"), x)
    fr = h[: len(h) // 441 * 441].reshape(-1, 441)
    db = 10 * np.log10((fr ** 2).mean(1) + 1e-12)
    loud = db > db.max() - 40
    d = np.abs(np.diff(db))[loud[1:] & loud[:-1]]
    return np.percentile(d, 95) if len(d) else 0.0

def pitch(x):
    """Median f0 of voiced 40 ms frames by autocorrelation (60-500 Hz)."""
    out = []
    n = int(0.04 * SR)
    for i in range(0, len(x) - n, n):
        fr = x[i:i + n] - x[i:i + n].mean()
        if np.sqrt((fr ** 2).mean()) < 0.02 * np.abs(x).max():
            continue
        ac = np.correlate(fr, fr, "full")[n - 1:]
        lo, hi = SR // 500, SR // 60
        k = lo + np.argmax(ac[lo:hi])
        if ac[k] > 0.45 * ac[0]:
            out.append(SR / k)
    return float(np.median(out)) if out else 0.0

def centroid(x):
    f, P = welch(x, SR, nperseg=4096)
    m = (f > 100) & (f < 5000)
    return float((f[m] * P[m]).sum() / P[m].sum())

def report(label, stems, keys=("mouth-top", "mouth-1", "mouth-2", "mouth-end")):
    xs = [stems[k] for k in keys]
    print(f"{label:<34} frog {np.mean([frogness(x) for x in xs]):.3f}  valve {np.mean([valveness(x) for x in xs]):5.1f} dB"
          f"  f0 {np.median([pitch(x) for x in xs]):5.0f} Hz  centroid {np.mean([centroid(x) for x in xs]):5.0f} Hz")

def frog_peak(x):
    """How spiky the 15-80 Hz envelope modulation is (max / median): a croak
    is a periodic pulse train and shows a sharp peak; roughness is flat."""
    env = np.abs(hilbert(sosfilt(butter(2, [200, 3000], "bandpass", fs=SR, output="sos"), x)))
    env = sosfilt(butter(2, 150, "lowpass", fs=SR, output="sos"), env)[::49]
    f, P = welch(env - env.mean(), 900, nperseg=4096)
    band = P[(f > 15) & (f < 80)]
    return float(band.max() / np.median(band))
