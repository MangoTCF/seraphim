"""Shared descriptions and validation for the workbench's synthesis controls."""
import math
import os


def field(key, label, help, *, low=0, high=None, step=.05, default=None, kind='number', target='option'):
    return dict(key=key, label=label, help=help, min=low, max=high, step=step,
                default=default, kind=kind, target=target)


def sections():
    from .cli import KNOB_HELP
    from .score import TONES
    from .samplebank import catalog, CHANNELS
    banks = catalog()
    bank_choices = [dict(value='', label='Formant synth')] + [dict(value=b['id'], label=b['name']) for b in banks if b['ready']]
    damage = ('growl', 'fry', 'roar', 'whistle', 'throat', 'disfigure', 'pitch')
    style = ('breath', 'moan', 'whisper', 'grab', 'hunger', 'swap')
    def knobs(keys):
        return [field(k, k.capitalize(), KNOB_HELP[k], low=None if k == 'pitch' else 0,
                      high=None if k == 'pitch' else 1, step=1 if k == 'pitch' else .05, target='knobs') for k in keys]
    return [
        dict(title='Recorded voicebanks', help='Choose a local recorded singer independently for every mouth. Approximate phonemes are reported after render; unsupported sounds use formant fallback.', fields=[
            dict(key=k, label={'top':'Top','1':'Main 1','2':'Main 2','end':'End','praise-1':'Prayer I','praise-2':'Prayer II','praise-3':'Prayer III'}[k], help='WORLD resynthesis follows the score timing and pitch.', kind='select', target='banks', default='', choices=bank_choices) for k in CHANNELS] + [field('sample_approximation', 'Allow nearest bank phonemes', 'When off, missing exact phonemes use the formant engine instead. Coverage is shown for each voice.', kind='checkbox', default=True)]),
        dict(title='Speech transitions', help='Transition smoothness shapes phoneme ramps. Syllable blend renders compatible words continuously, without word-by-word fades, and repairs short joins. It does not smear whole vowels. Explicit pauses and consonant closures remain.', fields=[
            field('transitions', 'Transition smoothness', '0 linear ramps, 1 smooth formants, voicing and pitch.', high=1, default=1),
            field('syllable_blend', 'Syllable blend · global', '0 independent words; positive values enable connected words. Higher values soften short joins more. Applies on render.', high=1, default=.5)] + [
            field(k, {'top':'Top','1':'Main 1','2':'Main 2','end':'End','praise-1':'Prayer I','praise-2':'Prayer II','praise-3':'Prayer III'}[k] + ' · syllable blend',
                  'Blank inherits the global knob. 0 explicitly disables blending for this mouth.', high=1, target='blends') for k in CHANNELS]),
        dict(title='Individual voices', help='Blank inherits the score or dialect. −1 masculine, 0 androgynous, +1 feminine. Choir sets all three prayer voices.',
             fields=[field(k, name, 'Pitch, vocal tract and voice quality.', low=-1, high=1, target='voices')
                     for k, name in [('top', 'Top'), ('1', 'Main 1'), ('2', 'Main 2'), ('end', 'End'), ('choir', 'Prayer choir')]]),
        dict(title='Breath, intimacy & movement', help='Blank keeps the score or dialect setting. Swap controls the nephilim halves.', fields=knobs(style)),
        dict(title='Damage & distortion', help='Damage controls apply where the selected dialect uses damaged voices. Pitch is in semitones.', fields=knobs(damage)),
        dict(title='Emotion & delivery', help='These intensities add to score and word tones. Neutral clears inherited tones first; other explicit intensities still apply.',
             fields=[field(k, k.capitalize(), 'Makes speech breathy and shaky, with little pitch catches and weak vowel endings.'
                           if k == 'whimper' else 'Global render intensity.', high=1, target='tones')
                     for k in TONES if k != 'neutral'] +
                    [field('neutral', 'Clear inherited tones', 'Remove default, score and word tones before applying these intensities.', kind='checkbox', default=False, target='tones')]),
        dict(title='Prayer, brightness & closed mouths', help='Prayer language follows tense. Glitter affects extra-bright vowels; hum sets closed-mouth vocalization.', fields=[
            field('prayer_time', 'Audible tense signatures', 'Falling far past; steady gnomic; rising near past; arching non-past. Disable for legacy chant.', kind='checkbox', default=True),
            field('prayer_tail', 'Prayer fade · seconds', 'Carry the closing prayer syllables through the fade. Set to 0 to turn off.', high=12, step=.1, default=2.4),
            field('prayer_rise', 'Prayer rise · semitones', 'Pitch rise over the fade. Set to 0 for a level pitch.', high=24, step=1, default=7),
            field('choir_level', 'Choir level', 'Prayer voice gain before spatial mixing.', default=.42),
            field('choir_pitch', 'Choir pitch · semitones', 'Transpose the prayer choir relative to its chant register.', low=None, step=1, target='knobs'),
            field('gender', 'Dialect voice default', 'Dialect gender default; explicit voice controls take precedence.', low=-1, high=1, target='knobs'),
            field('hum', 'Closed-mouth hum', '0 silences closed mouths.', default=.3),
            field('glitter', 'Brightness glitter', 'Noise glitter on extra-bright vowels; 0 turns it off.', default=1),
            field('reverse_4d', 'Reverse displaced speech', 'Play 4D-moved morphemes backwards, as well as their anticipatory echoes.', kind='checkbox', default=False)]),
        dict(title='Room & spatial sound', help='Reverb amount is above. Blank room overrides inherit score metadata.', fields=[
            field('space', 'Binaural positioning', 'Off uses plain stereo instead of binaural placement.', kind='checkbox', default=True),
            field('reverb_time', 'Decay · RT60 seconds', 'Override the room decay time.'),
            field('reverb_tone', 'Darkness', '0 bright to 1 dark.', high=1),
            field('predelay', 'Predelay · milliseconds', 'Delay before room reflections.', step=1),
            field('reverb_mix', 'Mouth reverb send', 'How much speech is sent into the room; choir send remains independent.', default=.28)]),
        dict(title='Rendering & export', help='Solo playback always uses compatible PCM16. Download and bundle formats can preserve floating-point headroom.', fields=[
            field('master', 'Master the mix', 'DC/rumble removal, peak normalization and saturation. Turn off for raw mixing.', kind='checkbox', default=True),
            field('jobs', 'Parallel workers', '0 uses all cores; 1 renders serially. Blank uses up to four cores.', step=1),
            dict(key='format', label='WAV format', help='Float32 preserves raw headroom; PCM16 is widely compatible.', kind='select', target='export', default='pcm16', choices=['pcm16', 'float32']),
            field('normalize_stems', 'Normalize exported stems', 'Normalize each downloadable stem independently. Solo audition keeps original gain.', kind='checkbox', default=False, target='export'),
            field('preview', 'Include offline HTML preview', 'Add a self-contained player with embedded audio to the render bundle.', kind='checkbox', default=False, target='export')])]


