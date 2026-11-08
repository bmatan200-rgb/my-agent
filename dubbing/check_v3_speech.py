from pathlib import Path
import json
from faster_whisper import WhisperModel
from movie_dub import project_path
r=Path(__file__).resolve().parent
video=Path.home()/'.personal-ai-agent/uploads/20261107-233904-edd21f7e.mp4'
p=project_path(video)
m=WhisperModel('small',device='cpu',compute_type='int8',local_files_only=True)
segments,_=m.transcribe(str(p/'dubbed.wav'),language='he',beam_size=5)
result={'intended':json.loads((p/'manifest.json').read_text(encoding='utf-8'))['segments'],'heard':' '.join(s.text for s in segments)}
(r/'dub_work/v3-readback.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('READBACK_READY')