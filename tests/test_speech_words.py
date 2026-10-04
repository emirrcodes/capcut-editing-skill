"""ASR/VAD disagreement and independent hallucination rechecks."""
import unittest
from unittest.mock import patch
import wave

import test_workflow as fixtures
from test_workflow import audio, draft, project
import capcut_tool as tool
import speech_words


def segment(start, end, words, ratio=1.0):
    return {"start": start, "end": end, "compression_ratio": ratio,
            "words": [{"word": text, "start": left, "end": right} for text, left, right in words]}


class WordReviewTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown

    def analysis(self):
        return {"method": "silero-vad-with-gap-review", "audio_duration_us": 2_000_000,
                "keep_ranges_us": [[0, 500_000]], "speech_ranges_us": [[0, 500_000]],
                "conservatively_protected_ranges_us": [], "gap_reviews": []}

    def test_weak_word_missing_from_vad_is_kept_whole(self):
        words = [{"word": "quiet consonants", "start_us": 600_000, "end_us": 900_000}]
        result = speech_words.word_protection(words, [(0, 500_000)], 2_000_000)
        self.assertEqual(result, [(580_000, 920_000)])

    def test_long_inflated_word_timestamp_does_not_preserve_long_noise_gap(self):
        words = [{"word": "word", "start_us": 0, "end_us": 2_000_000}]
        result = speech_words.word_protection(words, [(0, 700_000), (1_300_000, 2_000_000)], 2_000_000)
        self.assertEqual(result, [(0, 720_000), (1_280_000, 2_000_000)])

    def test_short_intra_word_gap_is_preserved(self):
        words = [{"word": "word", "start_us": 0, "end_us": 800_000}]
        self.assertEqual(speech_words.word_protection(words, [(0, 300_000), (500_000, 800_000)], 2_000_000), [(0, 820_000)])

    def test_long_approximate_word_times_are_reported_for_audio_inspection(self):
        work = self.root / "long-word"
        work.mkdir()
        words = {"segments": [segment(0, 2, [("stretched", 0, 2)])]}
        with patch.object(speech_words, "transcribe", return_value=words):
            report = speech_words.review(self.media, self.analysis(), self.config, work)
        self.assertEqual(report["word_review"]["long_word_timing_ranges_us"], [[0, 2_000_000]])

    def test_compressed_repetition_is_rechecked_without_trusting_original_words(self):
        work = self.root / "word-review"
        work.mkdir()
        original = {"segments": [segment(0, .5, [("real", 0, .5)]), segment(1, 2, [("repeat", 1, 2)], 5.39)]}
        retry = {"segments": [segment(0, .6, [("last real word", .4, .6)])]}
        with patch.object(speech_words, "transcribe", side_effect=[original, retry]) as engine:
            report = speech_words.review(self.media, self.analysis(), self.config, work)
        self.assertEqual(report["word_review"]["independent_rechecks"], 1)
        self.assertEqual(report["word_review"]["trusted_word_count"], 2)
        self.assertTrue(all(end <= 1_220_000 for start, end in report["keep_ranges_us"]))
        self.assertTrue(all(call.kwargs["speech_review"] for call in engine.call_args_list))
        self.assertFalse((work / "speech-word-review.wav").exists())

    def test_unresolved_repetition_is_kept_for_inspection_with_bounded_retry(self):
        work = self.root / "uncertain"
        work.mkdir()
        suspect = {"segments": [segment(1, 2, [("repeat", 1, 2)], 5.39)]}
        retry = {"segments": [segment(.4, 1.4, [("repeat", .4, 1.4)], 5.39)]}
        with patch.object(speech_words, "transcribe", side_effect=[suspect, retry]) as engine:
            result = speech_words.review(self.media, self.analysis(), self.config, work)
        self.assertEqual(engine.call_count, 2)
        self.assertEqual(result["word_review"]["trusted_word_count"], 0)
        self.assertEqual(result["word_review"]["unresolved_kept_ranges_us"], [[1_000_000, 2_000_000]])
        self.assertIn([1_000_000, 2_000_000], result["keep_ranges_us"])

    @unittest.skipUnless(tool.shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_word_review_in_cut_mode_does_not_add_captions_and_cleans_transcripts(self):
        folder = project(self.root, draft(self.media, (2_000_000,)))
        self.config["speech_word_review"] = True
        work = self.root / "cut-only"
        words = {"segments": [segment(0, .5, [("real", 0, .5)]), segment(1, 1.3, [("weak", 1, 1.3)])]}
        with patch("speech_scan.analyze", return_value=self.analysis()), patch.object(speech_words, "transcribe", return_value=words):
            tool.prepare(folder, "speech", work, self.config)
        result, plan, _ = tool.build_result(work, None)
        self.assertFalse(any(track.get("type") == "text" for track in result["tracks"]))
        self.assertEqual(plan["report"]["word_review"]["trusted_word_count"], 2)
        with patch.object(tool, "is_capcut_running", return_value=False):
            tool.apply(work)
        self.assertFalse(work.exists())


if __name__ == "__main__":
    unittest.main()
