"""Reports explain real recorded branches without reading photograph pixels."""
import csv
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch

import pytest

from photobook_curator.audit_report import (
    build_audit_report, build_photo_audit, write_audit_csv, write_audit_report,
)
from photobook_curator.models import BookPlan, Photo, Region
from photobook_curator.selection import build_book_order, mark_candidates
from photobook_curator.selection_audit import begin_selection_audit, finalize_selection_audit
from photobook_curator.selection_reasons import selection_reasons
from photobook_curator.i18n import get_language, set_language


def photo(number=0, **kwargs):
    return Photo(path=Path('/originals') / str(number) / 'same.jpg', filename='same.jpg',
                 datetime_taken=datetime(2026, 4, 1) + timedelta(minutes=number), **kwargs)


def automatic_run(monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _path: None)
    photos = [photo(i, technical_score=score) for i, score in enumerate([95, 80, 60])]
    plan = BookPlan(regions=[Region('Kyoto', photo_indices=[0, 1, 2])])
    mark_candidates(photos, plan, 1, candidate_factor=1)
    build_book_order(photos, plan)
    return photos


def test_actual_selection_branch_and_exact_peer_path_not_duplicate_filename(monkeypatch):
    photos = automatic_run(monkeypatch)
    report = build_audit_report(photos, language='en')
    selected, omitted = report.photos[0], report.photos[2]
    assert selected.provenance_available and selected.automatic_selected is True
    assert omitted.provenance_available and omitted.automatic_selected is False
    assert omitted.primary_code == 'candidate_not_selected'
    assert 'shortlist' in omitted.primary_reasons[0]
    assert 'rank among eligible photos: 3' in omitted.primary_reasons[0]
    assert omitted.comparisons[0].peer_index == 0
    assert omitted.comparisons[0].peer_path == str(photos[0].path)
    assert report.summary['recorded'] == 3
    assert report.summary['selected'] == 1


def test_current_manual_review_never_rewrites_last_automatic_reason(monkeypatch):
    photos = automatic_run(monkeypatch)
    original = photos[0].selection_trace.copy()
    photos[0].manual_decision, photos[0].decision_reason = 'reject', 'Not this memory'
    audit = build_photo_audit(photos, 0, selected_override=False, language='en')
    assert not audit.selected and audit.automatic_selected is True
    assert audit.primary_code == 'manual_reject'
    assert any('Not this memory' in line for line in audit.primary_reasons)
    assert any('diversity' in line for line in audit.automatic_reasons)
    assert photos[0].selection_trace == original
    report = build_audit_report(photos, kept={2}, language='en')
    assert [p.selected for p in report.photos] == [False, False, True]
    assert report.photos[2].primary_code == 'review_changed'
    assert photos[0].is_selected  # The read-only override must not alter the model.


def test_pending_and_legacy_keep_facts_separate_from_unrecorded_causes():
    p = photo(is_duplicate=True, technical_score=12, region='Tokyo')
    legacy = build_photo_audit([p], 0, language='en')
    assert not legacy.provenance_available and legacy.automatic_selected is None
    assert 'not recorded' in legacy.primary_reasons[0]
    assert any('duplicate' in hint for hint in legacy.quality_hints)
    assert any('not recorded' in reason for reason in legacy.location_reasons)
    begin_selection_audit([p])
    p.selection_trace['events'].append({'code': 'candidate_selected', 'stage': 'candidate', 'details': {'quota': 1}})
    pending = build_photo_audit([p], 0, language='en')
    assert pending.primary_code == 'analysis_pending'
    assert not pending.provenance_available and pending.automatic_selected is None
    assert pending.recorded_decisions
    assert not pending.automatic_reasons


def test_generic_final_status_is_known_but_causal_provenance_remains_unknown():
    photos = [photo(0), photo(1)]
    begin_selection_audit(photos)
    finalize_selection_audit(photos, [(0, 'Kyoto/main', 'Hauptteil')])
    a, b = build_audit_report(photos, language='en').photos
    assert a.automatic_selected is True and b.automatic_selected is False
    assert not a.provenance_available and not b.provenance_available
    assert 'specific selection reason is missing' in a.automatic_reasons[0]
    assert 'specific selection reason is missing' in b.primary_reasons[0]


def test_malformed_trace_and_unmatched_peer_do_not_invent_comparison(monkeypatch):
    photos = automatic_run(monkeypatch)
    photos[2].selection_trace['events'][0]['details']['peer_path'] = 42
    invalid = build_photo_audit(photos, 2, language='en')
    assert invalid.automatic_selected is None and not invalid.comparisons
    photos[1].selection_trace = {'version': 1, 'run_id': 'x', 'context': {},
        'status': 'not_selected', 'final_reason': 'histogram_rejected', 'events': [
            {'code': 'histogram_rejected', 'stage': 'test', 'details': {
                'peer_path': '/elsewhere/same.jpg', 'similarity': 1, 'threshold': .9,
                'comparison_available': False}}]}
    unavailable = build_photo_audit(photos, 1, language='en')
    assert unavailable.comparisons[0].peer_index is None
    assert 'no measured image comparison' in unavailable.primary_reasons[0]
    assert 'measured similarity' not in unavailable.primary_reasons[0]


