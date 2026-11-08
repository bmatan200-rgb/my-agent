from pathlib import Path
r=Path(__file__).resolve().parent
s=(r/'dub_8s.py').read_text(encoding='utf-8')
old='''            generated.append(part)
            del mel'''
new='''            generated.append(part)
            # Anchor all later chunks to the SAME Hebrew speaker sample.
            # Keep the whole chunk so the reference transcript matches its audio.
            if index == 0 and no_ref_audio and len(chunks) > 1:
                ref_audio = torch.from_numpy(part.copy()).unsqueeze(0).to(device=device, dtype=torch.float32)
                ref_frames = ref_audio.shape[1] // 256
                ref_text = chunk
                no_ref_audio = False
                sf.write(str(OUT_DIR / "speaker_anchor.wav"), part, 24000, subtype="PCM_16")
                print("Speaker anchor established from first Hebrew chunk; reused for all later chunks.", flush=True)
            del mel'''
assert s.count(old)==1
s=s.replace(old,new)
compile(s,'dub_voice_lock.py','exec')
(r/'dub_voice_lock.py').write_text(s,encoding='utf-8')