def numeric(value, name, low=None, high=None, integer=False):
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{name} must be a number.') from None
    if not math.isfinite(n) or (low is not None and n < low) or (high is not None and n > high):
        raise ValueError(f'{name} must be finite' + (f' and at least {low}' if low is not None else '') +
                         (f' and at most {high}' if high is not None else '') + '.')
    if integer and not n.is_integer():
        raise ValueError(f'{name} must be a whole number.')
    return int(n) if integer else n


def boolean(request, key, default):
    value = request.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f'{key} must be true or false.')
    return value


def score_controls(score):
    """Show the score's metadata and inherited dialect tuning."""
    from .dialects import KNOBS, get as get_dialect
    from .render import resolve_gender
    from .score import parse_tones

    meta = score.meta
    values = {key: meta[key] for key in ('title', 'room', 'reverb', 'tempo', 'tense', 'dialect')
              if key in meta}
    dialect = get_dialect(meta.get('dialect'), {k: meta[k] for k in KNOBS if k in meta})
    values['dialect'] = dialect.name
    voices = resolve_gender(score, dialect)
    values['voice'] = voices['all']
    tones = parse_tones(meta.get('tone', dialect.tone or ''))
    for section in sections():
        for item in section['fields']:
            key, target = item['key'], item['target']
            if target == 'voices':
                value = voices.get(key, voices['all'])
            elif target == 'tones':
                value = key in tones if key == 'neutral' else tones.get(key, 0)
            elif target == 'knobs':
                value = getattr(dialect, key)
                if value is None:
                    value = 0
            elif target == 'option' and key in meta:
                value = float(meta[key]) * (1000 if key == 'predelay' else 1)
            else:
                continue
            values[f'control-{target}-{key}'] = value
    return values


