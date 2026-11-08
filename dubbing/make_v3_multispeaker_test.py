from pathlib import Path
import numpy as np,soundfile as sf,subprocess,json,os
r=Path(__file__).resolve().parent
voices=r/'models/english-test-voices'
audio=np.zeros(105*24000,dtype='float32')
events=[]
for start,voice in [(2,'male_1'),(15,'female_1'),(28,'male_2'),(41,'female_1'),(54,'male_1')]:
 x,sr=sf.read(str(voices/(voice+'.wav')),dtype='float32');assert sr==24000
 audio[start*sr:start*sr+len(x)]=x
 events.append({'start':start,'end':start+len(x)/sr,'source_voice':voice})
wav=r/'dub_work/multi-source.wav';sf.write(str(wav),audio,24000)
video=r/'dub_work/multi-source-105s.mp4'
subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=c=navy:s=640x360:r=10:d=105','-i',str(wav),'-c:v','libx264','-preset','ultrafast','-c:a','aac','-shortest',str(video)],check=True)
(r/'dub_work/multi-expected.json').write_text(json.dumps(events,indent=2),encoding='utf-8')
env=os.environ.copy();env['PYTHONIOENCODING']='utf-8'
with (r/'dub_work/v3-multi-analysis.log').open('w',encoding='utf-8') as log:
 proc=subprocess.run([str(r/'.venv-tts/Scripts/python.exe'),str(r/'movie_dub.py'),'--input',str(video),'--output',str(r/'dub_work/v3-multi.mp4'),'--translate-only'],env=env,stdout=log,stderr=subprocess.STDOUT)
print('MULTI_ANALYSIS_EXIT:',proc.returncode)