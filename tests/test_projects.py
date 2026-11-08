"""Travel projects persist config without duplicating selections or credentials."""
from dataclasses import dataclass
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from photobook_curator.projects import (
    PROJECT_FILENAME, TravelProject, config_kwargs, create_project, forget_project,
    load_project, project_from_config, recent_projects, remember_project, save_project,
)
from photobook_curator.travel_profiles import get_profile, profile_choices


@pytest.fixture
def locations(tmp_path):
    source = tmp_path / 'Originale'
    source.mkdir()
    return source, tmp_path / 'Meine Reise'


def test_create_reopen_preserves_profile_config_and_selection_draft(locations):
    source, output = locations
    project = create_project('Island 2026', source, output, profile_id='roadtrip', remember=False)
    draft = output / 'selection_draft.json'
    draft.write_text('{"kept": ["favourite.jpg"]}')
    project.settings.update(target_n=230, page_count=80, photos_per_page=2.5)
    save_project(project, remember=False)
    loaded = load_project(output, remember=False)
    assert loaded.name == 'Island 2026'
    assert loaded.profile_id == 'roadtrip'
    assert loaded.settings['target_n'] == 230
    assert loaded.settings['max_transit_quota'] == 8
    assert loaded.settings['page_count'] == 80
    assert loaded.settings['photos_per_page'] == 2.5
    assert json.loads(draft.read_text()) == {'kept': ['favourite.jpg']}
    assert loaded.input_dir == source.resolve()


def test_credentials_never_saved_from_settings(locations):
    source, output = locations
    project = create_project('Reise', source, output, profile_id='custom', settings={
        'target_n': 160, 'ANTHROPIC_API_KEY': 'sensitive',
        'gemini_token': 'sensitive', 'password': 'sensitive',
    }, remember=False)
    text = project.path.read_text()
    assert 'sensitive' not in text
    assert project.settings['target_n'] == 160
    assert not any('key' in key.lower() or 'token' in key.lower() or 'password' in key.lower()
                   for key in project.settings)


def test_profiles_are_copied_not_shared_or_destination_specific():
    city = get_profile('city')
    city.settings['target_n'] = 9999
    assert get_profile('city').settings['target_n'] == 180
    assert {pid for pid, _ in profile_choices()} == {'balanced', 'city', 'beach', 'roadtrip', 'custom'}
    assert get_profile('city').settings['enable_weak_night_filter'] is False
    assert get_profile('beach').settings['burst_keep'] == 1
    with pytest.raises(ValueError):
        get_profile('missing')


def test_existing_project_never_silently_overwritten(locations):
    source, output = locations
    original = create_project('Erste Reise', source, output, remember=False)
    previous = original.path.read_bytes()
    with pytest.raises(FileExistsError):
        create_project('Andere Reise', source, output, remember=False)
    assert original.path.read_bytes() == previous


def test_failed_atomic_save_leaves_previous_project(locations):
    source, output = locations
    project = create_project('Reise', source, output, remember=False)
    original = project.path.read_bytes()
    project.name = 'Andere Bezeichnung'
    with patch('photobook_curator.projects.os.replace', side_effect=OSError('disk full')):
        with pytest.raises(OSError):
            save_project(project, remember=False)
    assert project.path.read_bytes() == original
    assert not list(output.glob('*.tmp'))


def test_moved_output_uses_current_project_location(locations, tmp_path):
    source, output = locations
    create_project('Reise', source, output, remember=False)
    moved = tmp_path / 'Archiv' / 'Reise'
    moved.parent.mkdir()
    output.rename(moved)
    loaded = load_project(moved / PROJECT_FILENAME, remember=False)
    assert loaded.output_dir == moved.resolve()
    assert loaded.input_dir == source.resolve()


def test_recent_catalog_deduplicates_and_removal_never_deletes_project(locations, tmp_path):
    source, output = locations
    first = create_project('Reise A', source, output, remember=False)
    second = create_project('Reise B', source, tmp_path / 'Reise B', remember=False)
    catalog = tmp_path / 'config' / 'recent.json'
    remember_project(first, catalog_path=catalog)
    remember_project(second, catalog_path=catalog)
    remember_project(first, catalog_path=catalog)
    records = recent_projects(catalog_path=catalog)
    assert [record['name'] for record in records] == ['Reise A', 'Reise B']
    assert all(record['exists'] for record in records)
    forget_project(first.path, catalog_path=catalog)
    assert first.path.exists()
    assert [r['name'] for r in recent_projects(catalog_path=catalog)] == ['Reise B']
    assert recent_projects(0, catalog_path=catalog) == []
    second.path.unlink()
    assert recent_projects(catalog_path=catalog)[0]['exists'] is False


def test_unknown_project_version_and_invalid_settings_are_rejected(locations):
    source, output = locations
    p = create_project('Reise', source, output, remember=False)
    data = json.loads(p.path.read_text())
    data['version'] = 999
    p.path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match='Projektversion'):
        load_project(p.path, remember=False)
    p.settings['broken'] = float('nan')
    with pytest.raises(ValueError, match='broken'):
        save_project(p, remember=False)


def test_invalid_source_and_ancestor_destination_are_rejected(tmp_path):
    with pytest.raises(ValueError, match='Originalordner'):
        create_project('Reise', tmp_path / 'missing', tmp_path / 'out', remember=False)
    source = tmp_path / 'originals'
    source.mkdir()
    with pytest.raises(ValueError, match='umfassen'):
        create_project('Reise', source, tmp_path, remember=False)


