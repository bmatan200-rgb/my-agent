from pathlib import Path
import subprocess,os
r=Path(__file__).resolve().parent
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
with (r/'dub_work/v3-multi-analysis.log').open('w',encoding='utf-8') as log:
 p=subprocess.run([str(r/'.venv-tts/Scripts/python.exe'),str(r/'movie_dub.py'),'--input',str(r/'dub_work/multi-source-105s.mp4'),'--output',str(r/'dub_work/v3-multi.mp4'),'--translate-only'],env=env,stdout=log,stderr=subprocess.STDOUT)
print('MULTI_ANALYSIS_EXIT:',p.returncode)