#!/usr/bin/env python3
"""Normalize local Whisper engines to the same word-timestamp JSON format."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import platform
import sys


def choose_backend(config: dict) -> str:
    backend = config["backend"]
    apple = platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}
    if backend == "auto":
        backend = "mlx" if apple and importlib.util.find_spec("mlx_whisper") else "faster"
    if backend == "mlx" and not apple:
        raise RuntimeError("MLX requires an Apple Silicon Mac. Use backend=faster on Windows/Intel")
    module = "mlx_whisper" if backend == "mlx" else "faster_whisper"
    if not importlib.util.find_spec(module):
        raise RuntimeError(f"{module} is missing from {sys.executable}. Run setup.py with the matching backend")
    return backend


def quality(segment) -> dict:
    result = {}
    for key in ("compression_ratio", "avg_logprob", "no_speech_prob"):
        value = segment.get(key) if isinstance(segment, dict) else getattr(segment, key, None)
        if isinstance(value, (int, float)):
            result[key] = float(value)
    return result


def transcribe(audio: Path, config: dict, *, speech_review: bool = False) -> dict:
    os.environ["ORT_DISABLE_TELEMETRY"] = "1"
    backend = choose_backend(config)
    review_options = {"hallucination_silence_threshold": 2.0} if speech_review else {}
    if backend == "mlx":
        import mlx_whisper
        result = mlx_whisper.transcribe(
            str(audio), path_or_hf_repo=config["model"] or "mlx-community/whisper-large-v3-turbo",
            language=config["language"], word_timestamps=True,
            condition_on_previous_text=False, verbose=False,
            **review_options,
        )
        return {"backend": "mlx", "language": config["language"], "segments": [{"start": float(segment["start"]), "end": float(segment["end"]), "text": segment.get("text", ""), **quality(segment), "words": [{"start": float(word["start"]), "end": float(word["end"]), "word": word["word"]} for word in segment.get("words", [])]} for segment in result["segments"]]}
    from faster_whisper import WhisperModel
    model = WhisperModel(config["model"] or "large-v3-turbo", device=config["device"], compute_type="int8" if config["device"] == "cpu" else "float16")
    # Keep original timeline coordinates; the cut pass already handled silence.
    segments, info = model.transcribe(str(audio), language=config["language"], word_timestamps=True, vad_filter=False, condition_on_previous_text=False, **review_options)
    return {"backend": "faster", "language": info.language, "segments": [{"start": float(segment.start), "end": float(segment.end), "text": segment.text, **quality(segment), "words": [{"start": float(word.start), "end": float(word.end), "word": word.word} for word in (segment.words or [])]} for segment in segments]}
