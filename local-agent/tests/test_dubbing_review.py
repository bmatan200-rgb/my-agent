"""Fast local dubbing tests: edit -> synth input, cache invalidation and UI plumbing."""
import ast
import hashlib
import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

AGENT = Path(__file__).resolve().parents[1] / "agent.py"
DUBBER = Path.home() / "video-dubbing-local" / "movie_dub.py"


def load_dubber():
    sys.path.insert(0, str(DUBBER.parent))
    spec = importlib.util.spec_from_file_location("local_movie_dub_test", DUBBER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def speech_key(version, segment, voice):
    return hashlib.sha256(json.dumps(
        [version, segment, voice], ensure_ascii=False, sort_keys=True
    ).encode()).hexdigest()[:24]


class DubbingReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dub = load_dubber()
        cls.segments = [
            dict(id="00001", speaker="SPEAKER_00", hebrew="שלום", source="hello", start=0.0, end=1.0),
            dict(id="00002", speaker="SPEAKER_01", hebrew="בוקר טוב", source="good morning", start=2.0, end=3.0),
        ]

    def test_reviewed_text_replaces_spoken_text_for_one_segment(self):
        before = self.segments
        review = "[00001|SPEAKER_00] שלום\n[00002|SPEAKER_01] יום טוב יותר"
        after = self.dub.apply_review(before, review, {"SPEAKER_00", "SPEAKER_01"})
        self.assertEqual(after[1]["hebrew"], "יום טוב יותר")
        self.assertEqual(after[0]["hebrew"], before[0]["hebrew"])
        self.assertEqual(before[1]["hebrew"], "בוקר טוב")

    def test_modified_segment_invalidates_only_its_speech_cache(self):
        before = self.segments
        after = self.dub.apply_review(before, "[00001|SPEAKER_00] שלום\n[00002|SPEAKER_01] משפט מתוקן", {"SPEAKER_00", "SPEAKER_01"})
        self.assertEqual(speech_key(self.dub.VERSION, before[0], "female_1"),
                         speech_key(self.dub.VERSION, after[0], "female_1"))
        self.assertNotEqual(speech_key(self.dub.VERSION, before[1], "male_1"),
                            speech_key(self.dub.VERSION, after[1], "male_1"))

    def test_review_rejects_partial_and_non_hebrew_segments(self):
        with self.assertRaises(ValueError):
            self.dub.apply_review(self.segments, "[00001|SPEAKER_00] שלום", {"SPEAKER_00", "SPEAKER_01"})
        with self.assertRaises(ValueError):
            self.dub.apply_review(self.segments, "[00001|SPEAKER_00] שלום\n[00002|SPEAKER_01] مرحبا", {"SPEAKER_00", "SPEAKER_01"})

    def test_ui_submits_text_to_dubbing_backend(self):
        tree = ast.parse(AGENT.read_text(encoding="utf-8"))
        page_node = next(n for n in tree.body if isinstance(n, ast.Assign) and
                         any(isinstance(target, ast.Name) and target.id == "PAGE" for target in n.targets))
        page = ast.literal_eval(page_node.value)
        self.assertIn("hebrew_text:hebrewText.value.trim()", page)
        self.assertIn("if(d.translation){hebrewText.value=d.translation", page)
        source = AGENT.read_text(encoding="utf-8")
        self.assertIn("data.get('hebrew_text'", source)
        self.assertIn("'--hebrew-override'", source)


if __name__ == "__main__":
    unittest.main()