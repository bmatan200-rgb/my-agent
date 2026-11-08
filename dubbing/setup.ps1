$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "Creating separate Python 3.11 environment for local TTS..."
py -3.11 -m venv .venv-tts
$PY = Join-Path $PSScriptRoot ".venv-tts\Scripts\python.exe"
& $PY -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed' }
# CUDA-enabled Torch, with older NVIDIA cards supported by CUDA 12.6 builds.
& $PY -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu126
if ($LASTEXITCODE -ne 0) { throw 'PyTorch installation failed' }
& $PY -m pip install "f5-tts==1.1.22" faster-whisper soundfile huggingface_hub
if ($LASTEXITCODE -ne 0) { throw 'TTS installation failed' }
Write-Host "Installation complete. Run .\.venv-tts\Scripts\python.exe .\dub_8s.py" -ForegroundColor Green