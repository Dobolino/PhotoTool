"""Optionale Erkennung: Finger vor der Linse / große Haut-Verdeckung am Bildrand."""

from __future__ import annotations

from pathlib import Path
from urllib.request import urlretrieve

import cv2
import numpy as np
from tqdm import tqdm

from .models import Photo
from .utils import load_image, to_cv_bgr

_HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)

# Heuristik-Schwellen für typischen Finger-vor-der-Linse-Fehler
MIN_COVER_RATIO = 0.10  # mind. 10% der Bildfläche
MIN_BORDER_TOUCH_RATIO = 0.15  # Anteil der Kontur am Bildrand
SOFTNESS_RATIO = 0.55  # Region deutlich weicher als Rest des Bildes
HAND_AREA_RATIO = 0.12  # große Hand nahe Kamera


def _ensure_hand_model(cache_dir: Path) -> Path | None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    model_path = cache_dir / "hand_landmarker.task"
    if model_path.exists() and model_path.stat().st_size > 1000:
        return model_path
    try:
        urlretrieve(_HAND_MODEL_URL, model_path)
        if model_path.stat().st_size < 1000:
            model_path.unlink(missing_ok=True)
            return None
        return model_path
    except Exception:
        if model_path.exists():
            model_path.unlink(missing_ok=True)
        return None


def skin_mask_bgr(bgr: np.ndarray) -> np.ndarray:
    """Einfache Hautmaske (YCrCb + HSV), robust genug für Finger-Blobs."""
    ycrcb = cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb)
    # typische Hautbereiche
    mask_y = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask_h = cv2.inRange(hsv, (0, 30, 50), (25, 180, 255))
    mask_h2 = cv2.inRange(hsv, (160, 30, 50), (180, 180, 255))
    mask = cv2.bitwise_or(mask_y, cv2.bitwise_or(mask_h, mask_h2))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    return mask


def detect_soft_border_skin(bgr: np.ndarray) -> tuple[bool, float]:
    """
    Erkennt große, weiche Hautflächen am Bildrand (klassischer Finger vor Linse).
    Returns (detected, cover_ratio).
    """
    h, w = bgr.shape[:2]
    area = float(h * w)
    if area < 1:
        return False, 0.0

    mask = skin_mask_bgr(bgr)
    n_skin = int(cv2.countNonZero(mask))
    if n_skin / area < MIN_COVER_RATIO:
        return False, n_skin / area

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # lokale Weichheit über Laplacian-Varianz in der Maske vs. außerhalb
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    lap2 = lap * lap
    skin_vals = lap2[mask > 0]
    other_vals = lap2[mask == 0]
    if skin_vals.size < 100 or other_vals.size < 100:
        return False, n_skin / area
    skin_sharp = float(skin_vals.mean())
    other_sharp = float(other_vals.mean()) + 1e-6
    softness = skin_sharp / other_sharp  # klein = weicher

    # größte Komponente
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    best_ratio = 0.0
    best_border = 0.0
    for i in range(1, num):
        x, y, bw, bh, ca = stats[i]
        ratio = ca / area
        if ratio < MIN_COVER_RATIO:
            continue
        # Randberührung der Komponente
        comp = labels == i
        border_pixels = 0
        border_pixels += int(np.count_nonzero(comp[0, :]))
        border_pixels += int(np.count_nonzero(comp[-1, :]))
        border_pixels += int(np.count_nonzero(comp[:, 0]))
        border_pixels += int(np.count_nonzero(comp[:, -1]))
        perimeter_est = max(1, 2 * (bw + bh))
        border_touch = border_pixels / perimeter_est
        if ratio > best_ratio:
            best_ratio = ratio
            best_border = border_touch

    # Finger vor Linse: groß, weich, am Rand
    detected = (
        best_ratio >= MIN_COVER_RATIO
        and best_border >= MIN_BORDER_TOUCH_RATIO
        and softness <= SOFTNESS_RATIO
    )
    return detected, best_ratio


def detect_large_hand_mediapipe(bgr: np.ndarray, landmarker) -> bool:
    """Große Hand nahe der Kamera via MediaPipe Hand Landmarker."""
    if landmarker is None:
        return False
    import mediapipe as mp

    h, w = bgr.shape[:2]
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
    if not result.hand_landmarks:
        return False
    for hand in result.hand_landmarks:
        xs = [lm.x for lm in hand]
        ys = [lm.y for lm in hand]
        if not xs or not ys:
            continue
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        # Bounding-Box-Anteil der Bildfläche (normalisierte Koords)
        box_area = max(0.0, bw) * max(0.0, bh)
        # Nähe zum Rand: Finger oft von außen rein
        min_edge = min(min(xs), min(ys), 1.0 - max(xs), 1.0 - max(ys))
        if box_area >= HAND_AREA_RATIO and min_edge < 0.08:
            return True
        # Sehr große Hand irgendwo im Bild (Linse fast zu)
        if box_area >= 0.28:
            return True
    return False


class FingerObstructionAnalyzer:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self._mode = "heuristic"
        self._landmarker = None
        self._init(cache_dir or Path.home() / ".cache" / "photobook_curator")

    def _init(self, cache_dir: Path) -> None:
        try:
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision

            model = _ensure_hand_model(cache_dir)
            if model is None:
                return
            options = vision.HandLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(model)),
                num_hands=2,
                min_hand_detection_confidence=0.4,
                min_hand_presence_confidence=0.4,
            )
            self._landmarker = vision.HandLandmarker.create_from_options(options)
            self._mode = "mediapipe+heuristic"
        except Exception:
            self._mode = "heuristic"

    @property
    def backend(self) -> str:
        return self._mode

    def analyze_bgr(self, bgr: np.ndarray) -> tuple[bool, float]:
        soft, ratio = detect_soft_border_skin(bgr)
        if soft:
            return True, ratio
        if detect_large_hand_mediapipe(bgr, self._landmarker):
            return True, max(ratio, HAND_AREA_RATIO)
        return False, ratio

    def close(self) -> None:
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception:
                pass


def apply_finger_obstruction(photo: Photo, detected: bool, cover_ratio: float = 0.0) -> None:
    photo.finger_on_lens = bool(detected)
    if not detected:
        return
    photo.add_flag("finger_on_lens")
    if not photo.quality_issue:
        photo.quality_issue = "Finger vor der Linse"
    else:
        photo.quality_issue = f"{photo.quality_issue}; Finger vor der Linse"
    # starker Score-Abzug; Auswahl schließt zusätzlich aus
    photo.technical_score = float(max(0.0, photo.technical_score - 50.0))
    _ = cover_ratio


def analyze_finger_obstruction(photos: list[Photo]) -> str:
    """Markiert Fotos mit Finger vor der Linse. Gibt Backend-Namen zurück."""
    analyzer = FingerObstructionAnalyzer()
    backend = analyzer.backend
    for photo in tqdm(photos, desc=f"Finger-Check ({backend})", unit="img"):
        if getattr(photo, "is_aside", False) or "unreadable" in photo.flags:
            photo.finger_on_lens = False
            continue
        try:
            bgr = to_cv_bgr(load_image(photo.path))
        except Exception:
            photo.finger_on_lens = False
            continue
        detected, ratio = analyzer.analyze_bgr(bgr)
        apply_finger_obstruction(photo, detected, ratio)
        # Score nach Flags neu berechnen behalten wir nicht – Abzug bereits gesetzt
        if not detected:
            # sicherstellen, dass Feld existiert
            photo.finger_on_lens = False
    analyzer.close()
    return backend
