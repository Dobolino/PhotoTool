"""Tests für Features 1–6: Cache, Embeddings, Zeitzone, Ästhetik, Video, Smile."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from photobook_curator.analysis_cache import AnalysisCache, apply_quality_payload, quality_payload
from photobook_curator.content_clusters import mark_content_clusters
from photobook_curator.embeddings import cosine_similarity, _fallback_embedding
from photobook_curator.face_quality import FaceQualityResult, apply_face_quality
from photobook_curator.local_aesthetic import apply_local_aesthetic
from photobook_curator.models import Photo
from photobook_curator.quality import compute_technical_score
from photobook_curator.scan import _apply_timezone_shift, _parse_exif_offset_hours, scan_photos
from photobook_curator.selection import compute_final_score
from photobook_curator.video_frames import extract_best_frame, extract_video_stills


def test_sqlite_cache_roundtrip_and_embedding(tmp_path: Path) -> None:
    img_path = tmp_path / "a.jpg"
    Image.new("RGB", (80, 60), (20, 80, 160)).save(img_path)
    photo = Photo(
        path=img_path,
        filename="a.jpg",
        sharpness=120.0,
        exposure_mean=110.0,
        contrast=40.0,
        saturation=50.0,
        smiling=True,
        looking_at_camera=True,
        is_accidental=False,
        is_weak_night=False,
    )
    compute_technical_score(photo)
    emb = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    cache = AnalysisCache(tmp_path / "analysis_cache.json")
    assert cache.cache_path.suffix == ".sqlite"
    cache.put(img_path, quality_payload(photo), embedding=emb)
    cache.save()

    cache2 = AnalysisCache(tmp_path / "analysis_cache.json")
    hit = cache2.get(img_path)
    assert hit is not None
    assert hit["smiling"] is True
    assert hit["looking_at_camera"] is True
    photo2 = Photo(path=img_path, filename="a.jpg")
    apply_quality_payload(photo2, hit)
    assert photo2.smiling is True
    got = cache2.get_embedding(img_path)
    assert got is not None
    assert np.allclose(got, emb)
    cache2.close()


def test_legacy_json_migrates_to_sqlite(tmp_path: Path) -> None:
    img_path = tmp_path / "b.jpg"
    Image.new("RGB", (40, 30), (1, 2, 3)).save(img_path)
    st = img_path.stat()
    key = f"{img_path.resolve()}|{st.st_mtime_ns}|{st.st_size}"
    legacy = tmp_path / "analysis_cache.json"
    import json

    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": {
                    key: {
                        "sharpness": 55.0,
                        "exposure_mean": 100.0,
                        "contrast": 20.0,
                        "saturation": 30.0,
                        "is_too_dark": False,
                        "is_overexposed": False,
                        "phash": "abcd",
                        "flags": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    cache = AnalysisCache(legacy)
    hit = cache.get(img_path)
    assert hit is not None
    assert hit["sharpness"] == 55.0
    assert cache.cache_path.suffix == ".sqlite"
    cache.close()


def test_fallback_embedding_and_similarity() -> None:
    a = np.zeros((64, 64, 3), dtype=np.uint8)
    a[:, :, 2] = 200
    b = a.copy()
    c = np.zeros((64, 64, 3), dtype=np.uint8)
    c[:, :, 1] = 200
    ea = _fallback_embedding(a)
    eb = _fallback_embedding(b)
    ec = _fallback_embedding(c)
    assert cosine_similarity(ea, eb) > 0.99
    assert cosine_similarity(ea, ec) < cosine_similarity(ea, eb)


def test_content_clusters_marks_duplicates() -> None:
    photos = [
        Photo(path=Path(f"{i}.jpg"), filename=f"{i}.jpg", datetime_taken=datetime(2024, 1, 1, 12, i))
        for i in range(3)
    ]
    for p in photos:
        p.technical_score = 50.0
    photos[0].technical_score = 90.0
    base = np.asarray([1.0, 0.0, 0.0], dtype=np.float32)
    embeddings = {
        0: base,
        1: base * 0.99 + np.asarray([0.01, 0.0, 0.0], dtype=np.float32),
        2: np.asarray([0.0, 1.0, 0.0], dtype=np.float32),
    }
    # normalize
    for k, v in list(embeddings.items()):
        embeddings[k] = v / (np.linalg.norm(v) + 1e-8)
    marked = mark_content_clusters(photos, embeddings, similarity=0.95, max_hours=24.0)
    assert marked >= 1
    assert photos[0].is_duplicate is False
    assert photos[1].is_duplicate is True
    assert photos[1].content_cluster_id is not None


def test_timezone_offset_shift() -> None:
    raw = datetime(2024, 6, 1, 10, 0, 0)
    shifted = _apply_timezone_shift(raw, timezone_offset_hours=9.0)
    assert shifted == datetime(2024, 6, 1, 19, 0, 0)
    with_exif = _apply_timezone_shift(
        raw, timezone_offset_hours=0.0, apply_exif_offset=True, exif_offset_hours=9.0
    )
    assert with_exif == datetime(2024, 6, 1, 1, 0, 0)


def test_parse_exif_offset_hours() -> None:
    assert _parse_exif_offset_hours({"EXIF OffsetTimeOriginal": "+09:00"}) == 9.0
    assert _parse_exif_offset_hours({"EXIF OffsetTime": "-05:30"}) == -5.5


def test_scan_applies_timezone(tmp_path: Path) -> None:
    # Minimal JPEG without EXIF datetime – just ensures scan API accepts offset
    path = tmp_path / "x.jpg"
    Image.new("RGB", (32, 24), (10, 10, 10)).save(path)
    photos = scan_photos(tmp_path, timezone_offset_hours=2.0)
    assert len(photos) == 1


def test_local_aesthetic_sets_score(tmp_path: Path) -> None:
    path = tmp_path / "aes.jpg"
    img = Image.new("RGB", (200, 150), (90, 110, 140))
    ImageDraw.Draw(img).line([(20, 50), (180, 100)], fill=(255, 255, 255), width=3)
    img.save(path)
    photo = Photo(
        path=path,
        filename="aes.jpg",
        sharpness=300.0,
        exposure_mean=120.0,
        contrast=45.0,
        saturation=60.0,
        smiling=True,
    )
    bgr = np.asarray(img.convert("RGB"))[:, :, ::-1].copy()
    score = apply_local_aesthetic(photo, bgr)
    assert 0.0 <= score <= 10.0
    assert photo.aesthetic_score == score
    # AI-reviewed scores bleiben erhalten
    photo.ai_reviewed = True
    photo.aesthetic_score = 8.5
    assert apply_local_aesthetic(photo, bgr) == 8.5


def test_video_best_frame(tmp_path: Path) -> None:
    # Synthetic "video" via OpenCV VideoWriter
    import cv2

    video = tmp_path / "clip.mp4"
    writer = cv2.VideoWriter(
        str(video),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5.0,
        (80, 60),
    )
    assert writer.isOpened()
    for i in range(8):
        frame = np.zeros((60, 80, 3), dtype=np.uint8)
        # Frame 4 is sharpest (high-contrast edges)
        if i == 4:
            frame[:, ::2] = 255
            frame[::2, :] = 128
        else:
            frame[:] = 40 + i * 5
        writer.write(frame)
    writer.release()

    dest = tmp_path / "best.jpg"
    out = extract_best_frame(video, dest, max_sample_frames=8)
    assert out is not None and dest.is_file()

    # Sibling image → skip
    sibling = tmp_path / "clip.jpg"
    Image.new("RGB", (20, 20), (1, 1, 1)).save(sibling)
    stills = extract_video_stills(tmp_path, tmp_path / "stills", enabled=True)
    assert stills == [] or all("clip" not in p.stem or "__bestframe" not in p.name for p in stills)


def test_smile_and_looking_flags() -> None:
    photo = Photo(path=Path("x.jpg"), filename="x.jpg", face_count=1, sharpness=400, exposure_mean=120, contrast=50, saturation=80)
    compute_technical_score(photo)
    result = FaceQualityResult(
        face_count=1,
        eyes_closed=False,
        smiling=True,
        looking_at_camera=False,
        issues=["schaut nicht in die Kamera"],
    )
    apply_face_quality(photo, result)
    assert photo.smiling is True
    assert photo.looking_at_camera is False
    assert "looking_away" in photo.flags
    compute_final_score(photo)
    # looking_away reduces relative to smile-only
    photo2 = Photo(path=Path("y.jpg"), filename="y.jpg", face_count=1, sharpness=400, exposure_mean=120, contrast=50, saturation=80, smiling=True, looking_at_camera=True)
    compute_technical_score(photo2)
    compute_final_score(photo2)
    assert photo2.final_score >= photo.final_score
