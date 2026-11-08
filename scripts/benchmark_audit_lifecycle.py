"""Verify a real JPEG pipeline and the report/project lifecycle on synthetic input.

Generate fixture separately with benchmark_pipeline_scale.py, then run:
  python scripts/benchmark_audit_lifecycle.py --input /tmp/bench/input \
      --output /tmp/audit-lifecycle

Output must be new/empty. This executes real decoding, local analysis, export,
report generation, CSV/draft reopening and a second manual export. No network,
face detection, embeddings or AI is enabled. Repeated geometric templates are
not a real-photo quality assessment. Timing excludes fixture generation; peak
RSS includes imports and all lifecycle phases. Windows RSS is reported as null.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

try:
    import resource
except ImportError:
    resource = None

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def peak_rss_mib():
    if resource is None:
        return None
    scale = 1024 * 1024 if sys.platform == 'darwin' else 1024
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / scale, 1)


def assert_export_matches(photos, order, output):
    """Verify every kept original at its exact export path, including its bytes."""
    counters = Counter()
    expected = set()
    for index, folder, _kind in order:
        counters[folder] += 1
        photo = photos[index]
        relative = Path(folder) / f'{counters[folder]:03d}_{photo.filename}'
        expected.add(relative)
        exported = output / 'selected' / relative
        assert exported.is_file(), relative
        with photo.path.open('rb') as source, exported.open('rb') as destination:
            assert hashlib.file_digest(source, 'sha256').digest() == hashlib.file_digest(destination, 'sha256').digest(), relative
    actual = {path.relative_to(output / 'selected')
              for path in (output / 'selected').rglob('*') if path.is_file()}
    assert actual == expected, (actual - expected, expected - actual)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-count', type=int, default=2000)
    parser.add_argument('--target', type=int, default=180)
    args = parser.parse_args()
    source, output = args.input.resolve(), args.output.resolve()
    if not source.is_dir() or args.expected_count < 3 or args.target < 3:
        parser.error('existing input, expected count >=3 and target >=3 required')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error('output must be new or empty; existing project is never overwritten')
    if source.is_relative_to(output) or output.is_relative_to(source):
        parser.error('input and benchmark output must be separate folders')
    output.mkdir(parents=True, exist_ok=True)

    from photobook_curator.audit_report import build_audit_report, write_audit_report
    from photobook_curator.models import Photo, set_manual_decision
    from photobook_curator.output import write_csv
    from photobook_curator.pipeline import PipelineConfig, run_pipeline
    from photobook_curator.review_export import apply_manual_selection, load_photos_from_csv, plan_from_photos
    from photobook_curator.scan import find_images
    from photobook_curator.selection_draft import save_selection_draft, load_selection_draft, apply_selection_draft
    from photobook_curator.trace_schema import MAX_TRACE_BYTES, MAX_TRACE_EVENTS, selection_trace_json

    paths = sorted(find_images(source))
    assert len(paths) == args.expected_count, (len(paths), args.expected_count)
    # Seed supported persistent intent in the existing-analysis format. No draft
    # is seeded because a draft also intentionally overrides the selected set.
    seeds = [Photo(path=path, filename=path.name) for path in paths[:3]]
    seeds[0].is_favorite = True
    set_manual_decision(seeds[1], 'keep', 'Synthetic prior keep')
    set_manual_decision(seeds[2], 'reject', 'Synthetic prior reject')
    write_csv(seeds, output / 'photos_analysis.csv')
    cfg = PipelineConfig(input_dir=source, output_dir=output, target_n=args.target,
                         max_per_day=18, max_per_chapter=60, coverage_intensity=.8,
                         storytelling_intensity=.5, geocode=False, ai_review=False,
                         ai_provider='none', enable_faces=False, enable_content_clusters=False,
                         enable_accidental_filter=False, enable_weak_night_filter=False)
    stages = {}
    start = time.perf_counter()
    result = run_pipeline(cfg)
    stages['pipeline_seconds'] = round(time.perf_counter() - start, 3)
    stages['pipeline_peak_rss_mib'] = peak_rss_mib()
    photos = result['photo_objects']
    assert len(photos) == args.expected_count
    by_path = {p.path: i for i, p in enumerate(photos)}
    favorite, forced, rejected = (by_path[path] for path in paths[:3])
    kept = {i for i, p in enumerate(photos) if p.is_selected}
    assert favorite in kept and photos[favorite].is_favorite
    assert forced in kept and photos[forced].manual_decision == 'keep'
    assert rejected not in kept and photos[rejected].manual_decision == 'reject'
    assert all(p.selection_trace.get('status') == ('selected' if i in kept else 'not_selected')
               for i, p in enumerate(photos))
    assert all(p.selection_trace.get('final_reason') for p in photos)
    serialized = [selection_trace_json(p.selection_trace) for p in photos]
    assert all(serialized)
    trace_sizes = [len(value.encode('utf-8')) for value in serialized]
    assert max(trace_sizes) <= MAX_TRACE_BYTES
    assert max(len(p.selection_trace['events']) for p in photos) <= MAX_TRACE_EVENTS
    assert {i for i, _, _ in result['order']} == kept
    assert_export_matches(photos, result['order'], output)

    start = time.perf_counter()
    snapshot = build_audit_report(photos, kept, language='de', project_name='Synthetic lifecycle')
    stages['report_snapshot_seconds'] = round(time.perf_counter() - start, 3)
    assert snapshot.summary['total'] == len(photos)
    assert snapshot.summary['selected'] == len(kept)
    assert snapshot.summary['recorded'] == len(photos)
    assert max(snapshot.summary['days_selected'].values()) <= cfg.max_per_day
    assert max(snapshot.summary['chapters_selected'].values()) <= cfg.max_per_chapter
    start = time.perf_counter()
    write_audit_report(photos, output / 'audit-before.html', kept, output / 'audit-before.csv',
                       language='de', project_name='Synthetic lifecycle')
    stages['html_and_report_csv_seconds'] = round(time.perf_counter() - start, 3)
    assert (output / 'audit-before.html').read_text(encoding='utf-8').count('<article class="photo"') == len(photos)
    with (output / 'audit-before.csv').open(encoding='utf-8', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(photos)
    assert sum(row['selected'] == 'True' for row in rows) == len(kept)

    start = time.perf_counter()
    loaded = load_photos_from_csv(output / 'photos_analysis.csv')
    stages['analysis_csv_load_seconds'] = round(time.perf_counter() - start, 3)
    assert [selection_trace_json(p.selection_trace) for p in loaded] == serialized
    assert [p.location_evidence for p in loaded] == [p.location_evidence for p in photos]
    assert {i for i, p in enumerate(loaded) if p.is_selected} == kept
    assert loaded[favorite].is_favorite and loaded[forced].manual_decision == 'keep'
    assert loaded[rejected].manual_decision == 'reject'
    remove = next(i for i in sorted(kept) if not loaded[i].is_favorite and loaded[i].manual_decision == 'auto')
    add = next(i for i, p in enumerate(loaded) if i not in kept and p.manual_decision == 'auto'
               and 'unreadable' not in p.flags and not p.is_aside)
    set_manual_decision(loaded[remove], 'reject', 'Synthetic manual remove')
    set_manual_decision(loaded[add], 'keep', 'Synthetic manual add')
    manual_kept = (kept - {remove}) | {add}
    for i, p in enumerate(loaded):
        p.is_selected = i in manual_kept
    start = time.perf_counter()
    save_selection_draft(output, loaded, manual_kept,
                         review_state={'benchmark_path': str(loaded[add].path)})
    reopened = load_photos_from_csv(output / 'photos_analysis.csv')
    restored = apply_selection_draft(reopened, load_selection_draft(output))
    stages['draft_save_csv_reopen_apply_seconds'] = round(time.perf_counter() - start, 3)
    assert restored == manual_kept
    assert [selection_trace_json(p.selection_trace) for p in reopened] == serialized
    assert reopened[favorite].is_favorite and reopened[forced].manual_decision == 'keep'
    assert reopened[rejected].manual_decision == 'reject'
    assert reopened[remove].manual_decision == 'reject' and reopened[add].manual_decision == 'keep'
    assert reopened[remove].decision_reason == 'Synthetic manual remove'
    assert reopened[add].decision_reason == 'Synthetic manual add'

    start = time.perf_counter()
    manual_order = apply_manual_selection(reopened, plan_from_photos(reopened), sorted(restored), output)
    stages['manual_export_seconds'] = round(time.perf_counter() - start, 3)
    assert {i for i, _, _ in manual_order} == manual_kept
    assert_export_matches(reopened, manual_order, output)
    final = load_photos_from_csv(output / 'photos_analysis.csv')
    assert {i for i, p in enumerate(final) if p.is_selected} == manual_kept
    assert [selection_trace_json(p.selection_trace) for p in final] == serialized
    assert [p.location_evidence for p in final] == [p.location_evidence for p in reopened]
    for index in (favorite, forced, rejected, remove, add):
        assert final[index].is_favorite == reopened[index].is_favorite
        assert final[index].manual_decision == reopened[index].manual_decision
        assert final[index].decision_reason == reopened[index].decision_reason
    final_report = build_audit_report(final, language='en')
    assert final_report.summary['recorded'] == len(photos)
    assert final_report.photos[remove].primary_code == 'manual_reject'
    assert final_report.photos[add].primary_code == 'manual_keep'
    assert final_report.photos[remove].automatic_selected is True
    assert final_report.photos[add].automatic_selected is False
    write_audit_report(final, output / 'audit-after.html', manual_kept,
                       output / 'audit-after.csv', language='en')
    dimensions = sorted({(p.width, p.height) for p in photos})
    report = {'kind': 'synthetic_24mp_pipeline_audit_state_lifecycle', 'photos': len(photos),
              'source_pixels': [list(size) for size in dimensions],
              'fixture': 'Repeated geometric templates from benchmark_pipeline_scale.py',
              'days': len(snapshot.summary['days']),
              'cache_existed_before_run': False, 'config': {k: str(v) if isinstance(v, Path) else v
                                                        for k, v in asdict(cfg).items()},
              'measurements': stages, 'whole_process_peak_rss_mib': peak_rss_mib(),
              'automatic_kept': len(kept), 'manual_kept': len(manual_kept),
              'trace_bytes_max': max(trace_sizes), 'trace_bytes_total': sum(trace_sizes),
              'events_max': max(len(p.selection_trace['events']) for p in photos),
              'report_summary': snapshot.summary, 'all_assertions_passed': True,
              'export_verification': 'Exact path set and SHA-256 of every kept original before and after manual review',
              'output_sizes_bytes': {name: (output/name).stat().st_size for name in
                                     ('photos_analysis.csv', 'selection_draft.json', 'audit-before.html',
                                      'audit-before.csv', 'audit-after.html', 'audit-after.csv')},
              'excluded': ['faces', 'embeddings', 'AI', 'network_geocoding', 'HEIC', 'GUI', 'real_photo_quality_evaluation']}
    (output / 'lifecycle-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
