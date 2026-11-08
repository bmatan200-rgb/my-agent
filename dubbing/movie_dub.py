"""Local timeline-preserving Hebrew dubbing with per-speaker voices and checkpoints."""
from pathlib import Path
import os,sys,json,re,hashlib,subprocess,argparse,math,shutil,time,gc
from voice_library import catalog, choose, transform_audio, estimate_film_style
ROOT=Path(__file__).resolve().parent
VERSION='movie-2'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'

def atomic(path,data):
 path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp')
 tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)
def read(path,default=None):
 return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default
def run(args):subprocess.run([str(x) for x in args],check=True)
def extract(video,dest,sr=16000):
 tmp=dest.with_suffix('.tmp.wav')
 run(['ffmpeg','-v','error','-y','-i',video,'-vn','-ac',1,'-ar',sr,tmp]);os.replace(tmp,dest)
def duration(video):
 return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(video)],text=True))
def project_path(video):
 st=video.stat();key=f'{VERSION}|{video.resolve()}|{st.st_size}|{st.st_mtime_ns}'
 return Path.home()/'.personal-ai-agent/dub_projects'/hashlib.sha256(key.encode()).hexdigest()[:24]
def speaker_at(start,end,turns):
 candidates=[t for t in turns if t['end']>start and t['start']<end]
 if candidates:return max(candidates,key=lambda t:min(t['end'],end)-max(t['start'],start))['speaker']
 if not turns:raise RuntimeError('לא זוהו דוברים בשמע')
 return min(turns,key=lambda t:abs((t['start']+t['end'])/2-(start+end)/2))['speaker']
def make_segments(words,turns):
 result=[];current=None
 for w in words:
  text=w['word'].strip()
  if not text:continue
  speaker=speaker_at(w['start'],w['end'],turns)
  if current and (speaker!=current['speaker'] or w['end']-current['start']>9 or w['start']-current['end']>0.7):
   result.append(current);current=None
  if current is None:current={'start':w['start'],'end':w['end'],'speaker':speaker,'source':text}
  else:current['end']=w['end'];current['source']+=' '+text
  if re.search(r'[.!?]$',text) and current['end']-current['start']>1.5:result.append(current);current=None
 if current:result.append(current)
 for i,s in enumerate(result):s['id']=f'{i+1:05d}'
 return result

def transcribe(wav,project,seconds,turns):
 import soundfile as sf,numpy as np
 from faster_whisper import WhisperModel
 model=WhisperModel('small',device='cpu',compute_type='int8',local_files_only=True)
 islands=[]
 for t in sorted(turns,key=lambda t:t['start']):
  if islands and t['start']-islands[-1][1]<0.45:islands[-1][1]=max(islands[-1][1],t['end'])
  else:islands.append([t['start'],t['end']])
 windows=[]
 for a,b in islands:
  for k in range(max(1,math.ceil((b-a)/25))):windows.append((a+k*25,min(b,a+(k+1)*25)))
 words=[]
 for i,(start,end) in enumerate(windows):
  key=hashlib.sha256(f'asr2|{start}|{end}'.encode()).hexdigest()[:20]
  cache=project/f'asr-{key}.json';rows=read(cache)
  if rows is None:
   left=max(0,start-.25);right=min(seconds,end+.25)
   with sf.SoundFile(wav) as f:f.seek(round(left*16000));audio=f.read(round((right-left)*16000),dtype='float32')
   rms=float(np.sqrt(np.mean(audio*audio)));peak=float(np.max(np.abs(audio)))
   if rms<1e-6:rows=[]
   else:
    audio=audio*min(100,0.10/rms,.95/max(peak,1e-6))
    segs,_=model.transcribe(audio,language='en',beam_size=5,word_timestamps=True,vad_filter=False,condition_on_previous_text=False)
    rows=[]
    for seg in segs:
     for w in seg.words or []:
      a=left+w.start;b=left+w.end
      if start-.15<=(a+b)/2<end+.15:rows.append({'start':max(0,a),'end':min(b,seconds),'word':w.word})
   atomic(cache,rows)
  words.extend(rows);print(f'תמלול קטע דיבור {i+1}/{len(windows)}',flush=True)
  print(f'DUB_PROGRESS|transcribe|{i+1}|{len(windows)}|{time.time():.3f}',flush=True)
 del model;gc.collect()
 return sorted(words,key=lambda w:w['start'])

