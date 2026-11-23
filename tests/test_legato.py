"""Syllable blend smooths joins while preserving timing and explicit barriers."""
from dataclasses import replace
import unittest

import numpy as np

from seraphim.legato import amount, blend_features, parse_overrides, validate
from seraphim.render import Options, line_segments, plan, synthesize
from seraphim.score import ScoreError, parse
from seraphim.synth import SR, Voice, Seg, render


class LegatoTests(unittest.TestCase):
    def test_formant_blend_connects_hyphens_but_preserves_explicit_rests(self):
        line = parse('word\n top: מי☀ - מי☀ | מי☀\n').words[0].mouths['top']
        off = line_segments(line, 1)
        half = line_segments(line, 1, formant_blend=.5)
        full = line_segments(line, 1, formant_blend=1)
        self.assertEqual([s.dur for s in off if s.phone == 'sil'], [.08, .08])
        self.assertEqual([s.dur for s in half if s.phone == '_join'], [.04])
        self.assertEqual([s.dur for s in full if s.phone == 'sil'], [.08])
        self.assertFalse(any(s.phone == '_join' for s in full))

    def fixture(self):
        times=np.arange(121)*.005
        segs=[Seg('i',.3),Seg('a',.3)]
        sp=np.ones((121,8));sp[60:]=100
        ap=np.full_like(sp,.1);ap[60:]=.7
        f0=np.full(121,180.);f0[60:]=240
        amp=np.full(121,.5);amp[60:]=1
        return sp,ap,f0,amp,times,segs,np.array([0,.3,.6])

    def test_zero_is_an_exact_feature_bypass(self):
        args=self.fixture()
        before=[a.copy() for a in args[:4]]
        output=blend_features(*args,0)
        for original,old,new in zip(args[:4],before,output):
            self.assertIs(new,original)
            np.testing.assert_array_equal(new,old)

    def test_timbre_pitch_and_gain_steps_are_reduced(self):
        args=self.fixture()
        sp,ap,f0,amp=blend_features(*args,1)
        self.assertLess(np.max(np.abs(np.diff(np.log(sp[40:80,0])))),np.log(100)*.3)
        np.testing.assert_array_equal(sp[:50],args[0][:50])
        np.testing.assert_array_equal(sp[70:],args[0][70:])
        self.assertLess(np.max(np.abs(np.diff(ap[40:80,0]))),.15)
        self.assertLess(np.max(np.abs(np.diff(f0[40:80]))),15)
        self.assertLess(np.max(np.abs(np.diff(amp[40:80]))),.5*.3)
        self.assertTrue(np.isfinite(sp).all())
        for original,new in zip(args[:4],(sp,ap,f0,amp)):
            self.assertEqual(original.shape,new.shape)

    def test_silence_and_stop_frames_do_not_borrow_across_boundaries(self):
        for barrier in ('sil','t','ʔ'):
            times=np.arange(121)*.005
            segs=[Seg('i',.2),Seg(barrier,.2),Seg('a',.2)]
            sp=np.ones((121,8));sp[40:80]=1e-12;sp[80:]=100
            ap=np.ones_like(sp)
            f0=np.full(121,200.);f0[40:80]=0
            amp=np.ones(121);amp[40:80]=0
            output=blend_features(sp,ap,f0,amp,times,segs,np.array([0,.2,.4,.6]),1)
            for before,after in zip((sp,ap,f0,amp),output):
                np.testing.assert_allclose(before[41:79],after[41:79],rtol=1e-12,atol=1e-12)
            self.assertTrue(np.all(output[2][40:80]==0))

    def test_independent_mouth_override_and_inheritance(self):
        options=Options(syllable_blend=.7,mouth_blend=validate({'top':0,'choir':.3,'praise-1':1}))
        self.assertEqual(amount(options,'top'),0)
        self.assertEqual(amount(options,'1'),.7)
        self.assertEqual(amount(options,'praise-1'),1)
        self.assertEqual(amount(options,'praise-2'),.3)
        self.assertEqual(parse_overrides('top=0,1=.9'),{'top':0,'1':.9})
        for bad in [{'top':1.1},{'wrong':.5},{'top':float('nan')}]:
            with self.assertRaises(ScoreError):validate(bad)

    def test_formant_timing_and_tags_are_unchanged(self):
        segs=[Seg('i',.18,(150,170),0,.7),Seg('m',.07,(170,175),1,1.1),Seg('a',.2,(175,150),2,.9),Seg('sil',.1),Seg('u',.2,(150,150),3)]
        voice=Voice('test',150)
        old=render(segs,voice,np.random.default_rng(2))
        new=render(segs,replace(voice,syllable_blend=1),np.random.default_rng(2))
        self.assertEqual(len(old.audio),len(new.audio))
        self.assertEqual(old.spans,new.spans)
        self.assertGreater(float(np.sqrt(np.mean((old.audio-new.audio)**2))),1e-4)

    def test_per_mouth_change_only_changes_the_selected_dry_stem(self):
        score=parse('word\n top: אי☀ מה\n 1: אי☀ מה\n')
        base=Options(choir=False,room='dry',jobs=1,hum=0,syllable_blend=0,tones={'neutral':1})
        first=plan(score,base);second=plan(score,replace(base,mouth_blend={'1':1}))
        self.assertEqual(first.total,second.total)
        self.assertEqual(first.words[0].duration,second.words[0].duration)
        _,before=synthesize(score,render_plan=first)
        _,after=synthesize(score,render_plan=second)
        np.testing.assert_array_equal(before['mouth-top'],after['mouth-top'])
        self.assertGreater(float(np.sqrt(np.mean((before['mouth-1']-after['mouth-1'])**2))),1e-5)
        self.assertEqual(second.summary()['syllable_blend']['1'],1)
        self.assertEqual(second.summary()['syllable_blend']['top'],0)

    def test_connected_words_have_no_synthetic_gap_and_keep_word_timings(self):
        score=parse('word\n top: מי☀\nword\n top: מי☀\n')
        opts=Options(choir=False,room='dry',jobs=1,hum=0,syllable_blend=0,tones={'neutral':1})
        off=plan(score,opts);on=plan(score,replace(opts,syllable_blend=.5))
        _,before=synthesize(score,render_plan=off);_,after=synthesize(score,render_plan=on)
        self.assertEqual([(w.start,w.duration) for w in off.words],[(w.start,w.duration) for w in on.words])
        left=int((off.words[0].start+off.words[0].duration)*SR)+5
        right=int(off.words[1].start*SR)-5
        self.assertGreater(right,left)
        self.assertEqual(float(np.max(np.abs(before['mouth-top'][left:right]))),0)
        self.assertGreater(float(np.sqrt(np.mean(after['mouth-top'][left:right]**2))),.005)

    def test_word_gap_can_carry_unvoiced_frication(self):
        score=parse('word\n top: אס\nword\n top: אס\n')
        p=plan(score,Options(choir=False,room='dry',jobs=1,hum=0,syllable_blend=1,tones={'neutral':1}))
        _,stems=synthesize(score,render_plan=p)
        left=int((p.words[0].start+p.words[0].duration)*SR)+5
        right=int(p.words[1].start*SR)-5
        self.assertGreater(float(np.sqrt(np.mean(stems['mouth-top'][left:right]**2))),.0001)

    def test_closed_mouth_hums_do_not_restart_at_each_word(self):
        score=parse('word\n top: Ø\nword\n top: Ø\n')
        p=plan(score,Options(choir=False,room='dry',jobs=1,hum=.3,syllable_blend=.5,tones={'neutral':1}))
        _,stems=synthesize(score,render_plan=p)
        left=int((p.words[0].start+p.words[0].duration)*SR)+5
        right=int(p.words[1].start*SR)-5
        self.assertGreater(float(np.sqrt(np.mean(stems['mouth-top'][left:right]**2))),.001)

    def test_sentence_boundary_is_not_bridged(self):
        score=parse('word\n top: מי☀\n---\nword\n top: מי☀\n')
        p=plan(score,Options(choir=False,room='dry',jobs=1,hum=0,syllable_blend=1,tones={'neutral':1}))
        _,stems=synthesize(score,render_plan=p)
        left=int((p.words[0].start+p.words[0].duration+.05)*SR)
        right=int((p.words[1].start-.05)*SR)
        self.assertGreater(right,left)
        self.assertEqual(float(np.max(np.abs(stems['mouth-top'][left:right]))),0)


if __name__=='__main__':
    unittest.main()
