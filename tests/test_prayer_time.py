"""Tense signatures follow final playback time, even in backwards choirs."""
import random
import unittest
from dataclasses import replace

import numpy as np

from seraphim import choir, synth
from seraphim.render import Options, plan, synthesize
from seraphim.score import parse


def at(segments, when, reverse=False):
    total = sum(s.dur for s in segments)
    source_time = total - when if reverse else when
    cursor = 0
    for s in segments:
        if cursor <= source_time < cursor + s.dur:
            fraction = (source_time - cursor) / s.dur
            pitch = s.f0[0] + fraction * (s.f0[1] - s.f0[0]) if s.f0 else None
            return s.tag, pitch
        cursor += s.dur
    raise AssertionError('Time outside schedule')


class TransitionTests(unittest.TestCase):
    def test_smooth_tracks_preserve_targets_and_have_flat_endpoint_slopes(self):
        q = np.linspace(0, 1, 10001)
        smooth = synth.interpolate_track([0,1],[0,1],q)
        linear = synth.interpolate_track([0,1],[0,1],q,0)
        np.testing.assert_allclose(linear,q)
        self.assertEqual(smooth[0],0)
        self.assertEqual(smooth[-1],1)
        self.assertTrue(np.all(np.diff(smooth)>=0))
        self.assertLess((smooth[1]-smooth[0])/(q[1]-q[0]), .001)
        self.assertLess((smooth[-1]-smooth[-2])/(q[1]-q[0]), .001)
        np.testing.assert_allclose(synth.interpolate_track([0,0,1],[.5,0,1],q),smooth)

    def test_stop_subparts_share_one_pitch_glide_without_restarts(self):
        stop = synth.Seg('t', .1, (100, 200))
        parts = synth._expand([stop, synth.Seg('a', .2)])
        stopped = [p for p in parts if p[1] is stop]
        self.assertEqual(stopped[0][3][0],100)
        self.assertAlmostEqual(stopped[-1][3][1],200)
        for first, second in zip(stopped, stopped[1:]):
            self.assertAlmostEqual(first[3][1],second[3][0])
        self.assertAlmostEqual(sum(p[2] for p in stopped),.1)

    def test_smoothing_preserves_silence_and_stop_duration(self):
        segs=[synth.Seg('k',.08),synth.Seg('i',.18),synth.Seg('sil',.15),synth.Seg('a',.2)]
        voice=synth.Voice('test',160)
        old=synth.render(segs,replace(voice,transitions=0),np.random.default_rng(4)).audio
        new=synth.render(segs,voice,np.random.default_rng(4)).audio
        self.assertEqual(len(old),len(new))
        self.assertTrue(np.isfinite(new).all())
        self.assertGreater(float(np.sqrt(np.mean((old-new)**2))),.001)
        # A real pause must remain a pause, rather than becoming a crossfade.
        middle=new[int(.32*synth.SR):int(.36*synth.SR)]
        self.assertLess(float(np.sqrt(np.mean(middle**2))),.005)


