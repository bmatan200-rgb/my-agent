"""Offline voice-catalog regression tests (no audio model initialization)."""
import ast
import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path.home() / "video-dubbing-local"
sys.path.insert(0, str(ROOT))
import voice_library as lib


class VoiceLibraryTests(unittest.TestCase):
    def test_licensed_samples_and_presets(self):
        voices = lib.catalog()
        self.assertEqual(len([v for v in voices if not v["is_preset"]]), 16)
        self.assertEqual(len([v for v in voices if v["is_preset"]]), 16)
        self.assertEqual(len({v["id"] for v in voices}), len(voices))
        self.assertEqual({v["type"] for v in voices}, {"male", "female"})
        self.assertTrue(all((ROOT / "models" / "hebrew-voices" / v["file"]).is_file() for v in voices))

    def test_automatic_suggestions_and_distinct_ids(self):
        first = lib.choose("male", "animation")
        second = lib.choose("male", "animation", {first})
        self.assertNotEqual(first, second)
        self.assertTrue(lib.voice(first)["is_preset"])
        self.assertFalse(lib.voice(lib.choose("female", "live"))["is_preset"])
        self.assertIsNone(lib.choose("unknown", "animation"))

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'NumPy available only in dubbing venv')
    def test_pitch_shift_keeps_duration_and_amplitude(self):
        import numpy as np
        signal = np.sin(np.linspace(0, 4000, 24000, dtype=np.float32)) * 0.08
        out = lib.transform_audio(signal, 24000, "cartoon_child_bright")
        self.assertEqual(len(signal), len(out))
        self.assertTrue(np.isfinite(out).all())
        self.assertGreater(float(np.std(out)), 0.001)
        self.assertLess(float(np.max(np.abs(out))), 0.96)
        self.assertFalse(np.array_equal(signal, out))

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'NumPy available only in dubbing venv')
    def test_original_voice_unmodified(self):
        import numpy as np
        signal = np.linspace(-0.08, 0.08, 24000, dtype=np.float32)
        result = lib.transform_audio(signal, 24000, "female_1")
        np.testing.assert_array_equal(result, signal)

    @unittest.skipUnless(importlib.util.find_spec('numpy'), 'NumPy available only in dubbing venv')
    def test_invalid_voice_rejected(self):
        import numpy as np
        with self.assertRaises(ValueError):
            lib.transform_audio(np.ones(24000, dtype=np.float32), 24000, "not-a-voice")

    def test_movie_accepts_styles_voice_maps(self):
        source = (ROOT / "movie_dub.py").read_text(encoding="utf-8")
        self.assertIn("'--film-style'", source)
        self.assertIn("get('base_id'", source)
        self.assertIn("x=transform_audio", source)
        self.assertIn("if a.voice_map:", source)


if __name__ == "__main__":
    unittest.main()