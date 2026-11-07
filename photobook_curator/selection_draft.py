"""Zwischenstand der manuellen Auswahl (Überleben von Absturz/Abbruch)."""

from __future__ import annotations

import json
import ntpath
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import Photo, normalized_manual_decision
from .trace_schema import latest_selection_trace, normalize_selection_trace
from .location_schema import latest_location_evidence, normalize_location_evidence

DRAFT_NAME = "selection_draft.json"


def _path_key(value: Any) -> str:
    """Respect case-sensitive POSIX files while accepting Windows separators/case."""
    raw = str(value or "").replace("\\", "/")
    if not raw:
        return ""
    if os.name == "nt" or ntpath.splitdrive(raw)[0]:
        return ntpath.abspath(raw).replace("\\", "/").casefold()
    return os.path.abspath(raw)


def draft_path(output_dir: Path) -> Path:
    return Path(output_dir) / DRAFT_NAME


def save_selection_draft(
    output_dir: Path,
    photos: list[Photo],
    kept_indices: set[int] | list[int],
    *, review_state: dict[str, Any] | None = None,
) -> Path:
    """Speichert behaltene Bilder per Pfad (+ Kapitelordner)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    kept = set(kept_indices)
    entries: list[dict[str, Any]] = []
    for i in sorted(kept):
        if i < 0 or i >= len(photos):
            continue
        p = photos[i]
        entries.append(
            {
                "path": str(p.path),
                "filename": p.filename,
                "chapter_folder": p.chapter_folder or "",
                "chapter_type": p.chapter_type or "",
                "region": p.region,
                "is_favorite": p.is_favorite,
            }
        )
    payload = {
        "version": 3,
        "review_state": review_state or {},
        "photo_states": [dict(path=str(p.path), filename=p.filename,
            selection_trace=normalize_selection_trace(p.selection_trace),
            location_evidence=normalize_location_evidence(p.location_evidence),
            **{key: getattr(p, key) for key in ("chapter_folder", "chapter_type",
                "region", "place_label", "country", "assigned_by_time", "is_aside", "is_duplicate", "is_burst_reject",
                "duplicate_of", "flags", "review_added", "manual_decision",
                "decision_reason")}) for p in photos],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "kept_count": len(entries),
        "kept": entries,
        "favorites": [str(p.path) for p in photos if p.is_favorite],
    }
    path = draft_path(output_dir)
    # Replace atomically so an interrupted save cannot truncate the previous draft.
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output_dir,
                                         suffix=".tmp", delete=False) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return path


def load_selection_draft(output_dir: Path) -> Optional[dict[str, Any]]:
    from .source_relink import recover_source_relink

    recover_source_relink(output_dir)
    path = draft_path(output_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("kept"), list):
        return None
    return data


def apply_selection_draft(
    photos: list[Photo],
    draft: dict[str, Any],
) -> set[int]:
    """
    Wendet Entwurf auf Photos an (is_selected / chapter_*).
    Returns: Indizes der behaltenen Fotos.
    """
    by_path = {_path_key(p.path): i for i, p in enumerate(photos)}
    version = draft.get("version", 1)
    # Modern projects use explicit source relinking. A reused camera filename
    # must not apply an old photo's selected state or chapter to a new source.
    allow_name_fallback = isinstance(version, int) and version < 3
    by_name: dict[str, list[int]] = {}
    for i, p in enumerate(photos):
        by_name.setdefault(p.filename.lower(), []).append(i)

    # Fresh analysis geography must not be reverted by a previous automatic
    # region/folder snapshot. Explicit chapter placement remains a user choice.
    current_location = {i: normalize_location_evidence(p.location_evidence) for i, p in enumerate(photos)}
    guard_region = {i for i, evidence in current_location.items() if evidence}
    fresh_location = set(guard_region)
    manual_chapter_flags = {"manual_chapter", "manual_chapter_override"}
    manual_chapters = {i for i, p in enumerate(photos) if manual_chapter_flags.intersection(p.flags)}

    def geographic_flag(flag: str) -> bool:
        return flag in {"assigned_by_time", "unbestimmt", "transit", "preamble_next_region"} or flag.startswith(
            ("location_", "gps_"))

    states = draft.get("photo_states", [])
    for entry in states if isinstance(states, list) else []:
        if not isinstance(entry, dict):
            continue
        idx = by_path.get(_path_key(entry.get("path")))
        if idx is not None:
            current_evidence = current_location[idx]
            saved_evidence = normalize_location_evidence(entry.get("location_evidence"))
            chosen_evidence = latest_location_evidence(current_evidence, saved_evidence)
            photos[idx].location_evidence = chosen_evidence
            manual_location = saved_evidence.get("source") == "manual" and chosen_evidence == saved_evidence
            if not current_evidence or chosen_evidence != current_evidence or manual_location:
                guard_region.discard(idx)
                fresh_location.discard(idx)
            elif current_evidence == saved_evidence:
                fresh_location.discard(idx)
            flags = entry.get("flags")
            if isinstance(flags, list) and all(isinstance(flag, str) for flag in flags):
                if manual_chapter_flags.intersection(flags):
                    manual_chapters.add(idx)
            if "selection_trace" in entry:
                photos[idx].selection_trace = latest_selection_trace(
                    photos[idx].selection_trace, entry["selection_trace"])
            photos[idx].manual_decision = normalized_manual_decision(
                entry.get("manual_decision"), flags=entry.get("flags") or ())
            reason = entry.get("decision_reason")
            photos[idx].decision_reason = reason if isinstance(reason, str) else ""
        if idx is None and allow_name_fallback:
            matches = by_name.get(str(entry.get("filename", "")).lower(), [])
            idx = matches[0] if len(matches) == 1 else None
        if idx is None:
            continue
        for key in ("chapter_folder", "chapter_type", "region", "place_label", "country", "duplicate_of"):
            if key in ("region", "place_label", "country") and idx in guard_region:
                continue
            if key in ("chapter_folder", "chapter_type") and idx in fresh_location and idx not in manual_chapters:
                continue
            value = entry.get(key)
            if key in entry and (value is None or isinstance(value, str)):
                setattr(photos[idx], key, value)
        for key in ("is_aside", "is_duplicate", "is_burst_reject", "review_added", "assigned_by_time"):
            if key == "assigned_by_time" and idx in guard_region:
                continue
            if key == "is_aside" and idx in fresh_location and idx not in manual_chapters:
                continue
            if isinstance(entry.get(key), bool):
                setattr(photos[idx], key, entry[key])
        flags = entry.get("flags")
        if isinstance(flags, list) and all(isinstance(f, str) for f in flags):
            if idx in guard_region:
                photos[idx].flags = list(dict.fromkeys(
                    [flag for flag in flags if not geographic_flag(flag)]
                    + [flag for flag in photos[idx].flags if geographic_flag(flag)]))
            else:
                photos[idx].flags = list(flags)

    kept: set[int] = set()
    if isinstance(draft.get("favorites"), list):
        favorite_paths = {_path_key(path) for path in draft["favorites"] if isinstance(path, str)}
        for p in photos:
            p.is_favorite = _path_key(p.path) in favorite_paths
    for entry in draft.get("kept") or []:
        if not isinstance(entry, dict):
            continue
        raw = _path_key(entry.get("path"))
        idx = by_path.get(raw)
        exact_match = idx is not None
        if idx is None and allow_name_fallback:
            names = by_name.get(str(entry.get("filename") or "").lower(), [])
            if len(names) == 1:
                idx = names[0]
        if idx is None:
            continue
        kept.add(idx)
        raw_folder = entry.get("chapter_folder")
        raw_ctype = entry.get("chapter_type")
        folder = raw_folder.strip() if isinstance(raw_folder, str) else ""
        ctype = raw_ctype.strip() if isinstance(raw_ctype, str) else ""
        allow_folder = idx not in fresh_location or idx in manual_chapters
        if folder and allow_folder:
            photos[idx].chapter_folder = folder
            # Verschieben aus Optional muss is_aside löschen, sonst setzt Speichern wieder 99_…
            from .documents import ASIDE_FOLDER

            if folder == ASIDE_FOLDER or folder.startswith("99_"):
                photos[idx].is_aside = True
            else:
                photos[idx].is_aside = False
        if ctype and allow_folder:
            photos[idx].chapter_type = ctype
        if idx not in guard_region and "region" in entry and (entry["region"] is None or isinstance(entry["region"], str)):
            photos[idx].region = entry["region"]
        if exact_match and "is_favorite" in entry:
            photos[idx].is_favorite = entry["is_favorite"] is True

    for i, p in enumerate(photos):
        p.is_selected = i in kept
        if i not in kept:
            p.book_position = None
    return kept


def draft_exists(output_dir: Path) -> bool:
    return draft_path(output_dir).is_file()


def restore_project_decisions(photos: list[Photo], output_dir: Path) -> dict[str, int]:
    """Restore durable intent for the same source paths before a new analysis.

    Current selected state and analysis scores are deliberately not restored.
    Draft entries override exported CSV, including an explicit reset to auto.
    Filename-only matches never carry durable intent to a different image.
    """
    from .review_export import load_photos_from_csv

    csv_path = output_dir / "photos_analysis.csv"
    previous = load_photos_from_csv(csv_path) if csv_path.is_file() else []
    state = {_path_key(p.path): (p.is_favorite, p.manual_decision, p.decision_reason)
             for p in previous}
    draft = load_selection_draft(output_dir)
    if draft:
        favorites = draft.get("favorites")
        has_favorites = isinstance(favorites, list)
        favorite_paths = {_path_key(path) for path in (favorites if has_favorites else [])
                          if isinstance(path, str)}
        entries = draft.get("photo_states")
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                    continue
                key = _path_key(entry["path"])
                reason = entry.get("decision_reason")
                favorite = key in favorite_paths if has_favorites else state.get(key, (False,))[0]
                state[key] = (favorite, normalized_manual_decision(
                    entry.get("manual_decision"), flags=entry.get("flags") or ()),
                    reason if isinstance(reason, str) else "")
        else:
            # Older drafts had only kept entries plus a complete favorite list.
            if has_favorites:
                state = {key: (key in favorite_paths, decision, reason)
                         for key, (_favorite, decision, reason) in state.items()}
            for entry in draft.get("kept", []):
                if isinstance(entry, dict) and isinstance(entry.get("path"), str):
                    key = _path_key(entry["path"])
                    favorite, decision, reason = state.get(key, (False, "auto", ""))
                    state[key] = (entry.get("is_favorite") is True or key in favorite_paths,
                                  decision, reason)
        for key in favorite_paths:
            _favorite, decision, reason = state.get(key, (False, "auto", ""))
            state[key] = (True, decision, reason)
    for photo in photos:
        favorite, decision, reason = state.get(_path_key(photo.path), (False, "auto", ""))
        photo.is_favorite = favorite
        photo.manual_decision = decision
        photo.decision_reason = reason
    return {"favorites": sum(p.is_favorite for p in photos),
            "keep": sum(p.manual_decision == "keep" for p in photos),
            "reject": sum(p.manual_decision == "reject" for p in photos)}


def restore_favorites(photos: list[Photo], output_dir: Path) -> int:
    """Compatibility entrypoint: restore favorites and durable manual decisions."""
    return restore_project_decisions(photos, output_dir)["favorites"]
