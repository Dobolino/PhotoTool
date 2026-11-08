"""CSV-, Ordner- und Markdown-Ausgabe."""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

from .models import BookPlan, Photo


CSV_FIELDS = [
    "filename",
    "path",
    "date",
    "time",
    "region",
    "location_evidence",
    "chapter_type",
    "scene_type",
    "mood",
    "camera_model",
    "gps_lat",
    "gps_lon",
    "width",
    "height",
    "sharpness",
    "exposure_mean",
    "contrast",
    "saturation",
    "face_count",
    "eyes_closed",
    "face_cut_off",
    "face_too_small",
    "bad_face",
    "finger_on_lens",
    "is_accidental",
    "is_weak_night",
    "smiling",
    "looking_at_camera",
    "content_cluster_id",
    "person_cluster_ids",
    "technical_score",
    "aesthetic_score",
    "landmark",
    "quality_issue",
    "keep_recommendation",
    "ai_reviewed",
    "final_score",
    "selection_trace",
    "flags",
    "is_candidate",
    "is_selected",
    "is_favorite",
    "manual_decision",
    "decision_reason",
    "review_added",
    "book_position",
    "chapter_folder",
    "is_duplicate",
    "duplicate_of",
    "is_burst_reject",
    "burst_group_id",
    "is_screenshot",
    "is_aside",
    "aside_type",
    "assigned_by_time",
    "fine_cluster_id",
    "country",
    "place_label",
]


def write_csv(photos: list[Photo], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", newline="", encoding="utf-8",
                                         dir=path.parent, suffix=".tmp", delete=False) as f:
            temporary = Path(f.name)
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            for photo in photos:
                writer.writerow(photo.to_csv_row())
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def _staged_directory(destination: Path):
    """Keep the previous export until every source file has copied successfully.

    The two renames happen on the same filesystem. If publishing the prepared
    directory fails (for example a Windows folder is open), restore the old one.
    A process crash between renames leaves the previous export in the explicitly
    named backup directory instead of deleting it.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{destination.name}-pending-",
                                    dir=destination.parent))
    backup = staging.with_name(staging.name.replace("-pending-", "-previous-", 1))
    moved_previous = False
    published = False
    try:
        yield staging
        if destination.exists():
            os.replace(destination, backup)
            moved_previous = True
        try:
            os.replace(staging, destination)
            published = True
        except OSError:
            if moved_previous:
                os.replace(backup, destination)
            raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if published and moved_previous:
            shutil.rmtree(backup, ignore_errors=True)


EXPORT_LAYOUTS = ("chapters", "flat")


def validate_export_layout(export_layout: str) -> str:
    """Validate before changing selection metadata or creating output files."""
    if export_layout not in EXPORT_LAYOUTS:
        raise ValueError("Exportaufteilung muss 'chapters' oder 'flat' sein")
    return export_layout


def _export_filename(filename: str) -> str:
    if (not isinstance(filename, str) or not filename or filename in (".", "..")
            or any(char in filename for char in ("/", "\\", ":", "\x00"))):
        raise ValueError("Ein Exportdateiname darf keinen Pfad enthalten")
    return filename


def _export_chapter(folder: str) -> Path:
    """Accept portable relative chapter paths, never an escape from selected/."""
    if not isinstance(folder, str) or not folder or "\x00" in folder:
        raise ValueError("Ungültiger Kapitelordner für den Export")
    normalized = folder.replace("\\", "/")
    parts = normalized.split("/")
    if (normalized.startswith("/") or PureWindowsPath(folder).drive
            or any(part in ("", ".", "..") or ":" in part
                   or part.rstrip(" .") != part for part in parts)):
        raise ValueError("Kapitelordner muss innerhalb des Auswahlordners liegen")
    return Path(*parts)


def selected_export_paths(
    photos: list[Photo],
    order: list[tuple[int, str, str]],
    *, export_layout: str = "chapters",
) -> list[tuple[int, Path]]:
    """Return exact paths relative to selected/, without writes or mutations.

    Flat names use the final album order; chapter names retain the established
    per-folder counter. Both modes prefix original filenames so reused camera
    names from different folders do not overwrite each other.
    """
    validate_export_layout(export_layout)
    result: list[tuple[int, Path]] = []
    counters: dict[Path, int] = {}
    flat_digits = max(3, len(str(len(order))))
    for position, (idx, folder, _ctype) in enumerate(order, start=1):
        if type(idx) is not int or not 0 <= idx < len(photos):
            raise ValueError("Ungültiger Fotoindex für den Export")
        filename = _export_filename(photos[idx].filename)
        if export_layout == "flat":
            relative = Path(f"{position:0{flat_digits}d}_{filename}")
        else:
            chapter = _export_chapter(folder)
            counters[chapter] = counters.get(chapter, 0) + 1
            relative = chapter / f"{counters[chapter]:03d}_{filename}"
        result.append((idx, relative))
    return result


def copy_selected(
    photos: list[Photo],
    order: list[tuple[int, str, str]],
    output_dir: Path,
    *, export_layout: str = "chapters",
) -> None:
    destinations = selected_export_paths(photos, order, export_layout=export_layout)
    selected_root = output_dir / "selected"
    with _staged_directory(selected_root) as staging:
        for idx, relative in destinations:
            photo = photos[idx]
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(photo.path, destination)

    _prewarm_review_thumbs([photos[idx].path for idx, _f, _c in order])


# Muss zur THUMB-Kantenlänge in review_gui.py passen (sonst nur Cache-Miss, kein Fehler).
_REVIEW_THUMB_EDGE = 120


def _prewarm_review_thumbs(paths: list[Path]) -> None:
    """Erzeugt die Vorschau-Thumbnails der Auswahl im Hintergrund vor, damit
    „Auswahl prüfen" schon beim ersten Öffnen flüssig ist. Blockiert den Export nicht."""
    if not paths:
        return

    def _worker() -> None:
        try:
            from .utils import warm_thumb_cache

            warm_thumb_cache(paths, _REVIEW_THUMB_EDGE)
        except Exception:
            pass

    try:
        import threading

        threading.Thread(target=_worker, daemon=True).start()
    except Exception:
        pass


