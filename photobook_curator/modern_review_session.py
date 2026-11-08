"""Thread-safe review state for the local desktop web interface.

The HTTP/native host is deliberately separate. This module works on metadata,
uses the established draft/export services and never decodes an image.
"""
from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from copy import deepcopy
from dataclasses import asdict, replace
import math
from pathlib import Path
import re
import threading
from typing import Any, Callable
from uuid import uuid4

from .models import BookPlan, Photo, set_manual_decision
from .review_compare import candidate_relation, ordered_album_indices
from .review_export import _guess_folder, apply_manual_selection, plan_from_photos
from .review_history import FIELDS, ReviewHistory
from .selection_draft import apply_selection_draft, load_selection_draft, save_selection_draft
from .location_schema import normalize_location_evidence
from .utils import slugify


class SessionError(ValueError):
    def __init__(self, message: str, *, status: int = 400, state: dict | None = None):
        super().__init__(message)
        self.status = status
        self.state = state


class _LocationCancelled(Exception):
    pass


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except OverflowError:
        return None


def _chapter(photo: Photo) -> str:
    return (_guess_folder(photo) or "Unbestimmt").replace("\\", "/").split("/", 1)[0]


def _chapter_name(value: str) -> str:
    return re.sub(r"^\d+[a-z]?[_\s]+", "", value).replace("_", " ")


def _canonical_chapters(photos: list[Photo]) -> list[str]:
    """Attach reserves to one evidenced automatic chapter, without renaming any.

    Selection only assigns chapter folders to chosen photos. A reserve still
    belongs beside them when the region/country and generated folder slug match.
    User-created chapters and ambiguous repeated visit roots remain distinct.
    Two linear passes avoid a collection scan for every reserve.
    """
    exact: dict[tuple[str, str], set[str]] = defaultdict(set)
    regions: dict[str, set[str]] = defaultdict(set)
    countries: dict[str, set[str]] = defaultdict(set)
    for photo in photos:
        if photo.region and photo.country:
            countries[photo.region.strip().casefold()].add(photo.country.strip().casefold())
        if not photo.chapter_folder or {"manual_chapter", "manual_chapter_override"}.intersection(photo.flags):
            continue
        root = photo.chapter_folder.replace("\\", "/").split("/", 1)[0]
        match = re.match(r"^\d+[a-z]?_(.+)$", root)
        if not match or not photo.region or match.group(1).casefold() != slugify(photo.region).casefold():
            continue
        region = photo.region.strip().casefold()
        country = (photo.country or "").strip().casefold()
        exact[(region, country)].add(root)
        regions[region].add(root)
    result = []
    for photo in photos:
        root = _chapter(photo)
        if not photo.chapter_folder and photo.region:
            region = photo.region.strip().casefold()
            country = (photo.country or "").strip().casefold()
            candidates = exact.get((region, country), set()) if country else regions.get(region, set())
            if len(candidates) == 1:
                root = next(iter(candidates))
            elif len(countries.get(region, set())) > 1:
                # Equal city names in different countries are not one chapter.
                root += " · " + (photo.country or "Land unbekannt")
        result.append(root)
    return result


def _metadata_state(photos: list[Photo]) -> list[tuple]:
    return [tuple(tuple(photo.flags) if field == "flags" else getattr(photo, field)
                  for field in FIELDS) for photo in photos]


def _restore_metadata(photos: list[Photo], states: list[tuple]) -> None:
    for photo, values in zip(photos, states):
        for field, value in zip(FIELDS, values):
            setattr(photo, field, list(value) if field == "flags" else value)


