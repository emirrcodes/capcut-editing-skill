"""Optional ASR cross-check of speech cuts; word times protect, never prove cuts."""
from __future__ import annotations
import math
import re
from difflib import SequenceMatcher
from pathlib import Path
import wave

from speech_scan import gaps, merge
from transcribe import transcribe


def suspicious(segment: dict) -> bool:
    ratio = segment.get("compression_ratio")
    if ratio is not None and (not math.isfinite(ratio) or ratio > 2.4):
        return True
    return segment.get("no_speech_prob", 0) > 0.6 and segment.get("avg_logprob", 0) < -1


def interval(start, end, duration: int) -> tuple[int, int]:
    if not all(type(value) in (int, float) and math.isfinite(value) for value in (start, end)):
        raise RuntimeError("Invalid ASR timestamp during speech review")
    left, right = max(0, round(start * 1e6)), min(duration, round(end * 1e6))
    if right <= left:
        raise RuntimeError("Empty/out-of-range ASR timestamp during speech review")
    return left, right


def trusted_words(result: dict, duration: int, offset: int = 0) -> tuple[list[dict], list[tuple[int, int]]]:
    words, suspects = [], []
    for segment in result.get("segments", []):
        if suspicious(segment):
            suspects.append(interval(segment["start"] + offset / 1e6, segment["end"] + offset / 1e6, duration))
            continue
        for word in segment.get("words", []):
            if str(word.get("word", "")).strip():
                start, end = interval(word["start"] + offset / 1e6, word["end"] + offset / 1e6, duration)
                words.append({"start_us": start, "end_us": end, "word": word["word"]})
    return words, merge(suspects, duration)


def segment_words(result: dict, duration: int, offset: int = 0) -> tuple[list[dict], list[tuple[int, int]]]:
    """A malformed word quarantines its bounded segment, not the full decode.

    Whisper may return zero-length word alignments on real recordings. They
    cannot establish speech boundaries. Recheck the segment independently and
    preserve it if unresolved. Invalid segment bounds still stop the operation.
    """
    words, suspects = [], []
    for segment in result.get("segments", []):
        try:
            found, uncertain = trusted_words({"segments": [segment]}, duration, offset)
            words.extend(found); suspects.extend(uncertain)
        except (RuntimeError, KeyError, TypeError, ValueError, OverflowError):
            suspects.append(interval(segment["start"] + offset / 1e6,
                                     segment["end"] + offset / 1e6, duration))
    return words, merge(suspects, duration)


def extract_window(path: Path, output: Path, start: int, end: int) -> None:
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        first, last = round(start / 1e6 * rate), round(end / 1e6 * rate)
        source.setpos(min(first, source.getnframes()))
        frames = source.readframes(last - first)
        with wave.open(str(output), "wb") as target:
            target.setparams(source.getparams())
            target.writeframes(frames)


def word_protection(words: list[dict], speech: list[tuple[int, int]], duration: int) -> list[tuple[int, int]]:
    protected = []
    for word in words:
        start, end = word["start_us"], word["end_us"]
        overlaps = merge([(max(start, left), min(end, right)) for left, right in speech], duration)
        overlap = sum(right - left for left, right in overlaps)
        if overlap < max(100_000, round((end - start) * .35)):
            # A possibly real weak word can be missed by VAD. Keep its full
            # acoustic interval, not merely the printed token in another ASR run.
            protected.append((start - 20_000, end + 20_000))
        else:
            # Do not preserve a long non-speech gap just because ASR stretched
            # one word over it. Bridge only short intra-word gaps.
            joined = merge(overlaps, duration, 350_000)
            protected.extend((left - 20_000, right + 20_000) for left, right in joined)
    return merge(protected, duration)


