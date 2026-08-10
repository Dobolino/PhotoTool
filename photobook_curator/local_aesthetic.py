"""Lokale Ästhetik-Heuristik (ohne Cloud-API / ohne Torch)."""

from __future__ import annotations

import cv2
import numpy as np

from .models import Photo


def local_aesthetic_score(photo: Photo, bgr: np.ndarray | None = None) -> float:
    """
    Score 0–10 analog zu typischen KI-Ästhetikwerten.
    Nutzt Schärfe, Belichtung, Kontrast, Sättigung und grobe Drittel-Regel.
    """
    sharp_n = min(1.0, photo.sharpness / 450.0)
    exposure_n = max(0.0, 1.0 - abs(photo.exposure_mean - 118.0) / 118.0)
    contrast_n = min(1.0, photo.contrast / 65.0)
    sat_n = min(1.0, photo.saturation / 90.0)

    thirds = 0.45
    if bgr is not None and bgr.size:
        thirds = _thirds_score(bgr)

    score = 10.0 * (
        0.28 * sharp_n
        + 0.22 * exposure_n
        + 0.18 * contrast_n
        + 0.12 * sat_n
        + 0.20 * thirds
    )
    if getattr(photo, "is_accidental", False):
        score -= 3.0
    if getattr(photo, "is_weak_night", False):
        score -= 2.5
    if getattr(photo, "bad_face", False):
        score -= 1.5
    if getattr(photo, "smiling", None) is True:
        score += 0.4
    if getattr(photo, "looking_at_camera", None) is False and photo.face_count > 0:
        score -= 0.6
    return float(max(0.0, min(10.0, score)))


def _thirds_score(bgr: np.ndarray) -> float:
    """Wie stark Kantenenergie nahe den Drittel-Linien liegt (0–1)."""
    h, w = bgr.shape[:2]
    scale = 360 / max(h, w)
    if scale < 1:
        small = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale))))
    else:
        small = bgr
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 70, 150)
    eh, ew = edges.shape
    total = float(cv2.countNonZero(edges)) + 1e-6
    band_x = max(2, ew // 20)
    band_y = max(2, eh // 20)
    xs = (ew // 3, 2 * ew // 3)
    ys = (eh // 3, 2 * eh // 3)
    mask = np.zeros_like(edges)
    for x in xs:
        mask[:, max(0, x - band_x) : min(ew, x + band_x)] = 255
    for y in ys:
        mask[max(0, y - band_y) : min(eh, y + band_y), :] = 255
    near = float(cv2.countNonZero(cv2.bitwise_and(edges, mask))) / total
    # typische Fotos 0.15–0.45; normalisieren
    return float(max(0.0, min(1.0, (near - 0.08) / 0.35)))


def apply_local_aesthetic(photo: Photo, bgr: np.ndarray | None = None) -> float:
    """Setzt aesthetic_score nur, wenn noch keine KI-Bewertung vorliegt."""
    if photo.aesthetic_score is not None and photo.ai_reviewed:
        return float(photo.aesthetic_score)
    score = local_aesthetic_score(photo, bgr)
    photo.aesthetic_score = score
    return score
