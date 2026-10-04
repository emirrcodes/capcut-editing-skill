#!/usr/bin/env python3
"""Normalize local Whisper engines to the same word-timestamp JSON format."""
from __future__ import annotations
import importlib.util
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


def transcribe(audio: Path, config: dict) -> dict:
    backend = choose_backend(config)
    if backend == "mlx":
        import mlx_whisper
        result = mlx_whisper.transcribe(
            str(audio), path_or_hf_repo=config["model"] or "mlx-community/whisper-large-v3-turbo",
            language=config["language"], word_timestamps=True,
            condition_on_previous_text=False, verbose=False,
        )
        return {"backend": "mlx", "language": config["language"], "segments": [{"start": segment["start"], "end": segment["end"], "text": segment.get("text", ""), "words": [{"start": word["start"], "end": word["end"], "word": word["word"]} for word in segment.get("words", [])]} for segment in result["segments"]]}
    from faster_whisper import WhisperModel
    model = WhisperModel(config["model"] or "large-v3-turbo", device=config["device"], compute_type="int8" if config["device"] == "cpu" else "float16")
    # Keep original timeline coordinates; the cut pass already handled silence.
    segments, info = model.transcribe(str(audio), language=config["language"], word_timestamps=True, vad_filter=False, condition_on_previous_text=False)
    return {"backend": "faster", "language": info.language, "segments": [{"start": segment.start, "end": segment.end, "text": segment.text, "words": [{"start": word.start, "end": word.end, "word": word.word} for word in (segment.words or [])]} for segment in segments]}
