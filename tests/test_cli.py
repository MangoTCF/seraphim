"""Authoring and export behavior at the public command boundary."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from scipy.io import wavfile

from seraphim.cli import main


class AuthoringTests(unittest.TestCase):
    def test_inspect_resolves_score_and_cli_settings(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "score.sera")
            path.write_text("@room: cathedral\n@voice: feminine\nword\n top: /26/☀\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(["inspect", str(path), "--room", "room"])
            result = json.loads(out.getvalue())
            self.assertEqual(result["room"]["name"], "room")
            self.assertEqual(result["voice"]["all"], 1)
            self.assertEqual(len(result["words"]), 1)

    def test_check_json_and_strict_status(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "score.sera")
            path.write_text("word\n top: א☀ א☀\n")  # two unhouseable vowels
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as cm:
                main(["check", str(path), "--json", "--strict"])
            self.assertEqual(cm.exception.code, 1)
            diagnostics = json.loads(out.getvalue())
            self.assertEqual(diagnostics[0]["mouth"], "top")
            self.assertIn("syllable", diagnostics[0]["message"])

    def test_preview_and_float_stem_export(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d, "score.sera")
            path.write_text("@title: <test>\nword\n top: /26/☀\n")
            preview, output, stems = Path(d, "preview.html"), Path(d, "mix.wav"), Path(d, "stems")
            main(["synth", str(path), "--no-choir", "--room", "dry", "-j", "1", "-q",
                  "--format", "float32", "--no-master", "--stems", str(stems),
                  "--preview", str(preview), "-o", str(output)])
            text = preview.read_text()
            self.assertIn("&lt;test&gt;", text)
            self.assertIn('data-word="0"', text)
            self.assertIn("data:audio/wav;base64,", text)
            _, stem = wavfile.read(stems / "mouth-top.wav")
            _, mixed = wavfile.read(output)
            self.assertEqual(stem.dtype, np.float32)
            self.assertLess(np.abs(stem).max(), .9)  # no independent peak normalization
            self.assertTrue(np.isfinite(mixed).all())


if __name__ == "__main__":
    unittest.main()
