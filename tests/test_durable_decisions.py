"""Explicit keep/reject intent survives all supported project lifecycle paths."""
from pathlib import Path
import csv

import pytest

from photobook_curator.models import Photo, set_manual_decision
from photobook_curator.output import write_csv
from photobook_curator.review_export import load_photos_from_csv, rebuild_selection_from_analysis
from photobook_curator.review_history import ReviewHistory
from photobook_curator.selection_draft import (
    save_selection_draft, load_selection_draft, apply_selection_draft, restore_project_decisions,
)


def photos_at(root):
    return [Photo(path=root / f'{i}.jpg', filename=f'{i}.jpg', region='Holiday',
                  technical_score=80-i, final_score=80-i) for i in range(4)]


def test_decision_is_distinct_from_selection_and_favorite(tmp_path):
    photo = photos_at(tmp_path)[0]
    set_manual_decision(photo, 'keep', '  a special memory  ')
    assert photo.manual_decision == 'keep'
    assert photo.decision_reason == 'a special memory'
    assert not photo.is_selected and not photo.is_favorite
    with pytest.raises(ValueError):
        set_manual_decision(photo, 'sometimes')


def test_csv_and_draft_roundtrip_all_decisions_and_reasons(tmp_path):
    photos = photos_at(tmp_path)
    set_manual_decision(photos[0], 'keep', 'first stop')
    set_manual_decision(photos[1], 'reject', 'nearly identical')
    csv_path = tmp_path / 'photos_analysis.csv'
    write_csv(photos, csv_path)
    loaded = load_photos_from_csv(csv_path)
    assert [(p.manual_decision, p.decision_reason) for p in loaded] == [
        (p.manual_decision, p.decision_reason) for p in photos]
    save_selection_draft(tmp_path, photos, {0})
    fresh = photos_at(tmp_path)
    assert apply_selection_draft(fresh, load_selection_draft(tmp_path)) == {0}
    assert fresh[1].manual_decision == 'reject'
    assert fresh[1].decision_reason == 'nearly identical'


def test_draft_overrides_csv_and_explicit_auto_clears_legacy_flags(tmp_path):
    photos = photos_at(tmp_path)
    set_manual_decision(photos[0], 'keep', 'before')
    photos[0].flags = ['manual_add']
    photos[0].is_favorite = True
    write_csv(photos, tmp_path / 'photos_analysis.csv')
    set_manual_decision(photos[0], 'auto')
    photos[0].is_favorite = False
    set_manual_decision(photos[1], 'reject', 'blurred')
    save_selection_draft(tmp_path, photos, {2})
    fresh = photos_at(tmp_path)
    counts = restore_project_decisions(fresh, tmp_path)
    assert counts == {'favorites': 0, 'keep': 0, 'reject': 1}
    assert fresh[0].manual_decision == 'auto' and fresh[0].decision_reason == ''
    assert fresh[1].decision_reason == 'blurred'
    assert not any(p.is_selected for p in fresh)


def test_new_unexported_photo_draft_intent_survives_reanalysis(tmp_path):
    photos = photos_at(tmp_path)
    write_csv(photos[:1], tmp_path / 'photos_analysis.csv')
    set_manual_decision(photos[3], 'keep', 'new file')
    save_selection_draft(tmp_path, photos, {3})
    fresh = photos_at(tmp_path)
    assert restore_project_decisions(fresh, tmp_path)['keep'] == 1
    assert fresh[3].decision_reason == 'new file'


def test_same_filename_elsewhere_never_inherits_durable_intent(tmp_path):
    old = photos_at(tmp_path / 'old')
    set_manual_decision(old[0], 'reject', 'old source')
    save_selection_draft(tmp_path, old, {0})
    fresh = photos_at(tmp_path / 'new')
    restore_project_decisions(fresh, tmp_path)
    assert all(p.manual_decision == 'auto' for p in fresh)
    assert apply_selection_draft(fresh, load_selection_draft(tmp_path)) == set()
    assert all(p.manual_decision == 'auto' for p in fresh)
    assert not any(p.is_selected for p in fresh)


def test_legacy_csv_manual_flags_are_migrated_only_without_explicit_column(tmp_path):
    path = tmp_path / 'photos_analysis.csv'
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['filename', 'path', 'flags'])
        writer.writeheader()
        writer.writerow({'filename': 'old.jpg', 'path': str(tmp_path / 'old.jpg'), 'flags': 'manual_reject'})
    assert load_photos_from_csv(path)[0].manual_decision == 'reject'


def test_decision_and_reason_undo_redo(tmp_path):
    photos = photos_at(tmp_path)
    history = ReviewHistory(photos)
    set_manual_decision(photos[0], 'reject', 'out of focus')
    history.record(photos)
    history.undo(photos)
    assert photos[0].manual_decision == 'auto' and photos[0].decision_reason == ''
    history.redo(photos)
    assert photos[0].manual_decision == 'reject' and photos[0].decision_reason == 'out of focus'


def test_rebuild_honors_decisions_without_new_analysis(tmp_path, monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _: None)
    photos = photos_at(tmp_path)
    set_manual_decision(photos[0], 'reject', 'unwanted')
    set_manual_decision(photos[3], 'keep', 'memory')
    photos[3].is_duplicate = True  # explicit keep overrides automatic duplicate rejection
    _, order = rebuild_selection_from_analysis(photos, 2)
    assert 0 not in {i for i, _, _ in order}
    assert 3 in {i for i, _, _ in order}
    assert len(order) == 2


def test_manual_export_respects_forced_keep_reject_and_records_new_intent(tmp_path, monkeypatch):
    from photobook_curator.models import BookPlan
    from photobook_curator.review_export import apply_manual_selection

    photos = photos_at(tmp_path)
    set_manual_decision(photos[0], 'keep', 'protected memory')
    set_manual_decision(photos[1], 'reject', 'unwanted')
    photos[2].is_selected = True
    for function in ('write_csv', 'copy_selected', 'copy_aside_pool', 'write_markdown_overview'):
        monkeypatch.setattr('photobook_curator.review_export.' + function, lambda *_, **__: None)
    order = apply_manual_selection(photos, BookPlan(), [1, 3], tmp_path)
    assert {i for i, _, _ in order} == {0, 3}
    assert photos[2].manual_decision == 'reject'
    assert photos[3].manual_decision == 'keep'
