from pathlib import Path
import json,time
from transformers import MarianMTModel,MarianTokenizer
root=Path.home()/'video-dubbing-local'
model_id='Helsinki-NLP/opus-mt-en-he'
t=MarianTokenizer.from_pretrained(model_id)
m=MarianMTModel.from_pretrained(model_id)
texts=["Want to upgrade your shower routine?","Salt and Stone body wash has a warm, earthy scent.","The pump makes it easy to use.","A generous 450 milliliters for everyday use."]
start=time.monotonic()
result=t.batch_decode(m.generate(**t(texts,return_tensors='pt',padding=True),num_beams=4,max_new_tokens=160),skip_special_tokens=True)
target=root/'models/opus-en-he'
m.save_pretrained(target);t.save_pretrained(target)
(root/'dub_work/opus-test.json').write_text(json.dumps({'seconds':time.monotonic()-start,'source':texts,'translation':result},ensure_ascii=False,indent=2),encoding='utf-8')
print('Translation model cached and tested',flush=True)