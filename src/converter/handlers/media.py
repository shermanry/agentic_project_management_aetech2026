"""Audio and video, using the ffmpeg binary bundled with imageio-ffmpeg (no system install).

video -> keyframes (image chunks) + short low-res clips (video chunks) + transcript (if available)
audio -> 30 s wav segments (audio chunks) + transcript (if available)

Transcription runs locally only if `faster-whisper` is installed
(pip install faster-whisper); otherwise segments are still produced and the
package carries a warning so the pipeline can transcribe later.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

from ..core import Package, Chunk
from ..engine import register, Context

SEGMENT_SEC = 30
MAX_KEYFRAMES = 24
MAX_SEGMENTS = 60  # 30 minutes


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run_ffmpeg(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", *args]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {p.stderr.strip().splitlines()[-1] if p.stderr.strip() else p.returncode}")
    return p


def probe(path: Path) -> dict:
    """Parse `ffmpeg -i` output (ffprobe is not bundled)."""
    err = run_ffmpeg("-i", str(path), check=False).stderr
    info: dict = {"has_video": False, "has_audio": False}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if m:
        info["duration_s"] = round(int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]), 2)
    for line in err.splitlines():
        if "Stream #" in line and "Video:" in line and "attached pic" not in line:
            info["has_video"] = True
            if (r := re.search(r"(\d{2,5})x(\d{2,5})", line)):
                info["width"], info["height"] = int(r[1]), int(r[2])
            if (r := re.search(r"([\d.]+) fps", line)):
                info["fps"] = float(r[1])
            if (r := re.search(r"Video: (\w+)", line)):
                info["video_codec"] = r[1]
        elif "Stream #" in line and "Audio:" in line:
            info["has_audio"] = True
            if (r := re.search(r"Audio: (\w+)", line)):
                info["audio_codec"] = r[1]
    for key in ("creation_time", "location", "com.apple.quicktime.location.ISO6709", "title", "artist", "comment",
                "encoder", "make", "model", "com.apple.quicktime.make", "com.apple.quicktime.model"):
        if (r := re.search(rf"^\s+{re.escape(key)}\s*:\s*(.+)$", err, re.M)):
            info[key.split(".")[-1]] = r[1].strip()
    loc = info.get("location") or info.get("ISO6709")
    if loc and (r := re.match(r"([+-][\d.]+)([+-][\d.]+)([+-][\d.]+)?", loc)):
        info["gps"] = {"lat": float(r[1]), "lon": float(r[2])}
        if r[3]:
            info["gps"]["alt_m"] = float(r[3])
    return info


def fmt_t(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def transcribe(wav: Path) -> tuple[list[dict], str | None]:
    """Returns ([{start, end, text}], language) or ([], None) if no local ASR is installed."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return [], None
    model = WhisperModel(os.environ.get("CONVERTER_WHISPER_MODEL", "base"), device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(wav), vad_filter=True)
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments], info.language


def add_transcript(pkg: Package, wav: Path, label: str) -> None:
    segs, lang = transcribe(wav)
    if lang is None:
        pkg.warnings.append("no transcript: install faster-whisper for local speech-to-text")
        pkg.metadata["transcript"] = "pending"
        return
    pkg.metadata.update(transcript="local:faster-whisper", language=lang)
    # group whisper segments into ~SEGMENT_SEC windows so they align with media chunks
    window, buf, start = SEGMENT_SEC, [], None
    for s in segs:
        start = s["start"] if start is None else start
        buf.append(s["text"])
        if s["end"] - start >= window:
            pkg.add(Chunk("text", text=" ".join(buf), role="transcript",
                          locator={"t_start": round(start, 2), "t_end": round(s["end"], 2)}))
            buf, start = [], None
    if buf:
        pkg.add(Chunk("text", text=" ".join(buf), role="transcript",
                      locator={"t_start": round(start or 0, 2), "t_end": round(segs[-1]["end"], 2)}))
    full = " ".join(s["text"] for s in segs)
    if full:
        pkg.description = f"{label}. Transcript begins: {full[:300]}"


