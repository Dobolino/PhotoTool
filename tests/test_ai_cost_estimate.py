"""KI-Kostenschätzung für die GUI."""

from photobook_curator.ai_review import (
    ESTIMATED_COST_PER_IMAGE_USD,
    estimate_candidate_count,
    estimate_cost,
)


def test_estimate_candidate_count_caps_by_found():
    assert estimate_candidate_count(100, found=50, candidate_factor=4.0) == 50
    assert estimate_candidate_count(100, found=0, candidate_factor=4.0) == 400
    assert estimate_candidate_count(80, found=10000, candidate_factor=4.0) == 320


def test_estimate_cost_matches_per_image_rate():
    est = estimate_cost(1350)
    assert est["candidates"] == 1350
    assert est["usd_per_image"] == ESTIMATED_COST_PER_IMAGE_USD
    assert abs(est["usd_total_estimate"] - 13.5) < 0.01
