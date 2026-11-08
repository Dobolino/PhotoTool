"""Evidence labels and review ordering must not imply unrelated photos are best."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from photobook_curator.models import Photo
from photobook_curator.review_compare import (
    candidate_relation,
    comparison_candidates,
    ordered_album_indices,
)


def photo(name, **kwargs):
    return Photo(path=Path("/trip") / name, filename=Path(name).name, **kwargs)


def test_landscape_and_unrelated_statue_have_only_contextual_relationship():
    photos = [
        photo("landscape.jpg", chapter_folder="01_Kyoto/hauptteil", region="Kyoto", scene_type="landschaft"),
        photo("statue.jpg", chapter_folder="01_Kyoto/hauptteil", region="Kyoto", scene_type="detail", is_candidate=True, final_score=99),
    ]
    assert candidate_relation(photos, 0, 1) == ("other", "Weitere Aufnahmen")
    assert comparison_candidates(photos, 0, {0}) == [1]
    assert "best" not in candidate_relation(photos, 0, 1)[1].casefold()


def test_related_rejects_precede_high_scoring_unrelated_candidates():
    photos = [
        photo("album.jpg", burst_group_id=7, content_cluster_id=3, region="Kyoto"),
        photo("statue.jpg", region="Kyoto", is_candidate=True, final_score=99),
        photo("burst.jpg", burst_group_id=7, is_burst_reject=True, final_score=40),
        photo("visual.jpg", content_cluster_id=3, is_duplicate=True, final_score=60),
    ]
    assert candidate_relation(photos, 0, 2) == ("series", "Serie")
    assert candidate_relation(photos, 0, 3) == ("visual", "Visuelle Gruppe")
    assert comparison_candidates(photos, 0, {0}) == [3, 2, 1]


def test_duplicate_basename_must_identify_one_photo_unambiguously():
    photos = [
        photo("camera-a/IMG_0001.JPG", region="Kyoto"),
        photo("camera-b/IMG_0001.JPG", region="Kyoto"),
        photo("copy.JPG", duplicate_of="IMG_0001.JPG", is_duplicate=True),
    ]
    assert candidate_relation(photos, 0, 2)[0] == "other"
    assert candidate_relation(photos, 1, 2)[0] == "other"
    assert comparison_candidates(photos, 0, {0, 1}) == []
    photos[2].duplicate_of = str(photos[0].path)
    assert candidate_relation(photos, 0, 2)[0] == "duplicate"
    assert candidate_relation(photos, 1, 2)[0] == "other"


def test_unique_duplicate_link_works_in_both_directions_and_for_zero_group_id():
    photos = [photo("original.jpg"), photo("copy.jpg", duplicate_of="original.jpg")]
    assert candidate_relation(photos, 0, 1) == ("duplicate", "Duplikatbezug")
    assert candidate_relation(photos, 1, 0)[0] == "duplicate"
    photos[0].burst_group_id = photos[1].burst_group_id = 0
    assert candidate_relation(photos, 0, 1)[0] == "series"


def test_missing_group_ids_and_missing_regions_do_not_match_everything():
    photos = [photo("album.jpg"), photo("candidate.jpg", is_candidate=True)]
    assert candidate_relation(photos, 0, 1)[0] == "other"
    assert comparison_candidates(photos, 0, {0}) == []


def test_kept_and_unreadable_are_excluded_but_manual_reject_can_be_inspected():
    photos = [
        photo("album.jpg", burst_group_id=2),
        photo("already-kept.jpg", burst_group_id=2),
        photo("unreadable.jpg", burst_group_id=2, flags=["unreadable"]),
        photo("manual-reject.jpg", burst_group_id=2, manual_decision="reject"),
    ]
    assert comparison_candidates(photos, 0, {0, 1}) == [3]


def test_pool_is_frozen_and_helpers_do_not_mutate_metadata_or_kept_set():
    photos = [
        photo("album.jpg", region="Kyoto"),
        photo("a.jpg", region="Kyoto", is_candidate=True, final_score=70),
        photo("b.jpg", region="Kyoto", is_candidate=True, final_score=70),
    ]
    before = deepcopy(photos)
    kept = {0}
    pool = comparison_candidates(photos, 0, kept)
    assert pool == [1, 2]
    assert photos == before and kept == {0}
    kept.add(1)
    assert pool == [1, 2]
    assert comparison_candidates(photos, 0, kept) == [2]


def test_fallback_can_use_same_chapter_without_region_and_limit_is_bounded():
    photos = [
        photo("album.jpg", chapter_folder="01_Kyoto/hauptteil"),
        photo("food.jpg", chapter_folder="01_Kyoto/essen", is_candidate=True, final_score=80),
        photo("other-trip.jpg", chapter_folder="02_Osaka/hauptteil", is_candidate=True, final_score=99),
    ]
    assert comparison_candidates(photos, 0, {0}) == [1]
    assert comparison_candidates(photos, 0, {0}, limit=0) == []
    assert comparison_candidates(photos, -1, {0}) == []
    assert candidate_relation(photos, 0, 99)[0] == "other"


def test_nonfinite_scores_do_not_break_deterministic_ranking():
    photos = [
        photo("album.jpg", region="Kyoto"),
        photo("a.jpg", region="Kyoto", is_candidate=True, final_score=float("nan"), technical_score=75),
        photo("b.jpg", region="Kyoto", is_candidate=True, final_score=float("inf"), technical_score=70),
    ]
    assert comparison_candidates(photos, 0, {0}) == [1, 2]


def test_album_positions_win_then_unpositioned_photos_follow_time_and_path():
    base = datetime(2025, 4, 1, 10)
    photos = [
        photo("first-time.jpg", datetime_taken=base, book_position=3),
        photo("first-position.jpg", datetime_taken=base + timedelta(days=1), book_position=1),
        photo("b.jpg", datetime_taken=base),
        photo("a.jpg", datetime_taken=base),
        photo("unknown-date.jpg"),
    ]
    assert ordered_album_indices(photos, {4, 3, 2, 1, 0, 99}) == [1, 0, 3, 2, 4]


def test_album_order_accepts_mixed_timezone_metadata():
    photos = [
        photo("later.jpg", datetime_taken=datetime(2025, 4, 1, 10)),
        photo("earlier.jpg", datetime_taken=datetime(2025, 4, 1, 18, tzinfo=timezone(timedelta(hours=9)))),
    ]
    assert ordered_album_indices(photos, {0, 1}) == [1, 0]
