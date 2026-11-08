from pathlib import Path
import os,json
os.environ['HF_HUB_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
import torch,numpy as np,soundfile as sf
from scipy.signal import resample_poly
from pyannote.audio.pipelines.speaker_verification import PretrainedSpeakerEmbedding
r=Path(__file__).resolve().parent
torch.set_num_threads(4)
embed=PretrainedSpeakerEmbedding(str(r/'models/speaker-community-1/embedding'),device=torch.device('cpu'))
root=r/'models/hebrew-voices'
data=json.loads((root/'candidates.json').read_text(encoding='utf-8'))
chosen=[];vectors=[]
for v in data['voices']:
 x,sr=sf.read(str(root/v['file']),dtype='float32')
 x=resample_poly(x,2,3)
 e=embed(torch.from_numpy(x).reshape(1,1,-1))[0]
 e=e/np.linalg.norm(e)
 same=[float(e@z) for w,z in zip(chosen,vectors) if w['type']==v['type']]
 print(v['id'],'closest cosine',round(max(same),3) if same else None,flush=True)
 if same and max(same)>.72:continue
 if sum(w['type']==v['type'] for w in chosen)>=4:continue
 chosen.append(v);vectors.append(e)
data['voices']=chosen
(root/'voices.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('SELECTED:',[v['id'] for v in chosen],flush=True)