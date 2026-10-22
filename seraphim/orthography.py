"""Seraphim writing.

Every phoneme is written right to left, but a syllable runs left to right.
For each word the four mouths' morphemes are listed by scope (top, 1, 2, end);
the one with the most letters becomes the core glyphs, and every other letter
turns into a diacritic: above the core if its morpheme outscopes the core,
below if not. The result looks like Hebrew zalgo. Brightness is shown by
colour: bright orange, extra bright yellow, ionized cyan.

The video's diacritic table is approximated with Unicode combining marks of
similar shape (circumflex, caron, ring, tilde, diaeresis, breve, ...).
"""

import html

from . import hebrew
from .score import MOUTHS, BRIGHT, EXTRA, IONIZED

ORDER = "אבגדהוזחטיכלמנסעפצקרשתךםןףץ"
ABOVE = [0x0302, 0x030C, 0x030A, 0x0303, 0x0308, 0x0306, 0x0311, 0x0352, 0x034B, 0x0350,
         0x035B, 0x0346, 0x030F, 0x030B, 0x0314, 0x033F, 0x034C, 0x033E, 0x0305, 0x0351,
         0x0313, 0x0304, 0x0312, 0x0315, 0x0310, 0x0357, 0x033D]
BELOW = [0x032D, 0x032C, 0x0325, 0x0330, 0x0324, 0x032E, 0x032F, 0x031F, 0x0359, 0x0354,
         0x0326, 0x035C, 0x0329, 0x0332, 0x0333, 0x033A, 0x033B, 0x0323, 0x0355, 0x0318,
         0x0319, 0x0347, 0x0348, 0x031E, 0x0320, 0x0349, 0x031D]
MARK_ABOVE = {c: chr(m) for c, m in zip(ORDER, ABOVE)}
MARK_BELOW = {c: chr(m) for c, m in zip(ORDER, BELOW)}

COLORS = {BRIGHT: "#ff9500", EXTRA: "#ffd60a", IONIZED: "#22d3ee"}
ANSI = {BRIGHT: "\033[38;5;208m", EXTRA: "\033[38;5;220m", IONIZED: "\033[38;5;51m"}
LRI, RLI, PDI = "⁦", "⁧", "⁩"


def _morphemes(word):
    """(scope, tokens) per non-silent mouth, highest scope first."""
    out = []
    for scope, m in enumerate(MOUTHS):
        ml = word.mouths[m]
        if not ml.silent:
            out.append((scope, [t for t in ml.tokens if t.kind == "phoneme"]))
    return out


def compose(word):
    """Returns a list of (text, brightness) glyph runs for one word."""
    ms = _morphemes(word)
    if not ms:
        return []
    core_i = max(range(len(ms)), key=lambda i: sum(len(hebrew.letters(t.text)) for t in ms[i][1]))
    core_scope, core = ms[core_i]
    above, below = [], []
    for scope, toks in ms:
        if scope == core_scope:
            continue
        letters = "".join(hebrew.letters(t.text) for t in toks)
        (above if scope < core_scope else below).append(letters)
    above = "".join(above)
    below = "".join(below)
    slots = [hebrew.letters(t.text) for t in core]
    n = sum(len(s) for s in slots)
    marks = [[] for _ in range(n)]
    for k, ch in enumerate(above):
        marks[k % n].append(MARK_ABOVE[ch])
    for k, ch in enumerate(below):
        marks[k % n].append(MARK_BELOW[ch])
    runs, k = [], 0
    for t, s in zip(core, slots):
        text = ""
        for ch in s:
            text += ch + "".join(marks[k])
            k += 1
        runs.append((text, t.brightness if t.cls == "V" or t.brightness else 0))
    return runs


def terminal(score):
    lines = []
    for w in score.words:
        runs = compose(w)
        if w.sentence_start and lines:
            lines.append("")
        body = " ".join(f"{ANSI.get(b, '')}{RLI}{t}{PDI}\033[0m" for t, b in runs)
        lines.append(LRI + body + PDI)
    return "\n".join(lines)


def html_page(score, title="Seraphim"):
    words = []
    for w in score.words:
        runs = compose(w)
        spans = "".join(
            f'<bdi dir="rtl" class="ph"{f" style=color:{COLORS[b]}" if b else ""}>{html.escape(t)}</bdi>'
            for t, b in runs)
        sep = '<span class="br"></span>' if w.sentence_start and words else ""
        words.append(f'{sep}<span class="w" dir="ltr">{spans}</span>')
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>
:root{{--bg:#fbfaf7;--fg:#1d1b18;--mute:#7a746b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#14130f;--fg:#efe9dd;--mute:#9a9385}}}}
body{{background:var(--bg);color:var(--fg);font-family:"SBL Hebrew","Ezra SIL","Noto Serif Hebrew",serif;
margin:0;padding:48px 16px;line-height:3.2}}
main{{max-width:900px;margin:auto}}
h1{{font-size:14px;letter-spacing:.08em;text-transform:uppercase;color:var(--mute);font-family:system-ui,sans-serif}}
.w{{font-size:40px;margin:0 22px 0 0;padding:0 22px 0 0;white-space:nowrap;display:inline-block;
border-right:1px solid color-mix(in srgb,var(--mute) 35%,transparent)}}
.ph{{margin:0 3px}} .br{{display:block;height:24px}}
p.key{{font:13px system-ui,sans-serif;color:var(--mute)}}
p.key b{{font-weight:600}}
</style></head><body><main><h1>{html.escape(title)}</h1>
{"".join(words)}
<p class="key">Core morpheme in full, the other mouths as diacritics above or below by scope.
Vowel brightness: <b style="color:#ff9500">bright</b>, <b style="color:#ffd60a">extra bright</b>,
<b style="color:#22d3ee">ionized</b>. The praise voices are not written.</p></main></body></html>"""
