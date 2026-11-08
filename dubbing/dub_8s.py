"""Experimental offline English->Hebrew voice-similar dubbing of first eight seconds.
Downloads open models during first run; no hosted inference / paid API.
"""
from __future__ import annotations

import argparse
import json
import os
import math
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VIDEO = ROOT / "test.mp4"
OUT_DIR = ROOT / "dub_work"
OUT_DIR.mkdir(exist_ok=True)
SRC_WAV = OUT_DIR / "source_full.wav"
REF_WAV = OUT_DIR / "reference_voice.wav"
HEB_WAV = OUT_DIR / "hebrew_full.wav"
FINAL_MP4 = ROOT / "dubbed_he_full.mp4"
HEBREW_OVERRIDE = ROOT / "hebrew_override.txt"


def run(cmd: list[str]) -> None:
    print("$", " ".join(map(str,cmd)), flush=True)
    subprocess.run(cmd, check=True)


def translate_local(text: str) -> str:
    """Dedicated local English-to-Hebrew translation; no cloud inference."""
    import re
    import gc
    import torch
    from transformers import MarianMTModel, MarianTokenizer
    model_path = ROOT / "models" / "opus-en-he"
    if not model_path.is_dir():
        raise RuntimeError("מודל התרגום המקומי חסר. הפעל SETUP_TRANSLATION.bat פעם אחת.")
    tokenizer = MarianTokenizer.from_pretrained(str(model_path), local_files_only=True)
    model = MarianMTModel.from_pretrained(str(model_path), local_files_only=True).eval()
    torch.set_num_threads(min(4, os.cpu_count() or 1))
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks = []
    for sentence in sentences:
        words = sentence.split()
        # Bound input length; no silent tokenizer truncation.
        current = []
        for word in words:
            trial = " ".join(current + [word])
            if len(tokenizer.encode(trial)) > 400 and current:
                chunks.append(" ".join(current)); current = []
            current.append(word)
        if current:chunks.append(" ".join(current))
    outputs = []
    for index, chunk in enumerate(chunks):
        inputs = tokenizer(chunk, return_tensors="pt")
        with torch.inference_mode():
            result = model.generate(**inputs, num_beams=4, max_new_tokens=512)
        translated = tokenizer.decode(result[0], skip_special_tokens=True).strip()
        if not translated or not any(0x0590 <= ord(c) <= 0x05ff for c in translated):
            raise RuntimeError("התרגום לא הפיק טקסט עברי תקין.")
        outputs.append(translated)
        print(f"Translated sentence {index+1}/{len(chunks)}", flush=True)
    hebrew = " ".join(outputs)
    # Optional, explicit brand glossary; apply only when the source mentions that brand.
    glossary_path = ROOT / "translation_glossary.json"
    if glossary_path.is_file():
        for entry in json.loads(glossary_path.read_text(encoding="utf-8")):
            if entry.get("source", "").lower() in text.lower() and entry.get("source"):
                for variant in entry.get("variants", []):
                    hebrew = hebrew.replace(variant, entry["hebrew"])
    del model, tokenizer
    gc.collect()
    return hebrew


def transcribe(audio: Path) -> str:
    from faster_whisper import WhisperModel
    print("Loading Whisper small on CPU...", flush=True)
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio), language="en", beam_size=3)
    result = " ".join(s.text.strip() for s in segments).strip()
    del model
    if not result:
        raise RuntimeError("No English speech was recognized in the uploaded audio.")
    return result


def check_audio(samples, label: str, max_abs: float = 30.0) -> dict:
    """Reject silence, non-finite values, constant audio, and exploding model output."""
    import numpy as np

    x = np.asarray(samples, dtype=np.float64).reshape(-1)
    if x.size < 1000:
        raise RuntimeError(f"{label}: too few samples ({x.size}).")
    bad = int(np.count_nonzero(~np.isfinite(x)))
    if bad:
        raise RuntimeError(f"{label}: {bad}/{x.size} NaN or Inf samples.")
    peak = float(np.max(np.abs(x)))
    rms = float(np.sqrt(np.mean(x * x)))
    std = float(np.std(x))
    print(
        f"AUDIO [{label}]: peak={peak:.6g}, rms={rms:.6g}, std={std:.6g}, samples={x.size}",
        flush=True,
    )
    if std < 0.00001 or rms < 0.00001:
        raise RuntimeError(f"{label}: silent or constant output.")
    if peak > max_abs:
        raise RuntimeError(
            f"{label}: invalid amplitude (peak={peak:.3g}); unstable synthesis. "
            "The WAV was not written."
        )
    return {"peak": peak, "rms": rms, "std": std}


