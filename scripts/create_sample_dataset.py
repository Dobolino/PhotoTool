#!/usr/bin/env python3
"""Erzeugt einen kleinen synthetischen Datensatz mit 3 Regionen + Transit."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import piexif
from PIL import Image, ImageDraw


# Ungefähre Koordinaten
REGIONS = {
    "Paris": {"lat": 48.8566, "lon": 2.3522, "day": 0},
    "Lyon": {"lat": 45.7640, "lon": 4.8357, "day": 3},
    "Marseille": {"lat": 43.2965, "lon": 5.3698, "day": 5},
}

# Transit Paris -> Lyon (Tag 2 Abend), Lyon -> Marseille (Tag 4)
TRANSITS = [
    {"from": "Paris", "to": "Lyon", "day": 2, "hour": 14, "count": 4},
    {"from": "Lyon", "to": "Marseille", "day": 4, "hour": 10, "count": 4},
]


def _to_deg(value: float):
    sign = 1 if value >= 0 else -1
    value = abs(value)
    deg = int(value)
    minutes_f = (value - deg) * 60
    minutes = int(minutes_f)
    seconds = (minutes_f - minutes) * 60
    return sign, ((deg, 1), (minutes, 1), (int(seconds * 100), 100))


def make_exif(dt: datetime, lat: float, lon: float, camera: str = "iPhone 14 Pro") -> bytes:
    lat_sign, lat_dms = _to_deg(lat)
    lon_sign, lon_dms = _to_deg(lon)
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: b"Apple",
            piexif.ImageIFD.Model: camera.encode("utf-8"),
            piexif.ImageIFD.DateTime: dt.strftime("%Y:%m:%d %H:%M:%S").encode("utf-8"),
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: dt.strftime("%Y:%m:%d %H:%M:%S").encode("utf-8"),
            piexif.ExifIFD.DateTimeDigitized: dt.strftime("%Y:%m:%d %H:%M:%S").encode("utf-8"),
        },
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N" if lat_sign >= 0 else b"S",
            piexif.GPSIFD.GPSLatitude: lat_dms,
            piexif.GPSIFD.GPSLongitudeRef: b"E" if lon_sign >= 0 else b"W",
            piexif.GPSIFD.GPSLongitude: lon_dms,
        },
    }
    return piexif.dump(exif_dict)


def draw_scene(
    path: Path,
    kind: str,
    seed: int,
    size: tuple[int, int] = (1200, 900),
) -> None:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    img = Image.new("RGB", size, (30, 30, 30))
    draw = ImageDraw.Draw(img)

    if kind == "landschaft":
        sky = (70 + rng.randint(0, 40), 140 + rng.randint(0, 40), 220)
        ground = (40 + rng.randint(0, 30), 120 + rng.randint(0, 40), 50)
        draw.rectangle([0, 0, size[0], size[1] // 2], fill=sky)
        draw.rectangle([0, size[1] // 2, size[0], size[1]], fill=ground)
        # Sonne
        draw.ellipse([size[0] - 220, 40, size[0] - 80, 180], fill=(255, 220, 80))
    elif kind == "essen":
        draw.rectangle([0, 0, size[0], size[1]], fill=(40, 30, 25))
        # Teller
        cx, cy = size[0] // 2, size[1] // 2
        draw.ellipse([cx - 280, cy - 220, cx + 280, cy + 220], fill=(230, 230, 220))
        color = (180 + rng.randint(0, 50), 60 + rng.randint(0, 40), 40)
        draw.ellipse([cx - 160, cy - 120, cx + 160, cy + 120], fill=color)
        # Garnitur
        for _ in range(8):
            x = cx + rng.randint(-140, 140)
            y = cy + rng.randint(-100, 100)
            draw.ellipse([x, y, x + 30, y + 30], fill=(50, 140, 50))
    elif kind == "portrait":
        bg = (200 + rng.randint(0, 40), 200 + rng.randint(0, 40), 190)
        draw.rectangle([0, 0, size[0], size[1]], fill=bg)
        # Gesicht
        cx, cy = size[0] // 2, size[1] // 2 - 40
        draw.ellipse([cx - 140, cy - 180, cx + 140, cy + 180], fill=(230, 190, 160))
        draw.ellipse([cx - 50, cy - 40, cx - 20, cy - 10], fill=(40, 30, 30))
        draw.ellipse([cx + 20, cy - 40, cx + 50, cy - 10], fill=(40, 30, 30))
        draw.arc([cx - 40, cy + 40, cx + 40, cy + 90], 0, 180, fill=(120, 60, 60), width=4)
    elif kind == "transport":
        draw.rectangle([0, 0, size[0], size[1]], fill=(90, 100, 110))
        # Fensterstreifen Zug
        for i in range(4):
            x0 = 40 + i * 280
            draw.rectangle([x0, 120, x0 + 220, 520], fill=(160, 200, 230))
            draw.rectangle([x0, 560, x0 + 220, 780], fill=(50, 50, 55))
    elif kind == "sehenswuerdigkeit":
        draw.rectangle([0, 0, size[0], size[1] // 2], fill=(135, 180, 230))
        draw.rectangle([0, size[1] // 2, size[0], size[1]], fill=(90, 90, 90))
        # Gebäude / Turm
        draw.polygon(
            [(size[0] // 2, 80), (size[0] // 2 - 80, 700), (size[0] // 2 + 80, 700)],
            fill=(60, 60, 70),
        )
        draw.rectangle([size[0] // 2 - 120, 500, size[0] // 2 + 120, 780], fill=(100, 90, 80))
    else:  # alltag / detail
        base = (rng.randint(40, 200), rng.randint(40, 200), rng.randint(40, 200))
        draw.rectangle([0, 0, size[0], size[1]], fill=base)
        for _ in range(12):
            x0 = rng.randint(0, size[0] - 100)
            y0 = rng.randint(0, size[1] - 100)
            c = (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
            draw.rectangle([x0, y0, x0 + rng.randint(40, 160), y0 + rng.randint(40, 160)], fill=c)

    # Leichtes Rauschen für unterschiedliche pHashes
    arr = np.array(img).astype(np.int16)
    noise = np_rng.integers(-12, 13, size=arr.shape, dtype=np.int16)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    Image.fromarray(arr).save(path, quality=92)


def create_dataset(out_dir: Path, base_date: datetime | None = None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    if base_date is None:
        base_date = datetime(2024, 6, 10, 9, 0, 0)

    seq = 0

    def save(name: str, kind: str, dt: datetime, lat: float, lon: float, jitter: float = 0.002):
        nonlocal seq
        seq += 1
        path = out_dir / f"{seq:03d}_{name}.jpg"
        draw_scene(path, kind, seed=seq)
        # GPS-Jitter für realistischere Cluster
        la = lat + random.uniform(-jitter, jitter)
        lo = lon + random.uniform(-jitter, jitter)
        exif = make_exif(dt, la, lo)
        piexif.insert(exif, str(path))
        return path

    random.seed(42)

    # Paris – 2 Tage
    paris = REGIONS["Paris"]
    kinds_p = [
        "landschaft",
        "sehenswuerdigkeit",
        "portrait",
        "essen",
        "alltag",
        "landschaft",
        "essen",
        "detail",
        "gruppe" if False else "portrait",
        "sehenswuerdigkeit",
    ]
    for i, kind in enumerate(kinds_p):
        day = 0 if i < 6 else 1
        dt = base_date.replace(hour=9, minute=0, second=0) + timedelta(
            days=day, hours=i % 8, minutes=10 * i
        )
        save(f"paris_{kind}_{i}", kind, dt, paris["lat"], paris["lon"])

    # Duplikat-Paar in Paris (ähnlich, wenige Minuten)
    dup_dt = base_date.replace(hour=12, minute=5, second=0)
    p1 = save("paris_dup_a", "landschaft", dup_dt, paris["lat"], paris["lon"], jitter=0.0001)
    # zweites Bild fast gleich: Kopie + kleines Rauschen
    img = Image.open(p1)
    arr = np.array(img)
    arr = np.clip(arr.astype(np.int16) + 3, 0, 255).astype(np.uint8)
    p2 = out_dir / f"{seq + 1:03d}_paris_dup_b.jpg"
    seq += 1
    Image.fromarray(arr).save(p2, quality=92)
    piexif.insert(make_exif(dup_dt + timedelta(minutes=1), paris["lat"], paris["lon"]), str(p2))

    # Transit Paris -> Lyon (klarer Zeitspalt zwischen Regionen)
    for i in range(4):
        dt = base_date.replace(hour=14, minute=0, second=0) + timedelta(
            days=2, minutes=15 * i
        )
        # Koordinaten zwischen Paris und Lyon
        t = (i + 1) / 5
        lat = paris["lat"] + t * (REGIONS["Lyon"]["lat"] - paris["lat"])
        lon = paris["lon"] + t * (REGIONS["Lyon"]["lon"] - paris["lon"])
        save(f"transit_paris_lyon_{i}", "transport", dt, lat, lon, jitter=0.01)

    # Lyon
    lyon = REGIONS["Lyon"]
    for i, kind in enumerate(
        ["landschaft", "essen", "portrait", "alltag", "sehenswuerdigkeit", "essen", "detail", "landschaft"]
    ):
        dt = base_date.replace(hour=9, minute=0, second=0) + timedelta(
            days=3, hours=i, minutes=5 * i
        )
        save(f"lyon_{kind}_{i}", kind, dt, lyon["lat"], lyon["lon"])

    # Transit Lyon -> Marseille
    for i in range(4):
        dt = base_date.replace(hour=10, minute=0, second=0) + timedelta(
            days=4, minutes=20 * i
        )
        t = (i + 1) / 5
        lat = lyon["lat"] + t * (REGIONS["Marseille"]["lat"] - lyon["lat"])
        lon = lyon["lon"] + t * (REGIONS["Marseille"]["lon"] - lyon["lon"])
        save(f"transit_lyon_marseille_{i}", "transport", dt, lat, lon, jitter=0.01)

    # Marseille
    marseille = REGIONS["Marseille"]
    for i, kind in enumerate(
        ["landschaft", "portrait", "essen", "sehenswuerdigkeit", "alltag", "detail", "essen"]
    ):
        dt = base_date.replace(hour=10, minute=0, second=0) + timedelta(
            days=5, hours=i, minutes=8 * i
        )
        save(f"marseille_{kind}_{i}", kind, dt, marseille["lat"], marseille["lon"])

    # Ein Bild ohne GPS (zeitlich in Paris)
    seq += 1
    path = out_dir / f"{seq:03d}_paris_no_gps.jpg"
    draw_scene(path, "alltag", seed=seq)
    dt = base_date.replace(hour=14, minute=0, second=0)
    exif_dict = {
        "0th": {
            piexif.ImageIFD.Make: b"Apple",
            piexif.ImageIFD.Model: b"iPhone 14 Pro",
            piexif.ImageIFD.DateTime: dt.strftime("%Y:%m:%d %H:%M:%S").encode("utf-8"),
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: dt.strftime("%Y:%m:%d %H:%M:%S").encode("utf-8"),
        },
    }
    piexif.insert(piexif.dump(exif_dict), str(path))

    # Vermutlicher Screenshot (keine Kamera, Screen-Auflösung)
    seq += 1
    path = out_dir / f"{seq:03d}_screenshot.png"
    Image.new("RGB", (1170, 2532), (20, 20, 40)).save(path)

    print(f"Datensatz erzeugt in {out_dir} ({seq} Dateien)")


if __name__ == "__main__":
    create_dataset(Path("sample_photos"))
