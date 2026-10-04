# CapCut Editing Skill repository

When asked to install this package, follow the installer section at the start of README.md. Choose the actual host agent, default to project scope, run the installed setup and doctor, and report any missing prerequisite. Do not edit a CapCut project during installation.

The self-contained skill is skills/capcut-editing. Read its SKILL.md for editing requests. Source scripts live inside that folder so installed copies do not depend on this repository's checkout path. Keep shared instructions portable to Claude Code, Cursor and Codex.

Use synthetic media and temporary draft folders for development. Never commit personal footage, transcripts, draft JSON, backup files, font binaries or model weights. Run `python -m unittest discover -s tests -v` after script changes. Windows code/CI support is distinct from successful round-trip validation in the native Windows CapCut editor; do not conflate those claims.
