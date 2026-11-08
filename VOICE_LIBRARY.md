# Offline Hebrew dubbing voice library — version 3.1

The local Windows agent now includes a **32-option selectable voice catalog**:
16 licensed Hebrew source recordings from Google FLEURS (8 male / 8 female) plus
16 **synthetic character-style voice presets** (cartoon child, comedy, fairy,
monster, robot, hero, villain, wizard, narrator, etc.). These are not separate
professional actors and not clones of existing cartoon characters.

Base recording attribution: **Google FLEURS**, CC BY 4.0,
https://huggingface.co/datasets/google/fleurs
FLEURS (Conneau et al., 2022): https://arxiv.org/abs/2205.12446
If distributing generated derivative audio, retain appropriate attribution and
review the dataset and model terms. Only source code is in GitHub; WAV files and
model weights remain on the local computer.

### Workflow
1. Upload a video in the agent UI.
2. Click Prepare translation.
3. Review the Hebrew text. Choose **Auto**, **Animation**, **Live Action**, or
   **Mixed** for the overall video, and select a distinct voice for each speaker.
4. Edit Hebrew text, then click Dub. Changes trigger regeneration only for
   changed segments/changed voice IDs; the original background stem is reused.
5. The engine runs offline through local F5-TTS and FFmpeg.

Automatic animation detection is a **conservative visual heuristic**, not a
trained scene classifier. It may miss 3D animation or stylized content and
cannot reliably identify fictional characters, performance age or emotions.
Use manual style and voice selection for quality control. Mixed videos can be
set manually, but automatic scene-by-scene voice/style changes are not implemented.

### Local test
Use the dubbing venv Python for full audio tests:
`<video-dubbing-local>/.venv-tts/Scripts/python.exe -m unittest discover -s tests -v`
from `local-agent/`. 17 tests passed on Windows, including audio filters.
A 20.455-second cartoon-voice render passed, and a preview job via the local
agent HTTP API exposed the 32 choices and accepted a manual voice map.

### Restore
See `backup/pre-voice-library-20261108` for the previous commit. The source
backup was also kept locally in `~/.personal-ai-agent/backups/`.
