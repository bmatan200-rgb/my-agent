from pathlib import Path
import subprocess,os
r=Path(__file__).resolve().parent
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
with (r/'dub_work/v3-render.log').open('w',encoding='utf-8') as log:
 p=subprocess.run([str(r/'.venv-tts/Scripts/python.exe'),str(r/'movie_dub.py'),'--input',str(Path.home()/'.personal-ai-agent/uploads/20261107-233904-edd21f7e.mp4'),'--output',str(r/'dub_work/v3-sample.mp4'),'--hebrew-override',str(r/'dub_work/v3-sample_work/translation.txt')],env=env,stdout=log,stderr=subprocess.STDOUT)
print('RENDER_RETURN_CODE:',p.returncode)