def copy_aside_pool(photos: list[Photo], output_dir: Path) -> int:
    """Kopiert alle Aside-Dokumente in optional_dokumente/ (Pool zum späteren Einfügen)."""
    aside = [p for p in photos if getattr(p, "is_aside", False) and not p.is_duplicate]
    pool_root = output_dir / "optional_dokumente"
    aside_sorted = sorted(
        aside,
        key=lambda p: (
            p.aside_type or "",
            p.datetime_taken.isoformat() if p.datetime_taken else "",
            p.filename,
        ),
    )
    with _staged_directory(pool_root) as staging:
        for n, photo in enumerate(aside_sorted, start=1):
            kind = photo.aside_type or "dokument"
            dest_name = f"{n:03d}_{kind}_{photo.filename}"
            shutil.copy2(photo.path, staging / dest_name)
    if not aside:
        pool_root.rmdir()
    return len(aside_sorted)


def write_markdown_overview(
    photos: list[Photo],
    plan: BookPlan,
    order: list[tuple[int, str, str]],
    path: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Fotobuch – Inhaltsverzeichnis", ""]

    transit_by_after = {t.chapter_index: t for t in plan.transits}
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for idx, _folder, ctype in order:
        region = photos[idx].region or ""
        counts[(region, ctype)] += 1

    for r_idx, region in enumerate(plan.regions):
        main_count = counts.get((region.name, "Hauptteil"), 0)
        food_count = counts.get((region.name, "Essen"), 0)
        start = region.start_time.strftime("%Y-%m-%d") if region.start_time else "?"
        end = region.end_time.strftime("%Y-%m-%d") if region.end_time else "?"
        lines.append(f"## Kapitel {r_idx + 1}: {region.name}")
        lines.append(f"- Zeitraum: {start} – {end}")
        lines.append(f"- Hauptteil: {main_count} Bilder")
        lines.append(f"- Essen: {food_count} Bilder")
        lines.append("")

        if r_idx in transit_by_after:
            t = transit_by_after[r_idx]
            t_key = f"Transit:{t.from_region}->{t.to_region}"
            t_count = counts.get((t_key, "Transit"), 0)
            lines.append(f"## Transit: {t.name}")
            lines.append(f"- Bilder: {t_count}")
            lines.append("")

    aside = [p for p in photos if getattr(p, "is_aside", False) and not p.is_duplicate]
    if aside:
        from collections import Counter

        by_type = Counter(p.aside_type or "dokument" for p in aside)
        selected_aside = sum(1 for p in aside if p.is_selected)
        lines.append("## Optional: Dokumente & Screenshots")
        lines.append(
            f"- Im Pool: {len(aside)} Dateien "
            f"({', '.join(f'{k}: {v}' for k, v in sorted(by_type.items()))})"
        )
        lines.append(f"- Davon ins Buch übernommen: {selected_aside}")
        lines.append("- Pool-Ordner: `optional_dokumente/` (alles zum Durchschauen)")
        lines.append("- Ins Buch übernommen → `selected/99_Optional_Dokumente/`")
        lines.append("")

    selected_total = sum(1 for p in photos if p.is_selected)
    lines.append("---")
    lines.append(f"Gesamt ausgewählt: {selected_total} Bilder")
    lines.append(f"Gesamt gescannt: {len(photos)} Bilder")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
