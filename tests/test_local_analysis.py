"""Lokale Analyse: ein Decode pro Foto für mehrere Features."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from photobook_curator.local_analysis import LocalAnalysisOptions, run_local_analysis
from photobook_curator.models import Photo
from photobook_curator.scan import scan_photos
from photobook_curator.utils import clear_bgr_cache


def test_local_analysis_decodes_once_per_photo(tmp_path: Path, monkeypatch) -> None:
    inp = tmp_path / "in"
    inp.mkdir()
    for name, color in (("a.jpg", (10, 20, 30)), ("b.jpg", (200, 40, 10))):
        Image.new("RGB", (160, 120), color).save(inp / name)

    photos = scan_photos(inp)
    assert len(photos) == 2
    clear_bgr_cache()

    calls: list[str] = []
    import photobook_curator.local_analysis as la

    real = la.load_bgr_cached

    def counting_load(path, max_edge=1024):
        calls.append(str(path))
        return real(path, max_edge=max_edge)

    monkeypatch.setattr(la, "load_bgr_cached", counting_load)

    result = run_local_analysis(
        photos,
        LocalAnalysisOptions(
            enable_documents=True,
            enable_faces=True,
            enable_finger=False,
        ),
        cache=None,
    )
    # Genau ein Decode je Foto – nicht Qualität+Docs+pHash+Faces getrennt
    assert result.decoded == 2
    assert len(calls) == 2
    assert all(p.phash for p in photos)
    assert all(p.technical_score >= 0 for p in photos)


def test_local_analysis_marks_screenshot_aside(tmp_path: Path) -> None:
    path = tmp_path / "Screenshot_ticket.png"
    Image.new("RGB", (200, 400), (240, 240, 240)).save(path)
    photos = [
        Photo(
            path=path,
            filename=path.name,
            width=200,
            height=400,
            is_screenshot=True,
        )
    ]
    clear_bgr_cache()
    result = run_local_analysis(
        photos,
        LocalAnalysisOptions(enable_documents=True, enable_faces=False),
    )
    assert result.aside_count == 1
    assert photos[0].is_aside