def translate(segments,project):
 import torch
 from transformers import MarianMTModel,MarianTokenizer
 path=ROOT/'models/opus-en-he'
 tokenizer=MarianTokenizer.from_pretrained(str(path),local_files_only=True)
 model=MarianMTModel.from_pretrained(str(path),local_files_only=True).eval();torch.set_num_threads(4)
 cache=read(project/'translations.json',{})
 glossary=read(ROOT/'translation_glossary.json',[])
 for i,s in enumerate(segments):
  key=hashlib.sha256(s['source'].encode()).hexdigest()
  if key not in cache:
   tokens=tokenizer(s['source'],return_tensors='pt')
   if tokens['input_ids'].shape[-1]>400:raise ValueError('קטע תמלול ארוך מדי לתרגום')
   with torch.inference_mode():out=model.generate(**tokens,num_beams=4,max_new_tokens=400)
   text=tokenizer.decode(out[0],skip_special_tokens=True).strip()
   if not re.search('[א-ת]',text):raise ValueError('לא הופק תרגום עברי; יש לבדוק את קטע המקור')
   for e in glossary:
    if e.get('source','').lower() in s['source'].lower():
     for v in e.get('variants',[]):text=text.replace(v,e['hebrew'])
   cache[key]=text;atomic(project/'translations.json',cache)
  s['hebrew']=cache[key]
  print(f'תרגום קטע {i+1}/{len(segments)}',flush=True)
  print(f'DUB_PROGRESS|translate|{i+1}|{len(segments)}|{time.time():.3f}',flush=True)
 del model,tokenizer;gc.collect()
 return segments

def classify_speakers(wav,turns,bank):
 import torch,numpy as np,soundfile as sf
 from transformers import Wav2Vec2ForSequenceClassification,Wav2Vec2FeatureExtractor
 path=ROOT/'models/voice-type'
 model=Wav2Vec2ForSequenceClassification.from_pretrained(str(path),local_files_only=True).eval()
 processor=Wav2Vec2FeatureExtractor.from_pretrained(str(path),local_files_only=True)
 used=set();speakers=[];torch.set_num_threads(4)
 for sid in sorted({t['speaker'] for t in turns}):
  samples=sorted([t for t in turns if t['speaker']==sid and t['end']-t['start']>=1],key=lambda t:t['end']-t['start'],reverse=True)[:3]
  scores=[]
  for t in samples:
   with sf.SoundFile(wav) as f:f.seek(round(t['start']*16000));x=f.read(round(min(6,t['end']-t['start'])*16000),dtype='float32')
   inp=processor(x,sampling_rate=16000,return_tensors='pt',padding=True)
   with torch.inference_mode():scores.append(model(**inp).logits.softmax(-1)[0].numpy())
  if scores:
   avg=np.mean(scores,axis=0);idx=int(avg.argmax());kind=model.config.id2label[idx].lower();confidence=float(avg[idx])
  else:kind='unknown';confidence=0.0
  options=[v for v in bank if v['type']==kind and v['id'] not in used]
  voice=options[0]['id'] if options and confidence>=0.8 else ''
  if voice:used.add(voice)
  speakers.append({'id':sid,'suggested_type':kind,'confidence':round(confidence,3),'voice_id':voice})
 del model,processor;gc.collect()
 return speakers

def review_text(segments):
 return '\n'.join(f"[{s['id']}|{s['speaker']}] {s['hebrew']}" for s in segments)
def apply_review(segments,text,speakers):
 lines={}
 for line in text.splitlines():
  if not line.strip():continue
  m=re.fullmatch(r'\[(\d{5})\|(SPEAKER_\d+)\]\s*(.*)',line.strip())
  if not m:raise ValueError('יש לשמור את מספרי הקטעים והדוברים בסוגריים בתחילת כל שורה')
  key,sid,he=m.groups()
  if key in lines or sid not in speakers:raise ValueError('מספר קטע כפול או דובר לא מוכר')
  if he and (not re.search('[א-ת]',he) or re.search('[\u0600-\u06ff]',he)):raise ValueError('יש להזין טקסט עברי תקין')
  if len(he)>1000:raise ValueError('טקסט ארוך מדי בקטע בודד')
  lines[key]=(sid,he)
 if set(lines)!={s['id'] for s in segments}:raise ValueError('חסרים מספרי קטעים; כדי להשמיט דיבור השאר את תוכן השורה ריק')
 result=[]
 for s in segments:
  row=dict(s);row['speaker'],row['hebrew']=lines[s['id']];result.append(row)
 return result

