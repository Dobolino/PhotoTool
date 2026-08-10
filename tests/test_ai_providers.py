"""KI-Anbieter: Anthropic vs. Ollama (gratis)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from photobook_curator.ai_review import (
    PROVIDER_ANTHROPIC,
    PROVIDER_OLLAMA,
    apply_ai_result,
    estimate_cost,
    normalize_ai_provider,
    parse_ai_response,
    run_ai_review,
)
from photobook_curator.models import Photo


def test_normalize_provider_aliases():
    assert normalize_ai_provider("Anthropic") == PROVIDER_ANTHROPIC
    assert normalize_ai_provider("claude") == PROVIDER_ANTHROPIC
    assert normalize_ai_provider("ollama") == PROVIDER_OLLAMA
    assert normalize_ai_provider("gratis") == PROVIDER_OLLAMA
    assert normalize_ai_provider("free") == PROVIDER_OLLAMA


def test_estimate_cost_ollama_is_free():
    est = estimate_cost(100, provider="ollama")
    assert est["usd_total_estimate"] == 0.0
    assert est["usd_per_image"] == 0.0
    assert est["provider"] == PROVIDER_OLLAMA


def test_estimate_cost_anthropic_unchanged():
    est = estimate_cost(10, provider="anthropic")
    assert est["usd_total_estimate"] == 0.1
    assert est["provider"] == PROVIDER_ANTHROPIC


def test_run_ai_review_dry_run_ollama():
    photos = [Photo(path=Path("a.jpg"), filename="a.jpg")]
    stats = run_ai_review(photos, [0], dry_run=True, provider="ollama")
    assert stats["dry_run"] is True
    assert stats["usd_total_estimate"] == 0.0
    assert stats["provider"] == PROVIDER_OLLAMA


def test_run_ai_review_ollama_applies_result():
    photo = Photo(path=Path("a.jpg"), filename="a.jpg")
    fake_data = {
        "aesthetic_score": 77,
        "landmark": None,
        "scene_type": "portrait",
        "mood": "ruhig",
        "quality_issue": None,
        "keep_recommendation": True,
    }
    with (
        patch("photobook_curator.ai_review.check_ollama_available", return_value=(True, "ok")),
        patch(
            "photobook_curator.ai_review._review_one_ollama",
            return_value=(photo, fake_data, None),
        ),
    ):
        stats = run_ai_review([photo], [0], provider="ollama", concurrency=1)
    assert stats["ok"] == 1
    assert photo.ai_reviewed is True
    assert photo.aesthetic_score == 77
    assert photo.scene_type == "portrait"


def test_run_ai_review_ollama_unreachable_raises():
    photo = Photo(path=Path("a.jpg"), filename="a.jpg")
    with patch(
        "photobook_curator.ai_review.check_ollama_available",
        return_value=(False, "down"),
    ):
        try:
            run_ai_review([photo], [0], provider="ollama")
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "down" in str(exc)


def test_parse_and_apply_still_work():
    data = parse_ai_response(
        '{"aesthetic_score": 80, "landmark": null, "scene_type": "essen", '
        '"mood": "ok", "quality_issue": null, "keep_recommendation": true}'
    )
    assert data is not None
    photo = Photo(path=Path("x.jpg"), filename="x.jpg")
    apply_ai_result(photo, data)
    assert photo.scene_type == "essen"
