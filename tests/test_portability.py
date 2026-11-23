"""Scores must decode without the author's machine or personal vocabulary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from seraphim.grammar import build, clause_from_gloss, to_sera
from seraphim.lexicon import Entry, Lexicon, LexiconError, score_lexicon
from seraphim.reading import english, read_score
from seraphim.score import ScoreError, parse


class PortableScoreTests(unittest.TestCase):
    def make_score(self):
        lx = Lexicon(user_path=None, save=False)
        sentence = clause_from_gloss("NPFV 1S admire:V -OBJ starlight:N", lexicon=lx)
        build([sentence], lx)
        return to_sera([sentence], lx)

    def test_fresh_process_decodes_without_user_vocabulary(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "score.sera")
            path.write_text(self.make_score(), encoding="utf-8")
            result = subprocess.run([sys.executable, "-m", "seraphim", "read", str(path), "--strict"],
                                    env=dict(os.environ, XDG_DATA_HOME=d), capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("I am admiring the starlight.", result.stdout)

    def test_embedded_vocabulary_beats_conflicting_local_entries(self):
        score = parse(self.make_score())
        lx = Lexicon(user_path=None, save=False)
        lx.entries["admire"] = Entry("admire", "N", ["א☀"], "user")
        self.assertEqual(english(read_score(score, lx)[0]), "I am admiring the starlight.")

    def test_corrupt_snapshot_rejected(self):
        text = self.make_score().replace('"pos":"V"', '"pos":"N"', 1)
        with self.assertRaisesRegex(ScoreError, "hash mismatch"):
            parse(text)

    def test_unknown_morphemes_reported_in_legacy_scores(self):
        score = parse("word\n top: /26/☀ /45/☢ /26/☀\n")
        self.assertTrue(any("unknown morpheme" in p for p in read_score(score)[0]["problems"]))

    def test_only_used_entries_are_embedded(self):
        score = parse(self.make_score())
        entries = score.lexicon
        self.assertIn("admire", entries)
        self.assertNotIn("Aghma_Shwa", entries)
        self.assertEqual(set(score_lexicon(score).entries), set(entries))

    def test_snapshot_collision_rejected(self):
        entries = {"a": {"pos": "N", "tokens": ["א☀"]}, "b": {"pos": "N", "tokens": ["א☀"]}}
        with self.assertRaisesRegex(ScoreError, "collision"):
            parse("@lexicon: " + json.dumps(entries) + "\nword\n top: א☀\n")


class PersistenceTests(unittest.TestCase):
    def test_invalid_tokens_and_collisions_fail_at_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "lexicon.tsv")
            for body, message in (("bad\tN\tnot-hebrew\n", "line 1"),
                                  ("a\tN\tא☀\nb\tN\tא☀\n", "collision")):
                path.write_text(body, encoding="utf-8")
                with self.assertRaisesRegex(LexiconError, message):
                    Lexicon(str(path), save=False)

    def test_failed_replace_preserves_original_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "lexicon.tsv")
            lx = Lexicon(str(path))
            lx.coin("starlight")
            original = path.read_bytes()
            with mock.patch("seraphim.lexicon.os.replace", side_effect=OSError("disk error")):
                with self.assertRaises(OSError):
                    lx.add("starlight", "ADJ", lx.entries["starlight"].tokens, replace=True)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(list(Path(d).glob(".lexicon-*")))

    def test_concurrent_coining_keeps_both_updates(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d, "lexicon.tsv"))
            script = "from seraphim.lexicon import Lexicon; import sys; Lexicon(sys.argv[1]).coin(sys.argv[2])"
            processes = [subprocess.Popen([sys.executable, "-c", script, path, word],
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                         for word in ("starlight", "moonlight")]
            for process in processes:
                _, err = process.communicate(timeout=30)
                self.assertEqual(process.returncode, 0, err.decode())
            lx = Lexicon(path, save=False)
            self.assertIn("starlight", lx.entries)
            self.assertIn("moonlight", lx.entries)

    def test_add_rejects_phonemic_alias_and_injected_rows(self):
        with tempfile.TemporaryDirectory() as d:
            lx = Lexicon(str(Path(d, "lexicon.tsv")))
            e = lx.coin("starlight")
            with self.assertRaisesRegex(LexiconError, "collision"):
                lx.add("other", "N", e.tokens)
            with self.assertRaises(LexiconError):
                lx.add("bad\nrow", "N", e.tokens)
