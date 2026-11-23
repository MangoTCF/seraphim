"""Browser-local dictionary overlays and pre-render score inspection."""
import re

from . import dialects, hebrew
from .lexicon import Entry, Lexicon, LexiconError, POS_VALUES, validate_entry
from .score import MOUTH_ALIASES, diagnostics


def entry_data(entry):
    return dict(pos=entry.pos, tokens=entry.tokens)


def browser_lexicon(overrides):
    if not isinstance(overrides, dict):
        raise LexiconError('Dictionary overrides must be an object keyed by gloss.')
    lexicon = Lexicon(save=False)
    for gloss, entry in overrides.items():
        if not isinstance(entry, dict) or set(entry) != {'pos', 'tokens'}:
            raise LexiconError(f'Invalid dictionary entry for {gloss!r}.')
        validate_entry(gloss, entry['pos'], entry['tokens'])
        lexicon.entries[gloss] = Entry(gloss, entry['pos'], entry['tokens'], 'browser')
    lexicon.by_signature()
    return lexicon


def dictionary_catalog():
    lexicon = browser_lexicon({})
    return dict(entries={g: entry_data(e) for g, e in lexicon.entries.items()},
                parts=sorted(POS_VALUES), vowels=hebrew.VOWEL_VALUES,
                consonants=hebrew.CONSONANT_VALUES)


def mouth_line(line):
    label, sep, body = line.split('#', 1)[0].partition(':')
    return MOUTH_ALIASES.get(label.strip().lower()) if sep else None, body.strip()


def score_view(text, score):
    from .lexicon import score_lexicon
    from .reading import decode_line

    lexicon = score_lexicon(score)
    signatures = lexicon.by_signature()
    words = []
    lines = text.splitlines()
    starts = [word.line - 1 for word in score.words] + [len(lines)]
    for i, word in enumerate(score.words):
        raw = dict(mouth_line(line) for line in lines[starts[i] + 1:starts[i + 1]])
        mouths = {}
        labels = []
        for name, mouth in word.mouths.items():
            mouths[name] = raw.get(name) or 'Ø'
            decoded = decode_line(mouth, lexicon, signatures)
            if decoded:
                labels.append(decoded.gloss)
        words.append(dict(tense='+'.join(word.tenses), sentenceStart=word.sentence_start,
                          tone=','.join(f'{k}:{v}' for k, v in word.tones.items()),
                          stammer=word.stammer, mouths=mouths, label=' / '.join(labels)))
    return dict(words=words, title=score.meta.get('title', 'Untitled score'),
                dialect=dialects.get(score.meta['dialect']).name,
                diagnostics=diagnostics(score))


def arrange(text, score, index, action):
    """Edit word positions while keeping inter-word comments and sentence markers."""
    if type(index) is not int or not 0 <= index < len(score.words):
        raise ValueError('Select a word first.')
    lines = text.splitlines(keepends=True)
    starts = [word.line - 1 for word in score.words]
    ends = [start + 1 for start in starts]
    for i, start in enumerate(starts):
        limit = starts[i + 1] if i + 1 < len(starts) else len(lines)
        for j in range(start + 1, limit):
            label, _ = mouth_line(lines[j])
            if label:
                ends[i] = j + 1

    # Make inherited tenses explicit on affected words before changing their order.
    def block(i):
        start = starts[i]
        header = lines[start]
        if not re.match(r'^\s*word\s+(?!tone=|stammer(?:\s|$))[^#\s]+',
                        header, re.IGNORECASE):
            header = re.sub(r'^(\s*word)\b', r'\1 ' + '+'.join(score.words[i].tenses),
                            header, count=1, flags=re.IGNORECASE)
        return ''.join([header, *lines[start + 1:ends[i]]]).rstrip('\r\n') + '\n'

    edits = {}
    next_index = index
    if action == 'insert':
        edits[index] = block(index) + 'word ' + '+'.join(score.words[index].tenses) + '\n  top: Ø\n'
        next_index += 1
    elif action == 'delete':
        if len(starts) == 1:
            raise ValueError('A score needs at least one word.')
        edits[index] = ''
        next_index = min(index, len(starts) - 2)
    elif action in ('up', 'down'):
        next_index += -1 if action == 'up' else 1
        if not 0 <= next_index < len(starts):
            raise ValueError('The word is already at the edge of the score.')
        edits[index], edits[next_index] = block(next_index), block(index)
    else:
        raise ValueError('Unknown score action.')
    for i in list(edits):
        if i + 1 < len(starts) and i + 1 not in edits:
            edits[i + 1] = block(i + 1)
    for i in sorted(edits, reverse=True):
        lines[starts[i]:ends[i]] = [edits[i]]
    return ''.join(lines), next_index
