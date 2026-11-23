"""Convert an unpacked DDI/DDB pair into Seraphim's local sample-bank format.

Requires an inspected checkout of yuukawahiroshi/ddb-tools for DDI parsing:
  python tools/import_vocaloid_bank.py BANK.ddi --id miku-en --name 'Miku English'

The output contains local recordings and is intentionally excluded from Git.
"""
import argparse
import hashlib
import json
import mmap
from pathlib import Path
import struct
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]


def pointer(value):
    return int(value.split('=')[1].split('_')[0],16)


def convert(ddi, output, bank_id, name, language, parser_path):
    sys.path.insert(0,str(parser_path.resolve()))
    from utils.ddi_utils import DDIModel
    model=DDIModel(ddi.read_bytes());model.read()
    output.mkdir(parents=True,exist_ok=True)
    (output/'samples').mkdir(exist_ok=True)
    voiced=set(model.phdc_data['phoneme']['voiced'])
    candidates=[]
    for group in model.sta_data.values():
        phone=group['phoneme']
        # EVEC internal append markers are distinct styles, not IPA phones.
        if '#' in phone or phone.startswith('*'):
            continue
        for item in group['stap'].values():
            candidates.append(([phone],item,'stationary'))
    for group in model.art_data.values():
        for unit in group.get('artu',{}).values():
            phones=[group['phoneme'],unit['phoneme']]
            if any('#' in p or p.startswith('*') for p in phones):
                continue
            for item in unit['artp'].values():
                if len(item.get('frame_align',[]))==2:
                    candidates.append((phones,item,'transition'))
    units=[]
    source=ddi.with_suffix('.ddb')
    with source.open('rb') as file,mmap.mmap(file.fileno(),0,access=mmap.ACCESS_READ) as data:
        for phones,item,kind in candidates:
            offset=pointer(item['snd'])
            header=offset if kind=='transition' else data.rfind(b'SND ',max(0,offset-0x10000),offset+4)
            if header<0 or data[header:header+4]!=b'SND ':
                raise ValueError(f'Missing SND header at {offset:x}')
            size,rate,channels,frames=struct.unpack_from('<IIHI',data,header+4)
            if rate!=44100 or channels!=1 or size<18 or header+size>len(data) or size-18!=frames*2:
                raise ValueError(f'Unsupported or invalid sample at {header:x}')
            pcm=data[header+18:header+size]
            duration=len(pcm)/(rate*2)
            if kind=='stationary':
                start=(offset-header)/(rate*2)
                finish=(item['snd_length']-(offset-header))/(rate*2)
                regions=[dict(phone=phones[0],start=max(0,start),end=min(duration,finish))]
            else:
                origin=(pointer(item['snd_start'])-header)/(rate*2)
                regions=[dict(phone=p,start=max(0,origin+a['start']*256/rate),
                              end=min(duration,origin+a['end']*256/rate))
                         for p,a in zip(phones,item['frame_align'])]
            if any(r['end']<=r['start'] for r in regions):
                continue
            filename=f'samples/{header:016x}.wav'
            path=output/filename
            if not path.exists():
                with wave.open(str(path),'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate);wav.writeframes(pcm)
            units.append(dict(file=filename,sha256=hashlib.sha256(pcm).hexdigest(),phones=phones,
                              regions=regions,pitch_hz=440*2**(float(item['pitch1'])/1200),
                              kind=kind,voiced=[p in voiced for p in phones]))
    if not units:
        raise ValueError('No usable units were extracted.')
    manifest=dict(format=1,id=bank_id,name=name,language=language,sample_rate=44100,
                  source=dict(ddi_sha256=hashlib.sha256(ddi.read_bytes()).hexdigest(),ddb=source.name),units=units)
    temporary=output/'bank.json.tmp'
    temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');temporary.replace(output/'bank.json')
    print(f'{bank_id}: {len(units)} indexed units → {output}/bank.json',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ddi',type=Path)
    parser.add_argument('--id',required=True)
    parser.add_argument('--name',required=True)
    parser.add_argument('--language',choices=['english','japanese'],default='english')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--parser',type=Path,default=ROOT/'src/ddb-tools')
    args=parser.parse_args()
    if not args.id or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in args.id):
        parser.error('Bank ID must use lowercase letters, digits and hyphens.')
    convert(args.ddi,args.output or ROOT/'vocaloid-vbanks/converted'/args.id,
            args.id,args.name,args.language,args.parser)


if __name__=='__main__':
    main()
