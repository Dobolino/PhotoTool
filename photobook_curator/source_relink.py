"""Preview and safely persist relocated original files without analysing them."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
import ntpath
import os
from pathlib import Path, PureWindowsPath
import shutil
import tempfile
from typing import Any

from .models import Photo
from .selection_draft import _path_key

_JOURNAL = '.source-relink-transaction.json'
_PROJECT_FILES = ('photos_analysis.csv', 'selection_draft.json')
_PROJECT_METADATA = 'phototool_project.json'


@dataclass(frozen=True)
class SourceRelinkEntry:
    index: int
    old_path: Path
    new_path: Path | None
    status: str  # ready | unchanged | outside_root | missing | ambiguous | invalid
    message: str = ''


@dataclass(frozen=True)
class SourceRelinkPreview:
    old_root: str
    new_root: Path
    missing_only: bool
    entries: tuple[SourceRelinkEntry, ...]
    expanded_indices: tuple[int, ...] = ()  # available originals included for a coherent project-root move

    @property
    def changes(self) -> tuple[SourceRelinkEntry, ...]:
        return tuple(entry for entry in self.entries if entry.status == 'ready')

    @property
    def can_apply(self) -> bool:
        return bool(self.changes) and not any(
            entry.status in {'missing', 'ambiguous', 'invalid'} for entry in self.entries)


def missing_source_indices(photos: list[Photo]) -> list[int]:
    return [i for i, photo in enumerate(photos) if not photo.path.is_file()]


def _relative_source(path: Path, old_root: str) -> Path:
    # Windows source paths remain interpretable after opening a project on Linux.
    if ntpath.splitdrive(old_root)[0] or '\\' in old_root:
        relative = PureWindowsPath(str(path)).relative_to(PureWindowsPath(old_root))
        return Path(*relative.parts)
    return path.resolve().relative_to(Path(old_root).resolve())


def _read_project_source(output_dir: Path) -> tuple[dict, str] | None:
    path = output_dir / _PROJECT_METADATA
    if not path.is_file():
        return None
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('Projektdatei ist zu gross')
    data = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(data, dict) or data.get('kind') != 'phototool_project'
            or data.get('version') != 1 or not isinstance(data.get('input_dir'), str)):
        raise ValueError('Projektdatei kann nicht sicher neu verknüpft werden')
    source = data['input_dir']
    if not Path(source).is_absolute() and not ntpath.splitdrive(source)[0]:
        source = str(output_dir / source)
    return data, source


def preview_source_relink(
    photos: list[Photo], old_root: Path | str, new_root: Path | str,
    *, missing_only: bool = True, output_dir: Path | None = None,
) -> SourceRelinkPreview:
    """Map paths below old_root to existing files at the same relative new path.

    Missing sources outside this mapping are reported but may be repaired using
    another root later. Missing/ambiguous targets inside the mapping block apply.
    When output_dir identifies a project whose source root is moving, the
    preview also includes available originals under that root. Otherwise a
    later scan of the new root would lose their durable path-based decisions.
    These expanded rows are explicitly identified in the preview.
    There is deliberately no filename guessing or recursive fuzzy search.
    """
    old_root = str(old_root)
    if not str(new_root).strip():
        raise ValueError('Der neue Quellordner darf nicht leer sein')
    new_root = Path(new_root).resolve()
    entries: list[SourceRelinkEntry] = []
    if not old_root.strip():
        raise ValueError('Der bisherige Quellordner darf nicht leer sein')
    if not new_root.is_dir():
        raise ValueError(f'Der neue Quellordner existiert nicht: {new_root}')
    project_source = None
    if output_dir is not None:
        metadata = _read_project_source(Path(output_dir))
        if metadata is not None:
            try:
                _relative_source(Path(metadata[1]), old_root)
                project_source = metadata[1]
            except ValueError:
                pass
    expanded_indices: list[int] = []
    for i, photo in enumerate(photos):
        expanded = False
        if missing_only and photo.path.is_file():
            if project_source is None:
                continue
            try:
                _relative_source(photo.path, project_source)
            except ValueError:
                continue
            expanded = True
        try:
            relative = _relative_source(photo.path, old_root)
        except ValueError:
            entries.append(SourceRelinkEntry(i, photo.path, None, 'outside_root',
                                            'Liegt ausserhalb des bisherigen Quellordners'))
            continue
        candidate = (new_root / relative).resolve()
        if '..' in relative.parts or not candidate.is_relative_to(new_root):
            entries.append(SourceRelinkEntry(i, photo.path, candidate, 'invalid',
                                            'Ziel liegt ausserhalb des neuen Quellordners'))
        elif not candidate.is_file():
            entries.append(SourceRelinkEntry(i, photo.path, candidate, 'missing',
                                            'Datei am neuen Ort nicht gefunden'))
        elif _path_key(photo.path) == _path_key(candidate):
            entries.append(SourceRelinkEntry(i, photo.path, candidate, 'unchanged'))
        else:
            message = ('Auch vorhandenes Original: wird für die neue Projektquelle verknüpft'
                       if expanded else '')
            entries.append(SourceRelinkEntry(i, photo.path, candidate, 'ready', message))
            if expanded:
                expanded_indices.append(i)
    target_owners: dict[str, list[int]] = {}
    mapped_indices = {entry.index for entry in entries if entry.status == 'ready'}
    for i, photo in enumerate(photos):
        if i not in mapped_indices:
            target_owners.setdefault(_path_key(photo.path.resolve()), []).append(i)
    for entry in entries:
        if entry.status == 'ready':
            target_owners.setdefault(_path_key(entry.new_path), []).append(entry.index)
    entries = [replace(entry, status='ambiguous', message='Mehrere Fotos würden dieselbe Datei verwenden')
               if entry.status == 'ready' and len(target_owners[_path_key(entry.new_path)]) > 1
               else entry for entry in entries]
    return SourceRelinkPreview(old_root, new_root, missing_only, tuple(entries), tuple(expanded_indices))


def _fsync_file(path: Path) -> None:
    with path.open('rb') as handle:
        os.fsync(handle.fileno())


def _write_journal(path: Path, data: dict) -> None:
    temporary = path.with_suffix('.tmp')
    try:
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(data, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def recover_source_relink(output_dir: Path) -> bool:
    """Rollback an interrupted project-metadata relink, preserving both original snapshots.

    Loaders call this before reading project metadata. Never analyse or copy an
    original photo here. A malformed journal fails closed instead of guessing.
    """
    output_dir = Path(output_dir)
    journal = output_dir / _JOURNAL
    if not journal.is_file():
        return False
    try:
        data = json.loads(journal.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise RuntimeError('Quellverknüpfungs-Protokoll konnte nicht gelesen werden') from exc
    if not isinstance(data, dict):
        raise RuntimeError('Ungültiges Quellverknüpfungs-Protokoll')
    folder = data.get('staging')
    existed = data.get('existed')
    allowed_files = (set(_PROJECT_FILES), set(_PROJECT_FILES + (_PROJECT_METADATA,)))
    if (data.get('version') not in (1, 2) or not isinstance(folder, str) or not folder.startswith('.source-relink-')
            or Path(folder).name != folder or not isinstance(existed, dict)
            or set(existed) not in allowed_files
            or (data.get('version') == 1 and set(existed) != set(_PROJECT_FILES))
            or not all(isinstance(value, bool) for value in existed.values())):
        raise RuntimeError('Ungültiges Quellverknüpfungs-Protokoll; Projektdateien wurden nicht verändert')
    staging = output_dir / folder
    if not staging.is_dir() or staging.resolve().parent != output_dir.resolve():
        raise RuntimeError('Sicherung der Quellverknüpfung fehlt; Projektdateien wurden nicht verändert')
    files = tuple(name for name in _PROJECT_FILES + (_PROJECT_METADATA,) if name in existed)
    for name in files:
        if existed[name] and not (staging / f'before-{name}').is_file():
            raise RuntimeError(f'Sicherung fehlt: {name}')
    for name in files:
        target = output_dir / name
        if existed[name]:
            temporary = staging / f'restore-{name}'
            shutil.copy2(staging / f'before-{name}', temporary)
            _fsync_file(temporary)
            os.replace(temporary, target)
        else:
            target.unlink(missing_ok=True)
    journal.unlink()
    shutil.rmtree(staging, ignore_errors=True)
    return True


def _remap_review_state(value: Any, paths: dict[str, str]) -> Any:
    if isinstance(value, str):
        return paths.get(_path_key(value), value)
    if isinstance(value, list):
        return [_remap_review_state(item, paths) for item in value]
    if isinstance(value, dict):
        return {key: _remap_review_state(item, paths) for key, item in value.items()}
    return value


def _relocated_project_metadata(output_dir: Path, preview: SourceRelinkPreview,
                                photos: list[Photo]) -> dict | None:
    """Preserve project settings while moving a covered source root."""
    metadata = _read_project_source(output_dir)
    if metadata is None:
        return None
    data, source = metadata
    try:
        relative = _relative_source(Path(source), preview.old_root)
    except ValueError:
        return None
    relocated = (preview.new_root / relative).resolve()
    if ('..' in relative.parts or not relocated.is_relative_to(preview.new_root)
            or not relocated.is_dir()):
        raise ValueError('Der verknüpfte Projekt-Quellordner existiert nicht')
    if relocated.is_relative_to(output_dir.resolve()):
        raise ValueError('Der neue Originalordner darf nicht im Ausgabeordner liegen')
    # Updating the future scan root must never silently lose known originals;
    # the root-aware preview includes available originals in its mapped scope.
    for photo in photos:
        try:
            photo_relative = _relative_source(photo.path, source)
        except ValueError:
            continue
        candidate = (relocated / photo_relative).resolve()
        if not candidate.is_relative_to(relocated) or not candidate.is_file():
            raise ValueError('Der neue Projektordner enthält noch nicht alle bekannten Originale: '
                             + str(photo_relative))
    result = dict(data)
    result['input_dir'] = str(relocated)
    result['updated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    return result


def apply_source_relink(
    photos: list[Photo], preview: SourceRelinkPreview, output_dir: Path,
    *, review_state: dict[str, Any] | None = None,
) -> int:
    """Revalidate, save CSV/draft/project together, then update live photo paths.

    Project metadata is backed up before any replacement. A handled error
    rolls back all files; a hard interruption is recovered by the next metadata read.
    """
    from .output import write_csv
    from .selection_draft import load_selection_draft, save_selection_draft

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    recover_source_relink(output_dir)
    current = preview_source_relink(photos, preview.old_root, preview.new_root,
                                    missing_only=preview.missing_only, output_dir=output_dir)
    if not preview.can_apply or current != preview:
        raise ValueError('Quellverknüpfung ist unvollständig oder geändert; bitte Vorschau erneut prüfen')
    metadata = _relocated_project_metadata(output_dir, preview, photos)
    files = _PROJECT_FILES + ((_PROJECT_METADATA,) if metadata is not None else ())
    updated = [replace(photo) for photo in photos]
    mapping: dict[str, str] = {}
    for entry in preview.changes:
        updated[entry.index].path = entry.new_path
        updated[entry.index].filename = entry.new_path.name
        mapping[_path_key(entry.old_path)] = str(entry.new_path)
    draft = load_selection_draft(output_dir)
    view = review_state if review_state is not None else (draft or {}).get('review_state', {})
    view = _remap_review_state(view, mapping)
    staging = Path(tempfile.mkdtemp(prefix='.source-relink-', dir=output_dir))
    journal = output_dir / _JOURNAL
    journal_written = False
    try:
        write_csv(updated, staging / _PROJECT_FILES[0])
        save_selection_draft(staging, updated, {i for i, p in enumerate(updated) if p.is_selected},
                             review_state=view if isinstance(view, dict) else {})
        if metadata is not None:
            _write_journal(staging / _PROJECT_METADATA, metadata)
        existed = {name: (output_dir / name).is_file() for name in files}
        for name, exists in existed.items():
            if exists:
                shutil.copy2(output_dir / name, staging / f'before-{name}')
                _fsync_file(staging / f'before-{name}')
        _write_journal(journal, {'version': 2, 'staging': staging.name, 'existed': existed})
        journal_written = True
        for name in files:
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
    for entry in preview.changes:
        photos[entry.index].path = entry.new_path
        photos[entry.index].filename = entry.new_path.name
    return len(preview.changes)
