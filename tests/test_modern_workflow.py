"""Real project lifecycle checks for the modern review, independent of its widgets."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import time

from PIL import Image
import pytest

from photobook_curator.models import Photo
from photobook_curator.output import write_csv
from photobook_curator.review_export import load_photos_from_csv, plan_from_photos


def project_photos(directory: Path) -> list[Photo]:
    photos = []
    for index in range(8):
        # Two cameras reuse the same original basename; export must retain both.
        name = 'IMG_0001.JPG' if index in {0, 1, 3} else f'photo-{index}.jpg'
        path = directory / f'camera-{index}' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (480, 320), (20 + index * 23, 100, 190 - index * 12)).save(path)
        region = 'Tokyo' if index in {4, 6} else 'Kyoto'
        selected = index in {0, 1, 2, 6}
        photos.append(Photo(
            path, name, datetime_taken=datetime(2026, 5, 1, 10) + timedelta(minutes=index),
            region=region, chapter_folder=f'0{2 if region == "Tokyo" else 1}_{region}/hauptteil',
            chapter_type='Hauptteil', width=480, height=320,
            is_candidate=True, is_selected=selected, book_position={0: 1, 1: 2, 2: 3, 6: 4}.get(index),
            is_favorite=index == 6, manual_decision='reject' if index == 7 else 'auto',
            decision_reason='Unscharfe Erinnerung' if index == 7 else '',
            technical_score=95-index, final_score=95-index,
            burst_group_id=7 if index in {0, 3} else None,
            is_aside=index == 5,
        ))
    return photos


def new_session(photos, output):
    from photobook_curator.modern_review_session import ReviewSession
    return ReviewSession(photos, plan_from_photos(photos), output)


def wait_job(session, response, timeout=15):
    job = response['job']
    deadline = time.monotonic() + timeout
    while job['status'] in {'running', 'pending', 'queued'}:
        assert time.monotonic() < deadline, 'Modern export did not finish'
        time.sleep(.02)
        job = session.action({'action': 'job', 'job_id': job['id']})['job']
    assert job['status'] == 'done', job
    return job


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def test_real_selection_resume_and_both_exports_preserve_originals_and_slot(tmp_path):
    photos = project_photos(tmp_path / 'originals')
    output = tmp_path / 'project'
    output.mkdir()
    write_csv(photos, output / 'photos_analysis.csv')
    original_hashes = {str(photo.path): digest(photo.path) for photo in photos}
    session = new_session(photos, output)
    initial = session.snapshot()
    assert {photo['id'] for photo in initial['photos']} == set(range(8))
    assert set(initial['kept']) == {0, 1, 2, 6}
    chapter = next(photo['chapter'] for photo in initial['photos'] if photo['id'] == 0)

    scoped = session.action({'action': 'view', 'view': {'chapter': chapter, 'filter': 'alternatives'}})
    assert 3 in scoped['view']['alternative_ids']
    added = session.action({'action': 'toggle', 'id': 3, 'selected': True})
    assert 3 in added['view']['alternative_ids'], 'Adding must not make the focused alternative disappear'
    assert set(added['kept']) == {0, 1, 2, 3, 6}
    assert next(photo for photo in added['photos'] if photo['id'] == 3)['selected']
    assert set(session.action({'action': 'undo'})['kept']) == {0, 1, 2, 6}

    replaced = session.action({'action': 'replace', 'anchor': 0, 'id': 3})
    assert set(replaced['kept']) == {1, 2, 3, 6}
    assert next(photo for photo in replaced['photos'] if photo['id'] == 3)['position'] == 1
    session.action({'action': 'view', 'view': {
        'layout': 'B', 'chapter': chapter, 'filter': 'alternatives', 'focus': 3, 'anchor': 3,
        'theme': 'dark', 'export_layout': 'flat',
    }})
    session.save()
    session.close()

    # Reopen the on-disk analysis as the actual launcher does, then apply its draft.
    reopened = new_session(load_photos_from_csv(output / 'photos_analysis.csv'), output)
    state = reopened.snapshot()
    assert set(state['kept']) == {1, 2, 3, 6}
    assert {key: state['view'][key] for key in ('layout', 'chapter', 'filter', 'focus', 'anchor', 'theme', 'export_layout')} == {
        'layout': 'B', 'chapter': chapter, 'filter': 'alternatives', 'focus': 3, 'anchor': 3,
        'theme': 'dark', 'export_layout': 'flat',
    }
    assert next(photo for photo in state['photos'] if photo['id'] == 3)['position'] == 1
    assert next(photo for photo in state['photos'] if photo['id'] == 6)['favorite']
    assert next(photo for photo in state['photos'] if photo['id'] == 7)['manual_decision'] == 'reject'
    assert next(photo for photo in state['photos'] if photo['id'] == 7)['decision_reason'] == 'Unscharfe Erinnerung'

    expected = Counter(digest(reopened.image_photo(index).path) for index in state['kept'])
    for layout in ('flat', 'chapters'):
        wait_job(reopened, reopened.action({'action': 'export', 'export_layout': layout}))
        files = [path for path in (output / 'selected').rglob('*') if path.is_file()]
        assert len(files) == 4
        assert Counter(digest(path) for path in files) == expected
        if layout == 'flat':
            assert all(path.parent == output / 'selected' for path in files)
            assert digest(sorted(files)[0]) == digest(reopened.image_photo(3).path), 'Replacement must keep the first album slot'
            assert sum(path.name.endswith('IMG_0001.JPG') for path in files) == 2
        else:
            assert all(path.parent != output / 'selected' for path in files)
        assert next(photo for photo in reopened.snapshot()['photos'] if photo['id'] == 3)['position'] == 1
    assert (output / 'selection_audit.html').is_file()
    assert (output / 'selection_audit.csv').is_file()
    assert {str(photo.path): digest(photo.path) for photo in photos} == original_hashes
    reopened.close()


def test_protected_and_rejected_photos_cannot_be_changed_by_plain_toggle_or_replace(tmp_path):
    from photobook_curator.modern_review_session import SessionError
    session = new_session(project_photos(tmp_path / 'originals'), tmp_path / 'project')
    initial = set(session.snapshot()['kept'])
    for payload in ({'action': 'toggle', 'id': 6, 'selected': False},
                    {'action': 'replace', 'anchor': 6, 'id': 3},
                    {'action': 'toggle', 'id': 7, 'selected': True},
                    {'action': 'replace', 'anchor': 0, 'id': 7}):
        with pytest.raises(SessionError):
            session.action(payload)
        assert set(session.snapshot()['kept']) == initial
    session.action({'action': 'decision', 'id': 1, 'decision': 'keep', 'reason': 'Wichtige Erinnerung'})
    with pytest.raises(SessionError):
        session.action({'action': 'toggle', 'id': 1, 'selected': False})
    session.action({'action': 'decision', 'id': 1, 'decision': 'auto', 'reason': ''})
    assert 1 not in session.action({'action': 'toggle', 'id': 1, 'selected': False})['kept']
    session.close()


def test_save_failure_and_stale_revision_cannot_partially_change_selection(tmp_path, monkeypatch):
    import photobook_curator.modern_review_session as module
    session = new_session(project_photos(tmp_path / 'originals'), tmp_path / 'project')
    session.save()
    before = session.snapshot()
    draft = tmp_path / 'project' / 'selection_draft.json'
    saved = draft.read_bytes()
    original_save = module.save_selection_draft
    def fail(*args, **kwargs):
        raise OSError('simulated disk full')
    monkeypatch.setattr(module, 'save_selection_draft', fail)
    with pytest.raises(OSError):
        session.action({'action': 'toggle', 'id': 3, 'selected': True})
    after = session.snapshot()
    for key in ('kept', 'photos', 'revision', 'can_undo', 'can_redo'):
        assert after[key] == before[key]
    assert draft.read_bytes() == saved
    monkeypatch.setattr(module, 'save_selection_draft', original_save)
    session.action({'action': 'toggle', 'id': 3, 'selected': True, 'expected_revision': before['revision']})
    with pytest.raises(module.SessionError) as error:
        session.action({'action': 'toggle', 'id': 4, 'selected': True, 'expected_revision': before['revision']})
    assert error.value.status == 409
    assert 4 not in session.snapshot()['kept']
    session.close()


def test_two_thousand_photo_snapshot_is_metadata_only_and_contains_omitted_photos(tmp_path, monkeypatch):
    def no_pixels(*args, **kwargs):
        raise AssertionError('Snapshot decoded an image')
    monkeypatch.setattr(Image, 'open', no_pixels)
    photos = [Photo(tmp_path / 'originals' / f'{index}.jpg', f'{index}.jpg',
                    region='Kyoto', is_selected=index % 10 == 0, is_candidate=True,
                    book_position=index // 10 + 1 if index % 10 == 0 else None)
              for index in range(2000)]
    session = new_session(photos, tmp_path / 'project')
    state = session.snapshot()
    assert len(state['photos']) == 2000
    assert len(state['kept']) == 200
    assert sum(not photo['selected'] for photo in state['photos']) == 1800
    assert len(json.dumps(state, ensure_ascii=False).encode()) < 4 * 1024 * 1024
    assert all('selection_trace' not in photo for photo in state['photos'])
    session.close()


def test_location_repair_keeps_selection_and_persists_a_valid_new_chapter(tmp_path):
    photos = project_photos(tmp_path / 'originals')
    for photo in photos:
        photo.region = 'Hong Kong'
        photo.country = 'China'
        photo.chapter_folder = '01_Hong-Kong/hauptteil'
    photos[0].gps_lat, photos[0].gps_lon = 34.6851, 135.8048
    output = tmp_path / 'project'
    output.mkdir()
    write_csv(photos, output / 'photos_analysis.csv')
    session = new_session(photos, output)
    chapter = session.snapshot()['chapters'][0]['id']
    session.action({'action': 'view', 'view': {'chapter': chapter, 'focus': 1, 'layout': 'B'}})
    before = session.snapshot()
    audit = session.action({'action': 'audit', 'id': 1})['audit']
    assert audit['automatic_selected'] is None
    assert any('nicht aufgezeichnet' in text for text in audit['primary_reasons'])
    result = wait_job(session, session.action({'action': 'location_preview', 'online': False, 'max_hours': 6}))['result']
    after = session.action({'action': 'location_apply', 'preview_id': result['preview_id']})
    assert set(after['kept']) == set(before['kept'])
    assert after['view']['focus'] == 1 and after['view']['layout'] == 'B'
    assert after['view']['chapter'] == 'all' or after['view']['chapter'] in {item['id'] for item in after['chapters']}
    assert next(photo for photo in after['photos'] if photo['id'] == 1)['region'] == 'Nara'
    assert next(photo for photo in after['photos'] if photo['id'] == 6)['favorite']
    assert next(photo for photo in after['photos'] if photo['id'] == 7)['manual_decision'] == 'reject'
    # Verify the location transaction saved the new view already, not just a
    # later pause/close which could hide an invalid persisted chapter.
    reopened = new_session(load_photos_from_csv(output / 'photos_analysis.csv'), output)
    restored = reopened.snapshot()
    assert restored['view']['chapter'] == after['view']['chapter']
    assert restored['view']['focus'] == 1
    assert restored['kept'] == after['kept']
    reopened.close()
    session.close()
