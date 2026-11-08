"""Regression for repeated stopovers swallowing a trip's GPS-less photos."""
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from photobook_curator.geocoding import GeocodeCache
from photobook_curator.location_repair import apply_location_repair, preview_location_repair
from photobook_curator.models import Photo
from photobook_curator.regions import build_location_plan
from photobook_curator.scan import _dms_to_decimal


def photo(name, at, lat=None, lon=None, **kwargs):
    return Photo(Path(name), name, datetime_taken=at, gps_lat=lat, gps_lon=lon, **kwargs)


def test_repeated_hong_kong_stopover_does_not_swallow_japan(tmp_path):
    base = datetime(2025, 11, 1, 10)
    photos = [photo('arrival.jpg', base, 22.3193, 114.1694),
              photo('nara-gps.jpg', base + timedelta(days=7), 34.6851, 135.8048),
              photo('sony-nara.jpg', base + timedelta(days=7, hours=1)),
              photo('return.jpg', base + timedelta(days=14), 22.3193, 114.1694),
              photo('unanchored.jpg', base + timedelta(days=4))]
    plan = build_location_plan(photos, GeocodeCache(tmp_path / 'cache.json', enabled=False))
    assert photos[2].region == 'Nara'
    assert photos[2].location_evidence['source'] == 'time_nearest'
    assert photos[2].location_evidence['anchor_path'] == 'nara-gps.jpg'
    assert photos[2].location_evidence['delta_hours'] == 1
    assert photos[4].region == 'Unbestimmt'
    assert photos[4].location_evidence['warning'] == 'no_nearby_anchor'
    assert plan.unassigned_indices == [4]
    assert next(region for region in plan.regions if region.name == 'Hong Kong').day_count == 2


def test_reopened_city_counts_only_actual_photo_days():
    from photobook_curator.review_export import plan_from_photos
    base = datetime(2025, 11, 1, 10)
    photos = [photo('arrival.jpg', base, region='Hong Kong'),
              photo('another.jpg', base + timedelta(hours=1), region='Hong Kong'),
              photo('return.jpg', base + timedelta(days=14), region='Hong Kong')]
    plan = plan_from_photos(photos)
    assert plan.regions[0].day_count == 2


def test_inferred_photos_never_extend_time_anchor_chain(tmp_path):
    base = datetime(2025, 1, 1, 10)
    photos = [photo('gps.jpg', base, 34.6851, 135.8048),
              photo('5h.jpg', base + timedelta(hours=5)),
              photo('10h.jpg', base + timedelta(hours=10))]
    build_location_plan(photos, GeocodeCache(tmp_path / 'cache.json', enabled=False))
    assert photos[1].region == 'Nara'
    assert photos[2].region == 'Unbestimmt'


@pytest.mark.parametrize('same_time', [False, True])
def test_conflicting_nearby_cities_remain_unknown(tmp_path, same_time):
    base = datetime(2025, 1, 1, 10)
    photos = [photo('nara.jpg', base, 34.6851, 135.8048),
              photo('tokyo.jpg', base if same_time else base + timedelta(hours=2), 35.6762, 139.6503),
              photo('sony.jpg', base + timedelta(hours=1))]
    build_location_plan(photos, GeocodeCache(tmp_path / 'cache.json', enabled=False))
    assert photos[2].region == 'Unbestimmt'
    assert photos[2].location_evidence['warning'] == 'conflicting_anchors'
    assert {c['region'] for c in photos[2].location_evidence['candidates']} == {'Nara', 'Tokyo'}


def test_unresolved_actual_gps_not_overridden_by_time(tmp_path):
    base = datetime(2025, 1, 1, 10)
    photos = [photo('nara.jpg', base, 34.6851, 135.8048),
              photo('elsewhere.jpg', base + timedelta(minutes=1), 0.0, 0.0),
              photo('invalid.jpg', base, float('nan'), 135.0)]
    build_location_plan(photos, GeocodeCache(tmp_path / 'cache.json', enabled=False))
    assert photos[1].location_evidence['warning'] == 'gps_unresolved'
    assert photos[2].location_evidence['warning'] == 'invalid_gps'


