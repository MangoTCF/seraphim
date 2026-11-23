"""Audit an extracted ddb-tools sample directory and make a vowel audition.

Usage: python tools/audit_voicebank.py out/miku-v4/english-samples out/miku-v4/audit
This inspects labelled WAV/LAB data; it does not run installers or synthesize a
VOCALOID performance. Output is local investigation material, not bundled assets.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import numpy as np
from scipy.io import wavfile
from scipy.signal import correlate, find_peaks


def pitch_estimate(audio, rate):
    """Rough verification only, using a stable middle portion of a held vowel."""
    center = len(audio) // 2
    half = min(int(rate * .12), len(audio) // 3)
    x = audio[max(0, center-half):center+half].astype(float)
    if len(x) < 100:
        return None
    x -= x.mean()
    x *= np.hanning(len(x))
    correlation = correlate(x, x, mode='full', method='fft')[len(x)-1:]
    low, high = int(rate/900), min(int(rate/100), len(x)-1)
    peaks, _ = find_peaks(correlation[low:high])
    if not len(peaks):
        return None
    peaks += low
    lag = int(peaks[np.argmax(correlation[peaks])])
    return rate / lag


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('samples', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    files = sorted(args.samples.rglob('*.wav'))
    formats, groups, invalid = Counter(), Counter(), []
    records = []
    for path in files:
        rate, pcm = wavfile.read(path)
        groups[path.relative_to(args.samples).parts[0]] += 1
        formats[(rate, str(pcm.dtype), 1 if pcm.ndim == 1 else pcm.shape[1])] += 1
        match = re.match(r'\[(.*?)\]_pit([+-][0-9.]+)_([0-9a-f]+)\.wav$', path.name)
        label = match.group(1) if match else None
        lab = path.parent.parent/'lab'/path.with_suffix('.lab').name
        alignment = []
        if lab.is_file():
            for line in lab.read_text().splitlines():
                start, end, phone = line.split(maxsplit=2)
                start, end = float(start)/1e7, float(end)/1e7
                # Extractor labels can include the 18-byte SND header in the
                # final endpoint; clamp that tiny excess to actual audio length.
                if start < 0 or end < start or end > len(pcm)/rate + .002:
                    invalid.append(dict(file=str(path),line=line))
                alignment.append(dict(start=max(0,start),end=min(end,len(pcm)/rate),phone=phone))
        records.append(dict(file=str(path.resolve()),label=label,seconds=len(pcm)/rate,rate=rate,
                            pitch_cents=float(match.group(2)) if match else None,
                            alignment=alignment))
    if invalid:
        raise ValueError(f'{len(invalid)} unexpected alignment ranges; first: {invalid[0]}')
    audition, labels, cursor = [], [], 0.0
    # XSAMPA spellings are filename-escaped by the extractor (: becomes ;).
    for phoneme in ['i;', 'e', '{', 'O;', 'u;']:
        candidates = [r for r in records if r['label'] == phoneme and '/sta/' in r['file']]
        if not candidates:
            continue
        record = min(candidates, key=lambda r:r['pitch_cents'])
        rate, pcm = wavfile.read(record['file'])
        audio = pcm.astype(float)/32768
        keep = next((a for a in record['alignment'] if a['phone']!='sil'),None)
        if keep:
            audio = audio[int(keep['start']*rate):int(keep['end']*rate)]
        f0 = pitch_estimate(audio,rate)
        audio = audio[:int(rate*.6)]
        fade = min(int(rate*.01),len(audio)//2)
        if fade:
            audio[:fade] *= np.linspace(0,1,fade)
            audio[-fade:] *= np.linspace(1,0,fade)
        peak = np.max(np.abs(audio)) if len(audio) else 0
        if peak:
            audio *= .7/peak
        labels.append(dict(phoneme=phoneme,start=cursor,end=cursor+len(audio)/rate,estimated_hz=f0,
                           recorded_pitch_cents=record['pitch_cents'],source=record['file']))
        audition.extend([audio,np.zeros(int(.25*rate))])
        cursor += len(audio)/rate+.25
    summary = dict(files=len(files),groups=dict(groups),formats=[dict(rate=k[0],dtype=k[1],channels=k[2],count=v) for k,v in formats.items()],
                   aligned=sum(bool(r['alignment']) for r in records),invalid_alignment_count=len(invalid),audition=labels)
    (args.output/'inventory.json').write_text(json.dumps(records,indent=2)+'\n')
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    if audition:
        wavfile.write(args.output/'recovered-vowels.wav',rate,np.concatenate(audition).astype(np.float32))
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
