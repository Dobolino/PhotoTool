"""Cache-Optionen und sichere Reduktion grosser Fotosammlungen."""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from photobook_curator.analysis_cache import AnalysisCache
from photobook_curator.bursts import mark_bursts
from photobook_curator.content_clusters import mark_content_clusters
from photobook_curator.embeddings import ImageEmbedder, cosine_similarity
from photobook_curator.local_analysis import LocalAnalysisOptions, run_local_analysis
from photobook_curator.models import Photo
from photobook_curator.utils import BgrImageCache, clear_bgr_cache


def _photo(path: Path) -> Photo:
    return Photo(path=path, filename=path.name, width=160, height=120)


def _options(**changes) -> LocalAnalysisOptions:
    values = dict(enable_documents=False, enable_faces=False, enable_finger=False,
                  enable_accidental=False, enable_weak_night=False,
                  enable_embeddings=False, enable_local_aesthetic=False, workers=1)
    values.update(changes)
    return LocalAnalysisOptions(**values)


def test_enabling_faces_after_cached_skip_runs_analyzer(tmp_path, monkeypatch):
    import photobook_curator.local_analysis as la

    path = tmp_path / "a.jpg"
    Image.new("RGB", (160, 120), (30, 80, 160)).save(path)
    calls = []

    class Counter:
        backend = "test-faces"
        def count(self, bgr):
            calls.append("count")
            return 0
        def close(self):
            pass

    class Quality:
        backend = "test-quality"
        def close(self):
            pass

    monkeypatch.setattr(la, "FaceCounter", Counter)
    monkeypatch.setattr(la, "FaceQualityAnalyzer", Quality)
    cache = AnalysisCache(tmp_path / "analysis_cache.sqlite")
    try:
        run_local_analysis([_photo(path)], _options(), cache)
        clear_bgr_cache()
        result = run_local_analysis([_photo(path)], _options(enable_faces=True), cache)
        assert result.cache_hits == 1
        assert calls == ["count"]
        clear_bgr_cache()
        warm = run_local_analysis([_photo(path)], _options(enable_faces=True), cache)
        assert warm.decoded == 0
        assert calls == ["count"]
    finally:
        cache.close()


def test_cached_filter_rejections_follow_enabled_options(tmp_path, monkeypatch):
    import photobook_curator.local_analysis as la

    path = tmp_path / "a.jpg"
    Image.new("RGB", (160, 120), (30, 80, 160)).save(path)
    calls = []

    def composition(photo, bgr, **kwargs):
        calls.append(1)
        photo.is_accidental = photo.is_weak_night = True
        photo.add_flag("accidental")
        photo.add_flag("weak_night")
        return SimpleNamespace(is_accidental=True, is_weak_night=True)

    monkeypatch.setattr(la, "analyze_composition_bgr", composition)
    cache = AnalysisCache(tmp_path / "analysis_cache.sqlite")
    try:
        run_local_analysis([_photo(path)], _options(enable_accidental=True, enable_weak_night=True), cache)
        photo = _photo(path)
        run_local_analysis([photo], _options(), cache)
        assert not photo.is_accidental and not photo.is_weak_night
        assert "accidental" not in photo.flags and "weak_night" not in photo.flags
        run_local_analysis([_photo(path)], _options(enable_accidental=True, enable_weak_night=True), cache)
        assert len(calls) == 2
    finally:
        cache.close()


def test_cached_documents_do_not_require_another_decode(tmp_path):
    path = tmp_path / "a.jpg"
    Image.new("RGB", (160, 120), (30, 80, 160)).save(path)
    cache = AnalysisCache(tmp_path / "analysis_cache.sqlite")
    try:
        run_local_analysis([_photo(path)], _options(enable_documents=True), cache)
        clear_bgr_cache()
        result = run_local_analysis([_photo(path)], _options(enable_documents=True), cache)
        assert result.cache_hits == 1 and result.decoded == 0
    finally:
        cache.close()