def save_verified_wav(samples, filename: Path, sr: int = 24000) -> None:
    import numpy as np
    import soundfile as sf
    import os

    x = np.asarray(samples, dtype=np.float32).reshape(-1)
    info = check_audio(x, "raw vocoder output")
    if info["peak"] > 0.95:
        x = (x * (0.95 / info["peak"])).astype(np.float32)
        print(f"Scaled valid output peak from {info['peak']:.3f} to 0.95.", flush=True)

    temp_wav = filename.with_name(filename.stem + ".validating.wav")
    try:
        sf.write(str(temp_wav), x, sr, subtype="PCM_16")
        reread, actual_sr = sf.read(str(temp_wav), dtype="float32")
        if actual_sr != sr:
            raise RuntimeError(f"Expected {sr} Hz, got {actual_sr} Hz from saved WAV.")
        check_audio(reread, "saved WAV", max_abs=1.0)
        saturated_ratio = float(np.mean(np.abs(reread) >= 0.999))
        if saturated_ratio > 0.02:
            raise RuntimeError(f"Saved WAV has {saturated_ratio:.1%} clipped samples.")
        os.replace(temp_wav, filename)
    finally:
        if temp_wav.exists():
            temp_wav.unlink()
    print(f"VALID WAV: {filename}", flush=True)


