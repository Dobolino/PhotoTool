from datetime import datetime, timedelta
from pathlib import Path

import pytest

from photobook_curator.models import BookPlan, Photo, Region
from photobook_curator.review_insights import (
    build_motif_groups, build_review_queue, chapter_story_summary, story_role,
)
from photobook_curator.selection import (
    apply_selection_caps, balance_story_roles, build_book_order, mark_candidates,
)
from photobook_curator.story_budget import calculate_book_budget, assess_budget


def photo(index, scene='landschaft', score=90, day=0, **kwargs):
    return Photo(path=Path(f'{index}.jpg'), filename=f'{index}.jpg', scene_type=scene,
                 datetime_taken=datetime(2026, 4, 1) + timedelta(days=day, minutes=index),
                 technical_score=score, final_score=score, region='Tokyo', **kwargs)


def decide(p, value):
    p.manual_decision = value
    return p


def test_page_budget_reserves_title_and_text_pages():
    budget = calculate_book_budget(80, 2.5, 4)
    assert budget.photo_pages == 76
    assert budget.target_count == 190
    assert calculate_book_budget(3, 1.5, 0).target_count == 4


@pytest.mark.parametrize('pages,density,reserved', [(0, 2, 0), (80, 0, 4),
    (80, float('nan'), 4), (80, '2.5', 4), (80, True, 4), (80, 2, 80), (80, 2, -1)])
def test_page_budget_rejects_invalid_inputs(pages, density, reserved):
    with pytest.raises(ValueError):
        calculate_book_budget(pages, density, reserved)


