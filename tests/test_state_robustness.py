"""Failure-path tests for durable project state and album exports."""
from pathlib import Path
import os

import pytest

from photobook_curator.models import Photo
from photobook_curator.output import copy_aside_pool, copy_selected, write_csv
from photobook_curator.selection_draft import (
    apply_selection_draft, load_selection_draft, save_selection_draft,
)


def photo(path: Path, **kwargs) -> Photo:
    return Photo(path=path, filename=path.name, **kwargs)


@pytest.mark.parametrize('kind', ['selected', 'optional_dokumente'])
def test_failed_copy_preserves_previous_export(tmp_path, kind, monkeypatch):
    out = tmp_path / 'out'
    previous = out / kind
    previous.mkdir(parents=True)
    (previous / 'previous.jpg').write_bytes(b'previous album')
    source = tmp_path / 'available.jpg'
    source.write_bytes(b'new image')
    photos = [photo(source, is_aside=True), photo(tmp_path / 'missing.jpg', is_aside=True)]
    monkeypatch.setattr('photobook_curator.output._prewarm_review_thumbs', lambda _: None)
    with pytest.raises(FileNotFoundError):
        if kind == 'selected':
            copy_selected(photos, [(0, 'Tokyo', 'Hauptteil'), (1, 'Tokyo', 'Hauptteil')], out)
        else:
            copy_aside_pool(photos, out)
    assert (previous / 'previous.jpg').read_bytes() == b'previous album'
    assert list(previous.iterdir()) == [previous / 'previous.jpg']
    assert not list(out.glob('.*-pending-*'))


def test_failed_publish_rolls_back_previous_export(tmp_path, monkeypatch):
    out = tmp_path / 'out'
    previous = out / 'selected'
    previous.mkdir(parents=True)
    (previous / 'previous.jpg').write_bytes(b'previous album')
    source = tmp_path / 'new.jpg'
    source.write_bytes(b'new image')
    replace = os.replace

    def fail_promotion(src, dst):
        if '-pending-' in str(src) and Path(dst) == previous:
            raise PermissionError('destination locked')
        return replace(src, dst)

    monkeypatch.setattr('photobook_curator.output.os.replace', fail_promotion)
    with pytest.raises(PermissionError, match='locked'):
        copy_selected([photo(source)], [(0, 'Tokyo', 'Hauptteil')], out)
    assert (previous / 'previous.jpg').read_bytes() == b'previous album'


def test_successful_export_replaces_previous_without_leftovers(tmp_path, monkeypatch):
    out = tmp_path / 'out'
    previous = out / 'selected'
    previous.mkdir(parents=True)
    (previous / 'stale.jpg').write_bytes(b'old')
    source = tmp_path / 'new.jpg'
    source.write_bytes(b'new image')
    monkeypatch.setattr('photobook_curator.output._prewarm_review_thumbs', lambda _: None)
    copy_selected([photo(source)], [(0, 'Tokyo', 'Hauptteil')], out)
    assert (previous / 'Tokyo' / '001_new.jpg').read_bytes() == b'new image'
    assert not (previous / 'stale.jpg').exists()
    assert not list(out.glob('.*'))


def test_failed_csv_write_preserves_analysis(tmp_path, monkeypatch):
    target = tmp_path / 'photos_analysis.csv'
    target.write_text('previous analysis', encoding='utf-8')
    bad_photo = photo(tmp_path / 'a.jpg')
    monkeypatch.setattr(bad_photo, 'to_csv_row', lambda: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError, match='disk full'):
        write_csv([bad_photo], target)
    assert target.read_text() == 'previous analysis'
    assert list(tmp_path.iterdir()) == [target]


def test_failed_draft_publish_preserves_project(tmp_path, monkeypatch):
    photos = [photo(tmp_path / 'a.jpg', is_favorite=True), photo(tmp_path / 'b.jpg')]
    save_selection_draft(tmp_path, photos, {0})
    original = (tmp_path / 'selection_draft.json').read_bytes()
    monkeypatch.setattr('photobook_curator.selection_draft.os.replace',
                        lambda *_: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError, match='disk full'):
        save_selection_draft(tmp_path, photos, {1})
    assert (tmp_path / 'selection_draft.json').read_bytes() == original
    assert load_selection_draft(tmp_path)['kept_count'] == 1
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.skipif(os.name == 'nt', reason='requires case-sensitive filesystem semantics')
def test_distinct_case_sensitive_paths_keep_the_correct_photo(tmp_path):
    photos = [photo(tmp_path / 'IMG.JPG'), photo(tmp_path / 'img.jpg')]
    save_selection_draft(tmp_path, photos, {0})
    fresh = [photo(p.path) for p in photos]
    assert apply_selection_draft(fresh, load_selection_draft(tmp_path)) == {0}


def test_windows_paths_accept_case_and_separator_changes():
    photos = [photo(Path('C:/Japan/IMG_1234.JPG'))]
    draft = {'kept': [{'path': 'c:\\japan\\img_1234.jpg', 'filename': 'different-name.jpg'}]}
    assert apply_selection_draft(photos, draft) == {0}


def test_invalid_optional_draft_fields_do_not_block_resume(tmp_path):
    photos = [photo(tmp_path / 'a.jpg', region='Tokyo')]
    draft = {'kept': [{'path': str(photos[0].path), 'chapter_folder': 3,
                        'chapter_type': [], 'region': {'broken': True}}]}
    assert apply_selection_draft(photos, draft) == {0}
    assert photos[0].region == 'Tokyo'
