"""Tests für AI-Antwort-Parsing und Heuristiken."""

from pathlib import Path

from photobook_curator.ai_review import (
    apply_ai_result,
    estimate_cost,
    heuristic_scene_type,
    parse_ai_response,
)
from photobook_curator.models import Photo


def test_parse_plain_json():
    data = parse_ai_response(
        '{"aesthetic_score": 80, "landmark": null, "scene_type": "essen", '
        '"mood": "gemuetlich", "quality_issue": null, "keep_recommendation": true}'
    )
    assert data is not None
    assert data["scene_type"] == "essen"
    assert data["keep_recommendation"] is True


def test_parse_fenced_json():
    text = """```json
{"aesthetic_score": 55, "landmark": "Eiffelturm", "scene_type": "sehenswuerdigkeit",
 "mood": "wow", "quality_issue": null, "keep_recommendation": true}
```"""
    data = parse_ai_response(text)
    assert data["landmark"] == "Eiffelturm"


def test_parse_invalid():
    assert parse_ai_response("keine json antwort") is None


def test_apply_ai_result():
    photo = Photo(path=Path("x.jpg"), filename="x.jpg")
    apply_ai_result(
        photo,
        {
            "aesthetic_score": 90,
            "landmark": None,
            "scene_type": "portrait",
            "mood": "ruhig",
            "quality_issue": "Augen geschlossen",
            "keep_recommendation": False,
        },
    )
    assert photo.aesthetic_score == 90
    assert photo.scene_type == "portrait"
    assert photo.keep_recommendation is False
    assert "ai_reject" in photo.flags
    assert "quality_issue" in photo.flags


def test_heuristic_from_filename():
    photo = Photo(path=Path("a.jpg"), filename="paris_essen_3.jpg")
    assert heuristic_scene_type(photo) == "essen"
    photo2 = Photo(path=Path("b.jpg"), filename="transit_paris_lyon_0.jpg")
    assert heuristic_scene_type(photo2) == "transport"


def test_cost_estimate():
    cost = estimate_cost(10)
    assert cost["candidates"] == 10
    assert cost["usd_total_estimate"] == 0.1
