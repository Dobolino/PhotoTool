"""P2: Pipeline-Fortschritts-Callback und Abbruch."""

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from photobook_curator.pipeline import (
    PipelineCancelled,
    PipelineConfig,
    run_pipeline,
)


def test_run_pipeline_reports_progress(tmp_path: Path):
    inp = tmp_path / "in"
    out = tmp_path / "out"
    inp.mkdir()

    a = Image.new("RGB", (160, 120), (20, 80, 140))
    ImageDraw.Draw(a).rectangle([0, 0, 40, 120], fill=(255, 200, 0))
    a.save(inp / "a.jpg")
    b = Image.new("RGB", (160, 120), (200, 40, 30))
    ImageDraw.Draw(b).ellipse([20, 20, 140, 100], fill=(0, 180, 80))
    b.save(inp / "b.jpg")

    events: list[tuple[str, float]] = []

    def on_progress(label: str, frac: float) -> None:
        events.append((label, frac))

    cfg = PipelineConfig(
        input_dir=inp,
        output_dir=out,
        target_n=2,
        geocode=False,
        enable_faces=False,
        enable_bursts=False,
        enable_document_aside=False,
        enable_finger_filter=False,
        enable_map_preview=False,
    )
    result = run_pipeline(cfg, progress=on_progress)
    assert result.get("dry_run") is False
    assert events
    assert events[-1] == ("Fertig", 1.0)
    assert any(f >= 0.5 for _, f in events)
    assert any("Einlesen" in label or "Analyse" in label for label, _ in events)


def test_run_pipeline_can_be_cancelled(tmp_path: Path):
    """cancel_check True → PipelineCancelled an der ersten Phasengrenze, kein Export."""
    inp = tmp_path / "in"
    out = tmp_path / "out"
    inp.mkdir()

    cfg = PipelineConfig(
        input_dir=inp,
        output_dir=out,
        geocode=False,
        enable_faces=False,
        enable_bursts=False,
        enable_document_aside=False,
        enable_finger_filter=False,
        enable_map_preview=False,
    )
    with pytest.raises(PipelineCancelled):
        run_pipeline(cfg, cancel_check=lambda: True)

    # Abbruch vor dem Export: kein selected/ geschrieben
    assert not (out / "selected").exists()


def test_pipeline_rejects_shared_source_and_output_before_writes(tmp_path):
    cfg = PipelineConfig(input_dir=tmp_path, output_dir=tmp_path)
    with pytest.raises(RuntimeError, match='verschieden'):
        run_pipeline(cfg)
    assert not (tmp_path / 'analysis_cache.sqlite').exists()


def test_pipeline_does_not_reimport_nested_export(tmp_path):
    inp = tmp_path / 'in'
    inp.mkdir()
    out = inp / 'album'
    (out / 'selected').mkdir(parents=True)
    Image.new('RGB', (160, 120), (20, 80, 140)).save(inp / 'source.jpg')
    Image.new('RGB', (160, 120), (20, 80, 140)).save(out / 'selected' / 'old.jpg')
    cfg = PipelineConfig(input_dir=inp, output_dir=out, target_n=1,
                         enable_faces=False, enable_content_clusters=False,
                         enable_document_aside=False, geocode=False)
    result = run_pipeline(cfg)
    assert result['photos'] == 1
    assert [p.filename for p in result['photo_objects']] == ['source.jpg']


def test_empty_input_does_not_replace_existing_album(tmp_path):
    inp, out = tmp_path / 'in', tmp_path / 'out'
    inp.mkdir()
    (out / 'selected').mkdir(parents=True)
    original = out / 'selected' / 'keep.jpg'
    original.write_bytes(b'previous album')
    cfg = PipelineConfig(input_dir=inp, output_dir=out, enable_faces=False,
                         enable_content_clusters=False, geocode=False)
    with pytest.raises(RuntimeError, match='Keine unterstützten'):
        run_pipeline(cfg)
    assert original.read_bytes() == b'previous album'


def test_input_inside_output_is_rejected_before_export_can_replace_originals(tmp_path):
    inp = tmp_path / 'selected' / 'originals'
    inp.mkdir(parents=True)
    cfg = PipelineConfig(input_dir=inp, output_dir=tmp_path)
    with pytest.raises(RuntimeError, match='umfassen'):
        run_pipeline(cfg)
