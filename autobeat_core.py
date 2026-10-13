"""Testable media/export helpers for KHIETTRAN Autobeat Cut V3.2."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import shutil
import subprocess
from typing import Iterable, Sequence

RESOLUTIONS = {
    "Full HD": (1920, 1080), "2K": (2560, 1440), "4K": (3840, 2160),
    "6K": (5760, 3240), "8K": (7680, 4320),
}
CONTAINERS = {"MP4": ".mp4", "MOV": ".mov"}
CODECS = {"H.264": "libx264", "H.265": "libx265"}
FPS_OPTIONS = (25, 30, 60, 120)
BITRATE_MBPS_OPTIONS = (50, 100, 150, 200, 300)

@dataclass(frozen=True)
class ExportSettings:
    resolution: str = "Full HD"
    container: str = "MP4"
    codec: str = "H.264"
    fps: int = 30
    bitrate_mbps: int = 50
    ratio: str = "16:9"
    audio_bitrate_kbps: int = 192

    def validate(self) -> None:
        if self.resolution not in RESOLUTIONS:
            raise ValueError(f"Unsupported resolution: {self.resolution}")
        if self.container not in CONTAINERS:
            raise ValueError(f"Unsupported container: {self.container}")
        if self.codec not in CODECS:
            raise ValueError(f"Unsupported video codec: {self.codec}")
        if self.fps not in FPS_OPTIONS:
            raise ValueError(f"Unsupported FPS: {self.fps}")
        if self.bitrate_mbps not in BITRATE_MBPS_OPTIONS:
            raise ValueError(f"Unsupported bitrate: {self.bitrate_mbps} Mbps")
        if self.ratio not in ("16:9", "9:16", "4:5", "1:1"):
            raise ValueError(f"Unsupported aspect ratio: {self.ratio}")
        if not 64 <= self.audio_bitrate_kbps <= 512:
            raise ValueError("Audio bitrate must be between 64 and 512 kbps")

    @property
    def extension(self) -> str:
        self.validate()
        return CONTAINERS[self.container]

    def dimensions(self) -> tuple[int, int]:
        self.validate()
        w, h = RESOLUTIONS[self.resolution]
        if self.ratio == "9:16": return h, w
        if self.ratio == "4:5": return int(h * 4 / 5), h
        if self.ratio == "1:1": return h, h
        return w, h


def build_video_filter(settings: ExportSettings, genre: str = "", lut_path: str | None = None,
                       extra_filters: Sequence[str] = ()) -> str:
    w, h = settings.dimensions()
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={settings.fps}"
    grades = {
        "Wedding / Cưới": ",eq=contrast=1.02:saturation=1.05:brightness=0.015",
        "Portrait / Chân dung": ",eq=contrast=1.04:saturation=1.02",
        "Cinematic / Điện ảnh": ",eq=contrast=1.12:saturation=0.88",
        "Social / TikTok-Reels": ",eq=contrast=1.08:saturation=1.12",
    }
    vf += grades.get(genre, "")
    for extra_filter in extra_filters:
        if not extra_filter or any(ch in extra_filter for ch in "\r\n;\x00"):
            raise ValueError("Invalid automatic color filter")
        vf += "," + extra_filter
    if lut_path:
        lut = Path(lut_path).expanduser().resolve()
        if not lut.is_file():
            raise ValueError(f"LUT file does not exist: {lut}")
        # FFmpeg filter syntax needs escaping for Windows drive letters, colons and quotes.
        escaped = str(lut).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        vf += f",lut3d=file='{escaped}'"
    return vf


def build_encode_args(settings: ExportSettings, genre: str = "", audio_only: bool = False,
                      lut_path: str | None = None, extra_filters: Sequence[str] = ()) -> list[str]:
    settings.validate()
    if audio_only:
        return ["-c:a", "aac", "-b:a", f"{settings.audio_bitrate_kbps}k"]
    return ["-vf", build_video_filter(settings, genre, lut_path, extra_filters), "-c:v", CODECS[settings.codec],
            "-b:v", f"{settings.bitrate_mbps}M", "-maxrate", f"{settings.bitrate_mbps}M",
            "-bufsize", f"{settings.bitrate_mbps * 2}M", "-pix_fmt", "yuv420p",
            "-r", str(settings.fps), "-tag:v", "hvc1" if settings.codec == "H.265" and settings.container == "MOV" else "avc1" if settings.codec == "H.264" else "hev1"]


def probe_media(path: str, ffprobe: str | None = None) -> dict:
    binary = ffprobe or shutil.which("ffprobe")
    if not binary:
        raise RuntimeError("FFprobe was not found. Install FFmpeg/FFprobe or bundle them with the app.")
    result = subprocess.run([binary, "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "FFprobe could not read the output file")
    data = json.loads(result.stdout)
    if not Path(path).is_file() or Path(path).stat().st_size == 0:
        raise RuntimeError("Output file is missing or empty")
    return data


def validate_output(path: str, settings: ExportSettings, ffprobe: str | None = None) -> list[str]:
    """Return human-readable mismatches; empty means probed stream metadata matches."""
    settings.validate()
    data = probe_media(path, ffprobe)
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    errors = []
    if not video: return ["Output contains no video stream"]
    expected_codec = "h264" if settings.codec == "H.264" else "hevc"
    if video.get("codec_name") != expected_codec: errors.append(f"Codec expected {expected_codec}, got {video.get('codec_name')}")
    w, h = settings.dimensions()
    if (video.get("width"), video.get("height")) != (w, h): errors.append(f"Resolution expected {w}x{h}, got {video.get('width')}x{video.get('height')}")
    rate = video.get("avg_frame_rate", "0/1")
    try:
        num, den = rate.split("/"); actual_fps = float(num) / float(den)
        if abs(actual_fps - settings.fps) > 0.02: errors.append(f"FPS expected {settings.fps}, got {actual_fps:.3f}")
    except Exception: errors.append(f"Could not verify FPS: {rate}")
    if settings.container == "MOV" and Path(path).suffix.lower() != ".mov": errors.append("Expected MOV file extension")
    if settings.container == "MP4" and Path(path).suffix.lower() != ".mp4": errors.append("Expected MP4 file extension")
    format_name = str(data.get("format", {}).get("format_name", ""))
    if settings.container == "MOV" and "mov" not in format_name: errors.append(f"Expected MOV container metadata, got {format_name or 'unknown'}")
    if settings.container == "MP4" and "mp4" not in format_name: errors.append(f"Expected MP4 container metadata, got {format_name or 'unknown'}")
    try:
        actual_bitrate = int(video.get("bit_rate", 0))
        if actual_bitrate <= 0: errors.append("Video bitrate metadata is missing; requested bitrate could not be verified")
        elif actual_bitrate > settings.bitrate_mbps * 1_000_000 * 1.25: errors.append(f"Video bitrate exceeds configured target by more than 25% ({actual_bitrate} bit/s)")
    except (TypeError, ValueError): errors.append("Could not verify video bitrate metadata")
    if audio and audio.get("codec_name") not in ("aac", "alac", "pcm_s16le", "pcm_s24le", "pcm_s32le"): errors.append(f"Unexpected audio codec: {audio.get('codec_name')}")
    return errors


def detect_beats(audio_path: str, max_seconds: int = 180) -> tuple[float, list[float]]:
    """Return estimated BPM and beat timestamps; librosa errors are allowed to reach caller."""
    import librosa
    y, sr = librosa.load(audio_path, mono=True, duration=max_seconds)
    if y.size == 0: raise ValueError("Audio file contains no decodable samples")
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames", trim=False)
    times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    bpm = float(tempo[0] if getattr(tempo, "ndim", 0) else tempo)
    return bpm, times


def choose_nonrepeating_clips(candidates: Sequence[dict], max_clips: int | None = None,
                              similarity_threshold: float = 0.92) -> list[dict]:
    """Greedy quality selection; rejects shaky/soft clips and near-duplicate visual signatures.

    Candidate keys: score (0..1), stability (0..1), sharpness (0..1), signature (optional vector).
    This is a conservative heuristic, not semantic scene understanding.
    """
    ranked = sorted(candidates, key=lambda c: (float(c.get("stability", 0)) * .4 +
                    float(c.get("sharpness", 0)) * .25 + float(c.get("score", 0)) * .35), reverse=True)
    chosen = []
    for item in ranked:
        if float(item.get("stability", 0)) < .25 or float(item.get("sharpness", 0)) < .08: continue
        sig = item.get("signature")
        duplicate = False
        if sig is not None:
            for prev in chosen:
                other = prev.get("signature")
                if other is None or len(sig) != len(other): continue
                dot = sum(float(a)*float(b) for a,b in zip(sig,other))
                na = sum(float(a)**2 for a in sig) ** .5; nb = sum(float(b)**2 for b in other) ** .5
                similarity = dot / (na*nb) if na and nb else 0
                if similarity >= similarity_threshold: duplicate = True; break
        if not duplicate: chosen.append(item)
        if max_clips is not None and len(chosen) >= max_clips: break
    return chosen
