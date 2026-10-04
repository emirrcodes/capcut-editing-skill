"""Check recognition differences against actual ordered source slices, not text alone."""
from __future__ import annotations
from difflib import SequenceMatcher
from pathlib import Path
import re

from draft_primitives import cut_intersections, turkish_lower
from speech_scan import merge
from transcribe import transcribe


def intersect(left: int, right: int, spans: list) -> list[tuple[int, int]]:
    return merge([(max(left, start), min(right, end)) for start, end in spans], right)


def transcript_words(transcript: dict) -> list[dict]:
    output = []
    for segment in transcript.get("segments", []):
        for word in segment.get("words", []):
            token = re.sub(r"[^\w]+", "", turkish_lower(str(word.get("word", ""))))
            start, end = round(word["start"] * 1e6), round(word["end"] * 1e6)
            if token and end > start:
                output.append({"token": token, "word": word["word"], "start_us": start, "end_us": end})
    return output


def validate_sources(original: dict, candidate: dict, project: Path, keep: list) -> int:
    from capcut_tool import primary_track, media_for
    expected = list(cut_intersections(original, keep))
    actual = primary_track(candidate)["segments"]
    if len(expected) != len(actual):
        raise RuntimeError("Candidate source mapping differs from the protected cut plan")
    cursor = 0
    for (old, left, right), new in zip(expected, actual):
        source = {"start": old["source_timerange"]["start"] + left - old["target_timerange"]["start"], "duration": right - left}
        target = {"start": cursor, "duration": right - left}
        # CapCut's integer-microsecond frame resave can differ by one us.
        actual_source = new["source_timerange"]
        source_matches = all(abs(actual_source[key] - source[key]) <= 1 for key in ("start", "duration"))
        if not source_matches or new["target_timerange"] != target or media_for(original, project, old) != media_for(candidate, project, new):
            raise RuntimeError("Candidate source mapping differs from the protected cut plan")
        cursor += right - left
    return len(actual)


def compare(original_transcript: dict, candidate_transcript: dict, original: dict, project: Path, analysis: dict) -> dict:
    from capcut_tool import primary_track, media_for
    before, after = transcript_words(original_transcript), transcript_words(candidate_transcript)
    keep = analysis["keep_ranges_us"]
    speech = merge([tuple(span) for key in ("speech_ranges_us", "conservatively_protected_ranges_us") for span in analysis[key]], original["duration"])
    changes = []
    matcher = SequenceMatcher(a=[w["token"] for w in before], b=[w["token"] for w in after], autojunk=False)
    for tag, first, last, _, _ in matcher.get_opcodes():
        if tag not in {"delete", "replace"}:
            continue
        for index in range(first, last):
            word = before[index]; left, right = word["start_us"], word["end_us"]
            kept = intersect(left, right, keep)
            supported = intersect(left, right, speech)
            supported_us = sum(end - start for start, end in supported)
            supported_kept_us = sum(end - start for a, b in supported for start, end in intersect(a, b, keep))
            sources = []
            for old in primary_track(original)["segments"]:
                target = old["target_timerange"]
                a, b = max(left, target["start"]), min(right, target["start"] + target["duration"])
                if b <= a:
                    continue
                offset = old["source_timerange"]["start"] - target["start"]
                sources.append({"media": str(media_for(original, project, old)), "original_segment_id": old["id"],
                                "source_interval_us": [a + offset, b + offset],
                                "retained_source_ranges_us": [[c + offset, d + offset] for c, d in intersect(a, b, keep)]})
            changes.append({"original_word_index": index + 1, **word, "retained_timeline_ranges_us": [list(s) for s in kept],
                            "word_interval_kept_us": sum(b-a for a,b in kept), "vad_supported_us": supported_us,
                            "vad_supported_kept_us": supported_kept_us, "source_ranges": sources,
                            "interpretation": "Recognition changed; retained source evidence must be checked. This is not proof of deleted speech."})
    supported_total = sum(right-left for left,right in speech)
    supported_kept = sum(b-a for left,right in speech for a,b in intersect(left,right,keep))
    reviewed = analysis.get("reviewed_non_speech_ranges_us", [])
    reviewed_loss = 0
    for left, right in speech:
        for a, b in intersect(left, right, reviewed):
            reviewed_loss += (b-a) - sum(d-c for c,d in intersect(a,b,keep))
    pause=analysis.get("pause_review",{})
    independent=merge([tuple(span) for key in ("independent_short_word_protection_us","independent_context_word_protection_us")
                       for span in pause.get(key,[])],original["duration"])
    independent_loss=sum((b-a)-sum(d-c for c,d in intersect(a,b,keep)) for a,b in independent)
    reviewed_independent_loss=sum((b-a)-sum(d-c for c,d in intersect(a,b,keep))
                                 for left,right in independent for a,b in intersect(left,right,reviewed))
    return {"independent_word_source_loss_us":independent_loss,
            "unexpected_independent_word_source_loss_us":independent_loss-reviewed_independent_loss,
            "original_word_count": len(before), "candidate_word_count": len(after), "changed_or_missing_words": changes,
            "vad_supported_source_loss_us": supported_total-supported_kept,
            "user_reviewed_vad_override_us": reviewed_loss,
            "unexpected_vad_supported_source_loss_us": supported_total-supported_kept-reviewed_loss,
            "reviewed_non_speech_ranges_us": reviewed,
            "note": "No word is deleted because it disappears from recognition. Long word timings can include non-speech. Preserve repeats and false starts."}


def verify(original: dict, candidate: dict, project: Path, analysis: dict, audio: Path, config: dict, work: Path) -> dict:
    from capcut_tool import read_json, write_json
    pieces = validate_sources(original, candidate, project, analysis["keep_ranges_us"])
    result = transcribe(audio, config, speech_review=True)
    write_json(work / "speech-candidate-transcript.json", result)
    report = compare(read_json(work / "speech-word-transcript.json"), result, original, project, analysis)
    report["ordered_source_pieces_verified"] = pieces
    write_json(work / "speech-cut-verification.json", report)
    if report["unexpected_independent_word_source_loss_us"] > 1000:
        raise RuntimeError("Candidate removes independently protected word source audio; matching ASR tokens do not prove the prefix survived. Inspect speech-cut-verification.json")
    if report["unexpected_vad_supported_source_loss_us"] > 1000:
        raise RuntimeError("Candidate removes VAD-supported source audio; inspect speech-cut-verification.json and revise before apply")
    return report
