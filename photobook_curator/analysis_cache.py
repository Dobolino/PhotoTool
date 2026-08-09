"""Persistenter Analyse-Cache: Quality + pHash je Datei (path, mtime, size)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .models import Photo

CACHE_VERSION = 1


def _file_key(path: Path) -> str | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return f"{path.resolve()}|{st.st_mtime_ns}|{st.st_size}"


class AnalysisCache:
    def __init__(self, cache_path: Path) -> None:
        self.cache_path = cache_path
        self._data: dict[str, Any] = {"version": CACHE_VERSION, "entries": {}}
        if cache_path.exists():
            try:
                loaded = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict) and loaded.get("version") == CACHE_VERSION:
                    self._data = loaded
                    if "entries" not in self._data:
                        self._data["entries"] = {}
            except Exception:
                pass

    @property
    def entries(self) -> dict[str, Any]:
        return self._data.setdefault("entries", {})

    def get(self, path: Path) -> Optional[dict[str, Any]]:
        key = _file_key(path)
        if key is None:
            return None
        entry = self.entries.get(key)
        return entry if isinstance(entry, dict) else None

    def put(self, path: Path, payload: dict[str, Any]) -> None:
        key = _file_key(path)
        if key is None:
            return
        self.entries[key] = payload

    def save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def quality_payload(photo: Photo) -> dict[str, Any]:
    return {
        "sharpness": photo.sharpness,
        "exposure_mean": photo.exposure_mean,
        "contrast": photo.contrast,
        "saturation": photo.saturation,
        "is_too_dark": photo.is_too_dark,
        "is_overexposed": photo.is_overexposed,
        "phash": photo.phash,
        "flags": [f for f in photo.flags if f in ("too_dark", "overexposed", "unreadable", "phash_failed")],
    }


def apply_quality_payload(photo: Photo, data: dict[str, Any]) -> None:
    photo.sharpness = float(data.get("sharpness") or 0.0)
    photo.exposure_mean = float(data.get("exposure_mean") or 0.0)
    photo.contrast = float(data.get("contrast") or 0.0)
    photo.saturation = float(data.get("saturation") or 0.0)
    photo.is_too_dark = bool(data.get("is_too_dark"))
    photo.is_overexposed = bool(data.get("is_overexposed"))
    phash = data.get("phash")
    photo.phash = str(phash) if phash else None
    for flag in data.get("flags") or []:
        photo.add_flag(str(flag))
