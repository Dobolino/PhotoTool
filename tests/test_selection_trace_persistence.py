"""Recorded automatic provenance is durable, bounded and never invented."""
from copy import deepcopy
from pathlib import Path
import json

import pytest

from photobook_curator.models import Photo, set_manual_decision
from photobook_curator.output import write_csv
from photobook_curator.review_export import load_photos_from_csv
from photobook_curator.selection_draft import save_selection_draft, load_selection_draft, apply_selection_draft
from photobook_curator.source_relink import preview_source_relink, apply_source_relink
from photobook_curator.trace_schema import (
    MAX_TRACE_BYTES, latest_selection_trace, normalize_selection_trace, selection_trace_json,
)


def trace(run_id='recorded-run', *, time='2026-11-07T12:00:00+00:00', status='not_selected'):
    return {'version': 1, 'run_id': run_id, 'context': {'started_at': time, 'target_n': 80},
            'events': [{'code': 'candidate_rank_cutoff', 'stage': 'candidates',
                        'details': {'rank': 5, 'quota': 4, 'score': 71.5}}],
            'status': status, 'final_reason': 'candidate_rank_cutoff'}


def photo(path):
    return Photo(path=path, filename=path.name, selection_trace=trace())


def test_csv_and_manual_draft_preserve_last_automatic_trace(tmp_path):
    original = photo(tmp_path / 'a.jpg')
    # A subsequent manual keep must remain separate from the recorded rejection.
    set_manual_decision(original, 'keep', 'my memory')
    original.is_selected = True
    write_csv([original], tmp_path / 'photos_analysis.csv')
    save_selection_draft(tmp_path, [original], {0})
    loaded = load_photos_from_csv(tmp_path / 'photos_analysis.csv')
    assert loaded[0].selection_trace == original.selection_trace
    apply_selection_draft(loaded, load_selection_draft(tmp_path))
    assert loaded[0].manual_decision == 'keep' and loaded[0].is_selected
    assert loaded[0].selection_trace['status'] == 'not_selected'
    assert loaded[0].selection_trace['final_reason'] == 'candidate_rank_cutoff'
    assert json.loads(original.to_csv_row()['selection_trace']) == original.selection_trace


def test_old_csv_and_old_draft_stay_unknown_without_reconstructed_reasons(tmp_path):
    path = tmp_path / 'photos_analysis.csv'
    path.write_text('path,filename,is_selected,technical_score\na.jpg,a.jpg,True,99\n')
    loaded = load_photos_from_csv(path)
    assert loaded[0].selection_trace == {}
    apply_selection_draft(loaded, {'kept': [{'path': 'a.jpg', 'filename': 'a.jpg'}],
                                    'photo_states': [{'path': 'a.jpg', 'flags': ['manual_add']}]})
    assert loaded[0].selection_trace == {}
    assert loaded[0].to_csv_row()['selection_trace'] == ''


def test_older_draft_cannot_replace_new_automatic_csv_trace(tmp_path):
    old = photo(tmp_path / 'a.jpg')
    old.selection_trace = trace('old', time='2026-11-06T12:00:00+00:00')
    save_selection_draft(tmp_path, [old], {0})
    current = photo(old.path)
    current.selection_trace = trace('new', time='2026-11-07T12:00:00+00:00', status='selected')
    apply_selection_draft([current], load_selection_draft(tmp_path))
    assert current.selection_trace['run_id'] == 'new'


def test_newer_draft_trace_survives_unexported_automatic_rebuild(tmp_path):
    updated = photo(tmp_path / 'a.jpg')
    updated.selection_trace = trace('new', time='2026-11-07T12:00:00Z', status='selected')
    save_selection_draft(tmp_path, [updated], {0})
    loaded = photo(updated.path)
    loaded.selection_trace = trace('old', time='2026-11-06T12:00:00+00:00')
    apply_selection_draft([loaded], load_selection_draft(tmp_path))
    assert loaded.selection_trace['run_id'] == 'new'


def test_finished_trace_wins_over_checkpoint_of_same_run():
    pending, finished = trace(status='pending'), trace(status='selected')
    assert latest_selection_trace(pending, finished)['status'] == 'selected'
    assert latest_selection_trace(finished, pending)['status'] == 'selected'


@pytest.mark.parametrize('invalid', [None, '', 'not json', '[]', '{broken',
    {'version': 99}, {'version': True}, {'version': 1, 'run_id': 'missing fields'}])
def test_malformed_or_unsupported_legacy_trace_is_unknown(invalid):
    assert normalize_selection_trace(invalid) == {}


def test_invalid_details_nonfinite_and_oversized_structures_are_unknown():
    cases = []
    for key, value in [('number', float('nan')), ('text', 'x' * 4097),
                       ('items', list(range(65))), ('big', 1 << 256), ('value', object())]:
        invalid = trace()
        invalid['events'][0]['details'][key] = value
        cases.append(invalid)
    too_many = trace()
    too_many['events'] *= 25
    cases.append(too_many)
    cyclic = trace()
    cyclic['context']['cycle'] = cyclic['context']
    cases.append(cyclic)
    bad_peer = trace()
    bad_peer['events'][0]['details']['peer_path'] = ['a.jpg']
    cases.append(bad_peer)
    for invalid in cases:
        assert normalize_selection_trace(invalid) == {}
        assert selection_trace_json(invalid) == ''


