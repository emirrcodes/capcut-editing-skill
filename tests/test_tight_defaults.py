"""Default commands remove short pauses and retain their mode-specific safeguards."""
import copy
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from test_workflow import audio, draft, project, tool
from test_speech_words import segment


@unittest.skipUnless(tool.shutil.which("ffmpeg"), "FFmpeg not installed")
class TightDefaultWorkflowTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown

    def analysis(self):
        return {"method": "test-vad", "audio_duration_us": 2000000,
                "keep_ranges_us": [[0, 730000], [1270000, 2000000]],
                "speech_ranges_us": [[0, 700000], [1300000, 2000000]],
                "conservatively_protected_ranges_us": [], "gap_reviews": []}

    def test_unconfigured_speech_prepare_runs_word_pause_and_source_checks_without_captions(self):
        folder = project(self.root, draft(self.media, (2000000,)))
        work = self.root / "default-speech"
        original = {p: p.read_bytes() for p in tool.source_paths(folder)}
        words = {"segments": [segment(0, 2, [("merhaba", .1, .65), ("dünya", 1.35, 1.9)])]}
        candidate_words = {"segments": [segment(0, 1.46, [("merhaba", .1, .65), ("dünya", .81, 1.36)])]}
        def pause_review(audio_path, analysis, config, work_dir):
            analysis = copy.deepcopy(analysis)
            analysis["pause_review"] = {"method": "test-overlapping-contexts", "window_count": 2}
            tool.write_json(work_dir / "speech-pause-audit.json", analysis["pause_review"])
            return analysis
        with patch("speech_scan.analyze", return_value=self.analysis()), \
             patch("speech_words.transcribe", return_value=words) as word_engine, \
             patch("speech_pauses.review", side_effect=pause_review) as pause_engine, \
             patch("speech_verify.transcribe", return_value=candidate_words) as candidate_engine, \
             patch.object(tool, "detect_silence", side_effect=AssertionError("amplitude fallback")):
            report = tool.prepare(folder, "speech", work, tool.settings())
        self.assertEqual(word_engine.call_count, 1)
        self.assertEqual(pause_engine.call_count, 1)
        self.assertEqual(candidate_engine.call_count, 1)
        self.assertEqual(report["removed_duration_us"], 540000)
        self.assertEqual(report["cut_settings"]["speech_min_gap"], .08)
        self.assertEqual(report["cut_settings"]["speech_padding"], .03)
        self.assertEqual(report["cut_verification"]["unexpected_vad_supported_source_loss_us"], 0)
        self.assertTrue((work / "speech-pause-audit.json").is_file())
        self.assertTrue((work / "speech-cut-verification.json").is_file())
        self.assertNotIn("codex_subtitles", str(tool.read_json(work / "prepared.json")["tracks"]))
        self.assertFalse((work / "words.json").exists())
        self.assertEqual(original, {p: p.read_bytes() for p in original})

    def test_real_default_silence_cuts_120ms_pause_while_explicit_natural_preserves_it(self):
        audio(self.media, [(.5, True), (.12, False), (.5, True)])
        value = draft(self.media, (1120000,), audio_only=True)
        natural = tool.settings(tool.HERE.parent / "references/natural-pauses.config.json")
        strict, strict_report = tool.cut_silence(value, self.root, tool.settings())
        relaxed, _ = tool.cut_silence(value, self.root, natural)
        self.assertAlmostEqual(strict["duration"] / 1e6, 1.0, places=3)
        self.assertEqual(relaxed["duration"], 1120000)
        self.assertEqual(len(tool.primary_track(strict)["segments"]), 2)
        self.assertAlmostEqual(strict_report["removed_duration_us"] / 1e6, .12, places=3)
        self.assertEqual(value["duration"], 1120000)

    def test_default_silence_prepare_needs_no_speech_or_transcription(self):
        audio(self.media, [(.5, True), (.12, False), (.5, True)])
        folder = project(self.root, draft(self.media, (1120000,), audio_only=True))
        with patch("speech_scan.analyze", side_effect=AssertionError("VAD in silence mode")), \
             patch("transcribe.transcribe", side_effect=AssertionError("ASR in silence mode")):
            report = tool.prepare(folder, "silence", self.root / "default-silence", tool.settings())
        self.assertEqual(report["cut_settings"]["min_silence"], .08)
        self.assertEqual(report["cut_settings"]["noise_db"], -30)
        self.assertAlmostEqual(report["removed_duration_us"] / 1e6, .12, places=3)

    def test_missing_default_speech_transcription_stops_without_fallback_or_project_writes(self):
        folder = project(self.root, draft(self.media, (2000000,)))
        original = {p: p.read_bytes() for p in tool.source_paths(folder)}
        with patch("speech_scan.analyze", return_value=self.analysis()), \
             patch("speech_words.transcribe", side_effect=RuntimeError("local transcription missing")), \
             patch.object(tool, "detect_silence", side_effect=AssertionError("amplitude fallback")):
            with self.assertRaisesRegex(RuntimeError, "local transcription missing"):
                tool.prepare(folder, "speech", self.root / "missing-engine", tool.settings())
        self.assertEqual(original, {p: p.read_bytes() for p in original})
        self.assertFalse(list(folder.rglob("*.bak")))
