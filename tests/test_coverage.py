"""Tests für Tages-Abdeckung."""

from datetime import datetime, timedelta
from pathlib import Path

from photobook_curator.models import Photo
from photobook_curator.selection import allocate_day_quotas, _select_with_coverage


def test_allocate_even_vs_proportional():
    sizes = {datetime(2024, 6, 1).date(): 90, datetime(2024, 6, 2).date(): 10}
    prop = allocate_day_quotas(sizes, quota=10, intensity=0.0)
    assert prop[datetime(2024, 6, 1).date()] >= 8
    even = allocate_day_quotas(sizes, quota=10, intensity=1.0)
    # Stark gleichmäßig: beide Tage bekommen etwas, Tag1 nicht alles
    assert even[datetime(2024, 6, 2).date()] >= 2
    assert even[datetime(2024, 6, 1).date()] <= 7


def test_select_with_coverage_spreads_days():
    photos = []
    base = datetime(2024, 6, 1, 10, 0, 0)
    # 8 Fotos Tag 1, 2 Fotos Tag 2 – alle mit Score
    for i in range(10):
        day_offset = 0 if i < 8 else 1
        p = Photo(
            path=Path(f"{i}.jpg"),
            filename=f"{i}.jpg",
            datetime_taken=base + timedelta(days=day_offset, minutes=i),
            technical_score=90 - i,
            final_score=90 - i,
            is_candidate=True,
            scene_type="alltag",
        )
        photos.append(p)
    indices = list(range(10))
    # ohne Coverage: oft nur Tag 1
    no_cov = _select_with_coverage(
        photos, indices, quota=4, similarity_threshold=1.1, coverage_intensity=0.0
    )
    # mit starker Coverage: beide Tage vertreten
    with_cov = _select_with_coverage(
        photos, indices, quota=4, similarity_threshold=1.1, coverage_intensity=1.0
    )
    days_cov = {photos[i].datetime_taken.date() for i in with_cov}
    assert len(days_cov) >= 2
    assert len(with_cov) == 4
    assert len(no_cov) == 4
