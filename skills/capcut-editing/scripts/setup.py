#!/usr/bin/env python3
"""Install CPU speech detection and the chosen transcription engine in an isolated virtualenv."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import platform
import subprocess
import venv


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("auto", "mlx", "faster"), default="auto")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    apple = platform.system() == "Darwin" and platform.machine().lower() in {"arm64", "aarch64"}
    backend = ("mlx" if apple else "faster") if args.backend == "auto" else args.backend
    if backend == "mlx" and not apple:
        parser.error("Use faster on Windows or Intel Macs")
    root = Path(__file__).resolve().parent.parent
    environment = root / ".venv"
    python = environment / ("Scripts/python.exe" if platform.system() == "Windows" else "bin/python")
    if not args.check_only:
        if not python.is_file():
            venv.EnvBuilder(with_pip=True).create(environment)
        requirements = ["faster-whisper>=1.2.1,<2"]
        if backend == "mlx":
            requirements.append("mlx-whisper>=0.4,<1")
        subprocess.run([str(python), "-m", "pip", "install", *requirements], check=True)
    report = {"backend": backend, "python": str(python), "virtualenv_exists": python.is_file(), "speech_detector": "CPU Silero VAD bundled with faster-whisper", "note": "FFmpeg must be installed separately. The transcription model downloads on first speech-cut or caption use, then inference runs locally. Default speech cutting includes word and pause review. Explicit VAD-only configurations need no Whisper transcription weights."}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
