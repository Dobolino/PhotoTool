"""Persistenter Analyse-Cache (SQLite) inkl. Embedding-Vektoren."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .models import Photo

CACHE_VERSION = 2
_FLAG_KEEP = {
    "too_dark",
    "overexposed",
    "unreadable",
    "phash_failed",
    "accidental",
    "accidental_shot",
    "weak_night",
    "eyes_closed",
    "face_cut_off",
    "face_too_small",
    "bad_face",
    "no_smile",
    "looking_away",
}


def _file_key(path: Path) -> str | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return f"{path.resolve()}|{st.st_mtime_ns}|{st.st_size}"


def _file_meta(path: Path) -> tuple[str, int, int] | None:
    try:
        st = path.stat()
        return str(path.resolve()), int(st.st_mtime_ns), int(st.st_size)
    except OSError:
        return None


class AnalysisCache:
    """
    SQLite-Cache je Ausgabeordner.
    API bleibt get/put/save – speichert Quality, Faces, Komposition, optional Embedding.
    Migriert alte analysis_cache.json einmalig.
    """

    def __init__(self, cache_path: Path) -> None:
        # Aufrufer übergibt oft …/analysis_cache.json – wir nutzen .sqlite daneben
        if cache_path.suffix.lower() == ".json":
            self.cache_path = cache_path.with_suffix(".sqlite")
            self._legacy_json = cache_path
        else:
            self.cache_path = cache_path
            self._legacy_json = cache_path.with_suffix(".json")
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.cache_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_schema()
        self._migrate_legacy_json()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS features (
                key TEXT PRIMARY KEY,
                path TEXT NOT NULL,
                mtime_ns INTEGER NOT NULL,
                size INTEGER NOT NULL,
                payload TEXT NOT NULL,
                embedding BLOB,
                updated_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL)"
        )
        self._conn.execute(
            "INSERT OR REPLACE INTO meta(k, v) VALUES ('version', ?)",
            (str(CACHE_VERSION),),
        )
        self._conn.commit()

    def _migrate_legacy_json(self) -> None:
        if not self._legacy_json.is_file():
            return
        try:
            loaded = json.loads(self._legacy_json.read_text(encoding="utf-8"))
        except Exception:
            return
        entries = loaded.get("entries") if isinstance(loaded, dict) else None
        if not isinstance(entries, dict):
            return
        cur = self._conn.execute("SELECT COUNT(*) FROM features")
        if int(cur.fetchone()[0]) > 0:
            return
        now = datetime.now(timezone.utc).isoformat()
        for key, payload in entries.items():
            if not isinstance(payload, dict):
                continue
            parts = str(key).rsplit("|", 2)
            path = parts[0] if parts else ""
            try:
                mtime_ns = int(parts[1]) if len(parts) > 1 else 0
                size = int(parts[2]) if len(parts) > 2 else 0
            except ValueError:
                mtime_ns, size = 0, 0
            self._conn.execute(
                "INSERT OR REPLACE INTO features(key, path, mtime_ns, size, payload, embedding, updated_at) "
                "VALUES (?, ?, ?, ?, ?, NULL, ?)",
                (key, path, mtime_ns, size, json.dumps(payload, ensure_ascii=False), now),
            )
        self._conn.commit()

    def get(self, path: Path) -> Optional[dict[str, Any]]:
        key = _file_key(path)
        if key is None:
            return None
        row = self._conn.execute(
            "SELECT payload FROM features WHERE key = ?", (key,)
        ).fetchone()
        if not row:
            return None
        try:
            data = json.loads(row[0])
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def get_embedding(self, path: Path) -> Optional[np.ndarray]:
        key = _file_key(path)
        if key is None:
            return None
        row = self._conn.execute(
            "SELECT embedding FROM features WHERE key = ?", (key,)
        ).fetchone()
        if not row or row[0] is None:
            return None
        try:
            arr = np.frombuffer(row[0], dtype=np.float32)
            return arr.copy()
        except Exception:
            return None

    def put(
        self,
        path: Path,
        payload: dict[str, Any],
        embedding: np.ndarray | None = None,
    ) -> None:
        meta = _file_meta(path)
        if meta is None:
            return
        resolved, mtime_ns, size = meta
        key = f"{resolved}|{mtime_ns}|{size}"
        blob = None
        if embedding is not None:
            blob = np.asarray(embedding, dtype=np.float32).tobytes()
        else:
            row = self._conn.execute(
                "SELECT embedding FROM features WHERE key = ?", (key,)
            ).fetchone()
            if row and row[0] is not None:
                blob = row[0]
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO features(key, path, mtime_ns, size, payload, embedding, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                resolved,
                mtime_ns,
                size,
                json.dumps(payload, ensure_ascii=False),
                blob,
                now,
            ),
        )

    def save(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.commit()
            self._conn.close()
        except Exception:
            pass


def quality_payload(photo: Photo) -> dict[str, Any]:
    return {
        "sharpness": photo.sharpness,
        "exposure_mean": photo.exposure_mean,
        "contrast": photo.contrast,
        "saturation": photo.saturation,
        "is_too_dark": photo.is_too_dark,
        "is_overexposed": photo.is_overexposed,
        "phash": photo.phash,
        "face_count": photo.face_count,
        "eyes_closed": photo.eyes_closed,
        "face_cut_off": photo.face_cut_off,
        "face_too_small": photo.face_too_small,
        "bad_face": photo.bad_face,
        "is_accidental": getattr(photo, "is_accidental", False),
        "is_weak_night": getattr(photo, "is_weak_night", False),
        "smiling": getattr(photo, "smiling", None),
        "looking_at_camera": getattr(photo, "looking_at_camera", None),
        "aesthetic_score": photo.aesthetic_score,
        "flags": [f for f in photo.flags if f in _FLAG_KEEP],
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
    if "face_count" in data:
        photo.face_count = int(data.get("face_count") or 0)
    photo.eyes_closed = bool(data.get("eyes_closed"))
    photo.face_cut_off = bool(data.get("face_cut_off"))
    photo.face_too_small = bool(data.get("face_too_small"))
    photo.bad_face = bool(data.get("bad_face"))
    photo.is_accidental = bool(data.get("is_accidental"))
    photo.is_weak_night = bool(data.get("is_weak_night"))
    if "smiling" in data:
        val = data.get("smiling")
        photo.smiling = None if val is None else bool(val)
    if "looking_at_camera" in data:
        val = data.get("looking_at_camera")
        photo.looking_at_camera = None if val is None else bool(val)
    if data.get("aesthetic_score") is not None:
        try:
            photo.aesthetic_score = float(data["aesthetic_score"])
        except (TypeError, ValueError):
            pass
    for flag in data.get("flags") or []:
        photo.add_flag(str(flag))
