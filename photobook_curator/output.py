"""CSV-, Ordner- und Markdown-Ausgabe."""

from __future__ import annotations

import csv
import shutil
from collections import defaultdict
from pathlib import Path

from .models import BookPlan, Photo


CSV_FIELDS = [
    "filename",
    "path",
    "date",
    "time",
    "region",
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
    "person_cluster_ids",
    "technical_score",
    "aesthetic_score",
    "landmark",
    "quality_issue",
    "keep_recommendation",
    "final_score",
    "flags",
    "is_candidate",
    "is_selected",
    "book_position",
    "chapter_folder",
    "is_duplicate",
    "is_burst_reject",
    "burst_group_id",
    "is_screenshot",
    "is_aside",
    "aside_type",
    "assigned_by_time",
    "fine_cluster_id",
]


def write_csv(photos: list[Photo], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for photo in photos:
            writer.writerow(photo.to_csv_row())


def copy_selected(
    photos: list[Photo],
    order: list[tuple[int, str, str]],
    output_dir: Path,
) -> None:
    selected_root = output_dir / "selected"
    if selected_root.exists():
        shutil.rmtree(selected_root)
    selected_root.mkdir(parents=True, exist_ok=True)

    counters: dict[str, int] = {}
    for idx, folder, _ctype in order:
        photo = photos[idx]
        dest_dir = selected_root / folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        counters[folder] = counters.get(folder, 0) + 1
        n = counters[folder]
        dest_name = f"{n:03d}_{photo.filename}"
        shutil.copy2(photo.path, dest_dir / dest_name)


def copy_aside_pool(photos: list[Photo], output_dir: Path) -> int:
    """Kopiert alle Aside-Dokumente in optional_dokumente/ (Pool zum späteren Einfügen)."""
    aside = [p for p in photos if getattr(p, "is_aside", False) and not p.is_duplicate]
    pool_root = output_dir / "optional_dokumente"
    if pool_root.exists():
        shutil.rmtree(pool_root)
    if not aside:
        return 0
    pool_root.mkdir(parents=True, exist_ok=True)
    aside_sorted = sorted(
        aside,
        key=lambda p: (
            p.aside_type or "",
            p.datetime_taken.isoformat() if p.datetime_taken else "",
            p.filename,
        ),
    )
    for n, photo in enumerate(aside_sorted, start=1):
        kind = photo.aside_type or "dokument"
        dest_name = f"{n:03d}_{kind}_{photo.filename}"
        shutil.copy2(photo.path, pool_root / dest_name)
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
