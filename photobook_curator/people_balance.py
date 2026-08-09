"""Personen-Balance: Gesichter clustern und Überrepräsentation dämpfen."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image
from tqdm import tqdm

from .models import Photo
from .utils import download_model, load_image, to_cv_bgr

# MediaPipe Face Detector Modell (gleich wie faces.py)
_MP_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/"
    "blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)


def _ensure_detector_model(cache_dir: Path) -> Path | None:
    return download_model(_MP_MODEL_URL, cache_dir / "blaze_face_short_range.tflite")


def _face_signature(crop_bgr: np.ndarray) -> str | None:
    """Kompakte Signatur eines Gesichtscrops (pHash)."""
    try:
        if crop_bgr.size == 0:
            return None
        rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        img = img.resize((64, 64), Image.Resampling.LANCZOS)
        return str(imagehash.phash(img, hash_size=8))
    except Exception:
        return None


def _hamming(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


class FaceCropper:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self._mode = "none"
        self._detector = None
        self._init(cache_dir or Path.home() / ".cache" / "photobook_curator")

    def _init(self, cache_dir: Path) -> None:
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            model = _ensure_detector_model(cache_dir)
            if model is None:
                return
            options = vision.FaceDetectorOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(model)),
                min_detection_confidence=0.45,
            )
            self._detector = vision.FaceDetector.create_from_options(options)
            self._mode = "mediapipe"
        except Exception:
            self._mode = "none"

    @property
    def backend(self) -> str:
        return self._mode

    def crops(self, bgr: np.ndarray) -> list[np.ndarray]:
        if self._mode != "mediapipe" or self._detector is None:
            return []
        import mediapipe as mp

        h, w = bgr.shape[:2]
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        result = self._detector.detect(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        )
        out: list[np.ndarray] = []
        if not result.detections:
            return out
        for det in result.detections:
            bbox = det.bounding_box
            x0 = max(0, int(bbox.origin_x))
            y0 = max(0, int(bbox.origin_y))
            x1 = min(w, int(bbox.origin_x + bbox.width))
            y1 = min(h, int(bbox.origin_y + bbox.height))
            if x1 - x0 < 24 or y1 - y0 < 24:
                continue
            # etwas Kontext
            pad_x = int(0.1 * (x1 - x0))
            pad_y = int(0.1 * (y1 - y0))
            xa, ya = max(0, x0 - pad_x), max(0, y0 - pad_y)
            xb, yb = min(w, x1 + pad_x), min(h, y1 + pad_y)
            out.append(bgr[ya:yb, xa:xb].copy())
        return out

    def close(self) -> None:
        if self._detector is not None:
            try:
                self._detector.close()
            except Exception:
                pass


def analyze_people_clusters(
    photos: list[Photo],
    hash_threshold: int = 12,
) -> str:
    """
    Erkennt Gesichter, clustert ähnliche Crops zu Personen-IDs
    und speichert photo.person_cluster_ids.
    """
    cropper = FaceCropper()
    backend = cropper.backend
    # (photo_idx, sig)
    face_entries: list[tuple[int, str]] = []

    for i, photo in enumerate(tqdm(photos, desc=f"Personen-Cluster ({backend})", unit="img")):
        photo.person_cluster_ids = []
        if getattr(photo, "is_aside", False) or "unreadable" in photo.flags:
            continue
        try:
            bgr = to_cv_bgr(load_image(photo.path))
        except Exception:
            continue
        for crop in cropper.crops(bgr):
            sig = _face_signature(crop)
            if sig:
                face_entries.append((i, sig))

    cropper.close()
    if not face_entries:
        return backend

    parent = list(range(len(face_entries)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for a in range(len(face_entries)):
        for b in range(a + 1, len(face_entries)):
            if _hamming(face_entries[a][1], face_entries[b][1]) <= hash_threshold:
                union(a, b)

    root_to_id: dict[int, int] = {}
    next_id = 1
    photo_people: dict[int, set[int]] = defaultdict(set)
    for idx, (photo_i, _sig) in enumerate(face_entries):
        root = find(idx)
        if root not in root_to_id:
            root_to_id[root] = next_id
            next_id += 1
        photo_people[photo_i].add(root_to_id[root])

    for photo_i, people in photo_people.items():
        photos[photo_i].person_cluster_ids = sorted(people)
        if people:
            photos[photo_i].add_flag("people_clustered")

    return backend


def people_balance_penalty(
    photo: Photo,
    person_counts: dict[int, int],
    intensity: float,
) -> float:
    """Abzug für bereits oft vorkommende Personen; Bonus für neue Gesichter."""
    if intensity <= 0:
        return 0.0
    ids = getattr(photo, "person_cluster_ids", None) or []
    if not ids:
        # leichte Bevorzugung von Personenfotos bleibt dem normalen Score überlassen
        return 0.0
    over = sum(person_counts.get(pid, 0) for pid in ids)
    new_people = sum(1 for pid in ids if person_counts.get(pid, 0) == 0)
    # intensitätsabhängiger Abzug / Bonus
    return float(intensity * (14.0 * over - 6.0 * new_people))