def refine_long_words(audio: Path, words: list[dict], duration: int, config: dict, work: Path, speech: list[tuple[int, int]] | None = None) -> tuple[list[dict], list[dict]]:
    """Refine stretched word times with one independent contextual recheck.

    A missing token never licenses removal. Replace a long interval only when
    an independently recognized matching word has a shorter valid interval.
    Keep all other trusted words recovered in that same context.
    """
    from capcut_tool import write_json
    from draft_primitives import turkish_lower
    normalized = lambda text: re.sub(r"[^\w]+", "", turkish_lower(str(text)))
    output, reviews = [], []
    temporary = work / "speech-long-word-review.wav"
    try:
        for word in words:
            word_length = word["end_us"] - word["start_us"]
            overlap = sum(end-start for start,end in merge([(max(word["start_us"], left), min(word["end_us"], right)) for left,right in (speech or [])], duration))
            weak_stretched = speech is not None and word_length >= 500_000 and overlap < max(100_000, round(word_length * .35))
            if word_length <= 1_500_000 and not weak_stretched:
                output.append(word)
                continue
            # Do not introduce an unbounded retry for abnormal long decodes.
            if word["end_us"] - word["start_us"] > 30_000_000:
                output.append(word)
                reviews.append({"original_word": word, "status": "unresolved-kept", "reason": "Word interval exceeds bounded contextual review"})
                continue
            left = max(0, word["start_us"] - 400_000)
            right = min(duration, word["end_us"] + 400_000)
            extract_window(audio, temporary, left, right)
            result = transcribe(temporary, config, speech_review=True)
            local, suspects = segment_words(result, duration, left)
            matches = [candidate for candidate in local
                       if candidate["end_us"] - candidate["start_us"] <= 1_500_000
                       and candidate["end_us"] - candidate["start_us"] < word_length
                       and candidate["end_us"] > word["start_us"] and candidate["start_us"] < word["end_us"]
                       and SequenceMatcher(None, normalized(word["word"]), normalized(candidate["word"]), autojunk=False).ratio() >= .85]
            uncertain = any(end > word["start_us"] and start < word["end_us"] for start, end in suspects)
            accepted = bool(matches) and not uncertain
            if accepted:
                output.extend(local)
            else:
                output.append(word)
                output.extend(local)
            reviews.append({"original_word": word, "context_range_us": [left, right],
                            "status": "refined" if accepted else "unresolved-kept",
                            "matching_words": matches, "recovered_words": local,
                            "suspect_ranges_us": [list(span) for span in suspects], "transcript": result})
    finally:
        temporary.unlink(missing_ok=True)
    unique = {}
    for word in output:
        unique[(word["start_us"], word["end_us"], normalized(word["word"]))] = word
    write_json(work / "speech-long-word-rechecks.json", {"windows": reviews})
    return list(unique.values()), reviews


def review(audio: Path, analysis: dict, config: dict, work: Path) -> dict:
    from capcut_tool import write_json
    duration = analysis["audio_duration_us"]
    original = transcribe(audio, config, speech_review=True)
    write_json(work / "speech-word-transcript.json", original)
    words, suspects = segment_words(original, duration)
    unresolved, rechecks = [], []
    temporary = work / "speech-word-review.wav"
    try:
        for left, right in suspects:
            cursor = left
            while cursor < right:
                finish = min(right, cursor + 30_000_000)
                first, last = max(0, cursor - 400_000), min(duration, finish + 400_000)
                extract_window(audio, temporary, first, last)
                # No previous text is supplied; retries are bounded to one
                # independent pass per window, never a transcription retry loop.
                result = transcribe(temporary, config, speech_review=True)
                new_words, new_suspects = segment_words(result, duration, first)
                words.extend(word for word in new_words if word["end_us"] > cursor and word["start_us"] < finish)
                uncertain = [(max(cursor, start), min(finish, end)) for start, end in new_suspects if min(finish, end) > max(cursor, start)]
                unresolved.extend(uncertain)
                rechecks.append({"start_us": first, "end_us": last, "unresolved_ranges_us": [list(span) for span in uncertain], "transcript": result})
                cursor = finish
    finally:
        temporary.unlink(missing_ok=True)
    write_json(work / "speech-word-recheck.json", {"windows": rechecks})
    original_stretched = [[word["start_us"], word["end_us"]] for word in words
                          if word["end_us"] - word["start_us"] > 1_500_000]
    speech = merge([tuple(span) for key in ("speech_ranges_us", "conservatively_protected_ranges_us") for span in analysis[key]], duration)
    words, long_reviews = refine_long_words(audio, words, duration, config, work, speech)
    protected = word_protection(words, speech, duration)
    stretched = [[word["start_us"], word["end_us"]] for word in words
                 if word["end_us"] - word["start_us"] > 1_500_000]
    uncertain = merge(unresolved, duration)
    keep = merge([*(tuple(span) for span in analysis["keep_ranges_us"]), *protected, *uncertain], duration, round(config["speech_min_gap"] * 1e6))
    if not keep:
        raise RuntimeError("No usable speech found after VAD and word review; no project files changed")
    output = dict(analysis)
    output.update({"method": "silero-vad-gap-and-word-review", "keep_ranges_us": [list(span) for span in keep],
                   "removed_ranges_us": [list(span) for span in gaps(keep, duration)],
                   "word_review": {"trusted_word_count": len(words), "suspect_ranges_us": [list(span) for span in suspects],
                                   "independent_rechecks": len(rechecks), "protected_word_ranges_us": [list(span) for span in protected],
                                   "long_word_timing_ranges_us": stretched,
                                   "original_long_word_timing_ranges_us": original_stretched,
                                   "long_word_reviews": [{key: value for key, value in item.items() if key != "transcript"} for item in long_reviews],
                                   "unresolved_kept_ranges_us": [list(span) for span in uncertain],
                                   "note": "Suspicious compressed/repeated ASR text is rechecked, never trusted automatically. Unresolved intervals are kept for closer inspection. Transcript differences alone do not prove audio loss."}})
    return output