class PrayerTimeTests(unittest.TestCase):
    def test_linger_rises_in_playback_order_with_or_without_backmask(self):
        for reverse in (False, True):
            phrase = [synth.Seg('a', .3, (180, 200)), synth.Seg('sil', .1)]
            source = [replace(s, f0=s.f0[::-1] if s.f0 else None)
                      for s in phrase[::-1]] if reverse else phrase
            segments, start = choir.linger(source, 2, 12, backmask=reverse)
            self.assertAlmostEqual(start, .3)
            self.assertAlmostEqual(at(segments, start + .01, reverse)[1], 201)
            self.assertAlmostEqual(at(segments, start + 1.99, reverse)[1], 399)

    def test_prayer_tail_extends_dry_stems_and_fades_to_silence(self):
        score = parse('word\n top: /26/☀')
        opts = Options(room='dry', space=False, keep_stems=True, jobs=1, prayer_tail=3)
        long = plan(score, opts)
        short = plan(score, replace(opts, prayer_tail=0))
        self.assertAlmostEqual(long.total - short.total, 3)
        _, stems = synthesize(score, render_plan=long)
        for channel in ('praise-1', 'praise-2', 'praise-3'):
            stem = stems[channel]
            end = np.flatnonzero(np.abs(stem) > 1e-6)[-1]
            self.assertGreater(end / synth.SR, long.words[-1].start + 3)
            self.assertLess(end, len(stem) - synth.SR // 4)
            self.assertLess(np.max(np.abs(stem[end - 1000:end])),
                            np.max(np.abs(stem[end - synth.SR:end - synth.SR // 2])) * .1)

    def test_tail_carries_vowels_and_consonants_in_playback_order(self):
        closing = [synth.Seg(phone, .2, (180, 180), tag='latin') for phone in ('s', 'a', 'n', 'u')]
        for reverse in (False, True):
            source = closing[::-1] if reverse else closing
            segments, start = choir.linger(source, 1, 7, backmask=reverse)
            tail = (segments[::-1] if reverse else segments)[len(closing):]
            self.assertEqual([s.phone for s in tail], ['s', 'a', 'n', 'u'])
            self.assertAlmostEqual(sum(s.dur for s in tail), 1)
            self.assertGreater(at(segments, start + .8, reverse)[1],
                               at(segments, start + .2, reverse)[1])

    def spans(self,first='farpast'):
        return [dict(start=0,end=1,tense=first,language='aramaic',word=0),
                dict(start=1,end=2,tense='nonpast',language='latin',word=1)]

    def test_each_motif_has_a_distinct_shape(self):
        curves={t:[choir.motif_pitch(t,p) for p in (0,.5,1)] for t in choir.TENSE_MOTIFS}
        self.assertGreater(curves['farpast'][0],curves['farpast'][1])
        self.assertGreater(curves['farpast'][1],curves['farpast'][2])
        self.assertEqual(len(set(curves['gnomic'])),1)
        self.assertLess(curves['nearpast'][0],curves['nearpast'][2])
        self.assertGreater(curves['nonpast'][1],curves['nonpast'][0])
        self.assertGreater(curves['nonpast'][1],curves['nonpast'][2])

    def test_schedule_languages_and_motifs_survive_reversal(self):
        for reverse in (False,True):
            segs=choir.timed_schedule(self.spans(),0,rng=random.Random(4),backmask=reverse)
            self.assertAlmostEqual(sum(s.dur for s in segs),2,places=9)
            self.assertTrue(all(s.dur>0 for s in segs))
            self.assertEqual(at(segs,.5,reverse)[0],'aramaic')
            self.assertEqual(at(segs,1.5,reverse)[0],'latin')
            # Cue direction is defined on the final audible timeline.
            first=at(segs,.10,reverse)[1]
            later=at(segs,.28,reverse)[1]
            self.assertIsNotNone(first)
            self.assertGreater(first,later)
            gnomic=choir.timed_schedule(self.spans('gnomic'),0,rng=random.Random(4),backmask=reverse)
            self.assertAlmostEqual(at(gnomic,.10,reverse)[1],at(gnomic,.28,reverse)[1],places=6)

    def test_four_way_stack_reaches_all_prayer_voices(self):
        score=parse('word farpast+gnomic+nearpast+nonpast\n top: /26/☀')
        p=plan(score,Options(jobs=1,room='dry'))
        found=set()
        for voice in range(3):
            spans=choir.time_spans(p.words,voice,0,p.total)
            found.update(s['tense'] for s in spans)
            self.assertAlmostEqual(sum(s['end']-s['start'] for s in spans),p.total)
        self.assertEqual(found,{'farpast','gnomic','nearpast','nonpast'})

    def test_farpast_and_gnomic_differ_in_audio_but_legacy_is_available(self):
        scores=[parse(f'word {t}\n top: /26/☀') for t in ('farpast','gnomic')]
        def render(score,enabled):
            return synthesize(score,Options(jobs=1,room='dry',prayer_time=enabled,tones={'neutral':1}))[1]
        a,b=[render(score,True) for score in scores]
        np.testing.assert_array_equal(a['mouth-top'],b['mouth-top'])
        self.assertGreater(float(np.sqrt(np.mean((a['praise-1']-b['praise-1'])**2))),.001)
        a,b=[render(score,False) for score in scores]
        np.testing.assert_array_equal(a['praise-1'],b['praise-1'])


if __name__=='__main__':
    unittest.main()
