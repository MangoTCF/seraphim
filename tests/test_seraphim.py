"""Behavioral regression tests for Seraphim."""

import argparse
import os
import tempfile
import unicodedata
import unittest
from unittest import mock

from seraphim.grammar import GrammarError, build, clause_from_gloss
from seraphim.lexicon import Lexicon, LexiconError, Varier, check_tokens
from seraphim.reading import english, read_score
from seraphim.score import ScoreError, parse


def make_lexicon(tmpdir):
    return Lexicon(user_path=os.path.join(tmpdir, "lexicon.tsv"), save=False)


class LexiconTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "lexicon.tsv")

    def tearDown(self):
        self.dir.cleanup()

    def load(self, text):
        with open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        return Lexicon(user_path=self.path, save=False)

    def test_malformed_line_reports_file_and_line(self):
        with self.assertRaises(LexiconError) as cm:
            self.load("ok\tN\tא☀\nbroken line\n")
        self.assertIn(self.path, str(cm.exception))
        self.assertIn("line 2", str(cm.exception))

    def test_unknown_part_of_speech(self):
        with self.assertRaises(LexiconError):
            self.load("word\tZZZ\tא☀\n")

    def test_empty_token_list(self):
        with self.assertRaises(LexiconError):
            self.load("word\tN\t\n")

    def test_crlf_is_stripped(self):
        lx = self.load("crlfword\tN\tא☀\tuser\r\n")
        self.assertEqual(lx.entries["crlfword"].tokens, ["א☀"])

    def test_check_tokens_rejects_empty(self):
        with self.assertRaises(LexiconError):
            check_tokens([])

    def test_coin_gives_up_instead_of_saving_a_collision(self):
        lx = Lexicon(user_path=None, save=False)
        with mock.patch("seraphim.lexicon.signature", return_value=(("x",),)):
            with mock.patch.object(lx, "by_signature", return_value={(("x",),): None}):
                with self.assertRaises(LexiconError):
                    lx.coin("collides")


class VarierTests(unittest.TestCase):
    def test_respell_does_not_repeat_alternates(self):
        v = Varier(seed=1)
        value = max(v.bank, key=lambda k: len(v.bank[k]))
        words = [w for w in v.bank[value][:8]
                 if not any(unicodedata.category(c) == "Mn" for c in w)]
        self.assertGreaterEqual(len(words), 4)
        v.bank = {value: words}
        with mock.patch("seraphim.lexicon.hebrew.spell", return_value=[]):
            out = [v.respell(words[0] + "☀") for _ in range(len(words))]
        self.assertEqual(len(set(out)), len(out))


class ScoreMetadataTests(unittest.TestCase):
    def parse_meta(self, meta):
        return parse(meta + "\nword\n  top: א☀\n", heresy=True)

    def test_rejects_bad_metadata(self):
        bad = [
            "@tense: bogus", "@tense: farpast+nonpast", "@tempo: 0",
            "@tempo: -1", "@tempo: abc", "@tone: bogus", "@room: bogus",
            "@voice: bogus", "@reading: weird", "@begadkefat: weird",
            "@reverb_tone: 5", "@predelay: -1", "@growl: 1.5",
            "@gender: 2", "@pitch: nan",
            "@temop: 2", "@voice: typo=0.7", "@format: 999",
        ]
        for meta in bad:
            with self.subTest(meta=meta):
                with self.assertRaises(ScoreError):
                    self.parse_meta(meta)

    def test_accepts_signed_pitch_and_gender(self):
        self.assertEqual(self.parse_meta("@pitch: -4").meta["pitch"], "-4")
        self.assertEqual(self.parse_meta("@gender: -0.5").meta["gender"], "-0.5")


class GrammarTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.lx = make_lexicon(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_unknown_category(self):
        with self.assertRaises(GrammarError):
            clause_from_gloss("x:ZZZ 1S comprehend", lexicon=self.lx)

    def test_unknown_tense(self):
        with self.assertRaises(GrammarError):
            clause_from_gloss("NPFV 1S comprehend", tense="bogus", lexicon=self.lx)

    def test_subject_after_negation_moves(self):
        s = clause_from_gloss("NPFV 1S NEG comprehend-OBJ ABS-allure", lexicon=self.lx)
        build([s], self.lx)
        self.assertEqual(s.terms[1].gloss, "1S.NOM")

    def test_subject_after_adverb_moves(self):
        s = clause_from_gloss("NPFV quickly:ADV 1S comprehend-OBJ ABS-allure", lexicon=self.lx)
        build([s], self.lx)
        self.assertEqual(s.terms[1].gloss, "1S.NOM")

    def test_nom_marked_subject_stays_in_situ(self):
        s = clause_from_gloss("NPFV NOM- man INS- dog see -OBJ woman INS- cat", lexicon=self.lx)
        build([s], self.lx)
        self.assertFalse(s.terms[1].gloss.endswith(".NOM"))
        self.assertIn("NOM-", [t.gloss for t in s.terms])


class ReadingTests(unittest.TestCase):
    def test_sentences_split_only_at_explicit_breaks(self):
        lx = Lexicon(user_path=None, save=False)
        one = parse("word nonpast\n  top: א☀\nword nonpast\n  top: ב☀\n", heresy=True)
        self.assertEqual(len(read_score(one, lx)), 1)
        two = parse("word nonpast\n  top: א☀\n---\nword nonpast\n  top: ב☀\n", heresy=True)
        self.assertEqual(len(read_score(two, lx)), 2)


HAVE_ENGLISH = True
try:
    from seraphim.english import nlp
    nlp()
except (SystemExit, ImportError, OSError):
    HAVE_ENGLISH = False


@unittest.skipUnless(HAVE_ENGLISH, "spaCy English model not installed")
class EnglishRoundTripTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.lx = make_lexicon(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def roundtrip(self, text):
        from seraphim.english import translate
        from seraphim.grammar import to_sera
        sentences = translate(text, self.lx)
        build(sentences, self.lx)
        score = parse(to_sera(sentences, self.lx, title=text), heresy=True)
        reads = read_score(score, self.lx)
        self.assertEqual([p for r in reads for p in r["problems"]], [])
        return " / ".join(english(r, self.lx) for r in reads), sentences

    def test_multiword_subject_roundtrip(self):
        text, sentences = self.roundtrip("A man with a dog saw a woman with a cat.")
        self.assertEqual(text, "The man with the dog saw the woman with the cat.")
        self.assertNotIn("NOM-", [t.gloss for s in sentences for t in s.terms])
        self.assertTrue(any(t.role == "mainsubj" for s in sentences for t in s.terms))

    def test_construct_subject_roundtrip(self):
        text, _ = self.roundtrip("The child of the king sleeps.")
        self.assertEqual(text, "The child of the king is sleeping.")

    def test_time_adverb_roundtrip(self):
        text, _ = self.roundtrip("They will sing in the temple tomorrow.")
        self.assertEqual(text, "They will sing in the temple tomorrow.")

    def test_passive_agent_and_patient(self):
        text, _ = self.roundtrip("The woman was seen by the man.")
        self.assertEqual(text, "The man saw the woman.")

    def test_agentless_passive(self):
        text, _ = self.roundtrip("The woman was not seen.")
        self.assertEqual(text, "The woman was not seen.")

    def test_separate_subjects_are_preserved(self):
        text, _ = self.roundtrip("I see you and you see me.")
        self.assertEqual(text, "I see you. / And you see me.")

    def test_noun_tagged_coordinated_predicate(self):
        text, _ = self.roundtrip("The man sings and the woman dances.")
        self.assertEqual(text, "The man sings. / And the woman is dancing.")

    def test_modal_distinctions_and_questions(self):
        for text in ("I can see you.", "I must leave.", "I may leave.", "I should leave.",
                     "I could leave.", "I might leave.", "I would leave.", "Can you see me?",
                     "I must not leave."):
            with self.subTest(text=text):
                back, _ = self.roundtrip(text)
                self.assertEqual(back, text)

    def test_strict_translation_rejects_unsupported_coordination(self):
        from seraphim.english import translate
        with self.assertRaisesRegex(GrammarError, "unsupported coordination"):
            translate("I can sing and dance.", self.lx, strict=True)


class CliValidationTests(unittest.TestCase):
    def test_numeric_types(self):
        from seraphim.cli import (_finite_float, _nonnegative_float,
                                  _nonnegative_int, _positive_float, _unit_float)
        self.assertEqual(_positive_float("1.5"), 1.5)
        self.assertEqual(_nonnegative_int("0"), 0)
        self.assertEqual(_finite_float("-4"), -4.0)
        for fn, value in [(_positive_float, "0"), (_nonnegative_float, "-1"),
                          (_nonnegative_int, "-1"), (_unit_float, "2")]:
            with self.subTest(fn=fn.__name__, value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    fn(value)


if __name__ == "__main__":
    unittest.main()
