"""Analyse-Schritte und Fortschritts-IDs."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from photobook_curator.phases import (
    PHASE_STEPS,
    initial_phase_status,
    match_step_id,
    step_enabled,
)
from photobook_curator.pipeline import PipelineConfig, run_pipeline


def test_initial_phase_status_marks_optional_skipped():
    cfg = PipelineConfig(
        input_dir=Path("."),
        output_dir=Path("."),
        enable_faces=False,
        enable_bursts=False,
        enable_document_aside=False,
        enable_finger_filter=False,
        enable_map_preview=False,
        people_balance_intensity=0.0,
    )
    status = initial_phase_status(cfg)
    assert status["phash"] == "pending"
    assert status["duplicates"] == "pending"
    assert status["faces"] == "skipped"
    assert status["bursts"] == "skipped"
    assert status["documents"] == "skipped"
    assert status["finger"] == "skipped"
    assert status["map"] == "skipped"
    assert step_enabled(next(s for s in PHASE_STEPS if s.id == "phash"), cfg)


def test_match_step_id():
    assert match_step_id("pHash…") == "phash"
    assert match_step_id("Technische Analyse…") == "quality"
    assert match_step_id("Fertig") == "done"


def test_pipeline_emits_step_ids(tmp_path: Path):
    inp = tmp_path / "in"
    out = tmp_path / "out"
    inp.mkdir()
    Image.new("RGB", (120, 80), (10, 20, 30)).save(inp / "a.jpg")
    Image.new("RGB", (120, 80), (200, 40, 10)).save(inp / "b.jpg")

    events: list[tuple[str, float, str | None]] = []

    def on_progress(label: str, frac: float, step_id: str | None = None) -> None:
        events.append((label, frac, step_id))

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
    run_pipeline(cfg, progress=on_progress)
    step_ids = [s for _, _, s in events if s]
    assert "scan" in step_ids
    assert "phash" in step_ids
    assert "duplicates" in step_ids
    assert "export" in step_ids
    assert step_ids[-1] == "done"
    assert "faces" not in step_ids
    assert "documents" not in step_ids
