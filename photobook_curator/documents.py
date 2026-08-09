"""Erkennung von Screenshots, Dokumenten, Tickets – separat als Optional-Pool."""

from __future__ import annotations

import re

import cv2
import numpy as np
from tqdm import tqdm

from .models import Photo
from .utils import SCREEN_RESOLUTIONS, load_bgr_cached

ASIDE_FOLDER = "99_Optional_Dokumente"
ASIDE_TYPES = ("screenshot", "dokument", "karte", "ticket")

_NAME_HINTS = re.compile(
    r"(screenshot|screen[_-]?shot|boarding|ticket|pass|qr|barcode|rechnung|invoice|map|karte|chat|whatsapp|imessage)",
    re.IGNORECASE,
)


def _filename_hint(photo: Photo) -> str | None:
    name = photo.filename
    if _NAME_HINTS.search(name):
        lower = name.lower()
        if "board" in lower or "ticket" in lower or "pass" in lower:
            return "ticket"
        if "map" in lower or "karte" in lower:
            return "karte"
        if "screen" in lower or "chat" in lower or "whatsapp" in lower:
            return "screenshot"
        return "dokument"
    return None


def _looks_like_phone_ui(width: int, height: int, camera_model: str | None) -> bool:
    if (width, height) in SCREEN_RESOLUTIONS:
        return True
    if camera_model:
        return False
    # Sehr schlanke Handy-Seitenverhältnisse ohne Kameramodell
    if width > 0 and height > 0:
        ratio = max(width, height) / min(width, height)
        if ratio >= 1.9 and min(width, height) >= 640:
            return True
    return False


def classify_document_image(photo: Photo, bgr: np.ndarray | None = None) -> tuple[bool, str | None]:
    """
    Returns (is_aside, aside_type).
    Heuristik ohne OCR: Screenshot-Metadaten, Dateiname, flache/helle Textflächen.
    """
    hint = _filename_hint(photo)
    if photo.is_screenshot or _looks_like_phone_ui(photo.width, photo.height, photo.camera_model):
        return True, hint or "screenshot"

    if hint:
        return True, hint

    if bgr is None:
        return False, None

    h, w = bgr.shape[:2]
    if h < 80 or w < 80:
        return False, None

    # Analyse auf verkleinerter Kopie
    scale = 400 / max(h, w)
    if scale < 1:
        small = cv2.resize(bgr, (max(1, int(w * scale)), max(1, int(h * scale))))
    else:
        small = bgr
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

    # Sehr helle, flache Flächen (Dokumente/Tickets)
    bright_ratio = float((gray > 200).mean())
    sat_mean = float(hsv[:, :, 1].mean())
    edges = cv2.Canny(gray, 80, 160)
    edge_ratio = float((edges > 0).mean())

    # Dokument: viel Weiß, wenig Sättigung, aber genug Kanten (Text/Linien)
    if bright_ratio >= 0.55 and sat_mean <= 45 and 0.02 <= edge_ratio <= 0.25:
        return True, "dokument"

    # Karten-ähnlich: mittlere Sättigung, viele feine Kanten, oft viel Grau/Grün-Blau
    if edge_ratio >= 0.12 and sat_mean <= 70 and bright_ratio >= 0.25:
        # Zusätzlich: geringe „Foto-Varianz“ in Farbe
        color_std = float(np.std(small.reshape(-1, 3), axis=0).mean())
        if color_std < 45:
            return True, "karte"

    return False, None


def mark_aside_documents(photos: list[Photo]) -> int:
    """Markiert Screenshots/Dokumente als Optional-Pool (nicht Auto-Kapitel)."""
    count = 0
    for photo in tqdm(photos, desc="Dokumente/Screenshots", unit="img"):
        bgr = None
        # Bild nur laden, wenn Metadaten/Name nicht schon reichen
        need_pixels = not (
            photo.is_screenshot
            or _filename_hint(photo)
            or _looks_like_phone_ui(photo.width, photo.height, photo.camera_model)
        )
        if need_pixels:
            try:
                bgr = load_bgr_cached(photo.path)
            except Exception:
                bgr = None

        is_aside, aside_type = classify_document_image(photo, bgr)
        if not is_aside:
            continue
        photo.is_aside = True
        photo.aside_type = aside_type or "dokument"
        photo.add_flag("aside")
        photo.add_flag(f"aside_{photo.aside_type}")
        # Aus Regionen/Transit heraushalten – eigener Optional-Pool
        photo.region = "Optional"
        if photo.is_screenshot and "screenshot" not in photo.flags:
            photo.add_flag("screenshot")
        count += 1
    return count


def aside_indices(photos: list[Photo]) -> list[int]:
    return [i for i, p in enumerate(photos) if getattr(p, "is_aside", False)]
