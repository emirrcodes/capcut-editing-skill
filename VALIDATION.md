# v0.1.0 validation

- 20 automated tests passed locally on an Apple Silicon Mac with Python 3.13 and FFmpeg.
- Skill frontmatter/package validation passed.
- A synthetic Turkish voice recording was processed with the installed MLX Whisper large-v3-turbo model using the real transcription adapter. Preparation cut 0.409 seconds of silence from 7.782 seconds, produced 12 timestamped words, and validated two six-word semantic subtitle blocks over the proposed 7.373-second timeline. Only temporary synthetic project files were involved.
- Automated tests exercise combined preparation/apply, four identical mirrors, alternate draft_content.json layouts, user-caption preservation, hard-cut timing, stale-input rejection, fault-injected recovery, checked restore, and all three local agent installers.
- The GitHub Actions matrix runs the same synthetic-project tests on macOS, Windows, and Linux. Check the latest workflow status separately; local results do not imply those jobs passed.
- Windows CapCut editor round-trip verification is pending. No claim is made that tests alone prove native editor compatibility across CapCut versions.
- No actual user project was edited during package development. The public asset contains only blank subtitle schema/style defaults.
