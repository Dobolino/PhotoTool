"""Tests für Finger-vor-der-Linse-Erkennung."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from photobook_curator.finger_obstruction import (
    apply_finger_obstruction,
    detect_soft_border_skin,
    skin_mask_bgr,
)
from photobook_curator.models import Photo
from photobook_curator.selection import mark_candidates
from photobook_curator.models import BookPlan, Region


def test_skin_mask_finds_skin_tone():
    bgr = np.zeros((100, 100, 3), dtype=np.uint8)
    # BGR Hautton
    bgr[20:80, 20:80] = (90, 140, 200)
    mask = skin_mask_bgr(bgr)
    assert int(mask.sum() // 255) > 1000


def test_soft_border_skin_detects_finger_blob():
    # Scharfer Hintergrund + großer weicher Hautblob am linken Rand
    img = Image.new("RGB", (400, 300), (40, 120, 40))
    draw = ImageDraw.Draw(img)
    # strukturierter Hintergrund
    for x in range(0, 400, 8):
        draw.line([(x, 0), (x + 40, 300)], fill=(20, 90, 30), width=2)
    finger = Image.new("RGB", (400, 300), (0, 0, 0))
    fdraw = ImageDraw.Draw(finger)
    fdraw.ellipse([-80, 40, 180, 280], fill=(210, 160, 130))
    finger = finger.filter(ImageFilter.GaussianBlur(radius=18))
    # finger über Hintergrund legen wo nicht schwarz
    base = np.array(img)
    overlay = np.array(finger)
    mask = overlay.sum(axis=2) > 20
    base[mask] = overlay[mask]
    bgr = base[:, :, ::-1].copy()
    detected, ratio = detect_soft_border_skin(bgr)
    assert bool(detected)
    assert ratio >= 0.10


def test_sharp_portrait_skin_not_flagged_as_finger():
    # Scharfe Hautfläche in der Mitte, nicht am Rand dominant
    img = Image.new("RGB", (400, 300), (80, 140, 200))
    draw = ImageDraw.Draw(img)
    draw.ellipse([140, 80, 260, 220], fill=(210, 170, 140))
    # Augen/Details für etwas Schärfe
    draw.ellipse([165, 120, 185, 140], fill=(30, 30, 30))
    draw.ellipse([215, 120, 235, 140], fill=(30, 30, 30))
    bgr = np.array(img)[:, :, ::-1].copy()
    detected, _ratio = detect_soft_border_skin(bgr)
    assert not bool(detected)


def test_apply_finger_obstruction_flags_and_penalizes():
    photo = Photo(
        path=Path("f.jpg"),
        filename="f.jpg",
        technical_score=80.0,
        sharpness=400,
        exposure_mean=120,
        contrast=50,
        saturation=70,
    )
    apply_finger_obstruction(photo, True, 0.2)
    assert photo.finger_on_lens is True
    assert "finger_on_lens" in photo.flags
    assert photo.technical_score <= 30.0


def test_finger_excluded_from_candidates():
    photos = [
        Photo(
            path=Path("ok.jpg"),
            filename="ok.jpg",
            technical_score=90,
            region="Paris",
        ),
        Photo(
            path=Path("bad.jpg"),
            filename="bad.jpg",
            technical_score=95,
            region="Paris",
            finger_on_lens=True,
        ),
    ]
    plan = BookPlan(
        regions=[Region(name="Paris", photo_indices=[0, 1], quota=2, day_count=1)]
    )
    mark_candidates(photos, plan, target_n=2, candidate_factor=1.0)
    assert photos[0].is_candidate is True
    assert photos[1].is_candidate is False
