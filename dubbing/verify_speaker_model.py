from pathlib import Path
import os,json
os.environ['HF_HUB_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
import torch,soundfile as sf
from pyannote.audio import Pipeline
root=Path(__file__).resolve().parent
torch.set_num_threads(4)
pipe=Pipeline.from_pretrained(str(root/'models/speaker-community-1'))
wav,sr=sf.read(str(root/'dub_work/verified-v2-auto_work/source.wav'),dtype='float32')
result=pipe({'waveform':torch.from_numpy(wav).unsqueeze(0),'sample_rate':sr})
turns=[{'start':float(t.start),'end':float(t.end),'speaker':str(s)} for t,s in result.speaker_diarization]
(root/'dub_work/speaker-model-test.json').write_text(json.dumps(turns,indent=2),encoding='utf-8')
print('Speaker model ran offline. Speakers:',len({t['speaker'] for t in turns}),'turns:',len(turns),flush=True)