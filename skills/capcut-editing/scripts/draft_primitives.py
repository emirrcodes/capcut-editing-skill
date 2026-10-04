"""Draft primitives adapted from the original local CapCut workflow."""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

MIN_CLIP_US = 100_000


def cut_intersections(draft: dict, keep_ranges: list[tuple[int, int]]):
    """Compute actual output pieces before mutating any tracks/materials."""
    previous_end = 0
    for start, end in keep_ranges:
        if type(start) is not int or type(end) is not int or start < previous_end or end <= start or end > draft["duration"]:
            raise RuntimeError("Keep ranges must be ordered, disjoint, positive and inside the current timeline")
        previous_end = end
    for track in draft.get("tracks", []):
        if track.get("type") not in {"video", "audio"}:
            continue
        for original in track.get("segments", []):
            target = original["target_timerange"]
            left, right = target["start"], target["start"] + target["duration"]
            for start, end in keep_ranges:
                first, last = max(left, start), min(right, end)
                if last > first:
                    yield original, first, last


def validate_cut_fragments(draft: dict, original_draft: dict) -> None:
    originals = {segment["id"]: segment for track in original_draft["tracks"]
                 if track.get("type") in {"video", "audio"} for segment in track.get("segments", [])}
    for track in draft["tracks"]:
        if track.get("type") not in {"video", "audio"}:
            continue
        for segment in track.get("segments", []):
            duration = segment["target_timerange"]["duration"]
            if duration >= MIN_CLIP_US:
                continue
            old = originals.get(segment.get("id"))
            unchanged = old and old["target_timerange"]["duration"] == duration and all(
                old.get(key) == segment.get(key) for key in ("source_timerange", "material_id", "extra_material_refs"))
            if not unchanged:
                raise RuntimeError(f"New or shortened micro-clip {segment.get('id')}: {duration} us < {MIN_CLIP_US} us")


def protect_cut_boundaries(draft: dict, keep_ranges: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], list[list[int]]]:
    """Keep extra audio inside existing clips instead of dropping tiny pieces.

    Existing short clips stay whole. Extending timeline intervals never merges
    distinct source ranges; apply still intersects each original clip separately.
    """
    from speech_scan import merge, gaps
    original_keep = merge(keep_ranges, draft["duration"])
    additions = []
    for track in draft["tracks"]:
        if track.get("type") in {"video", "audio"}:
            for segment in track.get("segments", []):
                target = segment["target_timerange"]
                if target["duration"] < MIN_CLIP_US:
                    additions.append((target["start"], target["start"] + target["duration"]))
    for original, start, end in cut_intersections(draft, original_keep):
        if end - start >= MIN_CLIP_US:
            continue
        target = original["target_timerange"]
        left, right = target["start"], target["start"] + target["duration"]
        if right - left < MIN_CLIP_US:
            additions.append((left, right))
        else:
            first = max(left, min(start, right - MIN_CLIP_US))
            additions.append((first, min(right, max(end, first + MIN_CLIP_US))))
    protected = merge([*original_keep, *additions], draft["duration"])
    extra = [(max(left, start), min(right, end)) for left, right in gaps(original_keep, draft["duration"])
             for start, end in protected if min(right, end) > max(left, start)]
    return protected, [list(span) for span in extra]

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
    for original, start, end in cut_intersections(draft, keep_ranges):
        if end - start < MIN_CLIP_US and end - start < original["target_timerange"]["duration"]:
            raise RuntimeError(f"Cut would create a micro-clip at {original.get('id')}: {end-start} us < {MIN_CLIP_US} us. Revise the cut to keep more boundary audio; do not discard speech.")
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
