"""Versioned travel-project metadata and recent projects.

The project describes sources and analysis settings. Selection decisions remain
in selection_draft.json; this file must never become a second selection state.
No API keys, tokens or environment values are persisted here.
"""
from __future__ import annotations

from dataclasses import MISSING, dataclass, fields, is_dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path, PureWindowsPath
import tempfile
from typing import Any

from .travel_profiles import get_profile

PROJECT_FILENAME = "phototool_project.json"
PROJECT_VERSION = 1
PROJECT_KIND = "phototool_project"
MAX_PROJECT_BYTES = 1024 * 1024
_SECRET_PARTS = ("api_key", "apikey", "secret", "token", "password", "credential")


@dataclass
class TravelProject:
    name: str
    input_dir: Path
    output_dir: Path
    settings: dict[str, Any]
    profile_id: str = "custom"
    created_at: str = ""
    updated_at: str = ""

    @property
    def path(self) -> Path:
        return self.output_dir / PROJECT_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_settings(settings: dict | None) -> dict[str, Any]:
    """Config values are flat JSON primitives; reject secrets and non-finite data."""
    if settings is None:
        return {}
    if not isinstance(settings, dict):
        raise ValueError("Projekteinstellungen müssen ein Objekt sein")
    result = {}
    for key, value in settings.items():
        if not isinstance(key, str) or key in ("input_dir", "output_dir"):
            continue
        if any(part in key.lower() for part in _SECRET_PARTS):
            continue
        if value is None or isinstance(value, (str, bool, int)):
            result[key] = value
        elif isinstance(value, float) and math.isfinite(value):
            result[key] = value
        else:
            raise ValueError(f"Ungültige Projekteinstellung: {key}")
    return result


def _default_config_settings() -> dict[str, Any]:
    # Import only on explicit project create/open, after the startup window exists.
    # Materializing defaults prevents settings from a different trip leaking into
    # a project whose file contains only profile overrides.
    from .pipeline import PipelineConfig
    result = {}
    for field in fields(PipelineConfig):
        if field.name in ("input_dir", "output_dir"):
            continue
        if field.default is not MISSING:
            result[field.name] = field.default
        elif field.default_factory is not MISSING:
            result[field.name] = field.default_factory()
    return _safe_settings(result)


