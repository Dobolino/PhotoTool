"""Zwischenstand der manuellen Auswahl (Überleben von Absturz/Abbruch)."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import Photo

DRAFT_NAME = "selection_draft.json"


def draft_path(output_dir: Path) -> Path:
    return Path(output_dir) / DRAFT_NAME


def save_selection_draft(
    output_dir: Path,
    photos: list[Photo],
    kept_indices: set[int] | list[int],
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
        "version": 1,
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
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return path


def load_selection_draft(output_dir: Path) -> Optional[dict[str, Any]]:
    path = draft_path(output_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or "kept" not in data:
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
    by_path = {str(p.path).replace("\\", "/").lower(): i for i, p in enumerate(photos)}
    by_name: dict[str, list[int]] = {}
    for i, p in enumerate(photos):
        by_name.setdefault(p.filename.lower(), []).append(i)

    kept: set[int] = set()
    if isinstance(draft.get("favorites"), list):
        favorite_paths = {str(path).replace("\\", "/").lower() for path in draft["favorites"]}
        for p in photos:
            p.is_favorite = str(p.path).replace("\\", "/").lower() in favorite_paths
    for entry in draft.get("kept") or []:
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("path") or "").replace("\\", "/").lower()
        idx = by_path.get(raw)
        if idx is None:
            names = by_name.get(str(entry.get("filename") or "").lower(), [])
            if len(names) == 1:
                idx = names[0]
        if idx is None:
            continue
        kept.add(idx)
        folder = (entry.get("chapter_folder") or "").strip()
        ctype = (entry.get("chapter_type") or "").strip()
        if folder:
            photos[idx].chapter_folder = folder
            # Verschieben aus Optional muss is_aside löschen, sonst setzt Speichern wieder 99_…
            from .documents import ASIDE_FOLDER

            if folder == ASIDE_FOLDER or folder.startswith("99_"):
                photos[idx].is_aside = True
            else:
                photos[idx].is_aside = False
        if ctype:
            photos[idx].chapter_type = ctype
        if "region" in entry:
            photos[idx].region = entry["region"]
        if "is_favorite" in entry:
            photos[idx].is_favorite = entry["is_favorite"] is True

    for i, p in enumerate(photos):
        p.is_selected = i in kept
        if i not in kept:
            p.book_position = None
    return kept


def draft_exists(output_dir: Path) -> bool:
    return draft_path(output_dir).is_file()


def restore_favorites(photos: list[Photo], output_dir: Path) -> int:
    """Carry protection into a new analysis of the same paths/output directory."""
    from .review_export import load_photos_from_csv

    csv_path = output_dir / "photos_analysis.csv"
    previous = load_photos_from_csv(csv_path) if csv_path.is_file() else []
    draft = load_selection_draft(output_dir)
    if draft and isinstance(draft.get("kept"), list):
        # A draft may exist before the first export, so apply to fresh photos too.
        if not previous:
            previous = [Photo(path=p.path, filename=p.filename) for p in photos]
        apply_selection_draft(previous, draft)
    protected = {os.path.normcase(str(p.path.resolve())) for p in previous if p.is_favorite}
    for p in photos:
        p.is_favorite = os.path.normcase(str(p.path.resolve())) in protected
    return sum(p.is_favorite for p in photos)