def test_repair_preserves_all_decisions_and_manual_chapter(tmp_path):
    base = datetime(2025, 1, 1, 10)
    photos = [photo('gps.jpg', base, 34.6851, 135.8048, region='Hong Kong'),
              photo('sony.jpg', base + timedelta(hours=1), region='Hong Kong', is_selected=True,
                    book_position=7, manual_decision='keep', decision_reason='Erinnerung', is_favorite=True,
                    chapter_folder='02_Hong-Kong/hauptteil', chapter_type='Hauptteil'),
              photo('custom.jpg', base + timedelta(hours=2), region='Hong Kong', is_selected=True,
                    book_position=8, chapter_folder='Mein Kapitel/hauptteil', flags=['manual_chapter'])]
    original = deepcopy(photos)
    preview = preview_location_repair(photos, GeocodeCache(tmp_path / 'cache.json', enabled=False))
    assert photos == original  # preview is reversible, zero live mutations
    assert preview.photos[1].region == 'Nara'
    assert 'Nara' in preview.photos[1].chapter_folder
    assert preview.photos[2].chapter_folder == 'Mein Kapitel/hauptteil'
    # Preserve edits made to non-geographic data after the preview as well.
    photos[0].decision_reason = 'Nachträgliche Notiz'
    apply_location_repair(photos, preview)
    assert photos[0].decision_reason == 'Nachträgliche Notiz'
    assert photos[1].book_position == 7 and photos[1].is_selected
    assert photos[1].is_favorite and photos[1].manual_decision == 'keep'
    assert photos[1].decision_reason == 'Erinnerung'


def test_repair_rejects_changed_source_identity(tmp_path):
    photos = [photo('a.jpg', None)]
    preview = preview_location_repair(photos, GeocodeCache(tmp_path / 'cache.json', enabled=False))
    photos[0].path = Path('other.jpg')
    with pytest.raises(ValueError):
        apply_location_repair(photos, preview)


def test_cache_keeps_offline_approximation_out_of_online_results(tmp_path):
    path = tmp_path / 'cache.json'
    offline = GeocodeCache(path, enabled=False)
    assert offline.reverse(34.6851, 135.8048)['city'] == 'Nara'
    offline.save()
    online = GeocodeCache(path, enabled=True, min_interval_s=0)
    online._geocoder = MagicMock()
    online._geocoder.reverse.return_value = None
    assert online.reverse(34.6851, 135.8048)['city'] is None
    online._geocoder.reverse.assert_called_once()


@pytest.mark.parametrize('values,ref', [([90, 1, 0], 'N'), ([180, 0, 1], 'W'),
    ([1, 60, 0], 'N'), ([1, 0, 60], 'E'), ([float('nan'), 0, 0], 'S'),
    ([1, 2, 3], 'Q'), ([-1, 0, 0], 'N')])
def test_malformed_exif_gps_rejected(values, ref):
    assert _dms_to_decimal(values, ref) is None


@pytest.mark.parametrize('lat_ref,lon_ref', [('E', 'E'), ('N', 'S')])
def test_exif_coordinate_ref_must_match_its_axis(tmp_path, monkeypatch, lat_ref, lon_ref):
    from photobook_curator.scan import photo_from_path
    from types import SimpleNamespace
    image = tmp_path / 'malformed.jpg'
    image.write_bytes(b'')
    monkeypatch.setattr('photobook_curator.scan.exifread.process_file', lambda *a, **kw: {
        'GPS GPSLatitude': SimpleNamespace(values=[35, 0, 0]), 'GPS GPSLatitudeRef': lat_ref,
        'GPS GPSLongitude': SimpleNamespace(values=[139, 0, 0]), 'GPS GPSLongitudeRef': lon_ref})
    result = photo_from_path(image)
    assert not result.has_gps
    assert 'gps_invalid' in result.flags
