"""Phase 1: Rekursiver Scan und EXIF-Metadatenextraktion."""

from __future__ import annotations

from datetime import datetime, timedelta
import math
import os
from pathlib import Path
from typing import Iterable, Optional

import exifread
from tqdm import tqdm

from .models import Photo
from .utils import (
    SCREEN_RESOLUTIONS,
    image_display_size,
    is_image_file,
    register_heif,
)


def find_images(input_dir: Path, *, exclude_dirs: Iterable[Path] | None = None) -> list[Path]:
    """Find originals, pruning excluded output trees before descending into them."""
    register_heif()
    excluded = tuple(Path(p).resolve() for p in (exclude_dirs or ()))

    def excluded_path(path: Path) -> bool:
        resolved = path.resolve()
        return any(resolved.is_relative_to(parent) for parent in excluded)

    if excluded_path(input_dir):
        return []
    paths: list[Path] = []
    for directory, child_dirs, filenames in os.walk(input_dir, followlinks=False):
        current = Path(directory)
        child_dirs[:] = [name for name in child_dirs if not excluded_path(current / name)]
        for name in filenames:
            p = current / name
            if p.is_file() and is_image_file(p) and not excluded_path(p):
                paths.append(p)
    return sorted(paths)


def _ratio_to_float(ratio) -> Optional[float]:
    try:
        return float(ratio.num) / float(ratio.den)
    except Exception:
        try:
            return float(ratio)
        except Exception:
            return None


def _dms_to_decimal(values, ref: str) -> Optional[float]:
    try:
        ref = ref.strip().upper()
        if ref not in ("N", "S", "E", "W") or len(values) != 3:
            return None
        deg = _ratio_to_float(values[0])
        minutes = _ratio_to_float(values[1])
        seconds = _ratio_to_float(values[2])
        if deg is None or minutes is None or seconds is None:
            return None
        if not all(math.isfinite(v) for v in (deg, minutes, seconds)):
            return None
        if deg < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
            return None
        dec = deg + minutes / 60.0 + seconds / 3600.0
        if dec > (90 if ref in ("N", "S") else 180):
            return None
        if ref in ("S", "W"):
            dec = -dec
        return dec
    except Exception:
        return None


def _parse_exif_datetime(tags: dict) -> Optional[datetime]:
    for key in ("EXIF DateTimeOriginal", "EXIF DateTimeDigitized", "Image DateTime"):
        if key in tags:
            raw = str(tags[key])
            for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    return datetime.strptime(raw.strip(), fmt)
                except ValueError:
                    continue
    return None


def _parse_exif_offset_hours(tags: dict) -> Optional[float]:
    """EXIF OffsetTime* → Stunden als float, z. B. +09:00 → 9.0."""
    for key in (
        "EXIF OffsetTimeOriginal",
        "EXIF OffsetTimeDigitized",
        "EXIF OffsetTime",
    ):
        if key not in tags:
            continue
        raw = str(tags[key]).strip()
        if not raw or raw in ("+", "-"):
            continue
        try:
            sign = 1.0
            if raw[0] in "+-":
                sign = -1.0 if raw[0] == "-" else 1.0
                raw = raw[1:]
            parts = raw.split(":")
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            return sign * (hours + minutes / 60.0)
        except Exception:
            continue
    return None


def extract_exif(path: Path) -> dict:
    result = {
        "datetime_taken": None,
        "camera_model": None,
        "gps_lat": None,
        "gps_lon": None,
        "width": 0,
        "height": 0,
        "exif_offset_hours": None,
        "gps_invalid": False,
    }
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)
    except Exception:
        tags = {}

    result["datetime_taken"] = _parse_exif_datetime(tags)
    result["exif_offset_hours"] = _parse_exif_offset_hours(tags)

    if "Image Model" in tags:
        result["camera_model"] = str(tags["Image Model"]).strip()

    if "GPS GPSLatitude" in tags and "GPS GPSLatitudeRef" in tags:
        ref = str(tags["GPS GPSLatitudeRef"]).strip().upper()
        if ref in ("N", "S"):
            result["gps_lat"] = _dms_to_decimal(tags["GPS GPSLatitude"].values, ref)
    if "GPS GPSLongitude" in tags and "GPS GPSLongitudeRef" in tags:
        ref = str(tags["GPS GPSLongitudeRef"]).strip().upper()
        if ref in ("E", "W"):
            result["gps_lon"] = _dms_to_decimal(tags["GPS GPSLongitude"].values, ref)
    has_gps_tags = "GPS GPSLatitude" in tags or "GPS GPSLongitude" in tags
    result["gps_invalid"] = has_gps_tags and (result["gps_lat"] is None or result["gps_lon"] is None)

    # Bildmasse in Anzeige-Orientierung, ohne vollen Pixel-Decode
    try:
        result["width"], result["height"] = image_display_size(path)
    except Exception:
        for wkey, hkey in (
            ("EXIF ExifImageWidth", "EXIF ExifImageLength"),
            ("Image ImageWidth", "Image ImageLength"),
        ):
            if wkey in tags and hkey in tags:
                try:
                    result["width"] = int(str(tags[wkey]))
                    result["height"] = int(str(tags[hkey]))
                    # EXIF-Orientation ggf. Breite/Höhe tauschen
                    orient = tags.get("Image Orientation")
                    try:
                        orient_v = int(str(orient).split()[0]) if orient else 1
                    except Exception:
                        orient_v = 1
                    if orient_v in (5, 6, 7, 8):
                        result["width"], result["height"] = result["height"], result["width"]
                    break
                except Exception:
                    pass

    return result


