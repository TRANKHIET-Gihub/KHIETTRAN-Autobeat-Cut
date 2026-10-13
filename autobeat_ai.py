"""Local, explainable AI-assisted video color analysis.

This module uses deterministic computer-vision heuristics (not a trained neural model),
so it works offline and does not upload user footage anywhere.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


def filters_from_statistics(mean_luma: float, mean_bgr: tuple[float, float, float],
                            auto_light: bool = True, auto_color: bool = True,
                            auto_white_balance: bool = True) -> list[str]:
    """Build conservative FFmpeg filters from normalized image statistics.

    mean_luma and B/G/R channel means are normalized to 0..1. Output adjustments
    are intentionally bounded to avoid aggressive grading on a single sample frame.
    """
    if not 0 <= mean_luma <= 1 or len(mean_bgr) != 3 or any(not 0 <= float(v) <= 1 for v in mean_bgr):
        raise ValueError("Image statistics must be normalized to the range 0..1")
    filters: list[str] = []
    if auto_light:
        brightness = max(-0.10, min(0.10, (0.48 - mean_luma) * 0.30))
        contrast = max(0.92, min(1.12, 1.0 + (0.48 - mean_luma) * 0.12))
        filters.append(f"eq=brightness={brightness:.4f}:contrast={contrast:.4f}")
    if auto_color:
        saturation = max(0.88, min(1.12, 1.0 + (0.38 - abs(mean_luma - 0.5)) * 0.12))
        filters.append(f"eq=saturation={saturation:.4f}")
    if auto_white_balance:
        blue, green, red = (float(v) for v in mean_bgr)
        neutral = (blue + green + red) / 3.0
        # Colorbalance values are bounded and centered around zero.
        rs = max(-0.08, min(0.08, (neutral - red) * 0.35))
        gs = max(-0.05, min(0.05, (neutral - green) * 0.20))
        bs = max(-0.08, min(0.08, (neutral - blue) * 0.35))
        filters.append(f"colorbalance=rs={rs:.4f}:gs={gs:.4f}:bs={bs:.4f}:pl=1")
    return filters


def analyze_video_filters(path: str, auto_light: bool = True, auto_color: bool = True,
                          auto_white_balance: bool = True) -> list[str]:
    """Sample a representative frame using OpenCV and return conservative filters."""
    if not any((auto_light, auto_color, auto_white_balance)):
        return []
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for automatic color analysis. Install opencv-python.") from exc
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Video source not found: {source}")
    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            raise RuntimeError(f"Could not open video for color analysis: {source.name}")
        frames = capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        if frames > 1:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(frames * 0.5))
        ok, frame = capture.read()
        if not ok or frame is None:
            raise RuntimeError(f"Could not read a frame for color analysis: {source.name}")
        frame = cv2.resize(frame, (min(320, frame.shape[1]), min(180, frame.shape[0])))
        mean_bgr = tuple(float(v) / 255.0 for v in frame.mean(axis=(0, 1)))
        luma = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_luma = float(luma.mean()) / 255.0
        return filters_from_statistics(mean_luma, mean_bgr, auto_light, auto_color, auto_white_balance)
    finally:
        capture.release()


def trim_source_range(duration_seconds: float, enabled: bool, edge_seconds: float = 2.0) -> tuple[float, float]:
    """Return a safe source range after optionally trimming both ends."""
    duration_seconds = float(duration_seconds)
    edge_seconds = float(edge_seconds)
    if duration_seconds < 0 or edge_seconds < 0:
        raise ValueError("Duration and trim edge must be non-negative")
    start = edge_seconds if enabled else 0.0
    end = duration_seconds - edge_seconds if enabled else duration_seconds
    if end <= start:
        raise ValueError("Source video is too short for the requested edge trim")
    return start, end
