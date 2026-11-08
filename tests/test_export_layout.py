"""Final-folder layouts share the same original-copy and publication guarantees."""
from copy import deepcopy
import csv
from pathlib import Path

import pytest

from photobook_curator.models import BookPlan, Photo
from photobook_curator.output import copy_selected, selected_export_paths


def originals(tmp_path):
    photos = []
    for i, folder in enumerate(('camera-a', 'camera-b', 'documents')):
        path = tmp_path / folder / ('ticket.jpg' if i == 2 else 'IMG_0001.JPG')
        path.parent.mkdir()
        path.write_bytes(f'untouched original {i}'.encode())
        photos.append(Photo(path, path.name, chapter_folder=f'0{i+1}_City/hauptteil',
                            chapter_type='Hauptteil', book_position=i+1,
                            is_aside=i == 2, aside_type='ticket' if i == 2 else None))
    return photos


def test_flat_layout_copies_only_final_images_and_keeps_reused_names(tmp_path):
    photos = originals(tmp_path)
    before = [p.path.read_bytes() for p in photos]
    order = [(1, '02_City/hauptteil', 'Hauptteil'), (0, '01_City/hauptteil', 'Hauptteil')]
    output = tmp_path / 'out'
    copy_selected(photos, order, output, export_layout='flat')
    selected = output / 'selected'
    assert sorted(p.name for p in selected.iterdir()) == ['001_IMG_0001.JPG', '002_IMG_0001.JPG']
    assert (selected / '001_IMG_0001.JPG').read_bytes() == before[1]
    assert (selected / '002_IMG_0001.JPG').read_bytes() == before[0]
    assert [p.path.read_bytes() for p in photos] == before
    assert all(p.is_file() for p in selected.iterdir())


