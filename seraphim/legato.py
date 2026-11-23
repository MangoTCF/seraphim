"""Duration-preserving legato controls shared by both voice backends."""
import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .phones import PHONES
from .score import ScoreError

CHANNELS=('top','1','2','end','praise-1','praise-2','praise-3')
KEYS=(*CHANNELS,'choir','all')


def validate(overrides):
    if overrides is None:
        return {}
    if not isinstance(overrides,dict) or set(overrides)-set(KEYS):
        raise ScoreError('Mouth blend keys must be top, 1, 2, end, praise-1/2/3, choir or all.')
    result={}
    for key,value in overrides.items():
        if value in (None,''):
            continue
        try:
            number=float(value)
        except (TypeError,ValueError):
            raise ScoreError(f'Invalid syllable blend for {key}: {value!r}') from None
        if not math.isfinite(number) or not 0<=number<=1:
            raise ScoreError(f'Syllable blend for {key} must be between 0 and 1.')
        result[key]=number
    return result


def parse_overrides(spec):
    values={}
    for item in spec.split(','):
        key,sep,value=item.partition('=')
        if not sep:
            raise ValueError('Use top=0.8,1=0.5,praise-1=0; blank mouths inherit the global setting.')
        values[key.strip()]=value.strip()
    try:
        return validate(values)
    except ScoreError as exc:
        raise ValueError(str(exc)) from None


def amount(options,channel):
    values=options.mouth_blend or {}
    if channel in values:
        return values[channel]
    if channel.startswith('praise-') and 'choir' in values:
        return values['choir']
    return values.get('all',options.syllable_blend)


def smooth_runs(values,mask,sigma):
    """Filter independent allowed stretches; never borrow across a barrier."""
    if sigma<=0 or not np.any(mask):
        return values.copy()
    out=values.copy()
    edges=np.flatnonzero(np.diff(np.r_[False,mask,False].astype(int)))
    for start,end in zip(edges[::2],edges[1::2]):
        if end-start>1:
            out[start:end]=gaussian_filter1d(values[start:end],sigma,axis=0,mode='nearest')
    return out


def masks(segs,starts,times):
    indices=np.clip(np.searchsorted(starts,times,side='right')-1,0,len(segs)-1)
    allowed=np.array([PHONES.get(segs[i].phone,{}).get('kind') not in (None,'stop','glottal') for i in indices])
    # The trailing synthesis padding is outside the utterance, not another vowel.
    allowed &= times<starts[-1]
    return allowed


def blend_features(sp,ap,f0,amp,times,segs,starts,strength):
    """Repair short joins without averaging whole phonemes or normalizing energy.

    Stops, glottal closures and explicit pauses are barriers. Cues and expressive
    timing remain at their planned locations. Zero is an exact bypass.
    """
    if strength<=0:
        return sp,ap,f0,amp
    allowed=masks(segs,starts,times)
    hop=float(times[1]-times[0]) if len(times)>1 else .005
    logs=np.log(np.maximum(sp,1e-12))
    # Only repair discontinuities immediately at joins. Averaging entire vowel
    # trajectories and automatic energy leveling erased articulation/dynamics.
    out_sp=sp.copy();out_logs=logs.copy();out_ap=ap.copy();out_amp=amp.copy();out_f0=f0.copy()
    width=.006+.012*strength
    for index in range(1,len(segs)):
        left,right=PHONES.get(segs[index-1].phone),PHONES.get(segs[index].phone)
        if not left or not right or left['kind'] in ('stop','glottal') or right['kind'] in ('stop','glottal'):
            continue
        boundary=starts[index]
        rows=np.flatnonzero(allowed&(np.abs(times-boundary)<width))
        if len(rows)<3:
            continue
        a,b=rows[0],rows[-1]
        u=((times[rows]-times[a])/max(times[b]-times[a],hop))
        u=u*u*(3-2*u)
        for original,result in [(logs,out_logs),(ap,out_ap),(amp,out_amp)]:
            mix=u[:,None] if original.ndim==2 else u
            bridge=(1-mix)*original[a]+mix*original[b]
            result[rows]=original[rows]+strength*(bridge-original[rows])
        out_sp[rows]=np.exp(out_logs[rows])
        if np.all(f0[rows]>0):
            bridge=np.exp((1-u)*np.log(f0[a])+u*np.log(f0[b]))
            out_f0[rows]=f0[rows]+strength*(bridge-f0[rows])
    return out_sp,np.clip(out_ap,0,1),out_f0,out_amp
