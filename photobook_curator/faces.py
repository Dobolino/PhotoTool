"""Phase 1: Gesichtszählung via MediaPipe Tasks oder OpenCV Haar-Fallback."""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlretrieve

import cv2
import numpy as np
from tqdm import tqdm

from .models import Photo
from .quality import compute_technical_score
from .utils import load_image, to_cv_bgr

# Offizielles MediaPipe Face Detector Modell (short range)
_MP_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)


def _ensure_mp_model(cache_dir: Path) -> Path | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / "blaze_face_short_range.tflite"
    if model_path.exists() and model_path.stat().st_size > 1000:
        return model_path
    try:
        urlretrieve(_MP_MODEL_URL, model_path)
        return model_path
    except Exception:
        if model_path.exists():
            model_path.unlink(missing_ok=True)
        return None


class FaceCounter:
    def __init__(self, model_cache_dir: Path | None = None) -> None:
        self._mode = "none"
        self._legacy_detector = None
        self._tasks_detector = None
        self._haar = None
        self._init_backend(model_cache_dir or Path.home() / ".cache" / "photobook_curator")

    def _init_backend(self, cache_dir: Path) -> None:
        # 1) Legacy mediapipe.solutions (pre-1.0)
        try:
            import mediapipe as mp

            if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_detection"):
                self._legacy_detector = mp.solutions.face_detection.FaceDetection(
                    model_selection=1, min_detection_confidence=0.5
                )
                self._mode = "mediapipe_solutions"
                return
        except Exception:
            pass

        # 2) MediaPipe Tasks API
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            model_path = _ensure_mp_model(cache_dir)
            if model_path is not None:
                base_options = mp_python.BaseOptions(model_asset_path=str(model_path))
                options = vision.FaceDetectorOptions(
                    base_options=base_options,
                    min_detection_confidence=0.5,
                )
                self._tasks_detector = vision.FaceDetector.create_from_options(options)
                self._mode = "mediapipe_tasks"
                return
        except Exception:
            pass

        # 3) OpenCV Haar-Fallback
        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            self._haar = cv2.CascadeClassifier(cascade_path)
            if not self._haar.empty():
                self._mode = "haar"
        except Exception:
            self._mode = "none"

    @property
    def backend(self) -> str:
        return self._mode

    def count(self, bgr: np.ndarray) -> int:
        if self._mode == "mediapipe_solutions" and self._legacy_detector is not None:
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            result = self._legacy_detector.process(rgb)
            if not result.detections:
                return 0
            return len(result.detections)

        if self._mode == "mediapipe_tasks" and self._tasks_detector is not None:
            import mediapipe as mp

            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self._tasks_detector.detect(mp_image)
            return len(result.detections) if result.detections else 0

        if self._mode == "haar" and self._haar is not None:
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
            faces = self._haar.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
            return len(faces)

        return 0

    def close(self) -> None:
        if self._legacy_detector is not None:
            try:
                self._legacy_detector.close()
            except Exception:
                pass
        if self._tasks_detector is not None:
            try:
                self._tasks_detector.close()
            except Exception:
                pass


def count_faces(photos: list[Photo], model_cache_dir: Path | None = None) -> str:
    counter = FaceCounter(model_cache_dir=model_cache_dir)
    backend = counter.backend
    for photo in tqdm(photos, desc=f"Gesichter ({backend})", unit="img"):
        try:
            img = load_image(photo.path)
            bgr = to_cv_bgr(img)
            photo.face_count = counter.count(bgr)
        except Exception:
            photo.face_count = 0
            photo.add_flag("face_failed")
        compute_technical_score(photo)
    counter.close()
    return backend
