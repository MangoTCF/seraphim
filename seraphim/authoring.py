"""Lossless word edits against score source, with validation before acceptance."""
import re
from .score import MOUTHS, ScoreError, parse, parse_tones



def edit_word(text, index, edit, *, seed=0, dialect=None, heresy=False):
    """Replace one word block; retain metadata, vocabulary, other words and breaks."""
    original = parse(text, seed=seed, dialect=dialect, heresy=heresy)
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(original.words):
        raise ValueError('Select a valid word to edit.')
    if not isinstance(edit, dict):
        raise ValueError('Word edit must be an object.')
    word = original.words[index]
    tenses = edit.get('tense') or '+'.join(word.tenses)
    if not isinstance(tenses, str) or any(c.isspace() for c in tenses):
        raise ValueError('Tense must be a single label or a + stack.')
    tones = edit.get('tone', ','.join(f'{k}:{v}' for k, v in word.tones.items()))
    if not isinstance(tones, str):
        raise ValueError('Tone must be text.')
    parse_tones(tones)
    stammer = edit.get('stammer', word.stammer)
    if not isinstance(stammer, bool):
        raise ValueError('Stammer must be true or false.')
    header = f'word {tenses}' + (f' tone={tones}' if tones else '') + (' stammer' if stammer else '')
    lines = [header]
    mouths = edit.get('mouths', {})
    if not isinstance(mouths, dict) or set(mouths) - set(MOUTHS):
        raise ValueError('Expected top, 1, 2 and end mouth text.')
    for key in MOUTHS:
        ml = word.mouths[key]
        default = ('~ ' if ml.moved else '') + (' '.join(t.text + {0: '', 1: '☀', 2: '🔆', 3: '☢'}[t.brightness] for t in ml.tokens) or 'Ø')
        body = mouths.get(key, default)
        if not isinstance(body, str) or '\n' in body or '\r' in body or '#' in body:
            raise ValueError('Each mouth must contain a single line of score notation, without comments.')
        lines.append(f'  {key}: {body or "Ø"}')
    # Word.line is one-based and points at the real header, never a preceding blank.
    source = text.splitlines(keepends=True)
    start = word.line - 1
    end = original.words[index + 1].line - 1 if index + 1 < len(original.words) else len(source)
    # Keep comments/blank lines/separators after the last mouth line, including ---.
    body_end = start + 1
    for i in range(start + 1, end):
        if re.match(r'^\s*(?:top|t|1|one|2|two|end|e)\s*:', source[i], re.I):
            body_end = i + 1
    updated = ''.join(source[:start]) + '\n'.join(lines) + '\n' + ''.join(source[body_end:])
    validated = parse(updated, seed=seed, dialect=dialect, heresy=heresy)
    if len(validated.words) != len(original.words):
        raise ScoreError('Editing changed the number of words unexpectedly.')
    brightness = edit.get('brightness', {})
    if not isinstance(brightness, dict) or set(brightness) - set(MOUTHS):
        raise ValueError('Brightness overrides must name existing mouths.')
    if brightness:
        marked = {}
        for key, level in brightness.items():
            if type(level) is not int or level not in (1, 2, 3):
                raise ValueError('Vowel brightness must be 1 (bright), 2 (extra), or 3 (ionized).')
            ml = validated.words[index].mouths[key]
            marked[key] = ('~ ' if ml.moved else '') + (' '.join(
                t.text + {0: '', 1: '☀', 2: '🔆', 3: '☢'}[level if t.cls == 'V' else t.brightness]
                for t in ml.tokens) or 'Ø')
        return edit_word(text, index, {**edit, 'mouths': {**mouths, **marked}, 'brightness': {}},
                         seed=seed, dialect=dialect, heresy=heresy)
    # Freeze the following word's inherited tense if this edit would change it.
    if index + 1 < len(original.words) and validated.words[index + 1].tenses != original.words[index + 1].tenses:
        following = validated.words[index + 1]
        lines = updated.splitlines(keepends=True)
        line = lines[following.line - 1].rstrip('\r\n')
        options = line.strip().split()[1:]
        if options and not options[0].startswith('tone=') and options[0] != 'stammer':
            options.pop(0)
        lines[following.line - 1] = 'word ' + '+'.join(original.words[index + 1].tenses) + (' ' + ' '.join(options) if options else '') + '\n'
        updated = ''.join(lines)
        parse(updated, seed=seed, dialect=dialect, heresy=heresy)
    return updated
