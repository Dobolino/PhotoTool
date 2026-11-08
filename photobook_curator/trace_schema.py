"""Bounded JSON schema for recorded automatic-selection evidence.

Missing or invalid evidence stays unknown. This module never reconstructs an
algorithmic reason from a score, current selection flag, filename, or image.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
from typing import Any

TRACE_VERSION = 1
MAX_TRACE_BYTES = 64 * 1024
MAX_TRACE_EVENTS = 24
_MAX_STRING = 4096
_MAX_CONTAINER = 64
_MAX_DEPTH = 6
_MAX_NODES = 2048
_STATUSES = frozenset({'pending', 'selected', 'not_selected'})


def normalize_selection_trace(value: Any) -> dict[str, Any]:
    """Return an independent valid trace or {}, within predictable parse bounds."""
    if isinstance(value, str):
        if len(value) > MAX_TRACE_BYTES:
            return {}
        try:
            if len(value.encode('utf-8')) > MAX_TRACE_BYTES:
                return {}
            value = json.loads(value)
        except (ValueError, RecursionError, UnicodeError):
            return {}
    if not isinstance(value, dict) or not value or len(value) > 10:
        return {}
    if type(value.get('version')) is not int or value['version'] != TRACE_VERSION:
        return {}
    run_id = value.get('run_id')
    context, events = value.get('context'), value.get('events')
    status, final_reason = value.get('status'), value.get('final_reason', '')
    if (not isinstance(run_id, str) or not run_id or len(run_id) > 128
            or not isinstance(context, dict) or not isinstance(events, list)
            or len(events) > MAX_TRACE_EVENTS or not isinstance(status, str)
            or status not in _STATUSES or not isinstance(final_reason, str)
            or len(final_reason) > _MAX_STRING):
        return {}
    remaining = _MAX_NODES

    def clean(item: Any, depth: int = 0) -> Any:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > _MAX_DEPTH:
            raise ValueError('trace exceeds structural limit')
        if item is None or isinstance(item, bool):
            return item
        if isinstance(item, int):
            if item.bit_length() > 128:
                raise ValueError('integer exceeds trace bounds')
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError('nonfinite trace value')
            return item
        if isinstance(item, str):
            if len(item) > _MAX_STRING:
                raise ValueError('trace string too long')
            return item
        if isinstance(item, list):
            if len(item) > _MAX_CONTAINER:
                raise ValueError('trace list too long')
            return [clean(child, depth + 1) for child in item]
        if isinstance(item, dict):
            if len(item) > _MAX_CONTAINER:
                raise ValueError('trace object too large')
            result = {}
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 128:
                    raise ValueError('invalid trace key')
                result[key] = clean(child, depth + 1)
            return result
        raise ValueError('unsupported trace value')

    try:
        normalized_events = []
        for event in events:
            if not isinstance(event, dict) or set(event) != {'code', 'stage', 'details'}:
                return {}
            code, stage, details = event['code'], event['stage'], event['details']
            if (not isinstance(code, str) or not code or len(code) > 128
                    or not isinstance(stage, str) or not stage or len(stage) > 64
                    or not isinstance(details, dict)):
                return {}
            if ('peer_path' in details and (not isinstance(details['peer_path'], str)
                                           or not details['peer_path'])):
                return {}
            if ('peer_paths' in details and (not isinstance(details['peer_paths'], list)
                                            or not all(isinstance(path, str) and path
                                                       for path in details['peer_paths']))):
                return {}
            normalized_events.append({'code': code, 'stage': stage, 'details': clean(details)})
        result = {'version': TRACE_VERSION, 'run_id': run_id,
                  'context': clean(context), 'events': normalized_events,
                  'status': status, 'final_reason': final_reason}
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        if len(encoded.encode('utf-8')) > MAX_TRACE_BYTES:
            return {}
        return result
    except (ValueError, TypeError, RecursionError, UnicodeError, OverflowError):
        return {}


def selection_trace_json(value: Any) -> str:
    trace = normalize_selection_trace(value)
    # Empty is deliberately blank for compatibility with existing analysis CSVs.
    return json.dumps(trace, ensure_ascii=False, allow_nan=False, separators=(',', ':')) if trace else ''


def _started_at(trace: dict) -> datetime | None:
    value = trace.get('context', {}).get('started_at')
    if not isinstance(value, str) or len(value) > 80:
        return None
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date if date.tzinfo is not None else None
    except ValueError:
        return None


def latest_selection_trace(current: Any, saved: Any) -> dict[str, Any]:
    """Keep the newest recorded run when a manual draft overlays an analysis CSV."""
    current, saved = normalize_selection_trace(current), normalize_selection_trace(saved)
    if not current:
        return saved
    if not saved:
        return current
    if current['run_id'] == saved['run_id']:
        if current['status'] == 'pending' and saved['status'] != 'pending':
            return saved
        if saved['status'] == 'pending' and current['status'] != 'pending':
            return current
        return saved if len(saved['events']) > len(current['events']) else current
    current_time, saved_time = _started_at(current), _started_at(saved)
    if current_time is not None and saved_time is not None and saved_time > current_time:
        return saved
    return current
