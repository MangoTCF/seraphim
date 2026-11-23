"""Write dry transition A/Bs and a four-tense prayer comparison.

    .venv/bin/python tools/prayer_time_demo.py [output-directory]

Prayer clips are independently normalized for easy listening. The reference
uses linear ramps with current articulatory identities, not an archived build.
"""
from dataclasses import replace
from pathlib import Path
import json
import sys

import numpy as np
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from seraphim.render import Options, mouth_voice, synthesize
from seraphim.score import parse
from seraphim.synth import Seg, SR, render


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('out/prayer-time')
    output.mkdir(parents=True, exist_ok=True)
    score_text = 'word {tense}\n top: /26/☀\n 1: /45/☀'
    combined, manifest, cursor = [], [], 0.0
    for tense in ('farpast','gnomic','nearpast','nonpast'):
        _, stems = synthesize(parse(score_text.format(tense=tense)),
                              Options(jobs=1, room='dry', tones={'neutral':1}))
        # Keep the entry cue and the word itself; omit the long silent tail.
        audio = stems['praise-1'][int(.7*SR):int(3.2*SR)]
        peak = float(np.max(np.abs(audio)))
        if peak:
            audio = audio * (.7 / peak)
        wavfile.write(output / f'{tense}.wav', SR, audio.astype(np.float32))
        manifest.append(dict(tense=tense,start=cursor,end=cursor+len(audio)/SR))
        combined += [audio,np.zeros(SR//2)]
        cursor += len(audio)/SR + .5
    wavfile.write(output / 'prayer-tense-comparison.wav',SR,np.concatenate(combined).astype(np.float32))
    segments = [Seg('k',.08,(145,180)),Seg('i',.2,(180,160)),Seg('l',.07,(160,150)),
                Seg('a',.2,(150,190)),Seg('t',.08,(190,150)),Seg('u',.2,(150,145))]
    voice = mouth_voice('1')
    for strength,label in [(0,'linear'),(1,'smooth')]:
        audio = render(segments,replace(voice,transitions=strength),np.random.default_rng(4)).audio
        assert np.isfinite(audio).all()
        wavfile.write(output/f'transitions-{label}.wav',SR,audio.astype(np.float32))
    (output/'order.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'Wrote prayer and transition comparisons to {output}')


if __name__ == '__main__':
    main()
