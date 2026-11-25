"""Spoken briefing through OpenRouter text-to-speech."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import httpx

from .config import env


def chunks(text: str, limit: int) -> list[str]:
    out = [""]
    for s in re.split(r"(?<=[.!?])\s+", text.strip()):
        if out[-1] and len(out[-1]) + len(s) + 1 > limit:
            out.append("")
        out[-1] = f"{out[-1]} {s}".strip()
    return out


def synth(text: str, out: Path) -> Path:
    fmt = env("TTS_FORMAT", "pcm")  # pcm or mp3; HeyGen and Gemini voices only return pcm
    rate = "24000"
    raw = out.with_suffix(f".raw.{fmt}")
    with raw.open("wb") as f:  # MP3 frames and raw PCM both concatenate; ffmpeg rewrites the header below
        for part in chunks(text, int(env("TTS_CHUNK_CHARS", "1800"))):
            r = httpx.post("https://openrouter.ai/api/v1/audio/speech", timeout=300,
                           headers={"Authorization": f"Bearer {env('OPENROUTER_API_KEY')}"},
                           json={"model": env("TTS_MODEL", "heygen/heygen-voice-1-turbo"), "input": part,
                                 "voice": env("TTS_VOICE", "gareth"), "response_format": fmt})
            if r.status_code >= 400:
                raise RuntimeError(f"TTS {r.status_code}: {r.text[:300]}")
            m = re.search(r"rate=(\d+)", r.headers.get("content-type", ""))
            rate = m[1] if m else rate
            f.write(r.content)
    src = ["-f", "s16le", "-ar", rate, "-ac", "1"] if fmt == "pcm" else []
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *src, "-i", str(raw), "-ac", "1", "-b:a", "64k", str(out)], check=True)
    raw.unlink()
    return out