def _extract_wav(src: Path, dst: Path) -> bool:
    return run_ffmpeg("-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(dst), check=False).returncode == 0


@register("audio", ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wma", ".webm", ".amr", ".3ga")
def convert_audio(pkg: Package, ctx: Context) -> None:
    info = probe(pkg.source)
    if info.get("has_video") and pkg.source.suffix.lower() == ".webm":
        pkg.kind = "video"
        return convert_video(pkg, ctx)
    pkg.metadata.update(info)
    dur = info.get("duration_s", 0)
    label = f"Audio recording '{pkg.original_name}', {fmt_t(dur)} long"
    pkg.description = label
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "full.wav"
        if not _extract_wav(pkg.source, wav):
            raise RuntimeError("could not decode audio")
        pattern = Path(td) / "seg_%03d.wav"
        run_ffmpeg("-y", "-i", str(wav), "-f", "segment", "-segment_time", str(SEGMENT_SEC), "-c", "copy", str(pattern))
        segs = sorted(Path(td).glob("seg_*.wav"))[:MAX_SEGMENTS]
        for i, seg in enumerate(segs):
            t0, t1 = i * SEGMENT_SEC, min((i + 1) * SEGMENT_SEC, dur or (i + 1) * SEGMENT_SEC)
            rel = pkg.add_asset_bytes(f"audio_{i:03d}.wav", seg.read_bytes())
            pkg.add(Chunk("audio", text=f"{label}: segment {fmt_t(t0)}-{fmt_t(t1)}.", asset=rel, mime="audio/wav",
                          role="segment", locator={"t_start": t0, "t_end": t1}))
        add_transcript(pkg, wav, label)
    pkg.tags.add("voice-note" if dur and dur < 600 else "recording")


@register("video", ".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".mts", ".m2ts", ".3gp")
def convert_video(pkg: Package, ctx: Context) -> None:
    info = probe(pkg.source)
    pkg.metadata.update(info)
    if info.get("gps"):
        pkg.metadata["location"] = info["gps"]
        pkg.tags.add("geolocated")
    dur = info.get("duration_s") or 0
    label = f"Video '{pkg.original_name}', {fmt_t(dur)} long" + (
        f", {info['width']}x{info['height']}" if "width" in info else "")
    pkg.description = label + "."

    # keyframes: evenly spaced, one every ~5 s, capped
    n = max(1, min(MAX_KEYFRAMES, int(dur // 5) or 1))
    with tempfile.TemporaryDirectory() as td:
        for i in range(n):
            t = dur * (i + 0.5) / n
            out = Path(td) / f"kf_{i:03d}.jpg"
            run_ffmpeg("-y", "-ss", f"{t:.2f}", "-i", str(pkg.source), "-frames:v", "1",
                       "-vf", "scale='min(1280,iw)':-2", "-q:v", "3", str(out), check=False)
            if out.exists():
                rel = pkg.add_asset_bytes(f"keyframe_{i:03d}_{int(t)}s.jpg", out.read_bytes())
                pkg.add_image(rel, f"{label}: frame at {fmt_t(t)}.", role="keyframe", locator={"t": round(t, 2)})

        # short low-res clips for video-native embedding models
        pattern = Path(td) / "clip_%03d.mp4"
        p = run_ffmpeg("-y", "-i", str(pkg.source), "-t", str(SEGMENT_SEC * MAX_SEGMENTS),
                       "-vf", "scale=-2:'min(480,ih)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
                       "-force_key_frames", f"expr:gte(t,n_forced*{SEGMENT_SEC})",
                       "-c:a", "aac", "-b:a", "64k", "-ac", "1",
                       "-f", "segment", "-segment_time", str(SEGMENT_SEC), "-reset_timestamps", "1", str(pattern),
                       check=False)
        clips = sorted(Path(td).glob("clip_*.mp4"))
        if p.returncode != 0 or not clips:
            pkg.warnings.append("could not cut video clips; keyframes only")
        for i, clip in enumerate(clips):
            t0, t1 = i * SEGMENT_SEC, min((i + 1) * SEGMENT_SEC, dur or (i + 1) * SEGMENT_SEC)
            rel = pkg.add_asset_bytes(f"clip_{i:03d}.mp4", clip.read_bytes())
            pkg.add(Chunk("video", text=f"{label}: clip {fmt_t(t0)}-{fmt_t(t1)}.", asset=rel, mime="video/mp4",
                          role="segment", locator={"t_start": t0, "t_end": t1}))
        if dur > SEGMENT_SEC * MAX_SEGMENTS:
            pkg.warnings.append(f"clips only cover the first {SEGMENT_SEC * MAX_SEGMENTS // 60} minutes")

        if info.get("has_audio"):
            wav = Path(td) / "audio.wav"
            if _extract_wav(pkg.source, wav):
                add_transcript(pkg, wav, label)
    if any(k in (info.get("make", "") + info.get("model", "") + info.get("encoder", "")).lower() for k in ("dji", "parrot", "skydio", "autel")):
        pkg.tags.update({"flight", "drone-capture"})