def synthesize(ref_text: str, hebrew_text: str, speech_seconds: float) -> None:
    import gc
    import numpy as np
    import soundfile as sf
    import torch
    from huggingface_hub import hf_hub_download
    from f5_tts.model import DiT
    from f5_tts.infer.utils_infer import load_model, load_vocoder
    from phonikud_onnx import Phonikud

    phonikud_path = ROOT / "models" / "phonikud" / "phonikud-1.0.int8.onnx"
    if not phonikud_path.is_file():
        raise RuntimeError(f"Missing local Phonikud model: {phonikud_path}")
    phonikud = Phonikud(str(phonikud_path))
    # This checkpoint was trained on Hebrew letters with niqqud and stress marks.
    hebrew_model_text = phonikud.add_diacritics(hebrew_text.strip()).replace("|", "")
    if not hebrew_model_text.strip():
        raise RuntimeError("Phonikud returned empty vocalized Hebrew text.")
    allowed_chars = set(Path(hf_hub_download(repo_id="Yzamari/f5tts-hebrew-v2", filename="vocab.txt")).read_text(encoding="utf-8").splitlines())
    unknown_chars = sorted(set(hebrew_model_text) - allowed_chars)
    if unknown_chars:
        raise RuntimeError(f"Phonikud output has characters missing from F5 vocabulary: {ascii(unknown_chars)}")
    print("Hebrew text vocalized with local Phonikud.", flush=True)
    print("Vocalized text (escaped):", ascii(hebrew_model_text), flush=True)

    chosen = os.environ.get("TTS_DEVICE", "auto").lower().strip()
    if chosen not in ("auto", "cpu", "cuda"):
        raise RuntimeError("TTS_DEVICE must be auto, cpu or cuda")
    device = "cuda" if (chosen == "cuda" or (chosen == "auto" and torch.cuda.is_available())) else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("TTS_DEVICE=cuda requested but CUDA is not available.")
    print("Speech synthesis device:", device, flush=True)
    print("Downloading/using cached Hebrew voice model...", flush=True)
    repo = "Yzamari/f5tts-hebrew-v2"
    ckpt = hf_hub_download(repo_id=repo, filename="model.safetensors")
    vocab = hf_hub_download(repo_id=repo, filename="vocab.txt")
    model_cfg = dict(dim=1024, depth=22, heads=16, ff_mult=2, text_dim=512,
                     text_mask_padding=True, conv_layers=4, pe_attn_head=None)
    print("Loading F5-TTS Hebrew v2...", flush=True)
    # Load in float32 on CPU first. Direct CUDA loading can select FP16 and
    # produce exploding vocoder samples that sound like silence after PCM clipping.
    model = load_model(DiT, model_cfg, ckpt, vocab_file=vocab, use_ema=False,
                       device="cpu")
    model = model.to(device=device, dtype=torch.float32).eval()
    vocoder = load_vocoder(vocoder_name="vocos", device=device)
    vocoder = vocoder.to(device=device, dtype=torch.float32).eval()
    audio, sr = sf.read(str(REF_WAV), dtype="float32")
    if sr != 24000:
        raise RuntimeError(f"Reference audio must be 24000 Hz, got {sr}")
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    audio = np.asarray(audio, dtype=np.float32)
    ref_stats = check_audio(audio, "reference voice", max_abs=1.0)
    if ref_stats["rms"] < 0.1:
        factor = min(0.1 / ref_stats["rms"], 0.95 / max(ref_stats["peak"], 1e-6))
        audio = audio * np.float32(factor)
    no_ref_audio = os.environ.get("TTS_NO_REF_AUDIO", "1").strip() == "1"
    if no_ref_audio:
        # Diagnostic mode: check Hebrew synthesis without an English voice prompt.
        ref_audio = torch.zeros((1, 4096), device=device, dtype=torch.float32)
        ref_frames = 4096 // 256
        target_duration = ref_frames + round(speech_seconds * 24000 / 256)
        text = [hebrew_model_text.strip()]
        print("Hebrew voice mode: original speaker identity is NOT preserved.", flush=True)
    else:
        ref_audio = torch.from_numpy(audio).unsqueeze(0).to(device=device, dtype=torch.float32)
        ref_frames = ref_audio.shape[1] // 256
        # An 8-second dubbed sentence, plus the six-second reference prompt.
        target_duration = ref_frames + round(speech_seconds * 24000 / 256)
        text = [ref_text.rstrip(". ") + ". " + hebrew_model_text.strip()]
    # The checkpoint expects Hebrew characters with niqqud/stress marks.
    print("Generating Hebrew voice from vocalized Hebrew text.", flush=True)
    from f5_tts.model.utils import convert_char_to_pinyin
    # Generate bounded chunks with one loaded model to keep GPU use stable.
    words = hebrew_model_text.split()
    chunk_count = min(len(words), max(1, math.ceil(speech_seconds / 10.0)))
    chunks = [" ".join(words[round(i*len(words)/chunk_count):round((i+1)*len(words)/chunk_count)]) for i in range(chunk_count)]
    generated = []
    total_chars = sum(len(chunk) for chunk in chunks)
    for index, chunk in enumerate(chunks):
        seconds = speech_seconds * len(chunk) / max(1,total_chars)
        target_duration = ref_frames + max(100, round(seconds * 24000 / 256))
        prompt_text = chunk if no_ref_audio else ref_text.rstrip(". ") + ". " + chunk
        print(f"Generating speech chunk {index+1}/{len(chunks)} ({seconds:.1f}s)", flush=True)
        with torch.inference_mode():
            mel, _ = model.sample(cond=ref_audio, text=convert_char_to_pinyin([prompt_text]),
                                  duration=target_duration, steps=32, cfg_strength=2.0,
                                  sway_sampling_coef=-1.0, no_ref_audio=no_ref_audio)
            if not torch.isfinite(mel).all().item() or float(mel.abs().max().item()) > 100:
                raise RuntimeError("F5-TTS returned unstable audio; no output was saved.")
            mel = mel[:, ref_frames:, :].permute(0, 2, 1).to(torch.float32)
            if mel.shape[-1] == 0:raise RuntimeError("Generated mel has no speech frames.")
            part = vocoder.decode(mel).squeeze().detach().cpu().numpy()
            check_audio(part, f"chunk {index+1}")
            stats = check_audio(part, f"level check {index+1}")
            gain = min(0.12 / max(stats["rms"], 1e-6), 0.95 / max(stats["peak"], 1e-6))
            part = part * np.float32(gain)
            fade = min(120, len(part)//2)
            part[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
            part[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
            generated.append(part)
            # Anchor all later chunks to the SAME Hebrew speaker sample.
            # Keep the whole chunk so the reference transcript matches its audio.
            if index == 0 and no_ref_audio and len(chunks) > 1:
                ref_audio = torch.from_numpy(part.copy()).unsqueeze(0).to(device=device, dtype=torch.float32)
                ref_frames = ref_audio.shape[1] // 256
                ref_text = chunk
                no_ref_audio = False
                sf.write(str(OUT_DIR / "speaker_anchor.wav"), part, 24000, subtype="PCM_16")
                print("Speaker anchor established from first Hebrew chunk; reused for all later chunks.", flush=True)
            del mel
        if device == "cuda":torch.cuda.empty_cache()
    speech = np.concatenate(generated)
    save_verified_wav(speech, HEB_WAV, 24000)
    del vocoder, model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def main() -> None:
    global VIDEO, FINAL_MP4, HEBREW_OVERRIDE, OUT_DIR, SRC_WAV, REF_WAV, HEB_WAV
    parser = argparse.ArgumentParser(description="Local English-to-Hebrew dubbing of a full clip")
    parser.add_argument("--input", default=str(VIDEO), help="Input video path")
    parser.add_argument("--output", default=str(FINAL_MP4), help="Output MP4 path")
    parser.add_argument("--hebrew-override", default="", help="Optional approved Hebrew translation text file")
    parser.add_argument("--translate-only", action="store_true", help="Prepare Hebrew text for review without generating speech")
    parser.add_argument("--max-duration", type=float, default=90.0, help="Maximum video duration in seconds")
    args = parser.parse_args()
    VIDEO = Path(args.input).expanduser().resolve()
    FINAL_MP4 = Path(args.output).expanduser().resolve()
    FINAL_MP4.parent.mkdir(parents=True, exist_ok=True)
    OUT_DIR = FINAL_MP4.parent / (FINAL_MP4.stem + '_work')
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SRC_WAV, REF_WAV, HEB_WAV = (OUT_DIR / n for n in ('source.wav', 'reference.wav', 'hebrew.wav'))
    if args.hebrew_override:
        HEBREW_OVERRIDE = Path(args.hebrew_override).expanduser().resolve()
    elif VIDEO == (ROOT / "test.mp4").resolve():
        HEBREW_OVERRIDE = ROOT / "hebrew_override.txt"
    else:
        HEBREW_OVERRIDE = ROOT / "_no_override_for_uploaded_video.txt"
    if not VIDEO.is_file():
        sys.exit("Input video file does not exist: " + str(VIDEO))
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(VIDEO)], check=True, capture_output=True, text=True)
    clip_seconds = float(probe.stdout.strip())
    if clip_seconds <= 0 or clip_seconds > args.max_duration:
        raise RuntimeError(f"אורך הסרטון חייב להיות עד {args.max_duration:g} שניות. אורך הקובץ: {clip_seconds:.1f} שניות.")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(VIDEO),
         "-vn", "-ac", "1", "-ar", "16000", str(SRC_WAV)])
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(VIDEO),
         "-t", "6", "-vn", "-ac", "1", "-ar", "24000", str(REF_WAV)])
    english = transcribe(SRC_WAV)
    reference_english = transcribe(REF_WAV)
    print("English transcript:", english, flush=True)
    if HEBREW_OVERRIDE.is_file():
        hebrew = HEBREW_OVERRIDE.read_text(encoding="utf-8-sig").strip()
        print("Using approved Hebrew text from:", HEBREW_OVERRIDE, flush=True)
    else:
        hebrew = translate_local(english)
    if not hebrew:
        raise RuntimeError("Hebrew translation is empty.")
    has_hebrew = any("\u0590" <= ch <= "\u05ff" for ch in hebrew)
    has_arabic = any("\u0600" <= ch <= "\u06ff" for ch in hebrew)
    if not has_hebrew or has_arabic:
        (OUT_DIR / "translation_rejected.txt").write_text(hebrew, encoding="utf-8")
        raise RuntimeError("Automatic translation was not valid Hebrew. Enter a Hebrew translation in the agent's translation box and run dubbing again.")
    print("Hebrew translation:", hebrew, flush=True)
    (OUT_DIR / "translation.txt").write_text(hebrew, encoding="utf-8")
    if args.translate_only:
        print("TRANSLATION_READY:", OUT_DIR / "translation.txt", flush=True)
        return
    synthesize(reference_english, hebrew, clip_seconds)
    # First test: replace the original soundtrack. Background music is not retained.
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(VIDEO),
         "-i", str(HEB_WAV), "-t", f"{clip_seconds:.3f}", "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "veryfast", "-af", f"apad,atrim=0:{clip_seconds:.3f}", "-c:a", "aac", str(FINAL_MP4)])
    print("OUTPUT:", FINAL_MP4)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Dubbing test failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)