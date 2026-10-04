#!/usr/bin/env python3
"""Install the chosen speech engine in this skill's isolated virtualenv."""
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
        requirement = "mlx-whisper>=0.4,<1" if backend == "mlx" else "faster-whisper>=1.1,<2"
        subprocess.run([str(python), "-m", "pip", "install", requirement], check=True)
    report = {"backend": backend, "python": str(python), "virtualenv_exists": python.is_file(), "note": "FFmpeg must be installed separately. The speech model downloads on first use, then inference runs locally."}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
