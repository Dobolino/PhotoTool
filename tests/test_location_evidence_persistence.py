"""Location proof is persisted independently of automatic/legacy region labels."""
from copy import deepcopy
from pathlib import Path

import pytest

from photobook_curator.models import Photo
from photobook_curator.output import write_csv
from photobook_curator.review_export import load_photos_from_csv
from photobook_curator.selection_draft import save_selection_draft, load_selection_draft, apply_selection_draft
from photobook_curator.source_relink import preview_source_relink, apply_source_relink
from photobook_curator.location_schema import (
    MAX_LOCATION_EVIDENCE_BYTES, normalize_location_evidence, location_evidence_json,
)


def gps_evidence():
    return {'version': 1, 'source': 'gps_offline', 'assigned_at': '2026-11-07T12:00:00+00:00',
            'latitude': 35.0116, 'longitude': 135.7681}


def old_evidence(path):
    return {'version': 1, 'source': 'time_nearest', 'assigned_at': '2026-11-06T12:00:00+00:00',
            'anchor_path': str(path), 'anchor_region': 'Hong Kong', 'anchor_country': 'China',
            'delta_hours': 0.25, 'anchor_delta_hours': 0.25}


def test_csv_and_draft_roundtrip_location_evidence_without_inference(tmp_path):
    original = Photo(tmp_path / 'a.jpg', 'a.jpg', region='Kyoto', location_evidence=gps_evidence())
    write_csv([original], tmp_path / 'photos_analysis.csv')
    save_selection_draft(tmp_path, [original], {0})
    loaded = load_photos_from_csv(tmp_path / 'photos_analysis.csv')
    assert loaded[0].location_evidence == original.location_evidence
    fresh = Photo(original.path, original.filename)
    apply_selection_draft([fresh], load_selection_draft(tmp_path))
    assert fresh.region == 'Kyoto' and fresh.location_evidence == original.location_evidence
    legacy = tmp_path / 'old.csv'
    legacy.write_text('path,filename,region\na.jpg,a.jpg,Hong Kong\n')
    loaded_legacy = load_photos_from_csv(legacy)
    assert loaded_legacy[0].region == 'Hong Kong' and loaded_legacy[0].location_evidence == {}


def test_fresh_csv_location_wins_stale_selected_and_unselected_draft_geography(tmp_path):
    old = [Photo(tmp_path / f'{i}.jpg', f'{i}.jpg', region='Hong Kong', country='China',
                 place_label='Hong Kong', assigned_by_time=True,
                 chapter_folder='01_Hong-Kong/hauptteil', chapter_type='Hauptteil',
                 flags=['assigned_by_time', 'manual_reject'], location_evidence=old_evidence(tmp_path / 'anchor.jpg'))
           for i in range(2)]
    save_selection_draft(tmp_path, old, {0})
    current = [Photo(p.path, p.filename, region='Kyoto', country='Japan', place_label='Kyoto',
                     assigned_by_time=False, chapter_folder='02_Kyoto/hauptteil', chapter_type='Hauptteil',
                     location_evidence=gps_evidence()) for p in old]
    apply_selection_draft(current, load_selection_draft(tmp_path))
    for photo in current:
        assert photo.region == 'Kyoto' and photo.country == 'Japan' and photo.place_label == 'Kyoto'
        assert photo.chapter_folder == '02_Kyoto/hauptteil'
        assert not photo.assigned_by_time and 'assigned_by_time' not in photo.flags
        assert 'manual_reject' in photo.flags
        assert photo.location_evidence == gps_evidence()
    assert current[0].is_selected and not current[1].is_selected


def test_manual_chapter_marker_preserves_folder_but_cannot_relabel_gps_region(tmp_path):
    old = Photo(tmp_path / 'a.jpg', 'a.jpg', region='Hong Kong', country='China',
                chapter_folder='My-memories/essen', chapter_type='Essen', flags=['manual_chapter'],
                location_evidence=old_evidence(tmp_path / 'anchor.jpg'))
    save_selection_draft(tmp_path, [old], {0})
    current = Photo(old.path, old.filename, region='Kyoto', country='Japan',
                    chapter_folder='02_Kyoto/hauptteil', location_evidence=gps_evidence())
    apply_selection_draft([current], load_selection_draft(tmp_path))
    assert current.chapter_folder == 'My-memories/essen' and current.chapter_type == 'Essen'
    assert current.region == 'Kyoto' and current.country == 'Japan'
    assert current.location_evidence == gps_evidence()


