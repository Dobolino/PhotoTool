"""Source relocation verifies mappings and commits project metadata safely."""
from pathlib import Path

import pytest

from photobook_curator.models import Photo, set_manual_decision
from photobook_curator.output import write_csv
from photobook_curator.review_export import load_photos_from_csv
from photobook_curator.selection_draft import save_selection_draft, load_selection_draft, restore_project_decisions
from photobook_curator.source_relink import (
    apply_source_relink, preview_source_relink, missing_source_indices, recover_source_relink,
)


def project(tmp_path):
    old, new, output = tmp_path / 'old', tmp_path / 'moved', tmp_path / 'project'
    photos = []
    for city in ('Tokyo', 'Kyoto'):
        destination = new / city / 'IMG_0001.jpg'
        destination.parent.mkdir(parents=True)
        destination.write_bytes(f'original image {city}'.encode())
        photos.append(Photo(path=old / city / destination.name, filename=destination.name,
                            region=city, is_selected=True, technical_score=82))
    set_manual_decision(photos[0], 'keep', 'arrival')
    set_manual_decision(photos[1], 'reject', 'variant')
    photos[1].is_selected = False
    photos[0].is_favorite = True
    write_csv(photos, output / 'photos_analysis.csv')
    save_selection_draft(output, photos, {0}, review_state={
        'current_photo': str(photos[0].path), 'preview': [str(photos[1].path)], 'kind': 'album'})
    return photos, old, new, output


def test_relink_preserves_relative_paths_decisions_favorites_and_preview(tmp_path):
    photos, old, new, output = project(tmp_path)
    assert missing_source_indices(photos) == [0, 1]
    preview = preview_source_relink(photos, old, new)
    assert preview.can_apply and len(preview.changes) == 2
    assert apply_source_relink(photos, preview, output) == 2
    assert all(p.path.is_file() for p in photos)
    assert photos[0].path == new / 'Tokyo' / 'IMG_0001.jpg'
    assert photos[1].path == new / 'Kyoto' / 'IMG_0001.jpg'
    loaded = load_photos_from_csv(output / 'photos_analysis.csv')
    assert loaded[0].manual_decision == 'keep' and loaded[0].is_favorite
    assert loaded[0].technical_score == 82
    assert loaded[1].manual_decision == 'reject' and loaded[1].decision_reason == 'variant'
    draft = load_selection_draft(output)
    assert draft['review_state']['current_photo'] == str(photos[0].path)
    assert draft['review_state']['preview'] == [str(photos[1].path)]
    fresh = [Photo(path=p.path, filename=p.filename) for p in photos]
    assert restore_project_decisions(fresh, output) == {'favorites': 1, 'keep': 1, 'reject': 1}
    assert not list(output.glob('.source-relink-*'))


def test_missing_destination_blocks_entire_mapping_without_changes(tmp_path):
    photos, old, new, output = project(tmp_path)
    photos_before = [p.path for p in photos]
    (new / 'Kyoto' / 'IMG_0001.jpg').unlink()
    before = (output / 'photos_analysis.csv').read_bytes()
    preview = preview_source_relink(photos, old, new)
    assert not preview.can_apply
    with pytest.raises(ValueError):
        apply_source_relink(photos, preview, output)
    assert [p.path for p in photos] == photos_before
    assert (output / 'photos_analysis.csv').read_bytes() == before


def test_duplicate_target_is_ambiguous_even_when_existing_photo_not_remapped(tmp_path):
    photos, old, new, output = project(tmp_path)
    photos.append(Photo(path=new / 'Tokyo' / 'IMG_0001.jpg', filename='IMG_0001.jpg'))
    preview = preview_source_relink(photos, old, new)
    assert not preview.can_apply
    assert preview.entries[0].status == 'ambiguous'


def test_revalidate_target_removed_after_preview(tmp_path):
    photos, old, new, output = project(tmp_path)
    preview = preview_source_relink(photos, old, new)
    (new / 'Tokyo' / 'IMG_0001.jpg').unlink()
    with pytest.raises(ValueError, match='Vorschau'):
        apply_source_relink(photos, preview, output)


def test_relink_supports_windows_paths_from_another_computer(tmp_path):
    new = tmp_path / 'new'
    (new / 'Kyoto').mkdir(parents=True)
    (new / 'Kyoto' / 'a.jpg').write_bytes(b'image')
    photos = [Photo(path=Path('D:\\Holidays\\Kyoto\\a.jpg'), filename='a.jpg')]
    preview = preview_source_relink(photos, 'd:\\holidays', new)
    assert preview.can_apply
    assert preview.changes[0].new_path == new / 'Kyoto' / 'a.jpg'


