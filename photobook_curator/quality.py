"""Phase 1: Schärfe, Belichtung, Kontrast, Sättigung und technischer Score."""

from __future__ import annotations

import cv2
import numpy as np
from tqdm import tqdm

from .models import Photo
from .utils import load_bgr_cached


def analyze_image_quality(photo: Photo) -> None:
    try:
        bgr = load_bgr_cached(photo.path)
    except Exception:
        photo.add_flag("unreadable")
        photo.technical_score = 0.0
        return

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    photo.sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Belichtung über Luminanz-Histogramm
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    hist_norm = hist / max(hist.sum(), 1.0)
    bins = np.arange(256)
    photo.exposure_mean = float((bins * hist_norm).sum())

    dark_ratio = float(hist_norm[:25].sum())
    bright_ratio = float(hist_norm[230:].sum())
    photo.is_too_dark = dark_ratio > 0.55 or photo.exposure_mean < 45
    photo.is_overexposed = bright_ratio > 0.35 or photo.exposure_mean > 220
    if photo.is_too_dark:
        photo.add_flag("too_dark")
    if photo.is_overexposed:
        photo.add_flag("overexposed")

    photo.contrast = float(gray.std())

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    photo.saturation = float(hsv[:, :, 1].mean())


def compute_technical_score(photo: Photo) -> float:
    """Score 0–100 aus Schärfe, Belichtung, Kontrast, Sättigung minus Abzüge."""
    # Empirische Normalisierung für typische Handyfotos
    sharp_n = min(1.0, photo.sharpness / 500.0)
    # Belichtung: Ideal um 110–140
    exposure_penalty = abs(photo.exposure_mean - 125.0) / 125.0
    exposure_n = max(0.0, 1.0 - exposure_penalty)
    contrast_n = min(1.0, photo.contrast / 70.0)
    sat_n = min(1.0, photo.saturation / 100.0)

    score = 100.0 * (
        0.40 * sharp_n + 0.25 * exposure_n + 0.20 * contrast_n + 0.15 * sat_n
    )

    if photo.is_screenshot:
        score -= 40.0
    if photo.is_duplicate:
        score -= 50.0
    if getattr(photo, "is_burst_reject", False):
        score -= 40.0
    if photo.is_too_dark:
        score -= 20.0
    if photo.is_overexposed:
        score -= 20.0
    if "unreadable" in photo.flags:
        score = 0.0

    # Leichter Bonus für erkennbare Personen (Erinnerungswert)
    if photo.face_count >= 1:
        score += min(8.0, 3.0 * photo.face_count)

    # Starke Abzüge bei schlechten Gesichtern (Fotobuch-Killer)
    if getattr(photo, "eyes_closed", False):
        score -= 35.0
    if getattr(photo, "face_cut_off", False):
        score -= 15.0
    if getattr(photo, "face_too_small", False) and photo.face_count >= 1:
        score -= 8.0

    photo.technical_score = float(max(0.0, min(100.0, score)))
    return photo.technical_score


def analyze_all(photos: list[Photo]) -> None:
    for photo in tqdm(photos, desc="Technische Analyse", unit="img"):
        analyze_image_quality(photo)
        compute_technical_score(photo)
