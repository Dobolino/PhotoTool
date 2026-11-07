"""Provenance follows executed branches and never invents legacy explanations."""
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from photobook_curator.models import BookPlan, Photo, Region
from photobook_curator.selection import build_book_order, mark_candidates
from photobook_curator.selection_audit import (
    MAX_EVENTS, begin_selection_audit, finalize_selection_audit, record_selection_event,
)


def photos_for(scores, days=None):
    return [Photo(path=Path('/originals') / str(i) / 'same-name.jpg', filename='same-name.jpg',
                  datetime_taken=datetime(2026, 4, 1) + timedelta(days=(days[i] if days else 0), minutes=i),
                  technical_score=score, scene_type='alltag')
            for i, score in enumerate(scores)]


def plan_for(photos):
    return BookPlan(regions=[Region('Trip', photo_indices=list(range(len(photos))))])


def events(photo, code):
    return [e['details'] for e in photo.selection_trace.get('events', []) if e['code'] == code]


def test_candidate_checkpoint_is_pending_and_completed_run_has_exact_status(monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = photos_for([90, 80, 70])
    plan = plan_for(photos)
    mark_candidates(photos, plan, 1, candidate_factor=1)
    run_id = photos[0].selection_trace['run_id']
    assert all(p.selection_trace['status'] == 'pending' for p in photos)
    assert all(p.selection_trace['final_reason'] == '' for p in photos)
    omitted = events(photos[2], 'candidate_not_selected')[0]
    assert omitted['eligible_rank'] == 3 and omitted['candidate_limit'] == 1
    assert omitted['peer_path'] == str(photos[0].path)  # Filename alone would be ambiguous.
    order = build_book_order(photos, plan)
    assert [i for i, _, _ in order] == [0]
    assert photos[0].selection_trace['status'] == 'selected'
    assert photos[2].selection_trace['status'] == 'not_selected'
    assert photos[2].selection_trace['final_reason'] == 'candidate_not_selected'
    assert all(p.selection_trace['run_id'] == run_id for p in photos)
    assert events(photos[0], 'selection_finalized')[0]['book_position'] == 1


def test_histogram_blocker_and_relaxed_fallback_are_both_recorded(monkeypatch):
    histogram = np.asarray([1, 2, 3], dtype=np.float32)
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: histogram)
    photos = photos_for([90, 80, 70])
    plan = plan_for(photos)
    mark_candidates(photos, plan, 2)
    order = build_book_order(photos, plan, similarity_threshold=.9)
    assert [i for i, _, _ in order] == [0, 1]
    rejected = events(photos[1], 'histogram_rejected')[0]
    assert rejected['similarity'] == pytest.approx(1)
    assert rejected['threshold'] == .9
    assert rejected['comparison_available'] is True
    assert rejected['peer_path'] == str(photos[0].path)
    fallback = events(photos[1], 'diversity_fallback_selected')[0]
    assert fallback['histogram_filter_relaxed'] is True
    assert photos[1].selection_trace['final_reason'] == 'diversity_fallback_selected'
    assert photos[2].selection_trace['status'] == 'not_selected'