def test_new_explicit_manual_location_can_override_earlier_gps_region(tmp_path):
    manual = Photo(tmp_path / 'a.jpg', 'a.jpg', region='User location', country='Custom',
                   location_evidence={'version': 1, 'source': 'manual',
                                      'assigned_at': '2026-11-08T12:00:00+00:00'})
    save_selection_draft(tmp_path, [manual], {0})
    current = Photo(manual.path, manual.filename, region='Kyoto', country='Japan', location_evidence=gps_evidence())
    apply_selection_draft([current], load_selection_draft(tmp_path))
    assert current.region == 'User location' and current.country == 'Custom'
    assert current.location_evidence['source'] == 'manual'


def test_legacy_draft_without_evidence_does_not_invent_proof_or_repair_region(tmp_path):
    photo = Photo(tmp_path / 'a.jpg', 'a.jpg', region='Hong Kong')
    save_selection_draft(tmp_path, [photo], {0})
    fresh = Photo(photo.path, photo.filename)
    apply_selection_draft([fresh], load_selection_draft(tmp_path))
    assert fresh.region == 'Hong Kong' and fresh.location_evidence == {}


@pytest.mark.parametrize('value', [None, 'broken', '[]', {'version': 1, 'source': 'AI guess'},
    {'version': 1, 'source': 'gps_online', 'latitude': float('nan')},
    {'version': 1, 'source': 'time_nearest', 'delta_hours': -1},
    {'version': 1, 'source': 'gps_online', 'assigned_at': 'not-a-time'},
    {'version': 1, 'source': 'gps_online', 'assigned_at': '2026-11-07T12:00:00'},
    {'version': 1, 'source': 'time_nearest', 'anchor_path': ['not a path']},
    {'version': 1, 'source': 'unknown', 'candidates': [1, 2, 3]},
    {'version': 1, 'source': 'unknown', 'confidence': 0.99}])
def test_malformed_location_evidence_stays_unknown(value):
    assert normalize_location_evidence(value) == {}
    assert location_evidence_json(value) == ''


def test_massive_location_json_never_reaches_parser(monkeypatch):
    import photobook_curator.location_schema as module
    monkeypatch.setattr(module.json, 'loads', lambda _: (_ for _ in ()).throw(AssertionError('parsed')))
    assert normalize_location_evidence('x' * (MAX_LOCATION_EVIDENCE_BYTES + 1)) == {}


def test_relink_updates_top_and_ambiguous_candidate_anchor_paths(tmp_path):
    old, new, output = tmp_path / 'old', tmp_path / 'new', tmp_path / 'output'
    photos = []
    for city in ('Tokyo', 'Kyoto'):
        target = new / city / 'IMG_0001.jpg'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'original')
        photos.append(Photo(old / city / target.name, target.name))
    evidence = {'version': 1, 'source': 'unknown', 'assigned_at': '2026-11-07T12:00:00Z',
                'anchor_path': str(photos[0].path), 'warning': 'conflicting_anchors',
                'candidates': [{'anchor_path': str(p.path), 'region': p.path.parent.name,
                                'country': 'Japan', 'delta_hours': 0.5} for p in photos]}
    photos[1].location_evidence = evidence
    before = deepcopy(evidence)
    write_csv(photos, output / 'photos_analysis.csv')
    save_selection_draft(output, photos, set())
    apply_source_relink(photos, preview_source_relink(photos, old, new), output)
    loaded = load_photos_from_csv(output / 'photos_analysis.csv')
    for photo in (photos[1], loaded[1]):
        assert photo.location_evidence['anchor_path'] == str(new / 'Tokyo' / 'IMG_0001.jpg')
        assert [entry['anchor_path'] for entry in photo.location_evidence['candidates']] == [str(p.path) for p in photos]
        assert photo.location_evidence['warning'] == before['warning']
        assert [entry['delta_hours'] for entry in photo.location_evidence['candidates']] == [0.5, 0.5]


@pytest.mark.parametrize('latitude,longitude', [
    (None, None), (35, None), (None, 135), (float('nan'), 135), (35, float('nan')),
    (float('inf'), 135), (35, float('-inf')), (91, 135), (-91, 135), (35, 181),
    (35, -181), (True, 135), (35, False), ('35', 135), (1 << 4096, 0),
])
def test_has_gps_rejects_invalid_or_partial_coordinates(latitude, longitude):
    assert not Photo(Path('a.jpg'), 'a.jpg', gps_lat=latitude, gps_lon=longitude).has_gps


@pytest.mark.parametrize('latitude,longitude', [(35.0116, 135.7681), (0, 0), (-90, -180), (90, 180)])
def test_has_gps_accepts_finite_in_range_coordinates(latitude, longitude):
    assert Photo(Path('a.jpg'), 'a.jpg', gps_lat=latitude, gps_lon=longitude).has_gps