class HebrewVoiceEngine:
 def __init__(self,bank):
  import torch
  from huggingface_hub import hf_hub_download
  from f5_tts.model import DiT
  from f5_tts.infer.utils_infer import load_model,load_vocoder
  from phonikud_onnx import Phonikud
  self.torch=torch;self.device='cuda' if torch.cuda.is_available() else 'cpu';self.bank={v['id']:v for v in bank};self.refs={}
  self.phonikud=Phonikud(str(ROOT/'models/phonikud/phonikud-1.0.int8.onnx'))
  ckpt=hf_hub_download('Yzamari/f5tts-hebrew-v2','model.safetensors',local_files_only=True)
  vocab=hf_hub_download('Yzamari/f5tts-hebrew-v2','vocab.txt',local_files_only=True)
  self.vocab=set(Path(vocab).read_text(encoding='utf-8').splitlines())
  cfg=dict(dim=1024,depth=22,heads=16,ff_mult=2,text_dim=512,text_mask_padding=True,conv_layers=4,pe_attn_head=None)
  self.model=load_model(DiT,cfg,ckpt,vocab_file=vocab,use_ema=False,device='cpu').to(device=self.device,dtype=torch.float32).eval()
  self.vocoder=load_vocoder(vocoder_name='vocos',device=self.device).to(dtype=torch.float32).eval()
 def vocalize(self,text):
  from num2words import num2words
  text=re.sub(r'\d+',lambda m:num2words(int(m.group()),lang='he') if len(m.group())<10 else ' '.join(num2words(int(c),lang='he') for c in m.group()),text)
  text=text.replace('"','').replace('״','').replace('־','-')
  text=self.phonikud.add_diacritics(text).replace('|','')
  unknown=set(text)-self.vocab
  if unknown:raise ValueError('יש תווים לא נתמכים בטקסט: '+repr(''.join(sorted(unknown))))
  return text
 def synthesize(self,text,voice,seconds,seed):
  import soundfile as sf,numpy as np
  from f5_tts.model.utils import convert_char_to_pinyin
  t=self.torch
  if voice not in self.refs:
   v=self.bank[voice];x,sr=sf.read(str(ROOT/'models/hebrew-voices'/v['file']),dtype='float32')
   if sr!=24000:raise ValueError('Voice reference sample rate mismatch')
   peak=float(np.max(np.abs(x)));rms=float(np.sqrt(np.mean(x*x)))
   if rms<1e-5:raise ValueError('Silent voice reference')
   x=x*min(0.12/rms,0.95/max(peak,1e-6))
   self.refs[voice]=(t.from_numpy(x).unsqueeze(0).to(self.device),self.vocalize(v['text']))
  ref,reftext=self.refs[voice];frames=ref.shape[-1]//256
  # Allow slightly longer synthesis for dense translated speech; fit to timeline afterward.
  target=max(0.8,seconds,len(text.split())/4.5)
  modeltext=self.vocalize(text)
  t.manual_seed(seed)
  with t.inference_mode():
   mel,_=self.model.sample(cond=ref,text=convert_char_to_pinyin([reftext.rstrip('. ') + '. '+modeltext]),duration=frames+round(target*24000/256),steps=32,cfg_strength=2.0,sway_sampling_coef=-1.0,no_ref_audio=False)
   if not t.isfinite(mel).all() or float(mel.abs().max())>100:raise ValueError('יצירת שמע לא יציבה')
   x=self.vocoder.decode(mel[:,frames:,:].permute(0,2,1).float()).squeeze().cpu().numpy()
  if not np.isfinite(x).all() or float(np.std(x))<1e-5:raise ValueError('נוצר שמע לא תקין')
  x=x*min(0.12/max(float(np.sqrt(np.mean(x*x))),1e-6),0.95/max(float(np.max(np.abs(x))),1e-6))
  n=round(seconds*24000)
  if len(x)>n:
   from scipy.signal import resample_poly
   x=resample_poly(x,n,len(x))
  x=np.pad(x[:n],(0,max(0,n-len(x))))
  fade=min(120,len(x)//2);x[:fade]*=np.linspace(0,1,fade);x[-fade:]*=np.linspace(1,0,fade)
  if self.device=='cuda':t.cuda.empty_cache()
  return x

def background_track(video,project,seconds):
 """Get a reusable stereo non-vocal stem of the original film, locally."""
 stems_dir=project/'background_stems'
 source=project/'background-source.wav'
 bg=stems_dir/'htdemucs'/'background-source'/'no_vocals.wav'
 if bg.is_file() and bg.stat().st_size>1024:
  if abs(duration(bg)-seconds)<=1: 
   print('צלילי הרקע נטענו מהמטמון',flush=True)
   print(f'DUB_PROGRESS|background|1|1|{time.time():.3f}',flush=True)
   return bg
 print(f'DUB_PROGRESS|background|0|1|{time.time():.3f}',flush=True)
 # Use a lossless stereo copy so effects are not collapsed to mono.
 if not source.is_file() or abs(duration(source)-seconds)>1:
  temp=project/'background-source.tmp.wav'
  run(['ffmpeg','-v','error','-y','-i',video,'-vn','-ac','2','-ar','44100','-c:a','pcm_s16le',temp])
  os.replace(temp,source)
 python=sys.executable
 base=[python,'-m','demucs.separate','--two-stems','vocals',
       '-n','htdemucs','--segment','7','--overlap','0.1','--shifts','0',
       '--float32','--out',str(stems_dir),str(source)]
 errors=[]
 # A GTX 1660 Ti has 6 GB: use short segments on CUDA; CPU is a fallback.
 for device in ('cuda','cpu'):
  print('מפריד צלילי רקע ודיבור באמצעות Demucs מקומי ('+device+')',flush=True)
  cmd=base[:2]+[base[2]]+['-d',device]+base[3:]
  log_path=project/('demucs-'+device+'.log')
  with log_path.open('w',encoding='utf-8') as log:
   try:
    result=subprocess.run(cmd,cwd=str(ROOT),stdout=log,stderr=subprocess.STDOUT,
                          env={**os.environ,'PYTHONIOENCODING':'utf-8'},timeout=48*3600,check=False)
    if result.returncode==0 and bg.is_file() and bg.stat().st_size>1024:break
    errors.append(device+': '+log_path.read_text(encoding='utf-8',errors='replace')[-500:])
   except (OSError,subprocess.TimeoutExpired) as e:errors.append(device+': '+str(e))
 if not bg.is_file() or bg.stat().st_size<1024:
  raise RuntimeError('הפרדת צלילי הרקע נכשלה. לא מחליף את הפסקול המקורי בשקט. '+str(errors)[-700:])
 if abs(duration(bg)-seconds)>1:raise RuntimeError('אורך ערוץ הרקע אינו תואם לסרטון המקורי')
 print(f'DUB_PROGRESS|background|1|1|{time.time():.3f}',flush=True)
 return bg

def render(video,project,seconds,segments,speakers,bank,output):
 import numpy as np,soundfile as sf
 mapping={s['id']:s['voice_id'] for s in speakers};valid={v['id'] for v in bank}
 profiles={v['id']:v for v in bank}
 if any(v not in valid for v in mapping.values()):raise ValueError('יש לבחור קול לכל דובר לפני תחילת הדיבוב')
 if len(set(mapping.values()))!=len(mapping):raise ValueError('בחר קול שונה לכל דובר כדי לשמור על הבחנה ביניהם')
 cache=project/'speech';cache.mkdir(exist_ok=True)
 engine=None;parts=[]
 print(f'DUB_PROGRESS|synthesize|0|{len(segments)}|{time.time():.3f}',flush=True)
 for i,s in enumerate(segments):
  if not s['hebrew'].strip():continue
  key=hashlib.sha256(json.dumps([VERSION,s,mapping[s['speaker']]],ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:24]
  part=cache/(key+'.wav')
  if not part.exists():
   if engine is None:engine=HebrewVoiceEngine(bank)
   try:
    choice=profiles[mapping[s['speaker']]]
    x=engine.synthesize(s['hebrew'],choice.get('base_id',choice['id']),s['end']-s['start'],int(key[:8],16)%2**31)
    x=transform_audio(x,24000,choice['id'])
   except Exception as e:raise RuntimeError('שורה '+s['id']+': '+str(e)) from e
   temp=part.with_suffix('.tmp.wav');sf.write(str(temp),x,24000,subtype='PCM_16');os.replace(temp,part)
  parts.append((s,part));print(f'דיבוב קטע {i+1}/{len(segments)} (תוצאות נשמרות להמשך)',flush=True)
  print(f'DUB_PROGRESS|synthesize|{i+1}|{len(segments)}|{time.time():.3f}',flush=True)
 del engine;gc.collect()
 # Disk-backed timeline: no movie-length waveform is held in RAM.
 raw=project/'timeline.f32';n=round(seconds*24000)
 with raw.open('wb') as f:f.truncate(n*4)
 timeline=np.memmap(raw,dtype='float32',mode='r+',shape=(n,))
 for s,part in parts:
  x,sr=sf.read(str(part),dtype='float32');start=round(s['start']*24000);end=min(n,start+len(x));timeline[start:end]+=x[:end-start]
 timeline.flush()
 wav=project/'dubbed.wav'
 with sf.SoundFile(str(wav),'w',samplerate=24000,channels=1,subtype='PCM_16',format='WAV') as f:
  for a in range(0,n,240000):f.write(np.clip(timeline[a:a+240000],-.98,.98))
 del timeline;raw.unlink(missing_ok=True)
 # Preserve original soundtrack without the original spoken/sung vocal stem.
 bg=background_track(video,project,seconds)
 print(f'DUB_PROGRESS|mux|0|1|{time.time():.3f}',flush=True)
 tmp=output.with_name(output.stem+'.building.mp4')
 mixer=('[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=1.00[dub];'
        '[2:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.85[bg];'
        '[bg][dub]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,'
        'alimiter=limit=0.95[outa]')
 run(['ffmpeg','-v','error','-y','-i',video,'-i',wav,'-i',bg,
      '-filter_complex',mixer,'-map','0:v:0','-map','[outa]',
      '-c:v','copy','-c:a','aac','-b:a','192k',
      '-t',f'{seconds:.3f}','-movflags','+faststart',tmp])
 if abs(duration(tmp)-seconds)>1:raise ValueError('משך סרטון הפלט אינו תואם למקור')
 os.replace(tmp,output)
 print(f'DUB_PROGRESS|done|1|1|{time.time():.3f}',flush=True)
 print('הסרטון המדובב מוכן',flush=True)

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);p.add_argument('--translate-only',action='store_true');p.add_argument('--hebrew-override');p.add_argument('--voice-map');p.add_argument('--film-style',choices=('auto','live','animation','mixed'),default='auto');p.add_argument('--max-duration',type=float,default=10800);p.add_argument('--parent-pid',type=int)
 a=p.parse_args();video=Path(a.input).resolve(strict=True);output=Path(a.output).resolve();output.parent.mkdir(parents=True,exist_ok=True)
 if a.parent_pid and os.name=='nt':
  import threading,ctypes
  def watch_parent():
   kernel=ctypes.windll.kernel32
   kernel.OpenProcess.restype=ctypes.c_void_p
   kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
   kernel.CloseHandle.argtypes=[ctypes.c_void_p]
   handle=kernel.OpenProcess(0x00100000,False,a.parent_pid)
   if not handle:return
   kernel.WaitForSingleObject(handle,0xFFFFFFFF);kernel.CloseHandle(handle)
   subprocess.run(['taskkill','/PID',str(os.getpid()),'/T','/F'],capture_output=True)
  threading.Thread(target=watch_parent,daemon=True).start()
 seconds=duration(video)
 if not math.isfinite(seconds) or not 0<seconds<=a.max_duration:raise ValueError('משך הסרטון חייב להיות עד 3 שעות')
 project=project_path(video);project.mkdir(parents=True,exist_ok=True)
 # OS lock is released even after a crash. Never run two renders of one project.
 lock=(project/'project.lock').open('a+b');lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
 if os.name=='nt':
  import msvcrt
  try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
  except OSError:raise RuntimeError('אותו סרטון כבר מעובד. המתן או עצור את המשימה הפעילה')
 if shutil.disk_usage(project).free < seconds*1800000+video.stat().st_size:raise RuntimeError('אין מספיק מקום פנוי להפרדת שמע, קובצי עבודה והפקת הסרטון (כולל צלילי רקע)')
 bank=catalog()
 detected_style=estimate_film_style(video) if a.film_style=='auto' else {'style':a.film_style,'confidence':1.0,'method':'manual'}
 film_style=detected_style['style']
 manifest=read(project/'manifest.json')
 if manifest is None:
  wav=project/'source.wav'
  if not wav.exists():extract(video,wav)
  diar=project/'speakers.json'
  if not diar.exists():run([ROOT/'.venv-speakers/Scripts/python.exe',ROOT/'speaker_worker.py',wav,diar])
  turns=read(diar)['turns']
  segments=make_segments(transcribe(wav,project,seconds,turns),turns)
  if not segments:raise ValueError('לא נמצא דיבור באנגלית לתמלול')
  segments=translate(segments,project)
  used={s['speaker'] for s in segments}
  speakers=classify_speakers(wav,[t for t in turns if t['speaker'] in used],bank)
  rawturns=read(diar)['raw_turns'];active=[];overlaps=False
  for x in sorted(rawturns,key=lambda t:t['start']):
   active=[y for y in active if y['end']>x['start']]
   if any(x['speaker']!=y['speaker'] and min(x['end'],y['end'])-x['start']>.2 for y in active):overlaps=True;break
   active.append(x)
  manifest={'version':VERSION,'duration':seconds,'speakers':speakers,'segments':segments,'overlapping_speech':overlaps}
  atomic(project/'manifest.json',manifest)
 segments=manifest['segments'];speakers=[dict(s) for s in manifest['speakers']]
 # Select per-speaker cartoon presets for recognized animation, preserving manual overrides.
 if film_style=='animation':
  assigned=set()
  for speaker in speakers:
   match=choose(speaker.get('suggested_type'),style='animation',used=assigned)
   if match:speaker['voice_id']=match;assigned.add(match)
 # Some legitimate voices are low-confidence but still have a male/female prediction.
 # Do not fail an entire long film merely because the confidence was below 0.8.
 already={s['voice_id'] for s in speakers if s.get('voice_id')}
 for speaker in speakers:
  if speaker.get('voice_id'):continue
  if speaker.get('suggested_type') not in ('male','female'):continue
  options=[v for v in bank if v['type']==speaker['suggested_type'] and v['id'] not in already]
  if options:speaker['voice_id']=options[0]['id'];already.add(options[0]['id'])
 if any(not s.get('voice_id') for s in speakers):
  raise ValueError('יש דוברים שטרם נבחר להם קול. יש לבחור קול גברי או נשי לכל דובר לפני הפקת הסרטון.')
 print(f'DUB_PROGRESS|voices|1|1|{time.time():.3f}',flush=True)
 if a.hebrew_override:segments=apply_review(segments,Path(a.hebrew_override).read_text(encoding='utf-8-sig'),{s['id'] for s in speakers})
 if a.voice_map:
  selected=read(a.voice_map,{})
  if set(selected)-{s['id'] for s in speakers}:raise ValueError('מפת קולות מכילה דובר לא מוכר')
  for s in speakers:s['voice_id']=selected.get(s['id'],s['voice_id'])
 outdir=output.parent/(output.stem+'_work');outdir.mkdir(exist_ok=True)
 (outdir/'translation.txt').write_text(review_text(segments),encoding='utf-8')
 atomic(outdir/'review.json',{'speakers':speakers,'voices':bank,'duration':seconds,'overlapping_speech':manifest['overlapping_speech'],'project':project.name,'film_style':detected_style})
 if a.translate_only:
  print(f'DUB_PROGRESS|done|1|1|{time.time():.3f}',flush=True)
  print('התרגום והקולות מוכנים לבדיקה ולאישור',flush=True);return
 render(video,project,seconds,segments,speakers,bank,output)
if __name__=='__main__':
 try:main()
 except Exception as e:print('DUB_ERROR: '+str(e),file=sys.stderr,flush=True);sys.exit(1)