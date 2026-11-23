"""Optional local sample-bank rendering through WORLD spectral resynthesis.

No recordings ship with Seraphim. Manifests refer to converted local banks.
"""
from collections import Counter, defaultdict
from functools import lru_cache
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import warnings

import numpy as np
from scipy.io import wavfile
from scipy.ndimage import gaussian_filter1d

from .phones import PHONES, V, NAS, APPROX, TRILL
from .score import ScoreError
from .synth import SR, Rendered, interpolate_track

CHANNELS = ('top','1','2','end','praise-1','praise-2','praise-3')
KEYS = (*CHANNELS,'all','choir')
EN_EXACT = dict(zip(
    ['i','ɪ','u','ʊ','ɛ','ɔ','æ','ə','m','n','ŋ','b','d','g','p','t','k','f','v','θ','ð','s','z','ʃ','ʒ','h','l','j','w'],
    ['i:','I','u:','U','e','O:','{','@','m','n','N','b','d','g','p','t','k','f','v','T','D','s','z','S','Z','h','l','j','w']))
EN_APPROX = {'a':'Q','e':'e','o':'O:','y':'u:','r':'r','ɾ':'r','ɸ':'f'}
JP_EXACT = {'a':'a','i':'i','e':'e','o':'o','m':'m','n':'n','ŋ':'N','b':'b','d':'d','g':'g',
            'p':'p','t':'t','k':'k','s':'s','z':'z','h':'h','ç':'C','ɸ':'p\\','ɾ':'4','j':'j','w':'w'}
JP_APPROX = {'u':'M','ʊ':'M','ɪ':'i','ɛ':'e','ɔ':'o','æ':'a','ə':'a','y':'i','r':'4','l':'4',
             'f':'p\\','v':'b','θ':'s','ð':'z','ʃ':'S','ʒ':'Z'}


def roots():
    configured = os.environ.get('SERAPHIM_BANK_DIR')
    if configured:
        return [Path(p).expanduser().resolve() for p in configured.split(os.pathsep) if p]
    return [Path(__file__).resolve().parent.parent/'vocaloid-vbanks/converted',
            Path.home()/'.local/share/seraphim/voicebanks']


def manifests():
    found = {}
    for root in roots():
        if root.is_dir():
            for path in sorted(root.glob('*/bank.json')):
                bank_id = path.parent.name
                if bank_id not in found:
                    found[bank_id] = path
    return found


def catalog():
    records=[]
    ready=importlib.util.find_spec('pyworld') is not None
    for bank_id,path in manifests().items():
        try:
            data=json.loads(path.read_text())
            if data.get('format')!=1 or not isinstance(data.get('units'),list) or not data['units']:
                continue
            records.append(dict(id=bank_id,name=data.get('name',bank_id),language=data.get('language','unknown'),
                                units=len(data['units']),ready=ready))
        except (OSError,ValueError,TypeError):
            continue
    return records


def validate_selection(selection):
    if selection is None:
        return {}
    if not isinstance(selection,dict) or set(selection)-set(KEYS):
        raise ScoreError('Sample-bank assignment keys must be all, choir, top, 1, 2, end or praise-1/2/3.')
    available=manifests()
    for key,value in selection.items():
        if not isinstance(value,str) or (value and value not in available):
            raise ScoreError(f'Unknown sample bank for {key}: {value!r}')
    if any(selection.values()):
        world()
    return dict(selection)


def parse_selection(spec):
    out={}
    for item in str(spec).split(','):
        key,sep,value=item.partition('=')
        if not sep:
            key,value='all',key
        key,value=key.strip(),value.strip()
        if key not in KEYS or not value:
            raise ValueError('Use BANK or top=BANK,1=BANK,choir=BANK,praise-1=BANK; formant selects the built-in synth.')
        out[key]='' if value=='formant' else value
    return out


def selected(selection,channel):
    selection=selection or {}
    if channel in selection:
        return selection[channel] or None
    if channel.startswith('praise-') and 'choir' in selection:
        return selection['choir'] or None
    return selection.get('all') or None


@lru_cache(maxsize=1)
def world():
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message="pkg_resources is deprecated as an API.*", category=UserWarning)
            import pyworld
        return pyworld
    except ImportError as exc:
        raise ScoreError("Sample banks need optional dependencies: install Seraphim with '.[samples]'.") from exc


