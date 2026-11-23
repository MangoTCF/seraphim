"""Write dry before/after samples of the same articulation exercise.

Run .venv/bin/python tools/articulation_demo.py [output-directory].
The reference disables new context/identity settings; it is not an archived build.
"""
from dataclasses import replace
from pathlib import Path
import json
import sys

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from seraphim.render import mouth_voice
from seraphim.synth import Seg, SR, render


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('out/articulation')
    output.mkdir(parents=True, exist_ok=True)
    phones = ['k','i','t','a','m','u','s','a','l','i','q','a']
    segments = [Seg(p, .15 if p in 'aiu' else .075, (160,160)) for p in phones]
    metrics = {}
    for mouth in ('top','1','2','end'):
        current = mouth_voice(mouth)
        reference = replace(current, jitter=.006, tilt=3500, coarticulation=0, articulation=1)
        for name, voice in [('reference',reference),('current',current)]:
            audio = render(segments, voice, rng=np.random.default_rng(41)).audio
            assert np.isfinite(audio).all()
            filename = f'{mouth}-{name}.wav'
            wavfile.write(output/filename,SR,audio.astype(np.float32))
            metrics[filename] = dict(seconds=len(audio)/SR,rms=float(np.sqrt(np.mean(audio**2))),peak=float(np.max(np.abs(audio))))
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    print(f'Wrote 8 dry A/B samples to {output}')


if __name__ == '__main__':
    main()
