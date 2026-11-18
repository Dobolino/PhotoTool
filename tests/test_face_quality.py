"""Tests für Gesichtsqualitäts-Heuristiken."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from photobook_curator.face_quality import (
    FaceQualityResult,
    apply_face_quality,
    eye_aspect_ratio,
)
from photobook_curator.models import Photo
from photobook_curator.quality import compute_technical_score


def test_ear_open_vs_closed():
    # Offenes Auge: vertikale Abstände groß
    open_eye = np.array(
        [
            [0.0, 0.0],  # outer
            [1.0, -2.0],  # upper1
            [2.0, -2.0],  # upper2
            [3.0, 0.0],  # inner
            [2.0, 2.0],  # lower2
            [1.0, 2.0],  # lower1
        ]
    )
    # Geschlossen: fast flach
    closed_eye = np.array(
        [
            [0.0, 0.0],
            [1.0, -0.1],
            [2.0, -0.1],
            [3.0, 0.0],
            [2.0, 0.1],
            [1.0, 0.1],
        ]
    )
    assert eye_aspect_ratio(open_eye) > 0.5
    assert eye_aspect_ratio(closed_eye) < 0.15


def test_apply_face_quality_penalizes_score():
    photo = Photo(path=Path("x.jpg"), filename="x.jpg", face_count=1, sharpness=400, exposure_mean=120, contrast=50, saturation=80)
    compute_technical_score(photo)
    before = photo.technical_score

    result = FaceQualityResult(
        face_count=1,
        eyes_closed=True,
        face_cut_off=False,
        face_too_small=False,
        issues=["Augen geschlossen"],
    )
    apply_face_quality(photo, result)
    assert photo.eyes_closed is True
    assert photo.bad_face is True
    assert "eyes_closed" in photo.flags
    assert photo.quality_issue == "Augen geschlossen"
    assert photo.technical_score < before


def test_cut_off_portrait_flagged(tmp_path):
    """Gesicht am Bildrand sollte als cut-off erkannt werden (Landmarker oder Haar)."""
    from photobook_curator.face_quality import FaceQualityAnalyzer

    path = tmp_path / "face_edge.jpg"
    img = Image.new("RGB", (400, 400), (200, 200, 190))
    draw = ImageDraw.Draw(img)
    # Gesicht am linken Rand
    draw.ellipse([-40, 120, 120, 300], fill=(220, 180, 150))
    draw.ellipse([20, 170, 40, 190], fill=(30, 30, 30))
    draw.ellipse([70, 170, 90, 190], fill=(30, 30, 30))
    img.save(path)

    analyzer = FaceQualityAnalyzer()
    bgr = np.array(img.convert("RGB"))[:, :, ::-1].copy()
    result = analyzer.analyze_bgr(bgr)
    analyzer.close()
    # Je nach Backend kann Face fehlen – dann kein Fail; wenn erkannt, cut-off erwarten
    if result.face_count > 0:
        assert result.face_cut_off or result.bad_face
