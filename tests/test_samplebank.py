"""Sample selection and resynthesis without requiring proprietary recordings."""
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from scipy.io import wavfile

from seraphim import samplebank
from seraphim.render import Options, plan, synthesize
from seraphim.score import ScoreError, parse
from seraphim.synth import Seg, Voice, SR, render


class SampleBankTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.root=Path(self.temporary.name)
        self.folder=self.root/'fixture';self.folder.mkdir()
        units=[]
        for phone,label in [('i','i:'),('a','Q')]:
            audio=render([Seg(phone,.5)],Voice('recording',330,fscale=1.2,jitter=0)).audio
            wavfile.write(self.folder/f'{phone}.wav',SR,(audio*32767).astype(np.int16))
            units.append(dict(file=f'{phone}.wav',phones=[label],regions=[dict(start=.02,end=.48,phone=label)],pitch_hz=330,kind='stationary'))
        self.manifest=dict(format=1,id='fixture',name='Synthetic fixture',language='english',units=units)
        (self.folder/'bank.json').write_text(json.dumps(self.manifest))
        self.environment=patch.dict(os.environ,{'SERAPHIM_BANK_DIR':str(self.root)})
        self.environment.start()
        samplebank._bank.cache_clear()
        samplebank._features.cache_clear()

    def tearDown(self):
        samplebank._bank.cache_clear();samplebank._features.cache_clear()
        self.environment.stop();self.temporary.cleanup()

    def test_assignment_and_explicit_formant_override(self):
        assignment=samplebank.parse_selection('fixture,top=formant,choir=fixture,praise-2=formant')
        self.assertEqual(samplebank.selected(assignment,'1'),'fixture')
        self.assertIsNone(samplebank.selected(assignment,'top'))
        self.assertIsNone(samplebank.selected(assignment,'praise-2'))
        self.assertEqual(samplebank.selected(assignment,'praise-1'),'fixture')
        for bad in ['unknown=fixture','top=']:
            with self.assertRaises(ValueError): samplebank.parse_selection(bad)
        with self.assertRaises(ScoreError): samplebank.validate_selection({'top':'absent'})

    def test_catalog_mapping_and_missing_phoneme_reporting(self):
        self.assertEqual(samplebank.catalog()[0]['id'],'fixture')
        report=samplebank.coverage('fixture',['i','a','ʕ','sil'])
        self.assertEqual(report['counts'],{'sample':{'i':1},'approximation':{'a':1},'formant':{'ʕ':1}})
        report=samplebank.coverage('fixture',['a'],False)
        self.assertEqual(report['counts'],{'formant':{'a':1}})

    def test_manifest_path_and_alignment_validation(self):
        self.manifest['units'][0]['file']='../escape.wav'
        (self.folder/'bank.json').write_text(json.dumps(self.manifest))
        with self.assertRaises(ScoreError): samplebank.Bank(self.folder/'bank.json')
        self.manifest['units'][0]['file']='i.wav'
        self.manifest['units'][0]['regions'][0]['end']=-1
        (self.folder/'bank.json').write_text(json.dumps(self.manifest))
        with self.assertRaises(ScoreError): samplebank.Bank(self.folder/'bank.json')

    @unittest.skipUnless(importlib.util.find_spec('pyworld'), 'optional pyworld not installed')
    def test_pitch_duration_cache_and_tags(self):
        voice=Voice('target',200,fscale=1.08,jitter=0,breath=0)
        segs=[Seg('i',.5,(200,200),'vowel')]
        first=samplebank.render(segs,voice,np.random.default_rng(1),'fixture')
        second=samplebank.render(segs,voice,np.random.default_rng(1),'fixture')
        self.assertEqual(len(first.audio),int(.5*SR))
        self.assertEqual(first.spans,[('vowel',0,int(.5*SR))])
        self.assertTrue(np.isfinite(first.audio).all())
        np.testing.assert_array_equal(first.audio,second.audio)
        self.assertTrue(list((self.folder/'world-cache').glob('*.npz')))
        pw=samplebank.world()
        measured,t=pw.dio(first.audio,SR,f0_floor=100,f0_ceil=500)
        voiced=measured[(t>.1)&(t<.4)&(measured>0)]
        self.assertGreater(len(voiced),5)
        self.assertAlmostEqual(float(np.median(voiced)),200,delta=8)

    @unittest.skipUnless(importlib.util.find_spec('pyworld'), 'optional pyworld not installed')
    def test_fallback_and_pause_keep_their_slots(self):
        voice=Voice('target',200,jitter=0)
        segs=[Seg('i',.2,(200,200),0),Seg('ʕ',.15,(200,200),1),Seg('sil',.15),Seg('i',.2,(200,200),2)]
        result=samplebank.render(segs,voice,np.random.default_rng(2),'fixture')
        self.assertLessEqual(abs(len(result.audio)-.7*SR),1)
        self.assertTrue(np.isfinite(result.audio).all())
        self.assertLess(float(np.max(np.abs(result.audio[int(.40*SR):int(.46*SR)]))),1e-6)
        self.assertGreater(float(np.sqrt(np.mean(result.audio[int(.21*SR):int(.33*SR)]**2))),.001)

    @unittest.skipUnless(importlib.util.find_spec('pyworld'), 'optional pyworld not installed')
    def test_end_to_end_render_preserves_plan_and_reports_backends(self):
        score=parse('word gnomic\n top: /26/☢\n 1: ~ /45/☀\n')
        opts=Options(choir=True,room='dry',jobs=1,sample_banks={'top':'fixture','praise-1':'fixture'},
                     tones={'neutral':1})
        planned=plan(score,opts)
        expected=plan(score,replace(opts,sample_banks=None))
        self.assertEqual(planned.total,expected.total)
        audio,stems=synthesize(score,render_plan=planned)
        self.assertTrue(np.isfinite(audio).all())
        self.assertEqual(len(audio),int(planned.total*SR))
        self.assertIn('mouth-top',stems)
        self.assertEqual(set(planned.sample_report),{'top','praise-1'})
        self.assertIn('formant',planned.sample_report['top']['counts'])
        self.assertEqual(planned.summary()['sample_banks']['top']['bank'],'fixture')

    @unittest.skipUnless(importlib.util.find_spec('pyworld'), 'optional pyworld not installed')
    def test_sample_layers_work_with_fallen_effects_and_brightness(self):
        score=parse('word stammer\n top: /26/🔆\n 1: ~ /45/☢\n',dialect='succubus')
        planned=plan(score,Options(choir=False,room='dry',jobs=1,reverse_4d=True,
                                  sample_banks={'top':'fixture','1':'fixture'}))
        audio,stems=synthesize(score,render_plan=planned)
        self.assertTrue(np.isfinite(audio).all())
        self.assertIn('whisper-top',stems)
        self.assertIn('whisper-1',stems)
        self.assertGreater(float(np.max(np.abs(stems['mouth-1']))),0)
        self.assertEqual(set(planned.sample_report),{'top','1'})

    @unittest.skipUnless(importlib.util.find_spec('pyworld'), 'optional pyworld not installed')
    def test_join_blending_preserves_slots_without_changing_unit_selection(self):
        for name,phones,native in [('ia',['i','a'],['i:','Q']),('ai',['a','i'],['Q','i:'])]:
            audio=render([Seg(p,.25) for p in phones],Voice('pair',330,fscale=1.1)).audio
            wavfile.write(self.folder/f'{name}.wav',SR,(audio*32767).astype(np.int16))
            self.manifest['units'].append(dict(file=f'{name}.wav',phones=native,pitch_hz=330,kind='transition',
                regions=[dict(phone=native[0],start=.02,end=.25),dict(phone=native[1],start=.25,end=.48)]))
        (self.folder/'bank.json').write_text(json.dumps(self.manifest))
        voice=Voice('target',200,jitter=0)
        segs=[Seg('i',.2,(200,210),0),Seg('a',.2,(210,220),1),Seg('i',.2,(220,200),2)]
        off=samplebank.render(segs,voice,np.random.default_rng(2),'fixture')
        cached_before=set((self.folder/'world-cache').glob('*.npz'))
        on=samplebank.render(segs,replace(voice,syllable_blend=1),np.random.default_rng(2),'fixture')
        self.assertEqual(len(off.audio),len(on.audio))
        self.assertEqual(off.spans,on.spans)
        self.assertTrue(np.isfinite(on.audio).all())
        self.assertGreater(float(np.sqrt(np.mean((off.audio-on.audio)**2))),1e-4)
        self.assertEqual(set((self.folder/'world-cache').glob('*.npz')),cached_before)

    @unittest.skipUnless(importlib.util.find_spec('pyworld'), 'optional pyworld not installed')
    def test_sample_word_gap_is_filled_without_changing_preview_timing(self):
        score=parse('word\n top: אי☀\nword\n top: אי☀\n')
        opts=Options(choir=False,room='dry',jobs=1,hum=0,sample_banks={'top':'fixture'},
                     syllable_blend=0,tones={'neutral':1})
        off=plan(score,opts);on=plan(score,replace(opts,syllable_blend=.5))
        _,before=synthesize(score,render_plan=off);_,after=synthesize(score,render_plan=on)
        self.assertEqual([(w.start,w.duration) for w in off.words],[(w.start,w.duration) for w in on.words])
        start=int((off.words[0].start+off.words[0].duration)*SR)+5
        end=int(off.words[1].start*SR)-5
        self.assertEqual(float(np.max(np.abs(before['mouth-top'][start:end]))),0)
        self.assertGreater(float(np.sqrt(np.mean(after['mouth-top'][start:end]**2))),.005)

    @unittest.skipUnless(importlib.util.find_spec('pyworld'), 'optional pyworld not installed')
    def test_parallel_sample_jobs_match_serial_audio(self):
        word='word\n'+''.join(f' {mouth}: אי☀\n' for mouth in ('top','1','2','end'))
        score=parse(word*12)
        opts=Options(choir=False,room='dry',jobs=1,sample_banks={'all':'fixture'},tones={'neutral':1},hum=0)
        serial,_=synthesize(score,opts)
        parallel,_=synthesize(score,replace(opts,jobs=2))
        np.testing.assert_array_equal(serial,parallel)


if __name__=='__main__':
    unittest.main()
