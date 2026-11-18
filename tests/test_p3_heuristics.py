"""P3: Szenen-Heuristik, Haversine-Cluster, Analyse-Cache, Haar-Augen."""

from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from photobook_curator.ai_review import _visual_scene_hint, heuristic_scene_type
from photobook_curator.analysis_cache import AnalysisCache, apply_quality_payload, quality_payload
from photobook_curator.face_quality import FaceQualityAnalyzer
from photobook_curator.models import Photo
from photobook_curator.quality import analyze_all, analyze_image_quality, compute_technical_score
from photobook_curator.regions import cluster_fine_locations
from photobook_curator.utils import clear_bgr_cache


def test_haar_analyze_never_sets_eyes_closed():
    """Haar-Pfad setzt eyes_closed immer False (Unit auf _analyze_haar)."""
    import cv2

    analyzer = FaceQualityAnalyzer()
    analyzer._mode = "haar"
    # Dummy-Classifier umgehen: Methode mit Fake-Faces stubben
    class _FakeHaar:
        def detectMultiScale(self, *args, **kwargs):
            return np.array([[10, 10, 120, 140]], dtype=np.int32)

    analyzer._haar_face = _FakeHaar()
    bgr = np.zeros((200, 200, 3), dtype=np.uint8)
    bgr[:] = (200, 180, 160)
    result = analyzer._analyze_haar(bgr, 200, 200)
    assert result.eyes_closed is False
    assert result.face_count == 1
    analyzer.close()
    _ = cv2


def test_haversine_clusters_nearby_points():
    photos = []
    # ~200 m auseinander in Paris
    coords = [
        (48.8566, 2.3522),
        (48.8575, 2.3530),
        (48.8570, 2.3515),
    ]
    for i, (lat, lon) in enumerate(coords):
        photos.append(
            Photo(
                path=Path(f"{i}.jpg"),
                filename=f"{i}.jpg",
                datetime_taken=datetime(2024, 6, 1, 10, i),
                gps_lat=lat,
                gps_lon=lon,
            )
        )
    clusters = cluster_fine_locations(photos, eps_meters=400, min_samples=2)
    # Alle drei sollten in einem Cluster landen (oder höchstens Noise-Singletons vermeiden)
    member_counts = [len(c.photo_indices) for c in clusters]
    assert max(member_counts) >= 2


def test_visual_food_hint(tmp_path: Path):
    path = tmp_path / "food.jpg"
    # warmes, gesättigtes Bild ohne Gesichter
    img = Image.new("RGB", (200, 150), (220, 120, 40))
    ImageDraw.Draw(img).ellipse([40, 30, 160, 120], fill=(200, 60, 30))
    img.save(path)
    photo = Photo(
        path=path,
        filename="IMG_1.jpg",
        face_count=0,
        sharpness=120,
        contrast=40,
        saturation=90,
    )
    clear_bgr_cache()
    analyze_image_quality(photo)
    hint = _visual_scene_hint(photo)
    assert hint == "essen" or heuristic_scene_type(photo) == "essen"


def test_visual_landscape_hint(tmp_path: Path):
    path = tmp_path / "land.jpg"
    img = Image.new("RGB", (200, 150), (60, 140, 60))
    draw = ImageDraw.Draw(img)
    # heller blauer Himmel oben
    draw.rectangle([0, 0, 200, 55], fill=(180, 210, 240))
    img.save(path)
    photo = Photo(
        path=path,
        filename="IMG_2.jpg",
        face_count=0,
        sharpness=200,
        contrast=50,
        saturation=60,
    )
    clear_bgr_cache()
    analyze_image_quality(photo)
    scene = heuristic_scene_type(photo)
    assert scene in ("landschaft", "alltag")
    # Himmel-Heuristik sollte landschaft bevorzugen
    assert _visual_scene_hint(photo) == "landschaft" or scene == "landschaft"


def test_analysis_cache_hit(tmp_path: Path):
    inp = tmp_path / "p.jpg"
    img = Image.new("RGB", (120, 90), (40, 90, 130))
    ImageDraw.Draw(img).line([(0, 0), (120, 90)], fill=(255, 255, 0), width=3)
    ImageDraw.Draw(img).rectangle([10, 10, 50, 50], outline=(0, 0, 0), width=2)
    img.save(inp)
    photo = Photo(path=inp, filename="p.jpg")
    clear_bgr_cache()
    analyze_image_quality(photo)
    compute_technical_score(photo)
    cache = AnalysisCache(tmp_path / "analysis_cache.json")
    cache.put(inp, quality_payload(photo))
    cache.save()

    photo2 = Photo(path=inp, filename="p.jpg")
    cache2 = AnalysisCache(tmp_path / "analysis_cache.json")
    hit = cache2.get(inp)
    assert hit is not None
    apply_quality_payload(photo2, hit)
    assert abs(photo2.sharpness - photo.sharpness) < 1e-6

    # analyze_all soll Cache nutzen
    photos = [Photo(path=inp, filename="p.jpg")]
    analyze_all(photos, cache=cache2)
    assert abs(photos[0].sharpness - photo.sharpness) < 1e-6
