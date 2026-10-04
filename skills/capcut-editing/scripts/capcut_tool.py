#!/usr/bin/env python3
"""Portable, staged CapCut draft editing. No GUI automation or export."""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

from draft_primitives import (
    apply_timeline_keep_ranges, atomic_write, fresh_id,
    remove_previous_codex_subtitles, resolve_draft_media_path,
    subtitle_lower, turkish_lower, word_timing_payload, wrap_display_text,
    MIN_CLIP_US, protect_cut_boundaries, validate_cut_fragments,
)

HERE = Path(__file__).resolve().parent
DEFAULTS = {
    "draft_root": None, "ffmpeg": "ffmpeg", "language": "tr",
    "backend": "auto", "model": None, "device": "cpu",
    "noise_db": -30.0, "min_silence": 0.25, "merge_gap": 0.12,
    "min_keep": 0.10, "max_words": 6, "lowercase": True,
    "keep_terminal_punctuation": False, "font_path": None,
    "font_size": 10.0, "color": [1.0, 1.0, 1.0],
    "stroke_color": [0.0, 0.0, 0.0], "stroke_width": 0.06,
    "caption_y": 0.58,
    "speech_threshold": 0.5, "speech_review_threshold": 0.35,
    "speech_min_duration": 0.10, "speech_min_gap": 0.30,
    "speech_padding": 0.12, "speech_review_context": 0.40,
    "speech_review_window": 30.0, "speech_review_max_gain": 4.0,
    "speech_word_review": False, "speech_verify_cut": False, "speech_pause_review": False, "speech_reviewed_gaps": None,
}
MODES = ("silence", "speech", "subtitles", "both", "speech-subtitles")
CUT_MODES = {"silence", "speech", "both", "speech-subtitles"}
CAPTION_MODES = {"subtitles", "both", "speech-subtitles"}
SILENCE_RE = re.compile(r"silence_(start|end):\s*(-?\d+(?:\.\d+)?)")
WORK_MARKER = ".capcut-editing-work.json"


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"Cannot read JSON: {path}. Encrypted/binary drafts are unsupported.") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected a JSON object: {path}")
    return value


