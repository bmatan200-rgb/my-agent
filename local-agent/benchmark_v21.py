import requests,json,time,importlib.util
from pathlib import Path
root=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('engine',root/'action_engine.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
jobs=[
('translate',{'type':'object','properties':{'translation':{'type':'string'}},'required':['translation']},'Translate into fluent natural Hebrew, preserving the meaning and brand names. Return JSON translation only. English: Want to upgrade your shower routine? Salt and Stone body wash has a warm, earthy scent. The pump makes it easy to use. A generous 450 milliliters for everyday use.'),
('tool',e.schema(),'User asks in Hebrew: חפש בגוגל מחשבים ניידים. Choose the correct tool and arguments. Return JSON.'),
('clarify',e.schema(),'User asks: פתח את המייל שלי. No provider or website is known. Ask a brief clarification question in Hebrew using reply, do not guess a provider.')
]
report=[]
for label,fmt,prompt in jobs:
 start=time.monotonic()
 r=requests.post('http://127.0.0.1:11434/api/generate',json={'model':'qwen3:14b','prompt':prompt,'format':fmt,'think':False,'stream':False,'keep_alive':0,'options':{'num_predict':650,'num_ctx':4096,'temperature':0.1}},timeout=360)
 r.raise_for_status()
 data=r.json();report.append({'test':label,'seconds':round(time.monotonic()-start,1),'response':json.loads(data['response'])})
 (root/'model-v21-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(label,'completed',report[-1]['seconds'],flush=True)