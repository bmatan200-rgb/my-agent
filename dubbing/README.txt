Hebrew local dubbing proof of concept (experimental)

Copy dub_8s.py and setup.ps1 into:
%USERPROFILE%\video-dubbing-local
The file test.mp4 must also be in that directory.

1. In PowerShell, cd $HOME\video-dubbing-local
2. Run: .\setup.ps1
   If PowerShell script execution is blocked, run:
   powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
   Review local scripts before running them.
3. Run: .\.venv-tts\Scripts\python.exe .\dub_8s.py
4. If successful, open dubbed_he_8s.mp4

Requirements:
- Ollama qwen3:8b running locally on 127.0.0.1:11434.
- ffmpeg on PATH.
- Python 3.11 installed.
- Internet only for initially downloading models; inference is local.
- This creates its own environment and never modifies the existing .venv.

Caveats:
- This is an experimental eight-second first-pass test, NOT a guaranteed
  production dubbing pipeline. Model compatibility is not verified on your PC.
- Source English audio is used as reference; voice resemblance may be weak.
- It replaces all audio including music for the first test.
- First model downloads may take gigabytes. No API charges.
- Use only voices you have permission to clone.