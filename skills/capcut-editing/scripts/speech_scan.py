"""Speech-aware cuts with Silero VAD and a sensitive review of each gap.

The model bundled with faster-whisper runs on CPU on macOS and Windows.
This module never applies a volume threshold as a speech decision.
"""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import wave

RATE = 16000


def available() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in ("faster_whisper", "onnxruntime", "numpy"))


def merge(spans: list[tuple[int, int]], duration: int, gap: int = 0) -> list[tuple[int, int]]:
    result = []
    for start, end in sorted(spans):
        start, end = max(0, start), min(duration, end)
        if end <= start:
            continue
        if result and start - result[-1][1] <= gap:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return [tuple(span) for span in result]


def gaps(spans: list[tuple[int, int]], duration: int) -> list[tuple[int, int]]:
    result, cursor = [], 0
    for start, end in merge(spans, duration):
        if start > cursor:
            result.append((cursor, start))
        cursor = end
    if cursor < duration:
        result.append((cursor, duration))
    return result


def read_audio(path: Path):
    import numpy as np
    with wave.open(str(path), "rb") as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (RATE, 1, 2):
            raise RuntimeError("Speech analysis requires mono 16 kHz PCM16 audio")
        return np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768.0


def detect(samples, threshold: float, config: dict) -> list[tuple[int, int]]:
    # Suppress runtime telemetry before import, including initialization writes.
    os.environ["ORT_DISABLE_TELEMETRY"] = "1"
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    options = VadOptions(
        threshold=threshold,
        min_speech_duration_ms=round(config["speech_min_duration"] * 1000),
        min_silence_duration_ms=100,
        speech_pad_ms=0,
    )
    output = get_speech_timestamps(samples, vad_options=options, sampling_rate=RATE)
    spans = []
    for item in output:
        start, end = item.get("start"), item.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(samples):
            raise RuntimeError("The speech detector returned invalid sample coordinates")
        spans.append((start, end))
    return merge(spans, len(samples))


def analyze_samples(samples, config: dict) -> dict:
    """Keep strong speech, recheck gaps, and conservatively protect weak speech."""
    import numpy as np
    duration = len(samples)
    if duration == 0 or not np.isfinite(samples).all():
        raise RuntimeError("Empty/invalid speech-analysis audio")
    strong = detect(samples, config["speech_threshold"], config)
    minimum_gap = round(config["speech_min_gap"] * RATE)
    context = round(config["speech_review_context"] * RATE)
    # Limit memory and inference sizes for long gaps; adjacent windows overlap
    # by their context so a word on a window edge is not lost.
    window = round(config["speech_review_window"] * RATE)
    recovered, reviews = [], []
    for gap_start, gap_end in gaps(strong, duration):
        if gap_end - gap_start < minimum_gap:
            continue
        cursor = gap_start
        while cursor < gap_end:
            finish = min(gap_end, cursor + window)
            start, end = max(0, cursor - context), min(duration, finish + context)
            sample = samples[start:end]
            found = detect(sample, config["speech_review_threshold"], config)
            peak = float(np.max(np.abs(sample)))
            gain = min(config["speech_review_max_gain"], 0.25 / peak) if 0 < peak < 0.25 else 1.0
            if gain > 1:
                # Analysis gain only. Original clip audio and volume stay intact.
                found += detect(np.clip(sample * gain, -1, 1).astype(np.float32), config["speech_review_threshold"], config)
            protected = merge([(max(cursor, start + left), min(finish, start + right)) for left, right in found], duration)
            recovered.extend(protected)
            reviews.append({"start_us": round(cursor / RATE * 1e6), "end_us": round(finish / RATE * 1e6), "protected_speech_us": [[round(left / RATE * 1e6), round(right / RATE * 1e6)] for left, right in protected], "analysis_gain": gain})
            cursor = finish
    if not strong and not recovered:
        raise RuntimeError("No speech found after both VAD passes. No project files changed; inspect the audio/settings instead of deleting the entire timeline")
    raw_speech = merge([*strong, *recovered], duration)
    padding = round(config["speech_padding"] * RATE)
    # Preserve short natural pauses and pad consonants/word tails.
    keep = merge([(start - padding, end + padding) for start, end in raw_speech], duration, minimum_gap)
    if keep[0][0] < minimum_gap:
        keep[0] = (0, keep[0][1])
    if duration - keep[-1][1] < minimum_gap:
        keep[-1] = (keep[-1][0], duration)
    to_us = lambda span: [round(span[0] / RATE * 1e6), round(span[1] / RATE * 1e6)]
    return {"method": "silero-vad-with-gap-review", "audio_duration_us": round(duration / RATE * 1e6), "keep_ranges_us": [to_us(span) for span in keep], "speech_ranges_us": [to_us(span) for span in strong], "conservatively_protected_ranges_us": [to_us(span) for span in merge(recovered, duration)], "removed_ranges_us": [to_us(span) for span in gaps(keep, duration)], "gap_reviews": reviews, "note": "Weak speech found during review is kept. Background voices/singing can also count as speech; this is not speaker isolation."}


def analyze(path: Path, config: dict) -> dict:
    if not available():
        raise RuntimeError("Speech mode needs faster-whisper and its CPU Silero/ONNX dependencies. Run setup.py; no amplitude-only fallback is used")
    return analyze_samples(read_audio(path), config)
