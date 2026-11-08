from pathlib import Path
import os,json,argparse
os.environ['HF_HUB_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
os.environ['PYANNOTE_METRICS_ENABLED']='0'

def main():
 import torch,soundfile as sf
 from pyannote.audio import Pipeline
 p=argparse.ArgumentParser();p.add_argument('audio');p.add_argument('output');a=p.parse_args()
 root=Path(__file__).resolve().parent
 torch.set_num_threads(4)
 pipeline=Pipeline.from_pretrained(str(root/'models/speaker-community-1'))
 audio,sr=sf.read(a.audio,dtype='float32')
 if sr!=16000 or audio.ndim!=1:raise ValueError('Expected mono 16 kHz audio')
 print('מזהה דוברים לאורך הסרטון...',flush=True)
 out=pipeline({'waveform':torch.from_numpy(audio).unsqueeze(0),'sample_rate':sr})
 def turns(annotation):return [{'start':float(t.start),'end':float(t.end),'speaker':str(s)} for t,s in annotation]
 data={'turns':turns(out.exclusive_speaker_diarization),'raw_turns':turns(out.speaker_diarization)}
 dest=Path(a.output);tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(data),encoding='utf-8');os.replace(tmp,dest)
 print('זיהוי הדוברים הושלם',flush=True)
if __name__=='__main__':main()