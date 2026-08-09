"""Hilfsfunktionen: Bildladen, HEIC-Support, Normalisierung, Modell-Download."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Optional
from urllib.request import urlretrieve

import numpy as np
from PIL import Image, ImageOps

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
DEFAULT_DOWNLOAD_TIMEOUT_S = 30.0
MIN_MODEL_BYTES = 1000

# Typische Screenshot-Auflösungen (Breite x Höhe, beide Orientierungen)
SCREEN_RESOLUTIONS = {
    (1170, 2532), (2532, 1170),  # iPhone 12/13
    (1284, 2778), (2778, 1284),  # iPhone 12/13 Pro Max
    (1125, 2436), (2436, 1125),  # iPhone X/XS
    (1242, 2688), (2688, 1242),  # iPhone XS Max
    (1179, 2556), (2556, 1179),  # iPhone 14/15
    (1290, 2796), (2796, 1290),  # iPhone 14/15 Pro Max
    (1080, 2340), (2340, 1080),
    (750, 1334), (1334, 750),
    (640, 1136), (1136, 640),
    (1920, 1080), (1080, 1920),
    (2560, 1440), (1440, 2560),
}


_heif_registered = False


def register_heif() -> None:
    global _heif_registered
    if _heif_registered:
        return
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
        _heif_registered = True
    except Exception:
        pass


def is_image_file(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def load_image(path: Path) -> Image.Image:
    """Lädt ein Bild und wendet EXIF-Orientierung an (iPhone hochkant korrekt)."""
    register_heif()
    img = Image.open(path)
    img.load()
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")
    return img


def download_model(
    url: str,
    dest: Path,
    *,
    timeout: float = DEFAULT_DOWNLOAD_TIMEOUT_S,
    min_bytes: int = MIN_MODEL_BYTES,
) -> Path | None:
    """
    Lädt ein Modell mit Timeout herunter.
    Verwirft unvollständige Dateien; bei Fehler None.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > min_bytes:
        return dest

    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        urlretrieve(url, dest)
        if not dest.exists() or dest.stat().st_size < min_bytes:
            dest.unlink(missing_ok=True)
            return None
        return dest
    except Exception:
        if dest.exists():
            dest.unlink(missing_ok=True)
        return None
    finally:
        socket.setdefaulttimeout(old_timeout)


def to_cv_bgr(img: Image.Image) -> np.ndarray:
    import cv2

    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def resize_max_edge(img: Image.Image, max_edge: int = 1024) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        return img.copy()
    scale = max_edge / float(longest)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def normalize_01(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return float(max(0.0, min(1.0, (value - lo) / (hi - lo))))


def slugify(name: str) -> str:
    out: list[str] = []
    for ch in name.strip():
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        elif ch in (" ", "/", "\\", ",", ":"):
            out.append("-")
        elif ch in ("ä", "Ä"):
            out.append("ae")
        elif ch in ("ö", "Ö"):
            out.append("oe")
        elif ch in ("ü", "Ü"):
            out.append("ue")
        elif ch == "ß":
            out.append("ss")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "Unbenannt"
