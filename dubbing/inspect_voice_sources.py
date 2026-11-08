import requests,json
url='https://datasets-server.huggingface.co/rows'
r=requests.get(url,params={'dataset':'google/fleurs','config':'he_il','split':'test','offset':0,'length':30},timeout=60)
print('STATUS:',r.status_code)
data=r.json()
from pathlib import Path
p=Path(__file__).resolve().parent/'dub_work/voice-source-rows.json'
p.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
print('FEATURES:',json.dumps(data.get('features',[]),ensure_ascii=False))
for x in data.get('rows',[])[:3]:
 row=x['row'];print({k:v for k,v in row.items() if k not in ('audio',)})