def _atomic_json(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def _catalog_path() -> Path:
    from .settings import settings_path
    return settings_path().parent / "recent_projects.json"


def recent_projects(limit: int = 12, *, catalog_path: Path | None = None) -> list[dict]:
    if limit <= 0:
        return []
    path = catalog_path or _catalog_path()
    try:
        if path.stat().st_size > MAX_PROJECT_BYTES:
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("projects", []) if isinstance(data, dict) else []
    except (OSError, ValueError, TypeError):
        return []
    result = []
    seen = set()
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            continue
        try:
            project_path = Path(record["path"]).expanduser().resolve()
        except (OSError, ValueError, RuntimeError):
            continue
        identity = os.path.normcase(str(project_path))
        if identity in seen:
            continue
        seen.add(identity)
        result.append({"name": str(record.get("name") or project_path.parent.name),
                       "path": str(project_path), "updated_at": str(record.get("updated_at") or ""),
                       "exists": project_path.is_file()})
        if len(result) >= max(0, limit):
            break
    return result


def remember_project(project: TravelProject, *, catalog_path: Path | None = None) -> None:
    path = catalog_path or _catalog_path()
    identity = os.path.normcase(str(project.path.resolve()))
    records = [r for r in recent_projects(40, catalog_path=path)
               if os.path.normcase(r["path"]) != identity]
    records.insert(0, {"name": project.name, "path": str(project.path.resolve()),
                       "updated_at": _now()})
    _atomic_json(path, {"version": 1, "projects": [
        {k: r[k] for k in ("name", "path", "updated_at")} for r in records[:20]]})


def forget_project(project_path: Path, *, catalog_path: Path | None = None) -> None:
    """Remove only the launcher entry; project and photographs stay untouched."""
    path = catalog_path or _catalog_path()
    identity = os.path.normcase(str(project_path.expanduser().resolve()))
    records = [r for r in recent_projects(40, catalog_path=path)
               if os.path.normcase(r["path"]) != identity]
    _atomic_json(path, {"version": 1, "projects": [
        {k: r[k] for k in ("name", "path", "updated_at")} for r in records]})


def save_project(project: TravelProject, *, remember: bool = True) -> Path:
    name = str(project.name).strip()
    if not name or len(name) > 160:
        raise ValueError("Bitte einen Projektnamen mit 1–160 Zeichen eingeben")
    project.input_dir = Path(project.input_dir).expanduser().resolve()
    project.output_dir = Path(project.output_dir).expanduser().resolve()
    if project.input_dir.is_relative_to(project.output_dir):
        raise ValueError("Die Ausgabe darf den Originalordner nicht umfassen")
    settings = _safe_settings(project.settings)
    # A source within a portable project may become relative in a future schema.
    # Absolute source paths preserve the identity used by existing CSV/drafts.
    project.name = name
    project.settings = settings
    project.created_at = project.created_at or _now()
    project.updated_at = _now()
    path = _atomic_json(project.path, {
        "kind": PROJECT_KIND, "version": PROJECT_VERSION, "name": project.name,
        "input_dir": str(project.input_dir), "output_dir": ".",
        "profile_id": project.profile_id, "settings": settings,
        "created_at": project.created_at, "updated_at": project.updated_at,
    })
    if remember:
        try:
            remember_project(project)
        except OSError:
            # A launcher catalog failure must not invalidate the saved project.
            pass
    return path


def create_project(name: str, input_dir: Path, output_dir: Path, *,
                   profile_id: str = "balanced", settings: dict | None = None,
                   remember: bool = True) -> TravelProject:
    source, destination = Path(input_dir).expanduser().resolve(), Path(output_dir).expanduser().resolve()
    if not source.is_dir():
        raise ValueError(f"Originalordner nicht gefunden: {source}")
    if (destination / PROJECT_FILENAME).exists():
        raise FileExistsError("Dieser Ausgabeordner enthält bereits ein Projekt. Bitte dieses öffnen.")
    profile = get_profile(profile_id)
    options = _default_config_settings()
    options.update(profile.settings)
    options.update(_safe_settings(settings))
    project = TravelProject(name, source, destination, options, profile_id)
    save_project(project, remember=remember)
    return project


def load_project(path_or_output: Path, *, remember: bool = True) -> TravelProject:
    path = Path(path_or_output).expanduser().resolve()
    if path.is_dir():
        path = path / PROJECT_FILENAME
    from .source_relink import recover_source_relink
    recover_source_relink(path.parent)
    if path.stat().st_size > MAX_PROJECT_BYTES:
        raise ValueError("Projektdatei ist zu gross")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("kind") != PROJECT_KIND:
        raise ValueError("Keine PhotoTool-Projektdatei")
    if data.get("version") != PROJECT_VERSION:
        raise ValueError("Diese Projektversion wird nicht unterstützt. Bitte PhotoTool aktualisieren.")
    source = data.get("input_dir")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Im Projekt fehlt der Originalordner")
    source_path = Path(source).expanduser()
    foreign_windows_source = os.name != "nt" and PureWindowsPath(source).is_absolute()
    if not source_path.is_absolute() and not foreign_windows_source:
        source_path = path.parent / source_path
    if not foreign_windows_source:
        source_path = source_path.resolve()
    name = data.get("name")
    if not isinstance(name, str) or not name.strip() or len(name) > 160:
        raise ValueError("Ungültiger Projektname")
    profile_id = data.get("profile_id")
    if not isinstance(profile_id, str):
        profile_id = "custom"
    try:
        get_profile(profile_id)
    except ValueError:
        profile_id = "custom"
    settings = _default_config_settings()
    settings.update(_safe_settings(data.get("settings", {})))
    project = TravelProject(name.strip(), source_path, path.parent,
                            settings, profile_id,
                            str(data.get("created_at") or ""), str(data.get("updated_at") or ""))
    if remember:
        try:
            remember_project(project)
        except OSError:
            pass
    return project


def project_from_config(cfg, *, name: str | None = None, profile_id: str = "custom") -> TravelProject:
    if not is_dataclass(cfg):
        raise TypeError("Projektkonfiguration muss eine Dataclass sein")
    settings = {field.name: getattr(cfg, field.name) for field in fields(cfg)
                if field.name not in ("input_dir", "output_dir")}
    existing_path = Path(cfg.output_dir) / PROJECT_FILENAME
    if existing_path.is_file():
        project = load_project(existing_path, remember=False)
        if name:
            project.name = name
        project.settings = _safe_settings(settings)
        project.input_dir = Path(cfg.input_dir)
        if profile_id != "custom":
            project.profile_id = profile_id
        return project
    return TravelProject(name or Path(cfg.output_dir).name or "Meine Reise", Path(cfg.input_dir),
                          Path(cfg.output_dir), _safe_settings(settings), profile_id)


def config_kwargs(project: TravelProject, config_type=None) -> dict[str, Any]:
    """Known config fields only, so newer project settings can be opened safely."""
    if config_type is None:
        from .pipeline import PipelineConfig
        config_type = PipelineConfig
    allowed = {field.name for field in fields(config_type)}
    options = {key: value for key, value in project.settings.items() if key in allowed}
    options.update(input_dir=project.input_dir, output_dir=project.output_dir)
    return options
