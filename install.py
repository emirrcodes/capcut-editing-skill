#!/usr/bin/env python3
"""Install the self-contained skill for a local agent, without GitHub login."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import tempfile

AGENTS = {"codex": ".agents", "claude": ".claude", "cursor": ".cursor"}
NAME = "capcut-editing"


def install(agent: str, base: Path, replace: bool = False) -> dict:
    source = Path(__file__).resolve().parent / "skills" / NAME
    parent = base.expanduser().resolve() / AGENTS[agent] / "skills"
    destination = parent / NAME
    parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise RuntimeError("Refusing to replace a symlinked skill")
    if destination.exists() and not replace:
        raise RuntimeError(f"Skill already exists at {destination}. Use --replace to back it up and update")
    previous = None
    with tempfile.TemporaryDirectory(prefix=".capcut-install-", dir=parent) as temporary:
        staged = Path(temporary) / NAME
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns(".venv", "__pycache__", "*.pyc"))
        if destination.exists():
            previous = destination.with_name(NAME + ".backup-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
            os.replace(destination, previous)
        try:
            os.replace(staged, destination)
        except OSError:
            if previous:
                os.replace(previous, destination)
            raise
    return {"agent": agent, "skill": str(destination), "previous_skill_backup": str(previous) if previous else None, "next": f"Run setup.py in {destination / 'scripts'} and then capcut_tool.py doctor"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True, choices=tuple(AGENTS))
    parser.add_argument("--scope", choices=("project", "user"), default="project")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.agent, Path.home() if args.scope == "user" else args.project, args.replace), indent=2))
    except (RuntimeError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
