from pathlib import Path
import subprocess,sys,json
from huggingface_hub import snapshot_download
root=Path(__file__).resolve().parent
env=root/'.venv-speakers'
log=root/'dub_work/setup-speakers.log'
with log.open('w',encoding='utf-8') as f:
 if not (env/'Scripts/python.exe').exists():
  subprocess.run([sys.executable,'-m','venv',str(env)],check=True,stdout=f,stderr=f)
 print('Speaker environment ready',flush=True)
 subprocess.run([str(env/'Scripts/python.exe'),'-m','pip','install','pyannote.audio>=4,<5'],check=True,stdout=f,stderr=f)
 print('Speaker dependencies installed',flush=True)
 snapshot_download('pyannote/speaker-diarization-community-1',local_dir=str(root/'models/speaker-community-1'))
 print('SPEAKER_MODEL_READY',flush=True)