def test_failed_second_metadata_replace_rolls_back_both_and_live_paths(tmp_path, monkeypatch):
    import photobook_curator.source_relink as module
    photos, old, new, output = project(tmp_path)
    before = {name: (output / name).read_bytes() for name in ('photos_analysis.csv', 'selection_draft.json')}
    before_paths = [p.path for p in photos]
    preview = preview_source_relink(photos, old, new)
    real_replace = module.os.replace

    def fail_second(source, destination):
        if Path(source).name == 'selection_draft.json' and Path(destination).parent == output:
            raise OSError('disk full')
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, 'replace', fail_second)
    with pytest.raises(OSError, match='disk full'):
        apply_source_relink(photos, preview, output)
    assert [p.path for p in photos] == before_paths
    assert {name: (output / name).read_bytes() for name in before} == before
    assert not list(output.glob('.source-relink-*'))


def test_hard_interruption_recovers_before_next_csv_or_draft_read(tmp_path, monkeypatch):
    import photobook_curator.source_relink as module
    photos, old, new, output = project(tmp_path)
    before = {name: (output / name).read_bytes() for name in ('photos_analysis.csv', 'selection_draft.json')}
    preview = preview_source_relink(photos, old, new)
    real_replace = module.os.replace

    class HardInterruption(BaseException):
        pass

    def crash_second(source, destination):
        if Path(source).name == 'selection_draft.json' and Path(destination).parent == output:
            raise HardInterruption()
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, 'replace', crash_second)
    with pytest.raises(HardInterruption):
        apply_source_relink(photos, preview, output)
    assert (output / '.source-relink-transaction.json').exists()
    loaded = load_photos_from_csv(output / 'photos_analysis.csv')
    assert loaded[0].path == old / 'Tokyo' / 'IMG_0001.jpg'
    assert {name: (output / name).read_bytes() for name in before} == before
    assert not list(output.glob('.source-relink-*'))


def test_unrecognized_journal_is_not_allowed_to_modify_files(tmp_path):
    (tmp_path / '.source-relink-transaction.json').write_text('{"staging":"../outside"}')
    with pytest.raises(RuntimeError, match='Ungültiges'):
        recover_source_relink(tmp_path)


def test_sources_outside_mapping_are_reported_and_can_be_linked_separately(tmp_path):
    photos, old, new, output = project(tmp_path)
    photos.append(Photo(path=tmp_path / 'other-trip' / 'c.jpg', filename='c.jpg'))
    preview = preview_source_relink(photos, old, new)
    assert preview.can_apply and preview.entries[-1].status == 'outside_root'
    apply_source_relink(photos, preview, output)
    assert missing_source_indices(photos) == [2]


def write_project_metadata(output, old):
    import json
    metadata = {'kind': 'phototool_project', 'version': 1, 'name': 'My holiday',
                'input_dir': str(old), 'output_dir': '.', 'profile_id': 'balanced',
                'settings': {'target_n': 120, 'food_ratio': .12},
                'created_at': '2026-01-01T12:00:00+00:00', 'updated_at': '2026-01-01T12:00:00+00:00'}
    (output / 'phototool_project.json').write_text(json.dumps(metadata), encoding='utf-8')
    return metadata


def test_relink_updates_existing_project_source_and_preserves_settings(tmp_path):
    import json
    photos, old, new, output = project(tmp_path)
    metadata = write_project_metadata(output, old)
    apply_source_relink(photos, preview_source_relink(photos, old, new), output)
    updated = json.loads((output / 'phototool_project.json').read_text())
    assert updated['input_dir'] == str(new)
    assert updated['updated_at'] != metadata['updated_at']
    for key in ('name', 'profile_id', 'settings', 'created_at', 'output_dir'):
        assert updated[key] == metadata[key]


def test_failed_project_replace_rolls_back_all_three_files(tmp_path, monkeypatch):
    import photobook_curator.source_relink as module
    photos, old, new, output = project(tmp_path)
    write_project_metadata(output, old)
    names = ('photos_analysis.csv', 'selection_draft.json', 'phototool_project.json')
    before = {name: (output / name).read_bytes() for name in names}
    preview = preview_source_relink(photos, old, new)
    real_replace = module.os.replace

    def fail_last(source, destination):
        if Path(source).name == 'phototool_project.json' and Path(destination).parent == output:
            raise OSError('project locked')
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, 'replace', fail_last)
    with pytest.raises(OSError, match='project locked'):
        apply_source_relink(photos, preview, output)
    assert {name: (output / name).read_bytes() for name in names} == before
    assert photos[0].path == old / 'Tokyo' / 'IMG_0001.jpg'


def test_project_without_covered_source_root_is_left_unchanged(tmp_path):
    photos, old, new, output = project(tmp_path)
    write_project_metadata(output, tmp_path / 'another-source')
    before = (output / 'phototool_project.json').read_bytes()
    apply_source_relink(photos, preview_source_relink(photos, old, new), output)
    assert (output / 'phototool_project.json').read_bytes() == before


