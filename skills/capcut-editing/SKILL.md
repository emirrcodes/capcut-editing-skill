---
name: capcut-editing
description: "Edit local CapCut Desktop projects by name or folder: cut silence by audio level, cut non-speech using speech detection with gap review, and add editable phrase-based subtitles. Use separately or together, including audio-only projects. Works through local files and commands."
---

# CapCut Editing

Use the packaged scripts relative to this SKILL.md. Silence and non-speech are separate operations: FFmpeg -30 dB / 0.25 s for silence; local Silero VAD with a sensitive second pass over candidate gaps for non-speech. Default captions are Turkish lowercase, usually 4–6 words, maximum 6, white with black stroke. User requests override configurable presentation and detection defaults.

## Setup and scope

Read [references/workflow.md](references/workflow.md) for commands, speech review, and subtitle-spec details. Run scripts/setup.py if needed, then use its reported virtualenv Python to run scripts/capcut_tool.py doctor. FFmpeg is a separate dependency. CPU Silero VAD is installed on all platforms; transcription uses MLX Whisper on Apple Silicon or faster-whisper on Windows/Intel.

Resolve the exact project name or supplied path; require clarification only for a missing/ambiguous project. Inspect the current disk draft before every new request. Never reuse a prior transcript after user changes. Support single-timeline, forward 1.0x linear projects. The tool rejects encrypted drafts, inconsistent mirror copies, unsupported animated clips, and cutting a timeline with other populated user tracks. Subtitle-only operations preserve user tracks. Windows adaptation is experimental until verified in Windows CapCut; report that status honestly.

No computer/screen control is needed. Before apply/restore, CapCut must be closed so cached drafts cannot overwrite changes. If it is running, explain this specific blocker and request closure; never kill the app or discard unsaved edits. No mandatory manual review between cutting and captions.

## Execute the requested mode

- “sessiz kısımları kes”: prepare --mode silence, preview, apply. Detect low audio level with FFmpeg; do not add subtitles unless requested.
- “konuşmasız kısımları kes” / “konuşma olmayan kısımları kes”: prepare --mode speech, inspect speech-analysis.json and preview, apply. Scan for actual speech with VAD and review candidate gaps; never route this request to amplitude-only cutting or silently fall back when speech dependencies are missing.
- “altyazı ekle”: prepare --mode subtitles against the current disk timeline, create semantic ranges, preview, apply. Do not change the media cuts.
- Combined requests: silence + subtitles uses --mode both; non-speech + subtitles uses --mode speech-subtitles. Create semantic ranges from the newly cut timeline, preview, and apply in the same request.

Use a fresh working directory outside the CapCut project and tracked package files. Preparation records file fingerprints without writing to the project. Speech cutting scans the current timeline audio; caption modes transcribe the proposed timeline. Read the mode's report and words.json when generated. Run preview and resolve validation errors, then apply the user's authorized edit without adding a separate approval step. If source files changed, prepare again. Apply commits all mirror copies with timestamped backups and attempts recovery on failure.

## Semantic captions and cut alignment

Build subtitles.json using the indexed current words.json; copy its transcript_sha256. Prefer meaningful 4–6 word phrases. Short complete phrases may have fewer words. Never pad text or strand a Turkish predicate alone solely to satisfy a word count. Split longer sentences at natural phrase boundaries. Lowercase Turkish I→ı, İ→i, including brands; remove terminal punctuation by default. Correct only obvious transcription errors supported by the audio/context via replacements; never invent speech or omit spoken words. When uncertain, listen to the rendered timeline audio using available local tools.

Keep subtitle blocks touching from 0 through the timeline end. For a new phrase associated with the right clip, examine its first word and current clip cuts. The tool snaps its start to a cut only when the word begins <=0.25 s before that cut and ends after it; the preceding block ends at the same cut. A word that ends before a cut or starts after it keeps its natural timestamp. Speech continuing across clips keeps natural phrase boundaries; do not force every cut to start a caption. Compare caption_starts in the preview to words.json cuts and verify the right clip's phrase does not appear over the left clip. Timing offsets are relative to the adjusted block start and clamped to the block bounds.

The resulting codex_subtitles track contains native CapCut type: subtitle materials, recognition/base/display text, Turkish language metadata, and word timings. Reruns replace only that track and its unshared materials. Keep user-created text tracks.

## Finish and customization

Report old/new/removed duration for cutting, caption count for subtitles, and the exact backup_suffix. Successful apply cleans temporary audio and transcripts. On failure, clean the managed work directory after diagnostics unless it is needed for an immediate retry. Mention that reopening CapCut reloads the disk changes. The result stays editable in CapCut; export is outside this skill.

For explicit preferences, use an external JSON configuration based on [references/config.example.json](references/config.example.json). Prepare again after changing settings. See [references/workflow.md](references/workflow.md) for restore and separate silence/speech controls.

When noise or clipped speech is mentioned, inspect the current audio and the candidate removed/protected ranges, especially uncertain intervals. Help revise the selected mode's settings using that evidence. Lower VAD thresholds protect more possible speech; more padding protects word edges. VAD may retain background voices or singing and does not isolate the intended speaker. If a pass clipped words, restore the pre-edit backup before recutting: another pass cannot recover removed source ranges. A no-speech result stops without deleting the entire timeline.
