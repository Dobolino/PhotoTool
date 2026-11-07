"""Report failures must not invalidate a successful album copy."""
from pathlib import Path

from photobook_curator.models import BookPlan, Photo


def test_automatic_export_includes_reports(tmp_path):
    from photobook_curator.pipeline import export_book_outputs
    source = tmp_path / 'original.jpg'
    source.write_bytes(b'original preserved bytes')
    photos = [Photo(source, source.name, is_selected=True, chapter_folder='01_Album/hauptteil')]
    output = tmp_path / 'output'
    result = export_book_outputs(photos, BookPlan(), [(0, '01_Album/hauptteil', 'Hauptteil')], output)
    assert result['audit_warning'] is None
    assert (output / 'selection_audit.html').is_file()
    assert (output / 'selection_audit.csv').is_file()
    assert next((output / 'selected').rglob('*.jpg')).read_bytes() == source.read_bytes()


def test_automatic_report_failure_leaves_valid_album_and_warning(tmp_path, monkeypatch):
    import photobook_curator.pipeline as pipeline
    source = tmp_path / 'original.jpg'
    source.write_bytes(b'original preserved bytes')
    photos = [Photo(source, source.name, is_selected=True)]
    output = tmp_path / 'output'
    def fail(*args, **kwargs):
        raise OSError('report file unavailable')
    monkeypatch.setattr(pipeline, 'write_audit_report', fail)
    result = pipeline.export_book_outputs(photos, BookPlan(), [(0, 'Album/hauptteil', 'Hauptteil')], output)
    assert 'report file unavailable' in result['audit_warning']
    assert (output / 'photos_analysis.csv').is_file()
    assert next((output / 'selected').rglob('*.jpg')).read_bytes() == source.read_bytes()
