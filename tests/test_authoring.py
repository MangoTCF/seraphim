"""Word edits and exact tense survive source and reading round trips."""
import json
from pathlib import Path
import tempfile
import unittest

from seraphim.authoring import edit_word
from seraphim.score import parse, ScoreError, temporal_meaning
from seraphim.web import atomic_json, render_job


class AuthoringTests(unittest.TestCase):
    source = '@title: Original\n# keep this\nword farpast\n top: /26/☀\n 1: ~ /45/☢\n\n---\n# next sentence\nword stammer\n top: /86/☀\nword gnomic\n top: /45/☀\n'

    def test_edit_preserves_surroundings_brightness_and_inherited_tense(self):
        updated = edit_word(self.source, 0, dict(tense='gnomic+nonpast', tone='fear:0.4', stammer=True,
                                               brightness={'top': 3}))
        old, new = parse(self.source), parse(updated)
        self.assertIn('@title: Original\n# keep this', updated)
        self.assertIn('---\n# next sentence', updated)
        self.assertEqual(new.words[0].tenses, ['gnomic', 'nonpast'])
        self.assertEqual(new.words[0].tones, {'fear': .4})
        self.assertTrue(new.words[0].stammer)
        self.assertEqual(new.words[0].mouths['top'].tokens[0].brightness, 3)
        self.assertEqual(new.words[0].mouths['1'].tokens[0].brightness, 3)
        self.assertTrue(new.words[0].mouths['1'].moved)
        self.assertEqual(new.words[1].tenses, old.words[1].tenses)
        self.assertTrue(new.words[1].sentence_start)
        self.assertTrue(new.words[1].stammer)
        self.assertEqual(new.words[2].tenses, ['gnomic'])

    def test_bad_edits_do_not_produce_a_score(self):
        for edit in [dict(mouths={'top':'bad'}), dict(mouths={'top':'Ø\nword nonpast'}),
                     dict(tense='wrong'), dict(tone='scream:2'), dict(brightness={'top': 4}),
                     dict(mouths={'oops':'Ø'}), dict(stammer='true')]:
            with self.subTest(edit=edit), self.assertRaises((ValueError, ScoreError)):
                edit_word(self.source, 0, edit)
        self.assertEqual(parse(self.source).words[0].tenses, ['farpast'])

    def test_exact_tense_survives_readback(self):
        from seraphim.reading import read_score
        score = parse('word farpast\n top: /26/☀\nword gnomic\n top: /26/☀\nword gnomic+nonpast\n top: /26/☀\nword\n top: /26/☀')
        self.assertEqual(score.words[0].langs, score.words[1].langs)
        self.assertNotEqual(score.words[0].tenses, score.words[1].tenses)
        self.assertEqual(score.words[-1].tenses, ['gnomic', 'nonpast'])
        self.assertEqual([w.tenses for w in read_score(score)[0]['chain']], [w.tenses for w in score.words])
        self.assertIn('jointly', temporal_meaning(score.words[-1].tenses))
        self.assertIn('unspecified', temporal_meaning(['aramaic']))

    def test_word_audition_keeps_full_source_and_original_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            request = dict(mode='score', text=self.source, selection=1, choir=False, room='dry', jobs=1)
            atomic_json(directory / 'request.json', request)
            render_job(directory)
            state = json.loads((directory / 'status.json').read_text())
            self.assertEqual(state['state'], 'done', state)
            result = state['result']
            self.assertEqual(len(result['words']), 1)
            self.assertEqual(result['words'][0]['source_index'], 1)
            self.assertEqual(result['source'], self.source)
            self.assertEqual(result['words'][0]['tenses'], ['farpast'])
            self.assertEqual((directory / 'score.sera').read_text(), self.source)
            self.assertEqual(len(result['grammar']), 2)


if __name__ == '__main__':
    unittest.main()
