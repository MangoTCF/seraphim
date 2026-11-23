"""Offline audio/score preview with sample-aligned solo auditioning."""

import base64
import html
import io
import json

import numpy as np
from scipy.io import wavfile

from .lexicon import score_lexicon
from .orthography import compose
from .reading import decode_line
from .score import MOUTHS
from .synth import SR


def _wav_uri(audio):
    buffer = io.BytesIO()
    # Float WAV keeps quiet stems quiet and preserves raw render headroom.
    wavfile.write(buffer, SR, audio.astype(np.float32))
    return "data:audio/wav;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def html_preview(score, plan, audio, stems):
    lx = score_lexicon(score)
    index = lx.by_signature()
    rows = []
    for i, w in enumerate(plan.words):
        glyphs = " ".join(html.escape(t) for t, _ in compose(w.word))
        mouths = []
        for m in MOUTHS:
            line = w.word.mouths[m]
            decoded = decode_line(line, lx, index)
            gloss = decoded.gloss if decoded else "hum / silent"
            mouths.append(f'<td><span class="label">{m}</span> {html.escape(gloss)}'
                          f'<small>{html.escape(" ".join(t.text for t in line.tokens))}</small></td>')
        rows.append(f'<tr data-word="{i}" tabindex="0" aria-label="Seek to word {i + 1}">'
                    f'<th>{i + 1}<small>{w.start:.2f}s</small></th><td class="glyph" dir="rtl">{glyphs}</td>'
                    + "".join(mouths) + '</tr>')
    tracks = {"mix": _wav_uri(audio)}
    tracks.update({k: _wav_uri(v) for k, v in stems.items()})
    payload = json.dumps(dict(tracks=tracks, words=[dict(start=w.start, end=w.start + w.duration)
                                                for w in plan.words], duration=len(audio) / SR))
    payload = payload.replace("<", "\\u003c").replace("&", "\\u0026")
    title = html.escape(score.meta.get("title", "Seraphim preview"))
    choices = "".join(f'<option value="{html.escape(k)}">{html.escape(k)}</option>' for k in tracks)
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>
body{{margin:0;background:#15151c;color:#edeaf4;font:16px system-ui,sans-serif}}
main{{max-width:1200px;margin:auto;padding:28px 20px}}h1{{font-size:22px;line-height:1.5}}
.controls{{position:sticky;top:0;background:#15151cf5;padding:16px 0;display:flex;gap:12px;flex-wrap:wrap;align-items:center}}
button,select{{background:#353044;color:inherit;border:1px solid #8f819f;border-radius:6px;padding:9px;font:inherit}}
input{{accent-color:#bc9ae8}}#seek{{flex:1;min-width:160px}}small{{display:block;color:#bdb5ca;font-size:12px;margin-top:5px}}
.table-wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%}}td,th{{padding:14px 9px;border-bottom:1px solid #383140;text-align:left}}
tr{{cursor:pointer}}tr.active{{background:#443155}}tr:focus{{outline:2px solid #bc9ae8}}.glyph{{font:25px serif;min-width:90px}}
.label{{color:#bc9ae8;font-size:12px}}p{{color:#bdb5ca;line-height:1.6}}#status{{min-height:1.5em}}
</style></head><body><main><h1>{title}</h1>
<p>Follow the four mouths as they speak. Click a word to seek. Solo tracks are dry and preserve their original gain.</p>
<div class="controls"><button id="play" disabled>Loading audio…</button><button id="stop">Stop</button>
<label>Listen <select id="track">{choices}</select></label>
<input id="seek" aria-label="Playback position" type="range" min="0" max="{len(audio) / SR:.4f}" step="0.01" value="0">
<output id="time">0.0 s</output><label>Volume <input id="volume" aria-label="Volume" type="range" min="0" max="1" step="0.01" value="0.7"></label></div>
<p id="status" role="status">Audio stays in this page; no server is needed.</p>
<div class="table-wrap"><table><thead><tr><th>Word</th><th>Writing</th><th>Top</th><th>1</th><th>2</th><th>End</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div></main>
<script id="data" type="application/json">{payload}</script>
<script>
const data = JSON.parse(document.getElementById('data').textContent);
const play = document.getElementById('play'), seek = document.getElementById('seek');
const track = document.getElementById('track'), volume = document.getElementById('volume');
const status = document.getElementById('status'), clock = document.getElementById('time');
const rows = [...document.querySelectorAll('[data-word]')];
let ctx, gain, source = null, origin = 0, offset = 0, playing = false, active = -1;
const buffers = {{}};
function position() {{ return playing ? Math.min(ctx.currentTime - origin, data.duration) : offset; }}
function pause() {{
  offset = position(); playing = false;
  if (source) {{ source.onended = null; source.stop(); source = null; }}
  play.textContent = 'Play';
}}
async function start() {{
  try {{
    await ctx.resume();
    if (offset >= data.duration) offset = 0;
    source = ctx.createBufferSource(); source.buffer = buffers[track.value];
    source.connect(gain); origin = ctx.currentTime - offset; playing = true;
    source.onended = () => {{ offset = 0; playing = false; source = null; play.textContent = 'Play'; }};
    source.start(0, offset); play.textContent = 'Pause';
  }} catch (error) {{ playing = false; status.textContent = 'Could not play audio: ' + error.message; }}
}}
function jump(value) {{ const resume = playing; pause(); offset = Number(value); if (resume) start(); }}
play.onclick = () => playing ? pause() : start();
document.getElementById('stop').onclick = () => {{ pause(); offset = 0; }};
seek.oninput = () => jump(seek.value);
track.onchange = () => {{ if (playing) {{ pause(); start(); }} }};
volume.oninput = () => {{ if (gain) gain.gain.value = Number(volume.value); }};
rows.forEach((row, i) => {{
  row.onclick = () => jump(data.words[i].start);
  row.onkeydown = e => {{ if (e.key === 'Enter' || e.key === ' ') {{ e.preventDefault(); row.click(); }} }};
}});
function frame() {{
  const t = position(); seek.value = t; clock.textContent = t.toFixed(1) + ' s';
  const next = data.words.findIndex(w => t >= w.start && t < w.end);
  if (next !== active) {{
    if (active >= 0) rows[active].classList.remove('active');
    if (next >= 0) rows[next].classList.add('active'); active = next;
  }}
  requestAnimationFrame(frame);
}}
(async () => {{
  try {{
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    gain = ctx.createGain(); gain.gain.value = Number(volume.value); gain.connect(ctx.destination);
    for (const [name, uri] of Object.entries(data.tracks)) {{
      const bytes = await (await fetch(uri)).arrayBuffer();
      buffers[name] = await ctx.decodeAudioData(bytes);
    }}
    play.disabled = false; play.textContent = 'Play'; frame();
  }} catch (error) {{ status.textContent = 'Could not load audio: ' + error.message; }}
}})();
</script></body></html>'''