def looks_like_screenshot(camera_model: Optional[str], width: int, height: int) -> bool:
    if camera_model:
        return False
    return (width, height) in SCREEN_RESOLUTIONS


def _apply_timezone_shift(
    taken: Optional[datetime],
    *,
    timezone_offset_hours: float = 0.0,
    apply_exif_offset: bool = False,
    exif_offset_hours: Optional[float] = None,
) -> Optional[datetime]:
    """
    Korrigiert Aufnahmezeiten.
    - timezone_offset_hours: manuelle Verschiebung (Kamera auf Heimatzeit im Urlaub).
    - apply_exif_offset: EXIF OffsetTime auf UTC zurückrechnen (selten nötig).
    """
    if taken is None:
        return None
    dt = taken
    if apply_exif_offset and exif_offset_hours is not None:
        # Lokale EXIF-Zeit → UTC (naive)
        dt = dt - timedelta(hours=float(exif_offset_hours))
    if timezone_offset_hours:
        dt = dt + timedelta(hours=float(timezone_offset_hours))
    return dt


def photo_from_path(
    path: Path,
    *,
    timezone_offset_hours: float = 0.0,
    apply_exif_offset: bool = False,
) -> Photo:
    meta = extract_exif(path)
    taken = _apply_timezone_shift(
        meta["datetime_taken"],
        timezone_offset_hours=timezone_offset_hours,
        apply_exif_offset=apply_exif_offset,
        exif_offset_hours=meta.get("exif_offset_hours"),
    )
    photo = Photo(
        path=path.resolve(),
        filename=path.name,
        datetime_taken=taken,
        camera_model=meta["camera_model"],
        gps_lat=meta["gps_lat"],
        gps_lon=meta["gps_lon"],
        width=meta["width"],
        height=meta["height"],
    )
    if looks_like_screenshot(photo.camera_model, photo.width, photo.height):
        photo.is_screenshot = True
        photo.add_flag("screenshot")
    if meta.get("gps_invalid"):
        photo.add_flag("gps_invalid")
    return photo


def scan_photo_paths(
    paths: Iterable[Path],
    *,
    timezone_offset_hours: float = 0.0,
    apply_exif_offset: bool = False,
    desc: str = "Scan & EXIF",
) -> list[Photo]:
    photos: list[Photo] = []
    path_list = list(paths)
    for path in tqdm(path_list, desc=desc, unit="img"):
        photos.append(
            photo_from_path(
                path,
                timezone_offset_hours=timezone_offset_hours,
                apply_exif_offset=apply_exif_offset,
            )
        )
    return photos


def scan_photos(
    input_dir: Path,
    *,
    timezone_offset_hours: float = 0.0,
    apply_exif_offset: bool = False,
    extra_paths: Iterable[Path] | None = None,
    exclude_dirs: Iterable[Path] | None = None,
) -> list[Photo]:
    # Explicit extracted video stills remain allowed even when stored in output.
    paths = find_images(input_dir, exclude_dirs=exclude_dirs)
    if extra_paths:
        seen = {p.resolve() for p in paths}
        for ep in extra_paths:
            rp = Path(ep).resolve()
            if rp.is_file() and rp not in seen:
                paths.append(rp)
                seen.add(rp)
    return scan_photo_paths(
        paths,
        timezone_offset_hours=timezone_offset_hours,
        apply_exif_offset=apply_exif_offset,
    )
