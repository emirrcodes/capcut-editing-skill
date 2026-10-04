"""Speech detection, gap protection, and mode isolation on synthetic projects."""
import unittest
from unittest.mock import patch
import wave

import test_workflow as fixtures
from test_workflow import draft, project, transcript
import capcut_tool as tool
import speech_scan


class SpeechWorkflowTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown
    spec = fixtures.WorkflowTests.spec

    def analysis(self):
        return {"method": "silero-vad-with-gap-review", "audio_duration_us": 2_000_000,
                "keep_ranges_us": [[0, 600_000], [1_200_000, 2_000_000]],
                "gap_reviews": [{"start_us": 600_000, "end_us": 1_200_000}],
                "conservatively_protected_ranges_us": []}

    @unittest.skipUnless(tool.shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_speech_cut_uses_vad_not_amplitude_or_transcription_and_restores(self):
        folder = project(self.root, draft(self.media, audio_only=True))
        original = {p: p.read_bytes() for p in tool.source_paths(folder)}
        work = self.root / "speech-work"
        self.config["font_path"] = "/missing/not-needed-for-cuts.ttf"
        with patch("speech_scan.analyze", return_value=self.analysis()) as detector, \
             patch.object(tool, "detect_silence", side_effect=AssertionError("amplitude fallback")), \
             patch("transcribe.transcribe", side_effect=AssertionError("unrequested captions")):
            report = tool.prepare(folder, "speech", work, self.config)
        self.assertEqual(detector.call_count, 1)
        self.assertEqual(report["removed_duration_us"], 600_000)
        self.assertFalse((work / "words.json").exists())
        self.assertEqual(original, {p: p.read_bytes() for p in original})
        result, _, _ = tool.build_result(work, None)
        self.assertEqual(result["duration"], 1_400_000)
        self.assertEqual([(s["source_timerange"]["start"], s["source_timerange"]["duration"]) for s in result["tracks"][0]["segments"]], [(0, 600_000), (1_200_000, 800_000)])
        with patch.object(tool, "is_capcut_running", return_value=False):
            applied = tool.apply(work)
            self.assertIn(".codex-speechcut-", applied["backup_suffix"])
            self.assertEqual(len({p.read_bytes() for p in tool.draft_paths(folder)}), 1)
            tool.restore(folder, applied["backup_suffix"])
        self.assertEqual(original, {p: p.read_bytes() for p in original})
        self.assertFalse(work.exists())

    @unittest.skipUnless(tool.shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_speech_subtitles_transcribes_new_timeline_and_keeps_caption_invariants(self):
        folder = project(self.root, draft(self.media, (2_000_000,)))
        work = self.root / "speech-caption-work"
        def current_transcript(path, config):
            with wave.open(str(path)) as source:
                self.assertAlmostEqual(source.getnframes() / 16000, 1.4, places=3)
            value = transcript()
            for segment in value["segments"]:
                segment["start"] *= 0.65
                segment["end"] *= 0.65
                for word in segment["words"]:
                    word["start"] *= 0.65
                    word["end"] *= 0.65
            return value
        with patch("speech_scan.analyze", return_value=self.analysis()), patch("transcribe.transcribe", side_effect=current_transcript):
            tool.prepare(folder, "speech-subtitles", work, self.config)
        tool.write_json(work / "subtitles.json", self.spec(work))
        with patch.object(tool, "is_capcut_running", return_value=False):
            report = tool.apply(work)
        self.assertEqual(report["subtitle_blocks"], 2)
        self.assertEqual(report["new_duration_us"], 1_400_000)
        self.assertFalse(work.exists())

    @unittest.skipUnless(tool.shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_missing_speech_detector_never_falls_back_or_writes_project(self):
        folder = project(self.root, draft(self.media))
        original = {p: p.read_bytes() for p in tool.source_paths(folder)}
        with patch("speech_scan.available", return_value=False), patch.object(tool, "detect_silence", side_effect=AssertionError("fallback")):
            with self.assertRaisesRegex(RuntimeError, "no amplitude-only fallback"):
                tool.prepare(folder, "speech", self.root / "failed-work", self.config)
        self.assertEqual(original, {p: p.read_bytes() for p in original})
        self.assertFalse(list(folder.rglob("*.bak")))


@unittest.skipUnless(speech_scan.available(), "Run setup.py to test the real speech detector")
class SpeechDetectorTests(unittest.TestCase):
    def setUp(self):
        import numpy as np
        self.np = np
        self.config = tool.settings()

    def test_sensitive_gap_review_preserves_weak_speech_and_word_padding(self):
        rate = speech_scan.RATE
        samples = self.np.full(3 * rate, 0.05, dtype=self.np.float32)
        responses = [[(int(.5 * rate), rate), (int(2.2 * rate), int(2.7 * rate))],
                     [], [], [(int(.8 * rate), rate)], [], [], []]
        with patch.object(speech_scan, "detect", side_effect=responses):
            report = speech_scan.analyze_samples(samples, self.config)
        self.assertIn([1_400_000, 1_600_000], report["conservatively_protected_ranges_us"])
        self.assertTrue(any(start <= 1_400_000 and end >= 1_600_000 for start, end in report["keep_ranges_us"]))
        self.assertEqual(report["keep_ranges_us"][0][0], 380_000)
        self.assertEqual(len(report["gap_reviews"]), 3)
        self.assertTrue(all(item["analysis_gain"] == 4 for item in report["gap_reviews"]))

    def test_short_natural_pauses_survive_and_no_speech_stops(self):
        samples = self.np.zeros(32000, dtype=self.np.float32)
        with patch.object(speech_scan, "detect", return_value=[(1600, 16000), (19000, 30400)]):
            report = speech_scan.analyze_samples(samples, self.config)
        self.assertEqual(report["keep_ranges_us"], [[0, 2_000_000]])
        with patch.object(speech_scan, "detect", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "No speech found after both"):
                speech_scan.analyze_samples(samples, self.config)

    def test_long_gaps_are_reviewed_with_overlapping_context(self):
        samples = self.np.zeros(35 * speech_scan.RATE, dtype=self.np.float32)
        with patch.object(speech_scan, "detect", side_effect=[[(0, 16000)], [], []]) as detector:
            report = speech_scan.analyze_samples(samples, self.config)
        self.assertEqual(len(report["gap_reviews"]), 2)
        self.assertLessEqual(len(detector.call_args_list[1].args[0]), round(30.8 * speech_scan.RATE))

    def test_real_bundled_vad_rejects_noise_above_silence_threshold(self):
        # Loud stationary noise is non-silent, but it is not speech.
        samples = self.np.random.default_rng(42).normal(0, 0.10, 4 * speech_scan.RATE).astype(self.np.float32)
        self.assertGreater(float(self.np.sqrt(self.np.mean(samples ** 2))), 10 ** (-30 / 20))
        self.assertEqual(speech_scan.detect(samples, self.config["speech_threshold"], self.config), [])
        with self.assertRaisesRegex(RuntimeError, "No speech found after both"):
            speech_scan.analyze_samples(samples, self.config)


if __name__ == "__main__":
    unittest.main()
