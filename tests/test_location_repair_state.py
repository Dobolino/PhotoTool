"""Metadata-only location corrections commit CSV/draft as one recoverable unit."""
from dataclasses import replace
from pathlib import Path

import pytest

from photobook_curator.models import Photo
from photobook_curator.output import write_csv
from photobook_curator.selection_draft import load_selection_draft, save_selection_draft
from photobook_curator.review_export import load_photos_from_csv
from photobook_curator.location_repair_state import persist_location_repair


def project(tmp_path):
    photos = [Photo(tmp_path / f'{i}.jpg', f'{i}.jpg', region='Hong Kong',
                    is_selected=i == 0, book_position=1 if i == 0 else None,
                    is_favorite=i == 0, manual_decision='keep' if i == 0 else 'reject',
                    decision_reason=f'memory {i}', chapter_folder='Manual/chapter', flags=['manual_chapter'])
              for i in range(2)]
    output = tmp_path / 'project'
    write_csv(photos, output / 'photos_analysis.csv')
    save_selection_draft(output, photos, {0}, review_state={'current_photo': str(photos[0].path)})
    corrected = [replace(photo, region='Kyoto', country='Japan', location_evidence={
        'version': 1, 'source': 'gps_offline', 'assigned_at': '2026-11-07T12:00:00Z',
        'latitude': 35.0116, 'longitude': 135.7681}) for photo in photos]
    return photos, corrected, output


def test_repair_changes_only_metadata_and_preserves_user_selection_state(tmp_path):
    original, corrected, output = project(tmp_path)
    selected = output / 'selected'
    selected.mkdir()
    album_file = selected / 'already_exported.jpg'
    album_file.write_bytes(b'exported album remains untouched')
    persist_location_repair(corrected, {0}, output)
    loaded = load_photos_from_csv(output / 'photos_analysis.csv')
    assert [p.region for p in loaded] == ['Kyoto', 'Kyoto']
    assert [p.region for p in original] == ['Hong Kong', 'Hong Kong']
    for before, after in zip(original, loaded):
        assert (after.is_favorite, after.manual_decision, after.decision_reason, after.book_position,
                after.flags, after.chapter_folder) == (
                    before.is_favorite, before.manual_decision, before.decision_reason, before.book_position,
                    before.flags, before.chapter_folder)
    draft = load_selection_draft(output)
    assert draft['review_state'] == {'current_photo': str(original[0].path)}
    assert draft['kept_count'] == 1
    assert draft['photo_states'][0]['location_evidence']['source'] == 'gps_offline'
    assert album_file.read_bytes() == b'exported album remains untouched'
    assert not list(output.glob('.source-relink-*'))


def test_repair_can_save_current_unsaved_review_view(tmp_path):
    _original, corrected, output = project(tmp_path)
    view = {'current_photo': str(corrected[1].path), 'expanded': ['Manual/chapter']}
    persist_location_repair(corrected, {0}, output, review_state=view)
    assert load_selection_draft(output)['review_state'] == view


def test_failed_repair_rolls_back_both_metadata_files(tmp_path, monkeypatch):
    import photobook_curator.location_repair_state as module
    original, corrected, output = project(tmp_path)
    before = {name: (output / name).read_bytes() for name in ('photos_analysis.csv', 'selection_draft.json')}
    real_replace = module.os.replace

    def fail_second(source, destination):
        if Path(source).name == 'selection_draft.json' and Path(destination).parent == output:
            raise OSError('disk full')
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, 'replace', fail_second)
    with pytest.raises(OSError, match='disk full'):
        persist_location_repair(corrected, {0}, output)
    assert {name: (output / name).read_bytes() for name in before} == before
    assert all(p.region == 'Hong Kong' for p in original)


def test_hard_interruption_repair_recovers_on_next_metadata_read(tmp_path, monkeypatch):
    import photobook_curator.location_repair_state as module
    _original, corrected, output = project(tmp_path)
    real_replace = module.os.replace

    class HardInterruption(BaseException):
        pass

    def crash_second(source, destination):
        if Path(source).name == 'selection_draft.json' and Path(destination).parent == output:
            raise HardInterruption()
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, 'replace', crash_second)
    with pytest.raises(HardInterruption):
        persist_location_repair(corrected, {0}, output)
    assert (output / '.source-relink-transaction.json').exists()
    assert load_photos_from_csv(output / 'photos_analysis.csv')[0].region == 'Hong Kong'
    assert not list(output.glob('.source-relink-*'))