def test_config_roundtrip_and_unknown_future_keys_are_filtered(locations):
    @dataclass
    class Config:
        input_dir: Path
        output_dir: Path
        target_n: int = 200
        page_count: int = 80
        images_per_page: float = 2.5
        ai_model: str | None = None

    source, output = locations
    cfg = Config(source, output)
    project = project_from_config(cfg, name='Reise 1', profile_id='city')
    save_project(project, remember=False)
    project = load_project(output, remember=False)
    project.settings['future_option'] = 42
    assert config_kwargs(project, Config) == {
        'input_dir': source.resolve(), 'output_dir': output.resolve(), 'target_n': 200,
        'page_count': 80, 'images_per_page': 2.5, 'ai_model': None,
    }
    updated = project_from_config(Config(source, output, target_n=240))
    assert updated.name == 'Reise 1'
    assert updated.profile_id == 'city'
    assert updated.settings['target_n'] == 240


def test_malformed_recent_entry_does_not_break_launcher(tmp_path):
    catalog = tmp_path / 'recent.json'
    catalog.write_text(json.dumps({'projects': [{'path': '\u0000'}, None, {'path': str(tmp_path / 'ok.json')}]}))
    result = recent_projects(catalog_path=catalog)
    assert len(result) == 1
    assert result[0]['exists'] is False


def test_sparse_project_materializes_defaults_instead_of_leaking_previous_trip(locations):
    source, output = locations
    project = create_project('Neue Reise', source, output, profile_id='city', remember=False)
    assert project.settings['book_pages'] == 0
    assert project.settings['ai_provider'] == 'none'
    assert project.settings['enable_faces'] is True
    # A sparse old project can be opened after a pages/API-heavy trip safely.
    data = json.loads(project.path.read_text())
    data['settings'] = {'target_n': 123}
    project.path.write_text(json.dumps(data))
    loaded = load_project(project.path, remember=False)
    assert loaded.settings['target_n'] == 123
    assert loaded.settings['book_pages'] == 0
    assert loaded.settings['ai_provider'] == 'none'


def test_load_recovers_interrupted_source_relink_before_project_read(locations):
    source, output = locations
    project = create_project('Reise', source, output, remember=False)
    with patch('photobook_curator.source_relink.recover_source_relink') as recover:
        load_project(project.path, remember=False)
    recover.assert_called_once_with(output.resolve())


@pytest.mark.skipif(__import__('os').name == 'nt', reason='Foreign Windows path handling on a non-Windows host')
def test_windows_source_identity_preserved_for_relink_on_another_platform(locations):
    source, output = locations
    project = create_project('Reise', source, output, remember=False)
    data = json.loads(project.path.read_text())
    data['input_dir'] = r'D:\Fotos\Island'
    data['profile_id'] = 'future-profile'
    project.path.write_text(json.dumps(data))
    loaded = load_project(project.path, remember=False)
    assert str(loaded.input_dir) == r'D:\Fotos\Island'
    assert loaded.profile_id == 'custom'


def test_trip_budget_and_durable_decisions_survive_relink_and_stay_per_project(tmp_path):
    from datetime import datetime
    from PIL import Image
    from photobook_curator.models import Photo
    from photobook_curator.output import write_csv
    from photobook_curator.review_export import load_photos_from_csv, rebuild_selection_from_analysis
    from photobook_curator.selection_draft import restore_project_decisions, save_selection_draft
    from photobook_curator.source_relink import preview_source_relink, apply_source_relink
    from photobook_curator.story_budget import calculate_book_budget

    source, output = tmp_path / 'Originale', tmp_path / 'Reise A'
    source.mkdir()
    photos = []
    for i, decision in enumerate(('keep', 'reject')):
        path = source / f'{i}.jpg'
        Image.new('RGB', (80, 60), (60, 100, 150)).save(path)
        photos.append(Photo(path=path, filename=path.name, datetime_taken=datetime(2026, 4, 1),
                            technical_score=85, scene_type='alltag', region='Album',
                            manual_decision=decision, decision_reason='Meine Entscheidung',
                            is_selected=decision == 'keep'))
    project = create_project('Reise A', source, output, settings={
        'book_pages': 20, 'photos_per_page': 2.0, 'reserved_pages': 4,
    }, remember=False)
    write_csv(photos, output / 'photos_analysis.csv')
    save_selection_draft(output, photos, {0})
    relocated = tmp_path / 'Externe Platte' / 'Originale'
    relocated.parent.mkdir()
    source.rename(relocated)
    preview = preview_source_relink(photos, source, relocated)
    assert preview.can_apply
    assert apply_source_relink(photos, preview, output) == 2
    loaded = load_project(output, remember=False)
    assert loaded.input_dir == relocated
    assert loaded.settings['book_pages'] == 20
    budget = calculate_book_budget(loaded.settings['book_pages'],
                                   loaded.settings['photos_per_page'],
                                   loaded.settings['reserved_pages'])
    assert budget.target_count == 32
    restored = load_photos_from_csv(output / 'photos_analysis.csv')
    _plan, order = rebuild_selection_from_analysis(restored, budget.target_count)
    assert [restored[i].manual_decision for i, _, _ in order] == ['keep']
    assert [p.manual_decision for p in restored] == ['keep', 'reject']
    assert all(p.path.is_file() for p in restored)
    assert all(p.decision_reason == 'Meine Entscheidung' for p in restored)

    other = create_project('Reise B', relocated, tmp_path / 'Reise B', remember=False)
    assert other.settings['book_pages'] == 0
    fresh = [Photo(path=p.path, filename=p.filename) for p in restored]
    restore_project_decisions(fresh, other.output_dir)
    assert all(p.manual_decision == 'auto' for p in fresh)