def test_switching_layout_replaces_old_files_without_changing_chapter_metadata(tmp_path):
    from photobook_curator.review_export import apply_manual_selection
    photos = originals(tmp_path)
    output = tmp_path / 'out'
    chapters = [p.chapter_folder for p in photos]
    apply_manual_selection(photos, BookPlan(), [0, 1], output)
    assert (output / 'selected' / '01_City/hauptteil/001_IMG_0001.JPG').is_file()
    apply_manual_selection(photos, BookPlan(), [0, 1], output, export_layout='flat')
    assert sorted(p.name for p in (output / 'selected').iterdir()) == ['001_IMG_0001.JPG', '002_IMG_0001.JPG']
    assert [p.chapter_folder for p in photos] == chapters
    with (output / 'photos_analysis.csv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert [row['chapter_folder'] for row in rows] == chapters
    assert [row['is_selected'] for row in rows] == ['True', 'True', 'False']
    assert (output / 'optional_dokumente' / '001_ticket_ticket.jpg').is_file()
    assert (output / 'selection_audit.html').is_file()
    apply_manual_selection(photos, BookPlan(), [0, 1], output, export_layout='chapters')
    assert (output / 'selected' / '02_City/hauptteil/001_IMG_0001.JPG').is_file()
    assert not (output / 'selected' / '001_IMG_0001.JPG').exists()


def test_flat_export_preview_matches_exact_final_order_and_sorts_over_999():
    photo = Photo(Path('IMG_0001.JPG'), 'IMG_0001.JPG')
    photos = [photo] * 1_002
    order = [(i, 'City/hauptteil', 'Hauptteil') for i in range(len(photos))]
    paths = selected_export_paths(photos, order, export_layout='flat')
    assert paths[0] == (0, Path('0001_IMG_0001.JPG'))
    assert paths[-1] == (1001, Path('1002_IMG_0001.JPG'))
    names = [str(path) for _, path in paths]
    assert names == sorted(names) and len(set(names)) == len(photos)


@pytest.mark.parametrize('layout', ['invalid', '', None, 12])
def test_invalid_layout_rejected_before_selection_or_disk_changes(tmp_path, layout):
    from photobook_curator.review_export import apply_manual_selection
    from photobook_curator.pipeline import export_book_outputs, PipelineConfig, run_pipeline
    photos = originals(tmp_path)
    original_state = deepcopy(photos)
    output = tmp_path / 'out'
    with pytest.raises(ValueError, match='Exportaufteilung'):
        apply_manual_selection(photos, BookPlan(), [0], output, export_layout=layout)
    assert photos == original_state and not output.exists()
    with pytest.raises(ValueError, match='Exportaufteilung'):
        export_book_outputs(photos, BookPlan(), [(0, 'City', 'Hauptteil')], output, export_layout=layout)
    assert not output.exists()
    with pytest.raises(ValueError, match='Exportaufteilung'):
        run_pipeline(PipelineConfig(input_dir=tmp_path, output_dir=output, export_layout=layout))
    assert not output.exists()


@pytest.mark.parametrize('folder', ['../escape', '/absolute', 'C:/outside', r'C:\outside',
    r'\\server\share', r'City\..\escape', 'City/../escape', 'City/.. /escape', 'City:stream'])
def test_unsafe_chapter_paths_cannot_publish_outside_selected(tmp_path, folder):
    from photobook_curator.review_export import apply_manual_selection
    photos = originals(tmp_path)
    photos[0].chapter_folder = folder
    before = deepcopy(photos)
    output = tmp_path / 'out'
    with pytest.raises(ValueError):
        apply_manual_selection(photos, BookPlan(), [0], output)
    assert photos == before and not output.exists()
    with pytest.raises(ValueError):
        copy_selected(photos, [(0, folder, 'Hauptteil')], output)
    assert not output.exists()


def test_windows_relative_chapter_separator_is_portable(tmp_path):
    photos = originals(tmp_path)
    output = tmp_path / 'out'
    copy_selected(photos, [(0, r'01_City\hauptteil', 'Hauptteil')], output)
    assert (output / 'selected' / '01_City' / 'hauptteil' / '001_IMG_0001.JPG').is_file()


@pytest.mark.parametrize('filename', ['../escape.jpg', r'..\escape.jpg', '/outside.jpg', 'file.jpg:stream'])
def test_filename_path_injection_is_rejected_in_both_layouts(tmp_path, filename):
    photos = originals(tmp_path)
    photos[0].filename = filename
    for layout in ('flat', 'chapters'):
        output = tmp_path / layout
        with pytest.raises(ValueError, match='Exportdateiname'):
            copy_selected(photos, [(0, 'City', 'Hauptteil')], output, export_layout=layout)
        assert not output.exists()


def test_flat_failed_copy_preserves_previous_album(tmp_path, monkeypatch):
    import photobook_curator.output as output_module
    photos = originals(tmp_path)
    output = tmp_path / 'out'
    prior = output / 'selected'
    prior.mkdir(parents=True)
    (prior / 'previous.jpg').write_bytes(b'previous album')
    copy = output_module.shutil.copy2
    def fail_second(src, dst):
        if Path(src) == photos[1].path:
            raise OSError('source unavailable')
        return copy(src, dst)
    monkeypatch.setattr(output_module.shutil, 'copy2', fail_second)
    with pytest.raises(OSError, match='unavailable'):
        output_module.copy_selected(photos, [(0, 'City', 'Hauptteil'), (1, 'City', 'Hauptteil')],
                                    output, export_layout='flat')
    assert list(prior.iterdir()) == [prior / 'previous.jpg']
    assert (prior / 'previous.jpg').read_bytes() == b'previous album'
    assert not list(output.glob('.*-pending-*'))


def test_cli_passes_flat_layout_into_pipeline(tmp_path, monkeypatch):
    import photobook_curator.cli as cli
    observed = []
    monkeypatch.setattr(cli, 'run_pipeline', lambda cfg: observed.append(cfg) or {})
    assert cli.main(['-i', str(tmp_path), '-o', str(tmp_path/'out'), '--export-layout', 'flat']) == 0
    assert observed[0].export_layout == 'flat'


@pytest.mark.parametrize('layout', ['flat', 'chapters'])
def test_replacement_album_slot_survives_export_and_reopen(tmp_path, layout):
    from datetime import datetime
    from photobook_curator.review_export import apply_manual_selection, load_photos_from_csv
    photos = originals(tmp_path)
    # A later capture has deliberately replaced the first album image. The
    # earlier image still belongs in slot two, not first by timestamp.
    photos[0].datetime_taken, photos[0].book_position = datetime(2025, 11, 1), 2
    photos[1].datetime_taken, photos[1].book_position = datetime(2025, 11, 2), 1
    for p in photos[:2]:
        p.chapter_folder = '01_Kyoto/hauptteil'
        p.is_selected = True
    output = tmp_path / 'out'
    order = apply_manual_selection(photos, BookPlan(), [0, 1], output, export_layout=layout)
    assert [index for index, _, _ in order] == [1, 0]
    first = output / 'selected' / ('' if layout == 'flat' else '01_Kyoto/hauptteil') / '001_IMG_0001.JPG'
    assert first.read_bytes() == photos[1].path.read_bytes()
    loaded = load_photos_from_csv(output / 'photos_analysis.csv')
    assert loaded[1].book_position == 1 and loaded[0].book_position == 2