class ReviewSession:
    """One project and one mutation queue, with a durable save for each decision."""
    def __init__(self, photos: list[Photo], plan: BookPlan, output_dir: Path,
                 on_native: Callable[[str, dict], Any] | None = None):
        self.lock = threading.RLock()
        self.photos = photos
        self.plan = plan
        self.output_dir = Path(output_dir)
        self.on_native = on_native
        self.revision = 0
        self.image_revision = 0
        self.notice = ""
        self._closed = False
        self.close_requested = False
        self._busy = False
        self._active_job: str | None = None
        self._jobs: OrderedDict[str, dict] = OrderedDict()
        self._location_previews: dict[str, tuple[Any, int]] = {}
        self._source_previews: dict[str, tuple[Any, int]] = {}
        self._native_source: dict | None = None
        self._stop_location = threading.Event()
        self._legacy_view: dict = {}
        self.kept = {i for i, photo in enumerate(photos) if photo.is_selected}
        draft = load_selection_draft(self.output_dir)
        if draft is not None:
            self.kept = apply_selection_draft(photos, draft)
            raw = draft.get("review_state", {})
            self._legacy_view = raw if isinstance(raw, dict) else {}
        self.view = {"layout": "A", "filter": "all", "chapter": "all", "focus": 0 if photos else None,
                     "anchor": next(iter(sorted(self.kept)), None), "theme": "dark",
                     "export_layout": "flat", "alternative_ids": []}
        self._restore_view()
        self._sync_selected()
        self._history = ReviewHistory(photos)
        self._view_undo: list[dict] = []
        self._view_redo: list[dict] = []

    @property
    def busy(self) -> bool:
        with self.lock:
            return self._busy

    def _id(self, value: Any) -> int:
        if type(value) is not int or not 0 <= value < len(self.photos):
            raise SessionError("Dieses Foto ist nicht Teil des Projekts.")
        return value

    def image_photo(self, index: int) -> Photo:
        with self.lock:
            return replace(self.photos[self._id(index)])

    def _sync_selected(self) -> None:
        for i, photo in enumerate(self.photos):
            photo.is_selected = i in self.kept

    def _restore_view(self) -> None:
        by_path = {str(photo.path): i for i, photo in enumerate(self.photos)}
        chapters = set(_canonical_chapters(self.photos))
        old = self._legacy_view
        raw = old.get("modern_review")
        if isinstance(raw, dict):
            for key, allowed in (("layout", {"A", "B", "C"}), ("filter", {"all", "album", "alternatives"}),
                                 ("theme", {"dark", "light"}), ("export_layout", {"flat", "chapters"})):
                if isinstance(raw.get(key), str) and raw[key] in allowed:
                    self.view[key] = raw[key]
            chapter = raw.get("chapter", "all")
            if isinstance(chapter, str) and (chapter == "all" or chapter in chapters):
                self.view["chapter"] = chapter
            for field in ("focus", "anchor"):
                path = raw.get(field + "_path")
                index = by_path.get(path) if isinstance(path, str) else None
                if index is not None:
                    self.view[field] = index
            positions = raw.get("book_positions", {})
            if isinstance(positions, (dict, list)):
                pairs = positions.items() if isinstance(positions, dict) else (
                    (entry.get("path"), entry.get("position")) for entry in positions if isinstance(entry, dict))
                for path, position in pairs:
                    if not isinstance(path, str):
                        continue
                    index = by_path.get(path)
                    if index in self.kept and type(position) is int and position > 0:
                        self.photos[index].book_position = position
            paths = raw.get("alternative_paths")
            if isinstance(paths, list):
                self.view["alternative_ids"] = list(dict.fromkeys(by_path[path] for path in paths
                    if isinstance(path, str) and path in by_path))
        else:
            path = old.get("current_photo")
            focus = by_path.get(path) if isinstance(path, str) else None
            if focus is not None:
                self.view["focus"] = focus
            folder = old.get("folder")
            if isinstance(folder, str):
                chapter = folder.replace("\\", "/").split("/", 1)[0]
                if chapter in chapters:
                    self.view["chapter"] = chapter
        if not self.view["alternative_ids"]:
            self._refresh_alternatives()

    def _refresh_alternatives(self) -> None:
        chapter = self.view["chapter"]
        chapters = _canonical_chapters(self.photos)
        self.view["alternative_ids"] = [i for i, photo in enumerate(self.photos)
            if i not in self.kept and (chapter == "all" or chapters[i] == chapter)]

    def _persisted_review_state(self) -> dict:
        state = deepcopy(self._legacy_view)
        modern = {key: value for key, value in self.view.items()
                  if key not in {"focus", "anchor", "alternative_ids"}}
        for field in ("focus", "anchor"):
            index = self.view[field]
            modern[field + "_path"] = str(self.photos[index].path) if index is not None else ""
        modern["alternative_paths"] = [str(self.photos[i].path) for i in self.view["alternative_ids"]]
        # Paths are values, not dictionary keys: the established source-relink
        # service can then remap them together with focus/alternative paths.
        modern["book_positions"] = [{"path": str(self.photos[i].path), "position": self.photos[i].book_position}
            for i in sorted(self.kept) if self.photos[i].book_position is not None]
        state["modern_review"] = modern
        return state

    def _save(self) -> None:
        self._sync_selected()
        save_selection_draft(self.output_dir, self.photos, self.kept,
                             review_state=self._persisted_review_state())

    def save(self) -> None:
        with self.lock:
            if self._busy:
                raise SessionError("Der laufende Export bzw. die Ortsprüfung muss zuerst beendet werden.", status=409)
            self._save()

    def close(self) -> None:
        with self.lock:
            if self._closed:
                return
            if self._busy:
                raise SessionError("Es läuft noch ein Vorgang. Bitte warte bis zum Abschluss.", status=409)
            self._save()
            self._closed = True

    def snapshot(self) -> dict:
        with self.lock:
            chapters: OrderedDict[str, dict] = OrderedDict()
            records = []
            canonical = _canonical_chapters(self.photos)
            for index, photo in enumerate(self.photos):
                chapter = canonical[index]
                if chapter not in chapters:
                    chapters[chapter] = {"id": chapter, "name": _chapter_name(chapter), "total": 0, "selected": 0}
                chapters[chapter]["total"] += 1
                chapters[chapter]["selected"] += index in self.kept
                at = photo.datetime_taken
                location = normalize_location_evidence(photo.location_evidence)
                records.append({"id": index, "filename": photo.filename, "chapter": chapter,
                    "chapter_folder": photo.chapter_folder, "region": photo.region,
                    "date": at.date().isoformat() if at else None,
                    "time": at.strftime("%H:%M") if at else None,
                    "selected": index in self.kept, "favorite": bool(photo.is_favorite),
                    "manual_decision": photo.manual_decision, "position": photo.book_position,
                    "decision_reason": photo.decision_reason,
                    "width": photo.width, "height": photo.height,
                    "technical_score": _finite(photo.technical_score), "final_score": _finite(photo.final_score),
                    "scene_type": photo.scene_type, "landmark": photo.landmark,
                    "location_source": location.get("source"), "location_warning": location.get("warning"),
                    "flags": list(photo.flags), "burst_group_id": photo.burst_group_id,
                    "content_cluster_id": photo.content_cluster_id, "duplicate_of": photo.duplicate_of})
            names = Counter(chapter["name"] for chapter in chapters.values())
            for chapter in chapters.values():
                if names[chapter["name"]] > 1:
                    match = re.match(r"^(\d+[a-z]?)_", chapter["id"])
                    chapter["name"] += " · " + ("Kapitel " + match.group(1) if match else "ohne Nummer")
            return {"project": {"name": self.output_dir.name, "output_dir": str(self.output_dir)},
                    "revision": self.revision, "photos": records,
                    "image_revision": self.image_revision,
                    "kept": ordered_album_indices(self.photos, self.kept),
                    "chapters": list(chapters.values()), "view": deepcopy(self.view),
                    "can_undo": bool(self._history.undo_stack), "can_redo": bool(self._history.redo_stack),
                    "busy": self._busy, "job": deepcopy(self._jobs.get(self._active_job)),
                    "notice": self.notice, "close_requested": self.close_requested}

    def _guard_mutation(self, payload: dict) -> None:
        if self._closed:
            raise SessionError("Dieses Projektfenster ist bereits geschlossen.", status=409)
        if self._busy:
            raise SessionError("Es läuft noch ein Vorgang. Bitte warte bis zum Abschluss.", status=409,
                               state=self.snapshot())
        expected = payload.get("expected_revision")
        if expected is not None and (type(expected) is not int or expected != self.revision):
            raise SessionError("Die Auswahl wurde inzwischen geändert. Die Ansicht wurde aktualisiert.",
                               status=409, state=self.snapshot())

    def _transaction(self, mutate: Callable[[], None], *, history: bool = True) -> dict:
        before = _metadata_state(self.photos)
        kept = set(self.kept)
        view = deepcopy(self.view)
        notice = self.notice
        old_history = deepcopy(self._history)
        view_undo, view_redo = deepcopy(self._view_undo), deepcopy(self._view_redo)
        try:
            mutate()
            self._save()
            if history:
                self._history.record(self.photos)
                if self._history.current != before:
                    # Pair context is part of the same review operation, while
                    # filters/layout remain the user's current browsing choice.
                    self._view_undo.append({"before": {k: view[k] for k in ("focus", "anchor")},
                                            "after": {k: self.view[k] for k in ("focus", "anchor")}})
                    del self._view_undo[:-self._history.limit]
                    self._view_redo.clear()
        except Exception:
            _restore_metadata(self.photos, before)
            self.kept, self.view, self.notice, self._history = kept, view, notice, old_history
            self._view_undo, self._view_redo = view_undo, view_redo
            raise
        self.revision += 1
        return self.snapshot()

    def _can_remove(self, index: int) -> None:
        photo = self.photos[index]
        if photo.is_favorite:
            raise SessionError("Dieses Foto ist als Favorit geschützt. Hebe zuerst den Schutz auf.")
        if photo.manual_decision == "keep":
            raise SessionError("Dieses Foto wird dauerhaft behalten. Hebe zuerst diese Vorgabe auf.")

    def _can_add(self, index: int) -> None:
        photo = self.photos[index]
        if photo.manual_decision == "reject" and not photo.is_favorite:
            raise SessionError("Dieses Foto ist dauerhaft abgelehnt. Hebe zuerst diese Vorgabe auf.")
        if "unreadable" in photo.flags:
            raise SessionError("Das Original dieses Fotos konnte nicht gelesen werden.")

    def _add(self, index: int, *, folder: str | None = None, position: int | None = None) -> None:
        self._can_add(index)
        photo = self.photos[index]
        if index in self.kept:
            return
        self.kept.add(index)
        photo.is_selected = True
        photo.review_added = True
        photo.is_duplicate = photo.is_burst_reject = False
        photo.duplicate_of = None
        photo.flags = [flag for flag in photo.flags if flag not in
                       {"duplicate", "content_duplicate", "burst_reject", "manual_reject"}]
        photo.add_flag("manual_add")
        if folder:
            photo.chapter_folder = folder
            photo.chapter_type = "Essen" if folder.endswith("/essen") else "Hauptteil"
            photo.add_flag("manual_chapter")
        else:
            if not photo.chapter_folder:
                root = _canonical_chapters(self.photos)[index]
                part = "essen" if photo.scene_type == "essen" or photo.chapter_type == "Essen" else "hauptteil"
                photo.chapter_folder = f"{root}/{part}"
            photo.chapter_type = photo.chapter_type or ("Essen" if photo.scene_type == "essen" else "Hauptteil")
        photo.book_position = position if position is not None else max(
            (self.photos[i].book_position or 0 for i in self.kept if i != index), default=0) + 1

    def _remove(self, index: int) -> None:
        if index not in self.kept:
            return
        self._can_remove(index)
        self.kept.remove(index)
        self.photos[index].is_selected = False
        self.photos[index].book_position = None
        self.photos[index].add_flag("manual_reject")
        scope = self.view["chapter"]
        if (scope == "all" or _canonical_chapters(self.photos)[index] == scope) and index not in self.view["alternative_ids"]:
            self.view["alternative_ids"].append(index)

    def _set_view(self, raw: dict) -> None:
        if not isinstance(raw, dict):
            raise SessionError("Ungültiger Vorschauzustand.")
        old_chapter = self.view["chapter"]
        for key, allowed in (("layout", {"A", "B", "C"}), ("filter", {"all", "album", "alternatives"}),
                             ("theme", {"dark", "light"}), ("export_layout", {"flat", "chapters"})):
            if key in raw:
                if not isinstance(raw[key], str) or raw[key] not in allowed:
                    raise SessionError("Ungültige Ansichtseinstellung: " + key)
                self.view[key] = raw[key]
        if "chapter" in raw:
            chapter = raw["chapter"]
            if not isinstance(chapter, str) or (chapter != "all" and chapter not in set(_canonical_chapters(self.photos))):
                raise SessionError("Dieses Kapitel ist nicht Teil des Projekts.")
            self.view["chapter"] = chapter
        for key in ("focus", "anchor"):
            if key in raw:
                self.view[key] = self._id(raw[key]) if raw[key] is not None else None
        if old_chapter != self.view["chapter"] or raw.get("refresh_alternatives") is True:
            self._refresh_alternatives()

    def action(self, payload: dict) -> dict:
        if not isinstance(payload, dict) or not isinstance(payload.get("action"), str):
            raise SessionError("Ungültige Aktion.")
        name = payload["action"]
        if name == "source_choose":
            return self._choose_source()
        if name == "advanced":
            tool = payload.get("tool", "all")
            if not isinstance(tool, str) or tool not in {"all", "print", "motifs", "chapters", "rebuild"}:
                raise SessionError("Unbekanntes Werkzeug.")
            with self.lock:
                self._guard_mutation(payload)
                self._save()
            if self.on_native is None:
                raise SessionError("Weitere Werkzeuge sind nur im Desktopfenster verfügbar.")
            self.on_native("advanced_tools", {"tool": tool})
            return {"switching": True}
        if name == "open_folder":
            with self.lock:
                if self._closed:
                    raise SessionError("Dieses Projektfenster ist bereits geschlossen.", status=409)
                path = str(self.output_dir / "selected")
            if self.on_native is None:
                raise SessionError("Ordneröffnen ist in diesem Fenster nicht verfügbar.")
            self.on_native("open_folder", {"path": path})
            return self.snapshot()
        with self.lock:
            if name in {"state", "snapshot"}:
                return self.snapshot()
            if name == "job":
                job_id = payload.get("job_id")
                job = self._jobs.get(job_id) if isinstance(job_id, str) else None
                if job is None:
                    raise SessionError("Dieser Vorgang ist nicht mehr verfügbar.", status=404)
                return {"job": deepcopy(job), "state": self.snapshot()}
            if name == "audit":
                return self._audit(self._id(payload.get("id")))
            if name == "relation":
                code, label = candidate_relation(self.photos, self._id(payload.get("anchor")), self._id(payload.get("id")))
                return {"code": code, "label": label, "revision": self.revision}
            if name == "report":
                return self._report()
            if name == "location_cancel":
                self._stop_location.set()
                self._location_previews.clear()
                return self.snapshot()
            self._guard_mutation(payload)
            if name in {"toggle", "select"}:
                index = self._id(payload.get("id"))
                wanted = payload.get("selected", index not in self.kept)
                if type(wanted) is not bool:
                    raise SessionError("Der Auswahlstatus muss wahr oder falsch sein.")
                def toggle():
                    if wanted:
                        self._add(index)
                    else:
                        self._remove(index)
                    self.notice = "Ins Album aufgenommen." if wanted else "Aus dem Album entfernt. Das Foto bleibt sichtbar."
                return self._transaction(toggle)
            if name == "favorite":
                index = self._id(payload.get("id"))
                value = payload.get("value", not self.photos[index].is_favorite)
                if type(value) is not bool:
                    raise SessionError("Ungültiger Favoritenstatus.")
                def favorite():
                    self.photos[index].is_favorite = value
                    if value:
                        self._add(index)
                    self.notice = "Favorit geschützt." if value else "Favoritenschutz aufgehoben."
                return self._transaction(favorite)
            if name == "decision":
                index = self._id(payload.get("id"))
                decision = payload.get("decision")
                reason = payload.get("reason", "")
                if not isinstance(decision, str) or decision not in {"auto", "keep", "reject"} or not isinstance(reason, str) or len(reason) > 4096:
                    raise SessionError("Ungültige dauerhafte Entscheidung.")
                if decision == "reject" and self.photos[index].is_favorite:
                    raise SessionError("Hebe zuerst den Favoritenschutz auf.")
                def decide():
                    set_manual_decision(self.photos[index], decision, reason)
                    if decision == "keep":
                        self._add(index)
                    elif decision == "reject":
                        self._remove(index)
                    self.notice = "Dauerhafte Entscheidung gespeichert."
                return self._transaction(decide)
            if name == "replace":
                anchor, candidate = self._id(payload.get("anchor")), self._id(payload.get("id"))
                if anchor not in self.kept or anchor == candidate or candidate in self.kept:
                    raise SessionError("Wähle ein Albumfoto und eine noch nicht ausgewählte Alternative.")
                self._can_remove(anchor)
                self._can_add(candidate)
                def replace_current():
                    old = self.photos[anchor]
                    position, folder = old.book_position, old.chapter_folder or _guess_folder(old)
                    self._remove(anchor)
                    self._add(candidate, folder=folder, position=position)
                    self.view["anchor"] = candidate
                    self.view["focus"] = candidate
                    self.notice = "Am gleichen Albumplatz ersetzt. Rückgängig stellt beide Bilder wieder her."
                return self._transaction(replace_current)
            if name in {"undo", "redo"}:
                def history_action():
                    method = self._history.undo if name == "undo" else self._history.redo
                    if method(self.photos):
                        self.kept = {i for i, p in enumerate(self.photos) if p.is_selected}
                        source, target, key = ((self._view_undo, self._view_redo, "before") if name == "undo"
                                               else (self._view_redo, self._view_undo, "after"))
                        if source:
                            context = source.pop()
                            self.view.update(context[key])
                            target.append(context)
                    self.notice = "Änderung rückgängig gemacht." if name == "undo" else "Änderung wiederholt."
                return self._transaction(history_action, history=False)
            if name in {"view", "save"}:
                return self._transaction(lambda: self._set_view(payload.get("view", {})), history=False)
            if name == "close":
                self._save()
                self.close_requested = True
                return self.snapshot()
            if name == "export":
                return self._export(payload)
            if name == "location_preview":
                return self._location_preview(payload)
            if name == "location_apply":
                return self._location_apply(payload)
            if name == "source_preview":
                return self._source_preview(payload)
            if name == "source_apply":
                return self._source_apply(payload)
            raise SessionError("Unbekannte Aktion: " + name)

    def _audit(self, index: int) -> dict:
        from .audit_report import build_photo_audit
        audit = build_photo_audit(self.photos, index, selected_override=index in self.kept)
        automatic = "Unbekannt" if audit.automatic_selected is None else "Im Album" if audit.automatic_selected else "Ausgelassen"
        sections = [
            {"title": "Aktueller Stand", "text": "\n".join(audit.primary_reasons)},
            {"title": "Letzte automatische Auswahl: " + automatic,
             "text": "\n".join((*audit.automatic_reasons, audit.provenance_note))},
            {"title": "Deine dauerhafte Entscheidung", "text": {
                "keep": "Dauerhaft behalten", "reject": "Dauerhaft ablehnen", "auto": "Automatik"}.get(audit.manual_decision, "Automatik")
                + ("\n" + audit.manual_reason if audit.manual_reason else "")},
            {"title": "Qualitätsmerkmale", "text": f"Technisch: {audit.technical_score:.1f} · Gesamt: {audit.final_score:.1f}\n" + "\n".join(audit.quality_hints)},
            {"title": "Ort und Kapitelzuordnung", "text": "\n".join(audit.location_reasons)},
            {"title": "Gespeicherte Vergleiche", "text": "\n\n".join(c.filename + "\n" + c.explanation for c in audit.comparisons)
                or "Kein konkreter Vergleich mit einem anderen Bild gespeichert."},
            {"title": "Alle aufgezeichneten Auswahlschritte", "text": "\n\n".join(audit.recorded_decisions)},
        ]
        return {"audit": asdict(audit), "sections": sections, "revision": self.revision}

    def _report(self) -> dict:
        from .audit_report import write_audit_report
        write_audit_report(self.photos, self.output_dir / "selection_audit.html", kept=self.kept,
                           csv_path=self.output_dir / "selection_audit.csv")
        return {"report_url": "report.html", "csv_url": "report.csv", "revision": self.revision}

    def _start_job(self, kind: str, worker: Callable[[], dict]) -> dict:
        job_id = uuid4().hex
        self._busy = True
        self._active_job = job_id
        self._jobs[job_id] = {"id": job_id, "kind": kind, "status": "running"}
        while len(self._jobs) > 8:
            self._jobs.popitem(last=False)
        self.revision += 1
        def run():
            terminal: dict[str, Any] = {"status": "error", "error": "Der Vorgang wurde abgebrochen."}
            try:
                result = worker()
                terminal = {"status": "done", "result": result}
            except _LocationCancelled:
                terminal = {"status": "cancelled"}
            except Exception as exc:
                terminal = {"status": "error", "error": str(exc)}
            finally:
                with self.lock:
                    if kind == "location_preview" and self._stop_location.is_set():
                        terminal = {"status": "cancelled"}
                    # A terminal job must be published together with its idle
                    # state/revision. Otherwise a poll can stop on 'done' while
                    # still seeing busy=True and leave controls disabled.
                    self._jobs[job_id].update(terminal)
                    self._busy = False
                    self.revision += 1
        threading.Thread(target=run, name="review-" + kind, daemon=True).start()
        return {"job": deepcopy(self._jobs[job_id]), "state": self.snapshot()}

    def _export(self, payload: dict) -> dict:
        layout = payload.get("export_layout", self.view["export_layout"])
        if not isinstance(layout, str) or layout not in {"flat", "chapters"}:
            raise SessionError("Ungültige Exportstruktur.")
        if not self.kept:
            raise SessionError("Wähle zuerst mindestens ein Foto für das Album aus.")
        effective = self.kept | {i for i, photo in enumerate(self.photos)
                                 if photo.is_favorite or photo.manual_decision == "keep"}
        effective -= {i for i, photo in enumerate(self.photos)
                      if photo.manual_decision == "reject" and not photo.is_favorite}
        if effective != self.kept:
            raise SessionError("Die aktuelle Auswahl widerspricht gespeicherten Schutz- oder Ablehnungsregeln. "
                               "Prüfe diese Fotos vor dem Export im Prüfbericht.")
        self._transaction(lambda: self.view.update(export_layout=layout), history=False)
        photos = deepcopy(self.photos)
        kept = set(self.kept)
        def export_worker():
            warnings: list[str] = []
            order = apply_manual_selection(photos, plan_from_photos(photos), list(kept), self.output_dir,
                                           report_warning=warnings.append, export_layout=layout)
            with self.lock:
                for old, new in zip(self.photos, photos):
                    old.book_position = new.book_position
                    old.chapter_folder, old.chapter_type = new.chapter_folder, new.chapter_type
                self.plan = plan_from_photos(self.photos)
                # Export may compact book positions. Subsequent selection undo
                # must start from those live positions, not a stale baseline.
                self._history.current = _metadata_state(self.photos)
                try:
                    self._save()
                except Exception as exc:
                    warnings.append("Die Bilder wurden exportiert; der Entwurf konnte nicht aktualisiert werden: " + str(exc))
                self.notice = f"{len(order)} Originalkopien exportiert."
            return {"selected": len(order), "output_dir": str(self.output_dir / "selected"),
                    "export_layout": layout, "warnings": warnings,
                    "report_url": "report.html", "csv_url": "report.csv"}
        return self._start_job("export", export_worker)

    def _location_preview(self, payload: dict) -> dict:
        from .geocoding import GeocodeCache
        from .location_repair import preview_location_repair
        online = payload.get("online", False)
        hours = payload.get("max_hours", 6)
        if type(online) is not bool or isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours not in {1, 3, 6, 12, 24}:
            raise SessionError("Wähle ein Zeitfenster von 1, 3, 6, 12 oder 24 Stunden.")
        self._location_previews.clear()
        self._stop_location = threading.Event()
        stop = self._stop_location
        photos = deepcopy(self.photos)
        # The job itself increments revision once at start and once on finish.
        expected = self.revision + 2
        def location_worker():
            class CancellableCache(GeocodeCache):
                def reverse(self, lat, lon):
                    if stop.is_set():
                        raise _LocationCancelled()
                    result = super().reverse(lat, lon)
                    if stop.is_set():
                        raise _LocationCancelled()
                    return result
            preview = preview_location_repair(photos, CancellableCache(self.output_dir / "geocode_cache.json", enabled=online), max_hours=float(hours))
            if stop.is_set():
                raise _LocationCancelled()
            preview_id = uuid4().hex
            with self.lock:
                self._location_previews[preview_id] = (preview, expected)
            rows = []
            for change in preview.changes:
                row = asdict(change)
                evidence = normalize_location_evidence(preview.photos[change.index].location_evidence)
                if evidence.get("anchor_path"):
                    row["source_detail"] = "Anker " + str(evidence["anchor_path"]).replace("\\", "/").rsplit("/", 1)[-1]
                    if isinstance(evidence.get("delta_hours"), (int, float)):
                        row["source_detail"] += f" · {evidence['delta_hours']:.2f} h"
                rows.append(row)
            return {"preview_id": preview_id, "changed_count": preview.changed_count,
                    "unresolved_count": preview.unresolved_count,
                    "changes": rows}
        return self._start_job("location_preview", location_worker)

    def _location_apply(self, payload: dict) -> dict:
        from .location_repair import apply_location_repair
        from .location_repair_state import persist_location_repair
        preview_id = payload.get("preview_id")
        entry = self._location_previews.get(preview_id) if isinstance(preview_id, str) else None
        if entry is None:
            raise SessionError("Berechne zuerst eine Vorschau der Ortskorrekturen.")
        preview, revision = entry
        if revision != self.revision:
            raise SessionError("Die Auswahl wurde seit der Ortsvorschau geändert. Berechne die Vorschau erneut.", status=409)
        future_chapter = self.view["chapter"]
        canonical = _canonical_chapters(preview.photos)
        if future_chapter != "all" and future_chapter not in set(canonical):
            focus = self.view["focus"]
            future_chapter = canonical[focus] if focus is not None else "all"
        future_alternatives = [i for i, photo in enumerate(preview.photos)
            if i not in self.kept and (future_chapter == "all" or canonical[i] == future_chapter)]
        future_state = self._persisted_review_state()
        future_state["modern_review"]["chapter"] = future_chapter
        future_state["modern_review"]["alternative_paths"] = [str(preview.photos[i].path) for i in future_alternatives]
        persist_location_repair(preview.photos, self.kept, self.output_dir,
                                review_state=future_state)
        apply_location_repair(self.photos, preview)
        self.plan = plan_from_photos(self.photos)
        self.view["chapter"] = future_chapter
        self.view["alternative_ids"] = future_alternatives
        self._history = ReviewHistory(self.photos)
        self._view_undo.clear()
        self._view_redo.clear()
        self._location_previews.clear()
        self._refresh_alternatives()
        self.notice = f"{preview.changed_count} Ortskorrekturen gespeichert. Die Bildauswahl bleibt erhalten."
        self.revision += 1
        return self.snapshot()

    def _choose_source(self) -> dict:
        with self.lock:
            self._guard_mutation({})
            revision = self.revision
        if self.on_native is None:
            raise SessionError("Die Ordnerauswahl ist nur im Desktopfenster verfügbar.")
        result = self.on_native("choose_source", {})
        with self.lock:
            self._guard_mutation({"expected_revision": revision})
            if result is None or result == "":
                return {"cancelled": True, "revision": self.revision}
            if isinstance(result, (str, Path)):
                result = {"new_root": str(result)}
            if not isinstance(result, dict) or not isinstance(result.get("new_root"), str):
                raise SessionError("Die Ordnerauswahl lieferte keinen gültigen Pfad.")
            self._native_source = {key: result[key] for key in ("old_root", "new_root") if isinstance(result.get(key), str)}
            return {"choice": dict(self._native_source), "revision": self.revision}

    def _source_preview(self, payload: dict) -> dict:
        from .source_relink import _read_project_source, preview_source_relink
        if not self._native_source:
            raise SessionError("Wähle zuerst den neuen Originalordner aus.")
        new_root = self._native_source["new_root"]
        if "new_root" in payload and payload["new_root"] != new_root:
            raise SessionError("Verwende den über die Ordnerauswahl gewählten Pfad.")
        metadata = _read_project_source(self.output_dir)
        old_root = self._native_source.get("old_root") or (metadata[1] if metadata else None)
        if not old_root:
            import os
            try:
                old_root = os.path.commonpath([str(p.path.parent) for p in self.photos])
            except ValueError:
                raise SessionError("Der bisherige Originalordner ist nicht eindeutig. Öffne das Reiseprojekt mit seiner Projektdatei.")
        preview = preview_source_relink(self.photos, old_root, Path(new_root), output_dir=self.output_dir)
        preview_id = uuid4().hex
        self._source_previews = {preview_id: (preview, self.revision)}
        return {"preview_id": preview_id, "can_apply": preview.can_apply,
                "changed_count": len(preview.changes), "old_root": old_root, "new_root": new_root,
                "entries": [{"index": e.index, "filename": self.photos[e.index].filename,
                             "status": e.status, "message": e.message} for e in preview.entries],
                "revision": self.revision}

    def _source_apply(self, payload: dict) -> dict:
        from .source_relink import apply_source_relink
        preview_id = payload.get("preview_id")
        entry = self._source_previews.get(preview_id) if isinstance(preview_id, str) else None
        if entry is None or entry[1] != self.revision:
            raise SessionError("Berechne zuerst eine aktuelle Vorschau der Originalverknüpfung.", status=409)
        count = apply_source_relink(self.photos, entry[0], self.output_dir,
                                   review_state=self._persisted_review_state())
        self.image_revision += 1
        self._source_previews.clear()
        self._history = ReviewHistory(self.photos)
        self._view_undo.clear()
        self._view_redo.clear()
        self.notice = f"{count} Originale neu verknüpft. Keine Fotoanalyse gestartet."
        self.revision += 1
        return self.snapshot()
