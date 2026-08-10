"""KI-Anbieter: none / Gemini / Anthropic / Ollama."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from photobook_curator.ai_review import (
    PROVIDER_ANTHROPIC,
    PROVIDER_GEMINI,
    PROVIDER_NONE,
    PROVIDER_OLLAMA,
    apply_ai_result,
    estimate_cost,
    is_ai_provider_enabled,
    normalize_ai_provider,
    parse_ai_response,
    run_ai_review,
)
from photobook_curator.models import Photo


def test_normalize_provider_aliases():
    assert normalize_ai_provider(None) == PROVIDER_NONE
    assert normalize_ai_provider("none") == PROVIDER_NONE
    assert normalize_ai_provider("Anthropic") == PROVIDER_ANTHROPIC
    assert normalize_ai_provider("claude") == PROVIDER_ANTHROPIC
    assert normalize_ai_provider("gemini") == PROVIDER_GEMINI
    assert normalize_ai_provider("gratis") == PROVIDER_GEMINI
    assert normalize_ai_provider("free") == PROVIDER_GEMINI
    assert normalize_ai_provider("ollama") == PROVIDER_OLLAMA
    assert normalize_ai_provider("local") == PROVIDER_OLLAMA
    assert is_ai_provider_enabled("none") is False
    assert is_ai_provider_enabled("gemini") is True


def test_estimate_cost_free_providers():
    for prov in ("none", "gemini", "ollama"):
        est = estimate_cost(100, provider=prov)
        assert est["usd_total_estimate"] == 0.0
        assert est["usd_per_image"] == 0.0


def test_estimate_cost_anthropic_unchanged():
    est = estimate_cost(10, provider="anthropic")
    assert est["usd_total_estimate"] == 0.1
    assert est["provider"] == PROVIDER_ANTHROPIC


def test_run_ai_review_none_uses_heuristics():
    photo = Photo(path=Path("paris_essen_3.jpg"), filename="paris_essen_3.jpg")
    stats = run_ai_review([photo], [0], provider="none")
    assert stats["provider"] == PROVIDER_NONE
    assert photo.scene_type == "essen"


def test_run_ai_review_skips_cached():
    photo = Photo(path=Path("a.jpg"), filename="a.jpg")
    photo.ai_reviewed = True
    photo.scene_type = "portrait"
    with patch("photobook_curator.ai_review._review_one_gemini") as mocked:
        stats = run_ai_review([photo], [0], provider="gemini", api_key="x")
    mocked.assert_not_called()
    assert stats["skipped_cached"] == 1
    assert stats["ok"] == 0


def test_run_ai_review_dry_run_gemini():
    photos = [Photo(path=Path("a.jpg"), filename="a.jpg")]
    stats = run_ai_review(photos, [0], dry_run=True, provider="gemini")
    assert stats["dry_run"] is True
    assert stats["usd_total_estimate"] == 0.0
    assert stats["provider"] == PROVIDER_GEMINI


def test_run_ai_review_gemini_applies_result():
    photo = Photo(path=Path("a.jpg"), filename="a.jpg")
    fake_data = {
        "aesthetic_score": 81,
        "landmark": "Torii",
        "scene_type": "sehenswuerdigkeit",
        "mood": "wow",
        "quality_issue": None,
        "keep_recommendation": True,
    }
    fake_genai = MagicMock()
    fake_genai.GenerativeModel.return_value = MagicMock()
    with (
        patch.dict("sys.modules", {"google.generativeai": fake_genai}),
        patch(
            "photobook_curator.ai_review._review_one_gemini",
            return_value=(photo, fake_data, None),
        ),
    ):
        # Ensure import inside run_ai_review sees our mock
        import photobook_curator.ai_review as mod

        with patch.object(mod, "run_ai_review", wraps=mod.run_ai_review):
            with patch.dict(
                "sys.modules",
                {"google": MagicMock(), "google.generativeai": fake_genai},
            ):
                stats = mod.run_ai_review(
                    [photo], [0], provider="gemini", api_key="test-key", concurrency=1
                )
    assert stats["ok"] == 1
    assert photo.ai_reviewed is True
    assert photo.aesthetic_score == 81
    assert photo.landmark == "Torii"


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


def test_run_ai_review_gemini_missing_key_raises():
    photo = Photo(path=Path("a.jpg"), filename="a.jpg")
    import os

    env = {k: v for k, v in os.environ.items() if k not in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
    with patch.dict("os.environ", env, clear=True):
        try:
            run_ai_review([photo], [0], provider="gemini", api_key=None)
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "GEMINI_API_KEY" in str(exc)


def test_parse_and_apply_still_work():
    data = parse_ai_response(
        '{"aesthetic_score": 80, "landmark": null, "scene_type": "essen", '
        '"mood": "ok", "quality_issue": null, "keep_recommendation": true}'
    )
    assert data is not None
    photo = Photo(path=Path("x.jpg"), filename="x.jpg")
    apply_ai_result(photo, data)
    assert photo.scene_type == "essen"
