from pathlib import Path
import subprocess,shutil
r=Path(__file__).resolve().parent
p=r/'dub_work/verified-voice-lock.mp4'
result=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(p)],capture_output=True,text=True,check=True)
assert 20<float(result.stdout)<21
shutil.copy2(r/'dub_8s.py',r/'dub_8s.py.backup-before-voice-lock')
shutil.copy2(r/'dub_voice_lock.py',r/'dub_8s.py')
shutil.copy2(p,Path.home()/'OneDrive/שולחן העבודה/dubbing-voice-lock-preview.mp4')
print('Installed. Preview copied to Desktop. Duration:',result.stdout.strip())