def options(request, score):
    from .render import Options, parse_voice, plan
    from .score import parse_tones
    groups = {}
    for key in ('knobs', 'tones', 'voices', 'export', 'banks', 'blends'):
        groups[key] = request.get(key, {})
        if not isinstance(groups[key], dict):
            raise ValueError(f'{key} must be an object.')
    opts = Options(dialect=request.get('dialect') or None, room=request.get('room') or None,
                   seed=numeric(request.get('seed', 0), 'seed', integer=True),
                   choir=boolean(request, 'choir', True), jobs=min(4, os.cpu_count() or 1), keep_stems=True)
    schema = sections()
    for section in schema:
        for item in section['fields']:
            key, target = item['key'], item['target']
            source = request if target == 'option' else groups[target]
            if key not in source or source[key] in (None, ''):
                continue
            if item['kind'] == 'select':
                value = source[key]
                if value not in [c['value'] if isinstance(c, dict) else c for c in item['choices']]:
                    raise ValueError(f'Invalid {key}: {value}')
            elif item['kind'] == 'checkbox':
                value = boolean(source, key, item['default'])
            else:
                value = numeric(source[key], key, item['min'], item['max'], integer=key == 'jobs')
            if target == 'option':
                setattr(opts, key, value / 1000 if key == 'predelay' else value)
            else:
                groups[target][key] = value
    # Reject typos rather than quietly losing an adjustment.
    for group, values in groups.items():
        known = {f['key'] for s in schema for f in s['fields'] if f['target'] == group}
        if group == 'blends':
            from .legato import KEYS as BLEND_KEYS
            known.update(BLEND_KEYS)
        if group == 'banks':
            from .samplebank import KEYS
            known.update(KEYS)
        if set(values) - known:
            raise ValueError(f'Unknown {group} controls: {", ".join(sorted(set(values) - known))}')
    from .samplebank import validate_selection
    opts.sample_banks = validate_selection(groups['banks'])
    from .legato import validate as validate_blends
    opts.mouth_blend = validate_blends(groups['blends'])
    opts.knobs = {k: v for k, v in groups['knobs'].items() if v not in (None, '')}
    tones = groups['tones']
    opts.tones = parse_tones(','.join(f'{k}:{v}' for k, v in tones.items() if k != 'neutral' and v not in (None, '')))
    if tones.get('neutral'):
        opts.tones['neutral'] = 1
    if request.get('tempo') not in (None, ''):
        value = numeric(request['tempo'], 'tempo', 0)
        if value == 0:
            raise ValueError('tempo must be greater than zero.')
        score.meta['tempo'] = str(value)
    if request.get('reverb') not in (None, ''):
        opts.reverb = numeric(request['reverb'], 'reverb', 0)
    if request.get('voice') not in (None, ''):
        opts.voice = parse_voice(str(numeric(request['voice'], 'voice', -1, 1)))
    overrides = {k: v for k, v in groups['voices'].items() if v not in (None, '')}
    if overrides:
        # Partial per-mouth adjustments must retain the other dialect defaults.
        opts.voice = {**plan(score, opts).gender, **overrides}
    return opts
