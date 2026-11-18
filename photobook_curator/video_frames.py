"""Best-Frame aus kurzen Videos / Live Photos extrahieren."""

from __future__ import annotations

from pathlib import Path

import cv2
from tqdm import tqdm

from .utils import IMAGE_EXTENSIONS

VIDEO_EXTENSIONS = {".mov", ".mp4", ".m4v", ".avi"}


def find_videos(input_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for p in sorted(input_dir.rglob("*")):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS:
            paths.append(p)
    return paths


def _frame_sharpness(bgr) -> float:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def extract_best_frame(
    video_path: Path,
    dest_jpg: Path,
    *,
    max_sample_frames: int = 24,
) -> Path | None:
    """
    Wählt den schärfsten Frame und speichert ihn als JPEG.
    Returns dest path oder None.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        best_score = -1.0
        best = None
        if total <= 0:
            # sequentiell bis max_sample_frames
            idx = 0
            while idx < max_sample_frames:
                ok, frame = cap.read()
                if not ok:
                    break
                score = _frame_sharpness(frame)
                if score > best_score:
                    best_score = score
                    best = frame
                idx += 1
        else:
            step = max(1, total // max_sample_frames)
            sampled = 0
            for i in range(0, total, step):
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                score = _frame_sharpness(frame)
                if score > best_score:
                    best_score = score
                    best = frame
                sampled += 1
                if sampled >= max_sample_frames:
                    break
        if best is None:
            return None
        dest_jpg.parent.mkdir(parents=True, exist_ok=True)
        ok = cv2.imwrite(str(dest_jpg), best, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        return dest_jpg if ok and dest_jpg.is_file() else None
    finally:
        cap.release()


def extract_video_stills(
    input_dir: Path,
    cache_dir: Path,
    *,
    enabled: bool = True,
) -> list[Path]:
    """
    Extrahiert Best-Frames für Videos ohne schon vorhandenes Schwester-JPG/HEIC.
    Returns Liste neuer Standbild-Pfade.
    """
    if not enabled:
        return []
    videos = find_videos(input_dir)
    if not videos:
        return []
    out: list[Path] = []
    cache_dir.mkdir(parents=True, exist_ok=True)
    for video in tqdm(videos, desc="Video-Standbilder", unit="vid"):
        stem = video.stem
        # Live Photo: oft HEIC/JPG gleichen Namens → Video überspringen
        sibling_exists = any(
            (video.with_suffix(ext)).is_file() for ext in IMAGE_EXTENSIONS
        )
        if sibling_exists:
            continue
        dest = cache_dir / f"{stem}__bestframe.jpg"
        if dest.is_file():
            out.append(dest)
            continue
        path = extract_best_frame(video, dest)
        if path is not None:
            out.append(path)
    return out
