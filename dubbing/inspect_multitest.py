from movie_dub import project_path
from pathlib import Path
import soundfile as sf,numpy as np
r=Path(__file__).resolve().parent
p=project_path(r/'dub_work/multi-source-105s.mp4')
print((p/'speakers.json').read_text())
print((p/'asr-0000.json').read_text())
for f in (r/'models/english-test-voices').glob('*.wav'):
 x,sr=sf.read(f);print(f.name,'rms',float(np.sqrt(np.mean(x*x))),'peak',float(np.max(abs(x))))