class Bank:
    def __init__(self,path):
        self.path=Path(path).resolve()
        data=json.loads(self.path.read_text())
        if data.get('format')!=1 or data.get('language') not in ('english','japanese') or not data.get('units'):
            raise ScoreError(f'Unsupported sample-bank manifest: {self.path}')
        self.name=data.get('name',self.path.parent.name)
        self.language=data['language']
        self.pairs=defaultdict(list)
        self.singles=defaultdict(list)
        for unit in data['units']:
            path=(self.path.parent/unit['file']).resolve()
            if not path.is_relative_to(self.path.parent) or path.suffix.lower()!='.wav':
                raise ScoreError('A sample-bank unit must be a WAV inside its bank directory.')
            if len(unit['phones'])!=len(unit['regions']) or not 1<=len(unit['phones'])<=2:
                raise ScoreError('Expected aligned one- or two-phoneme sample units.')
            if not math.isfinite(unit['pitch_hz']) or unit['pitch_hz']<0:
                raise ScoreError('Invalid recorded sample pitch.')
            for region in unit['regions']:
                if not all(math.isfinite(region[k]) for k in ('start','end')) or not 0<=region['start']<region['end']:
                    raise ScoreError('Invalid sample alignment.')
            unit=dict(unit,path=str(path))
            if len(unit['phones'])==2:
                self.pairs[tuple(unit['phones'])].append(unit)
            for i,phone in enumerate(unit['phones']):
                self.singles[phone].append((unit,i))

    def mapping(self,phone,approximate=True):
        exact=EN_EXACT if self.language=='english' else JP_EXACT
        aliases=EN_APPROX if self.language=='english' else JP_APPROX
        native=exact.get(phone)
        status='sample'
        if native is None and approximate:
            native=aliases.get(phone)
            status='approximation'
        if native not in self.singles:
            return None,'formant'
        return native,status

    def choose(self,candidates,pitch,stationary=False):
        return min(candidates,key=lambda item:(
            (0 if not stationary or item[0].get('kind')=='stationary' else .7) +
            (abs(math.log2(item[0]['pitch_hz']/max(pitch,1))) if item[0]['pitch_hz'] else 0),item[0]['file'],item[1]))


@lru_cache(maxsize=12)
def _bank(path,mtime):
    return Bank(path)


def load(bank_id):
    path=manifests().get(bank_id)
    if path is None:
        raise ScoreError(f'Sample bank {bank_id!r} is not installed.')
    return _bank(str(path),path.stat().st_mtime_ns)


def coverage(bank_id,phones,approximate=True):
    bank=load(bank_id)
    grouped=defaultdict(Counter)
    mapping={}
    for phone in phones:
        if phone not in PHONES:
            continue
        native,kind=bank.mapping(phone,approximate)
        grouped[kind][phone]+=1
        if native:
            mapping[phone]=native
    return dict(bank=bank_id,name=bank.name,counts={k:dict(v) for k,v in grouped.items()},mapping=mapping)


