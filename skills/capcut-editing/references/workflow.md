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

| User request | --mode | Requirements beyond Python/FFmpeg |
| --- | --- | --- |
| sessiz kısımları kes | silence | None; uses -30 dBFS amplitude detection |
| konuşmasız kısımları kes / konuşma olmayan kısımları kes | speech | CPU Silero VAD bundled with faster-whisper |
| altyazı ekle | subtitles | Transcription engine, model, installed font |
| sessiz kısımları kes ve altyazı ekle | both | Caption requirements |
| konuşmasız kısımları kes ve altyazı ekle | speech-subtitles | VAD and caption requirements |

Default is both for compatibility; agents must pass the mode matching the actual request. Put `--config /absolute/config.json` **before** the subcommand. An explicit project folder works even when default discovery does not.

Speech mode renders the current timeline at 16 kHz mono and scans it with Silero VAD (primary probability threshold 0.5). Every candidate gap of at least 0.30 s is reviewed at threshold 0.35 with 0.40 s of surrounding context. Long gaps are reviewed in windows of at most 30 s plus context. Quiet review audio is also scanned with analysis-only gain up to 4x; source audio volume is unchanged. Additional possible speech is kept. Retained speech gets 0.12 s padding at each edge; remaining gaps shorter than 0.30 s are preserved. These thresholds are speech probabilities, not dB values. Silence settings do not control speech mode.

Read speech-analysis.json before apply: keep_ranges_us, removed_ranges_us, strong speech_ranges_us, conservatively_protected_ranges_us, and gap_reviews show decisions on the original current timeline. Listen to uncertain ranges in speech-original.wav using available local audio tools when the recording or report warrants closer inspection. VAD detects background voices/singing too; speaker isolation is outside this mode. Missing dependencies or no detected speech stop preparation without deleting project content; never substitute amplitude detection.

Configure speech_threshold / speech_review_threshold (lower protects more possible speech), speech_padding (larger protects word edges), speech_min_gap (larger retains longer natural pauses), and speech_min_duration (minimum detected speech burst) from audio evidence. Silence uses noise_db, min_silence, merge_gap, and min_keep. Restore the pre-cut backup before preparing again to recover already removed words.

Preparation writes only to its working directory. Cutting alone does not transcribe or add captions. Caption modes transcribe the proposed timeline after any requested cutting; words.json lists 1-based words, starts/ends in seconds, clip_cuts_us in integer microseconds, and a transcript_sha256. Have the agent compose semantic blocks in work-dir/subtitles.json:

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

Both cutting methods support one video track with embedded audio, or one audio-only track. Cutting additional music, overlays, captions made by the user, or other timed tracks is refused to avoid accidental resynchronization. Previous codex_subtitles may be removed when recutting because their text/timing would be stale. Subtitle-only mode keeps other tracks. Speed changes, reversed clips, primary-clip keyframes, and existing transitions during cutting are unsupported.

Backups use exclusive creation with microsecond timestamps; older backups are never overwritten. capcut-backup<suffix>.json records file paths and checksums. restore checks this manifest, backs up the current state, then restores all listed files. A failed multi-file write attempts to recover originals; interruption or filesystem failure can still require restore. JSON edits across multiple files cannot be a single filesystem transaction. A leftover .capcut-editing.lock must not be deleted while another edit is running; after confirming no process is active, use the backup manifest to diagnose an interrupted operation.

No scripts operate the desktop, close CapCut, or export a final video. The editor must be closed before writes. Preparation or transcription failure leaves the original timeline untouched; apply errors include recovery status. Cleanup deletes only tool-owned working filenames, never arbitrary project/media files.
