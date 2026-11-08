"""Local speaker timeline preparation. Not wired into production dubbing yet.
Requires pyannote.audio and user-authorized access to community-1.
No speech files are uploaded; inference runs locally.
"""
from pathlib import Path
import argparse,json,os

def analyze(audio_path, model_path=None):
    from pyannote.audio import Pipeline
    source=model_path or os.environ.get("DIARIZATION_MODEL_PATH")
    if source:
        pipeline=Pipeline.from_pretrained(str(Path(source).resolve()))
    else:
        from huggingface_hub import get_token
        token=get_token()
        if not token:
            raise RuntimeError("First accept community-1 access terms and sign in locally with Hugging Face.")
        pipeline=Pipeline.from_pretrained("pyannote/speaker-diarization-community-1",token=token)
    output=pipeline(str(Path(audio_path).resolve()))
    # Preserve overlaps instead of silently assigning simultaneous speakers to one voice.
    turns=[{"start":float(turn.start),"end":float(turn.end),"speaker":str(speaker)}
           for turn,speaker in output.speaker_diarization]
    speakers=sorted({t["speaker"] for t in turns})
    return {"speakers":[{"id":s,"voice_id":None,"voice_type":None} for s in speakers],
            "turns":turns,
            "status":"needs_voice_assignment",
            "note":"Speaker identity groups are not male/female labels. Assign a tested Hebrew voice per speaker before synthesis."}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("audio")
    p.add_argument("--model-path")
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result=analyze(args.audio,args.model_path)
    dest=Path(args.output)
    if dest.exists():raise FileExistsError("Choose a new output path.")
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(dest)