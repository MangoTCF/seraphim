"""Compare off, moderate and strong Miku syllable blending on one dry mouth."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.io import wavfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from seraphim.render import Options,plan,synthesize
from seraphim.score import parse
from seraphim.synth import SR


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bank',default='miku-jp-original')
    parser.add_argument('--score',type=Path,default=ROOT/'examples/kadosh.sera')
    parser.add_argument('--output',type=Path,default=ROOT/'out/legato')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    score=parse(args.score.read_text());score.meta['tempo']='1.5'
    recordings={}
    for amount,label in [(0,'off'),(.5,'moderate'),(1,'strong')]:
        opts=Options(choir=False,room='dry',jobs=1,tones={'neutral':1},sample_banks={'top':args.bank},
                     syllable_blend=0,mouth_blend={'top':amount})
        resolved=plan(score,opts)
        _,stems=synthesize(score,render_plan=resolved)
        recordings[label]=stems['mouth-top']
        (args.output/f'{label}-plan.json').write_text(json.dumps(resolved.summary(),indent=2,ensure_ascii=False)+'\n')
    # Use one common gain so level continuity remains meaningfully comparable.
    peak=max(float(np.max(np.abs(a))) for a in recordings.values()) or 1
    for label,audio in recordings.items():
        wavfile.write(args.output/f'{label}.wav',SR,(audio*.75/peak).astype(np.float32))
    comparison=np.concatenate([recordings['off'],np.zeros(SR//2),recordings['strong']])*.75/peak
    wavfile.write(args.output/'off-then-strong.wav',SR,comparison.astype(np.float32))
    print(f'Wrote off/moderate/strong dry comparisons to {args.output}')


if __name__=='__main__':
    main()
