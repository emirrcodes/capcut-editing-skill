"""Observable draft-editing invariants, using synthetic media/projects only."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "skills/capcut-editing/scripts"))
import capcut_tool as tool
import transcribe

loader = importlib.util.spec_from_file_location("skill_install", ROOT / "install.py")
installer = importlib.util.module_from_spec(loader)
loader.loader.exec_module(installer)


def audio(path: Path, portions: list[tuple[float, bool]]) -> None:
    with wave.open(str(path), "wb") as target:
        target.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        for length, tone in portions:
            target.writeframes(b"".join(struct.pack("<h", round(8000 * math.sin(2 * math.pi * 440 * i / 16000))) if tone else b"\0\0" for i in range(round(length * 16000))))


def draft(media: Path, durations=(1_000_000, 1_000_000), audio_only=False) -> dict:
    kind, bucket = ("audio", "audios") if audio_only else ("video", "videos")
    cursor = 0
    segments = []
    for index, length in enumerate(durations):
        segments.append({"id": f"segment-{index}", "material_id": "media", "extra_material_refs": ["speed"], "source_timerange": {"start": cursor, "duration": length}, "target_timerange": {"start": cursor, "duration": length}, "speed": 1.0, "reverse": False, "common_keyframes": [], "keyframe_refs": [], "render_index": 0})
        cursor += length
    return {"id": "synthetic-draft", "version": 360000, "duration": cursor, "tracks": [{"id": "primary", "type": kind, "segments": segments}], "materials": {bucket: [{"id": "media", "path": str(media), "type": kind}], "speeds": [{"id": "speed", "type": "speed", "speed": 1.0}], "texts": [], "material_animations": []}}


def project(root: Path, value: dict, alternate=False) -> Path:
    folder = root / "project"
    folder.mkdir()
    if alternate:
        mirrors = [folder / "draft_content.json"]
    else:
        timeline = folder / "Timelines/timeline-test"
        timeline.mkdir(parents=True)
        mirrors = [folder / "draft_info.json", timeline / "draft_info.json", folder / "template-2.tmp", timeline / "template-2.tmp"]
    for path in mirrors:
        path.write_bytes(tool.encoded(value))
    tool.write_json(folder / "draft_meta_info.json", {"draft_name": "test", "tm_duration": value["duration"], "duration": value["duration"], "unrelated": "preserve"})
    return folder


def transcript(crossing=True) -> dict:
    tokens = ["IŞIK", "İÇİN", "BUNU", "YAPIYORUZ.", "BU", "DİĞER", "KLİBE", "AİT."]
    starts = [0.05, 0.20, 0.40, 0.60, 0.90 if crossing else 1.05, 1.25, 1.45, 1.70]
    ends = [0.15, 0.35, 0.55, 0.75, 1.15 if crossing else 1.20, 1.40, 1.60, 1.90]
    return {"segments": [{"start": 0.05, "end": 1.90, "text": " ".join(tokens), "words": [{"word": word, "start": start, "end": end} for word, start, end in zip(tokens, starts, ends)]}]}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="capcut-skill-test-")
        self.root = Path(self.temporary.name)
        self.media = self.root / "source.wav"
        audio(self.media, [(2, True)])
        self.config = tool.settings()
        font = self.root / "test-font.ttf"
        font.write_bytes(b"test font path only")
        self.config["font_path"] = str(font)

    def tearDown(self):
        self.temporary.cleanup()

    def spec(self, work: Path) -> dict:
        return {"transcript_sha256": tool.read_json(work / "words.json")["transcript_sha256"], "ranges": [[1, 4], [5, 8]], "replacements": {}}

    def test_caption_cut_alignment_lowercase_and_relative_timing(self):
        value = draft(self.media)
        result = tool.insert_subtitles(value, transcript(), {"ranges": [[1, 4], [5, 8]]}, self.config)
        captions = result["tracks"][-1]["segments"]
        self.assertEqual(captions[0]["target_timerange"], {"start": 0, "duration": 1_000_000})
        self.assertEqual(captions[1]["target_timerange"], {"start": 1_000_000, "duration": 1_000_000})
        material = result["materials"]["texts"][1]
        self.assertEqual(material["words"]["start_time"][0], 0)
        self.assertEqual(material["recognize_text"], "bu diğer klibe ait")
        self.assertEqual(result["materials"]["texts"][0]["recognize_text"], "ışık için bunu yapıyoruz")
        self.assertEqual(tool.validate_subtitles(result, self.config)["subtitle_blocks"], 2)
        self.assertEqual(value["materials"]["texts"], [])

    def test_non_crossing_word_keeps_natural_start(self):
        for start, end in ((0.90, 0.95), (1.05, 1.20), (0.70, 1.10)):
            source = transcript()
            source["segments"][0]["words"][4].update({"start": start, "end": end})
            result = tool.insert_subtitles(draft(self.media), source, {"ranges": [[1, 4], [5, 8]]}, self.config)
            self.assertEqual(result["tracks"][-1]["segments"][1]["target_timerange"]["start"], round(start * 1e6))

    def test_user_text_and_shared_material_survive_rerun(self):
        value = draft(self.media)
        value["tracks"].append({"id": "user-track", "type": "text", "name": "my_title", "segments": [{"id": "user-segment", "material_id": "user-text", "extra_material_refs": [], "target_timerange": {"start": 0, "duration": 2_000_000}}]})
        value["materials"]["texts"].append({"id": "user-text", "type": "text", "content": "user title"})
        first = tool.insert_subtitles(value, transcript(), {"ranges": [[1, 4], [5, 8]]}, self.config)
        second = tool.insert_subtitles(first, transcript(), {"ranges": [[1, 4], [5, 8]]}, self.config)
        self.assertEqual([t for t in second["tracks"] if t.get("name") == "my_title"], [value["tracks"][1]])
        self.assertEqual(len([t for t in second["tracks"] if t.get("name") == "codex_subtitles"]), 1)
        self.assertEqual(len(second["materials"]["texts"]), 3)

    def test_invalid_ranges_and_replacement_word_count_refused(self):
        for spec in ({"ranges": [[1, 4], [4, 8]]}, {"ranges": [[1, 8]]}, {"ranges": [[1, 4]]}, {"ranges": [[1, 4], [5, 8]], "replacements": {"1": "one two three four five six seven"}}):
            with self.assertRaises(RuntimeError):
                tool.insert_subtitles(draft(self.media), transcript(), spec, self.config)

    def test_custom_case_punctuation_and_word_limit(self):
        self.config.update({"max_words": 8, "lowercase": False, "keep_terminal_punctuation": True})
        result = tool.insert_subtitles(draft(self.media), transcript(), {"ranges": [[1, 8]]}, self.config)
        self.assertIn("IŞIK", result["materials"]["texts"][0]["recognize_text"])
        self.assertTrue(result["materials"]["texts"][0]["recognize_text"].endswith("AİT."))

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_real_ffmpeg_silence_cut_audio_only_and_reference_resolution(self):
        audio(self.media, [(0.7, False), (0.9, True), (0.4, False), (0.8, True), (0.3, False)])
        value = draft(self.media, (3_100_000,), audio_only=True)
        result, report = tool.cut_silence(value, self.root, self.config)
        self.assertAlmostEqual(report["new_duration_us"] / 1e6, 1.7, places=3)
        self.assertAlmostEqual(report["removed_duration_us"] / 1e6, 1.4, places=3)
        self.assertEqual(len(result["tracks"][0]["segments"]), 2)
        self.assertEqual(tool.validate(result)["primary_type"], "audio")
        output = self.root / "cut.wav"
        tool.extract_audio(result, self.root, output, self.config)
        with wave.open(str(output)) as sample:
            self.assertAlmostEqual(sample.getnframes() / 16000, 1.7, places=3)
        self.assertEqual(value["duration"], 3_100_000)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_combined_prepare_preview_apply_and_restore(self):
        folder = project(self.root, draft(self.media))
        original = {p: p.read_bytes() for p in tool.source_paths(folder)}
        work = self.root / "work"
        with patch("transcribe.transcribe", return_value=transcript()):
            tool.prepare(folder, "both", work, self.config)
        self.assertEqual(original, {p: p.read_bytes() for p in original})
        tool.write_json(work / "subtitles.json", self.spec(work))
        prepared, _, _ = tool.build_result(work, None)
        self.assertTrue(tool.caption_preview(prepared)["captions"][1]["starts_at_clip_cut"])
        with patch.object(tool, "is_capcut_running", return_value=False):
            report = tool.apply(work)
        self.assertEqual(report["subtitle_blocks"], 2)
        self.assertFalse(work.exists())
        mirrors = tool.draft_paths(folder)
        self.assertEqual(len(mirrors), 4)
        self.assertEqual(len({p.read_bytes() for p in mirrors}), 1)
        self.assertEqual(tool.read_json(folder / "draft_meta_info.json")["unrelated"], "preserve")
        backup_content = {p: Path(str(p) + report["backup_suffix"]).read_bytes() for p in original}
        self.assertEqual(backup_content, original)
        # Deliberately inconsistent current mirrors must still be recoverable.
        mirrors[-1].write_bytes(b"interrupted write")
        with patch.object(tool, "is_capcut_running", return_value=False):
            tool.restore(folder, report["backup_suffix"])
        self.assertEqual(original, {p: p.read_bytes() for p in original})
        self.assertEqual(backup_content, {p: Path(str(p) + report["backup_suffix"]).read_bytes() for p in original})

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg not installed")
    def test_stale_project_or_subtitle_spec_refused_before_backup(self):
        folder = project(self.root, draft(self.media))
        work = self.root / "work"
        with patch("transcribe.transcribe", return_value=transcript()):
            tool.prepare(folder, "subtitles", work, self.config)
        spec = self.spec(work)
        spec["transcript_sha256"] = "wrong transcript"
        tool.write_json(work / "subtitles.json", spec)
        with self.assertRaisesRegex(RuntimeError, "another preparation"):
            tool.apply(work)
        tool.write_json(work / "subtitles.json", self.spec(work))
        meta = folder / "draft_meta_info.json"
        changed = tool.read_json(meta)
        changed["draft_name"] = "manual user edit"
        tool.write_json(meta, changed)
        with self.assertRaisesRegex(RuntimeError, "changed after preparation"):
            tool.apply(work)
        self.assertFalse(list(folder.rglob("*.bak")))

    def test_write_failure_rolls_back_all_copies(self):
        folder = project(self.root, draft(self.media))
        originals = {p: p.read_bytes() for p in tool.source_paths(folder)}
        expected = tool.snapshot(folder, list(originals))
        modified = draft(self.media)
        modified["name"] = "prepared update"
        payloads = {p: tool.encoded(modified) if p.name != "draft_meta_info.json" else originals[p] for p in originals}
        writer = tool.atomic_write
        counter = 0
        def fail_once(path, content):
            nonlocal counter
            counter += 1
            if counter == 2:
                raise OSError("simulated storage failure")
            writer(path, content)
        with patch.object(tool, "is_capcut_running", return_value=False), patch.object(tool, "atomic_write", side_effect=fail_once):
            with self.assertRaisesRegex(RuntimeError, "original files restored"):
                tool.commit(folder, payloads, expected, "edit")
        self.assertEqual(originals, {p: p.read_bytes() for p in originals})
        self.assertFalse((folder / ".capcut-editing.lock").exists())
        self.assertEqual(len(list(folder.rglob("*.bak"))), 5)

    def test_capcut_open_and_changed_layout_refused(self):
        folder = project(self.root, draft(self.media), alternate=True)
        paths = tool.source_paths(folder)
        expected = tool.snapshot(folder, paths)
        with patch.object(tool, "is_capcut_running", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "Close CapCut"):
                tool.commit(folder, {p: p.read_bytes() for p in paths}, expected, "edit")
        self.assertFalse(list(folder.rglob("*.bak")))
        (folder / "draft_info.json").write_bytes((folder / "draft_content.json").read_bytes())
        with self.assertRaisesRegex(RuntimeError, "changed after preparation"):
            tool.assert_snapshot(folder, expected)

    def test_supported_alternate_layout_and_name_resolution(self):
        folder = project(self.root, draft(self.media), alternate=True)
        self.assertEqual([p.name for p in tool.draft_paths(folder)], ["draft_content.json"])
        self.config["draft_root"] = str(self.root)
        self.assertEqual(tool.resolve_project("test", self.config), folder.resolve())

    def test_unsupported_tracks_and_speed_refused(self):
        value = draft(self.media)
        value["tracks"].append({"type": "audio", "segments": [{}]})
        with self.assertRaisesRegex(RuntimeError, "Other populated tracks"):
            tool.check_editable(value, "both")
        value = draft(self.media)
        value["tracks"][0]["segments"][0]["speed"] = 1.2
        with self.assertRaisesRegex(RuntimeError, "1.0x"):
            tool.check_editable(value, "subtitles")

    def test_mirror_disagreement_does_not_mutate(self):
        folder = project(self.root, draft(self.media))
        mirror = folder / "Timelines/timeline-test/draft_info.json"
        mirror.write_bytes(b'{"user_changed":true}')
        original = {p: p.read_bytes() for p in folder.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(RuntimeError, "copies differ"):
            tool.draft_paths(folder)
        self.assertEqual(original, {p: p.read_bytes() for p in original})

    def test_install_for_all_agents_and_preserve_previous_version(self):
        for agent, directory in installer.AGENTS.items():
            base = self.root / agent
            report = installer.install(agent, base)
            installed = base / directory / "skills/capcut-editing"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "scripts/capcut_tool.py").is_file())
            self.assertTrue((installed / "assets/subtitle-template.json").is_file())
            (installed / "user-note.txt").write_text("preserve my modification")
            with self.assertRaises(RuntimeError):
                installer.install(agent, base)
            update = installer.install(agent, base, replace=True)
            self.assertEqual((Path(update["previous_skill_backup"]) / "user-note.txt").read_text(), "preserve my modification")
            self.assertFalse((installed / "user-note.txt").exists())

    def test_windows_discovery_font_and_process_check(self):
        local = self.root / "LocalAppData"
        windows = self.root / "Windows"
        font = windows / "Fonts/arial.ttf"
        font.parent.mkdir(parents=True)
        font.write_bytes(b"test")
        self.config["font_path"] = None
        with patch.object(tool.platform, "system", return_value="Windows"), patch.dict(os.environ, {"LOCALAPPDATA": str(local), "WINDIR": str(windows)}):
            self.assertEqual(tool.default_roots()[0], local / "CapCut/User Data/Projects/com.lveditor.draft")
            self.assertEqual(tool.font_path(self.config), font.as_posix())
            with patch.object(tool, "run", return_value=types.SimpleNamespace(stdout='"CapCut.exe","123"\n')):
                self.assertTrue(tool.is_capcut_running())

    def test_faster_adapter_preserves_original_word_timestamps(self):
        sample = types.SimpleNamespace(start=0.1, end=0.4, text=" merhaba", compression_ratio=5.39, avg_logprob=-0.2, no_speech_prob=0.1, words=[types.SimpleNamespace(start=0.1, end=0.4, word=" merhaba")])
        mock_model = unittest.mock.Mock()
        mock_model.transcribe.return_value = (iter([sample]), types.SimpleNamespace(language="tr"))
        module = types.SimpleNamespace(WhisperModel=unittest.mock.Mock(return_value=mock_model))
        with patch.object(transcribe, "choose_backend", return_value="faster"), patch.dict(sys.modules, {"faster_whisper": module}):
            result = transcribe.transcribe(self.media, self.config, speech_review=True)
        self.assertEqual(result["segments"][0]["words"][0], {"start": 0.1, "end": 0.4, "word": " merhaba"})
        self.assertFalse(mock_model.transcribe.call_args.kwargs["vad_filter"])
        self.assertTrue(mock_model.transcribe.call_args.kwargs["word_timestamps"])
        self.assertEqual(result["segments"][0]["compression_ratio"], 5.39)
        self.assertFalse(mock_model.transcribe.call_args.kwargs["condition_on_previous_text"])
        self.assertEqual(mock_model.transcribe.call_args.kwargs["hallucination_silence_threshold"], 2.0)

    def test_packaged_template_contains_no_personal_content(self):
        asset = tool.read_json(ROOT / "skills/capcut-editing/assets/subtitle-template.json")
        serialized = json.dumps(asset)
        self.assertNotIn("/Users/", serialized)
        self.assertNotIn("recognize_task_id\": \"772", serialized)
        self.assertEqual(asset["text"]["recognize_text"], "")
        self.assertEqual(json.loads(asset["text"]["content"])["text"], "")
        self.assertEqual(asset["text"]["words"]["text"], [])

    def test_mlx_adapter_normalizes_timestamps_and_uses_turkish(self):
        source = transcript()
        source["segments"][0]["compression_ratio"] = 5.39
        module = types.SimpleNamespace(transcribe=unittest.mock.Mock(return_value=source))
        with patch.object(transcribe, "choose_backend", return_value="mlx"), patch.dict(sys.modules, {"mlx_whisper": module}):
            result = transcribe.transcribe(self.media, self.config, speech_review=True)
        self.assertEqual(result["segments"][0]["words"], transcript()["segments"][0]["words"])
        self.assertEqual(module.transcribe.call_args.kwargs["language"], "tr")
        self.assertTrue(module.transcribe.call_args.kwargs["word_timestamps"])
        self.assertEqual(result["segments"][0]["compression_ratio"], 5.39)
        self.assertEqual(module.transcribe.call_args.kwargs["hallucination_silence_threshold"], 2.0)

    def test_silence_merge_and_minimum_kept_slice(self):
        log = "silence_start: 0.05\nsilence_end: 0.30\nsilence_start: 0.40\nsilence_end: 0.70\n"
        with patch.object(tool, "run", return_value=types.SimpleNamespace(stderr=log)):
            spans = tool.detect_silence(self.media, 0, 1_000_000, self.config)
        self.assertEqual(spans, [(50_000, 700_000)])
        with patch.object(tool, "detect_silence", return_value=spans):
            result, _ = tool.cut_silence(draft(self.media, (1_000_000,)), self.root, self.config)
        self.assertEqual(result["duration"], 300_000)
        self.assertEqual(result["tracks"][0]["segments"][0]["source_timerange"], {"start": 700_000, "duration": 300_000})

    def test_work_directory_inside_project_refused_without_creation(self):
        folder = project(self.root, draft(self.media))
        work = folder / "nested-work"
        with self.assertRaisesRegex(RuntimeError, "outside the CapCut project"):
            tool.prepare(folder, "silence", work, self.config)
        self.assertFalse(work.exists())


if __name__ == "__main__":
    unittest.main()
