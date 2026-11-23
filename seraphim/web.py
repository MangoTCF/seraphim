"""Local browser workbench. Run with ``python -m seraphim.web``."""
import argparse
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ASSETS = Path(__file__).with_name('web_assets')
EXAMPLES = Path(__file__).with_name('examples')
if not EXAMPLES.is_dir():
    EXAMPLES = EXAMPLES.parent.parent / 'examples'


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def prepare(request, *, coined=None):
    from .score import parse
    mode, text = request.get('mode', 'score'), request.get('text', '')
    if not isinstance(text, str) or not text.strip():
        raise ValueError('Enter some text or open a score first.')
    dialect = request.get('dialect') or None
    from .web_controls import numeric, boolean
    seed = numeric(request.get('seed', 0), 'seed', integer=True)
    if mode == 'score':
        score_text = text
    elif mode in ('english', 'gloss'):
        from .web_authoring import browser_lexicon, entry_data
        from .grammar import build, clause_from_gloss, to_sera
        lx = browser_lexicon(request.get('dictionary', {}))
        known = set(lx.entries)
        if mode == 'english':
            from .english import translate
            try:
                sentences = translate(text, lx, strict=boolean(request, 'strict', False))
            except SystemExit as exc:
                raise ValueError(str(exc)) from None
        else:
            sentences = [clause_from_gloss(g.strip(), request.get('tense', 'nonpast'), lx)
                         for g in text.split('//') if g.strip()]
        front = request.get('front', '')
        if not isinstance(front, str):
            raise ValueError('Fronted morphemes must be text.')
        shuffle = request.get('shuffle')
        if shuffle not in (None, ''):
            shuffle = numeric(shuffle, 'shuffle', integer=True)
        else:
            shuffle = None
        build(sentences, lx, move=boolean(request, 'move', True), front=front.split(), shuffle=shuffle)
        score_text = to_sera(sentences, lx, title=request.get('title') or text[:100], seed=seed, dialect=dialect)
        if coined is not None:
            coined.update((g, entry_data(lx.entries[g])) for g in sorted(lx.entries.keys() - known))
    else:
        raise ValueError('Unknown input mode.')
    return score_text, parse(score_text, seed=seed, dialect=dialect, heresy=boolean(request, 'heresy', False))


