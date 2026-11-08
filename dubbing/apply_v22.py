from pathlib import Path
import shutil,subprocess,os
r=Path(__file__).resolve().parent
p=r/'dub_8s.py'
shutil.copy2(p,r/'dub_8s.py.backup-v21')
s=p.read_text(encoding='utf-8')
s=s.replace('os.environ.get("TTS_NO_REF_AUDIO", "0")','os.environ.get("TTS_NO_REF_AUDIO", "1")')
s=s.replace('Diagnostic mode: synthesis without speaker reference.','Hebrew voice mode: original speaker identity is NOT preserved.')
compile(s,str(p),'exec')
p.write_text(s,encoding='utf-8')
env=os.environ.copy()
env['HF_HUB_OFFLINE']='1'
env['TRANSFORMERS_OFFLINE']='1'
with (r/'dub_work/v22-full.log').open('w',encoding='utf-8') as log:
 result=subprocess.run([str(r/'.venv-tts/Scripts/python.exe'),str(p),'--input',str(Path.home()/'.personal-ai-agent/uploads/20261107-233904-edd21f7e.mp4'),'--output',str(r/'dub_work/verified-v22.mp4')],env=env,stdout=log,stderr=log)
print('Pipeline exit:',result.returncode,flush=True)
if result.returncode==0:
 from faster_whisper import WhisperModel
 m=WhisperModel('small',device='cpu',compute_type='int8',local_files_only=True)
 segments,_=m.transcribe(str(r/'dub_work/verified-v22_work/hebrew.wav'),language='he',beam_size=5)
 (r/'dub_work/v22-readback.txt').write_text(' '.join(s.text for s in segments),encoding='utf-8')
 print('Readback saved',flush=True)