def test_pixel_fallback_cannot_trigger_automatic_content_reduction(tmp_path, monkeypatch):
    import photobook_curator.embeddings as embeddings

    class Fallback:
        backend = "fallback"
        def embed_bgr(self, *args, **kwargs):
            raise AssertionError("Pixel-Fallback darf nicht für Auto-Reduktion laufen")
        def close(self):
            pass

    monkeypatch.setattr(embeddings, "ImageEmbedder", Fallback)
    path = tmp_path / "a.jpg"
    Image.new("RGB", (160, 120), (30, 80, 160)).save(path)
    result = run_local_analysis([_photo(path)], _options(enable_embeddings=True))
    assert result.embeddings == {}
    assert any("übersprungen" in note for note in result.notes)
    embedder = ImageEmbedder.__new__(ImageEmbedder)
    embedder._embedder = None
    assert embedder.embed_bgr(np.zeros((16, 16, 3), dtype=np.uint8), allow_fallback=False) is None


def test_cosine_rejects_incompatible_or_invalid_vectors():
    assert cosine_similarity(np.ones(3), np.ones(4)) == 0
    assert cosine_similarity(np.array([np.nan]), np.ones(1)) == 0
    assert cosine_similarity(np.ones(3) * 3, np.ones(3) * 7) > 0.9999


def test_content_clusters_never_choose_burst_reject_as_representative():
    photos = [_photo(Path(f"{i}.jpg")) for i in range(3)]
    for i, photo in enumerate(photos):
        photo.technical_score = 99 - i
    photos[0].is_burst_reject = True
    embeddings = {i: np.ones(4, dtype=np.float32) for i in range(3)}
    assert mark_content_clusters(photos, embeddings) == 1
    assert not photos[1].is_duplicate
    assert photos[2].is_duplicate
    assert photos[0].content_cluster_id is None


def test_burst_ids_do_not_collide_with_strict_phash_groups():
    photos = []
    base = datetime(2024, 1, 1)
    for i in range(6):
        photo = _photo(Path(f"{i}.jpg"))
        photo.datetime_taken = base + timedelta(seconds=i)
        photo.phash = "ffffffffffffffff"
        if i < 3:
            photo.burst_group_id = 1
        photos.append(photo)
    assert mark_bursts(photos, keep_per_burst=2) == 1
    assert {p.burst_group_id for p in photos[:3]} == {1}
    assert {p.burst_group_id for p in photos[3:]} == {2}


def test_bgr_cache_uses_scaled_decode_and_invalidates_changed_file(tmp_path, monkeypatch):
    import photobook_curator.utils as utils

    path = tmp_path / "a.jpg"
    Image.new("RGB", (2400, 1600), (240, 10, 10)).save(path)
    monkeypatch.setattr(utils, "load_image", lambda p: (_ for _ in ()).throw(AssertionError("Volldecode")))
    cache = BgrImageCache(maxsize=2, max_edge=128)
    first = cache.get(path)
    assert first.shape == (85, 128, 3)
    assert cache.get(path) is first
    Image.new("RGB", (2400, 1600), (10, 240, 10)).save(path)
    second = cache.get(path)
    assert second is not first
    assert second[:, :, 1].mean() > first[:, :, 1].mean() + 100


def test_cancel_callback_propagates_and_commits_completed_analysis(tmp_path):
    import pytest

    class StopRequested(Exception):
        pass

    paths = []
    for i in range(3):
        path = tmp_path / f"{i}.jpg"
        Image.new("RGB", (160, 120), (30, 80, 160)).save(path)
        paths.append(path)
    cache_path = tmp_path / "analysis_cache.sqlite"
    cache = AnalysisCache(cache_path)

    def cancel(_):
        raise StopRequested()

    try:
        with pytest.raises(StopRequested):
            run_local_analysis([_photo(p) for p in paths], _options(), cache, progress=cancel)
        # Auch eine zweite Verbindung sieht den gesicherten Checkpoint sofort.
        reader = AnalysisCache(cache_path)
        try:
            assert reader.get(paths[0]) is not None
            assert reader.get(paths[1]) is None
        finally:
            reader.close()
    finally:
        cache.close()
