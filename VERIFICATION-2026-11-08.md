# Verification snapshot — 2026-11-08

## Checked on Windows locally
- `py -3.11 -m unittest discover -s tests -v`: **11/11 passed**.
- Production agent UI: HTTP 200; local sync-status endpoint: HTTP 200.
- Unauthorized dubbing start without explicit confirmation: HTTP 403.
- Confirmed dubbing request for nonexistent upload: HTTP 404.
- Local 20.455-second video: ASR, Hebrew translation preview and speaker identification completed.
- End-to-end Hebrew dubbing from a manually edited six-segment translation completed; video duration 20.455 seconds, H.264 video and AAC audio. Audio had measurable nonzero signal.
- After changing only the first translation segment, second render completed. The speech cache grew from six to **seven** WAV files, while unchanged segments were reused. Both output files existed and differed.

## Not yet verified or fixed
- Stability over complete long movies (hours, large media files) is **not proven** by these short tests.
- Previous long-form dubbing attempts have hit overlong spoken text in a short segment, and a conflicting concurrent processing lock. These still require regression tests and recovery/error handling.
- Voice-library upgrades (animation/live action classification, expressive character voice matching) **have not been started**. Do not merge those features until the current pipeline has passed longer, repeatable test cases.

## Backup scope
This public repository includes source and test code only. It excludes personal configuration, auth tokens, datasets, model weights, audio reference samples, generated media, messages and memory files. `local-agent/agent.py` and `dubbing/movie_dub.py` are the active entry points. The original root-level examples remain for history.