def encoded(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def write_json(path: Path, value: dict) -> None:
    atomic_write(path, encoded(value))


def settings(path: Path | None = None) -> dict:
    config = copy.deepcopy(DEFAULTS)
    if path:
        overrides = read_json(path)
        unknown = set(overrides) - set(DEFAULTS)
        if unknown:
            raise RuntimeError(f"Unknown settings: {sorted(unknown)}")
        config.update(overrides)
    return validate_settings(config)


def validate_settings(config: dict) -> dict:
    if config["backend"] not in {"auto", "mlx", "faster"}:
        raise RuntimeError("backend must be auto, mlx, or faster")
    if config["device"] not in {"cpu", "cuda"}:
        raise RuntimeError("device must be cpu or cuda")
    if not isinstance(config["max_words"], int) or isinstance(config["max_words"], bool) or not 1 <= config["max_words"] <= 20:
        raise RuntimeError("max_words must be an integer from 1 to 20 (default 6)")
    for key in ("noise_db", "min_silence", "merge_gap", "min_keep", "font_size", "stroke_width", "caption_y"):
        if not isinstance(config[key], (int, float)) or not math.isfinite(config[key]):
            raise RuntimeError(f"Invalid numeric setting: {key}")
    if config["min_silence"] <= 0 or config["min_keep"] <= 0 or config["merge_gap"] < 0 or config["font_size"] <= 0 or config["stroke_width"] < 0:
        raise RuntimeError("Durations/font size must be positive; merge gap/stroke must be nonnegative")
    for key in ("lowercase", "keep_terminal_punctuation", "speech_word_review", "speech_verify_cut", "speech_pause_review"):
        if not isinstance(config[key], bool):
            raise RuntimeError(f"{key} must be true or false")
    reviewed = config["speech_reviewed_gaps"]
    if reviewed is not None:
        if not isinstance(reviewed, dict) or set(reviewed) != {"draft_sha256", "ranges_us", "basis"} or reviewed["basis"] != "user-confirmed" or not isinstance(reviewed["draft_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", reviewed["draft_sha256"]):
            raise RuntimeError("Reviewed gaps require a current draft hash, explicit user-confirmed basis, and ranges_us")
        if not isinstance(reviewed["ranges_us"], list) or not reviewed["ranges_us"]:
            raise RuntimeError("Reviewed gap ranges must be nonempty")
        end = 0
        for span in reviewed["ranges_us"]:
            if not isinstance(span, list) or len(span) != 2 or any(type(x) is not int for x in span) or not end <= span[0] < span[1]:
                raise RuntimeError("Reviewed gaps must be ordered, non-overlapping integer microsecond ranges")
            end = span[1]
    if config["speech_verify_cut"] and not config["speech_word_review"]:
        raise RuntimeError("speech_verify_cut requires speech_word_review")
    if config["speech_pause_review"] and not (config["speech_word_review"] and config["speech_verify_cut"]):
        raise RuntimeError("speech_pause_review requires speech_word_review and speech_verify_cut")
    for key in ("color", "stroke_color"):
        if not isinstance(config[key], list) or len(config[key]) != 3 or any(not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1 for x in config[key]):
            raise RuntimeError(f"{key} must contain three color components in [0, 1]")
    if not isinstance(config["language"], str) or not config["language"]:
        raise RuntimeError("language must be a nonempty language code")
    for key in ("speech_threshold", "speech_review_threshold", "speech_min_duration", "speech_min_gap", "speech_padding", "speech_review_context", "speech_review_window", "speech_review_max_gain"):
        if type(config[key]) not in (int, float) or not math.isfinite(config[key]):
            raise RuntimeError(f"Invalid numeric speech setting: {key}")
    if not 0 < config["speech_review_threshold"] <= config["speech_threshold"] < 1:
        raise RuntimeError("Speech review threshold must be <= primary speech threshold, both between 0 and 1")
    if config["speech_min_duration"] <= 0 or config["speech_min_gap"] <= 0 or config["speech_padding"] < 0 or config["speech_review_context"] < 0 or config["speech_review_window"] < 1 or config["speech_review_max_gain"] < 1:
        raise RuntimeError("Invalid speech duration, context, review window, padding, or gain")
    return config


def default_roots() -> list[Path]:
    if platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        return [local / "CapCut/User Data/Projects/com.lveditor.draft"]
    return [Path.home() / "Movies/CapCut/User Data/Projects/com.lveditor.draft"]


def resolve_project(value: str, config: dict) -> Path:
    direct = Path(value).expanduser()
    if direct.is_dir():
        return direct.resolve()
    roots = [Path(config["draft_root"]).expanduser()] if config["draft_root"] else default_roots()
    matches = []
    for root in roots:
        if not root.is_dir():
            continue
        for folder in root.iterdir():
            if not folder.is_dir():
                continue
            names = [folder.name]
            meta = folder / "draft_meta_info.json"
            if meta.is_file():
                try:
                    names.append(str(read_json(meta).get("draft_name", "")))
                except RuntimeError:
                    pass
            if any(turkish_lower(name) == turkish_lower(value) for name in names):
                matches.append(folder.resolve())
    matches = sorted(set(matches))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one exact project match, found {len(matches)}. Supply its folder path or configure draft_root.")
    return matches[0]


def draft_paths(project: Path, strict: bool = True) -> list[Path]:
    main = [project / name for name in ("draft_info.json", "draft_content.json") if (project / name).is_file()]
    if not main:
        raise RuntimeError("No draft_info.json or draft_content.json found")
    candidates = list(main)
    timelines = project / "Timelines"
    if timelines.is_dir():
        folders = [p for p in timelines.iterdir() if p.is_dir() and any((p / n).is_file() for n in ("draft_info.json", "draft_content.json"))]
        if len(folders) > 1:
            raise RuntimeError("Multiple timelines are unsupported; select a single-timeline project")
        if folders:
            candidates.extend(folders[0] / n for n in ("draft_info.json", "draft_content.json") if (folders[0] / n).is_file())
    for folder in dict.fromkeys(p.parent for p in candidates):
        template = folder / "template-2.tmp"
        if template.is_file():
            if strict:
                candidate = read_json(template)
                if "tracks" not in candidate or "materials" not in candidate:
                    raise RuntimeError(f"Unrecognized template-2.tmp layout: {template}")
            candidates.append(template)
    for path in candidates:
        if path.is_symlink() or not path.resolve().is_relative_to(project.resolve()):
            raise RuntimeError(f"Draft mirrors must be regular files inside the project: {path}")
    if strict:
        payloads = [p.read_bytes() for p in candidates]
        if len(set(payloads)) != 1:
            raise RuntimeError("Draft copies differ. Close the project in CapCut, then inspect again; do not guess which copy is current.")
        draft = read_json(main[0])
        if not isinstance(draft.get("tracks"), list) or not isinstance(draft.get("materials"), dict):
            raise RuntimeError("Unsupported draft schema: tracks/materials are missing")
    return candidates


def snapshot(project: Path, paths: list[Path]) -> dict:
    result = {}
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"Not a regular project file: {path}")
        payload = path.read_bytes()
        result[path.relative_to(project).as_posix()] = {"sha256": hashlib.sha256(payload).hexdigest(), "size": len(payload)}
    return result


def source_paths(project: Path, strict: bool = True) -> list[Path]:
    paths = draft_paths(project, strict)
    meta = project / "draft_meta_info.json"
    if meta.is_file():
        paths.append(meta)
    return paths


def assert_snapshot(project: Path, expected: dict) -> None:
    if snapshot(project, source_paths(project, strict=False)) != expected:
        raise RuntimeError("The project changed after preparation. Re-read and prepare the current timeline again.")


def primary_track(draft: dict) -> dict:
    videos = [t for t in draft["tracks"] if t.get("type") == "video" and t.get("segments")]
    tracks = videos or [t for t in draft["tracks"] if t.get("type") == "audio" and t.get("segments")]
    if len(tracks) != 1:
        raise RuntimeError("Expected one populated video track, or one audio-only track")
    return tracks[0]


def validate(draft: dict) -> dict:
    primary = primary_track(draft)
    ids = [m["id"] for items in draft["materials"].values() if isinstance(items, list) for m in items if isinstance(m, dict) and isinstance(m.get("id"), str)]
    if len(ids) != len(set(ids)):
        raise RuntimeError("Duplicate material IDs")
    known = set(ids)
    segment_ids = set()
    primary_end = 0
    duration = draft.get("duration")
    if not isinstance(duration, int) or duration <= 0:
        raise RuntimeError("Timeline must have a positive integer duration")
    for track in draft["tracks"]:
        end = 0
        for segment in track.get("segments", []):
            segment_id = segment.get("id")
            if not segment_id or segment_id in segment_ids:
                raise RuntimeError("Missing/duplicate segment ID")
            segment_ids.add(segment_id)
            target = segment.get("target_timerange") or {}
            start, length = target.get("start"), target.get("duration")
            if not isinstance(start, int) or not isinstance(length, int) or start < end or length <= 0 or start + length > duration:
                raise RuntimeError(f"Invalid/overlapping range: {segment_id}")
            if track is primary and start != end:
                raise RuntimeError("Primary video/audio track has a gap")
            end = start + length
            for ref in [segment.get("material_id"), *segment.get("extra_material_refs", [])]:
                if ref not in known:
                    raise RuntimeError(f"Unresolved material reference: {ref}")
        if track is primary:
            primary_end = end
    if primary_end != duration:
        raise RuntimeError("Timeline duration does not match the primary track end")
    return {"duration_us": duration, "primary_type": primary["type"], "segments": len(primary["segments"])}


def check_editable(draft: dict, mode: str) -> None:
    primary = primary_track(draft)
    for segment in primary["segments"]:
        source = segment.get("source_timerange") or {}
        target = segment["target_timerange"]
        if not isinstance(source.get("duration"), int) or abs(source["duration"] - target["duration"]) > 1 or abs(float(segment.get("speed", 1)) - 1) > 1e-9 or segment.get("reverse"):
            raise RuntimeError("Only forward 1.0x source clips are supported")
        if not isinstance(source.get("start"), int) or source["start"] < 0:
            raise RuntimeError("Missing/invalid source range")
        if segment.get("common_keyframes") or segment.get("keyframe_refs"):
            raise RuntimeError("Animated/keyframed primary clips are unsupported")
    if mode in CUT_MODES:
        others = [t for t in draft["tracks"] if t is not primary and t.get("segments") and not (t.get("type") == "text" and t.get("name") == "codex_subtitles")]
        if others:
            raise RuntimeError("Cutting supports a single media track with optional previous codex_subtitles. Other populated tracks are preserved by refusing the cut.")
        if any(draft["materials"].get(key) for key in ("transitions", "video_transitions")):
            raise RuntimeError("Remove existing transitions before cutting")


def media_for(draft: dict, project: Path, segment: dict) -> Path:
    track = primary_track(draft)
    bucket = "videos" if track["type"] == "video" else "audios"
    item = next((m for m in draft["materials"].get(bucket, []) if m.get("id") == segment["material_id"]), None)
    if not item or not isinstance(item.get("path"), str):
        raise RuntimeError("Missing media path")
    path = resolve_draft_media_path(project, item["path"])
    if not path.is_file():
        raise RuntimeError(f"Missing media: {path}")
    return path


def run(command: list[str]) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except OSError as exc:
        raise RuntimeError(f"Cannot run {command[0]}; check dependencies") from exc
    if result.returncode:
        raise RuntimeError(f"{command[0]} failed:\n{result.stderr[-4000:]}")
    return result


def detect_silence(media: Path, start: int, duration: int, config: dict) -> list[tuple[int, int]]:
    output = run([config["ffmpeg"], "-hide_banner", "-nostats", "-ss", f"{start/1e6:.6f}", "-t", f"{duration/1e6:.6f}", "-i", str(media), "-map", "0:a:0", "-vn", "-af", f"silencedetect=noise={config['noise_db']}dB:d={config['min_silence']}", "-f", "null", "-"])
    spans = []
    opened = None
    for kind, value in SILENCE_RE.findall(output.stderr):
        point = max(0, min(duration, round(float(value) * 1e6)))
        if kind == "start":
            opened = point
        elif opened is not None:
            if point > opened:
                spans.append((opened, point))
            opened = None
    if opened is not None and opened < duration:
        spans.append((opened, duration))
    merged = []
    for start, end in spans:
        if merged and start - merged[-1][1] <= round(config["merge_gap"] * 1e6):
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [tuple(span) for span in merged]


def cut_silence(draft: dict, project: Path, config: dict) -> tuple[dict, dict]:
    output = copy.deepcopy(draft)
    remove_previous_codex_subtitles(output)
    keep = []
    removed = 0
    for segment in primary_track(output)["segments"]:
        source = segment["source_timerange"]
        if segment["target_timerange"]["duration"] < MIN_CLIP_US:
            origin = segment["target_timerange"]["start"]
            keep.append((origin, origin + segment["target_timerange"]["duration"]))
            continue
        silences = detect_silence(media_for(output, project, segment), source["start"], source["duration"], config)
        removed += len(silences)
        cursor = 0
        for start, end in [*silences, (source["duration"], source["duration"])]:
            if start - cursor >= round(config["min_keep"] * 1e6):
                origin = segment["target_timerange"]["start"]
                keep.append((origin + cursor, origin + start))
            cursor = max(cursor, end)
    if not keep:
        raise RuntimeError("All audio is below the silence threshold. No files were changed; adjust settings.")
    keep, boundary_protection = protect_cut_boundaries(output, keep)
    apply_timeline_keep_ranges(output, keep)
    validate(output)
    validate_cut_fragments(output, draft)
    return output, {"old_duration_us": draft["duration"], "new_duration_us": output["duration"], "removed_duration_us": draft["duration"] - output["duration"], "detected_silence_ranges": removed, "boundary_protection_ranges_us": boundary_protection}


def extract_audio(draft: dict, project: Path, output: Path, config: dict) -> list[dict]:
    # Render each current source slice separately: bounded FFmpeg command sizes,
    # repeated source support, and identical behavior on Windows and macOS.
    # CapCut can round a media tail up to a video frame. Normalize each
    # individual slice, so a short tail cannot shift every later clip's words.
    tolerance = 0.02
    fps = draft.get("fps")
    if primary_track(draft)["type"] == "video" and type(fps) in (int, float) and math.isfinite(fps) and fps > 0:
        tolerance = max(tolerance, min(0.05, 1 / fps))
    adjustments = []
    with tempfile.TemporaryDirectory(prefix="capcut-audio-") as temp:
        parts = []
        for index, segment in enumerate(primary_track(draft)["segments"]):
            source = segment["source_timerange"]
            part = Path(temp) / f"{index:06d}.wav"
            run([config["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{source['start']/1e6:.6f}", "-t", f"{source['duration']/1e6:.6f}", "-i", str(media_for(draft, project, segment)), "-map", "0:a:0", "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(part)])
            parts.append(part)
        import wave
        with wave.open(str(output), "wb") as destination:
            destination.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            for index, (part, segment) in enumerate(zip(parts, primary_track(draft)["segments"])):
                expected = round(segment["source_timerange"]["duration"] / 1e6 * 16000)
                with wave.open(str(part), "rb") as source:
                    actual = source.getnframes()
                    if actual == 0 or abs(expected - actual) > math.ceil(tolerance * 16000):
                        raise RuntimeError("Rendered audio duration differs from the timeline; source audio may be truncated")
                    frames = source.readframes(min(actual, expected))
                if actual < expected:
                    frames += b"\0\0" * (expected - actual)
                destination.writeframes(frames)
                if actual != expected:
                    adjustments.append({"segment_index": index, "expected_samples": expected,
                                        "decoded_samples": actual, "tail_padding_samples": max(0, expected - actual),
                                        "tail_trim_samples": max(0, actual - expected)})
        with wave.open(str(output), "rb") as rendered:
            actual = rendered.getnframes() / rendered.getframerate()
        tolerance = max(0.02, len(parts) / 16000)
        if abs(actual - draft["duration"] / 1e6) > tolerance:
            raise RuntimeError("Rendered audio duration differs from the timeline; source audio may be truncated")
    return adjustments


def cut_speech(draft: dict, project: Path, work: Path, config: dict) -> tuple[dict, dict]:
    from speech_scan import analyze, merge
    original_audio = work / "speech-original.wav"
    audio_alignment = extract_audio(draft, project, original_audio, config)
    analysis = analyze(original_audio, config)
    analysis["audio_alignment"] = audio_alignment
    if config["speech_word_review"]:
        from speech_words import review
        analysis = review(original_audio, analysis, config, work)
    if config["speech_pause_review"]:
        from speech_pauses import review as review_pauses
        analysis = review_pauses(original_audio, analysis, config, work)
    # Rendered PCM is rounded to audio samples; clamp the final microseconds
    # to the actual timeline rather than inventing a gap at its end.
    keep = merge([tuple(span) for span in analysis["keep_ranges_us"]], draft["duration"])
    if not keep:
        raise RuntimeError("Speech scanning produced no kept ranges")
    if analysis["audio_duration_us"] - keep[-1][1] <= 1000:
        keep[-1] = (keep[-1][0], draft["duration"])
    reviewed = config["speech_reviewed_gaps"]
    if reviewed:
        from speech_scan import gaps
        approved = reviewed["ranges_us"]
        allowed = gaps([tuple(span) for span in approved], draft["duration"])
        keep = merge([(max(left, start), min(right, end)) for left, right in keep for start, end in allowed], draft["duration"])
        if not keep:
            raise RuntimeError("Reviewed gaps would delete the whole timeline")
        analysis["reviewed_non_speech_ranges_us"] = approved
        analysis["reviewed_gap_basis"] = "user-confirmed"
    keep, boundary_protection = protect_cut_boundaries(draft, keep)
    analysis["keep_ranges_us"] = [list(span) for span in keep]
    from speech_scan import gaps
    analysis["removed_ranges_us"] = [list(span) for span in gaps(keep, draft["duration"])]
    analysis["boundary_protection_ranges_us"] = boundary_protection
    write_json(work / "speech-analysis.json", analysis)
    output = copy.deepcopy(draft)
    remove_previous_codex_subtitles(output)
    apply_timeline_keep_ranges(output, keep)
    validate(output)
    validate_cut_fragments(output, draft)
    if config["speech_verify_cut"]:
        from speech_verify import verify
        candidate_audio = work / "speech-candidate.wav"
        analysis["candidate_audio_alignment"] = extract_audio(output, project, candidate_audio, config)
        analysis["cut_verification"] = verify(draft, output, project, analysis, candidate_audio, config, work)
        write_json(work / "speech-analysis.json", analysis)
    return output, {"old_duration_us": draft["duration"], "new_duration_us": output["duration"], "removed_duration_us": draft["duration"] - output["duration"], "speech_detection": analysis["method"], "reviewed_gap_windows": len(analysis["gap_reviews"]), "conservatively_protected_regions": len(analysis["conservatively_protected_ranges_us"]), "boundary_protection_ranges_us": boundary_protection, "word_review": analysis.get("word_review"), "pause_review": analysis.get("pause_review"), "cut_verification": analysis.get("cut_verification")}


def font_path(config: dict) -> str:
    if config["font_path"]:
        path = Path(config["font_path"]).expanduser()
        if not path.is_file():
            raise RuntimeError("Configured font_path does not exist")
        return path.as_posix()
    paths = [Path("/Applications/CapCut.app/Contents/Resources/Font/SystemFont/en.ttf"), Path("/System/Library/Fonts/Supplemental/Arial.ttf")]
    if platform.system() == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local")))
        paths = sorted((local / "CapCut/Apps").glob("*/Resources/Font/SystemFont/en.ttf"), reverse=True)
        paths.append(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts/arial.ttf")
    for path in paths:
        if path.is_file():
            return path.as_posix()
    raise RuntimeError("No usable font found. Configure font_path to an installed .ttf file")


def language_tag(value: str) -> str:
    return {"tr": "tr-TR", "en": "en-US"}.get(value, value)


def cleaned(text: str, config: dict) -> str:
    text = text.strip()
    if not config["keep_terminal_punctuation"]:
        text = text.strip(".,!?;:…\"“”()[]{}")
    if config["lowercase"]:
        text = subtitle_lower(text, config["language"])
    return text


def transcript_words(transcript: dict, duration: int) -> list[dict]:
    words = []
    previous = -1.0
    for segment in transcript.get("segments", []):
        for word in segment.get("words", []):
            start, end = float(word["start"]), float(word["end"])
            token = str(word["word"]).strip()
            if not token or not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start or start < previous or start >= duration / 1e6 or end > duration / 1e6 + 0.25:
                raise RuntimeError("Invalid/nonmonotonic word timestamps; re-transcribe the current timeline")
            words.append({"word": token, "start": start, "end": min(end, duration / 1e6)})
            previous = start
    if not words:
        raise RuntimeError("No timestamped speech words found; no project files were changed")
    return words


def caption_starts(blocks: list[list[dict]], draft: dict) -> list[int]:
    from subtitle_boundaries import boundary_plan
    return boundary_plan(blocks,draft)["starts_us"]


def subtitle_blocks(transcript: dict, spec: dict, config: dict, duration: int) -> list[list[dict]]:
    words = transcript_words(transcript, duration)
    ranges = spec.get("ranges", [])
    replacements = spec.get("replacements", {})
    if any(not str(index).isdigit() or not 1 <= int(index) <= len(words) or not isinstance(text, str) for index, text in replacements.items()):
        raise RuntimeError("Invalid word replacements")
    blocks = []
    cursor = 1
    for span in ranges:
        if not isinstance(span, list) or len(span) != 2 or any(type(x) is not int for x in span):
            raise RuntimeError("ranges must be lists of inclusive 1-based word indexes")
        start, end = span
        if start != cursor or end < start or end > len(words):
            raise RuntimeError("Subtitle blocks must cover all words exactly once, in order")
        block = copy.deepcopy(words[start - 1:end])
        for offset, word in enumerate(block, start):
            word["clean_word"] = cleaned(replacements.get(str(offset), word["word"]), config)
            if not word["clean_word"]:
                raise RuntimeError("A cleaned subtitle word became empty; revise the transcript")
        text = " ".join(w["clean_word"] for w in block)
        if len(text.split()) > config["max_words"]:
            raise RuntimeError("Subtitle exceeds configured max_words")
        blocks.append(block)
        cursor = end + 1
    if cursor != len(words) + 1 or not blocks:
        raise RuntimeError("Subtitle ranges must cover the entire transcript")
    return blocks


def insert_subtitles(draft: dict, transcript: dict, spec: dict, config: dict) -> dict:
    blocks=subtitle_blocks(transcript,spec,config,draft["duration"])
    result = copy.deepcopy(draft)
    remove_previous_codex_subtitles(result)
    template = read_json(HERE.parent / "assets/subtitle-template.json")
    path = font_path(config)
    starts = caption_starts(blocks, result)
    track = copy.deepcopy(template["track"])
    track["id"] = fresh_id()
    render_base = max([int(s.get("render_index", 0)) for t in result["tracks"] for s in t.get("segments", [])] + [13998]) + 2
    track_index = max([int(s.get("track_render_index", 0)) for t in result["tracks"] for s in t.get("segments", [])] + [0]) + 1
    for index, block in enumerate(blocks):
        start = starts[index]
        end = starts[index + 1] if index + 1 < len(starts) else result["duration"]
        text = " ".join(w["clean_word"] for w in block)
        material = copy.deepcopy(template["text"])
        material.update({"id": fresh_id(), "type": "subtitle", "recognize_text": text, "language": language_tag(config["language"]), "font_path": path, "font_size": config["font_size"]})
        material.update({"text_color": "#" + "".join(f"{round(x*255):02x}" for x in config["color"]), "border_color": "#" + "".join(f"{round(x*255):02x}" for x in config["stroke_color"]), "border_width": config["stroke_width"]})
        for field in ("content", "base_content"):
            content = json.loads(material[field])
            content["text"] = wrap_display_text(text) if field == "content" else text
            for style in content.get("styles", []):
                style.update({"range": [0, len(content["text"])], "size": config["font_size"], "font": {"id": "", "path": path}})
                style["fill"] = {"content": {"render_type": "solid", "solid": {"color": config["color"]}}}
                style["strokes"] = [{"width": config["stroke_width"], "mode": 0, "content": {"render_type": "solid", "solid": {"color": config["stroke_color"]}}}]
            material[field] = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
        timings = word_timing_payload(block, start / 1e6)
        length_ms = (end - start) // 1000
        timings["start_time"] = [min(t, length_ms) for t in timings["start_time"]]
        timings["end_time"] = [min(t, length_ms) for t in timings["end_time"]]
        material["words"] = timings
        material["current_words"] = copy.deepcopy(timings)
        animation = copy.deepcopy(template["animation"])
        animation["id"] = fresh_id()
        result["materials"].setdefault("texts", []).append(material)
        result["materials"].setdefault("material_animations", []).append(animation)
        segment = copy.deepcopy(template["segment"])
        segment.update({"id": fresh_id(), "material_id": material["id"], "extra_material_refs": [animation["id"]], "target_timerange": {"start": start, "duration": end - start}, "render_index": render_base + index * 2, "track_render_index": track_index})
        segment["clip"]["transform"]["y"] = config["caption_y"]
        track["segments"].append(segment)
    result["tracks"].append(track)
    validate(result)
    validate_subtitles(result, config, source_blocks=blocks)
    return result


def validate_subtitles(draft: dict, config: dict, source_blocks=None) -> dict:
    tracks = [t for t in draft["tracks"] if t.get("type") == "text" and t.get("name") == "codex_subtitles"]
    if len(tracks) != 1 or not tracks[0].get("segments"):
        raise RuntimeError("Expected exactly one populated codex_subtitles track")
    materials = {m["id"]: m for m in draft["materials"]["texts"]}
    cursor = 0
    for segment in tracks[0]["segments"]:
        target = segment["target_timerange"]
        if target["start"] != cursor or target["duration"] <= 0:
            raise RuntimeError("Subtitle gap/overlap")
        cursor += target["duration"]
        item = materials[segment["material_id"]]
        text = item["recognize_text"]
        if item["type"] != "subtitle" or len(text.split()) > config["max_words"]:
            raise RuntimeError("Invalid subtitle material or word count")
        if config["lowercase"] and text != subtitle_lower(text, config["language"]):
            raise RuntimeError("Subtitle is not lowercase")
        for field in ("content", "base_content"):
            if json.loads(item[field])["text"].split() != text.split():
                raise RuntimeError("Subtitle content fields disagree")
        for field in ("words", "current_words"):
            payload = item[field]
            if not len(payload["start_time"]) == len(payload["end_time"]) == len(payload["text"]):
                raise RuntimeError("Invalid subtitle word timing arrays")
            if any(not 0 <= left <= right <= target["duration"] // 1000 for left, right in zip(payload["start_time"], payload["end_time"])):
                raise RuntimeError("Subtitle word timing lies outside its block")
    if cursor != draft["duration"]:
        raise RuntimeError("Subtitles do not cover 0 through project duration")
    from subtitle_boundaries import validate_boundaries
    boundary_report=validate_boundaries(draft,source_blocks)
    return {"subtitle_blocks": len(tracks[0]["segments"]), "duration_us": cursor, **boundary_report}


def caption_preview(draft: dict) -> dict:
    cuts = [s["target_timerange"]["start"] for s in primary_track(draft)["segments"][1:]]
    texts = {m["id"]: m for m in draft["materials"].get("texts", [])}
    track = next(t for t in draft["tracks"] if t.get("type") == "text" and t.get("name") == "codex_subtitles")
    return {"clip_cuts_us": cuts, "captions": [{"text": texts[s["material_id"]]["recognize_text"], "start_us": s["target_timerange"]["start"], "end_us": s["target_timerange"]["start"] + s["target_timerange"]["duration"], "starts_at_clip_cut": s["target_timerange"]["start"] in cuts} for s in track["segments"]]}


def is_capcut_running() -> bool:
    if platform.system() == "Windows":
        import csv
        result = run(["tasklist", "/FO", "CSV", "/NH"])
        return any(row and row[0].lower() == "capcut.exe" for row in csv.reader(result.stdout.splitlines()))
    result = subprocess.run(["pgrep", "-x", "CapCut"], capture_output=True)
    if result.returncode not in (0, 1):
        raise RuntimeError("Cannot determine whether CapCut is running")
    return result.returncode == 0


def require_project_closed(project_closed: bool = False) -> None:
    # Process presence cannot identify which project is open. The flag records
    # the user's confirmation about this target project, not an app-wide close.
    if not project_closed and is_capcut_running():
        raise RuntimeError("Close the target project before writing draft files. CapCut may stay open on its home screen or another project. After confirming the target is closed, rerun apply/restore with --project-closed. No GUI control is used.")


def commit(project: Path, payloads: dict[Path, bytes], expected: dict, operation: str, verify_written=None, *, project_closed: bool = False) -> str:
    require_project_closed(project_closed)
    assert_snapshot(project, expected)
    def current_stats():
        return {name: ((project/name).stat().st_mtime_ns,(project/name).stat().st_size) for name in expected}
    stable_stats=current_stats()
    time.sleep(0.25)
    assert_snapshot(project, expected)
    if current_stats()!=stable_stats:
        raise RuntimeError("Project file mtime/size changed during stability checks; save/close the target and prepare again")
    lock = project / ".capcut-editing.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("Another edit may be running (.capcut-editing.lock exists)") from exc
    os.close(descriptor)
    originals = {}
    backups = {}
    suffix = ".codex-" + operation + "-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".bak"
    manifest = project / ("capcut-backup" + suffix + ".json")
    try:
        assert_snapshot(project, expected)
        for path, payload in payloads.items():
            if path.is_symlink() or not path.resolve().is_relative_to(project.resolve()):
                raise RuntimeError("Refusing an external/symlinked destination")
            json.loads(payload)
            originals[path] = path.read_bytes()
        for path, content in originals.items():
            backup = Path(str(path) + suffix)
            with backup.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            backups[path.relative_to(project).as_posix()] = {"file": backup.relative_to(project).as_posix(), "sha256": hashlib.sha256(content).hexdigest()}
        with manifest.open("x", encoding="utf-8") as handle:
            json.dump({"schema": 1, "suffix": suffix, "files": backups}, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        assert_snapshot(project, expected)
        if current_stats()!=stable_stats:
            raise RuntimeError("Project file mtime/size changed before writing; no draft payloads written")
        require_project_closed(project_closed)
        try:
            for path, content in payloads.items():
                atomic_write(path, content)
            for path, content in payloads.items():
                if path.read_bytes() != content:
                    raise RuntimeError("Written file differs from prepared payload")
            if verify_written:
                verify_written()
        except BaseException as failure:
            errors = []
            for path, content in originals.items():
                try:
                    atomic_write(path, content)
                except OSError as exc:
                    errors.append(str(exc))
            if errors:
                raise RuntimeError(f"Write failed and recovery is incomplete. Restore using {manifest}. Errors: {errors}") from failure
            raise RuntimeError(f"Write failed; original files restored. Backups: {suffix}") from failure
    finally:
        lock.unlink(missing_ok=True)
    return suffix


def prepare(project: Path, mode: str, work: Path, config: dict, do_transcribe: bool = True) -> dict:
    paths = source_paths(project)
    before = snapshot(project, paths)
    draft = read_json(paths[0])
    validate(draft)
    check_editable(draft, mode)
    reviewed = config["speech_reviewed_gaps"]
    if reviewed:
        if mode not in {"speech", "speech-subtitles"}:
            raise RuntimeError("Reviewed non-speech gaps are supported only in speech modes")
        if reviewed["draft_sha256"] != before[paths[0].relative_to(project).as_posix()]["sha256"]:
            raise RuntimeError("Reviewed gap times belong to another draft version; re-read and review the current timeline")
        if reviewed["ranges_us"][-1][1] > draft["duration"]:
            raise RuntimeError("Reviewed gap lies outside the current timeline")
    if project.resolve().is_relative_to(work.resolve()) or work.resolve().is_relative_to(project.resolve()):
        raise RuntimeError("The work directory must be outside the CapCut project")
    if work.exists() and any(work.iterdir()):
        raise RuntimeError("Use a new/empty work directory for each preparation")
    work.mkdir(parents=True, exist_ok=True)
    write_json(work / WORK_MARKER, {"schema": 1, "project": str(project)})
    report = {"old_duration_us": draft["duration"], "new_duration_us": draft["duration"], "removed_duration_us": 0}
    prepared = draft
    if mode in {"silence", "both"}:
        prepared, report = cut_silence(draft, project, config)
    elif mode in {"speech", "speech-subtitles"}:
        prepared, report = cut_speech(draft, project, work, config)
    if mode in CAPTION_MODES:
        font_path(config)
        audio = work / "timeline.wav"
        report["audio_alignment"] = extract_audio(prepared, project, audio, config)
        if do_transcribe:
            from transcribe import transcribe
            transcript = transcribe(audio, config)
            write_json(work / "transcript.json", transcript)
            words = transcript_words(transcript, prepared["duration"])
            cuts = [s["target_timerange"]["start"] for s in primary_track(prepared)["segments"][1:]]
            write_json(work / "words.json", {"duration_us": prepared["duration"], "clip_cuts_us": cuts, "transcript_sha256": hashlib.sha256(encoded(transcript)).hexdigest(), "words": [{"index": i, **word} for i, word in enumerate(words, 1)]})
    assert_snapshot(project, before)
    write_json(work / "prepared.json", prepared)
    plan = {"schema": 1, "project": str(project), "mode": mode, "snapshot": before, "prepared_sha256": hashlib.sha256(encoded(prepared)).hexdigest(), "settings": config, "report": report}
    if (work / "transcript.json").is_file():
        plan["transcript_sha256"] = hashlib.sha256((work / "transcript.json").read_bytes()).hexdigest()
    write_json(work / "plan.json", plan)
    return {**report, "operation": "prepared-without-project-writes", "mode": mode, "work_dir": str(work), "next": "Create semantic subtitles.json ranges from words.json, then apply" if mode in CAPTION_MODES else "Review speech-analysis.json and preview/apply" if mode == "speech" else "apply"}


def load_plan(work: Path) -> dict:
    marker = read_json(work / WORK_MARKER)
    plan = read_json(work / "plan.json")
    if plan.get("schema") != 1 or plan.get("mode") not in MODES or marker.get("project") != plan.get("project"):
        raise RuntimeError("Unrecognized work directory/plan")
    if hashlib.sha256((work / "prepared.json").read_bytes()).hexdigest() != plan["prepared_sha256"]:
        raise RuntimeError("Prepared draft was modified; prepare again")
    return plan


def build_result(work: Path, spec_path: Path | None) -> tuple[dict, dict, Path]:
    plan = load_plan(work)
    project = Path(plan["project"]).resolve()
    assert_snapshot(project, plan["snapshot"])
    draft = read_json(work / "prepared.json")
    config = settings_from_plan(plan)
    if plan["mode"] in CAPTION_MODES:
        spec_path = spec_path or work / "subtitles.json"
        transcript_path = work / "transcript.json"
        spec = read_json(spec_path)
        if hashlib.sha256(transcript_path.read_bytes()).hexdigest() != plan.get("transcript_sha256") or spec.get("transcript_sha256") != plan.get("transcript_sha256"):
            raise RuntimeError("Transcript/spec belongs to another preparation. Build new semantic blocks from the current words.json")
        draft = insert_subtitles(draft, read_json(transcript_path), spec, config)
    validate(draft)
    if plan["mode"] in CUT_MODES:
        validate_cut_fragments(draft, read_json(draft_paths(project)[0]))
    return draft, plan, project



def review_transcript(work: Path, review_path: Path) -> dict:
    """Stage bounded current-audio corrections and retain original/evidence files."""
    plan=load_plan(work); project=Path(plan["project"]).resolve()
    assert_snapshot(project,plan["snapshot"])
    if plan["mode"] not in CAPTION_MODES:
        raise RuntimeError("Transcript review requires a caption preparation")
    payload=read_json(review_path)
    if set(payload)!={"transcript_sha256","audio_ranges_us","transcript","note"} or not isinstance(payload["note"],str) or not payload["note"].strip():
        raise RuntimeError("Transcript review requires its current hash, audio ranges, transcript and evidence note")
    old_bytes=(work/"transcript.json").read_bytes(); before_sha=hashlib.sha256(old_bytes).hexdigest()
    if payload["transcript_sha256"]!=before_sha or before_sha!=plan.get("transcript_sha256"):
        raise RuntimeError("Transcript review is stale; use the current preparation hash")
    prepared=read_json(work/"prepared.json"); duration=prepared["duration"]
    ranges=payload["audio_ranges_us"]
    if not isinstance(ranges,list) or not ranges:
        raise RuntimeError("Transcript review needs explicit current-audio intervals")
    previous=0
    for span in ranges:
        if not isinstance(span,list) or len(span)!=2 or any(type(x) is not int for x in span) or not previous<=span[0]<span[1]<=duration:
            raise RuntimeError("Transcript review ranges must be ordered integer microseconds within the timeline")
        previous=span[1]
    old=transcript_words(read_json(work/"transcript.json"),duration)
    revised=payload["transcript"]; words=transcript_words(revised,duration)
    def outside(items):
        return [item for item in items if not any(round(item["end"]*1e6)>=left and round(item["start"]*1e6)<=right for left,right in ranges)]
    if outside(old)!=outside(words):
        raise RuntimeError("Transcript review changed words outside its reviewed current-audio intervals")
    archive=work/("transcript-before-review-"+before_sha+".json")
    with archive.open("xb") as handle:handle.write(old_bytes)
    evidence=work/("transcript-review-"+before_sha+".json")
    with evidence.open("xb") as handle:handle.write(encoded(payload))
    new_bytes=encoded(revised); after_sha=hashlib.sha256(new_bytes).hexdigest()
    report={"note":payload["note"],"audio_ranges_us":ranges,"original_word_count":len(old),"reviewed_word_count":len(words),
            "before_transcript_sha256":before_sha,"after_transcript_sha256":after_sha,"writes_project":False,"review_archives_retained":True}
    cuts=[segment["target_timerange"]["start"] for segment in primary_track(prepared)["segments"][1:]]
    assert_snapshot(project,plan["snapshot"])
    atomic_write(work/"transcript.json",new_bytes)
    write_json(work/"words.json",{"duration_us":duration,"clip_cuts_us":cuts,"transcript_sha256":after_sha,"words":[{"index":i,**word} for i,word in enumerate(words,1)]})
    plan["transcript_sha256"]=after_sha; plan["report"]["transcript_review"]=report
    write_json(work/"plan.json",plan)
    return report


def settings_from_plan(plan: dict) -> dict:
    # Validate saved settings with the same rules, without trusting arbitrary files.
    config = settings()
    if set(plan["settings"]) != set(config):
        raise RuntimeError("Plan settings are incomplete; prepare again")
    config.update(plan["settings"])
    return validate_settings(config)


def apply(work: Path, spec_path: Path | None = None, *, project_closed: bool = False) -> dict:
    draft, plan, project = build_result(work, spec_path)
    original = read_json(draft_paths(project)[0])
    raw_blocks = None
    if plan["mode"] in CAPTION_MODES:
        raw_blocks=subtitle_blocks(read_json(work/"transcript.json"),read_json(spec_path or work/"subtitles.json"),plan["settings"],draft["duration"])
    def verify_written():
        current = read_json(draft_paths(project)[0])
        validate(current)
        if raw_blocks is not None:
            validate_subtitles(current,plan["settings"],source_blocks=raw_blocks)
        if plan["mode"] in CUT_MODES:
            validate_cut_fragments(current, original)
    payload = encoded(draft)
    payloads = {path: payload for path in draft_paths(project)}
    meta_path = project / "draft_meta_info.json"
    if meta_path.is_file():
        meta = read_json(meta_path)
        for key in ("tm_duration", "duration", "draft_duration"):
            if key in meta:
                meta[key] = draft["duration"]
        payloads[meta_path] = encoded(meta)
    suffix = commit(project, payloads, plan["snapshot"], "silencecut" if plan["mode"] == "silence" else "speechcut" if plan["mode"] == "speech" else "subtitles" if plan["mode"] == "subtitles" else "edit", verify_written=verify_written, project_closed=project_closed)
    report = {**plan["report"], "backup_suffix": suffix, "project": str(project), "mode": plan["mode"], "validation": validate(draft)}
    if plan["mode"] in CAPTION_MODES:
        report.update(validate_subtitles(draft, plan["settings"],source_blocks=raw_blocks))
    cleanup(work)
    return report


def cleanup(work: Path) -> dict:
    read_json(work / WORK_MARKER)
    for name in ("speech-pause-audit.json", "speech-pause-review.wav", "speech-long-word-review.wav", "speech-long-word-rechecks.json", "speech-candidate.wav", "speech-candidate-transcript.json", "speech-cut-verification.json", "timeline.wav", "speech-original.wav", "speech-analysis.json", "speech-word-transcript.json", "speech-word-recheck.json", "speech-word-review.wav", "transcript.json", "words.json", "prepared.json", "subtitles.json", "plan.json", "preview.json", WORK_MARKER):
        path = work / name
        if path.is_file() or path.is_symlink():
            path.unlink()
    if not any(work.iterdir()):
        work.rmdir()
    return {"temporary_files_cleaned": True}


def restore(project: Path, suffix: str, *, project_closed: bool = False) -> dict:
    if not re.fullmatch(r"\.codex-(?:edit|silencecut|speechcut|subtitles|restore)-\d{8}-\d{6}-\d{6}\.bak", suffix):
        raise RuntimeError("Use the exact backup_suffix reported by this tool")
    manifest = read_json(project / ("capcut-backup" + suffix + ".json"))
    if manifest.get("schema") != 1 or manifest.get("suffix") != suffix:
        raise RuntimeError("Invalid backup manifest")
    paths = source_paths(project, strict=False)
    expected = snapshot(project, paths)
    if set(manifest["files"]) != set(expected):
        raise RuntimeError("Project file layout changed; restore manually from the preserved backup files")
    payloads = {}
    for relative, record in manifest["files"].items():
        path = project / relative
        backup = project / record["file"]
        if record["file"] != relative + suffix or path.is_symlink() or backup.is_symlink() or not backup.resolve().is_relative_to(project.resolve()):
            raise RuntimeError("Invalid backup destination")
        payload = backup.read_bytes()
        if hashlib.sha256(payload).hexdigest() != record["sha256"]:
            raise RuntimeError("Backup hash mismatch")
        json.loads(payload)
        payloads[path] = payload
    mirrors = draft_paths(project, strict=False)
    if len({payloads[path] for path in mirrors}) != 1:
        raise RuntimeError("Backup draft copies differ")
    validate(json.loads(payloads[mirrors[0]]))
    current_backup = commit(project, payloads, expected, "restore", project_closed=project_closed)
    return {"restored_backup": suffix, "pre_restore_backup_suffix": current_backup}


def doctor(config: dict) -> dict:
    from transcribe import choose_backend
    from speech_scan import available as speech_available
    try:
        font = font_path(config)
        font_error = None
    except RuntimeError as exc:
        font, font_error = None, str(exc)
    try:
        backend = choose_backend(config)
        backend_error = None
    except RuntimeError as exc:
        backend, backend_error = None, str(exc)
    ffmpeg = shutil.which(config["ffmpeg"])
    return {"python": platform.python_version(), "platform": platform.system(), "machine": platform.machine(), "ffmpeg": ffmpeg, "backend": backend, "backend_error": backend_error, "font": font, "font_error": font_error, "ready_for_silence": bool(ffmpeg), "ready_for_speech": bool(ffmpeg and speech_available()), "ready_for_subtitles": bool(ffmpeg and backend and font), "mlx_whisper": importlib.util.find_spec("mlx_whisper") is not None, "faster_whisper": importlib.util.find_spec("faster_whisper") is not None, "default_draft_roots": [str(p) for p in default_roots()], "note": "Windows draft round-trip support needs real CapCut verification; no GUI automation is required"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("project")
    prep = commands.add_parser("prepare")
    prep.add_argument("project")
    prep.add_argument("--mode", choices=MODES, default="both")
    prep.add_argument("--work-dir", type=Path, required=True)
    for name in ("preview", "apply"):
        command = commands.add_parser(name)
        command.add_argument("work_dir", type=Path)
        command.add_argument("--spec", type=Path)
        if name == "apply":
            command.add_argument("--project-closed", action="store_true", help="User confirmed the target project is closed; CapCut may remain open")
    undo = commands.add_parser("restore")
    undo.add_argument("project")
    undo.add_argument("--backup", required=True)
    undo.add_argument("--project-closed", action="store_true", help="User confirmed the target project is closed; CapCut may remain open")
    review = commands.add_parser("review-transcript")
    review.add_argument("work_dir", type=Path)
    review.add_argument("--review", type=Path, required=True)
    clean = commands.add_parser("cleanup")
    clean.add_argument("work_dir", type=Path)
    args = parser.parse_args()
    try:
        config = settings(args.config)
        if args.command == "doctor":
            report = doctor(config)
        elif args.command in {"inspect", "prepare", "restore"}:
            project = resolve_project(args.project, config)
            if args.command == "inspect":
                paths = draft_paths(project)
                draft = read_json(paths[0])
                report = {"project": str(project), "draft_version": draft.get("version"), "draft_format_version": draft.get("new_version"), "mirrors": [p.relative_to(project).as_posix() for p in paths], **validate(draft)}
            elif args.command == "prepare":
                report = prepare(project, args.mode, args.work_dir.resolve(), config)
            else:
                report = restore(project, args.backup, project_closed=args.project_closed)
        elif args.command == "preview":
            draft, plan, project = build_result(args.work_dir.resolve(), args.spec)
            report = {**plan["report"], "project": str(project), "validation": validate(draft), "writes_project": False}
            if plan["mode"] in CAPTION_MODES:
                raw_blocks=subtitle_blocks(read_json(args.work_dir/"transcript.json"),read_json(args.spec or args.work_dir/"subtitles.json"),plan["settings"],draft["duration"])
                report.update(validate_subtitles(draft, plan["settings"],source_blocks=raw_blocks))
                report.update(caption_preview(draft))
            if plan["mode"] in {"speech", "speech-subtitles"}:
                report["speech_analysis"] = read_json(args.work_dir / "speech-analysis.json")
        elif args.command == "review-transcript":
            report = review_transcript(args.work_dir.resolve(),args.review.resolve())
        elif args.command == "apply":
            report = apply(args.work_dir.resolve(), args.spec, project_closed=args.project_closed)
        else:
            report = cleanup(args.work_dir.resolve())
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
