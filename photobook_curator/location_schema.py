"""Bounded recorded location evidence; region labels alone are not proof."""
from __future__ import annotations

from datetime import datetime
import json
import math
from typing import Any

LOCATION_EVIDENCE_VERSION = 1
MAX_LOCATION_EVIDENCE_BYTES = 16 * 1024
LOCATION_SOURCES = frozenset({'gps_online', 'gps_offline', 'time_nearest', 'unknown', 'legacy', 'manual'})


def normalize_location_evidence(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        if len(value) > MAX_LOCATION_EVIDENCE_BYTES:
            return {}
        try:
            if len(value.encode('utf-8')) > MAX_LOCATION_EVIDENCE_BYTES:
                return {}
            value = json.loads(value)
        except (ValueError, UnicodeError, RecursionError):
            return {}
    if (not isinstance(value, dict) or type(value.get('version')) is not int
            or value['version'] != LOCATION_EVIDENCE_VERSION
            or not isinstance(value.get('source'), str) or value['source'] not in LOCATION_SOURCES
            or len(value) > 32):
        return {}
    remaining = 256

    def clean(item: Any, depth: int = 0) -> Any:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 3:
            raise ValueError('location evidence too complex')
        if item is None or isinstance(item, bool):
            return item
        if isinstance(item, str):
            if len(item) > 4096:
                raise ValueError('location evidence string too long')
            return item
        if isinstance(item, int):
            if item.bit_length() > 128:
                raise ValueError('location evidence integer too large')
            return item
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError('nonfinite location evidence')
            return item
        if isinstance(item, list):
            if len(item) > 16:
                raise ValueError('location evidence list too long')
            return [clean(child, depth + 1) for child in item]
        if isinstance(item, dict):
            if len(item) > 32:
                raise ValueError('location evidence object too large')
            result = {}
            for key, child in item.items():
                if not isinstance(key, str) or len(key) > 96:
                    raise ValueError('invalid location evidence key')
                result[key] = clean(child, depth + 1)
            return result
        raise ValueError('unsupported location evidence value')

    try:
        result = clean(value)
        if ('anchor_path' in result and (not isinstance(result['anchor_path'], str)
                                         or not result['anchor_path'])):
            return {}
        for key in ('latitude', 'longitude'):
            if key in result and (isinstance(result[key], bool)
                                  or not isinstance(result[key], (int, float))):
                return {}
        if 'candidates' in result:
            candidates = result['candidates']
            if not isinstance(candidates, list) or len(candidates) > 2:
                return {}
            for candidate in candidates:
                if (not isinstance(candidate, dict)
                        or not isinstance(candidate.get('anchor_path'), str) or not candidate['anchor_path']
                        or not isinstance(candidate.get('region'), str)
                        or (candidate.get('country') is not None and not isinstance(candidate['country'], str))
                        or isinstance(candidate.get('delta_hours'), bool)
                        or not isinstance(candidate.get('delta_hours'), (int, float))
                        or candidate['delta_hours'] < 0):
                    return {}
        for key in ('anchor_region', 'anchor_country', 'warning', 'confidence'):
            if key in result and result[key] is not None and not isinstance(result[key], str):
                return {}
        if 'assigned_at' in result:
            assigned_at = result['assigned_at']
            if not isinstance(assigned_at, str) or len(assigned_at) > 80:
                return {}
            date = datetime.fromisoformat(assigned_at.replace('Z', '+00:00'))
            if date.tzinfo is None:
                return {}
        for key in ('delta_hours', 'anchor_delta_hours'):
            if key in result and (isinstance(result[key], bool)
                                  or not isinstance(result[key], (int, float))
                                  or result[key] < 0):
                return {}
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        return result if len(encoded.encode('utf-8')) <= MAX_LOCATION_EVIDENCE_BYTES else {}
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        return {}


def location_evidence_json(value: Any) -> str:
    evidence = normalize_location_evidence(value)
    return json.dumps(evidence, ensure_ascii=False, allow_nan=False, separators=(',', ':')) if evidence else ''


def latest_location_evidence(current: Any, saved: Any) -> dict[str, Any]:
    """Prefer the latest recorded location run; legacy labels cannot become proof."""
    current, saved = normalize_location_evidence(current), normalize_location_evidence(saved)
    if not current:
        return saved
    if not saved:
        return current
    current_at, saved_at = current.get('assigned_at'), saved.get('assigned_at')
    if current_at and saved_at:
        if datetime.fromisoformat(saved_at.replace('Z', '+00:00')) > datetime.fromisoformat(
                current_at.replace('Z', '+00:00')):
            return saved
    return current
