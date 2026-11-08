"""Bounded provenance written by the real automatic selection branches.

These helpers never reconstruct reasons from a stored score. Legacy photos have
an empty trace until an actual automatic selection run is executed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Any
from uuid import uuid4

from .models import Photo

MAX_EVENTS = 24


def begin_selection_audit(photos: list[Photo], context: dict[str, Any] | None = None) -> str:
    run_id = uuid4().hex
    run_context = {**(context or {}), "started_at": datetime.now(timezone.utc).isoformat()}
    for photo in photos:
        photo.selection_trace = {
            "version": 1, "run_id": run_id, "context": run_context,
            "events": [], "status": "pending", "final_reason": "",
        }
    return run_id


def ensure_selection_audit(photos: list[Photo], context: dict[str, Any]) -> None:
    """Book selection can also be explicitly run without a new candidate pass."""
    traces = [getattr(p, "selection_trace", {}) for p in photos]
    run_ids = {t.get("run_id") for t in traces if isinstance(t, dict)}
    if (not traces or len(run_ids) != 1 or None in run_ids
            or any(not isinstance(t, dict) or t.get("version") != 1 or t.get("status") != "pending"
                   or not isinstance(t.get("context"), dict) or not isinstance(t.get("events"), list)
                   for t in traces)):
        begin_selection_audit(photos, {"entry_stage": "book_selection", **context})
    else:
        for trace in traces:
            trace["context"].update(context)


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value[:4096] if isinstance(value, str) else value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value[:32]]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in list(value.items())[:32]}
    return str(value)[:4096]


def record_selection_event(photo: Photo, code: str, stage: str, **details: Any) -> None:
    trace = getattr(photo, "selection_trace", None)
    if not isinstance(trace, dict) or trace.get("version") != 1 or trace.get("status") != "pending":
        return
    events = trace.get("events")
    if not isinstance(events, list):
        return
    event = {"code": code, "stage": stage, "details": _plain(details)}
    # One bounded event for each real branch/stage. Greedy re-evaluation retains
    # the latest observed value rather than recording every pairwise comparison.
    existing = next((i for i, old in enumerate(events)
                     if old.get("code") == code and old.get("stage") == stage), None)
    if existing is not None:
        events[existing] = event
    elif len(events) < MAX_EVENTS - 1:
        events.append(event)
    else:
        # Preserve early eligibility/budget facts and the latest decisive branch.
        events[-1] = event


def finalize_selection_audit(photos: list[Photo], order: list[tuple[int, str, str]]) -> None:
    positions = {idx: (position, folder, kind)
                 for position, (idx, folder, kind) in enumerate(order, start=1)}
    selected_reasons = (
        "forced_keep", "cap_refill_selected", "story_role_selected",
        "diversity_fallback_selected", "diversity_selected", "candidate_selected",
    )
    omitted_reasons = (
        "cap_day_removed", "cap_chapter_removed", "cap_refill_blocked", "forced_quota_displaced",
        "story_role_replaced", "diversity_quota_exhausted", "histogram_rejected",
        "landmark_limit_rejected", "candidate_not_selected", "eligibility_rejected",
    )
    for i, photo in enumerate(photos):
        trace = getattr(photo, "selection_trace", None)
        if not isinstance(trace, dict) or trace.get("version") != 1 or trace.get("status") != "pending":
            continue
        events = trace.get("events", [])
        codes = {event.get("code") for event in events if isinstance(event, dict)}
        selected = i in positions
        preferred = selected_reasons if selected else omitted_reasons
        reason = next((code for code in preferred if code in codes),
                      "final_selected" if selected else "final_not_selected")
        position, folder, kind = positions.get(i, (None, photo.chapter_folder, photo.chapter_type))
        events.append({"code": "selection_finalized", "stage": "final", "details": {
            "selected": selected, "book_position": position, "chapter_folder": folder,
            "chapter_type": kind}})
        trace["status"] = "selected" if selected else "not_selected"
        trace["final_reason"] = reason
