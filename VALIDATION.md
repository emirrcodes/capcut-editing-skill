# v0.2.0 validation

- 27 automated tests passed locally on an Apple Silicon Mac with Python 3.12 and FFmpeg. The real bundled Silero VAD rejected generated stationary noise above the -30 dBFS silence threshold, with no Whisper model download.
- Speech-mode tests cover sensitive gap review, weak-speech protection, padding, short natural pauses, long-gap windows, missing-dependency refusal, no-speech refusal, separate caption/cutting modes, identical draft mirrors, and speech-cut backup restoration.
- A synthetic Turkish voice mixed with fan-like background noise at -25.19 dBFS was processed using real CPU Silero VAD. The amplitude method removed 0 seconds; speech scanning removed 5.501 seconds from 12.749 seconds, leaving 7.248 seconds. Three candidate gaps were reviewed, protecting three additional speech-edge regions.
- The proposed noisy-recording timeline was transcribed by the real local MLX Whisper large-v3-turbo adapter. All 12 synthesized Turkish words were present, and two semantic six-word subtitle blocks passed timing/schema validation over the new 7.248-second timeline.
- Skill frontmatter/package validation passed. Transcription adapters, preserved user text tracks, cut alignment, stale-input rejection, fault-injected recovery, alternate draft layouts, and all three agent installers remain covered.
- The GitHub Actions matrix runs the synthetic-project suite, including the bundled CPU VAD test, on macOS, Windows, and Linux. Check the workflow status for the release commit separately; local results do not imply those jobs passed.
- Windows CapCut editor round-trip verification is pending. Tests do not prove native editor compatibility across CapCut versions.
- No actual user CapCut project was edited during development. All media/drafts used in tests were temporary synthetic artifacts; none are distributed.