def render_job(directory):
    """The only process that imports and runs the synthesis engine."""
    import numpy as np
    from scipy.io import wavfile
    from .render import plan, synthesize
    from .web_controls import options
    from .score import diagnostics, MOUTHS, temporal_meaning
    from .reading import read_score, english, decode_line
    from .lexicon import score_lexicon
    from .orthography import compose
    from .synth import SR
    directory = Path(directory)
    status = directory / 'status.json'
    def progress(message):
        atomic_json(status, dict(state='running', message=message))
    try:
        request = json.loads((directory / 'request.json').read_text())
        progress('Reading and planning the score…')
        text, score = prepare(request)
        opts = options(request, score)
        full_score = score
        selection = request.get('selection')
        selected_indices = list(range(len(score.words)))
        if selection is not None:
            from .web_controls import numeric
            selected = numeric(selection, 'selection', 0, len(score.words) - 1, integer=True)
            from dataclasses import replace
            score = replace(score, words=[score.words[selected]])
            selected_indices = [selected]
        resolved = plan(score, opts)
        if not resolved.words:
            raise ValueError('The score has no words.')
        if resolved.total > 600:
            raise ValueError('Please keep each render under ten minutes.')
        lx = score_lexicon(score)
        index = lx.by_signature()
        words = []
        for i, w in enumerate(resolved.words):
            mouths = {}
            for m in MOUTHS:
                ml = w.word.mouths[m]
                decoded = decode_line(ml, lx, index)
                mouths[m] = dict(notation=('~ ' if ml.moved else '') + (' '.join(t.text + {0: '', 1: '☀', 2: '🔆', 3: '☢'}[t.brightness] for t in ml.tokens) or 'Ø'),
                                 text=' '.join(t.text for t in ml.tokens),
                                 gloss=decoded.gloss if decoded else 'Hum / silent', moved=ml.moved)
            words.append(dict(index=i, source_index=selected_indices[i], tenses=w.word.tenses,
                              temporal=temporal_meaning(w.word.tenses), tones=w.word.tones, stammer=w.word.stammer,
                              scope=[dict(mouth=m, gloss=mouths[m]["gloss"], moved=mouths[m]["moved"]) for m in MOUTHS], start=w.start, end=w.start + w.duration,
                              glyphs=' '.join(t for t, _ in compose(w.word)), mouths=mouths,
                              languages=w.word.langs))
        from . import choir
        from .render import LEAD_IN, WORD_GAP
        prayer_end = resolved.words[-1].start + resolved.words[-1].duration + WORD_GAP / resolved.tempo + .8
        prayer_timeline = {f'praise-{i+1}': choir.time_spans(resolved.words, i, LEAD_IN - .9, prayer_end)
                           for i in range(3)} if opts.choir and opts.prayer_time else {}
        readings = read_score(full_score, lx)
        audio, stems = synthesize(score, progress=progress, render_plan=resolved)
        progress('Preparing playback and voice activity…')
        if not np.isfinite(audio).all() or any(not np.isfinite(s).all() for s in stems.values()):
            raise ValueError('Render contains nonfinite samples; reduce the synthesis settings.')
        tracks = {'mix': audio, **stems}
        exports = request.get('export', {})
        downloads = {}
        for name, samples in tracks.items():
            exported = samples
            if name != 'mix' and exports.get('normalize_stems'):
                peak = np.max(np.abs(samples))
                if peak > 0:
                    exported = samples / peak * .9
            encoded = exported.astype(np.float32) if exports.get('format') == 'float32' else (np.clip(exported, -1, 1) * 32767).astype(np.int16)
            filename = f'{name}-export.wav'
            wavfile.write(directory / filename, SR, encoded)
            downloads[name] = filename
        activity, names = {}, {}
        for name, samples in tracks.items():
            # PCM16 for universal browser playback; preserve dry stem gain.
            pcm = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
            wavfile.write(directory / f'{name}.wav', SR, pcm)
            names[name] = f'{name}.wav'
            mono = np.mean(samples, axis=1) if samples.ndim > 1 else samples
            hop = max(1, SR // 20)
            padded = np.pad(mono, (0, (-len(mono)) % hop))
            rms = np.sqrt(np.mean(padded.reshape(-1, hop) ** 2, axis=1))
            scale = max(float(np.percentile(rms, 95)), .00001)
            activity[name] = np.round(np.clip(rms / scale, 0, 1), 3).tolist()
        (directory / 'score.sera').write_text(text, encoding='utf-8')
        summary = resolved.summary()
        atomic_json(directory / 'plan.json', summary)
        atomic_json(directory / 'settings.json', request)
        if exports.get('preview'):
            from .preview import html_preview
            (directory / 'preview.html').write_text(html_preview(score, resolved, audio, stems), encoding='utf-8')
        with zipfile.ZipFile(directory / 'bundle.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, filename in downloads.items():
                archive.write(directory / filename, f'{name}.wav')
            for filename in ['score.sera', 'plan.json', 'settings.json'] + (['preview.html'] if exports.get('preview') else []):
                archive.write(directory / filename, filename)
        result = dict(prayer_time=opts.prayer_time, prayerTimeline=prayer_timeline, source=text, selection=selection, grammar=[dict(terms=r['terms'], problems=r['problems'],
                      chain=[w.spoken for w in r['chain']], temporal=r['temporal']) for r in readings], downloads=downloads, resolved=summary, preview=bool(exports.get('preview')), title=score.meta.get('title', 'Untitled score'), words=words, tracks=names,
                      activity=activity, activityHz=20, vowelBrightness=resolved.vowel_brightness, duration=len(audio) / SR,
                      reading=' '.join(english(r, lx) for r in readings), diagnostics=diagnostics(score),
                      dialect=resolved.dialect.name, choir=opts.choir)
        atomic_json(directory / 'result.json', result)
        atomic_json(status, dict(state='done', message='Ready to listen', result=result))
    except Exception as exc:
        atomic_json(status, dict(state='error', message=str(exc) or type(exc).__name__))


class Workbench(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, output):
        super().__init__(address, Handler)
        self.output = output.resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.Lock()
        self.process = None
        self.job = None

    def cancel(self):
        if self.process and self.process.poll() is None:
            # Worker owns a process group, including synthesis subprocesses.
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            self.process.wait(timeout=10)
            atomic_json(self.output / self.job / 'status.json', dict(state='cancelled', message='Render cancelled'))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, value, status=200):
        self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), 'application/json; charset=utf-8', status)

    def send_bytes(self, body, content_type, status=200):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(body)

    def local_host(self):
        host = self.headers.get('Host', '').split(':')[0]
        if host not in ('127.0.0.1', 'localhost'):
            self.respond(dict(error='Use the localhost address printed by the server.'), 403)
            return False
        return True

    def do_GET(self):
        if not self.local_host():
            return
        path = urlparse(self.path).path
        if path == '/api/dictionary':
            from .web_authoring import dictionary_catalog
            from .score import ScoreError
            try:
                return self.respond(dictionary_catalog())
            except ScoreError as exc:
                return self.respond(dict(error=str(exc)), 400)
        if path == '/api/session':
            return self.respond(dict(token=self.server.token))
        if path == '/api/banks':
            from .samplebank import catalog
            return self.respond(catalog())
        if path == '/api/controls':
            from .web_controls import sections
            return self.respond(sections())
        if path == '/api/examples':
            return self.respond([p.name for p in sorted(EXAMPLES.glob('*.sera'))])
        if path.startswith('/api/example/'):
            name = path.removeprefix('/api/example/')
            if Path(name).name != name or not name.endswith('.sera'):
                return self.respond(dict(error='Invalid example'), 400)
            file = EXAMPLES / name
        elif path.startswith('/api/jobs/'):
            parts = path.split('/')
            if len(parts) != 5 or len(parts[3]) != 16 or any(c not in '0123456789abcdef' for c in parts[3]):
                return self.respond(dict(error='Invalid job'), 404)
            name = parts[4]
            if name == 'status':
                directory = self.server.output / parts[3]
                file = directory / 'status.json'
                if file.exists():
                    with self.server.lock:
                        proc = self.server.process
                        current = parts[3] == self.server.job and proc is not None
                        worker_running = current and proc.poll() is None
                        value = json.loads(file.read_text())
                        if current:
                            if value['state'] in ('done', 'error') and worker_running:
                                value = dict(state='running', message='Finishing render…')
                            elif value['state'] == 'running' and not worker_running:
                                value = dict(state='error', message='Render process exited unexpectedly. Try a shorter score.')
                    return self.respond(value)
            elif name in ('score.sera', 'bundle.zip', 'preview.html', 'plan.json', 'settings.json') or (name.endswith('.wav') and all(c.isalnum() or c in '-.' for c in name)):
                file = self.server.output / parts[3] / name
            else:
                return self.respond(dict(error='Not found'), 404)
        else:
            file = ASSETS / {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css', '/docs': 'docs.html',
                           '/studio.js': 'studio.js'}.get(path, '__missing__')
        if not file.is_file():
            return self.respond(dict(error='Not found'), 404)
        types = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
                 '.css': 'text/css; charset=utf-8', '.zip': 'application/zip', '.json': 'application/json', '.wav': 'audio/wav'}
        self.send_bytes(file.read_bytes(), types.get(file.suffix, 'text/plain; charset=utf-8'))

    def do_POST(self):
        if not self.local_host():
            return
        # Custom same-origin token prevents other websites from triggering local jobs.
        if not secrets.compare_digest(self.headers.get('X-Seraphim-Token', ''), self.server.token):
            return self.respond(dict(error='Refresh the page to reconnect.'), 403)
        path = urlparse(self.path).path
        from .score import ScoreError
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 262144:
                raise ValueError('Input must be under 256 KB.')
            request = json.loads(self.rfile.read(length))
            if not isinstance(request, dict):
                raise ValueError('Expected a JSON object.')
            if path == '/api/dictionary':
                from .web_authoring import browser_lexicon
                browser_lexicon(request.get('dictionary', {}))
                return self.respond(dict(valid=True))
            if path == '/api/compose':
                from .web_authoring import score_view
                coined = {}
                source, score = prepare(request, coined=coined)
                return self.respond(dict(text=source, coined=coined, **score_view(source, score)))
            if path == '/api/arrange':
                from .web_authoring import arrange, score_view
                source, score = prepare({**request, 'mode': 'score'})
                updated, index = arrange(source, score, request.get('index'), request.get('action'))
                _, validated = prepare({**request, 'mode': 'score', 'text': updated})
                return self.respond(dict(text=updated, index=index, **score_view(updated, validated)))
            if path == '/api/score-controls':
                from .web_controls import score_controls
                _, score = prepare(dict(mode='score', text=request.get('text')))
                return self.respond(score_controls(score))
            if path == '/api/edit-word':
                from .authoring import edit_word
                from .web_controls import numeric, boolean
                source, _ = prepare(request)
                updated = edit_word(source, request.get('index'), request.get('edit'),
                                    seed=numeric(request.get('seed', 0), 'seed', integer=True),
                                    dialect=request.get('dialect') or None,
                                    heresy=boolean(request, 'heresy', False))
                return self.respond(dict(text=updated))
            with self.server.lock:
                if path == '/api/cancel':
                    self.server.cancel()
                    return self.respond(dict(state='cancelled'))
                if path != '/api/render':
                    return self.respond(dict(error='Not found'), 404)
                if self.server.process and self.server.process.poll() is None:
                    return self.respond(dict(error='A render is already running.'), 409)
                job = secrets.token_hex(8)
                directory = self.server.output / job
                directory.mkdir()
                atomic_json(directory / 'request.json', request)
                atomic_json(directory / 'status.json', dict(state='running', message='Starting synthesis…'))
                log = (directory / 'worker.log').open('w')
                try:
                    self.server.process = subprocess.Popen([sys.executable, '-m', 'seraphim.web', '--worker', str(directory)],
                                                           stdout=log, stderr=log, start_new_session=True)
                finally:
                    log.close()
                self.server.job = job
                self.respond(dict(job=job), 202)
        except (ValueError, TypeError, ScoreError) as exc:
            self.respond(dict(error=str(exc)), 400)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--output', type=Path, default=Path('out/webui'),
                        help='render directory (default: out/webui in the working directory)')
    parser.add_argument('--worker', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return render_job(args.worker)
    server = Workbench(('127.0.0.1', args.port), args.output)
    print(f'Seraphim workbench: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with server.lock:
            server.cancel()
        server.server_close()


if __name__ == '__main__':
    main()
