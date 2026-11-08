from pathlib import Path
import os,json,shutil,time,sys
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root))
import dub_8s as d
work=root/'dub_work/diagnostic_v22'
work.mkdir(exist_ok=True)
shutil.copy2(root/'dub_8s.py',work/'dub_8s_before.py')
d.REF_WAV=root/'dub_work/verified-v2-auto_work/reference.wav'
phrase='שלום לכולם. היום נבדוק יצירת דיבור ברור בעברית. תודה שהקשבתם.'
results=[]
for mode in ['reference','no_reference']:
 os.environ['TTS_NO_REF_AUDIO']='1' if mode=='no_reference' else '0'
 d.HEB_WAV=work/(mode+'.wav')
 import torch
 torch.manual_seed(42)
 d.synthesize('Want a more considered shower routine? Salt and Stone.',phrase,8)
 from faster_whisper import WhisperModel
 m=WhisperModel('small',device='cpu',compute_type='int8',local_files_only=True)
 segments,_=m.transcribe(str(d.HEB_WAV),language='he',beam_size=5)
 results.append({'mode':mode,'intended':phrase,'recognized':' '.join(s.text for s in segments)})
 del m
 (work/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
 print('FINISHED '+mode,flush=True)