from pathlib import Path
import requests,zipfile,io,tarfile,json,re
import soundfile as sf
from scipy.signal import resample_poly
root=Path(__file__).resolve().parent
dest=root/'models/hebrew-voices';dest.mkdir(parents=True,exist_ok=True)
rev='ab9a4b3b06dd4c34e86e048ad3ad84f7b149af5e'
u=f'https://huggingface.co/datasets/google/fleurs/resolve/{rev}/data/metadata.zip'
r=requests.get(u,timeout=90);r.raise_for_status()
rows={}
with zipfile.ZipFile(io.BytesIO(r.content)) as z:
 for name in z.namelist():
  if '/he_il/' not in name or not name.endswith('.tsv'):continue
  for line in z.read(name).decode('utf-8').splitlines():
   v=line.split('\t')
   if len(v)!=7:continue
   idx,filename,raw,trans,_,n,gender=v
   if gender not in ('MALE','FEMALE') or not 3<=int(n)/16000<=8 or re.search(r'[0-9A-Za-z]',raw):continue
   rows[filename]={'source_file':filename,'text':raw,'type':gender.lower(),'seconds':int(n)/16000}
print('Metadata ready',len(rows),flush=True)
count={'male':0,'female':0};voices=[]
u='https://storage.googleapis.com/xtreme_translations/FLEURS102/he_il.tar.gz'
with requests.get(u,stream=True,timeout=(30,120)) as r:
 r.raise_for_status()
 with tarfile.open(fileobj=r.raw,mode='r|gz') as tar:
  for item in tar:
   name=Path(item.name).name
   if name not in rows or not item.isfile():continue
   row=rows[name];kind=row['type']
   if count[kind]>=8:continue
   audio,sr=sf.read(io.BytesIO(tar.extractfile(item).read()),dtype='float32')
   if audio.ndim>1:audio=audio.mean(axis=1)
   if sr!=16000:continue
   vid=kind+'_'+str(count[kind]+1)
   sf.write(str(dest/(vid+'.wav')),resample_poly(audio,3,2),24000,subtype='PCM_16')
   voices.append(dict(row,id=vid,file=vid+'.wav'))
   count[kind]+=1
   print('Saved',vid,flush=True)
   if min(count.values())>=8:break
if min(count.values())<2:raise RuntimeError('Insufficient voice samples')
manifest={'source':'Google FLEURS Hebrew','license':'CC-BY-4.0','source_url':'https://huggingface.co/datasets/google/fleurs','voices':voices}
(dest/'candidates.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print('VOICE_CANDIDATES_READY',count,flush=True)