"""Local, licensed Hebrew voice library and cartoon-style presets.

Base samples: Google FLEURS Hebrew, CC BY 4.0.
https://huggingface.co/datasets/google/fleurs
FLEURS: Conneau et al., 2022. Effects are synthetic, not real cartoon actors.
Nothing is downloaded, no paid API is used.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VOICE_ROOT = ROOT / "models" / "hebrew-voices"

# Presets: ID, Hebrew name, licensed voice base, pitch, effect, vocal presentation.
PRESETS = [
    ("cartoon_child_bright", "ילד מצויר - עליז", "female_5", 1.28, "cartoon", "female"),
    ("cartoon_child_silly", "ילד מצויר - מצחיק", "female_3", 1.36, "cartoon", "female"),
    ("cartoon_fairy", "פיה מצוירת", "female_7", 1.19, "fairy", "female"),
    ("cartoon_creature", "יצור מצויר קטן", "female_4", 1.43, "cartoon", "female"),
    ("cartoon_funny_man", "דמות קומית", "male_2", 1.18, "cartoon", "male"),
    ("cartoon_hero", "גיבור על", "male_5", 1.04, "hero", "male"),
    ("cartoon_villain", "נבל מצויר", "male_8", 0.85, "villain", "male"),
    ("cartoon_witch", "מכשפה דרמטית", "female_6", 0.86, "villain", "female"),
    ("monster_deep", "מפלצת עמוקה", "male_7", 0.73, "monster", "male"),
    ("giant_rough", "ענק מחוספס", "male_3", 0.78, "monster", "male"),
    ("robot_male", "רובוט נמוך", "male_1", 0.94, "robot", "male"),
    ("robot_female", "רובוט גבוה", "female_2", 1.12, "robot", "female"),
    ("wizard_old", "קוסם זקן", "male_6", 0.84, "wizard", "male"),
    ("heroine_bright", "גיבורה אמיצה", "female_8", 1.02, "hero", "female"),
    ("narrator_warm", "קריינית חמימה", "female_1", 0.99, "natural", "female"),
    ("narrator_bold", "קריין עמוק", "male_4", 0.95, "natural", "male"),
]

# Character styles are non-identity-preserving effects; do not label speakers by age.
EFFECTS = {
    "natural": "",
    "cartoon": "highpass=f=125",
    "fairy": "highpass=f=210,aecho=0.7:0.25:32:0.18",
    "hero": "highpass=f=80,acompressor=threshold=-18dB:ratio=2.2:attack=12:release=80",
    "villain": "lowpass=f=4400,aecho=0.85:0.25:48:0.15",
    "monster": "lowpass=f=2700,aecho=0.8:0.3:65:0.22",
    "robot": "highpass=f=150,tremolo=f=13:d=0.34",
    "wizard": "lowpass=f=3200,tremolo=f=4:d=0.12",
}

def catalog():
    meta = json.loads((VOICE_ROOT / "candidates.json").read_text(encoding="utf-8"))
    if meta.get("source") != "Google FLEURS Hebrew" or meta.get("license", "").lower() != "cc-by-4.0":
        raise RuntimeError("Cannot confirm license for installed voice references")
    originals = []
    for item in meta.get("voices", []):
        file_name = item.get("file", "")
        if Path(file_name).name != file_name or not file_name.endswith(".wav"):
            raise ValueError("Invalid local voice file path")
        if not (VOICE_ROOT / file_name).is_file():
            continue
        v = dict(item)
        v.update(label=("קול גברי " if v["type"] == "male" else "קול נשי ") + v["id"].split("_")[-1],
                 base_id=v["id"], style="natural", pitch=1.0, is_preset=False)
        originals.append(v)
    by_id = {v["id"]: v for v in originals}
    voices = list(originals)
    for ident, label, base, pitch, style, kind in PRESETS:
        if base not in by_id:
            continue
        v = dict(by_id[base])
        v.update(id=ident, base_id=base, label=label, type=kind,
                 pitch=pitch, style=style, is_preset=True)
        voices.append(v)
    if not voices:
        raise RuntimeError("No licensed Hebrew voice references available")
    return voices

def voice(voice_id):
    return next((item for item in catalog() if item["id"] == voice_id), None)

def choose(kind, style="live", used=()):
    """Suggest a distinct voice based on acoustic type, not real-world identity."""
    choices = catalog()
    used = set(used)
    if kind not in {"male", "female"}:
        return None
    if style == "animation":
        preferred = (["cartoon_child_bright", "cartoon_fairy", "heroine_bright", "cartoon_witch"]
                     if kind == "female" else
                     ["cartoon_hero", "cartoon_funny_man", "cartoon_villain", "robot_male"])
        for ident in preferred:
            if ident not in used and any(v["id"] == ident for v in choices):
                return ident
    return next((v["id"] for v in choices if v["type"] == kind and not v["is_preset"]
                 and v["id"] not in used), None)

def transform_audio(samples, sample_rate, voice_id):
    """Change pitch/timbre offline while preserving exactly the input length."""
    import numpy as np
    settings = voice(voice_id)
    if settings is None:
        raise ValueError("Unknown voice ID")
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)
    if audio.size < 200 or not np.isfinite(audio).all():
        raise ValueError("Invalid audio for voice transformation")
    if not settings["is_preset"]:
        return audio.copy()
    if not shutil.which("ffmpeg"):
        raise RuntimeError("FFmpeg is needed for cartoon-style effects")
    pitch = float(settings["pitch"])
    if not math.isfinite(pitch) or not 0.65 <= pitch <= 1.5:
        raise ValueError("Invalid pitch factor")
    effects = [f"rubberband=pitch={pitch:.4f}:tempo=1.0"]
    extra = EFFECTS[settings["style"]]
    if extra:
        effects.append(extra)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "-i", "pipe:0",
        "-af", ",".join(effects),
        "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, input=audio.tobytes(), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=max(20, audio.size / sample_rate * 8))
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Voice effect timed out") from exc
    if proc.returncode:
        raise RuntimeError("Voice effect failed: " + proc.stderr.decode("utf-8", "replace")[-300:])
    result = np.frombuffer(proc.stdout, dtype="<f4").copy()
    if result.size < 100 or not np.isfinite(result).all():
        raise RuntimeError("Voice effect returned unusable audio")
    result = np.pad(result[:audio.size], (0, max(0, audio.size-result.size)))
    # Never overflow the mix after creative effects.
    peak = float(np.max(np.abs(result)))
    if peak > 0.95:
        result *= 0.95 / peak
    return result.astype(np.float32)

def estimate_film_style(video):
    """Conservative offline visual heuristic; uncertain results stay 'live'.

    This is not a trained animation classifier. Its confidence is deliberately
    low for 3D animation, stylized films, dark video, and mixed scenes.
    """
    import numpy as np
    video = Path(video)
    if not shutil.which("ffprobe") or not shutil.which("ffmpeg"):
        return {"style": "live", "confidence": 0.0, "method": "unavailable"}
    try:
        sec = float(subprocess.check_output([
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(video)
        ], text=True, timeout=12))
    except (subprocess.SubprocessError, ValueError, OSError):
        return {"style": "live", "confidence": 0.0, "method": "unavailable"}
    scores = []
    for frac in (0.14, 0.35, 0.60, 0.83):
        position = max(0, sec * frac)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(position),
               "-i", str(video), "-frames:v", "1", "-vf", "scale=96:54",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=15)
            if p.returncode or len(p.stdout) != 96*54*3:
                continue
            frame = np.frombuffer(p.stdout, dtype=np.uint8).reshape(54, 96, 3)
            flat = np.mean(np.max(abs(frame[:, 1:].astype("int16") -
                                     frame[:, :-1].astype("int16")), axis=2) < 7)
            colors = np.unique((frame // 24).reshape(-1, 3), axis=0).shape[0]
            cartoon = flat > 0.38 and colors < 350
            scores.append(bool(cartoon))
        except (OSError, subprocess.SubprocessError):
            pass
    if len(scores) < 2:
        return {"style": "live", "confidence": 0.0, "method": "insufficient_frames"}
    if all(scores):
        return {"style": "animation", "confidence": 0.60, "method": "visual_heuristic"}
    if any(scores) and len(scores) >= 3:
        return {"style": "mixed", "confidence": 0.35, "method": "visual_heuristic"}
    return {"style": "live", "confidence": 0.35, "method": "visual_heuristic"}