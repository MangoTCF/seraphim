"""Timing, DSP and concurrency guarantees without audio device access."""
import tempfile
from pathlib import Path
import unittest

import numpy as np
from scipy.io import wavfile

from seraphim import fx, synth
from seraphim.cli import _write
from seraphim.render import Options, master, plan, synthesize
from seraphim.score import parse


class TimingTests(unittest.TestCase):
    def test_stops_fit_their_allocated_time_even_at_high_tempo(self):
        for duration in (0.01, 0.06, 0.1):
            segs = [synth.Seg("t", duration), synth.Seg("a", 0.12)] * 10
            expected = sum(s.dur for s in segs)
            rendered = synth.render(segs, synth.Voice("test", 150))
            self.assertLessEqual(abs(len(rendered.audio) - expected * synth.SR), 1)

    def test_line_durations_match_plan(self):
        score = parse("word\n top: /26/☀ /45/☢\n 1: ~ /45/☀\nword\n top: /86/☀\n")
        p = plan(score, Options(jobs=1, choir=False, room="dry"))
        for w in p.words:
            for segs in w.lines.values():
                rendered = synth.render(segs, synth.Voice("test", 150))
                self.assertLessEqual(len(rendered.audio), round(w.duration * synth.SR) + 1)
        self.assertGreater(p.words[1].start, p.words[0].start + p.words[0].duration)

    def test_long_reverb_has_room_to_decay(self):
        score = parse("@reverb_time: 7\nword\n top: /26/☀\n")
        p = plan(score, Options(jobs=1))
        last = p.words[-1]
        self.assertGreater(p.total - last.start - last.duration, 8)
        self.assertEqual(p.summary()["room"]["rt60"], 7)

    def test_chunk_boundaries_follow_actual_rendered_time(self):
        from seraphim.render import phrase_chunks
        segs = [synth.Seg("t", .06), synth.Seg("a", .12), synth.Seg("sil", .1)] * 25
        chunks = phrase_chunks(segs, target=1)
        for (offset, chunk), (next_offset, _) in zip(chunks, chunks[1:]):
            audio = synth.render(chunk, synth.Voice("test", 150)).audio
            self.assertLessEqual(abs(len(audio) / synth.SR - (next_offset - offset)), 1 / synth.SR)