def test_huge_json_is_rejected_before_parsing(monkeypatch):
    import photobook_curator.trace_schema as module

    def must_not_parse(_):
        raise AssertionError('oversized trace reached the JSON parser')

    monkeypatch.setattr(module.json, 'loads', must_not_parse)
    assert normalize_selection_trace('x' * (MAX_TRACE_BYTES + 1)) == {}


def test_normalization_returns_independent_structures_and_default_fields(tmp_path):
    value = trace()
    result = normalize_selection_trace(value)
    result['events'][0]['details']['rank'] = 99
    assert value['events'][0]['details']['rank'] == 5
    a, b = Photo(tmp_path / 'a', 'a'), Photo(tmp_path / 'b', 'b')
    a.selection_trace['changed'] = True
    assert b.selection_trace == {}


def test_source_relink_remaps_only_exact_comparison_references_in_all_traces(tmp_path):
    old, new, output = tmp_path / 'old', tmp_path / 'new', tmp_path / 'output'
    photos = []
    for region in ('Tokyo', 'Kyoto'):
        destination = new / region / 'IMG_0001.jpg'
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b'original')
        photos.append(photo(old / region / destination.name))
    external = tmp_path / 'other' / 'IMG_0001.jpg'
    external.parent.mkdir()
    external.write_bytes(b'other trip image with same camera filename')
    photos.append(photo(external))
    for current in photos:
        details = current.selection_trace['events'][0]['details']
        details['peer_path'] = str(photos[0].path)
        details['peer_paths'] = [str(photos[1].path), str(external)]
        details['message'] = 'Original comparison at ' + str(photos[0].path)
    original_reason = deepcopy(photos[2].selection_trace)
    write_csv(photos, output / 'photos_analysis.csv')
    save_selection_draft(output, photos, set())
    assert apply_source_relink(photos, preview_source_relink(photos, old, new), output) == 2
    loaded = load_photos_from_csv(output / 'photos_analysis.csv')
    for current in photos + loaded:
        details = current.selection_trace['events'][0]['details']
        assert details['peer_path'] == str(new / 'Tokyo' / 'IMG_0001.jpg')
        assert details['peer_paths'] == [str(new / 'Kyoto' / 'IMG_0001.jpg'), str(external)]
        assert details['message'] == original_reason['events'][0]['details']['message']
    fresh = [photo(p.path) for p in photos]
    for p in fresh:
        p.selection_trace = {}
    apply_selection_draft(fresh, load_selection_draft(output))
    assert fresh[2].selection_trace == photos[2].selection_trace


def test_actual_automatic_run_trace_roundtrips_without_losing_events(tmp_path, monkeypatch):
    from datetime import datetime, timedelta
    from photobook_curator.models import BookPlan, Region
    from photobook_curator.selection import mark_candidates, build_book_order

    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _: None)
    photos = [Photo(path=tmp_path / f'{i}.jpg', filename=f'{i}.jpg', region='Holiday',
                    technical_score=90-i, scene_type='alltag',
                    datetime_taken=datetime(2026, 8, 1) + timedelta(days=i // 4, minutes=i))
              for i in range(8)]
    plan = BookPlan(regions=[Region('Holiday', photo_indices=list(range(8)))])
    mark_candidates(photos, plan, target_n=4, candidate_factor=1)
    order = build_book_order(photos, plan, max_per_day=2)
    assert all(p.selection_trace and p.selection_trace['status'] != 'pending' for p in photos)
    write_csv(photos, tmp_path / 'photos_analysis.csv')
    save_selection_draft(tmp_path, photos, {i for i, _, _ in order})
    loaded = load_photos_from_csv(tmp_path / 'photos_analysis.csv')
    apply_selection_draft(loaded, load_selection_draft(tmp_path))
    assert [p.selection_trace for p in loaded] == [p.selection_trace for p in photos]


def test_manual_album_export_writes_metadata_reports_and_preserves_trace(tmp_path):
    from photobook_curator.models import BookPlan
    from photobook_curator.review_export import apply_manual_selection

    original = photo(tmp_path / 'a.jpg')
    original.path.write_bytes(b'original source bytes')
    before = deepcopy(original.selection_trace)
    output = tmp_path / 'output'
    order = apply_manual_selection([original], BookPlan(), [0], output)
    assert len(order) == 1
    assert (output / 'selection_audit.html').is_file()
    assert (output / 'selection_audit.csv').is_file()
    assert original.selection_trace == before
    assert list((output / 'selected').rglob('*.jpg'))[0].read_bytes() == b'original source bytes'


def test_report_only_export_failure_is_a_warning_after_album_success(tmp_path, monkeypatch):
    import photobook_curator.audit_report as module
    from photobook_curator.models import BookPlan
    from photobook_curator.review_export import apply_manual_selection

    original = photo(tmp_path / 'a.jpg')
    original.path.write_bytes(b'original source bytes')
    monkeypatch.setattr(module, 'write_audit_report',
                        lambda *_, **__: (_ for _ in ()).throw(OSError('report disk full')))
    messages = []
    output = tmp_path / 'output'
    order = apply_manual_selection([original], BookPlan(), [0], output, report_warning=messages.append)
    assert len(order) == 1 and 'report disk full' in messages[0]
    assert (output / 'photos_analysis.csv').is_file()
    assert list((output / 'selected').rglob('*.jpg'))[0].read_bytes() == b'original source bytes'
