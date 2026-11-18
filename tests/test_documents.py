"""Tests für Optional-Pool: Screenshots/Dokumente."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from photobook_curator.documents import classify_document_image, mark_aside_documents
from photobook_curator.models import Photo
from photobook_curator.output import copy_aside_pool


def test_screenshot_marked_aside():
    photo = Photo(
        path=Path("x.png"),
        filename="037_screenshot.png",
        width=1170,
        height=2532,
        is_screenshot=True,
    )
    is_aside, kind = classify_document_image(photo, None)
    assert is_aside
    assert kind == "screenshot"


def test_boarding_pass_by_name_and_look(tmp_path):
    path = tmp_path / "boarding_pass_ticket.jpg"
    img = Image.new("RGB", (1000, 400), (250, 250, 245))
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 980, 380], outline=(0, 0, 0), width=2)
    draw.rectangle([40, 60, 600, 100], fill=(0, 0, 0))
    img.save(path)
    photo = Photo(path=path, filename=path.name, width=1000, height=400, camera_model="iPhone")
    bgr = np.array(img.convert("RGB"))[:, :, ::-1].copy()
    is_aside, kind = classify_document_image(photo, bgr)
    assert is_aside
    assert kind == "ticket"


def test_mark_and_copy_pool(tmp_path):
    shot = tmp_path / "screen.png"
    Image.new("RGB", (1170, 2532), (10, 10, 20)).save(shot)
    photo = Photo(
        path=shot,
        filename="screenshot.png",
        width=1170,
        height=2532,
        is_screenshot=True,
    )
    photos = [photo]
    n = mark_aside_documents(photos)
    assert n == 1
    assert photo.is_aside
    assert photo.region == "Optional"
    out = tmp_path / "out"
    copied = copy_aside_pool(photos, out)
    assert copied == 1
    assert (out / "optional_dokumente").is_dir()
    assert list((out / "optional_dokumente").glob("*"))
