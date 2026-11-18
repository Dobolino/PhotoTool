"""Tests für Personen-Balance."""

from pathlib import Path

from photobook_curator.models import Photo
from photobook_curator.people_balance import people_balance_penalty
from photobook_curator.selection import _select_diverse


def test_people_balance_penalty_zero_when_off():
    p = Photo(path=Path("a.jpg"), filename="a.jpg", person_cluster_ids=[1])
    assert people_balance_penalty(p, {1: 5}, intensity=0.0) == 0.0


def test_people_balance_penalty_penalizes_overrepresented():
    p = Photo(path=Path("a.jpg"), filename="a.jpg", person_cluster_ids=[1])
    over = people_balance_penalty(p, {1: 3}, intensity=1.0)
    fresh = people_balance_penalty(p, {}, intensity=1.0)
    assert over > fresh
    assert fresh < 0  # Bonus für neue Person


def test_select_diverse_balances_people():
    photos = []
    # Person 1 in vielen starken Fotos, Person 2 nur in etwas schwächeren
    for i in range(8):
        photos.append(
            Photo(
                path=Path(f"p1_{i}.jpg"),
                filename=f"p1_{i}.jpg",
                technical_score=95 - i,
                final_score=95 - i,
                is_candidate=True,
                scene_type="portrait",
                person_cluster_ids=[1],
            )
        )
    for i in range(4):
        photos.append(
            Photo(
                path=Path(f"p2_{i}.jpg"),
                filename=f"p2_{i}.jpg",
                technical_score=80 - i,
                final_score=80 - i,
                is_candidate=True,
                scene_type="portrait",
                person_cluster_ids=[2],
            )
        )
    indices = list(range(len(photos)))

    no_bal = _select_diverse(
        photos,
        indices,
        quota=6,
        similarity_threshold=1.1,
        people_balance_intensity=0.0,
    )
    with_bal = _select_diverse(
        photos,
        indices,
        quota=6,
        similarity_threshold=1.1,
        people_balance_intensity=1.0,
    )

    def person_set(sel):
        return {pid for i in sel for pid in photos[i].person_cluster_ids}

    # Ohne Balance: oft nur Person 1
    assert person_set(no_bal) == {1} or len(person_set(no_bal)) >= 1
    # Mit starker Balance: beide Personen
    assert person_set(with_bal) == {1, 2}
    assert len(with_bal) == 6
