"""Exercise the local HTTP boundary and real rendering/export contract."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from seraphim.web import Workbench, atomic_json, prepare, render_job


class WebTests(unittest.TestCase):
    def test_render_has_timed_mouths_seven_stems_and_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            atomic_json(directory / 'request.json', dict(mode='gloss', text='NPFV 1S see-OBJ ABS-light',
                                                        room='dry', tempo=3, choir=True))
            render_job(directory)
            status = json.loads((directory / 'status.json').read_text())
            self.assertEqual(status['state'], 'done', status)
            result = status['result']
            self.assertEqual(len(result['tracks']), 8)
            self.assertTrue(result['prayer_time'])
            self.assertEqual(set(result['prayerTimeline']), {'praise-1','praise-2','praise-3'})
            self.assertEqual(result['prayerTimeline']['praise-1'][0]['tense'], 'nonpast')
            self.assertGreater(result['duration'], result['words'][-1]['end'])
            for word in result['words']:
                self.assertGreater(word['end'], word['start'])
                self.assertEqual(set(word['mouths']), {'top', '1', '2', 'end'})
            for key, name in result['tracks'].items():
                self.assertTrue((directory / name).is_file())
                self.assertTrue(result['activity'][key])
            text = (directory / 'score.sera').read_text()
            _, score = prepare(dict(mode='score', text=text))
            self.assertEqual(len(score.words), len(result['words']))

    def test_full_synth_options_and_partial_voice_inheritance(self):
        from dataclasses import fields
        from seraphim.render import Options, plan
        from seraphim.web_controls import options, sections
        text, score = prepare(dict(mode='score', text='@dialect: nephilim\nword\n top: /26/☀'))
        baseline = plan(score).gender
        request = dict(voices={'choir': .9}, knobs={'growl': .7, 'pitch': -3, 'choir_pitch': 2},
                       tones={'neutral': True, 'anger': .4}, space=False, reverse_4d=True,
                       choir_level=.2, reverb_mix=.1, reverb_time=1.2, reverb_tone=.7,
                       predelay=25, hum=0, glitter=0, master=False, jobs=1)
        opts = options(request, score)
        self.assertEqual(opts.predelay, .025)
        self.assertEqual(opts.voice, {**baseline, 'choir': .9})
        self.assertEqual(opts.tones, {'neutral': 1, 'anger': .4})
        self.assertEqual(opts.knobs['pitch'], -3)
        self.assertFalse(opts.space)
        self.assertFalse(opts.master)
        self.assertTrue(opts.reverse_4d)
        self.assertEqual(opts.hum, 0)
        exposed = {f['key'] for group in sections() for f in group['fields'] if f['target'] == 'option'}
        exposed |= {'choir', 'dialect', 'room', 'seed', 'voice', 'reverb', 'knobs', 'tones', 'keep_stems', 'sample_banks', 'mouth_blend'}
        self.assertEqual({f.name for f in fields(Options)} - exposed, set())
        for bad in [dict(knobs={'growl': 1.1}), dict(voices={'top': float('nan')}),
                    dict(tones={'pain': -1}), dict(jobs=1.2), dict(master='false'),
                    dict(knobs={'grolw': .2}), dict(export={'format': 'mp3'}), dict(predelay=-1)]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                options(bad, score)

    def test_float_exports_normalization_bundle_and_preview(self):
        import zipfile
        import numpy as np
        from scipy.io import wavfile
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            request = dict(mode='score', text='word\n top: /26/☀', room='dry', choir=False,
                           master=False, jobs=1, voices={'top': .5}, tones={'neutral': True},
                           export={'format': 'float32', 'normalize_stems': True, 'preview': True})
            atomic_json(directory / 'request.json', request)
            render_job(directory)
            status = json.loads((directory / 'status.json').read_text())
            self.assertEqual(status['state'], 'done', status)
            result = status['result']
            _, audition = wavfile.read(directory / result['tracks']['mouth-top'])
            _, exported = wavfile.read(directory / result['downloads']['mouth-top'])
            self.assertEqual(audition.dtype, np.int16)
            self.assertEqual(exported.dtype, np.float32)
            self.assertAlmostEqual(float(np.max(np.abs(exported))), .9, places=5)
            self.assertFalse(result['resolved']['options']['master'])
            self.assertEqual(result['resolved']['voice']['top'], .5)
            with zipfile.ZipFile(directory / 'bundle.zip') as archive:
                self.assertIn('preview.html', archive.namelist())
                self.assertIn('settings.json', archive.namelist())
                self.assertIn('plan.json', archive.namelist())
                self.assertIn('mix.wav', archive.namelist())
                self.assertNotIn('praise-1.wav', archive.namelist())
                self.assertIn(b'data:audio/wav;base64,', archive.read('preview.html'))

    def test_invalid_settings_are_reported_without_audio(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            atomic_json(directory / 'request.json', dict(mode='score', text='word\n top: /26/☀', tempo='nan'))
            render_job(directory)
            status = json.loads((directory / 'status.json').read_text())
            self.assertEqual(status['state'], 'error')
            self.assertIn('tempo', status['message'])
            self.assertFalse((directory / 'mix.wav').exists())

    def test_local_http_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = Workbench(('127.0.0.1', 0), Path(tmp))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            try:
                with urlopen(base + '/') as response:
                    self.assertIn(b'id="angel"', response.read())
                for request in [Request(base + '/api/render', data=b'{}'),
                                Request(base + '/api/session', headers={'Host': 'attacker.example'}),
                                Request(base + '/api/example/../web.py')]:
                    with self.assertRaises(HTTPError) as error:
                        urlopen(request)
                    self.assertIn(error.exception.code, (400, 403, 404))
                with urlopen(base + '/api/session') as response:
                    token = json.load(response)['token']
                request = Request(base + '/api/render', data=b'[]', headers={'X-Seraphim-Token': token})
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(error.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == '__main__':
    unittest.main()
