"""P2: Pipeline-Fortschritts-Callback."""

from pathlib import Path

from PIL import Image, ImageDraw

from photobook_curator.pipeline import PipelineConfig, run_pipeline


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
