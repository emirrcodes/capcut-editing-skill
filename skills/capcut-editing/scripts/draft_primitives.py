"""Draft primitives adapted from the original local CapCut workflow."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

def atomic_write(path: Path, payload: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def fresh_id() -> str:
    return str(uuid.uuid4()).upper()


def resolve_draft_media_path(project: Path, raw_path: str) -> Path:
    placeholder = re.match(r"^##_draftpath_placeholder_[^#]+_##/(.+)$", raw_path)
    if placeholder:
        return project / placeholder.group(1)
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return project / path


def duplicate_material(draft: dict, material_index: dict[str, tuple[str, dict]], old_id: str) -> str:
    try:
        bucket, original = material_index[old_id]
    except KeyError as exc:
        raise RuntimeError(f"Unresolved material reference: {old_id}") from exc
    clone = copy.deepcopy(original)
    new_id = fresh_id()
    clone["id"] = new_id
    if "unique_id" in clone:
        clone["unique_id"] = uuid.uuid4().hex
    draft["materials"][bucket].append(clone)
    material_index[new_id] = (bucket, clone)
    return new_id


def apply_timeline_keep_ranges(draft: dict, keep_ranges: list[tuple[int, int]]) -> int:
    material_index: dict[str, tuple[str, dict]] = {}
    for bucket, items in draft.get("materials", {}).items():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                material_index[item["id"]] = (bucket, item)

    range_offsets: list[tuple[int, int, int]] = []
    output_cursor = 0
    for start, end in keep_ranges:
        range_offsets.append((start, end, output_cursor))
        output_cursor += end - start

    for track in draft.get("tracks", []):
        rebuilt: list[dict] = []
        for original in track.get("segments", []):
            target = original["target_timerange"]
            target_start = int(target["start"])
            target_duration = int(target["duration"])
            target_end = target_start + target_duration
            source = original.get("source_timerange")
            piece_number = 0
            for keep_start, keep_end, mapped_start in range_offsets:
                intersection_start = max(target_start, keep_start)
                intersection_end = min(target_end, keep_end)
                if intersection_end <= intersection_start:
                    continue
                piece = copy.deepcopy(original)
                if piece_number > 0:
                    piece["id"] = fresh_id()
                    if isinstance(original.get("material_id"), str):
                        piece["material_id"] = duplicate_material(
                            draft, material_index, original["material_id"]
                        )
                    piece["extra_material_refs"] = [
                        duplicate_material(draft, material_index, ref)
                        for ref in original.get("extra_material_refs", [])
                    ]
                piece_number += 1
                piece["target_timerange"] = {
                    "start": mapped_start + intersection_start - keep_start,
                    "duration": intersection_end - intersection_start,
                }
                if isinstance(source, dict) and target_duration > 0:
                    source_duration = int(source["duration"])
                    source_offset = round(
                        (intersection_start - target_start) * source_duration / target_duration
                    )
                    piece_source_duration = round(
                        (intersection_end - intersection_start) * source_duration / target_duration
                    )
                    piece["source_timerange"] = {
                        "start": int(source["start"]) + source_offset,
                        "duration": piece_source_duration,
                    }
                rebuilt.append(piece)
        track["segments"] = rebuilt

    draft["duration"] = output_cursor
    return output_cursor


def turkish_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def subtitle_lower(text: str, language: str) -> str:
    if language.lower().startswith("tr"):
        return turkish_lower(text)
    return text.lower()


def clean_subtitle_word(text: str, language: str) -> str:
    cleaned = text.strip().strip(".,!?;:…\"“”()[]{}")
    return subtitle_lower(cleaned, language)


def wrap_display_text(text: str, limit: int = 28) -> str:
    words = text.split()
    if len(text) <= limit or len(words) < 2:
        return text
    candidates = []
    for split_at in range(1, len(words)):
        left = " ".join(words[:split_at])
        right = " ".join(words[split_at:])
        candidates.append((max(len(left), len(right)), abs(len(left) - len(right)), split_at))
    _, _, split_at = min(candidates)
    return " ".join(words[:split_at]) + "\n" + " ".join(words[split_at:])


def word_timing_payload(words: list[dict], block_start_seconds: float) -> dict:
    starts: list[int] = []
    ends: list[int] = []
    text_parts: list[str] = []
    origin_ms = round(block_start_seconds * 1000)
    for index, word in enumerate(words):
        word_start = max(0, round(float(word["start"]) * 1000) - origin_ms)
        word_end = max(word_start, round(float(word["end"]) * 1000) - origin_ms)
        starts.append(word_start)
        ends.append(word_end)
        text_parts.append(word["clean_word"])
        if index + 1 < len(words):
            next_start = max(0, round(float(words[index + 1]["start"]) * 1000) - origin_ms)
            starts.append(next_start)
            ends.append(next_start)
            text_parts.append(" ")
    return {"start_time": starts, "end_time": ends, "text": text_parts}


def remove_previous_codex_subtitles(draft: dict) -> int:
    removed_tracks = [
        track
        for track in draft.get("tracks", [])
        if track.get("type") == "text" and track.get("name") == "codex_subtitles"
    ]
    removal_ids = {
        ref
        for track in removed_tracks
        for segment in track.get("segments", [])
        for ref in [segment.get("material_id"), *segment.get("extra_material_refs", [])]
        if isinstance(ref, str)
    }
    draft["tracks"] = [
        track
        for track in draft.get("tracks", [])
        if not (track.get("type") == "text" and track.get("name") == "codex_subtitles")
    ]
    still_referenced = {
        ref
        for track in draft.get("tracks", [])
        for segment in track.get("segments", [])
        for ref in [segment.get("material_id"), *segment.get("extra_material_refs", [])]
        if isinstance(ref, str)
    }
    safe_to_remove = removal_ids - still_referenced
    for bucket, items in draft.get("materials", {}).items():
        if isinstance(items, list):
            draft["materials"][bucket] = [
                item for item in items if not (isinstance(item, dict) and item.get("id") in safe_to_remove)
            ]
    return len(removed_tracks)
