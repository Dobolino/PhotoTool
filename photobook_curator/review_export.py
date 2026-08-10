"""Manuelle Nachkontrolle: Auswahl anpassen und Export neu schreiben."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .documents import ASIDE_FOLDER
from .models import BookPlan, Photo, Region, TransitSection
from .output import copy_aside_pool, copy_selected, write_csv, write_markdown_overview


def rebuild_order_from_kept(
    photos: list[Photo],
    kept_indices: list[int],
) -> list[tuple[int, str, str]]:
    """Baut Buchreihenfolge aus manuell behaltenen Indizes."""

    def sort_key(i: int) -> tuple:
        p = photos[i]
        pos = p.book_position if p.book_position is not None else 10_000_000
        dt = p.datetime_taken or datetime.max
        return (pos, dt, i)

    ordered = sorted(set(kept_indices), key=sort_key)

    folder_order: list[str] = []
    by_folder: dict[str, list[int]] = defaultdict(list)
    for i in ordered:
        folder = photos[i].chapter_folder or _guess_folder(photos[i])
        photos[i].chapter_folder = folder
        if folder not in by_folder:
            folder_order.append(folder)
        by_folder[folder].append(i)

    order: list[tuple[int, str, str]] = []
    for folder in folder_order:
        members = sorted(
            by_folder[folder],
            key=lambda i: photos[i].datetime_taken or datetime.min,
        )
        for i in members:
            ctype = photos[i].chapter_type or _guess_chapter_type(folder)
            photos[i].chapter_type = ctype
            order.append((i, folder, ctype))
    return order


def _guess_folder(photo: Photo) -> str:
    if photo.chapter_folder:
        return photo.chapter_folder
    if photo.region and photo.region.startswith("Transit:"):
        body = photo.region.split(":", 1)[1]
        a, _, b = body.partition("->")
        return f"Transit_{a}-{b}".replace(" ", "-")
    region = (photo.region or "Unbestimmt").replace(" ", "-")
    if photo.scene_type == "essen" or photo.chapter_type == "Essen":
        return f"{region}/essen"
    return f"{region}/hauptteil"


def _guess_chapter_type(folder: str) -> str:
    if "Transit" in folder:
        return "Transit"
    if folder.endswith("/essen") or folder.endswith("\\essen"):
        return "Essen"
    return "Hauptteil"


def apply_manual_selection(
    photos: list[Photo],
    plan: BookPlan,
    kept_indices: list[int],
    output_dir: Path,
) -> list[tuple[int, str, str]]:
    """Setzt is_selected/book_position neu und schreibt CSV, Ordner, Markdown."""
    kept = set(kept_indices)
    for i, photo in enumerate(photos):
        was_selected = photo.is_selected
        photo.is_selected = i in kept
        if i in kept:
            if "manual_reject" in photo.flags:
                photo.flags = [f for f in photo.flags if f != "manual_reject"]
            if was_selected is False and "manual_add" not in photo.flags:
                photo.add_flag("manual_add")
            # Aside → eigenes Optional-Kapitel im Buch
            if getattr(photo, "is_aside", False):
                photo.chapter_folder = ASIDE_FOLDER
                photo.chapter_type = "Optional"
                photo.region = photo.region or "Optional"
        else:
            photo.book_position = None
            if was_selected and "manual_reject" not in photo.flags:
                photo.add_flag("manual_reject")

    order = rebuild_order_from_kept(photos, list(kept))
    for pos, (idx, folder, ctype) in enumerate(order, start=1):
        photos[idx].book_position = pos
        photos[idx].chapter_folder = folder
        photos[idx].chapter_type = ctype
        photos[idx].is_selected = True

    write_csv(photos, output_dir / "photos_analysis.csv")
    copy_selected(photos, order, output_dir)
    copy_aside_pool(photos, output_dir)
    write_markdown_overview(photos, plan, order, output_dir / "inhaltsverzeichnis.md")
    return order


def plan_from_photos(photos: list[Photo]) -> BookPlan:
    """Rekonstruiert eine grobe BookPlan-Struktur aus Foto-Metadaten."""
    region_names: list[str] = []
    region_indices: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(photos):
        if not p.region or p.region.startswith("Transit:") or p.region == "Unbestimmt":
            continue
        if p.region not in region_indices:
            region_names.append(p.region)
        region_indices[p.region].append(i)

    def region_start(name: str) -> datetime:
        times = [
            photos[i].datetime_taken
            for i in region_indices[name]
            if photos[i].datetime_taken
        ]
        return min(times) if times else datetime.max

    region_names.sort(key=region_start)
    regions: list[Region] = []
    for idx, name in enumerate(region_names):
        indices = region_indices[name]
        times = [photos[i].datetime_taken for i in indices if photos[i].datetime_taken]
        start = min(times) if times else None
        end = max(times) if times else None
        day_count = 1
        if start and end:
            day_count = max(1, (end.date() - start.date()).days + 1)
        regions.append(
            Region(
                name=name,
                photo_indices=indices,
                start_time=start,
                end_time=end,
                day_count=day_count,
                chapter_index=idx,
            )
        )

    transit_groups: dict[str, list[int]] = defaultdict(list)
    for i, p in enumerate(photos):
        if p.region and p.region.startswith("Transit:"):
            transit_groups[p.region].append(i)

    transits: list[TransitSection] = []
    for key, indices in transit_groups.items():
        body = key.split(":", 1)[1]
        a, _, b = body.partition("->")
        chapter_index = next((r.chapter_index for r in regions if r.name == a), 0)
        transits.append(
            TransitSection(
                from_region=a,
                to_region=b or "?",
                photo_indices=indices,
                chapter_index=chapter_index,
            )
        )
    transits.sort(key=lambda t: t.chapter_index)
    return BookPlan(regions=regions, transits=transits)


def rebuild_selection_from_analysis(
    photos: list[Photo],
    target_n: int,
    *,
    food_ratio: float = 0.15,
    max_landmarks: int = 3,
    similarity_threshold: float = 0.92,
    coverage_intensity: float = 0.0,
    people_balance_intensity: float = 0.0,
    candidate_factor: float = 4.0,
) -> tuple[BookPlan, list[tuple[int, str, str]]]:
    """
    Erzeugt eine Buchauswahl aus bereits analysierter CSV-Daten **ohne neue KI**.
    Nutzt vorhandene Scores/Kandidaten (z. B. nach abgebrochenem Lauf).
    """
    from .selection import build_book_order, distribute_quotas, mark_candidates

    for p in photos:
        p.is_selected = False
        p.book_position = None

    plan = plan_from_photos(photos)
    # Alle Fotos den Regionen zuordnen (auch Nicht-Kandidaten), sonst leere Quotas
    if not plan.regions and not plan.transits:
        # Fallback: eine Kunst-Region
        from .models import Region

        plan.regions = [
            Region(
                name="Album",
                photo_indices=list(range(len(photos))),
                chapter_index=0,
            )
        ]

    distribute_quotas(photos, plan, target_n)
    # Kandidaten neu setzen (nutzt technical/aesthetic scores aus der CSV)
    for p in photos:
        p.is_candidate = False
    mark_candidates(
        photos,
        plan,
        target_n=target_n,
        candidate_factor=candidate_factor,
    )
    order = build_book_order(
        photos,
        plan,
        food_ratio=food_ratio,
        max_landmarks=max_landmarks,
        similarity_threshold=similarity_threshold,
        coverage_intensity=coverage_intensity,
        people_balance_intensity=people_balance_intensity,
    )
    return plan, order


def analysis_has_ai_scores(photos: list[Photo]) -> bool:
    return any(p.aesthetic_score is not None for p in photos)


def load_photos_from_csv(csv_path: Path) -> list[Photo]:
    """Lädt Fotozeilen aus der Analyse-CSV für die Review-Oberfläche."""
    photos: list[Photo] = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            path = Path(row.get("path") or "")
            date_s = (row.get("date") or "").strip()
            time_s = (row.get("time") or "").strip()
            taken: Optional[datetime] = None
            if date_s and time_s:
                try:
                    taken = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    taken = None
            elif date_s:
                try:
                    taken = datetime.strptime(date_s, "%Y-%m-%d")
                except ValueError:
                    taken = None

            def _float(key: str) -> Optional[float]:
                v = (row.get(key) or "").strip()
                if v == "":
                    return None
                try:
                    return float(v)
                except ValueError:
                    return None

            def _int(key: str, default: int = 0) -> int:
                v = (row.get(key) or "").strip()
                if v == "":
                    return default
                try:
                    return int(float(v))
                except ValueError:
                    return default

            def _bool(key: str) -> bool:
                return (row.get(key) or "").strip().lower() in ("true", "1", "yes")

            bp_raw = (row.get("book_position") or "").strip()
            photo = Photo(
                path=path,
                filename=row.get("filename") or path.name,
                datetime_taken=taken,
                camera_model=(row.get("camera_model") or None) or None,
                gps_lat=_float("gps_lat"),
                gps_lon=_float("gps_lon"),
                width=_int("width"),
                height=_int("height"),
                sharpness=float(_float("sharpness") or 0),
                exposure_mean=float(_float("exposure_mean") or 0),
                contrast=float(_float("contrast") or 0),
                saturation=float(_float("saturation") or 0),
                face_count=_int("face_count"),
                technical_score=float(_float("technical_score") or 0),
                aesthetic_score=_float("aesthetic_score"),
                landmark=(row.get("landmark") or None) or None,
                scene_type=(row.get("scene_type") or None) or None,
                mood=(row.get("mood") or None) or None,
                quality_issue=(row.get("quality_issue") or None) or None,
                final_score=float(_float("final_score") or 0),
                is_candidate=_bool("is_candidate"),
                is_selected=_bool("is_selected"),
                chapter_type=(row.get("chapter_type") or None) or None,
                book_position=_int("book_position") if bp_raw else None,
                chapter_folder=(row.get("chapter_folder") or None) or None,
                is_duplicate=_bool("is_duplicate"),
                is_burst_reject=_bool("is_burst_reject"),
                burst_group_id=_int("burst_group_id") if (row.get("burst_group_id") or "").strip() else None,
                is_screenshot=_bool("is_screenshot"),
                is_aside=_bool("is_aside"),
                aside_type=(row.get("aside_type") or None) or None,
                assigned_by_time=_bool("assigned_by_time"),
                eyes_closed=_bool("eyes_closed"),
                face_cut_off=_bool("face_cut_off"),
                face_too_small=_bool("face_too_small"),
                bad_face=_bool("bad_face"),
                finger_on_lens=_bool("finger_on_lens"),
                is_accidental=_bool("is_accidental"),
                is_weak_night=_bool("is_weak_night"),
                person_cluster_ids=[
                    int(x)
                    for x in (row.get("person_cluster_ids") or "").split("|")
                    if x.strip().isdigit()
                ],
                flags=[f for f in (row.get("flags") or "").split("|") if f],
                region=(row.get("region") or None) or None,
            )
            kr = (row.get("keep_recommendation") or "").strip().lower()
            if kr in ("true", "1", "yes"):
                photo.keep_recommendation = True
            elif kr in ("false", "0", "no"):
                photo.keep_recommendation = False
            photos.append(photo)
    return photos


def chapter_sections(photos: list[Photo], include_indices: list[int]) -> list[tuple[str, str, list[int]]]:
    """
    Gruppiert Indizes nach Kapitel.
    Returns list of (title, chapter_folder, indices).
    """
    ordered = sorted(
        include_indices,
        key=lambda i: (
            photos[i].book_position if photos[i].book_position is not None else 10**9,
            photos[i].datetime_taken or datetime.max,
            i,
        ),
    )
    sections: list[tuple[str, str, list[int]]] = []
    by_folder: dict[str, list[int]] = defaultdict(list)
    folder_order: list[str] = []
    for i in ordered:
        folder = photos[i].chapter_folder or _guess_folder(photos[i])
        if folder not in by_folder:
            folder_order.append(folder)
        by_folder[folder].append(i)
    for folder in folder_order:
        title = folder.replace("/", " · ").replace("\\", " · ").replace("_", " ")
        sections.append((title, folder, by_folder[folder]))
    return sections


def alternatives_for_index(
    photos: list[Photo],
    idx: int,
    kept: set[int],
    limit: int = 4,
) -> list[int]:
    """Beste Alternativen zum aktuellen Bild (Review-Diashow), ohne kept."""
    if idx < 0 or idx >= len(photos):
        return []
    folder = photos[idx].chapter_folder or ""
    if not folder:
        # Fallback: gleiche Region / Szene
        region = photos[idx].region
        pool = [
            i
            for i, p in enumerate(photos)
            if i not in kept
            and i != idx
            and p.is_candidate
            and not p.is_duplicate
            and not getattr(p, "is_burst_reject", False)
            and not getattr(p, "is_aside", False)
            and (not region or p.region == region)
        ]
        pool.sort(
            key=lambda i: photos[i].final_score or photos[i].technical_score,
            reverse=True,
        )
        return pool[:limit]
    alts = candidate_alternatives(
        photos, folder, limit=max(limit * 3, 12), exclude=kept | {idx}
    )
    out = [i for i in alts if i not in kept and i != idx]
    if len(out) < limit:
        # ergänzen mit Kandidaten derselben Region
        region = photos[idx].region
        extra = [
            i
            for i, p in enumerate(photos)
            if i not in kept
            and i != idx
            and i not in out
            and p.is_candidate
            and not p.is_duplicate
            and not getattr(p, "is_aside", False)
            and (p.region == region or (p.chapter_folder or "") == folder)
        ]
        extra.sort(
            key=lambda i: photos[i].final_score or photos[i].technical_score,
            reverse=True,
        )
        out.extend(extra)
    return out[:limit]


def candidate_alternatives(
    photos: list[Photo],
    chapter_folder: str,
    limit: int = 8,
    exclude: set[int] | None = None,
) -> list[int]:
    """Nicht ausgewählte Kandidaten derselben Kapitel-Region."""
    blocked = set(exclude or ())
    members = [
        i
        for i, p in enumerate(photos)
        if p.chapter_folder == chapter_folder or (
            p.is_selected and (p.chapter_folder or "").startswith(chapter_folder.split("/")[0])
        )
    ]
    regions = {photos[i].region for i in members if photos[i].region}
    if not regions:
        # Fallback: aus Ordnernamen
        base = chapter_folder.split("/")[0]
        if "Transit" in base:
            regions = {
                p.region
                for p in photos
                if p.region and p.region.startswith("Transit:")
            }
        else:
            regions = {p.region for p in photos if p.region and p.region.replace(" ", "-") in base}

    want_food = "/essen" in chapter_folder.replace("\\", "/")
    is_transit = "Transit" in chapter_folder

    pool: list[int] = []
    for i, p in enumerate(photos):
        if i in blocked:
            continue
        if (
            p.is_selected
            or p.is_duplicate
            or getattr(p, "is_burst_reject", False)
            or not p.is_candidate
        ):
            continue
        if p.region not in regions:
            continue
        if is_transit:
            if not (p.region and p.region.startswith("Transit:")):
                continue
        elif want_food:
            if p.scene_type != "essen":
                continue
        else:
            if p.scene_type == "essen":
                continue
        pool.append(i)

    pool.sort(key=lambda i: photos[i].final_score or photos[i].technical_score, reverse=True)
    return pool[:limit]
