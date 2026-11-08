import os,subprocess
from pathlib import Path
root=Path.home()/'video-dubbing-local'
env=os.environ.copy()
env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',PYTHONIOENCODING='utf-8')
cmd=[str(root/'.venv-tts/Scripts/python.exe'),str(root/'dub_8s.py'),'--input',str(Path.home()/'.personal-ai-agent/uploads/20261107-233904-edd21f7e.mp4'),'--output',str(root/'dub_work/verified-v2-auto.mp4')]
log=root/'dub_work/verified-v2-auto.log'
with log.open('w',encoding='utf-8') as out:
 result=subprocess.run(cmd,env=env,stdout=out,stderr=subprocess.STDOUT,timeout=1800)
print('AUTO DUB EXIT:',result.returncode,'LOG:',log,flush=True)
if result.returncode:print(log.read_text(encoding='utf-8')[-3000:]);raise SystemExit(result.returncode)
subprocess.run(['ffprobe','-v','error','-show_entries','stream=codec_type,duration','-of','json',str(root/'dub_work/verified-v2-auto.mp4')],check=True)