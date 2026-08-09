"""Phase 1: Rekursiver Scan und EXIF-Metadatenextraktion."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import exifread
from tqdm import tqdm

from .models import Photo
from .utils import IMAGE_EXTENSIONS, SCREEN_RESOLUTIONS, is_image_file, load_image, register_heif


def find_images(input_dir: Path) -> list[Path]:
    register_heif()
    paths: list[Path] = []
    for p in sorted(input_dir.rglob("*")):
        if p.is_file() and is_image_file(p):
            paths.append(p)
    return paths


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
        deg = _ratio_to_float(values[0])
        minutes = _ratio_to_float(values[1])
        seconds = _ratio_to_float(values[2])
        if deg is None or minutes is None or seconds is None:
            return None
        dec = deg + minutes / 60.0 + seconds / 3600.0
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


def extract_exif(path: Path) -> dict:
    result = {
        "datetime_taken": None,
        "camera_model": None,
        "gps_lat": None,
        "gps_lon": None,
        "width": 0,
        "height": 0,
    }
    try:
        with open(path, "rb") as f:
            tags = exifread.process_file(f, details=False)
    except Exception:
        tags = {}

    result["datetime_taken"] = _parse_exif_datetime(tags)

    if "Image Model" in tags:
        result["camera_model"] = str(tags["Image Model"]).strip()

    if "GPS GPSLatitude" in tags and "GPS GPSLatitudeRef" in tags:
        lat = _dms_to_decimal(tags["GPS GPSLatitude"].values, str(tags["GPS GPSLatitudeRef"]))
        result["gps_lat"] = lat
    if "GPS GPSLongitude" in tags and "GPS GPSLongitudeRef" in tags:
        lon = _dms_to_decimal(tags["GPS GPSLongitude"].values, str(tags["GPS GPSLongitudeRef"]))
        result["gps_lon"] = lon

    # Bildmasse bevorzugt aus Datei, Fallback EXIF
    try:
        img = load_image(path)
        result["width"], result["height"] = img.size
    except Exception:
        for wkey, hkey in (
            ("EXIF ExifImageWidth", "EXIF ExifImageLength"),
            ("Image ImageWidth", "Image ImageLength"),
        ):
            if wkey in tags and hkey in tags:
                try:
                    result["width"] = int(str(tags[wkey]))
                    result["height"] = int(str(tags[hkey]))
                    break
                except Exception:
                    pass

    return result


def looks_like_screenshot(camera_model: Optional[str], width: int, height: int) -> bool:
    if camera_model:
        return False
    return (width, height) in SCREEN_RESOLUTIONS


def scan_photos(input_dir: Path) -> list[Photo]:
    paths = find_images(input_dir)
    photos: list[Photo] = []
    for path in tqdm(paths, desc="Scan & EXIF", unit="img"):
        meta = extract_exif(path)
        photo = Photo(
            path=path.resolve(),
            filename=path.name,
            datetime_taken=meta["datetime_taken"],
            camera_model=meta["camera_model"],
            gps_lat=meta["gps_lat"],
            gps_lon=meta["gps_lon"],
            width=meta["width"],
            height=meta["height"],
        )
        if looks_like_screenshot(photo.camera_model, photo.width, photo.height):
            photo.is_screenshot = True
            photo.add_flag("screenshot")
        photos.append(photo)
    return photos
