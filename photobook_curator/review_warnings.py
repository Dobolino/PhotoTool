"""Warnungen für die Review-Oberfläche (Tageslücken, Personen, Auflösung)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .models import Photo

LOW_RES_MIN_SIDE = 1000


@dataclass(frozen=True)
class ReviewWarning:
    """Eine Warnung: i18n-Key + Format-Args."""

    key: str
    params: dict


def collect_review_warnings(
    photos: list[Photo],
    kept: Iterable[int],
    *,
    folder: str | None = None,
) -> list[ReviewWarning]:
    """
    Erzeugt priorisierte Warnungen für die aktuelle Auswahl.
    folder: wenn gesetzt, zusätzlich kapitelbezogene Hinweise.
    """
    kept_set = {int(i) for i in kept}
    kept_photos = [photos[i] for i in sorted(kept_set) if 0 <= i < len(photos)]
    warnings: list[ReviewWarning] = []
    if not kept_photos and not folder:
        return warnings

    # Tageslücken über die ganze Reise (Tage mit Fotos vs. Tage in der Auswahl)
    all_days: set[date] = set()
    kept_days: set[date] = set()
    for i, p in enumerate(photos):
        if getattr(p, "is_aside", False):
            continue
        if p.datetime_taken is None:
            continue
        d = p.datetime_taken.date()
        all_days.add(d)
        if i in kept_set:
            kept_days.add(d)
    gaps = sorted(all_days - kept_days)
    if gaps and len(all_days) >= 2:
        warnings.append(
            ReviewWarning(
                "warn_day_gaps",
                {"n": len(gaps), "sample": gaps[0].isoformat()},
            )
        )

    # Personen, die irgendwo erkannt wurden, aber in keiner Auswahl vorkommen
    all_people: set[int] = set()
    kept_people: set[int] = set()
    for i, p in enumerate(photos):
        for pid in p.person_cluster_ids or []:
            all_people.add(int(pid))
            if i in kept_set:
                kept_people.add(int(pid))
    missing_people = all_people - kept_people
    if missing_people and len(all_people) >= 2:
        warnings.append(
            ReviewWarning("warn_people_missing", {"n": len(missing_people)})
        )

    # Niedrige Auflösung in der Auswahl
    low_res = [
        p
        for p in kept_photos
        if (p.width or 0) > 0
        and (p.height or 0) > 0
        and min(p.width, p.height) < LOW_RES_MIN_SIDE
    ]
    if low_res:
        warnings.append(ReviewWarning("warn_low_res", {"n": len(low_res)}))

    # Kapitel: leer / dünn
    if folder:
        in_folder = [
            p
            for p in kept_photos
            if (p.chapter_folder or "") == folder
        ]
        if len(in_folder) == 0:
            warnings.append(ReviewWarning("warn_empty_chapter", {}))
        elif len(in_folder) == 1:
            warnings.append(ReviewWarning("warn_thin_chapter", {}))

    return warnings
