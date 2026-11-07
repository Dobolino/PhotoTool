"""Holiday selection budgets, global caps and coverage before candidate pruning."""
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from photobook_curator.models import BookPlan, Photo, Region, TransitSection
from photobook_curator.selection import (
    allocate_day_quotas, apply_selection_caps, build_book_order,
    distribute_quotas, mark_candidates,
)


def make_photos(n=20):
    return [Photo(path=Path(f'{i}.jpg'), filename=f'{i}.jpg',
                  datetime_taken=datetime(2026, 4, 1) + timedelta(days=i // 10, minutes=i),
                  technical_score=100-i, final_score=100-i, scene_type='alltag')
            for i in range(n)]


def test_total_budget_smaller_than_number_of_chapters():
    photos = make_photos()
    plan = BookPlan(regions=[Region(name=str(i), photo_indices=[i]) for i in range(10)])
    distribute_quotas(photos, plan, target_n=3)
    assert sum(r.quota for r in plan.regions) == 3
    assert all(0 <= r.quota <= 1 for r in plan.regions)


def test_transits_cannot_exceed_entire_album_budget():
    photos = make_photos()
    plan = BookPlan(transits=[TransitSection('A', 'B', photo_indices=list(range(5))),
                              TransitSection('B', 'C', photo_indices=list(range(5, 10)))])
    distribute_quotas(photos, plan, target_n=3)
    assert sum(t.quota for t in plan.transits) == 3


def test_chapter_budget_redistributed_to_eligible_capacity():
    photos = make_photos()
    photos[0].is_duplicate = True
    plan = BookPlan(regions=[Region('Tokyo', photo_indices=list(range(18))),
                             Region('Kyoto', photo_indices=[18, 19])])
    distribute_quotas(photos, plan, target_n=20, max_per_chapter=5)
    assert [r.quota for r in plan.regions] == [5, 2]


def test_candidate_coverage_keeps_quiet_day_and_resets_stale_flags():
    photos = make_photos()
    photos[-1].is_candidate = True
    photos[-1].is_aside = True
    plan = BookPlan(regions=[Region('Tokyo', photo_indices=list(range(20)))])
    candidates = mark_candidates(photos, plan, target_n=4, candidate_factor=1,
                                 coverage_intensity=1)
    assert len(candidates) == 4
    assert Counter(photos[i].datetime_taken.day for i in candidates) == {1: 2, 2: 2}
    assert not photos[-1].is_candidate


def test_day_allocation_fills_capacity_after_scarce_days():
    quotas = allocate_day_quotas({'busy': 200, 'quiet': 1}, quota=100, intensity=0)
    assert sum(quotas.values()) == 100
    assert quotas['busy'] <= 200 and quotas['quiet'] <= 1
    strong = allocate_day_quotas({'busy': 200, 'quiet': 1}, quota=100, intensity=1)
    assert strong == {'busy': 60, 'quiet': 1}
    assert allocate_day_quotas({'single': 200}, quota=100, intensity=1) == {'single': 100}


def test_day_cap_is_album_wide_and_favorites_reserve_capacity():
    photos = make_photos()
    photos[9].is_favorite = True  # low score retained before higher-scored pictures
    order = [(i, ('01_Tokyo/hauptteil' if i < 5 else '02_Kyoto/essen'), 'Hauptteil')
             for i in range(10)]
    selected = apply_selection_caps(photos, order, max_per_day=3)
    assert [i for i, _, _ in selected] == [0, 1, 9]
    assert not photos[2].is_selected


def test_chapter_cap_shared_by_food_and_main_and_favorites_override():
    photos = make_photos()
    order = [(i, '01_Tokyo/' + ('essen' if i % 2 else 'hauptteil'), 'Hauptteil')
             for i in range(8)]
    photos[6].is_favorite = photos[7].is_favorite = True
    assert [e[0] for e in apply_selection_caps(photos, order, max_per_chapter=3)] == [0, 6, 7]
    assert [e[0] for e in apply_selection_caps(photos, order, max_per_chapter=1)] == [6, 7]


def test_build_order_applies_caps_and_clears_previous_selection(monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = make_photos()
    for p in photos:
        p.is_selected = p.is_candidate = True
        p.book_position = 99
    plan = BookPlan(regions=[Region('Tokyo', photo_indices=list(range(20)), quota=20)])
    order = build_book_order(photos, plan, max_per_day=3, max_per_chapter=5)
    assert len(order) == 5
    assert max(Counter(photos[i].datetime_taken.date() for i, _, _ in order).values()) <= 3
    assert [photos[i].book_position for i, _, _ in order] == list(range(1, 6))
    assert all(p.book_position is None for p in photos if not p.is_selected)


def test_day_caps_refill_from_quieter_days_instead_of_underfilling(monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = [Photo(
        path=Path(f'{i}.jpg'), filename=f'{i}.jpg',
        datetime_taken=datetime(2026, 4, 1) + timedelta(days=0 if i < 100 else 1, minutes=i),
        technical_score=90 if i < 100 else 60, scene_type='alltag',
    ) for i in range(110)]
    plan = BookPlan(regions=[Region('Tokyo', photo_indices=list(range(110)))])
    mark_candidates(photos, plan, target_n=20, max_per_day=10)
    order = build_book_order(photos, plan, max_per_day=10)
    assert len(order) == 20
    assert Counter(photos[i].datetime_taken.date() for i, _, _ in order) == {
        datetime(2026, 4, 1).date(): 10,
        datetime(2026, 4, 2).date(): 10,
    }
    assert [photos[i].datetime_taken for i, _, _ in order] == sorted(photos[i].datetime_taken for i, _, _ in order)
    assert [photos[i].book_position for i, _, _ in order] == list(range(1, 21))


def test_refill_respects_food_budget_and_reject_filters():
    photos = make_photos()
    photos[11].is_duplicate = True
    original = [(i, '01_Tokyo/hauptteil', 'Hauptteil') for i in range(4)]
    original.append((4, '01_Tokyo/essen', 'Essen'))
    fallbacks = [(i, '01_Tokyo/essen', 'Essen') for i in range(10, 15)]
    selected = apply_selection_caps(photos, original, max_per_day=2, fallback_order=fallbacks)
    assert [e[0] for e in selected] == [0, 1, 10]
    assert sum(folder.endswith('/essen') for _, folder, _ in selected) == 1


def test_refill_respects_chapter_caps_and_protected_favorites():
    photos = make_photos()
    photos[8].is_favorite = True
    original = [(i, '01_Tokyo/hauptteil', 'Hauptteil') for i in range(4)]
    original.append((8, '01_Tokyo/hauptteil', 'Hauptteil'))
    fallbacks = [(i, '01_Tokyo/hauptteil', 'Hauptteil') for i in range(10, 20)]
    selected = apply_selection_caps(photos, original, max_per_day=2, max_per_chapter=3, fallback_order=fallbacks)
    assert [e[0] for e in selected] == [0, 8, 10]


def test_zero_food_ratio_disables_automatic_food_but_retains_favorites(monkeypatch):
    from photobook_curator.selection import select_for_region

    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = make_photos()
    for photo in photos:
        photo.is_candidate = True
    photos[10].scene_type = 'essen'
    main, food = select_for_region(photos, list(range(20)), quota=5, food_ratio=0)
    assert len(main) == 5
    assert food == []
    photos[10].is_favorite = True
    main, food = select_for_region(photos, list(range(20)), quota=5, food_ratio=0)
    assert len(main) == 4
    assert food == [10]