class SoundTests(unittest.TestCase):
    def test_deesser_reduces_strong_sibilance_and_preserves_bass(self):
        t = np.arange(synth.SR) / synth.SR
        high = .2 * np.sin(2 * np.pi * 6500 * t)
        low = .2 * np.sin(2 * np.pi * 200 * t)
        rms = lambda x: np.sqrt(np.mean(x[synth.SR // 4:] ** 2))
        self.assertLess(rms(fx.deess(high)), rms(high) * .7)
        self.assertAlmostEqual(rms(fx.deess(low)) / rms(low), 1, places=3)

    def test_master_rejects_dc_without_heavy_harmonic_distortion(self):
        t = np.arange(synth.SR) / synth.SR
        x = .1 + .2 * np.sin(2 * np.pi * 200 * t)
        audio = master(np.column_stack((x, x)))
        self.assertLess(abs(audio[synth.SR // 2:, 0].mean()), .001)
        self.assertLessEqual(np.abs(audio).max(), .89 + 1e-9)
        spectrum = np.abs(np.fft.rfft(audio[synth.SR // 2:, 0]))
        self.assertLess(spectrum[300] / spectrum[100], .02)  # 600 Hz / 200 Hz

    @unittest.skipUnless(synth.njit is not None, "numba not installed")
    def test_optional_filter_backend_matches_scipy(self):
        n, hop = 5000, 100
        rng = np.random.default_rng(2)
        src = rng.standard_normal(n)
        formants = np.stack([np.linspace(400, 1200, n // hop), np.linspace(1800, 1300, n // hop)])
        bandwidths = np.full_like(formants, 100)
        slow = synth._cascade_py(src, formants, bandwidths, hop, synth.SR)
        fast = synth._cascade_nb(src, formants, bandwidths, hop, float(synth.SR))
        np.testing.assert_allclose(slow, fast, rtol=1e-10, atol=1e-10)

    def test_float_wav_preserves_raw_stem_gain(self):
        signal = np.array([-.4, .2, 1.2], dtype=float)
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d, "raw.wav"))
            _write(path, signal, "float32")
            sr, decoded = wavfile.read(path)
            self.assertEqual(sr, synth.SR)
            self.assertEqual(decoded.dtype, np.float32)
            np.testing.assert_allclose(decoded, signal)


class RenderTests(unittest.TestCase):
    def test_all_dialects_render_finite_audio_with_choir_and_effects(self):
        for dialect in ("seraphic", "demonic", "succubus", "nephilim", "cupid"):
            with self.subTest(dialect=dialect):
                score = parse("word nonpast tone=pain:0.2\n top: /26/☀\n 1: ~ /45/☢\n 2: /86/🔆\n", dialect=dialect)
                audio, stems = synthesize(score, Options(dialect=dialect, jobs=1, room="room"))
                self.assertTrue(np.isfinite(audio).all())
                self.assertGreater(np.abs(audio).max(), .1)
                self.assertLessEqual(np.abs(audio).max(), .89 + 1e-9)
                self.assertEqual(audio.shape[1], 2)
                self.assertIn("praise-1", stems)

    def test_discarding_stems_does_not_change_mix(self):
        score = parse("word\n top: /26/☀\n")
        retained, stems = synthesize(score, Options(jobs=1, choir=False, room="dry"))
        discarded, empty = synthesize(score, Options(jobs=1, choir=False, room="dry", keep_stems=False))
        self.assertTrue(stems)
        self.assertEqual(empty, {})
        np.testing.assert_array_equal(retained, discarded)

    def test_actual_parallel_render_matches_sequential(self):
        # 12 * 4 lines exceeds the pool threshold; this exercises workers,
        # not merely two invocations of the sequential shortcut.
        word = "word\n top: /26/☀\n 1: /45/☢\n 2: /86/🔆\n end: /3/☀\n"
        score = parse(word * 12)
        seq, _ = synthesize(score, Options(jobs=1, choir=False, room="dry", hum=0, keep_stems=False))
        par, _ = synthesize(score, Options(jobs=2, choir=False, room="dry", hum=0, keep_stems=False))
        np.testing.assert_array_equal(seq, par)


if __name__ == "__main__":
    unittest.main()

class ArticulationTests(unittest.TestCase):
    def test_vowel_context_changes_stop_release_without_crossing_silence(self):
        def targets(vowel, silence=False):
            segs = [synth.Seg('k', .08)] + ([synth.Seg('sil', .05)] if silence else []) + [synth.Seg(vowel, .14)]
            parts = synth._expand(segs)
            original = [synth._targets(part, seg, synth.Voice('test', 150)) for part, seg, _, _ in parts]
            # contextual_targets only needs the valid formants in this case.
            changed = synth.contextual_targets(parts, original, .8)
            burst = next(i for i, (part, *_) in enumerate(parts) if part == 'burst')
            return original[burst]['f'], changed[burst]['f']
        _, front = targets('i')
        _, back = targets('u')
        self.assertGreater(front[1], back[1])
        original, blocked = targets('i', True)
        self.assertEqual(original, blocked)

    def test_identity_is_not_only_pitch_and_duration_is_preserved(self):
        from dataclasses import replace
        from seraphim.render import mouth_voice
        segments = [synth.Seg('k', .08), synth.Seg('i', .14), synth.Seg('s', .08), synth.Seg('a', .14)]
        voices = [replace(mouth_voice(m), f0=160, fscale=1) for m in ('top','1','2','end')]
        outputs = [synth.render(segments, v, rng=np.random.default_rng(41)).audio for v in voices]
        for audio in outputs:
            self.assertTrue(np.isfinite(audio).all())
            self.assertLessEqual(abs(len(audio) - sum(s.dur for s in segments) * synth.SR), 1)
        self.assertGreater(float(np.sqrt(np.mean((outputs[0]-outputs[-1])**2))), .001)
        self.assertEqual(len({(v.tilt,v.coarticulation,v.articulation) for v in voices}),4)
