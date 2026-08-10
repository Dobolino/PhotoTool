"""Fehlaufnahmen (Komposition) und schwache Nachtaufnahmen erkennen."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .models import Photo

# Fehlaufnahme / Auslöser-Miss
_FLOOR_BAND_UNIFORM = 28.0  # niedrige Farb-Std in Band
_FLOOR_BAND_SHARE = 0.42  # Band deckt viel Fläche ab
_CENTER_EDGE_SHARE_MAX = 0.28  # zu wenig Kanten in der Bildmitte
_BORDER_EDGE_SHARE_MIN = 0.55  # Kanten vor allem am Rand
_TILT_DEG_MIN = 12.0

# Schwache Nacht
_NIGHT_EXPOSURE_MAX = 88.0
_NIGHT_SHARPNESS_MAX = 95.0
_NIGHT_CONTRAST_MAX = 38.0
_NIGHT_NOISE_MIN = 12.0


@dataclass
class CompositionResult:
    is_accidental: bool = False
    is_weak_night: bool = False
    reasons: list[str] | None = None

    def __post_init__(self) -> None:
        if self.reasons is None:
            self.reasons = []


def _band_stats(bgr: np.ndarray) -> tuple[float, float, float]:
    """Std der Farbe in oberem / mittlerem / unterem Drittel."""
    h = bgr.shape[0]
    a, b = h // 3, 2 * h // 3
    bands = (bgr[:a], bgr[a:b], bgr[b:])
    stds = []
    for band in bands:
        stds.append(float(np.std(band.reshape(-1, 3), axis=0).mean()))
    return stds[0], stds[1], stds[2]


def _edge_layout(gray: np.ndarray) -> tuple[float, float]:
    """Anteil der Kanten in Randzone vs. Zentrum (0–1)."""
    h, w = gray.shape[:2]
    edges = cv2.Canny(gray, 60, 140)
    total = float(cv2.countNonZero(edges)) + 1e-6
    mx, my = int(w * 0.12), int(h * 0.12)
    border = edges.copy()
    border[my : h - my, mx : w - mx] = 0
    center = edges[my : h - my, mx : w - mx]
    border_share = float(cv2.countNonZero(border)) / total
    center_share = float(cv2.countNonZero(center)) / total
    return border_share, center_share


def _strong_tilt(gray: np.ndarray) -> bool:
    """Grobe Schräglage über dominante Linien."""
    h, w = gray.shape[:2]
    scale = 480 / max(h, w)
    if scale < 1:
        small = cv2.resize(gray, (max(1, int(w * scale)), max(1, int(h * scale))))
    else:
        small = gray
    edges = cv2.Canny(small, 80, 160)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=max(60, min(small.shape) // 4))
    if lines is None or len(lines) < 4:
        return False
    angles = []
    for item in lines[:40]:
        rho, theta = item[0]
        deg = abs(float(np.degrees(theta)) % 90)
        # Abstand zur Waagrechten/Senkrechten
        dist = min(deg, 90 - deg)
        angles.append(dist)
    if not angles:
        return False
    return float(np.median(angles)) >= _TILT_DEG_MIN


def _noise_estimate(gray: np.ndarray) -> float:
    """Einfaches Hochpass-Rauschmaß (höher = körniger)."""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    residual = cv2.absdiff(gray, blur)
    return float(residual.mean())


def detect_accidental_shot(photo: Photo, bgr: np.ndarray) -> tuple[bool, list[str]]:
    """
    Heuristik für Auslöser-Misses: viel Boden/Himmel, Motiv am Rand, starke Schräge.
    """
    reasons: list[str] = []
    h, w = bgr.shape[:2]
    if h < 80 or w < 80:
        return False, reasons

    scale = 480 / max(h, w)
    if scale < 1:
        small = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale))))
    else:
        small = bgr
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

    top_std, mid_std, bot_std = _band_stats(small)
    border_share, center_share = _edge_layout(gray)

    # Dominanter, flacher Boden ODER Himmel
    overall_std = float(np.std(small.reshape(-1, 3), axis=0).mean()) + 1e-6
    floorish = bot_std <= _FLOOR_BAND_UNIFORM and (bot_std / overall_std) <= 0.55
    skyish = top_std <= _FLOOR_BAND_UNIFORM and (top_std / overall_std) <= 0.55
    empty_center = center_share <= _CENTER_EDGE_SHARE_MAX
    border_heavy = border_share >= _BORDER_EDGE_SHARE_MIN

    if floorish or skyish:
        # flaches Band + vergleichsweise wenig Struktur in der Bildmitte
        if empty_center or center_share < border_share or photo.contrast < 30:
            reasons.append("dominanter Boden/Himmel")
    if border_heavy and empty_center and photo.face_count == 0:
        reasons.append("Motiv am Bildrand / angeschnitten")
    if _strong_tilt(gray) and (empty_center or photo.face_count == 0):
        reasons.append("starke Schräglage")

    # Extrem wenig Inhalt (oft Fehlauslösung gegen Boden/Wand)
    if (
        photo.contrast > 0
        and photo.contrast < 24
        and photo.sharpness < 70
        and photo.face_count == 0
    ):
        reasons.append("kaum Bildinhalt")

    if "dominanter Boden/Himmel" in reasons:
        return True, reasons
    if "kaum Bildinhalt" in reasons and (floorish or skyish or empty_center):
        return True, reasons
    if len(reasons) >= 2:
        return True, reasons
    return False, reasons


def detect_weak_night(photo: Photo, bgr: np.ndarray | None = None) -> tuple[bool, list[str]]:
    """
    Weiche/schwummerige Nachtaufnahmen: dunkel + unscharf + flau (+ Rauschen).
    """
    reasons: list[str] = []
    dark = photo.is_too_dark or photo.exposure_mean <= _NIGHT_EXPOSURE_MAX
    soft = photo.sharpness <= _NIGHT_SHARPNESS_MAX
    flat = photo.contrast <= _NIGHT_CONTRAST_MAX
    if not dark:
        return False, reasons
    if soft:
        reasons.append("weich/unscharf")
    if flat:
        reasons.append("wenig Kontrast")

    noisy = False
    if bgr is not None and dark and soft:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        if max(gray.shape) > 480:
            scale = 480 / max(gray.shape)
            gray = cv2.resize(
                gray,
                (max(1, int(gray.shape[1] * scale)), max(1, int(gray.shape[0] * scale))),
            )
        if _noise_estimate(gray) >= _NIGHT_NOISE_MIN and photo.sharpness < 140:
            noisy = True
            reasons.append("Nacht-Rauschen")

    # Nacht + (weich und flau) oder (weich und rauschig)
    if dark and soft and flat:
        return True, reasons
    if dark and soft and noisy:
        return True, reasons
    return False, reasons


def apply_accidental(photo: Photo, detected: bool, reasons: list[str] | None = None) -> None:
    photo.is_accidental = bool(detected)
    if not detected:
        return
    photo.add_flag("accidental")
    reason_txt = ", ".join(reasons or []) or "Fehlaufnahme"
    photo.add_flag("accidental_shot")
    if not photo.quality_issue:
        photo.quality_issue = f"Fehlaufnahme ({reason_txt})"
    else:
        photo.quality_issue = f"{photo.quality_issue}; Fehlaufnahme ({reason_txt})"


def apply_weak_night(photo: Photo, detected: bool, reasons: list[str] | None = None) -> None:
    photo.is_weak_night = bool(detected)
    if not detected:
        return
    photo.add_flag("weak_night")
    reason_txt = ", ".join(reasons or []) or "schwache Nachtaufnahme"
    if not photo.quality_issue:
        photo.quality_issue = f"Schwache Nachtaufnahme ({reason_txt})"
    else:
        photo.quality_issue = f"{photo.quality_issue}; schwache Nacht ({reason_txt})"


def analyze_composition_bgr(
    photo: Photo,
    bgr: np.ndarray,
    *,
    enable_accidental: bool = True,
    enable_weak_night: bool = True,
) -> CompositionResult:
    """Wendet optionale Filter auf bereits geladenes BGR an (vor finalem Score)."""
    out = CompositionResult()
    if getattr(photo, "is_aside", False) or "unreadable" in photo.flags:
        return out
    if enable_accidental:
        hit, reasons = detect_accidental_shot(photo, bgr)
        apply_accidental(photo, hit, reasons)
        out.is_accidental = hit
        if hit:
            out.reasons.extend(reasons)
    if enable_weak_night:
        hit, reasons = detect_weak_night(photo, bgr)
        apply_weak_night(photo, hit, reasons)
        out.is_weak_night = hit
        if hit:
            out.reasons.extend(reasons)
    return out