def test_caps_record_observed_counts_and_real_refill(monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = photos_for([99, 98, 97, 80, 79], days=[0, 0, 0, 1, 1])
    plan = plan_for(photos)
    mark_candidates(photos, plan, 3)
    order = build_book_order(photos, plan, max_per_day=1)
    assert {i for i, _, _ in order} == {0, 3}
    removal = events(photos[1], 'cap_day_removed')[0]
    assert removal['count'] == removal['limit'] == 1
    refill = events(photos[3], 'cap_refill_selected')[0]
    assert refill['day_count'] == 1 and refill['max_per_day'] == 1
    assert photos[3].selection_trace['final_reason'] == 'cap_refill_selected'


def test_forced_keep_records_filter_override_and_only_real_cap_excess(monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = photos_for([99, 20, 10])
    photos[1].manual_decision = photos[2].manual_decision = 'keep'
    photos[1].is_duplicate = True
    plan = plan_for(photos)
    mark_candidates(photos, plan, 1)
    order = build_book_order(photos, plan, max_per_day=1)
    assert {i for i, _, _ in order} == {1, 2}
    assert events(photos[1], 'eligibility_rejected')[0]['forced_override'] is True
    assert photos[1].selection_trace['final_reason'] == 'forced_keep'
    first = events(photos[1], 'forced_keep')[0]
    second = events(photos[2], 'forced_keep')[0]
    assert first['day_limit_exceeded'] is False
    assert second['day_limit_exceeded'] is True


def test_new_direct_rebuild_replaces_completed_trace_and_never_retains_old_reason(monkeypatch):
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = photos_for([90, 80])
    plan = plan_for(photos)
    mark_candidates(photos, plan, 1)
    build_book_order(photos, plan)
    old_run = photos[0].selection_trace['run_id']
    photos[0].manual_decision = 'reject'
    photos[1].is_candidate = True
    order = build_book_order(photos, plan)
    assert [i for i, _, _ in order] == [1]
    assert photos[0].selection_trace['run_id'] != old_run
    assert photos[0].selection_trace['status'] == 'not_selected'
    assert not events(photos[0], 'diversity_selected')
    assert photos[0].selection_trace['context']['entry_stage'] == 'book_selection'


def test_recording_is_bounded_and_final_event_survives():
    photos = photos_for([90])
    assert not getattr(photos[0], 'selection_trace', {})  # No inferred legacy provenance.
    begin_selection_audit(photos, {'entry_stage': 'test'})
    for i in range(100):
        record_selection_event(photos[0], f'branch_{i}', 'test', value=i)
    finalize_selection_audit(photos, [(0, 'Trip/hauptteil', 'Hauptteil')])
    trace = photos[0].selection_trace
    assert len(trace['events']) <= MAX_EVENTS
    assert trace['events'][-1]['code'] == 'selection_finalized'
    assert trace['status'] == 'selected'
    assert 'started_at' in trace['context']


def test_recorded_score_steps_reproduce_the_actual_result():
    from photobook_curator.selection import compute_final_score
    from photobook_curator.trace_schema import normalize_selection_trace
    photos = photos_for([80])
    p = photos[0]
    p.aesthetic_score, p.keep_recommendation = 100, False
    p.quality_issue, p.bad_face, p.smiling = 'blur', True, True
    p.looking_at_camera, p.face_count = False, 1
    begin_selection_audit(photos, {'entry_stage': 'test'})
    actual = compute_final_score(p)
    detail = events(p, 'score_computed')[0]
    score = detail['technical_weight'] * detail['technical_score'] + detail['aesthetic_weight'] * detail['aesthetic_score']
    for modifier in detail['modifiers']:
        score = score * modifier['value'] if modifier['operation'] == 'multiply' else score + modifier['value']
    assert max(0, min(100, score)) == pytest.approx(actual)
    finalize_selection_audit(photos, [(0, 'Trip/hauptteil', 'Hauptteil')])
    assert normalize_selection_trace(p.selection_trace) == p.selection_trace


def test_people_penalty_records_real_evaluation_and_winning_adjusted_score(monkeypatch):
    from photobook_curator.selection import _select_diverse
    monkeypatch.setattr('photobook_curator.selection.color_histogram', lambda _p: None)
    photos = photos_for([90, 80])
    for p in photos:
        p.final_score = p.technical_score
    photos[0].person_cluster_ids, photos[1].person_cluster_ids = [1], [2]
    begin_selection_audit(photos)
    picked = _select_diverse(photos, [0, 1], 1, 1.1, people_balance_intensity=1,
                             person_counts={1: 3})
    assert picked == [1]
    observed = events(photos[0], 'people_balance_evaluated')[0]
    assert observed['penalty'] == 42 and observed['adjusted_score'] == 48
    assert observed['person_counts'] == {'1': 3}
    winner = events(photos[1], 'diversity_selected')[0]
    assert winner['method'] == 'people_greedy' and winner['adjusted_score'] == 86


def test_story_swap_records_both_actual_peers():
    from photobook_curator.selection import balance_story_roles
    photos = photos_for([99, 98, 97, 80])
    for p in photos:
        p.scene_type, p.final_score = 'landschaft', p.technical_score
    photos[3].scene_type = 'portrait'
    begin_selection_audit(photos)
    picked = balance_story_roles(photos, [0, 1, 2], list(range(4)), 3, 1)
    assert picked == [0, 1, 3]
    assert events(photos[3], 'story_role_selected')[0]['peer_path'] == str(photos[2].path)
    assert events(photos[2], 'story_role_replaced')[0]['peer_path'] == str(photos[3].path)
