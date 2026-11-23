"""Render a matched formant/Miku comparison using locally imported banks.

    .venv/bin/python tools/demo_samplebanks.py

Uses all six Miku variants on the seven independently selectable channels;
Japanese Original is reused on the third prayer voice at its own chant register.
"""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.io import wavfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from seraphim.render import Options,plan,synthesize
from seraphim.samplebank import validate_selection
from seraphim.score import parse
from seraphim.synth import SR


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--score',type=Path,default=ROOT/'examples/kadosh.sera')
    parser.add_argument('--output',type=Path,default=ROOT/'out/miku-integration')
    args=parser.parse_args()
    assignments=dict(top='miku-jp-original',**{'1':'miku-en','2':'miku-jp-solid','end':'miku-jp-dark',
                     'praise-1':'miku-jp-soft','praise-2':'miku-jp-sweet','praise-3':'miku-jp-original'})
    validate_selection(assignments)
    args.output.mkdir(parents=True,exist_ok=True)
    text=args.score.read_text(encoding='utf-8')
    score=parse(text)
    score.meta['tempo']='1.5'
    for label,selection in [('formant',None),('miku-ensemble',assignments)]:
        opts=Options(jobs=1,room='dry',tones={'neutral':1},sample_banks=selection)
        resolved=plan(score,opts)
        audio,stems=synthesize(score,render_plan=resolved,progress=lambda m:print(f'{label}: {m}',flush=True))
        wavfile.write(args.output/f'{label}.wav',SR,audio.astype(np.float32))
        stem_directory=args.output/f'{label}-stems'
        stem_directory.mkdir(exist_ok=True)
        for name,samples in stems.items():
            wavfile.write(stem_directory/f'{name}.wav',SR,samples.astype(np.float32))
        (args.output/f'{label}-plan.json').write_text(json.dumps(resolved.summary(),indent=2,ensure_ascii=False)+'\n')
    print(f'Comparison saved in {args.output}')


if __name__=='__main__':
    main()