def test_location_provenance_uses_recorded_source_and_actual_time_anchor():
    p = photo(region='Kyoto', country='Japan', location_evidence={
        'version': 1, 'source': 'time_nearest', 'anchor_path': '/Tokyo/ref.jpg',
        'anchor_region': 'Kyoto', 'delta_hours': 1.25,
        'warning': 'conflicting_anchors', 'candidates': [
            {'anchor_path': '/a/a.jpg', 'region': 'Kyoto', 'delta_hours': 1.25},
            {'anchor_path': '/b/b.jpg', 'region': 'Tokyo', 'delta_hours': 1.5}]})
    lines = build_photo_audit([p], 0, language='en').location_reasons
    assert any('not GPS evidence' in line for line in lines)
    assert any('ref.jpg' in line and '1.25 h' in line for line in lines)
    assert any('different locations' in line for line in lines)
    assert any('Tokyo' in line and 'b.jpg' in line for line in lines)
    p.location_evidence = {'version': 1, 'source': 'manual'}
    assert any('manual location' in line for line in build_photo_audit([p], 0, language='en').location_reasons)


def test_unknown_nested_details_are_bounded_data_not_formatter_assumptions():
    p = photo(location_evidence={'version': 1, 'source': 'unknown', 'warning': ['unexpected']})
    p.selection_trace = {'version': 1, 'run_id': 'x', 'context': {}, 'status': 'not_selected',
        'final_reason': 'cap_refill_blocked', 'events': [
            {'code': 'score_computed', 'stage': 'test', 'details': {
                'modifiers': [{'code': 'x', 'operation': ['unexpected'], 'value': 1}]}},
            {'code': 'cap_refill_blocked', 'stage': 'test', 'details': {'constraint': ['unexpected']}}]}
    audit = build_photo_audit([p], 0, language='en')
    assert audit.provenance_available
    assert 'limit had been reached' in audit.primary_reasons[0]


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_html_escapes_untrusted_metadata_and_has_no_network_or_file_links(tmp_path):
    p = photo(manual_decision='keep', decision_reason='<script>alert(1)</script>',
              region='<img src="https://example.test/a">')
    p.filename = '<svg onload="alert(2)">.jpg'
    p.path = Path('/private/<bad>&".jpg')
    output = write_audit_report([p], tmp_path/'audit.html', kept={0},
        csv_path=tmp_path/'audit.csv', language='en', project_name='</title><script>oops</script>')
    content = output.read_text()
    parsed = Tags(); parsed.feed(content)
    assert [tag for tag, _ in parsed.tags].count('script') == 1  # Only fixed local filtering code.
    assert not any(tag in {'img', 'svg', 'iframe', 'link'} for tag, _ in parsed.tags)
    assert not any('src' in attrs or ('href' in attrs and not attrs['href'].startswith('#')) for _, attrs in parsed.tags)
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in content
    assert "default-src 'none'" in content
    assert 'current selection' in content
    assert (tmp_path/'audit.csv').exists()


def test_csv_protects_formula_cells_and_roundtrips_newlines(tmp_path):
    p = photo(manual_decision='keep', decision_reason='=SUM(A1)\nsecond line')
    p.filename = '=DDE()'
    output = write_audit_csv([p], tmp_path/'audit.csv', language='en')
    with output.open(newline='') as stream:
        row = next(csv.DictReader(stream))
    assert row['filename'] == "'=DDE()"
    assert row['manual_reason'] == "'=SUM(A1)\nsecond line"
    assert row['provenance_available'] == 'False'
    assert 'not recorded' in row['location_reasons']


def test_atomic_failure_preserves_existing_report_and_output_paths_must_differ(tmp_path):
    path = tmp_path/'audit.html'; path.write_text('previous valid report')
    with patch('photobook_curator.audit_report._write_html', side_effect=OSError('full disk')):
        with pytest.raises(OSError):
            write_audit_report([photo()], path)
    assert path.read_text() == 'previous valid report'
    assert not list(tmp_path.glob('*.tmp'))
    with pytest.raises(ValueError):
        write_audit_report([photo()], path, csv_path=path)
    assert path.read_text() == 'previous valid report'


def test_2200_image_report_is_metadata_only_and_indexed_once(tmp_path, monkeypatch):
    import photobook_curator.audit_report as module
    photos = [photo(i, technical_score=75, region='Kyoto') for i in range(2200)]
    begin_selection_audit(photos)
    for p in photos:
        p.selection_trace.update(status='not_selected', final_reason='candidate_not_selected')
        p.selection_trace['events'] = [{'code': 'candidate_not_selected', 'stage': 'candidate',
            'details': {'peer_path': str(photos[0].path), 'eligible_rank': 2200, 'candidate_limit': 200}}]
    calls = 0; original = module._source_key
    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)
    monkeypatch.setattr(module, '_source_key', counted)
    with patch('PIL.Image.open', side_effect=AssertionError('pixel access forbidden')):
        report = build_audit_report(photos, kept=range(200), language='en')
    assert len(report.photos) == 2200 and report.summary['selected'] == 200
    assert report.photos[-1].comparisons[0].peer_index == 0
    assert calls < len(photos)*4  # One global lookup, bounded per-event path matching.
    assert sum(report.summary['chapters_selected'].values()) == 200


def test_flat_reasons_include_actual_cause_without_hypothetical_quota(monkeypatch):
    photos = automatic_run(monkeypatch)
    previous = get_language(); set_language('en')
    try:
        reasons = selection_reasons(photos[2])
        assert any('Outside the limited shortlist' in line for line in reasons)
        assert not any('can also affect' in line for line in reasons)
    finally:
        set_language(previous)
