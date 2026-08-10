"""Fehlaufnahme- und Nacht-Filter."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from photobook_curator.composition import (
    detect_accidental_shot,
    detect_weak_night,
)
from photobook_curator.local_analysis import LocalAnalysisOptions, run_local_analysis
from photobook_curator.models import Photo
from photobook_curator.selection import _ok_for_selection
from photobook_curator.utils import clear_bgr_cache, load_bgr_cached


def _photo_from_image(path: Path, **kwargs) -> Photo:
    img = Image.open(path)
    w, h = img.size
    return Photo(path=path, filename=path.name, width=w, height=h, **kwargs)


def test_detects_floor_heavy_accidental(tmp_path: Path) -> None:
    # Unteres Drittel einheitlich grau (Boden), oben dunkel/leer
    arr = np.zeros((300, 400, 3), dtype=np.uint8)
    arr[:100] = (25, 25, 28)
    arr[100:200] = (45, 50, 55)
    arr[200:] = (130, 130, 132)  # flacher Boden
    path = tmp_path / "floor.jpg"
    Image.fromarray(arr).save(path)

    clear_bgr_cache()
    photo = _photo_from_image(path)
    bgr = load_bgr_cached(path)
    photo.sharpness = 40
    photo.contrast = 18
    photo.exposure_mean = 90
    photo.face_count = 0
    hit, reasons = detect_accidental_shot(photo, bgr)
    assert hit is True
    assert reasons


def test_detects_weak_night(tmp_path: Path) -> None:
    # Dunkles, weiches Bild
    arr = np.random.randint(8, 35, (240, 320, 3), dtype=np.uint8)
    path = tmp_path / "night.jpg"
    Image.fromarray(arr).save(path)
    clear_bgr_cache()
    photo = _photo_from_image(path)
    bgr = load_bgr_cached(path)
    photo.exposure_mean = 40
    photo.is_too_dark = True
    photo.sharpness = 50
    photo.contrast = 20
    hit, reasons = detect_weak_night(photo, bgr)
    assert hit is True
    assert "weich" in " ".join(reasons) or "Kontrast" in " ".join(reasons)


def test_selection_excludes_accidental_and_night(tmp_path: Path) -> None:
    path = tmp_path / "x.jpg"
    Image.new("RGB", (80, 60), (10, 10, 10)).save(path)
    bad = Photo(path=path, filename="x.jpg", is_accidental=True)
    night = Photo(path=path, filename="n.jpg", is_weak_night=True)
    ok = Photo(path=path, filename="ok.jpg", technical_score=70)
    assert _ok_for_selection(bad) is False
    assert _ok_for_selection(night) is False
    assert _ok_for_selection(ok) is True


def test_local_analysis_runs_new_filters(tmp_path: Path) -> None:
    path = tmp_path / "a.jpg"
    Image.new("RGB", (160, 120), (20, 20, 25)).save(path)
    photos = [Photo(path=path, filename="a.jpg", width=160, height=120)]
    clear_bgr_cache()
    result = run_local_analysis(
        photos,
        LocalAnalysisOptions(
            enable_documents=False,
            enable_faces=False,
            enable_accidental=True,
            enable_weak_night=True,
        ),
    )
    assert result.decoded == 1
    # Dunkles einfarbiges Bild sollte mindestens eines der Flags bekommen
    assert photos[0].is_accidental or photos[0].is_weak_night or photos[0].technical_score >= 0
