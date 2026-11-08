"""Persist an explicitly approved location repair without touching an album."""
from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .models import Photo
from .output import write_csv
from .selection_draft import load_selection_draft, save_selection_draft
from .source_relink import _JOURNAL, _PROJECT_FILES, _fsync_file, _write_journal, recover_source_relink


def persist_location_repair(
    corrected_photos: list[Photo], kept: set[int] | list[int], output_dir: Path,
    *, review_state: dict[str, Any] | None = None,
) -> None:
    """Commit corrected CSV/draft together, preserving user decisions and view.

    Only metadata is written: no original images, analysis models, exported album
    files, or project settings are changed. The caller updates live geographic
    fields only after this function succeeds. Interrupted writes share the
    existing metadata-journal recovery used by every project loader.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    recover_source_relink(output_dir)
    selected = set(kept)
    if any(type(index) is not int or not 0 <= index < len(corrected_photos) for index in selected):
        raise ValueError('Ungültige Auswahlindizes für die Ortskorrektur')
    if review_state is not None and not isinstance(review_state, dict):
        raise ValueError('Der Vorschauzustand muss ein Objekt sein')
    snapshot = [replace(photo, is_selected=index in selected)
                for index, photo in enumerate(corrected_photos)]
    existing_draft = load_selection_draft(output_dir)
    view = review_state if review_state is not None else (existing_draft or {}).get('review_state', {})
    if not isinstance(view, dict):
        view = {}
    # This intentionally uses the established recovery prefix/protocol. A hard
    # interruption is rolled back by the next CSV, draft, or project read.
    staging = Path(tempfile.mkdtemp(prefix='.source-relink-', dir=output_dir))
    journal = output_dir / _JOURNAL
    journal_written = False
    try:
        write_csv(snapshot, staging / _PROJECT_FILES[0])
        save_selection_draft(staging, snapshot, selected, review_state=view)
        existed = {name: (output_dir / name).is_file() for name in _PROJECT_FILES}
        for name, exists in existed.items():
            if exists:
                shutil.copy2(output_dir / name, staging / f'before-{name}')
                _fsync_file(staging / f'before-{name}')
        _write_journal(journal, {'version': 2, 'staging': staging.name, 'existed': existed})
        journal_written = True
        for name in _PROJECT_FILES:
            os.replace(staging / name, output_dir / name)
        journal.unlink()
        journal_written = False
    except Exception:
        if journal_written:
            recover_source_relink(output_dir)
            journal_written = False
        raise
    finally:
        if not journal_written:
            shutil.rmtree(staging, ignore_errors=True)