def test_budget_feasibility_accounts_for_day_chapter_caps_and_forced_keeps():
    photos = [photo(i, day=i//10) for i in range(20)]
    plan = BookPlan(regions=[Region('Tokyo', photo_indices=list(range(20)))])
    result = assess_budget(photos, plan, 20, max_per_day=3, max_per_chapter=5)
    assert result.available == 20
    assert result.capacity_upper_bound == 5
    assert not result.feasible
    assert any('höchstens 5' in text for text in result.warnings)
    for p in photos[:6]:
        decide(p, 'keep')
    result = assess_budget(photos, plan, 3, max_per_day=3, max_per_chapter=5)
    assert result.forced_count == 6 and not result.feasible


def test_persistent_keep_and_reject_override_recomputation_and_caps(monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = [photo(i, score=100-i) for i in range(10)]
    decide(photos[0], 'reject')  # Best automatic score must stay rejected.
    decide(photos[8], 'keep')
    decide(photos[9], 'keep')
    photos[9].is_duplicate = True  # Explicit keep overrides the duplicate filter.
    plan = BookPlan(regions=[Region('Tokyo', photo_indices=list(range(10)))])
    mark_candidates(photos, plan, target_n=1)
    order = build_book_order(photos, plan, max_per_day=1, max_per_chapter=1)
    assert {i for i, _, _ in order} == {8, 9}
    assert not photos[0].is_selected
    assert [photos[i].book_position for i, _, _ in order] == [1, 2]


def test_favorite_overrides_conflicting_durable_reject():
    p = decide(photo(0, is_favorite=True), 'reject')
    order = apply_selection_caps([p], [(0, 'Tokyo/hauptteil', 'Hauptteil')], max_per_day=1)
    assert order and p.is_selected


def test_narrative_balance_adds_missing_roles_without_discarding_keeps():
    photos = [photo(0), photo(1, score=89), photo(2, score=88), photo(3, score=87),
              photo(4, 'portrait', 80), photo(5, 'detail', 75), photo(6, 'alltag', 70)]
    decide(photos[0], 'keep')
    result = balance_story_roles(photos, [0, 1, 2, 3], list(range(7)), 4, 1)
    assert 0 in result
    assert {story_role(photos[i]) for i in result} == {'overview', 'people', 'detail', 'atmosphere'}
    photos[6].final_score = 10
    result = balance_story_roles(photos, [0, 1, 2, 3], list(range(7)), 4, 1)
    assert 6 not in result  # No very weak image solely to fill a role.


def test_narrative_balance_keeps_a_scarce_day_represented():
    photos = [photo(0, day=0), photo(1, day=1), photo(2, day=1),
              photo(3, 'portrait', 80, day=1)]
    result = balance_story_roles(photos, [0, 1, 2], list(range(4)), 3, 1, preserve_days=True)
    assert 0 in result and 3 in result


def test_motif_groups_use_existing_evidence_and_recommend_at_most_two():
    photos = [photo(0, burst_group_id=1), photo(1, burst_group_id=1), photo(2, burst_group_id=1)]
    decide(photos[0], 'reject')
    photos[2].is_favorite = True
    groups = build_motif_groups(photos)
    assert len(groups) == 1
    assert groups[0].kind == 'burst' and groups[0].indices == (0, 1, 2)
    assert groups[0].recommended_indices == (2, 1)
    assert groups[0].reasons


def test_uncertain_queue_prioritizes_quality_conflict_and_supplies_alternative():
    photos = [photo(0, is_selected=True, bad_face=True, burst_group_id=1),
              photo(1, score=88, burst_group_id=1), photo(2, score=60)]
    queue = build_review_queue(photos)
    assert queue[0].photo_index == 0
    assert 1 in queue[0].alternatives
    assert any('Qualitäts' in reason for reason in queue[0].reasons)
    assert any('Score' in reason for reason in queue[0].reasons)
    decide(photos[0], 'keep')
    assert all(item.photo_index != 0 for item in build_review_queue(photos))


def test_story_summary_reports_missing_roles_per_chapter():
    photos = [photo(0, is_selected=True), photo(1, 'portrait', is_selected=True),
              photo(2, 'detail')]
    chapter = chapter_story_summary(photos)[0]
    assert chapter.photo_count == 2
    assert chapter.counts['overview'] == 1 and chapter.counts['people'] == 1
    assert set(chapter.missing_roles) == {'detail', 'atmosphere'}


def test_forced_keeps_reserve_global_budget_before_other_regions(monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = [photo(i) for i in range(10)]
    for p in photos[:5]:
        decide(p, 'keep')
    plan = BookPlan(regions=[Region('A', photo_indices=list(range(5))),
                             Region('B', photo_indices=list(range(5, 10)))])
    mark_candidates(photos, plan, target_n=5)
    assert [r.quota for r in plan.regions] == [5, 0]
    order = build_book_order(photos, plan)
    assert {i for i, _, _ in order} == set(range(5))
    assert assess_budget(photos, plan, 5).feasible


def test_forced_keeps_across_regions_transits_and_optional_pool_share_budget(monkeypatch):
    from photobook_curator.models import TransitSection
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = [photo(i) for i in range(12)]
    decide(photos[0], 'keep')
    decide(photos[1], 'keep')
    photos[5].is_favorite = True
    decide(photos[9], 'keep')
    photos[11].is_favorite = photos[11].is_aside = True  # Outside all chapters.
    plan = BookPlan(regions=[Region('A', photo_indices=list(range(5))),
                             Region('B', photo_indices=list(range(5, 9)))],
                    transits=[TransitSection('A', 'B', photo_indices=[9, 10], chapter_index=0)])
    mark_candidates(photos, plan, target_n=8)
    order = build_book_order(photos, plan)
    selected = {i for i, _, _ in order}
    assert {0, 1, 5, 9, 11} <= selected
    assert len(selected) == len(order) == 8
    assert sum(r.quota for r in plan.regions) + plan.transits[0].quota == 7


def test_forced_cap_overflow_uses_only_remaining_global_places(monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = [photo(i) for i in range(10)]
    for p in photos[:5]:
        p.is_favorite = True
    plan = BookPlan(regions=[Region('A', photo_indices=list(range(5))),
                             Region('B', photo_indices=list(range(5, 10)))])
    mark_candidates(photos, plan, target_n=7, max_per_chapter=3)
    assert [r.quota for r in plan.regions] == [5, 2]
    order = build_book_order(photos, plan, max_per_chapter=3)
    assert len(order) == 7
    mark_candidates(photos, plan, target_n=3, max_per_chapter=3)
    order = build_book_order(photos, plan, max_per_chapter=3)
    assert {i for i, _, _ in order} == set(range(5))


def test_transit_forced_keeps_override_transit_cap_but_reserve_album_budget(monkeypatch):
    from photobook_curator.models import TransitSection
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = [photo(i) for i in range(10)]
    for p in photos[:5]:
        decide(p, 'keep')
    plan = BookPlan(regions=[Region('B', photo_indices=list(range(5, 10)))],
                    transits=[TransitSection('A', 'B', photo_indices=list(range(5)), chapter_index=0)])
    mark_candidates(photos, plan, target_n=7, max_transit_quota=2)
    assert plan.transits[0].quota == 5
    assert plan.regions[0].quota == 2
    assert len(build_book_order(photos, plan)) == 7
