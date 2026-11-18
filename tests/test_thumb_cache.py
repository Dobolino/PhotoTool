"""Vorschau-Thumbnail-Cache (persistente Platten-Ebene)."""

from pathlib import Path

from PIL import Image

from photobook_curator.utils import (
    _thumb_cache_key,
    load_thumb_cached,
    thumb_cache_dir,
    warm_thumb_cache,
)


def _redirect_cache(tmp_path, monkeypatch):
    # thumb_cache_dir liest LOCALAPPDATA zuerst -> in tmp umleiten
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "cache"))


def test_load_thumb_cached_creates_and_reuses(tmp_path, monkeypatch):
    _redirect_cache(tmp_path, monkeypatch)
    src = tmp_path / "big.jpg"
    Image.new("RGB", (400, 300), (10, 120, 90)).save(src)

    img = load_thumb_cached(src, 120)
    assert max(img.size) <= 120

    cached = thumb_cache_dir() / f"{_thumb_cache_key(src, 120)}.jpg"
    assert cached.exists()

    # Zweiter Aufruf: aus dem Cache, RGB, kein Fehler
    img2 = load_thumb_cached(src, 120)
    assert img2.mode == "RGB"
    assert max(img2.size) <= 120


def test_warm_thumb_cache_counts(tmp_path, monkeypatch):
    _redirect_cache(tmp_path, monkeypatch)
    paths = []
    for i in range(3):
        p = tmp_path / f"p{i}.jpg"
        Image.new("RGB", (200, 150), (i * 10, 100, 100)).save(p)
        paths.append(p)

    assert warm_thumb_cache(paths, 120) == 3
    # Erneut: alles schon vorhanden -> nichts Neues erzeugt
    assert warm_thumb_cache(paths, 120) == 0


def test_thumb_cache_key_changes_with_edge(tmp_path, monkeypatch):
    _redirect_cache(tmp_path, monkeypatch)
    src = tmp_path / "x.jpg"
    Image.new("RGB", (100, 100), (0, 0, 0)).save(src)
    assert _thumb_cache_key(src, 120) != _thumb_cache_key(src, 240)
