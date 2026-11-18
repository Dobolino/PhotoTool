"""Effective print resolution for a cropped, optionally rotated print size."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from .models import Photo


def effective_dpi(photo: Photo, width_cm: float, height_cm: float) -> float | None:
    if not all(math.isfinite(x) and x > 0 for x in (width_cm, height_cm)):
        raise ValueError("Print dimensions must be finite and positive")
    if photo.width <= 0 or photo.height <= 0:
        return None
    # Filling the rectangle crops the excess edge. Rotation is allowed.
    normal = min(photo.width / width_cm, photo.height / height_cm)
    rotated = min(photo.width / height_cm, photo.height / width_cm)
    return max(normal, rotated) * 2.54


def print_status(dpi: float | None, target: float = 300) -> str:
    if not math.isfinite(target) or target <= 0:
        raise ValueError("Target DPI must be finite and positive")
    if dpi is None:
        return "print_unknown"
    return "print_ok" if dpi >= target else "print_low"


def write_print_report(photos: list[Photo], kept: set[int], path: Path,
                       width_cm: float, height_cm: float, target: float) -> None:
    print_status(None, target)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("filename", "path", "width_cm", "height_cm", "target_dpi", "effective_dpi", "status"))
        for i in sorted(kept):
            p = photos[i]
            dpi = effective_dpi(p, width_cm, height_cm)
            writer.writerow((p.filename, str(p.path), width_cm, height_cm, target,
                             round(dpi, 1) if dpi is not None else "", print_status(dpi, target)))
