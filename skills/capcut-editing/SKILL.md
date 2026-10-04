---
name: capcut-editing
description: "Edit local CapCut Desktop projects by name or folder: remove silent source-audio ranges, close timeline gaps, and add editable phrase-based subtitles. Use for combined editing, silence-only, or subtitle-only requests, including audio-only projects. Works through local files and commands; does not require GUI control."
---

# CapCut Editing

Use the packaged scripts relative to this SKILL.md, not a personal workspace or another CapCut skill. This is the original amplitude-based workflow. Defaults: FFmpeg -30 dB / 0.25 s; merge silence gaps <=0.12 s; discard kept slices <0.10 s; Turkish lowercase captions, usually 4–6 words, maximum 6, white with black stroke. User requests override configurable presentation and detection defaults.

## Setup and scope

Read [references/workflow.md](references/workflow.md) for commands and subtitle-spec details. Run scripts/setup.py with the platform-appropriate backend if needed, then use its reported virtualenv Python to run scripts/capcut_tool.py doctor. FFmpeg is a separate dependency. Use MLX Whisper on Apple Silicon, faster-whisper on Windows/Intel; use the common word-timestamp format produced by scripts/transcribe.py.

Resolve the exact project name or supplied path; require clarification only for a missing/ambiguous project. Inspect the current disk draft before every new request. Never reuse a prior transcript after user changes. Support single-timeline, forward 1.0x linear projects. The tool rejects encrypted drafts, inconsistent mirror copies, unsupported animated clips, and cutting a timeline with other populated user tracks. Subtitle-only operations preserve user tracks. Windows adaptation is experimental until verified in Windows CapCut; report that status honestly.

No computer/screen control is needed. Before apply/restore, CapCut must be closed so cached drafts cannot overwrite changes. If it is running, explain this specific blocker and request closure; never kill the app or discard unsaved edits. No mandatory manual review between cutting and captions.

## Execute the requested mode

- Combined request (for example, “sessiz kısımları kes ve altyazı ekle” or “konuşma olmayan kısımları kes ve altyazı ekle”): prepare --mode both, create semantic subtitle ranges, preview, then apply in the same request.
- “sessiz kısımları kes”, “konuşma olmayan kısımları kes”, or audio-only silence removal: prepare --mode silence, preview, apply. Do not add subtitles unless requested. Treat these as natural request variants while honestly stating the amplitude-based detection boundary if background noise matters.
- “altyazı ekle”: prepare --mode subtitles against the current disk timeline, create semantic ranges, preview, apply. Do not change the media cuts.

Use a fresh working directory outside the CapCut project and outside tracked package files. Preparation renders the proposed current timeline audio, transcribes it locally, and records file fingerprints without writing to the project. Read the resulting report and words.json. Run preview and resolve validation errors, then apply the user's authorized edit without adding a separate approval/review step. If source files changed, prepare and transcribe again. Apply commits all mirror copies together with timestamped backups and attempts recovery on failure. Report errors honestly, including backup paths if recovery is incomplete.

## Semantic captions and cut alignment

Build subtitles.json using the indexed current words.json; copy its transcript_sha256. Prefer meaningful 4–6 word phrases. Short complete phrases may have fewer words. Never pad text or strand a Turkish predicate alone solely to satisfy a word count. Split longer sentences at natural phrase boundaries. Lowercase Turkish I→ı, İ→i, including brands; remove terminal punctuation by default. Correct only obvious transcription errors supported by the audio/context via replacements; never invent speech or omit spoken words. When uncertain, listen to the rendered timeline audio using available local tools.

Keep subtitle blocks touching from 0 through the timeline end. For a new phrase associated with the right clip, examine its first word and current clip cuts. The tool snaps its start to a cut only when the word begins <=0.25 s before that cut and ends after it; the preceding block ends at the same cut. A word that ends before a cut or starts after it keeps its natural timestamp. Speech continuing across clips keeps natural phrase boundaries; do not force every cut to start a caption. Compare caption_starts in the preview to words.json cuts and verify the right clip's phrase does not appear over the left clip. Timing offsets are relative to the adjusted block start and clamped to the block bounds.

The resulting codex_subtitles track contains native CapCut type: subtitle materials, recognition/base/display text, Turkish language metadata, and word timings. Reruns replace only that track and its unshared materials. Keep user-created text tracks.

## Finish and customization

Report old/new/removed duration for cutting, caption count for subtitles, and the exact backup_suffix. Successful apply cleans temporary audio and transcripts. On failure, clean the managed work directory after diagnostics unless it is needed for an immediate retry. Mention that reopening CapCut reloads the disk changes. The result stays editable in CapCut; export is outside this skill.

For explicit preferences, use an external JSON configuration based on [references/config.example.json](references/config.example.json). Prepare again after changing settings. See [references/workflow.md](references/workflow.md) for restore. Do not claim amplitude detection identifies speech in background noise; assess settings conservatively when noise is mentioned.

When the user describes fan/traffic/music/microphone noise, discuss the recording and inspect a short local audio sample when available. Help revise the threshold, minimum silence duration, and minimum kept duration using that evidence. If the first pass clipped quiet word endings, restore the pre-edit backup before recutting with safer settings: another pass on an already cut timeline cannot recover deleted source ranges. Do not present noise handling as a universal automatic fix.