@lru_cache(maxsize=64)
def _features(path,stamp,size,cache_directory):
    pw=world()
    source=Path(path)
    cache=Path(cache_directory)
    cache.mkdir(exist_ok=True)
    signature=f'world-v1:{pw.__version__}:{path}:{stamp}:{size}'.encode()
    destination=cache/(hashlib.sha256(signature).hexdigest()+'.npz')
    if destination.exists():
        try:
            with np.load(destination,allow_pickle=False) as data:
                return tuple(data[key] for key in ('time','f0','sp','ap'))
        except (OSError,ValueError,KeyError):
            pass
    rate,pcm=wavfile.read(source)
    if rate!=SR or pcm.ndim!=1 or pcm.dtype!=np.int16:
        raise ScoreError('Sample banks currently require mono 44.1 kHz PCM16 recordings.')
    audio=np.ascontiguousarray(pcm,dtype=np.float64)/32768
    if len(audio)<512:
        audio=np.pad(audio,(0,512-len(audio)))
    f0,time=pw.dio(audio,SR,f0_floor=80,f0_ceil=1000,frame_period=5)
    f0=pw.stonemask(audio,f0,time,SR)
    sp=pw.cheaptrick(audio,f0,time,SR,fft_size=2048)
    ap=pw.d4c(audio,f0,time,SR,fft_size=2048)
    rms=float(np.sqrt(np.mean(audio**2)))
    sp *= (.085/max(rms,1e-5))**2
    fd,temporary=tempfile.mkstemp(prefix='.world-',suffix='.npz',dir=cache)
    try:
        with os.fdopen(fd,'wb') as handle:
            np.savez_compressed(handle,time=time,f0=f0,sp=sp,ap=ap)
        os.replace(temporary,destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return time,f0,sp,ap


def render(segs,voice,rng,bank_id,approximate=True,default_f0=None):
    """Select units, time-warp their envelopes, then synthesize one continuous line.

    Formant spectra fill unsupported phones. All phonemes keep their original
    boundaries and tags; WORLD supplies a continuous excitation across joins.
    """
    from .synth import render as formant_render
    pw=world();bank=load(bank_id)
    durations=np.array([s.dur for s in segs],dtype=float)
    starts=np.r_[0,np.cumsum(durations)]
    n=int(starts[-1]*SR) if len(segs) else 0
    if not n:
        return Rendered(np.zeros(0))
    frame_time=np.arange(int(np.ceil(starts[-1]/.005))+1)*.005
    bins=1025
    sp=np.full((len(frame_time),bins),1e-12)
    ap=np.ones_like(sp)
    f0=np.zeros(len(frame_time))
    amp=np.zeros(len(frame_time))
    choices=[None]*len(segs)
    mapped=[bank.mapping(s.phone,approximate)[0] if s.phone in PHONES else None for s in segs]
    base=default_f0 or voice.f0
    def pitch(seg):
        return sum(seg.f0)/2 if seg.f0 else base
    i=0
    while i<len(segs):
        if i+1<len(segs) and mapped[i] and mapped[i+1] and (mapped[i],mapped[i+1]) in bank.pairs:
            pair=bank.pairs[(mapped[i],mapped[i+1])]
            unit,_=bank.choose([(u,0) for u in pair],(pitch(segs[i])+pitch(segs[i+1]))/2)
            choices[i],choices[i+1]=(unit,0),(unit,1)
            i+=2
        else:
            if mapped[i]:
                choices[i]=bank.choose(bank.singles[mapped[i]],pitch(segs[i]),stationary=True)
            i+=1
    unsupported=any(s.phone in PHONES and choices[i] is None for i,s in enumerate(segs))
    fallback=None
    if unsupported:
        # Analyze the existing renderer once, then borrow only missing regions.
        fallback_audio=formant_render(segs,voice,rng,default_f0=default_f0).audio
        if len(fallback_audio)<2048:
            fallback_audio=np.pad(fallback_audio,(0,2048-len(fallback_audio)))
        f,t=pw.dio(np.ascontiguousarray(fallback_audio),SR,f0_floor=60,f0_ceil=1200,frame_period=5)
        f=pw.stonemask(fallback_audio,f,t,SR)
        fallback=(t,f,pw.cheaptrick(fallback_audio,f,t,SR,fft_size=2048),pw.d4c(fallback_audio,f,t,SR,fft_size=2048))
    def unit_frames(choice,index,rows):
        unit,region_index=choice
        path=Path(unit['path']);stat=path.stat()
        time,source_f0,source_sp,source_ap=_features(str(path),stat.st_mtime_ns,stat.st_size,str(bank.path.parent/'world-cache'))
        region=unit['regions'][region_index]
        low,high=region['start'],min(region['end'],time[-1])
        if unit.get('kind')=='stationary' and PHONES[segs[index].phone]['kind']==V:
            margin=(high-low)*.12;low+=margin;high-=margin
        progress=(frame_time[rows]-starts[index])/max(segs[index].dur,1e-9)
        return interpolate_features(time,source_f0,source_sp,source_ap,low+progress*(high-low))

    def interpolate_features(time,source_f0,source_sp,source_ap,queries):
        fractional=np.interp(queries,time,np.arange(len(time)))
        left=np.floor(fractional).astype(int);right=np.minimum(left+1,len(time)-1)
        weight=(fractional-left)[:,None]
        logs=(1-weight)*np.log(np.maximum(source_sp[left],1e-12))+weight*np.log(np.maximum(source_sp[right],1e-12))
        return logs,(1-weight)*source_ap[left]+weight*source_ap[right],np.interp(queries,time,source_f0)

    for index,seg in enumerate(segs):
        rows=np.flatnonzero((frame_time>=starts[index])&(frame_time<starts[index+1]))
        if not len(rows) or seg.phone not in PHONES:
            continue
        choice=choices[index]
        if choice:
            logs,noise,source_pitch=unit_frames(choice,index,rows)
        else:
            logs,noise,source_pitch=interpolate_features(*fallback,frame_time[rows])
        sp[rows]=np.exp(logs)
        ap[rows]=noise
        phone=PHONES[seg.phone]
        voiced=phone['kind'] in (V,NAS,APPROX,TRILL)
        mask=np.ones(len(rows),dtype=bool) if voiced else source_pitch>0
        if not voiced and not phone.get('voiced',False):
            mask[:]=False
        a,b=seg.f0 or (base,base)
        f0[rows]=interpolate_track([starts[index],starts[index+1]],[a,b],frame_time[rows],voice.transitions)*mask
        amp[rows]=seg.amp
    # Internal, generated word-join slots are not score rests. Keep the preceding
    # vowel/sonorant alive through the scheduling gap; interpolate when the next
    # sound is voiced. Explicit silences and consonant closures are untouched.
    for index,seg in enumerate(segs):
        if seg.phone!='_join':
            continue
        rows=np.flatnonzero((frame_time>=starts[index])&(frame_time<starts[index+1]))
        if not len(rows):
            continue
        a,b=rows[0]-1,rows[-1]+1
        if a<0 or b>=len(frame_time) or amp[a]<=0:
            continue
        u=(frame_time[rows]-starts[index])/max(seg.dur,1e-9)
        u=u*u*(3-2*u)
        if f0[a]>0 and f0[b]>0:
            sp[rows]=np.exp((1-u[:,None])*np.log(np.maximum(sp[a],1e-12))+u[:,None]*np.log(np.maximum(sp[b],1e-12)))
            ap[rows]=(1-u[:,None])*ap[a]+u[:,None]*ap[b]
            f0[rows]=np.exp((1-u)*np.log(f0[a])+u*np.log(f0[b]))
            amp[rows]=((1-u)*amp[a]+u*amp[b])*seg.amp
        else:
            sp[rows]=sp[a];ap[rows]=ap[a];f0[rows]=f0[a];amp[rows]=amp[a]*seg.amp
    # Smooth unit joins in the spectral domain; preserve stops and true silence.
    logs=np.log(np.maximum(sp,1e-12))
    smoothed=gaussian_filter1d(logs,.8*voice.transitions,axis=0,mode='nearest') if voice.transitions else logs
    for index in range(1,len(segs)):
        left,right=PHONES.get(segs[index-1].phone),PHONES.get(segs[index].phone)
        if not left or not right or left['kind'] in ('stop','glottal') or right['kind'] in ('stop','glottal'):
            continue
        join=np.abs(frame_time-starts[index])<.015
        sp[join]=np.exp(smoothed[join])
    if voice.syllable_blend:
        from .legato import blend_features
        sp,ap,f0,amp=blend_features(sp,ap,f0,amp,frame_time,segs,starts,voice.syllable_blend)
    # Relative spectral scaling retains native character at neutral settings.
    scale=np.clip(voice.fscale/1.08*(1-.08*voice.throat)*(1+.12*voice.open),.65,1.5)
    positions=np.clip(np.arange(bins)/scale,0,bins-1)
    lo=positions.astype(int);hi=np.minimum(lo+1,bins-1);weight=positions-lo
    sp=(1-weight)*sp[:,lo]+weight*sp[:,hi]
    frequencies=np.linspace(0,SR/2,bins)
    tilt_ratio=(1+(frequencies/3500)**4)/(1+(frequencies/max(voice.tilt,800))**4)
    sp *= np.clip(tilt_ratio,.25,3)
    ap=np.clip(ap+voice.breath*.035,0,1)
    if voice.voicing<=0:
        ap[:]=1
    if voice.jitter:
        f0 *= 1+voice.jitter*np.interp(frame_time,np.linspace(0,frame_time[-1],max(3,int(frame_time[-1]*30))),rng.standard_normal(max(3,int(frame_time[-1]*30))))
    if voice.vibrato:
        f0 *= 1+voice.vibrato*np.sin(2*np.pi*voice.vib_rate*frame_time)
    audio=pw.synthesize(np.ascontiguousarray(f0),np.ascontiguousarray(sp),np.ascontiguousarray(ap),SR,frame_period=5)
    audio=np.pad(audio,(0,max(0,n-len(audio))))[:n]
    audio *= np.interp(np.arange(n)/SR,frame_time,amp)
    if not np.isfinite(audio).all():
        raise ScoreError('Sample resynthesis produced nonfinite audio.')
    spans=[]
    seen={}
    for index,seg in enumerate(segs):
        if seg.tag is None:
            continue
        a,b=int(starts[index]*SR),int(starts[index+1]*SR)
        if seg.tag in seen:
            j=seen[seg.tag];spans[j]=(seg.tag,spans[j][1],b)
        else:
            seen[seg.tag]=len(spans);spans.append((seg.tag,a,b))
    return Rendered(audio,spans)