def test_relink_does_not_create_project_metadata_for_legacy_output(tmp_path):
    photos, old, new, output = project(tmp_path)
    apply_source_relink(photos, preview_source_relink(photos, old, new), output)
    assert not (output / 'phototool_project.json').exists()


def test_project_scan_root_never_changes_to_incomplete_partial_copy(tmp_path):
    photos, old, new, output = project(tmp_path)
    available = old / 'Tokyo' / 'still-here.jpg'
    available.parent.mkdir(parents=True)
    available.write_bytes(b'original not moved yet')
    photos.append(Photo(path=available, filename=available.name))
    write_project_metadata(output, old)
    preview = preview_source_relink(photos, old, new, output_dir=output)
    assert not preview.can_apply  # the root-aware preview exposes the uncopied original
    assert preview.entries[-1].status == 'missing'
    before = (output / 'phototool_project.json').read_bytes()
    with pytest.raises(ValueError, match='Vorschau'):
        apply_source_relink(photos, preview, output)
    assert (output / 'phototool_project.json').read_bytes() == before
    assert photos[0].path == old / 'Tokyo' / 'IMG_0001.jpg'


def test_opening_project_recovers_interrupted_three_file_relink(tmp_path, monkeypatch):
    import photobook_curator.source_relink as module
    from photobook_curator.projects import load_project

    photos, old, new, output = project(tmp_path)
    write_project_metadata(output, old)
    before_csv = (output / 'photos_analysis.csv').read_bytes()
    real_replace = module.os.replace

    class HardInterruption(BaseException):
        pass

    def crash_last(source, destination):
        if Path(source).name == 'phototool_project.json' and Path(destination).parent == output:
            raise HardInterruption()
        return real_replace(source, destination)

    monkeypatch.setattr(module.os, 'replace', crash_last)
    with pytest.raises(HardInterruption):
        apply_source_relink(photos, preview_source_relink(photos, old, new), output)
    loaded = load_project(output, remember=False)
    assert loaded.input_dir == old
    assert (output / 'photos_analysis.csv').read_bytes() == before_csv
    assert not list(output.glob('.source-relink-*'))


def test_missing_only_project_move_also_maps_available_protected_original(tmp_path):
    from photobook_curator.projects import load_project
    from photobook_curator.scan import scan_photos

    photos, old, new, output = project(tmp_path)
    # Photo A still exists at its old location, while B is already missing.
    # Both have copies under new. A carries favorite+keep; B carries reject.
    photos[0].path.parent.mkdir(parents=True)
    photos[0].path.write_bytes(b'available original A')
    write_project_metadata(output, old)
    preview = preview_source_relink(photos, old, new, missing_only=True, output_dir=output)
    assert preview.can_apply
    assert preview.expanded_indices == (0,)
    assert preview.entries[0].message  # the preview explicitly reveals the enlarged scope
    assert {entry.index for entry in preview.changes} == {0, 1}
    assert apply_source_relink(photos, preview, output) == 2
    project_metadata = load_project(output, remember=False)
    assert project_metadata.input_dir == new
    loaded = load_photos_from_csv(output / 'photos_analysis.csv')
    assert all(p.path.is_relative_to(new) for p in loaded)
    assert load_selection_draft(output)['favorites'] == [str(new / 'Tokyo' / 'IMG_0001.jpg')]
    fresh = scan_photos(project_metadata.input_dir)
    assert restore_project_decisions(fresh, output) == {'favorites': 1, 'keep': 1, 'reject': 1}
    protected = next(p for p in fresh if p.path.parent.name == 'Tokyo')
    rejected = next(p for p in fresh if p.path.parent.name == 'Kyoto')
    assert protected.is_favorite and protected.manual_decision == 'keep'
    assert protected.decision_reason == 'arrival'
    assert rejected.manual_decision == 'reject' and rejected.decision_reason == 'variant'


def test_unexpanded_preview_cannot_silently_move_project_root(tmp_path):
    photos, old, new, output = project(tmp_path)
    photos[0].path.parent.mkdir(parents=True)
    photos[0].path.write_bytes(b'available original A')
    write_project_metadata(output, old)
    preview = preview_source_relink(photos, old, new, missing_only=True)
    assert {entry.index for entry in preview.changes} == {1}
    before = {name: (output / name).read_bytes() for name in (
        'photos_analysis.csv', 'selection_draft.json', 'phototool_project.json')}
    with pytest.raises(ValueError, match='Vorschau'):
        apply_source_relink(photos, preview, output)
    assert {name: (output / name).read_bytes() for name in before} == before
    assert all(p.path.is_relative_to(old) for p in photos)
