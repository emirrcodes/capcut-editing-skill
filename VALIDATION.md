# v0.3.0 validation

- 41 automated tests passed locally on Apple Silicon with Python 3.12 and FFmpeg; skill package/frontmatter validation passed.

- The new regressions reproduce a long keep range leaving 3 ms at an existing clip boundary, pre-existing short clips, one-frame output clips, safe additional source-audio retention, and post-write validation failure with rollback of all copies.
- Speech-word tests exercise weak-word/VAD disagreement, stretched timestamps, short intra-word pauses, high compression-ratio repetitions, bounded independent rechecks, unresolved-range protection, cut-only behavior, and temporary transcript cleanup. Both transcription adapters preserve decoding-quality metadata and normalized timestamps.
- A temporary synthetic Turkish voice with fan-like noise at -25.19 dBFS was processed by real CPU Silero VAD and cached local MLX Whisper large-v3-turbo. Word review was enabled with an explicitly tighter 80 ms gap / 40 ms padding configuration. It retained 12 recognized words, removed 3.748 s from 12.749 s, and produced a 9.001 s proposed timeline without captions. The shortest output clip was exactly 100 ms; 97 ms of extra boundary audio prevented a three-millisecond fragment.
- That recording exposed a stretched first-word timestamp extending into leading noise. Word review conservatively retained extra noise; long word intervals are now reported for audio inspection. The optional cross-check is not proof of exact phoneme boundaries, perfect noise removal, or intended-speaker isolation.
- The provided live-edit report informed synthetic regressions and instructions; the real user project and its private report/media are not included or edited by this update. No native CapCut round-trip was performed during this change.
- The GitHub Actions matrix runs the synthetic suite on macOS, Windows and Linux. Check the release commit's workflow result; local tests alone do not establish CI or native editor compatibility.
- Native Windows CapCut round-trip validation remains pending.
