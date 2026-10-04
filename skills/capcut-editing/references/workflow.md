# Commands and draft contract

Resolve SCRIPT_DIR from the installed skill. Use the virtualenv Python reported by setup.py (`.venv/bin/python` on macOS, `.venv/Scripts/python.exe` on Windows). Commands below use PYTHON and TOOL as placeholders for those absolute paths, not literal commands.

```text
PYTHON TOOL doctor
PYTHON TOOL inspect "project name or absolute folder"
PYTHON TOOL prepare "project name or absolute folder" --mode both --work-dir /outside/project/work-unique
PYTHON TOOL preview /outside/project/work-unique
PYTHON TOOL apply /outside/project/work-unique
PYTHON TOOL restore "project name or absolute folder" --backup .codex-edit-YYYYMMDD-HHMMSS-microseconds.bak
PYTHON TOOL cleanup /outside/project/work-unique
```

Modes are both, silence, and subtitles. Default is both. Silence mode needs Python + FFmpeg only; captions also need a local speech engine and a usable installed font. Put `--config /absolute/config.json` **before** the subcommand to customize settings. An explicit project folder works even when default draft discovery does not.

Preparation writes only to its working directory. After transcribing the proposed timeline, words.json lists 1-based words, starts/ends in seconds, clip_cuts_us in integer microseconds, and a transcript_sha256. Have the agent compose semantic blocks in work-dir/subtitles.json:

```json
{
  "transcript_sha256": "copy the exact current words.json hash",
  "ranges": [[1, 5], [6, 10], [11, 14]],
  "replacements": {"7": "mastercard"}
}
```

Ranges are inclusive, in order, and must cover all words exactly once. The agent chooses phrase boundaries; a fixed every-six-words algorithm is not an acceptable substitute. Corrections must retain the spoken meaning. Each block must fit max_words after replacements. No fake transcript/hash/spec examples may be applied to a real project.

Preview validates captions without writing project files. It reports phrase text and adjusted start/end timestamps, with flags identifying aligned cut transitions. Review those timings against the clip cuts and semantic ownership, then apply within the user's existing edit request. A fingerprint mismatch means prepare again from the new timeline, not force-write. Apply verifies the original project still matches, requires CapCut to be closed, preserves pre-edit files, updates draft duration metadata, and writes identical full draft payloads. There is no universal CapCut schema: unrecognized structures must stop rather than be guessed.

Supported layouts: JSON draft_info.json or draft_content.json at the project root; optional single Timelines/<id> copies and full-draft template-2.tmp mirrors. If root and timeline mirrors coexist, they must already be byte-identical. All detected full copies stay byte-identical. Existing metadata duration fields tm_duration, duration, and draft_duration are updated when present. Other metadata is preserved.

Silence mode supports one video track with embedded audio, or one audio-only track. Cutting additional music, overlays, captions made by the user, or other timed tracks is refused to avoid accidental resynchronization. Previous codex_subtitles may be removed when recutting because their text/timing would be stale. Subtitle-only mode keeps other tracks. Speed changes, reversed clips, primary-clip keyframes, and existing transitions during cutting are unsupported.

Backups use exclusive creation with microsecond timestamps; older backups are never overwritten. capcut-backup<suffix>.json records file paths and checksums. restore checks this manifest, backs up the current state, then restores all listed files. A failed multi-file write attempts to recover originals; interruption or filesystem failure can still require restore. JSON edits across multiple files cannot be a single filesystem transaction. A leftover .capcut-editing.lock must not be deleted while another edit is running; after confirming no process is active, use the backup manifest to diagnose an interrupted operation.

No scripts operate the desktop, close CapCut, or export a final video. The editor must be closed before writes. Preparation or transcription failure leaves the original timeline untouched; apply errors include recovery status. Cleanup deletes only tool-owned working filenames, never arbitrary project/media files.
